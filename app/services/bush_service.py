from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from html import escape
from typing import Any, TypeVar

from sqlalchemy import func, select

from app.database.models.bush import Bush
from app.database.models.enums import (
    AuditAction,
    EntityType,
    UserRole,
)
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories import (
    AuditContext,
    Repositories,
)
from app.services.access import (
    AccessDeniedError,
    AccessService,
)


EnumType = TypeVar(
    "EnumType",
    bound=Enum,
)


@dataclass(slots=True, frozen=True)
class BushView:
    """
    Представлення куща.
    """

    id: int

    name: str
    code: str | None
    description: str | None

    is_active: bool

    active_store_count: int
    total_store_count: int

    bush_admin_count: int
    lion_count: int

    created_at: datetime | None
    updated_at: datetime | None

    raw_bush: Bush


@dataclass(slots=True, frozen=True)
class BushCreateData:
    """
    Дані для створення куща.
    """

    name: str
    code: str | None = None
    description: str | None = None

    is_active: bool = True


@dataclass(slots=True, frozen=True)
class BushChangeResult:
    """
    Результат створення або редагування куща.
    """

    bush: Bush
    view: BushView

    was_created: bool
    was_changed: bool

    previous_values: dict[str, Any]
    current_values: dict[str, Any]

    audit_created: bool


@dataclass(slots=True, frozen=True)
class BushStatusChangeResult:
    """
    Результат активації або деактивації куща.
    """

    bush: Bush

    previous_active: bool
    current_active: bool

    was_changed: bool

    stores_detached: int
    bindings_deactivated: int

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class BushStoreMoveResult:
    """
    Результат переміщення ТТ між кущами.
    """

    store: Store

    previous_bush_id: int | None
    current_bush_id: int | None

    was_changed: bool

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class BushStatistics:
    """
    Статистика одного куща.
    """

    bush_id: int
    bush_name: str

    total_stores: int
    active_stores: int
    inactive_stores: int

    bush_admins: int
    lions: int

    cities: tuple[str, ...]

    stores_without_cluster: int


@dataclass(slots=True, frozen=True)
class BushBulkItemResult:
    """
    Результат одного куща в масовій операції.
    """

    name: str
    code: str | None

    success: bool
    was_created: bool
    was_changed: bool

    bush_id: int | None
    error: str | None


@dataclass(slots=True, frozen=True)
class BushBulkResult:
    """
    Результат масового створення кущів.
    """

    total_count: int

    success_count: int
    failed_count: int

    created_count: int
    changed_count: int
    unchanged_count: int

    items: tuple[
        BushBulkItemResult,
        ...,
    ]


