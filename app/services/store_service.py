from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from html import escape
from typing import Any, TypeVar

from sqlalchemy import func, or_, select

from app.database.models.bush import Bush
from app.database.models.cluster import Cluster
from app.database.models.enums import (
    AuditAction,
    EntityType,
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
class StoreCreateData:
    """
    Дані для створення торгової точки.
    """

    store_number: int
    code: str

    name: str
    city: str
    address: str | None = None

    bush_id: int | None = None
    cluster_id: int | None = None

    is_active: bool = True


@dataclass(slots=True, frozen=True)
class StoreView:
    """
    Безпечне представлення торгової точки.
    """

    id: int

    store_number: int | None
    code: str

    name: str
    city: str | None
    address: str | None

    bush_id: int | None
    bush_name: str | None

    cluster_id: int | None
    cluster_name: str | None
    cluster_hour: int | None

    is_active: bool

    created_at: datetime | None
    updated_at: datetime | None

    raw_store: Store


@dataclass(slots=True, frozen=True)
class StoreChangeResult:
    """
    Результат створення або редагування ТТ.
    """

    store: Store
    view: StoreView

    was_created: bool
    was_changed: bool

    previous_values: dict[str, Any]
    current_values: dict[str, Any]

    audit_created: bool


@dataclass(slots=True, frozen=True)
class StoreStatusChangeResult:
    """
    Результат активації або деактивації ТТ.
    """

    store: Store
    view: StoreView

    previous_active: bool
    current_active: bool

    was_changed: bool

    dependencies_deactivated: int

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class StoreBushChangeResult:
    """
    Результат перенесення ТТ між кущами.
    """

    store: Store

    previous_bush_id: int | None
    current_bush_id: int | None

    was_changed: bool

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class StoreClusterChangeResult:
    """
    Результат зміни кластера ТТ.
    """

    store: Store

    previous_cluster_id: int | None
    current_cluster_id: int | None

    was_changed: bool

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class StoreBulkItemResult:
    """
    Результат одного магазину в масовій операції.
    """

    code: str
    store_number: int

    success: bool
    was_created: bool
    was_changed: bool

    store_id: int | None
    error: str | None


@dataclass(slots=True, frozen=True)
class StoreBulkResult:
    """
    Результат масового створення ТТ.
    """

    total_count: int

    success_count: int
    failed_count: int

    created_count: int
    updated_count: int
    unchanged_count: int

    items: tuple[
        StoreBulkItemResult,
        ...,
    ]


class StoreService:
    """
    Сервіс торгових точок.

    Підтримує:

    - створення ТТ;
    - редагування ТТ;
    - пошук;
    - сортування за номером;
    - зміну куща;
    - зміну кластера;
    - деактивацію;
    - відновлення;
    - масове створення;
    - додавання SB-76 та SB-77;
    - AuditLog.

    Торгові точки не видаляються фізично.

    При закритті магазину використовується:

        is_active = False

    Це дозволяє зберегти старі звіти,
    відкриття, закриття та історію.
    """

    CODE_PATTERN = re.compile(
        r"^SB-\d{1,4}$",
        re.IGNORECASE,
    )

    MAX_BULK_SIZE = 500

    KNOWN_NEW_STORES = (
        StoreCreateData(
            store_number=76,
            code="SB-76",
            name="SB-76 Вінниця",
            city="Вінниця",
            address=None,
        ),
        StoreCreateData(
            store_number=77,
            code="SB-77",
            name="SB-77 Тернопіль",
            city="Тернопіль",
            address=None,
        ),
    )

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
    # ОТРИМАННЯ ОДНІЄЇ ТТ
    # ==========================================

    async def get_store(
        self,
        *,
        user: User,
        store_id: int,
    ) -> StoreView:
        """
        Повертає одну доступну користувачу ТТ.
        """

        store = await self.get_store_or_raise(
            store_id
        )

        await self.access.require_store_view(
            user,
            store.id,
        )

        return await self.build_store_view(
            store
        )

    async def get_store_by_code(
        self,
        *,
        user: User,
        code: str,
    ) -> StoreView:
        """
        Повертає ТТ за кодом SB-XX.
        """

        normalized_code = self.normalize_code(
            code
        )

        store = await self.find_by_code(
            normalized_code
        )

        if store is None:
            raise ValueError(
                f"Торгову точку {normalized_code} "
                "не знайдено."
            )

        await self.access.require_store_view(
            user,
            store.id,
        )

        return await self.build_store_view(
            store
        )

    # ==========================================
    # СПИСОК ТОРГОВИХ ТОЧОК
    # ==========================================

    async def get_stores(
        self,
        *,
        user: User,
        bush_id: int | None = None,
        cluster_id: int | None = None,
        city: str | None = None,
        active_only: bool = True,
        include_kyiv: bool = False,
    ) -> list[StoreView]:
        """
        Повертає доступні користувачу ТТ.
        """

        if bush_id is not None:
            await self.access.require_bush_view(
                user,
                bush_id,
            )

        elif cluster_id is None:
            self.access.require_network_view(
                user
            )

        accessible_store_ids = (
            await self.resolve_accessible_store_ids(
                user
            )
        )

        conditions: list[Any] = []

        if accessible_store_ids is not None:
            if not accessible_store_ids:
                return []

            conditions.append(
                Store.id.in_(
                    accessible_store_ids
                )
            )

        if bush_id is not None:
            conditions.append(
                Store.bush_id == bush_id
            )

        if cluster_id is not None:
            conditions.append(
                Store.cluster_id == cluster_id
            )

        if (
            active_only
            and hasattr(Store, "is_active")
        ):
            conditions.append(
                Store.is_active.is_(True)
            )

        city_column = self.model_column(
            "city"
        )

        if (
            city is not None
            and city_column is not None
        ):
            normalized_city = (
                self.normalize_required_text(
                    city,
                    field_name="Місто",
                    max_length=150,
                )
            )

            conditions.append(
                func.lower(city_column)
                == normalized_city.lower()
            )

        if not include_kyiv:
            self.append_kyiv_exclusion(
                conditions
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

        stores = list(
            result.unique().all()
        )

        return [
            await self.build_store_view(store)
            for store in stores
        ]

    # ==========================================
    # ПОШУК
    # ==========================================

    async def search_stores(
        self,
        *,
        user: User,
        query: str,
        active_only: bool = True,
        include_kyiv: bool = False,
        limit: int = 100,
    ) -> list[StoreView]:
        """
        Шукає ТТ за:

        - кодом;
        - номером;
        - містом;
        - адресою;
        - назвою.
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

        accessible_store_ids = (
            await self.resolve_accessible_store_ids(
                user
            )
        )

        if accessible_store_ids == set():
            return []

        search_value = (
            f"%{normalized_query}%"
        )

        searchable_columns = [
            self.model_column("code"),
            self.model_column(
                "name",
                "title",
                "display_name",
            ),
            self.model_column("city"),
            self.model_column("address"),
        ]

        searchable_columns = [
            column
            for column in searchable_columns
            if column is not None
        ]

        conditions: list[Any] = []

        if searchable_columns:
            conditions.append(
                or_(
                    *[
                        column.ilike(search_value)
                        for column
                        in searchable_columns
                    ]
                )
            )

        parsed_number = (
            self.try_parse_store_number(
                normalized_query
            )
        )

        number_column = self.model_column(
            "store_number",
            "number",
        )

        if (
            parsed_number is not None
            and number_column is not None
        ):
            if conditions:
                text_condition = conditions.pop()

                conditions.append(
                    or_(
                        text_condition,
                        number_column
                        == parsed_number,
                    )
                )

            else:
                conditions.append(
                    number_column
                    == parsed_number
                )

        if accessible_store_ids is not None:
            conditions.append(
                Store.id.in_(
                    accessible_store_ids
                )
            )

        if (
            active_only
            and hasattr(Store, "is_active")
        ):
            conditions.append(
                Store.is_active.is_(True)
            )

        if not include_kyiv:
            self.append_kyiv_exclusion(
                conditions
            )

        statement = (
            select(Store)
            .where(*conditions)
            .order_by(
                *self.store_order_columns()
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return [
            await self.build_store_view(store)
            for store
            in result.unique().all()
        ]

    # ==========================================
    # СТВОРЕННЯ ТТ
    # ==========================================

    async def create_store(
        self,
        *,
        actor: User,
        store_number: int,
        code: str | None = None,
        name: str | None = None,
        city: str,
        address: str | None = None,
        bush_id: int | None = None,
        cluster_id: int | None = None,
        is_active: bool = True,
        reason: str | None = None,
        created_at: datetime | None = None,
    ) -> StoreChangeResult:
        """
        Створює нову торгову точку.
        """

        now = created_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="created_at",
        )

        self.validate_store_number(
            store_number
        )

        normalized_code = self.normalize_code(
            code or f"SB-{store_number}"
        )

        normalized_city = (
            self.normalize_required_text(
                city,
                field_name="Місто",
                max_length=150,
            )
        )

        normalized_name = (
            self.normalize_optional_text(
                name,
                max_length=255,
            )
            or (
                f"{normalized_code} "
                f"{normalized_city}"
            )
        )

        normalized_address = (
            self.normalize_optional_text(
                address,
                max_length=500,
            )
        )

        await self.ensure_can_create_store(
            actor=actor,
            bush_id=bush_id,
        )

        if bush_id is not None:
            await self.get_bush_or_raise(
                bush_id
            )

        if cluster_id is not None:
            await self.get_cluster_or_raise(
                cluster_id
            )

        await self.ensure_unique_store(
            code=normalized_code,
            store_number=store_number,
        )

        payload = {
            "store_number": store_number,
            "number": store_number,
            "code": normalized_code,
            "name": normalized_name,
            "title": normalized_name,
            "display_name": normalized_name,
            "city": normalized_city,
            "address": normalized_address,
            "bush_id": bush_id,
            "cluster_id": cluster_id,
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
            store = self.extract_store(
                repository_result
            )

        else:
            store = Store(
                **self.filter_model_payload(
                    payload
                )
            )

            self.session.add(store)

            await self.session.flush()

        if store is None:
            raise RuntimeError(
                "Не вдалося створити "
                "торгову точку."
            )

        current_values = self.store_snapshot(
            store
        )

        await self.log_store_change(
            actor=actor,
            store=store,
            description=(
                "Створено нову торгову точку"
            ),
            reason=reason,
            previous_values={},
            current_values=current_values,
            was_created=True,
        )

        return StoreChangeResult(
            store=store,
            view=await self.build_store_view(
                store
            ),
            was_created=True,
            was_changed=True,
            previous_values={},
            current_values=current_values,
            audit_created=True,
        )

    # ==========================================
    # РЕДАГУВАННЯ ТТ
    # ==========================================

    async def update_store(
        self,
        *,
        actor: User,
        store_id: int,
        name: str | None = None,
        city: str | None = None,
        address: str | None = None,
        code: str | None = None,
        store_number: int | None = None,
        reason: str,
        updated_at: datetime | None = None,
    ) -> StoreChangeResult:
        """
        Редагує основні дані торгової точки.

        Значення None означає:
        не змінювати поточне поле.

        Для очищення адреси передай порожній рядок.
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

        store = await self.get_store_or_raise(
            store_id,
            for_update=True,
        )

        decision = await self.access.can_manage_store(
            actor,
            store.id,
        )

        decision.raise_if_denied()

        previous_values = self.store_snapshot(
            store
        )

        changes: dict[str, Any] = {}

        if name is not None:
            changes["name"] = (
                self.normalize_required_text(
                    name,
                    field_name="Назва",
                    max_length=255,
                )
            )

        if city is not None:
            changes["city"] = (
                self.normalize_required_text(
                    city,
                    field_name="Місто",
                    max_length=150,
                )
            )

        if address is not None:
            changes["address"] = (
                self.normalize_optional_text(
                    address,
                    max_length=500,
                )
            )

        if code is not None:
            normalized_code = (
                self.normalize_code(code)
            )

            await self.ensure_unique_store(
                code=normalized_code,
                exclude_store_id=store.id,
            )

            changes["code"] = normalized_code

        if store_number is not None:
            self.validate_store_number(
                store_number
            )

            await self.ensure_unique_store(
                store_number=store_number,
                exclude_store_id=store.id,
            )

            changes[
                "store_number"
            ] = store_number

        if not changes:
            return StoreChangeResult(
                store=store,
                view=await self.build_store_view(
                    store
                ),
                was_created=False,
                was_changed=False,
                previous_values=previous_values,
                current_values=previous_values,
                audit_created=False,
            )

        for field_name, value in changes.items():
            if field_name == "name":
                self.set_store_name(
                    store,
                    value,
                )

            elif field_name == "store_number":
                self.set_first_existing_attribute(
                    store,
                    value,
                    "store_number",
                    "number",
                )

            else:
                self.set_first_existing_attribute(
                    store,
                    value,
                    field_name,
                )

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

        current_values = self.store_snapshot(
            store
        )

        was_changed = (
            previous_values
            != current_values
        )

        if was_changed:
            await self.log_store_change(
                actor=actor,
                store=store,
                description=(
                    "Змінено дані торгової точки"
                ),
                reason=normalized_reason,
                previous_values=previous_values,
                current_values=current_values,
                was_created=False,
            )

        return StoreChangeResult(
            store=store,
            view=await self.build_store_view(
                store
            ),
            was_created=False,
            was_changed=was_changed,
            previous_values=previous_values,
            current_values=current_values,
            audit_created=was_changed,
        )

    # ==========================================
    # ЗМІНА КУЩА
    # ==========================================

    async def change_bush(
        self,
        *,
        actor: User,
        store_id: int,
        bush_id: int | None,
        reason: str,
        changed_at: datetime | None = None,
    ) -> StoreBushChangeResult:
        """
        Переносить торгову точку в інший кущ.

        bush_id=None прибирає ТТ із куща.
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

        if bush_id is not None:
            new_decision = (
                await self.access.can_manage_bush(
                    actor,
                    bush_id,
                )
            )

            new_decision.raise_if_denied()

            await self.get_bush_or_raise(
                bush_id
            )

        else:
            self.access.require_network_management(
                actor
            )

        if previous_bush_id == bush_id:
            return StoreBushChangeResult(
                store=store,
                previous_bush_id=previous_bush_id,
                current_bush_id=bush_id,
                was_changed=False,
                changed_at=now,
                changed_by_id=actor.id,
                reason=normalized_reason,
            )

        store.bush_id = bush_id

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

        await self.log_store_change(
            actor=actor,
            store=store,
            description=(
                "Змінено кущ торгової точки"
            ),
            reason=normalized_reason,
            previous_values={
                "bush_id": previous_bush_id,
            },
            current_values={
                "bush_id": bush_id,
            },
            was_created=False,
        )

        return StoreBushChangeResult(
            store=store,
            previous_bush_id=previous_bush_id,
            current_bush_id=bush_id,
            was_changed=True,
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # ЗМІНА КЛАСТЕРА
    # ==========================================

    async def change_cluster(
        self,
        *,
        actor: User,
        store_id: int,
        cluster_id: int | None,
        reason: str,
        changed_at: datetime | None = None,
    ) -> StoreClusterChangeResult:
        """
        Змінює кластер відкриття ТТ.

        cluster_id=None прибирає кластер.
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

        decision = await self.access.can_manage_store(
            actor,
            store.id,
        )

        decision.raise_if_denied()

        if cluster_id is not None:
            await self.get_cluster_or_raise(
                cluster_id
            )

        previous_cluster_id = getattr(
            store,
            "cluster_id",
            None,
        )

        if previous_cluster_id == cluster_id:
            return StoreClusterChangeResult(
                store=store,
                previous_cluster_id=(
                    previous_cluster_id
                ),
                current_cluster_id=cluster_id,
                was_changed=False,
                changed_at=now,
                changed_by_id=actor.id,
                reason=normalized_reason,
            )

        store.cluster_id = cluster_id

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

        await self.log_store_change(
            actor=actor,
            store=store,
            description=(
                "Змінено кластер торгової точки"
            ),
            reason=normalized_reason,
            previous_values={
                "cluster_id": (
                    previous_cluster_id
                ),
            },
            current_values={
                "cluster_id": cluster_id,
            },
            was_created=False,
        )

        return StoreClusterChangeResult(
            store=store,
            previous_cluster_id=(
                previous_cluster_id
            ),
            current_cluster_id=cluster_id,
            was_changed=True,
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # ДЕАКТИВАЦІЯ ТТ
    # ==========================================

    async def deactivate_store(
        self,
        *,
        actor: User,
        store_id: int,
        reason: str,
        deactivate_bindings: bool = True,
        changed_at: datetime | None = None,
    ) -> StoreStatusChangeResult:
        """
        Деактивує торгову точку без видалення.

        Старі відкриття, закриття та звіти
        залишаються в базі.
        """

        return await self.set_active_state(
            actor=actor,
            store_id=store_id,
            is_active=False,
            reason=reason,
            deactivate_bindings=(
                deactivate_bindings
            ),
            changed_at=changed_at,
        )

    async def reactivate_store(
        self,
        *,
        actor: User,
        store_id: int,
        reason: str,
        changed_at: datetime | None = None,
    ) -> StoreStatusChangeResult:
        """
        Повторно активує торгову точку.
        """

        return await self.set_active_state(
            actor=actor,
            store_id=store_id,
            is_active=True,
            reason=reason,
            deactivate_bindings=False,
            changed_at=changed_at,
        )

    async def set_active_state(
        self,
        *,
        actor: User,
        store_id: int,
        is_active: bool,
        reason: str,
        deactivate_bindings: bool,
        changed_at: datetime | None,
    ) -> StoreStatusChangeResult:
        """
        Змінює активність торгової точки.
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
            include_inactive=True,
        )

        decision = await self.access.can_manage_store(
            actor,
            store.id,
        )

        decision.raise_if_denied()

        previous_active = bool(
            getattr(
                store,
                "is_active",
                True,
            )
        )

        if previous_active == is_active:
            return StoreStatusChangeResult(
                store=store,
                view=await self.build_store_view(
                    store
                ),
                previous_active=previous_active,
                current_active=is_active,
                was_changed=False,
                dependencies_deactivated=0,
                changed_at=now,
                changed_by_id=actor.id,
                reason=normalized_reason,
            )

        self.set_first_existing_attribute(
            store,
            bool(is_active),
            "is_active",
            "active",
        )

        if is_active:
            self.set_first_existing_attribute(
                store,
                None,
                "deactivated_at",
                "closed_at",
            )

            self.set_first_existing_attribute(
                store,
                None,
                "deactivated_by_id",
                "closed_by_id",
            )

        else:
            self.set_first_existing_attribute(
                store,
                now,
                "deactivated_at",
                "closed_at",
            )

            self.set_first_existing_attribute(
                store,
                actor.id,
                "deactivated_by_id",
                "closed_by_id",
            )

        self.set_first_existing_attribute(
            store,
            normalized_reason,
            "deactivation_reason",
            "status_reason",
        )

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

        dependencies_deactivated = 0

        if (
            not is_active
            and deactivate_bindings
        ):
            dependencies_deactivated = (
                await self.deactivate_store_bindings(
                    store_id=store.id,
                    actor=actor,
                    reason=normalized_reason,
                    changed_at=now,
                )
            )

        await self.log_store_change(
            actor=actor,
            store=store,
            description=(
                "Торгову точку активовано"
                if is_active
                else "Торгову точку деактивовано"
            ),
            reason=normalized_reason,
            previous_values={
                "is_active": previous_active,
            },
            current_values={
                "is_active": is_active,
                "bindings_deactivated": (
                    dependencies_deactivated
                ),
            },
            was_created=False,
        )

        return StoreStatusChangeResult(
            store=store,
            view=await self.build_store_view(
                store
            ),
            previous_active=previous_active,
            current_active=is_active,
            was_changed=True,
            dependencies_deactivated=(
                dependencies_deactivated
            ),
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # SB-76 ТА SB-77
    # ==========================================

    async def ensure_new_stores(
        self,
        *,
        actor: User,
        sb76_address: str | None = None,
        sb76_bush_id: int | None = None,
        sb76_cluster_id: int | None = None,
        sb77_address: str | None = None,
        sb77_bush_id: int | None = None,
        sb77_cluster_id: int | None = None,
    ) -> StoreBulkResult:
        """
        Створює або оновлює:

        - SB-76 Вінниця;
        - SB-77 Тернопіль.

        Адреси можна додати пізніше.
        """

        data = [
            StoreCreateData(
                store_number=76,
                code="SB-76",
                name="SB-76 Вінниця",
                city="Вінниця",
                address=sb76_address,
                bush_id=sb76_bush_id,
                cluster_id=sb76_cluster_id,
            ),
            StoreCreateData(
                store_number=77,
                code="SB-77",
                name="SB-77 Тернопіль",
                city="Тернопіль",
                address=sb77_address,
                bush_id=sb77_bush_id,
                cluster_id=sb77_cluster_id,
            ),
        ]

        return await self.bulk_upsert(
            actor=actor,
            stores=data,
            update_existing=True,
            reason=(
                "Додавання нових торгових точок "
                "SB-76 та SB-77"
            ),
        )

    # ==========================================
    # МАСОВЕ СТВОРЕННЯ
    # ==========================================

    async def bulk_upsert(
        self,
        *,
        actor: User,
        stores: list[StoreCreateData],
        update_existing: bool = False,
        reason: str,
    ) -> StoreBulkResult:
        """
        Масово створює або оновлює ТТ.
        """

        if not stores:
            raise ValueError(
                "Список торгових точок порожній."
            )

        if len(stores) > self.MAX_BULK_SIZE:
            raise ValueError(
                "За один раз можна обробити "
                f"не більше {self.MAX_BULK_SIZE} ТТ."
            )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        self.access.require_network_management(
            actor
        )

        items: list[StoreBulkItemResult] = []

        for store_data in stores:
            try:
                normalized_code = (
                    self.normalize_code(
                        store_data.code
                    )
                )

                existing = await self.find_by_code(
                    normalized_code
                )

                if existing is None:
                    result = await self.create_store(
                        actor=actor,
                        store_number=(
                            store_data.store_number
                        ),
                        code=normalized_code,
                        name=store_data.name,
                        city=store_data.city,
                        address=store_data.address,
                        bush_id=store_data.bush_id,
                        cluster_id=(
                            store_data.cluster_id
                        ),
                        is_active=(
                            store_data.is_active
                        ),
                        reason=normalized_reason,
                    )

                    items.append(
                        StoreBulkItemResult(
                            code=normalized_code,
                            store_number=(
                                store_data
                                .store_number
                            ),
                            success=True,
                            was_created=True,
                            was_changed=True,
                            store_id=result.store.id,
                            error=None,
                        )
                    )

                    continue

                if not update_existing:
                    items.append(
                        StoreBulkItemResult(
                            code=normalized_code,
                            store_number=(
                                store_data
                                .store_number
                            ),
                            success=True,
                            was_created=False,
                            was_changed=False,
                            store_id=existing.id,
                            error=None,
                        )
                    )

                    continue

                update_result = (
                    await self.update_store(
                        actor=actor,
                        store_id=existing.id,
                        name=store_data.name,
                        city=store_data.city,
                        address=(
                            store_data.address
                            if (
                                store_data.address
                                is not None
                            )
                            else None
                        ),
                        code=normalized_code,
                        store_number=(
                            store_data.store_number
                        ),
                        reason=normalized_reason,
                    )
                )

                if (
                    existing.bush_id
                    != store_data.bush_id
                ):
                    await self.change_bush(
                        actor=actor,
                        store_id=existing.id,
                        bush_id=store_data.bush_id,
                        reason=normalized_reason,
                    )

                if (
                    existing.cluster_id
                    != store_data.cluster_id
                ):
                    await self.change_cluster(
                        actor=actor,
                        store_id=existing.id,
                        cluster_id=(
                            store_data.cluster_id
                        ),
                        reason=normalized_reason,
                    )

                if (
                    bool(existing.is_active)
                    != bool(store_data.is_active)
                ):
                    await self.set_active_state(
                        actor=actor,
                        store_id=existing.id,
                        is_active=(
                            store_data.is_active
                        ),
                        reason=normalized_reason,
                        deactivate_bindings=False,
                        changed_at=None,
                    )

                items.append(
                    StoreBulkItemResult(
                        code=normalized_code,
                        store_number=(
                            store_data.store_number
                        ),
                        success=True,
                        was_created=False,
                        was_changed=(
                            update_result.was_changed
                            or existing.bush_id
                            != store_data.bush_id
                            or existing.cluster_id
                            != store_data.cluster_id
                        ),
                        store_id=existing.id,
                        error=None,
                    )
                )

            except Exception as error:
                items.append(
                    StoreBulkItemResult(
                        code=store_data.code,
                        store_number=(
                            store_data.store_number
                        ),
                        success=False,
                        was_created=False,
                        was_changed=False,
                        store_id=None,
                        error=str(error),
                    )
                )

        return StoreBulkResult(
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
            updated_count=sum(
                item.success
                and not item.was_created
                and item.was_changed
                for item in items
            ),
            unchanged_count=sum(
                item.success
                and not item.was_changed
                for item in items
            ),
            items=tuple(items),
        )

    # ==========================================
    # ПРИВ’ЯЗКИ НЕАКТИВНОЇ ТТ
    # ==========================================

    async def deactivate_store_bindings(
        self,
        *,
        store_id: int,
        actor: User,
        reason: str,
        changed_at: datetime,
    ) -> int:
        """
        Деактивує активні прив’язки працівників ТТ.
        """

        repository = getattr(
            self.repositories,
            "bindings",
            None,
        )

        if repository is None:
            return 0

        method_names = (
            "deactivate_all_for_store",
            "deactivate_store_bindings",
            "remove_all_store_bindings",
            "unbind_all_from_store",
        )

        for method_name in method_names:
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(method):
                continue

            payload = {
                "store_id": store_id,
                "deactivated_by_id": actor.id,
                "removed_by_id": actor.id,
                "deactivated_at": changed_at,
                "removed_at": changed_at,
                "reason": reason,
            }

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
    # ДОСТУП
    # ==========================================

    async def ensure_can_create_store(
        self,
        *,
        actor: User,
        bush_id: int | None,
    ) -> None:
        """
        Перевіряє право створення ТТ.
        """

        if bush_id is None:
            self.access.require_network_management(
                actor
            )
            return

        decision = await self.access.can_manage_bush(
            actor,
            bush_id,
        )

        decision.raise_if_denied()

    async def resolve_accessible_store_ids(
        self,
        user: User,
    ) -> set[int] | None:
        """
        Повертає доступні ID ТТ.

        None означає доступ до всієї мережі.
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

            store_ids = getattr(
                result,
                "store_ids",
                None,
            )

            if store_ids is not None:
                return {
                    int(store_id)
                    for store_id in store_ids
                }

        repository = getattr(
            self.repositories,
            "bindings",
            None,
        )

        if repository is None:
            return set()

        for method_name in (
            "get_accessible_store_ids",
            "get_user_store_ids",
            "list_active_store_ids_for_user",
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
                int(store_id)
                for store_id in (
                    result or []
                )
            }

        return set()

    # ==========================================
    # МОДЕЛІ
    # ==========================================

    async def get_store_or_raise(
        self,
        store_id: int,
        *,
        for_update: bool = False,
        include_inactive: bool = False,
    ) -> Store:
        """
        Повертає торгову точку за ID.
        """

        if store_id <= 0:
            raise ValueError(
                "ID торгової точки повинен бути "
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

        if (
            not include_inactive
            and not bool(
                getattr(
                    store,
                    "is_active",
                    True,
                )
            )
        ):
            raise ValueError(
                "Торгова точка неактивна."
            )

        return store

    async def get_bush_or_raise(
        self,
        bush_id: int,
    ) -> Bush:
        """
        Повертає активний кущ.
        """

        if bush_id <= 0:
            raise ValueError(
                "ID куща повинен бути "
                "більшим за нуль."
            )

        bush = await self.session.get(
            Bush,
            bush_id,
        )

        if bush is None:
            raise ValueError(
                "Кущ не знайдено."
            )

        if not bool(
            getattr(
                bush,
                "is_active",
                True,
            )
        ):
            raise ValueError(
                "Кущ неактивний."
            )

        return bush

    async def get_cluster_or_raise(
        self,
        cluster_id: int,
    ) -> Cluster:
        """
        Повертає активний кластер.
        """

        if cluster_id <= 0:
            raise ValueError(
                "ID кластера повинен бути "
                "більшим за нуль."
            )

        cluster = await self.session.get(
            Cluster,
            cluster_id,
        )

        if cluster is None:
            raise ValueError(
                "Кластер не знайдено."
            )

        if not bool(
            getattr(
                cluster,
                "is_active",
                True,
            )
        ):
            raise ValueError(
                "Кластер неактивний."
            )

        return cluster

    async def find_by_code(
        self,
        code: str,
    ) -> Store | None:
        """
        Повертає ТТ за кодом.
        """

        code_column = self.model_column(
            "code"
        )

        if code_column is None:
            return None

        statement = (
            select(Store)
            .where(
                func.lower(code_column)
                == code.lower()
            )
            .limit(1)
        )

        return await self.session.scalar(
            statement
        )

    async def ensure_unique_store(
        self,
        *,
        code: str | None = None,
        store_number: int | None = None,
        exclude_store_id: int | None = None,
    ) -> None:
        """
        Перевіряє унікальність коду та номера.
        """

        conditions: list[Any] = []

        if code is not None:
            code_column = self.model_column(
                "code"
            )

            if code_column is not None:
                conditions.append(
                    func.lower(code_column)
                    == code.lower()
                )

        if store_number is not None:
            number_column = self.model_column(
                "store_number",
                "number",
            )

            if number_column is not None:
                conditions.append(
                    number_column
                    == store_number
                )

        if not conditions:
            return

        statement = (
            select(Store)
            .where(
                or_(*conditions)
            )
            .limit(1)
        )

        existing = await self.session.scalar(
            statement
        )

        if (
            existing is not None
            and existing.id
            != exclude_store_id
        ):
            raise ValueError(
                "Торгова точка з таким кодом "
                "або номером уже існує."
            )

    # ==========================================
    # STORE VIEW
    # ==========================================

    async def build_store_view(
        self,
        store: Store,
    ) -> StoreView:
        """
        Формує StoreView.
        """

        bush = None
        cluster = None

        bush_id = getattr(
            store,
            "bush_id",
            None,
        )

        cluster_id = getattr(
            store,
            "cluster_id",
            None,
        )

        if bush_id is not None:
            bush = await self.session.get(
                Bush,
                bush_id,
            )

        if cluster_id is not None:
            cluster = await self.session.get(
                Cluster,
                cluster_id,
            )

        return StoreView(
            id=store.id,
            store_number=(
                self.get_int_attribute(
                    store,
                    "store_number",
                    "number",
                )
            ),
            code=self.store_code(store),
            name=self.store_name(store),
            city=self.get_text_attribute(
                store,
                "city",
            ),
            address=self.get_text_attribute(
                store,
                "address",
            ),
            bush_id=bush_id,
            bush_name=(
                self.get_text_attribute(
                    bush,
                    "name",
                    "title",
                )
                if bush is not None
                else None
            ),
            cluster_id=cluster_id,
            cluster_name=(
                self.get_text_attribute(
                    cluster,
                    "name",
                    "title",
                )
                if cluster is not None
                else None
            ),
            cluster_hour=(
                self.get_int_attribute(
                    cluster,
                    "hour",
                    "opening_hour",
                    "start_hour",
                )
                if cluster is not None
                else None
            ),
            is_active=bool(
                getattr(
                    store,
                    "is_active",
                    True,
                )
            ),
            created_at=getattr(
                store,
                "created_at",
                None,
            ),
            updated_at=getattr(
                store,
                "updated_at",
                None,
            ),
            raw_store=store,
        )

    def store_snapshot(
        self,
        store: Store,
    ) -> dict[str, Any]:
        """
        Формує знімок торгової точки.
        """

        return {
            "id": store.id,
            "store_number": (
                self.get_int_attribute(
                    store,
                    "store_number",
                    "number",
                )
            ),
            "code": self.store_code(store),
            "name": self.store_name(store),
            "city": self.get_text_attribute(
                store,
                "city",
            ),
            "address": (
                self.get_text_attribute(
                    store,
                    "address",
                )
            ),
            "bush_id": getattr(
                store,
                "bush_id",
                None,
            ),
            "cluster_id": getattr(
                store,
                "cluster_id",
                None,
            ),
            "is_active": bool(
                getattr(
                    store,
                    "is_active",
                    True,
                )
            ),
        }

    # ==========================================
    # AUDIT LOG
    # ==========================================

    async def log_store_change(
        self,
        *,
        actor: User,
        store: Store,
        description: str,
        reason: str | None,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
        was_created: bool,
    ) -> None:
        """
        Записує зміну ТТ в AuditLog.
        """

        action = self.resolve_audit_action(
            "create" if was_created else "update",
            "created" if was_created else "changed",
        )

        entity_type = self.resolve_entity_type(
            "store",
            "shop",
            "trading_point",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=store.id,
            context=AuditContext(
                actor_user_id=actor.id,
                reason=self.normalize_optional_text(
                    reason,
                    max_length=2000,
                ),
                description=description,
                source="telegram_bot",
            ),
            old_values=previous_values,
            new_values={
                **current_values,
                "store_id": store.id,
                "bush_id": getattr(
                    store,
                    "bush_id",
                    None,
                ),
            },
        )

    # ==========================================
    # REPOSITORY ADAPTER
    # ==========================================

    async def try_repository_create(
        self,
        payload: dict[str, Any],
    ) -> Any | None:
        """
        Пробує створити ТТ через StoreRepository.
        """

        repository = getattr(
            self.repositories,
            "stores",
            None,
        )

        if repository is None:
            return None

        for method_name in (
            "create_store",
            "create",
            "add_store",
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
            "store",
            default=None,
        )

        if result is None:
            raise ValueError(
                "У EntityType відсутнє "
                "значення store."
            )

        return result

    @staticmethod
    def resolve_enum_member(
        enum_class: type[EnumType],
        *names: str,
        default: EnumType | None = None,
    ) -> EnumType | None:
        """
        Шукає enum за назвою або значенням.
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
    # МОДЕЛЬНІ ПОЛЯ
    # ==========================================

    @staticmethod
    def model_column(
        *names: str,
    ) -> Any | None:
        """
        Повертає першу наявну колонку Store.
        """

        for name in names:
            column = getattr(
                Store,
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
        Залишає лише реальні колонки Store.
        """

        available_columns = {
            column.key
            for column
            in Store.__mapper__.columns
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
        Залишає аргументи, які приймає метод.
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
    def extract_store(
        result: Any,
    ) -> Store | None:
        """
        Витягує Store з результату repository.
        """

        if isinstance(result, Store):
            return result

        if isinstance(result, tuple):
            for item in result:
                if isinstance(item, Store):
                    return item

        for field_name in (
            "store",
            "entity",
            "model",
            "result",
        ):
            value = getattr(
                result,
                field_name,
                None,
            )

            if isinstance(value, Store):
                return value

        return None

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def store_order_columns(
    ) -> tuple[Any, ...]:
        """
        Повертає сортування ТТ.
        """

        number_column = StoreService.model_column(
            "store_number",
            "number",
        )

        code_column = StoreService.model_column(
            "code"
        )

        columns: list[Any] = []

        if number_column is not None:
            columns.append(
                number_column.asc()
            )

        if code_column is not None:
            columns.append(
                code_column.asc()
            )

        columns.append(
            Store.id.asc()
        )

        return tuple(columns)

    @staticmethod
    def append_kyiv_exclusion(
        conditions: list[Any],
    ) -> None:
        """
        Виключає магазини Києва.
        """

        city_column = StoreService.model_column(
            "city"
        )

        if city_column is not None:
            conditions.append(
                or_(
                    city_column.is_(None),
                    func.lower(city_column)
                    .notin_(
                        {
                            "київ",
                            "киев",
                            "kyiv",
                            "kiev",
                        }
                    ),
                )
            )

    @staticmethod
    def store_code(
        store: Store,
    ) -> str:
        """
        Повертає код торгової точки.
        """

        code = getattr(
            store,
            "code",
            None,
        )

        if code:
            return str(code)

        store_number = (
            StoreService.get_int_attribute(
                store,
                "store_number",
                "number",
            )
        )

        if store_number is not None:
            return f"SB-{store_number}"

        return f"ТТ-{store.id}"

    @classmethod
    def store_name(
        cls,
        store: Store,
    ) -> str:
        """
        Повертає назву торгової точки.
        """

        for field_name in (
            "name",
            "title",
            "display_name",
        ):
            value = getattr(
                store,
                field_name,
                None,
            )

            if value:
                return str(value)

        return cls.store_code(store)

    @staticmethod
    def set_store_name(
        store: Store,
        value: str,
    ) -> None:
        """
        Записує назву в наявне поле Store.
        """

        StoreService.set_first_existing_attribute(
            store,
            value,
            "name",
            "title",
            "display_name",
        )

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
    def get_int_attribute(
        target: Any,
        *names: str,
    ) -> int | None:
        """
        Повертає перший цілий атрибут.
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

            try:
                return int(value)

            except (
                TypeError,
                ValueError,
            ):
                continue

        return None

    @staticmethod
    def get_text_attribute(
        target: Any,
        *names: str,
    ) -> str | None:
        """
        Повертає перший текстовий атрибут.
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

            normalized_value = str(
                value
            ).strip()

            if normalized_value:
                return normalized_value

        return None

    @staticmethod
    def result_to_count(
        result: Any,
    ) -> int:
        """
        Перетворює результат у кількість.
        """

        if result is None:
            return 0

        if isinstance(result, bool):
            return int(result)

        if isinstance(result, int):
            return max(result, 0)

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
    # ВАЛІДАЦІЯ
    # ==========================================

    @classmethod
    def normalize_code(
        cls,
        code: str,
    ) -> str:
        """
        Нормалізує код ТТ.
        """

        normalized_code = (
            code.strip()
            .upper()
            .replace(" ", "")
            .replace("_", "-")
        )

        if normalized_code.isdigit():
            normalized_code = (
                f"SB-{int(normalized_code)}"
            )

        if normalized_code.startswith("SB"):
            number_part = re.sub(
                r"\D",
                "",
                normalized_code,
            )

            if number_part:
                normalized_code = (
                    f"SB-{int(number_part)}"
                )

        if not cls.CODE_PATTERN.fullmatch(
            normalized_code
        ):
            raise ValueError(
                "Код торгової точки повинен "
                "мати формат SB-76."
            )

        return normalized_code

    @staticmethod
    def validate_store_number(
        store_number: int,
    ) -> None:
        """
        Перевіряє номер торгової точки.
        """

        if isinstance(store_number, bool):
            raise ValueError(
                "Номер ТТ повинен бути числом."
            )

        if (
            store_number < 1
            or store_number > 9999
        ):
            raise ValueError(
                "Номер ТТ повинен бути "
                "від 1 до 9999."
            )

    @staticmethod
    def try_parse_store_number(
        value: str,
    ) -> int | None:
        """
        Пробує витягнути номер ТТ.
        """

        number_text = re.sub(
            r"\D",
            "",
            value,
        )

        if not number_text:
            return None

        try:
            return int(number_text)

        except ValueError:
            return None

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
        Перевіряє наявність часового поясу.
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
    # TELEGRAM-ФОРМАТУВАННЯ
    # ==========================================

    @staticmethod
    def format_store(
        store: StoreView,
    ) -> str:
        """
        Формує картку ТТ для Telegram.
        """

        status = (
            "активна ✅"
            if store.is_active
            else "неактивна ❌"
        )

        lines = [
            (
                f"🏪 <b>{escape(store.code)}</b>"
            ),
            (
                f"<b>{escape(store.name)}</b>"
            ),
            "",
            (
                "Статус: "
                f"<b>{status}</b>"
            ),
        ]

        if store.city:
            lines.append(
                "📍 Місто: "
                f"<b>{escape(store.city)}</b>"
            )

        if store.address:
            lines.append(
                "🏠 Адреса: "
                f"{escape(store.address)}"
            )

        if store.bush_id is not None:
            lines.append(
                "🌿 Кущ: "
                f"<b>{escape(store.bush_name or str(store.bush_id))}</b>"
            )

        if store.cluster_id is not None:
            cluster_text = (
                store.cluster_name
                or f"#{store.cluster_id}"
            )

            if store.cluster_hour is not None:
                cluster_text += (
                    f" · {store.cluster_hour:02d}:00"
                )

            lines.append(
                "⏰ Кластер: "
                f"<b>{escape(cluster_text)}</b>"
            )

        return "\n".join(lines)

    @staticmethod
    def format_bulk_result(
        result: StoreBulkResult,
    ) -> str:
        """
        Формує результат масової операції.
        """

        lines = [
            "🏪 <b>Обробку торгових точок завершено</b>",
            "",
            (
                "Усього: "
                f"<b>{result.total_count}</b>"
            ),
            (
                "Успішно: "
                f"<b>{result.success_count}</b>"
            ),
            (
                "Створено: "
                f"<b>{result.created_count}</b>"
            ),
            (
                "Оновлено: "
                f"<b>{result.updated_count}</b>"
            ),
            (
                "Без змін: "
                f"<b>{result.unchanged_count}</b>"
            ),
            (
                "Помилки: "
                f"<b>{result.failed_count}</b>"
            ),
        ]

        failed_items = [
            item
            for item in result.items
            if not item.success
        ]

        if failed_items:
            lines.extend(
                [
                    "",
                    "⚠️ <b>Помилки:</b>",
                ]
            )

            for item in failed_items[:20]:
                lines.append(
                    f"• <b>{escape(item.code)}</b> — "
                    f"{escape(item.error or 'невідома помилка')}"
                )

        return "\n".join(lines)