class BushService:
    """
    Сервіс керування кущами.

    Підтримує:

    - створення куща;
    - редагування;
    - перегляд;
    - список кущів;
    - пошук;
    - статистику;
    - переміщення ТТ між кущами;
    - вилучення ТТ із куща;
    - деактивацію;
    - відновлення;
    - масове створення;
    - AuditLog.

    Кущ фізично не видаляється.

    Для вимкненого куща:

        is_active = False

    Це дозволяє не втрачати історичні дані.
    """

    MAX_BULK_SIZE = 100

    def __init__(
        self,
        repositories: Repositories,
        *,
        access_service: AccessService | None = None,
    ) -> None:
        self.repositories = repositories
        self.session = repositories.session

        self.access = (
            access_service
            or AccessService(repositories)
        )

    # ==========================================
    # ОДИН КУЩ
    # ==========================================

    async def get_bush(
        self,
        *,
        user: User,
        bush_id: int,
        include_inactive: bool = False,
    ) -> BushView:
        """
        Повертає один доступний кущ.
        """

        bush = await self.get_bush_or_raise(
            bush_id,
            include_inactive=include_inactive,
        )

        await self.access.require_bush_view(
            user,
            bush.id,
        )

        return await self.build_bush_view(
            bush
        )

    # ==========================================
    # СПИСОК КУЩІВ
    # ==========================================

    async def get_bushes(
        self,
        *,
        user: User,
        active_only: bool = True,
    ) -> list[BushView]:
        """
        Повертає доступні користувачу кущі.
        """

        self.access.ensure_active_user(user)

        accessible_bush_ids = (
            await self.resolve_accessible_bush_ids(
                user
            )
        )

        if accessible_bush_ids == set():
            return []

        conditions: list[Any] = []

        if accessible_bush_ids is not None:
            conditions.append(
                Bush.id.in_(
                    accessible_bush_ids
                )
            )

        if (
            active_only
            and hasattr(Bush, "is_active")
        ):
            conditions.append(
                Bush.is_active.is_(True)
            )

        statement = (
            select(Bush)
            .where(*conditions)
            .order_by(
                *self.bush_order_columns()
            )
        )

        result = await self.session.scalars(
            statement
        )

        bushes = list(
            result.unique().all()
        )

        return [
            await self.build_bush_view(bush)
            for bush in bushes
        ]

    # ==========================================
    # ПОШУК КУЩІВ
    # ==========================================

    async def search_bushes(
        self,
        *,
        user: User,
        query: str,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[BushView]:
        """
        Пошук за назвою або кодом.
        """

        if limit < 1 or limit > 500:
            raise ValueError(
                "Ліміт повинен бути "
                "від 1 до 500."
            )

        normalized_query = (
            self.normalize_required_text(
                query,
                field_name="Пошуковий запит",
                max_length=200,
            )
        )

        accessible_bush_ids = (
            await self.resolve_accessible_bush_ids(
                user
            )
        )

        if accessible_bush_ids == set():
            return []

        conditions: list[Any] = []

        searchable_columns = [
            self.model_column(
                "name",
                "title",
            ),
            self.model_column(
                "code",
                "slug",
            ),
            self.model_column(
                "description",
            ),
        ]

        searchable_columns = [
            column
            for column in searchable_columns
            if column is not None
        ]

        if searchable_columns:
            value = f"%{normalized_query}%"

            conditions.append(
                func.coalesce(
                    searchable_columns[0],
                    "",
                ).ilike(value)
                if len(searchable_columns) == 1
                else self.build_search_condition(
                    searchable_columns,
                    value,
                )
            )

        if accessible_bush_ids is not None:
            conditions.append(
                Bush.id.in_(
                    accessible_bush_ids
                )
            )

        if (
            active_only
            and hasattr(Bush, "is_active")
        ):
            conditions.append(
                Bush.is_active.is_(True)
            )

        statement = (
            select(Bush)
            .where(*conditions)
            .order_by(
                *self.bush_order_columns()
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return [
            await self.build_bush_view(bush)
            for bush
            in result.unique().all()
        ]

    # ==========================================
    # СТВОРЕННЯ
    # ==========================================

    async def create_bush(
        self,
        *,
        actor: User,
        name: str,
        code: str | None = None,
        description: str | None = None,
        is_active: bool = True,
        reason: str | None = None,
        created_at: datetime | None = None,
    ) -> BushChangeResult:
        """
        Створює новий кущ.
        """

        self.access.require_network_management(
            actor
        )

        now = created_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="created_at",
        )

        normalized_name = (
            self.normalize_required_text(
                name,
                field_name="Назва куща",
                max_length=255,
            )
        )

        normalized_code = (
            self.normalize_optional_code(code)
        )

        normalized_description = (
            self.normalize_optional_text(
                description,
                max_length=1000,
            )
        )

        await self.ensure_unique_bush(
            name=normalized_name,
            code=normalized_code,
        )

        payload = {
            "name": normalized_name,
            "title": normalized_name,

            "code": normalized_code,
            "slug": normalized_code,

            "description": (
                normalized_description
            ),

            "is_active": bool(is_active),

            "created_by_id": actor.id,
            "updated_by_id": actor.id,

            "created_at": now,
            "updated_at": now,
        }

        repository_result = (
            await self.try_repository_create(
                payload
            )
        )

        if repository_result is not None:
            bush = self.extract_bush(
                repository_result
            )

        else:
            bush = Bush(
                **self.filter_model_payload(
                    payload
                )
            )

            self.session.add(bush)

            await self.session.flush()

        if bush is None:
            raise RuntimeError(
                "Не вдалося створити кущ."
            )

        current_values = (
            self.bush_snapshot(bush)
        )

        await self.log_bush_change(
            actor=actor,
            bush=bush,
            description="Створено новий кущ",
            reason=reason,
            previous_values={},
            current_values=current_values,
            was_created=True,
        )

        return BushChangeResult(
            bush=bush,
            view=await self.build_bush_view(
                bush
            ),
            was_created=True,
            was_changed=True,
            previous_values={},
            current_values=current_values,
            audit_created=True,
        )

    # ==========================================
    # РЕДАГУВАННЯ
    # ==========================================

    async def update_bush(
        self,
        *,
        actor: User,
        bush_id: int,
        name: str | None = None,
        code: str | None = None,
        description: str | None = None,
        reason: str,
        updated_at: datetime | None = None,
    ) -> BushChangeResult:
        """
        Редагує кущ.

        None означає не змінювати поле.

        Порожній description очищає опис.
        """

        now = updated_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="updated_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        bush = await self.get_bush_or_raise(
            bush_id,
            include_inactive=True,
            for_update=True,
        )

        decision = await self.access.can_manage_bush(
            actor,
            bush.id,
        )

        decision.raise_if_denied()

        previous_values = (
            self.bush_snapshot(bush)
        )

        if name is not None:
            normalized_name = (
                self.normalize_required_text(
                    name,
                    field_name="Назва куща",
                    max_length=255,
                )
            )

            await self.ensure_unique_bush(
                name=normalized_name,
                exclude_bush_id=bush.id,
            )

            self.set_first_existing_attribute(
                bush,
                normalized_name,
                "name",
                "title",
            )

        if code is not None:
            normalized_code = (
                self.normalize_optional_code(code)
            )

            if normalized_code is not None:
                await self.ensure_unique_bush(
                    code=normalized_code,
                    exclude_bush_id=bush.id,
                )

            self.set_first_existing_attribute(
                bush,
                normalized_code,
                "code",
                "slug",
            )

        if description is not None:
            normalized_description = (
                self.normalize_optional_text(
                    description,
                    max_length=1000,
                )
            )

            self.set_first_existing_attribute(
                bush,
                normalized_description,
                "description",
            )

        self.set_first_existing_attribute(
            bush,
            actor.id,
            "updated_by_id",
            "modified_by_id",
        )

        self.set_first_existing_attribute(
            bush,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(bush)
        await self.session.flush()

        current_values = (
            self.bush_snapshot(bush)
        )

        was_changed = (
            previous_values
            != current_values
        )

        if was_changed:
            await self.log_bush_change(
                actor=actor,
                bush=bush,
                description=(
                    "Змінено дані куща"
                ),
                reason=normalized_reason,
                previous_values=previous_values,
                current_values=current_values,
                was_created=False,
            )

        return BushChangeResult(
            bush=bush,
            view=await self.build_bush_view(
                bush
            ),
            was_created=False,
            was_changed=was_changed,
            previous_values=previous_values,
            current_values=current_values,
            audit_created=was_changed,
        )

    # ==========================================
    # ПЕРЕМІЩЕННЯ ТТ
    # ==========================================

    async def move_store(
        self,
        *,
        actor: User,
        store_id: int,
        target_bush_id: int | None,
        reason: str,
        changed_at: datetime | None = None,
    ) -> BushStoreMoveResult:
        """
        Переміщує ТТ в інший кущ.

        target_bush_id=None:
        прибирає ТТ із куща.
        """

        now = changed_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        store = await self.get_store_or_raise(
            store_id,
            for_update=True,
        )

        previous_bush_id = getattr(
            store,
            "bush_id",
            None,
        )

        if previous_bush_id is not None:
            old_decision = (
                await self.access.can_manage_bush(
                    actor,
                    previous_bush_id,
                )
            )

            old_decision.raise_if_denied()

        else:
            self.access.require_network_management(
                actor
            )

        if target_bush_id is not None:
            await self.get_bush_or_raise(
                target_bush_id
            )

            new_decision = (
                await self.access.can_manage_bush(
                    actor,
                    target_bush_id,
                )
            )

            new_decision.raise_if_denied()

        else:
            self.access.require_network_management(
                actor
            )

        if previous_bush_id == target_bush_id:
            return BushStoreMoveResult(
                store=store,
                previous_bush_id=(
                    previous_bush_id
                ),
                current_bush_id=(
                    target_bush_id
                ),
                was_changed=False,
                changed_at=now,
                changed_by_id=actor.id,
                reason=normalized_reason,
            )

        store.bush_id = target_bush_id

        self.set_first_existing_attribute(
            store,
            actor.id,
            "updated_by_id",
            "modified_by_id",
        )

        self.set_first_existing_attribute(
            store,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(store)
        await self.session.flush()

        await self.log_store_move(
            actor=actor,
            store=store,
            reason=normalized_reason,
            previous_bush_id=(
                previous_bush_id
            ),
            current_bush_id=(
                target_bush_id
            ),
        )

        return BushStoreMoveResult(
            store=store,
            previous_bush_id=(
                previous_bush_id
            ),
            current_bush_id=(
                target_bush_id
            ),
            was_changed=True,
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # УСІ ТТ КУЩА
    # ==========================================

    async def get_bush_stores(
        self,
        *,
        user: User,
        bush_id: int,
        active_only: bool = True,
    ) -> list[Store]:
        """
        Повертає магазини куща.
        """

        await self.access.require_bush_view(
            user,
            bush_id,
        )

        conditions = [
            Store.bush_id == bush_id
        ]

        if (
            active_only
            and hasattr(Store, "is_active")
        ):
            conditions.append(
                Store.is_active.is_(True)
            )

        statement = (
            select(Store)
            .where(*conditions)
            .order_by(
                *self.store_order_columns()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def get_statistics(
        self,
        *,
        user: User,
        bush_id: int,
    ) -> BushStatistics:
        """
        Формує статистику куща.
        """

        bush = await self.get_bush_or_raise(
            bush_id,
            include_inactive=True,
        )

        await self.access.require_bush_view(
            user,
            bush_id,
        )

        store_statement = (
            select(Store)
            .where(
                Store.bush_id == bush_id
            )
        )

        store_result = await self.session.scalars(
            store_statement
        )

        stores = list(
            store_result.unique().all()
        )

        active_stores = [
            store
            for store in stores
            if bool(
                getattr(
                    store,
                    "is_active",
                    True,
                )
            )
        ]

        cities = sorted(
            {
                city
                for store in stores
                if (
                    city
                    := self.get_text_attribute(
                        store,
                        "city",
                    )
                )
            }
        )

        stores_without_cluster = sum(
            getattr(
                store,
                "cluster_id",
                None,
            )
            is None
            for store in active_stores
        )

        bush_admin_count = (
            await self.count_bush_users_by_role(
                bush_id=bush_id,
                role=UserRole.BUSH_ADMIN,
            )
        )

        lion_count = (
            await self.count_bush_users_by_role(
                bush_id=bush_id,
                role=UserRole.LION,
            )
        )

        return BushStatistics(
            bush_id=bush.id,
            bush_name=self.bush_name(bush),

            total_stores=len(stores),
            active_stores=len(
                active_stores
            ),
            inactive_stores=(
                len(stores)
                - len(active_stores)
            ),

            bush_admins=bush_admin_count,
            lions=lion_count,

            cities=tuple(cities),

            stores_without_cluster=(
                stores_without_cluster
            ),
        )

    # ==========================================
    # ДЕАКТИВАЦІЯ
    # ==========================================

    async def deactivate_bush(
        self,
        *,
        actor: User,
        bush_id: int,
        reason: str,
        detach_stores: bool = False,
        deactivate_bindings: bool = True,
        changed_at: datetime | None = None,
    ) -> BushStatusChangeResult:
        """
        Деактивує кущ.

        За замовчуванням магазини залишаються
        прив’язаними до куща, але сам кущ
        стає неактивним.

        detach_stores=True:
        у магазинів bush_id стане None.
        """

        return await self.set_active_state(
            actor=actor,
            bush_id=bush_id,
            is_active=False,
            reason=reason,
            detach_stores=detach_stores,
            deactivate_bindings=(
                deactivate_bindings
            ),
            changed_at=changed_at,
        )

    async def reactivate_bush(
        self,
        *,
        actor: User,
        bush_id: int,
        reason: str,
        changed_at: datetime | None = None,
    ) -> BushStatusChangeResult:
        """
        Повторно активує кущ.
        """

        return await self.set_active_state(
            actor=actor,
            bush_id=bush_id,
            is_active=True,
            reason=reason,
            detach_stores=False,
            deactivate_bindings=False,
            changed_at=changed_at,
        )

    async def set_active_state(
        self,
        *,
        actor: User,
        bush_id: int,
        is_active: bool,
        reason: str,
        detach_stores: bool,
        deactivate_bindings: bool,
        changed_at: datetime | None,
    ) -> BushStatusChangeResult:
        """
        Змінює активність куща.
        """

        now = changed_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        bush = await self.get_bush_or_raise(
            bush_id,
            include_inactive=True,
            for_update=True,
        )

        decision = await self.access.can_manage_bush(
            actor,
            bush_id,
        )

        decision.raise_if_denied()

        previous_active = bool(
            getattr(
                bush,
                "is_active",
                True,
            )
        )

        if previous_active == is_active:
            return BushStatusChangeResult(
                bush=bush,
                previous_active=(
                    previous_active
                ),
                current_active=is_active,
                was_changed=False,
                stores_detached=0,
                bindings_deactivated=0,
                changed_at=now,
                changed_by_id=actor.id,
                reason=normalized_reason,
            )

        self.set_first_existing_attribute(
            bush,
            is_active,
            "is_active",
            "active",
        )

        if is_active:
            self.set_first_existing_attribute(
                bush,
                None,
                "deactivated_at",
            )

            self.set_first_existing_attribute(
                bush,
                None,
                "deactivated_by_id",
            )

        else:
            self.set_first_existing_attribute(
                bush,
                now,
                "deactivated_at",
            )

            self.set_first_existing_attribute(
                bush,
                actor.id,
                "deactivated_by_id",
            )

        self.set_first_existing_attribute(
            bush,
            normalized_reason,
            "deactivation_reason",
            "status_reason",
        )

        self.set_first_existing_attribute(
            bush,
            actor.id,
            "updated_by_id",
            "modified_by_id",
        )

        self.set_first_existing_attribute(
            bush,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(bush)
        await self.session.flush()

        stores_detached = 0
        bindings_deactivated = 0

        if not is_active:
            if detach_stores:
                stores_detached = (
                    await self.detach_all_stores(
                        bush_id=bush.id,
                        actor=actor,
                        changed_at=now,
                    )
                )

            if deactivate_bindings:
                bindings_deactivated = (
                    await self.deactivate_bush_bindings(
                        bush_id=bush.id,
                        actor=actor,
                        reason=normalized_reason,
                        changed_at=now,
                    )
                )

        await self.log_bush_change(
            actor=actor,
            bush=bush,
            description=(
                "Кущ активовано"
                if is_active
                else "Кущ деактивовано"
            ),
            reason=normalized_reason,
            previous_values={
                "is_active": previous_active,
            },
            current_values={
                "is_active": is_active,
                "stores_detached": (
                    stores_detached
                ),
                "bindings_deactivated": (
                    bindings_deactivated
                ),
            },
            was_created=False,
        )

        return BushStatusChangeResult(
            bush=bush,
            previous_active=previous_active,
            current_active=is_active,
            was_changed=True,
            stores_detached=stores_detached,
            bindings_deactivated=(
                bindings_deactivated
            ),
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # ВІД’ЄДНАННЯ ВСІХ ТТ
    # ==========================================

    async def detach_all_stores(
        self,
        *,
        bush_id: int,
        actor: User,
        changed_at: datetime,
    ) -> int:
        """
        Прибирає bush_id у всіх ТТ куща.
        """

        statement = (
            select(Store)
            .where(
                Store.bush_id == bush_id
            )
            .with_for_update()
        )

        result = await self.session.scalars(
            statement
        )

        stores = list(
            result.unique().all()
        )

        for store in stores:
            store.bush_id = None

            self.set_first_existing_attribute(
                store,
                actor.id,
                "updated_by_id",
                "modified_by_id",
            )

            self.set_first_existing_attribute(
                store,
                changed_at,
                "updated_at",
                "modified_at",
            )

            self.session.add(store)

        if stores:
            await self.session.flush()

        return len(stores)

    # ==========================================
    # ДЕАКТИВАЦІЯ ПРИВ’ЯЗОК КУЩА
    # ==========================================

    async def deactivate_bush_bindings(
        self,
        *,
        bush_id: int,
        actor: User,
        reason: str,
        changed_at: datetime,
    ) -> int:
        """
        Деактивує прив’язки адміністраторів
        і левів до куща.
        """

        repository = getattr(
            self.repositories,
            "bindings",
            None,
        )

        if repository is None:
            return 0

        method_names = (
            "deactivate_all_for_bush",
            "deactivate_bush_bindings",
            "remove_all_bush_bindings",
            "unbind_all_from_bush",
        )

        payload = {
            "bush_id": bush_id,

            "deactivated_by_id": actor.id,
            "removed_by_id": actor.id,

            "deactivated_at": changed_at,
            "removed_at": changed_at,

            "reason": reason,
        }

        for method_name in method_names:
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(method):
                continue

            result = method(
                **self.filter_method_kwargs(
                    method,
                    payload,
                )
            )

            if inspect.isawaitable(result):
                result = await result

            return self.result_to_count(
                result
            )

        return 0

    # ==========================================
    # КІЛЬКІСТЬ КОРИСТУВАЧІВ КУЩА
    # ==========================================

    async def count_bush_users_by_role(
        self,
        *,
        bush_id: int,
        role: UserRole,
    ) -> int:
        """
        Рахує активних користувачів ролі
        у конкретному кущі.
        """

        repository = getattr(
            self.repositories,
            "bindings",
            None,
        )

        if repository is None:
            return 0

        method_names = (
            "count_bush_users_by_role",
            "count_users_for_bush",
            "get_bush_users",
            "list_users_for_bush",
        )

        payload = {
            "bush_id": bush_id,
            "role": role,
            "target_role": role,
            "active_only": True,
        }

        for method_name in method_names:
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(method):
                continue

            result = method(
                **self.filter_method_kwargs(
                    method,
                    payload,
                )
            )

            if inspect.isawaitable(result):
                result = await result

            if isinstance(result, int):
                return max(result, 0)

            values = self.as_list(result)

            count = 0

            for item in values:
                user = (
                    item
                    if isinstance(item, User)
                    else getattr(
                        item,
                        "user",
                        None,
                    )
                )

                if not isinstance(user, User):
                    continue

                if user.role == role:
                    count += 1

            return count

        return 0

    # ==========================================
    # МАСОВЕ СТВОРЕННЯ
    # ==========================================

    async def bulk_upsert(
        self,
        *,
        actor: User,
        bushes: list[BushCreateData],
        update_existing: bool = False,
        reason: str,
    ) -> BushBulkResult:
        """
        Масово створює кущі.
        """

        if not bushes:
            raise ValueError(
                "Список кущів порожній."
            )

        if len(bushes) > self.MAX_BULK_SIZE:
            raise ValueError(
                "За один раз можна обробити "
                f"не більше {self.MAX_BULK_SIZE} кущів."
            )

        self.access.require_network_management(
            actor
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        items: list[
            BushBulkItemResult
        ] = []

        for data in bushes:
            try:
                normalized_name = (
                    self.normalize_required_text(
                        data.name,
                        field_name="Назва куща",
                        max_length=255,
                    )
                )

                normalized_code = (
                    self.normalize_optional_code(
                        data.code
                    )
                )

                existing = await self.find_bush(
                    name=normalized_name,
                    code=normalized_code,
                )

                if existing is None:
                    result = await self.create_bush(
                        actor=actor,
                        name=normalized_name,
                        code=normalized_code,
                        description=(
                            data.description
                        ),
                        is_active=data.is_active,
                        reason=normalized_reason,
                    )

                    items.append(
                        BushBulkItemResult(
                            name=normalized_name,
                            code=normalized_code,
                            success=True,
                            was_created=True,
                            was_changed=True,
                            bush_id=result.bush.id,
                            error=None,
                        )
                    )

                    continue

                if not update_existing:
                    items.append(
                        BushBulkItemResult(
                            name=normalized_name,
                            code=normalized_code,
                            success=True,
                            was_created=False,
                            was_changed=False,
                            bush_id=existing.id,
                            error=None,
                        )
                    )

                    continue

                result = await self.update_bush(
                    actor=actor,
                    bush_id=existing.id,
                    name=normalized_name,
                    code=normalized_code,
                    description=(
                        data.description
                        if (
                            data.description
                            is not None
                        )
                        else None
                    ),
                    reason=normalized_reason,
                )

                current_active = bool(
                    getattr(
                        existing,
                        "is_active",
                        True,
                    )
                )

                status_changed = (
                    current_active
                    != data.is_active
                )

                if status_changed:
                    await self.set_active_state(
                        actor=actor,
                        bush_id=existing.id,
                        is_active=data.is_active,
                        reason=normalized_reason,
                        detach_stores=False,
                        deactivate_bindings=False,
                        changed_at=None,
                    )

                items.append(
                    BushBulkItemResult(
                        name=normalized_name,
                        code=normalized_code,
                        success=True,
                        was_created=False,
                        was_changed=(
                            result.was_changed
                            or status_changed
                        ),
                        bush_id=existing.id,
                        error=None,
                    )
                )

            except Exception as error:
                items.append(
                    BushBulkItemResult(
                        name=data.name,
                        code=data.code,
                        success=False,
                        was_created=False,
                        was_changed=False,
                        bush_id=None,
                        error=str(error),
                    )
                )

        return BushBulkResult(
            total_count=len(items),

            success_count=sum(
                item.success
                for item in items
            ),

            failed_count=sum(
                not item.success
                for item in items
            ),

            created_count=sum(
                item.was_created
                for item in items
            ),

            changed_count=sum(
                (
                    item.was_changed
                    and not item.was_created
                )
                for item in items
            ),

            unchanged_count=sum(
                (
                    item.success
                    and not item.was_changed
                )
                for item in items
            ),

            items=tuple(items),
        )

    # ==========================================
    # ПОШУК МОДЕЛІ КУЩА
    # ==========================================

    async def find_bush(
        self,
        *,
        name: str | None = None,
        code: str | None = None,
    ) -> Bush | None:
        """
        Шукає кущ за кодом або назвою.
        """

        conditions: list[Any] = []

        if code is not None:
            code_column = self.model_column(
                "code",
                "slug",
            )

            if code_column is not None:
                conditions.append(
                    func.lower(code_column)
                    == code.lower()
                )

        if name is not None:
            name_column = self.model_column(
                "name",
                "title",
            )

            if name_column is not None:
                conditions.append(
                    func.lower(name_column)
                    == name.lower()
                )

        if not conditions:
            return None

        from sqlalchemy import or_

        statement = (
            select(Bush)
            .where(
                or_(*conditions)
            )
            .limit(1)
        )

        return await self.session.scalar(
            statement
        )

    # ==========================================
    # УНІКАЛЬНІСТЬ
    # ==========================================

    async def ensure_unique_bush(
        self,
        *,
        name: str | None = None,
        code: str | None = None,
        exclude_bush_id: int | None = None,
    ) -> None:
        """
        Перевіряє унікальність куща.
        """

        existing = await self.find_bush(
            name=name,
            code=code,
        )

        if (
            existing is not None
            and existing.id
            != exclude_bush_id
        ):
            raise ValueError(
                "Кущ із такою назвою або кодом "
                "уже існує."
            )

    # ==========================================
    # BUSH VIEW
    # ==========================================

    async def build_bush_view(
        self,
        bush: Bush,
    ) -> BushView:
        """
        Формує BushView.
        """

        statistics = await self.get_statistics_internal(
            bush
        )

        return BushView(
            id=bush.id,

            name=self.bush_name(bush),

            code=self.get_text_attribute(
                bush,
                "code",
                "slug",
            ),

            description=self.get_text_attribute(
                bush,
                "description",
            ),

            is_active=bool(
                getattr(
                    bush,
                    "is_active",
                    True,
                )
            ),

            active_store_count=(
                statistics.active_stores
            ),

            total_store_count=(
                statistics.total_stores
            ),

            bush_admin_count=(
                statistics.bush_admins
            ),

            lion_count=(
                statistics.lions
            ),

            created_at=getattr(
                bush,
                "created_at",
                None,
            ),

            updated_at=getattr(
                bush,
                "updated_at",
                None,
            ),

            raw_bush=bush,
        )

    async def get_statistics_internal(
        self,
        bush: Bush,
    ) -> BushStatistics:
        """
        Статистика без повторної перевірки доступу.
        """

        statement = (
            select(Store)
            .where(
                Store.bush_id == bush.id
            )
        )

        result = await self.session.scalars(
            statement
        )

        stores = list(
            result.unique().all()
        )

        active_stores = [
            store
            for store in stores
            if bool(
                getattr(
                    store,
                    "is_active",
                    True,
                )
            )
        ]

        cities = sorted(
            {
                city
                for store in stores
                if (
                    city
                    := self.get_text_attribute(
                        store,
                        "city",
                    )
                )
            }
        )

        return BushStatistics(
            bush_id=bush.id,
            bush_name=self.bush_name(bush),

            total_stores=len(stores),

            active_stores=len(
                active_stores
            ),

            inactive_stores=(
                len(stores)
                - len(active_stores)
            ),

            bush_admins=(
                await self.count_bush_users_by_role(
                    bush_id=bush.id,
                    role=UserRole.BUSH_ADMIN,
                )
            ),

            lions=(
                await self.count_bush_users_by_role(
                    bush_id=bush.id,
                    role=UserRole.LION,
                )
            ),

            cities=tuple(cities),

            stores_without_cluster=sum(
                getattr(
                    store,
                    "cluster_id",
                    None,
                )
                is None
                for store in active_stores
            ),
        )

    # ==========================================
    # SNAPSHOT
    # ==========================================

    def bush_snapshot(
        self,
        bush: Bush,
    ) -> dict[str, Any]:
        """
        Формує знімок куща.
        """

        return {
            "id": bush.id,

            "name": self.bush_name(
                bush
            ),

            "code": self.get_text_attribute(
                bush,
                "code",
                "slug",
            ),

            "description": (
                self.get_text_attribute(
                    bush,
                    "description",
                )
            ),

            "is_active": bool(
                getattr(
                    bush,
                    "is_active",
                    True,
                )
            ),
        }

    # ==========================================
    # AUDIT
    # ==========================================

    async def log_bush_change(
        self,
        *,
        actor: User,
        bush: Bush,
        description: str,
        reason: str | None,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
        was_created: bool,
    ) -> None:
        """
        Записує зміну куща.
        """

        action = self.resolve_audit_action(
            (
                "create"
                if was_created
                else "update"
            ),
            (
                "created"
                if was_created
                else "changed"
            ),
        )

        entity_type = self.resolve_entity_type(
            "bush",
            "group",
            "region",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=bush.id,

            context=AuditContext(
                actor_user_id=actor.id,

                reason=(
                    self.normalize_optional_text(
                        reason,
                        max_length=2000,
                    )
                ),

                description=description,

                source="telegram_bot",
            ),

            old_values=previous_values,

            new_values={
                **current_values,
                "bush_id": bush.id,
            },
        )

    async def log_store_move(
        self,
        *,
        actor: User,
        store: Store,
        reason: str,
        previous_bush_id: int | None,
        current_bush_id: int | None,
    ) -> None:
        """
        Фіксує зміну куща торгової точки.
        """

        action = self.resolve_audit_action(
            "update",
            "changed",
            "transfer",
        )

        entity_type = self.resolve_entity_type(
            "store",
            "shop",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=store.id,

            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=(
                    "Торгову точку переміщено "
                    "між кущами"
                ),
                source="telegram_bot",
            ),

            old_values={
                "store_id": store.id,
                "bush_id": previous_bush_id,
            },

            new_values={
                "store_id": store.id,
                "bush_id": current_bush_id,
            },
        )

    # ==========================================
    # ДОСТУП
    # ==========================================

    async def resolve_accessible_bush_ids(
        self,
        user: User,
    ) -> set[int] | None:
        """
        None = доступ до всієї мережі.
        """

        self.access.ensure_active_user(user)

        if self.access.is_global_manager(user):
            return None

        scope_method = getattr(
            self.access,
            "get_user_scope",
            None,
        )

        if callable(scope_method):
            result = scope_method(user)

            if inspect.isawaitable(result):
                result = await result

            bush_ids = getattr(
                result,
                "bush_ids",
                None,
            )

            if bush_ids is not None:
                return {
                    int(value)
                    for value in bush_ids
                }

        repository = getattr(
            self.repositories,
            "bindings",
            None,
        )

        if repository is None:
            return set()

        for method_name in (
            "get_accessible_bush_ids",
            "get_user_bush_ids",
            "list_active_bush_ids_for_user",
        ):
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(method):
                continue

            result = method(
                **self.filter_method_kwargs(
                    method,
                    {
                        "user_id": user.id,
                        "active_only": True,
                    },
                )
            )

            if inspect.isawaitable(result):
                result = await result

            return {
                int(value)
                for value in (
                    result or []
                )
            }

        return set()

    # ==========================================
    # МОДЕЛІ
    # ==========================================

    async def get_bush_or_raise(
        self,
        bush_id: int,
        *,
        include_inactive: bool = False,
        for_update: bool = False,
    ) -> Bush:
        """
        Повертає кущ за ID.
        """

        if bush_id <= 0:
            raise ValueError(
                "ID куща повинен бути "
                "більшим за нуль."
            )

        statement = (
            select(Bush)
            .where(
                Bush.id == bush_id
            )
        )

        if for_update:
            statement = (
                statement.with_for_update()
            )

        bush = await self.session.scalar(
            statement
        )

        if bush is None:
            raise ValueError(
                "Кущ не знайдено."
            )

        if (
            not include_inactive
            and not bool(
                getattr(
                    bush,
                    "is_active",
                    True,
                )
            )
        ):
            raise ValueError(
                "Кущ неактивний."
            )

        return bush

    async def get_store_or_raise(
        self,
        store_id: int,
        *,
        for_update: bool = False,
    ) -> Store:
        """
        Повертає торгову точку.
        """

        if store_id <= 0:
            raise ValueError(
                "ID ТТ повинен бути "
                "більшим за нуль."
            )

        statement = (
            select(Store)
            .where(
                Store.id == store_id
            )
        )

        if for_update:
            statement = (
                statement.with_for_update()
            )

        store = await self.session.scalar(
            statement
        )

        if store is None:
            raise ValueError(
                "Торгову точку не знайдено."
            )

        return store

    # ==========================================
    # REPOSITORY CREATE
    # ==========================================

    async def try_repository_create(
        self,
        payload: dict[str, Any],
    ) -> Any | None:
        """
        Пробує створити кущ через repository.
        """

        repository = getattr(
            self.repositories,
            "bushes",
            None,
        )

        if repository is None:
            return None

        for method_name in (
            "create_bush",
            "create",
            "add_bush",
        ):
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(method):
                continue

            result = method(
                **self.filter_method_kwargs(
                    method,
                    payload,
                )
            )

            if inspect.isawaitable(result):
                result = await result

            return result

        return None

    # ==========================================
    # ENUM
    # ==========================================

    @classmethod
    def resolve_audit_action(
        cls,
        *names: str,
    ) -> AuditAction:
        """
        Знаходить AuditAction.
        """

        result = cls.resolve_enum_member(
            AuditAction,
            *names,
            default=None,
        )

        if result is not None:
            return result

        result = cls.resolve_enum_member(
            AuditAction,
            "update",
            "changed",
            default=None,
        )

        if result is None:
            raise ValueError(
                "У AuditAction відсутнє "
                "значення update."
            )

        return result

    @classmethod
    def resolve_entity_type(
        cls,
        *names: str,
    ) -> EntityType:
        """
        Знаходить EntityType.
        """

        result = cls.resolve_enum_member(
            EntityType,
            *names,
            default=None,
        )

        if result is not None:
            return result

        result = cls.resolve_enum_member(
            EntityType,
            "bush",
            default=None,
        )

        if result is None:
            result = cls.resolve_enum_member(
                EntityType,
                "system",
                default=None,
            )

        if result is None:
            raise ValueError(
                "Не знайдено EntityType "
                "для куща."
            )

        return result

    @staticmethod
    def resolve_enum_member(
        enum_class: type[EnumType],
        *names: str,
        default: EnumType | None = None,
    ) -> EnumType | None:
        """
        Шукає enum за name або value.
        """

        normalized_names = {
            name.strip().lower()
            for name in names
            if name.strip()
        }

        for enum_item in enum_class:
            candidates = {
                enum_item.name.lower(),
                str(enum_item.value).lower(),
            }

            if candidates.intersection(
                normalized_names
            ):
                return enum_item

        return default

    # ==========================================
    # MODEL HELPERS
    # ==========================================

    @staticmethod
    def model_column(
        *names: str,
    ) -> Any | None:
        """
        Повертає колонку Bush.
        """

        for name in names:
            column = getattr(
                Bush,
                name,
                None,
            )

            if column is not None:
                return column

        return None

    @staticmethod
    def filter_model_payload(
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Залишає лише реальні поля Bush.
        """

        available_columns = {
            column.key
            for column
            in Bush.__mapper__.columns
        }

        return {
            key: value
            for key, value in payload.items()
            if key in available_columns
        }

    @staticmethod
    def filter_method_kwargs(
        method: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Фільтрує kwargs за сигнатурою.
        """

        signature = inspect.signature(
            method
        )

        accepts_kwargs = any(
            parameter.kind
            == inspect.Parameter.VAR_KEYWORD
            for parameter
            in signature.parameters.values()
        )

        if accepts_kwargs:
            return dict(payload)

        return {
            key: value
            for key, value in payload.items()
            if key in signature.parameters
        }

    @staticmethod
    def extract_bush(
        result: Any,
    ) -> Bush | None:
        """
        Витягує Bush із результату.
        """

        if isinstance(result, Bush):
            return result

        if isinstance(result, tuple):
            for item in result:
                if isinstance(item, Bush):
                    return item

        for field_name in (
            "bush",
            "entity",
            "model",
            "result",
        ):
            value = getattr(
                result,
                field_name,
                None,
            )

            if isinstance(value, Bush):
                return value

        return None

    # ==========================================
    # SEARCH
    # ==========================================

    @staticmethod
    def build_search_condition(
        columns: list[Any],
        value: str,
    ) -> Any:
        """
        Формує OR для пошуку.
        """

        from sqlalchemy import or_

        return or_(
            *[
                column.ilike(value)
                for column in columns
            ]
        )

    # ==========================================
    # SORT
    # ==========================================

    @staticmethod
    def bush_order_columns(
    ) -> tuple[Any, ...]:
        """
        Сортування кущів.
        """

        name_column = BushService.model_column(
            "name",
            "title",
        )

        if name_column is not None:
            return (
                name_column.asc(),
                Bush.id.asc(),
            )

        return (
            Bush.id.asc(),
        )

    @staticmethod
    def store_order_columns(
    ) -> tuple[Any, ...]:
        """
        Сортування ТТ.
        """

        number_column = getattr(
            Store,
            "store_number",
            None,
        )

        if number_column is not None:
            return (
                number_column.asc(),
                Store.id.asc(),
            )

        return (
            Store.id.asc(),
        )

    # ==========================================
    # ATTRIBUTES
    # ==========================================

    @staticmethod
    def set_first_existing_attribute(
        target: Any,
        value: Any,
        *names: str,
    ) -> bool:
        """
        Записує перший наявний атрибут.
        """

        for name in names:
            if hasattr(target, name):
                setattr(
                    target,
                    name,
                    value,
                )

                return True

        return False

    @staticmethod
    def get_text_attribute(
        target: Any,
        *names: str,
    ) -> str | None:
        """
        Читає перший текстовий атрибут.
        """

        if target is None:
            return None

        for name in names:
            value = getattr(
                target,
                name,
                None,
            )

            if value is None:
                continue

            normalized = str(
                value
            ).strip()

            if normalized:
                return normalized

        return None

    @staticmethod
    def bush_name(
        bush: Bush,
    ) -> str:
        """
        Повертає назву куща.
        """

        for field_name in (
            "name",
            "title",
        ):
            value = getattr(
                bush,
                field_name,
                None,
            )

            if value:
                return str(value)

        return f"Кущ #{bush.id}"

    # ==========================================
    # LIST / COUNT
    # ==========================================

    @staticmethod
    def as_list(
        result: Any,
    ) -> list[Any]:
        """
        Нормалізує значення у список.
        """

        if result is None:
            return []

        if isinstance(result, list):
            return result

        if isinstance(result, tuple):
            return list(result)

        if isinstance(result, set):
            return list(result)

        try:
            return list(result)

        except TypeError:
            return [result]

    @staticmethod
    def result_to_count(
        result: Any,
    ) -> int:
        """
        Нормалізує результат у кількість.
        """

        if result is None:
            return 0

        if isinstance(result, bool):
            return int(result)

        if isinstance(result, int):
            return max(
                result,
                0,
            )

        for field_name in (
            "count",
            "changed_count",
            "deactivated_count",
            "removed_count",
        ):
            value = getattr(
                result,
                field_name,
                None,
            )

            if value is None:
                continue

            try:
                return max(
                    int(value),
                    0,
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

        try:
            return len(result)

        except TypeError:
            return 0

    # ==========================================
    # CODE
    # ==========================================

    @staticmethod
    def normalize_optional_code(
        value: str | None,
    ) -> str | None:
        """
        Нормалізує короткий код куща.
        """

        if value is None:
            return None

        normalized = (
            value.strip()
            .upper()
            .replace(" ", "_")
        )

        if not normalized:
            return None

        if len(normalized) > 50:
            raise ValueError(
                "Код куща занадто довгий."
            )

        return normalized

    # ==========================================
    # VALIDATION
    # ==========================================

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
        max_length: int,
    ) -> str:
        """
        Нормалізує обов’язковий текст.
        """

        normalized_value = " ".join(
            value.strip().split()
        )

        if not normalized_value:
            raise ValueError(
                f"{field_name} не може бути порожнім."
            )

        if len(normalized_value) > max_length:
            raise ValueError(
                f"{field_name} занадто довгий."
            )

        return normalized_value

    @staticmethod
    def normalize_optional_text(
        value: str | None,
        *,
        max_length: int = 2000,
    ) -> str | None:
        """
        Нормалізує необов’язковий текст.
        """

        if value is None:
            return None

        normalized_value = " ".join(
            value.strip().split()
        )

        if not normalized_value:
            return None

        if len(normalized_value) > max_length:
            raise ValueError(
                "Текстове значення занадто довге."
            )

        return normalized_value

    @staticmethod
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        """
        Перевіряє timezone.
        """

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{field_name} повинен містити "
                "часовий пояс."
            )

    # ==========================================
    # TELEGRAM
    # ==========================================

    @staticmethod
    def format_bush(
        bush: BushView,
    ) -> str:
        """
        Формує картку куща для Telegram.
        """

        status = (
            "активний ✅"
            if bush.is_active
            else "неактивний ❌"
        )

        lines = [
            (
                "🌿 "
                f"<b>{escape(bush.name)}</b>"
            ),
            "",
            (
                "Статус: "
                f"<b>{status}</b>"
            ),
        ]

        if bush.code:
            lines.append(
                "🏷 Код: "
                f"<code>{escape(bush.code)}</code>"
            )

        if bush.description:
            lines.append(
                "📝 "
                f"{escape(bush.description)}"
            )

        lines.extend(
            [
                "",
                (
                    "🏪 Активних ТТ: "
                    f"<b>{bush.active_store_count}</b>"
                ),
                (
                    "📦 Усього ТТ: "
                    f"<b>{bush.total_store_count}</b>"
                ),
                (
                    "👤 Адміністраторів: "
                    f"<b>{bush.bush_admin_count}</b>"
                ),
                (
                    "🦁 Левів: "
                    f"<b>{bush.lion_count}</b>"
                ),
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def format_statistics(
        statistics: BushStatistics,
    ) -> str:
        """
        Формує статистику куща.
        """

        cities_text = (
            ", ".join(
                escape(city)
                for city
                in statistics.cities
            )
            or "—"
        )

        return "\n".join(
            [
                (
                    "📊 <b>Статистика куща "
                    f"{escape(statistics.bush_name)}</b>"
                ),
                "",
                (
                    "🏪 Усього ТТ: "
                    f"<b>{statistics.total_stores}</b>"
                ),
                (
                    "✅ Активних: "
                    f"<b>{statistics.active_stores}</b>"
                ),
                (
                    "❌ Неактивних: "
                    f"<b>{statistics.inactive_stores}</b>"
                ),
                (
                    "⏰ Без кластера: "
                    f"<b>{statistics.stores_without_cluster}</b>"
                ),
                "",
                (
                    "👤 Адміністраторів: "
                    f"<b>{statistics.bush_admins}</b>"
                ),
                (
                    "🦁 Левів: "
                    f"<b>{statistics.lions}</b>"
                ),
                "",
                (
                    "📍 Міста: "
                    f"{cities_text}"
                ),
            ]
        )