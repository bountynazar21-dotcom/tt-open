from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from html import escape
from typing import Any, TypeVar

from sqlalchemy import select

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


class BindingScope(StrEnum):
    """
    Тип області прив’язки.
    """

    STORE = "store"
    BUSH = "bush"


@dataclass(slots=True, frozen=True)
class BindingView:
    """
    Безпечне представлення прив’язки.
    """

    id: int | None

    scope: BindingScope

    user_id: int
    store_id: int | None
    bush_id: int | None

    is_active: bool
    is_primary: bool

    created_by_id: int | None
    assigned_by_id: int | None

    created_at: datetime | None
    assigned_at: datetime | None

    deactivated_at: datetime | None
    deactivated_by_id: int | None

    raw_binding: Any


@dataclass(slots=True, frozen=True)
class BindingChangeResult:
    """
    Результат створення або зміни прив’язки.
    """

    binding: Any
    view: BindingView

    was_created: bool
    was_changed: bool
    was_reactivated: bool

    previous_values: dict[str, Any]
    current_values: dict[str, Any]


@dataclass(slots=True, frozen=True)
class BindingDeactivationResult:
    """
    Результат деактивації прив’язки.
    """

    binding_id: int | None
    user_id: int

    scope: BindingScope

    store_id: int | None
    bush_id: int | None

    was_deactivated: bool

    deactivated_at: datetime
    deactivated_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class StoreTransferResult:
    """
    Результат перенесення користувача між ТТ.
    """

    user: User

    source_store_id: int
    target_store_id: int

    source_binding_deactivated: bool
    target_binding_created: bool

    role_changed: bool

    transferred_at: datetime
    transferred_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class BushTransferResult:
    """
    Результат перенесення користувача між кущами.
    """

    user: User

    source_bush_id: int
    target_bush_id: int

    source_binding_deactivated: bool
    target_binding_created: bool

    current_role: UserRole

    transferred_at: datetime
    transferred_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class BulkBindingItemResult:
    """
    Результат одного елемента масової операції.
    """

    user_id: int

    success: bool
    was_created: bool
    was_changed: bool

    error: str | None

    binding: Any | None


@dataclass(slots=True, frozen=True)
class BulkBindingResult:
    """
    Результат масового призначення.
    """

    total_count: int

    success_count: int
    failed_count: int

    created_count: int
    changed_count: int

    items: tuple[
        BulkBindingItemResult,
        ...,
    ]


@dataclass(slots=True, frozen=True)
class UserBindingsResult:
    """
    Усі активні та неактивні прив’язки користувача.
    """

    user: User

    store_bindings: tuple[
        BindingView,
        ...,
    ]

    bush_bindings: tuple[
        BindingView,
        ...,
    ]


class BindingService:
    """
    Сервіс прив’язок користувачів.

    Відповідає за:

    - прив’язку працівника до ТТ;
    - прив’язку адміністратора до куща;
    - прив’язку лева до куща;
    - перенесення між ТТ;
    - перенесення між кущами;
    - основну ТТ користувача;
    - деактивацію доступу;
    - повторну активацію доступу;
    - масові призначення;
    - видалення всіх доступів;
    - AuditLog усіх змін.

    Commit виконується у middleware або handler.
    """

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
    # ОТРИМАННЯ ПРИВ’ЯЗОК КОРИСТУВАЧА
    # ==========================================

    async def get_user_bindings(
        self,
        *,
        actor: User,
        user_id: int,
        active_only: bool = False,
    ) -> UserBindingsResult:
        """
        Повертає всі прив’язки користувача.
        """

        target = await self.get_user_or_raise(
            user_id
        )

        await self.ensure_can_view_user_bindings(
            actor=actor,
            target=target,
        )

        store_bindings_raw = (
            await self.invoke_binding_repository(
                method_names=(
                    "get_user_store_bindings",
                    "get_store_bindings_for_user",
                    "list_user_store_bindings",
                    "get_store_bindings",
                ),
                user_id=target.id,
                active_only=active_only,
            )
        )

        bush_bindings_raw = (
            await self.invoke_binding_repository(
                method_names=(
                    "get_user_bush_bindings",
                    "get_bush_bindings_for_user",
                    "list_user_bush_bindings",
                    "get_bush_bindings",
                ),
                user_id=target.id,
                active_only=active_only,
            )
        )

        store_views = tuple(
            self.build_binding_view(
                binding,
                scope=BindingScope.STORE,
            )
            for binding in self.as_list(
                store_bindings_raw
            )
        )

        bush_views = tuple(
            self.build_binding_view(
                binding,
                scope=BindingScope.BUSH,
            )
            for binding in self.as_list(
                bush_bindings_raw
            )
        )

        return UserBindingsResult(
            user=target,
            store_bindings=store_views,
            bush_bindings=bush_views,
        )

    # ==========================================
    # КОРИСТУВАЧІ ТОРГОВОЇ ТОЧКИ
    # ==========================================

    async def get_store_users(
        self,
        *,
        actor: User,
        store_id: int,
        active_only: bool = True,
    ) -> list[User]:
        """
        Повертає користувачів конкретної ТТ.
        """

        decision = await self.access.can_manage_store(
            actor,
            store_id,
        )

        decision.raise_if_denied()

        result = await self.invoke_binding_repository(
            method_names=(
                "get_store_users",
                "list_users_for_store",
                "get_users_by_store",
                "get_bound_store_users",
            ),
            store_id=store_id,
            active_only=active_only,
        )

        users: list[User] = []

        for item in self.as_list(result):
            if isinstance(item, User):
                users.append(item)
                continue

            user = getattr(
                item,
                "user",
                None,
            )

            if isinstance(user, User):
                users.append(user)

        return users

    # ==========================================
    # КОРИСТУВАЧІ КУЩА
    # ==========================================

    async def get_bush_users(
        self,
        *,
        actor: User,
        bush_id: int,
        active_only: bool = True,
    ) -> list[User]:
        """
        Повертає адміністраторів і левів куща.
        """

        decision = await self.access.can_manage_bush(
            actor,
            bush_id,
        )

        decision.raise_if_denied()

        result = await self.invoke_binding_repository(
            method_names=(
                "get_bush_users",
                "list_users_for_bush",
                "get_users_by_bush",
                "get_bound_bush_users",
            ),
            bush_id=bush_id,
            active_only=active_only,
        )

        users: list[User] = []

        for item in self.as_list(result):
            if isinstance(item, User):
                users.append(item)
                continue

            user = getattr(
                item,
                "user",
                None,
            )

            if isinstance(user, User):
                users.append(user)

        return users

    # ==========================================
    # ПРИВ’ЯЗКА ДО ТТ
    # ==========================================

    async def assign_store(
        self,
        *,
        actor: User,
        user_id: int,
        store_id: int,
        make_primary: bool = True,
        activate_user: bool = True,
        change_role: bool = True,
        reason: str | None = None,
        assigned_at: datetime | None = None,
    ) -> BindingChangeResult:
        """
        Прив’язує користувача до торгової точки.
        """

        now = assigned_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="assigned_at",
        )

        decision = await self.access.can_manage_store(
            actor,
            store_id,
        )

        decision.raise_if_denied()

        store = await self.get_store_or_raise(
            store_id
        )

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

        existing = (
            await self.get_store_binding(
                user_id=target.id,
                store_id=store.id,
                active_only=False,
                for_update=True,
            )
        )

        previous_values = (
            self.binding_snapshot(existing)
        )

        result = (
            await self.invoke_binding_repository(
                method_names=(
                    "bind_user_to_store",
                    "upsert_store_binding",
                    "create_store_binding",
                    "assign_store",
                    "add_user_to_store",
                ),
                user_id=target.id,
                store_id=store.id,
                created_by_id=actor.id,
                assigned_by_id=actor.id,
                updated_by_id=actor.id,
                created_at=now,
                assigned_at=now,
                updated_at=now,
                is_active=True,
                is_primary=make_primary,
                make_primary=make_primary,
                reason=self.normalize_optional_text(
                    reason
                ),
            )
        )

        binding, was_created, was_changed = (
            self.parse_change_result(
                result,
                existing=existing,
            )
        )

        was_reactivated = bool(
            existing is not None
            and not self.binding_is_active(
                existing
            )
            and self.binding_is_active(
                binding
            )
        )

        role_changed = False

        if (
            change_role
            and target.role
            != UserRole.STORE_USER
        ):
            target.role = UserRole.STORE_USER
            role_changed = True

        if activate_user:
            active_status = (
                self.resolve_active_status(
                    target
                )
            )

            if active_status is not None:
                target.status = active_status

            self.set_existing_attribute(
                target,
                False,
                "is_blocked",
            )

        self.set_existing_attribute(
            target,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(target)
        await self.session.flush()

        current_values = (
            self.binding_snapshot(binding)
        )

        await self.log_binding_change(
            actor=actor,
            binding=binding,
            scope=BindingScope.STORE,
            description=(
                "Користувача прив’язано до "
                f"ТТ {self.store_display_name(store)}"
            ),
            reason=reason,
            previous_values=previous_values,
            current_values={
                **current_values,
                "role_changed": role_changed,
            },
            was_created=was_created,
        )

        return BindingChangeResult(
            binding=binding,
            view=self.build_binding_view(
                binding,
                scope=BindingScope.STORE,
            ),
            was_created=was_created,
            was_changed=was_changed,
            was_reactivated=was_reactivated,
            previous_values=previous_values,
            current_values=current_values,
        )

    # ==========================================
    # ПРИВ’ЯЗКА ДО КУЩА
    # ==========================================

    async def assign_bush(
        self,
        *,
        actor: User,
        user_id: int,
        bush_id: int,
        role: UserRole,
        activate_user: bool = True,
        reason: str | None = None,
        assigned_at: datetime | None = None,
    ) -> BindingChangeResult:
        """
        Прив’язує адміністратора або лева до куща.
        """

        if role not in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            raise ValueError(
                "До куща можна прив’язати лише "
                "BUSH_ADMIN або LION."
            )

        now = assigned_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="assigned_at",
        )

        decision = await self.access.can_manage_bush(
            actor,
            bush_id,
        )

        decision.raise_if_denied()

        bush = await self.get_bush_or_raise(
            bush_id
        )

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        await self.ensure_can_assign_bush_role(
            actor=actor,
            target=target,
            role=role,
            bush_id=bush.id,
        )

        existing = (
            await self.get_bush_binding(
                user_id=target.id,
                bush_id=bush.id,
                active_only=False,
                for_update=True,
            )
        )

        previous_values = (
            self.binding_snapshot(existing)
        )

        result = (
            await self.invoke_binding_repository(
                method_names=(
                    "bind_user_to_bush",
                    "upsert_bush_binding",
                    "create_bush_binding",
                    "assign_bush",
                    "add_user_to_bush",
                ),
                user_id=target.id,
                bush_id=bush.id,
                created_by_id=actor.id,
                assigned_by_id=actor.id,
                updated_by_id=actor.id,
                created_at=now,
                assigned_at=now,
                updated_at=now,
                is_active=True,
                role=role,
                target_role=role,
                reason=self.normalize_optional_text(
                    reason
                ),
            )
        )

        binding, was_created, was_changed = (
            self.parse_change_result(
                result,
                existing=existing,
            )
        )

        was_reactivated = bool(
            existing is not None
            and not self.binding_is_active(
                existing
            )
            and self.binding_is_active(
                binding
            )
        )

        role_changed = target.role != role

        target.role = role

        if activate_user:
            active_status = (
                self.resolve_active_status(
                    target
                )
            )

            if active_status is not None:
                target.status = active_status

            self.set_existing_attribute(
                target,
                False,
                "is_blocked",
            )

        self.set_existing_attribute(
            target,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(target)
        await self.session.flush()

        current_values = (
            self.binding_snapshot(binding)
        )

        await self.log_binding_change(
            actor=actor,
            binding=binding,
            scope=BindingScope.BUSH,
            description=(
                f"Користувача прив’язано до "
                f"куща {self.bush_display_name(bush)}"
            ),
            reason=reason,
            previous_values=previous_values,
            current_values={
                **current_values,
                "role": role.value,
                "role_changed": role_changed,
            },
            was_created=was_created,
        )

        return BindingChangeResult(
            binding=binding,
            view=self.build_binding_view(
                binding,
                scope=BindingScope.BUSH,
            ),
            was_created=was_created,
            was_changed=was_changed,
            was_reactivated=was_reactivated,
            previous_values=previous_values,
            current_values=current_values,
        )

    # ==========================================
    # ОСНОВНА ТОРГОВА ТОЧКА
    # ==========================================

    async def set_primary_store(
        self,
        *,
        actor: User,
        user_id: int,
        store_id: int,
        reason: str | None = None,
    ) -> BindingChangeResult:
        """
        Робить вибрану ТТ основною для користувача.
        """

        decision = await self.access.can_manage_store(
            actor,
            store_id,
        )

        decision.raise_if_denied()

        target = await self.get_user_or_raise(
            user_id
        )

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

        binding = (
            await self.get_store_binding(
                user_id=target.id,
                store_id=store_id,
                active_only=True,
                for_update=True,
            )
        )

        if binding is None:
            raise ValueError(
                "Користувач не має активної "
                "прив’язки до цієї ТТ."
            )

        previous_values = (
            self.binding_snapshot(binding)
        )

        result = (
            await self.invoke_binding_repository(
                method_names=(
                    "set_primary_store",
                    "set_primary_store_binding",
                    "mark_store_as_primary",
                    "change_primary_store",
                ),
                user_id=target.id,
                store_id=store_id,
                binding_id=self.binding_id(
                    binding
                ),
                updated_by_id=actor.id,
                changed_by_id=actor.id,
                reason=self.normalize_optional_text(
                    reason
                ),
            )
        )

        changed_binding = (
            self.extract_binding(result)
            or binding
        )

        current_values = (
            self.binding_snapshot(
                changed_binding
            )
        )

        await self.log_binding_change(
            actor=actor,
            binding=changed_binding,
            scope=BindingScope.STORE,
            description=(
                "Змінено основну торгову точку "
                "користувача"
            ),
            reason=reason,
            previous_values=previous_values,
            current_values=current_values,
            was_created=False,
        )

        return BindingChangeResult(
            binding=changed_binding,
            view=self.build_binding_view(
                changed_binding,
                scope=BindingScope.STORE,
            ),
            was_created=False,
            was_changed=(
                previous_values
                != current_values
            ),
            was_reactivated=False,
            previous_values=previous_values,
            current_values=current_values,
        )

    # ==========================================
    # ПЕРЕНЕСЕННЯ МІЖ ТТ
    # ==========================================

    async def transfer_store(
        self,
        *,
        actor: User,
        user_id: int,
        source_store_id: int,
        target_store_id: int,
        reason: str,
        make_primary: bool = True,
        transferred_at: datetime | None = None,
    ) -> StoreTransferResult:
        """
        Переносить користувача з однієї ТТ на іншу.
        """

        if source_store_id == target_store_id:
            raise ValueError(
                "Початкова та нова ТТ "
                "не можуть бути однаковими."
            )

        now = transferred_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="transferred_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        source_decision = (
            await self.access.can_manage_store(
                actor,
                source_store_id,
            )
        )

        source_decision.raise_if_denied()

        target_decision = (
            await self.access.can_manage_store(
                actor,
                target_store_id,
            )
        )

        target_decision.raise_if_denied()

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

        source_binding = (
            await self.get_store_binding(
                user_id=target.id,
                store_id=source_store_id,
                active_only=True,
                for_update=True,
            )
        )

        if source_binding is None:
            raise ValueError(
                "Користувач не має активної "
                "прив’язки до початкової ТТ."
            )

        deactivation = (
            await self.deactivate_store_binding(
                actor=actor,
                user_id=target.id,
                store_id=source_store_id,
                reason=normalized_reason,
                deactivated_at=now,
            )
        )

        assignment = await self.assign_store(
            actor=actor,
            user_id=target.id,
            store_id=target_store_id,
            make_primary=make_primary,
            activate_user=True,
            change_role=True,
            reason=normalized_reason,
            assigned_at=now,
        )

        await self.log_user_transfer(
            actor=actor,
            target=target,
            description=(
                "Користувача перенесено між ТТ"
            ),
            reason=normalized_reason,
            previous_values={
                "store_id": source_store_id,
            },
            current_values={
                "store_id": target_store_id,
            },
        )

        return StoreTransferResult(
            user=target,
            source_store_id=source_store_id,
            target_store_id=target_store_id,
            source_binding_deactivated=(
                deactivation.was_deactivated
            ),
            target_binding_created=(
                assignment.was_created
                or assignment.was_reactivated
                or assignment.was_changed
            ),
            role_changed=(
                target.role
                == UserRole.STORE_USER
            ),
            transferred_at=now,
            transferred_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # ПЕРЕНЕСЕННЯ МІЖ КУЩАМИ
    # ==========================================

    async def transfer_bush(
        self,
        *,
        actor: User,
        user_id: int,
        source_bush_id: int,
        target_bush_id: int,
        role: UserRole,
        reason: str,
        transferred_at: datetime | None = None,
    ) -> BushTransferResult:
        """
        Переносить адміністратора або лева
        між кущами.
        """

        if source_bush_id == target_bush_id:
            raise ValueError(
                "Початковий та новий кущ "
                "не можуть бути однаковими."
            )

        if role not in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            raise ValueError(
                "Для куща доступні лише ролі "
                "BUSH_ADMIN або LION."
            )

        now = transferred_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="transferred_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        source_decision = (
            await self.access.can_manage_bush(
                actor,
                source_bush_id,
            )
        )

        source_decision.raise_if_denied()

        target_decision = (
            await self.access.can_manage_bush(
                actor,
                target_bush_id,
            )
        )

        target_decision.raise_if_denied()

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        source_binding = (
            await self.get_bush_binding(
                user_id=target.id,
                bush_id=source_bush_id,
                active_only=True,
                for_update=True,
            )
        )

        if source_binding is None:
            raise ValueError(
                "Користувач не має активної "
                "прив’язки до початкового куща."
            )

        deactivation = (
            await self.deactivate_bush_binding(
                actor=actor,
                user_id=target.id,
                bush_id=source_bush_id,
                reason=normalized_reason,
                deactivated_at=now,
            )
        )

        assignment = await self.assign_bush(
            actor=actor,
            user_id=target.id,
            bush_id=target_bush_id,
            role=role,
            activate_user=True,
            reason=normalized_reason,
            assigned_at=now,
        )

        await self.log_user_transfer(
            actor=actor,
            target=target,
            description=(
                "Користувача перенесено між кущами"
            ),
            reason=normalized_reason,
            previous_values={
                "bush_id": source_bush_id,
                "role": target.role.value,
            },
            current_values={
                "bush_id": target_bush_id,
                "role": role.value,
            },
        )

        return BushTransferResult(
            user=target,
            source_bush_id=source_bush_id,
            target_bush_id=target_bush_id,
            source_binding_deactivated=(
                deactivation.was_deactivated
            ),
            target_binding_created=(
                assignment.was_created
                or assignment.was_reactivated
                or assignment.was_changed
            ),
            current_role=role,
            transferred_at=now,
            transferred_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # ДЕАКТИВАЦІЯ ПРИВ’ЯЗКИ ДО ТТ
    # ==========================================

    async def deactivate_store_binding(
        self,
        *,
        actor: User,
        user_id: int,
        store_id: int,
        reason: str,
        deactivated_at: datetime | None = None,
    ) -> BindingDeactivationResult:
        """
        Деактивує доступ користувача до ТТ.
        """

        now = deactivated_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="deactivated_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        decision = await self.access.can_manage_store(
            actor,
            store_id,
        )

        decision.raise_if_denied()

        target = await self.get_user_or_raise(
            user_id
        )

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

        binding = (
            await self.get_store_binding(
                user_id=user_id,
                store_id=store_id,
                active_only=False,
                for_update=True,
            )
        )

        if binding is None:
            return BindingDeactivationResult(
                binding_id=None,
                user_id=user_id,
                scope=BindingScope.STORE,
                store_id=store_id,
                bush_id=None,
                was_deactivated=False,
                deactivated_at=now,
                deactivated_by_id=actor.id,
                reason=normalized_reason,
            )

        previous_values = (
            self.binding_snapshot(binding)
        )

        result = (
            await self.invoke_binding_repository(
                method_names=(
                    "deactivate_store_binding",
                    "remove_store_binding",
                    "unbind_user_from_store",
                    "remove_user_from_store",
                    "deactivate_binding",
                ),
                binding_id=self.binding_id(
                    binding
                ),
                user_id=user_id,
                store_id=store_id,
                deactivated_by_id=actor.id,
                removed_by_id=actor.id,
                deactivated_at=now,
                removed_at=now,
                reason=normalized_reason,
            )
        )

        was_deactivated = self.result_to_bool(
            result,
            default=True,
        )

        changed_binding = (
            self.extract_binding(result)
            or binding
        )

        if was_deactivated:
            await self.log_binding_deactivation(
                actor=actor,
                binding=changed_binding,
                scope=BindingScope.STORE,
                description=(
                    "Деактивовано прив’язку "
                    "користувача до ТТ"
                ),
                reason=normalized_reason,
                previous_values=previous_values,
                current_values=(
                    self.binding_snapshot(
                        changed_binding
                    )
                ),
            )

        return BindingDeactivationResult(
            binding_id=self.binding_id(
                changed_binding
            ),
            user_id=user_id,
            scope=BindingScope.STORE,
            store_id=store_id,
            bush_id=None,
            was_deactivated=was_deactivated,
            deactivated_at=now,
            deactivated_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # ДЕАКТИВАЦІЯ ПРИВ’ЯЗКИ ДО КУЩА
    # ==========================================

    async def deactivate_bush_binding(
        self,
        *,
        actor: User,
        user_id: int,
        bush_id: int,
        reason: str,
        deactivated_at: datetime | None = None,
    ) -> BindingDeactivationResult:
        """
        Деактивує доступ користувача до куща.
        """

        now = deactivated_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="deactivated_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        decision = await self.access.can_manage_bush(
            actor,
            bush_id,
        )

        decision.raise_if_denied()

        target = await self.get_user_or_raise(
            user_id
        )

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

        binding = (
            await self.get_bush_binding(
                user_id=user_id,
                bush_id=bush_id,
                active_only=False,
                for_update=True,
            )
        )

        if binding is None:
            return BindingDeactivationResult(
                binding_id=None,
                user_id=user_id,
                scope=BindingScope.BUSH,
                store_id=None,
                bush_id=bush_id,
                was_deactivated=False,
                deactivated_at=now,
                deactivated_by_id=actor.id,
                reason=normalized_reason,
            )

        previous_values = (
            self.binding_snapshot(binding)
        )

        result = (
            await self.invoke_binding_repository(
                method_names=(
                    "deactivate_bush_binding",
                    "remove_bush_binding",
                    "unbind_user_from_bush",
                    "remove_user_from_bush",
                    "deactivate_binding",
                ),
                binding_id=self.binding_id(
                    binding
                ),
                user_id=user_id,
                bush_id=bush_id,
                deactivated_by_id=actor.id,
                removed_by_id=actor.id,
                deactivated_at=now,
                removed_at=now,
                reason=normalized_reason,
            )
        )

        was_deactivated = self.result_to_bool(
            result,
            default=True,
        )

        changed_binding = (
            self.extract_binding(result)
            or binding
        )

        if was_deactivated:
            await self.log_binding_deactivation(
                actor=actor,
                binding=changed_binding,
                scope=BindingScope.BUSH,
                description=(
                    "Деактивовано прив’язку "
                    "користувача до куща"
                ),
                reason=normalized_reason,
                previous_values=previous_values,
                current_values=(
                    self.binding_snapshot(
                        changed_binding
                    )
                ),
            )

        return BindingDeactivationResult(
            binding_id=self.binding_id(
                changed_binding
            ),
            user_id=user_id,
            scope=BindingScope.BUSH,
            store_id=None,
            bush_id=bush_id,
            was_deactivated=was_deactivated,
            deactivated_at=now,
            deactivated_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # ВІДНОВЛЕННЯ ПРИВ’ЯЗКИ
    # ==========================================

    async def reactivate_binding(
        self,
        *,
        actor: User,
        binding_id: int,
        reason: str,
        reactivated_at: datetime | None = None,
    ) -> BindingChangeResult:
        """
        Повторно активує деактивовану прив’язку.
        """

        if binding_id <= 0:
            raise ValueError(
                "ID прив’язки повинен бути "
                "більшим за нуль."
            )

        now = reactivated_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="reactivated_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        binding = (
            await self.invoke_binding_repository(
                method_names=(
                    "get_by_id_or_raise",
                    "get_binding_by_id_or_raise",
                    "get_by_id",
                ),
                binding_id=binding_id,
                entity_id=binding_id,
                for_update=True,
            )
        )

        if binding is None:
            raise ValueError(
                "Прив’язку не знайдено."
            )

        scope = self.detect_binding_scope(
            binding
        )

        await self.ensure_can_manage_binding(
            actor=actor,
            binding=binding,
            scope=scope,
        )

        previous_values = (
            self.binding_snapshot(binding)
        )

        result = (
            await self.invoke_binding_repository(
                method_names=(
                    "reactivate_binding",
                    "activate_binding",
                    "restore_binding",
                ),
                binding_id=binding_id,
                activated_by_id=actor.id,
                reactivated_by_id=actor.id,
                activated_at=now,
                reactivated_at=now,
                reason=normalized_reason,
                is_active=True,
            )
        )

        changed_binding = (
            self.extract_binding(result)
            or binding
        )

        current_values = (
            self.binding_snapshot(
                changed_binding
            )
        )

        await self.log_binding_change(
            actor=actor,
            binding=changed_binding,
            scope=scope,
            description=(
                "Повторно активовано прив’язку "
                "користувача"
            ),
            reason=normalized_reason,
            previous_values=previous_values,
            current_values=current_values,
            was_created=False,
        )

        return BindingChangeResult(
            binding=changed_binding,
            view=self.build_binding_view(
                changed_binding,
                scope=scope,
            ),
            was_created=False,
            was_changed=(
                previous_values
                != current_values
            ),
            was_reactivated=True,
            previous_values=previous_values,
            current_values=current_values,
        )

    # ==========================================
    # МАСОВЕ ПРИЗНАЧЕННЯ НА ТТ
    # ==========================================

    async def bulk_assign_store(
        self,
        *,
        actor: User,
        user_ids: list[int] | set[int],
        store_id: int,
        make_primary: bool = True,
        reason: str | None = None,
        assigned_at: datetime | None = None,
    ) -> BulkBindingResult:
        """
        Масово прив’язує користувачів до однієї ТТ.
        """

        normalized_user_ids = self.normalize_ids(
            user_ids
        )

        now = assigned_at or datetime.now(UTC)

        decision = await self.access.can_manage_store(
            actor,
            store_id,
        )

        decision.raise_if_denied()

        items: list[BulkBindingItemResult] = []

        for user_id in normalized_user_ids:
            try:
                result = await self.assign_store(
                    actor=actor,
                    user_id=user_id,
                    store_id=store_id,
                    make_primary=make_primary,
                    activate_user=True,
                    change_role=True,
                    reason=reason,
                    assigned_at=now,
                )

                items.append(
                    BulkBindingItemResult(
                        user_id=user_id,
                        success=True,
                        was_created=(
                            result.was_created
                        ),
                        was_changed=(
                            result.was_changed
                        ),
                        error=None,
                        binding=result.binding,
                    )
                )

            except Exception as error:
                items.append(
                    BulkBindingItemResult(
                        user_id=user_id,
                        success=False,
                        was_created=False,
                        was_changed=False,
                        error=str(error),
                        binding=None,
                    )
                )

        return self.build_bulk_result(items)

    # ==========================================
    # МАСОВЕ ПРИЗНАЧЕННЯ НА КУЩ
    # ==========================================

    async def bulk_assign_bush(
        self,
        *,
        actor: User,
        user_ids: list[int] | set[int],
        bush_id: int,
        role: UserRole,
        reason: str | None = None,
        assigned_at: datetime | None = None,
    ) -> BulkBindingResult:
        """
        Масово прив’язує адміністраторів
        або левів до куща.
        """

        normalized_user_ids = self.normalize_ids(
            user_ids
        )

        now = assigned_at or datetime.now(UTC)

        decision = await self.access.can_manage_bush(
            actor,
            bush_id,
        )

        decision.raise_if_denied()

        items: list[BulkBindingItemResult] = []

        for user_id in normalized_user_ids:
            try:
                result = await self.assign_bush(
                    actor=actor,
                    user_id=user_id,
                    bush_id=bush_id,
                    role=role,
                    activate_user=True,
                    reason=reason,
                    assigned_at=now,
                )

                items.append(
                    BulkBindingItemResult(
                        user_id=user_id,
                        success=True,
                        was_created=(
                            result.was_created
                        ),
                        was_changed=(
                            result.was_changed
                        ),
                        error=None,
                        binding=result.binding,
                    )
                )

            except Exception as error:
                items.append(
                    BulkBindingItemResult(
                        user_id=user_id,
                        success=False,
                        was_created=False,
                        was_changed=False,
                        error=str(error),
                        binding=None,
                    )
                )

        return self.build_bulk_result(items)

    # ==========================================
    # ВИДАЛЕННЯ ВСІХ ДОСТУПІВ
    # ==========================================

    async def deactivate_all_user_bindings(
        self,
        *,
        actor: User,
        user_id: int,
        reason: str,
        deactivated_at: datetime | None = None,
    ) -> int:
        """
        Деактивує всі прив’язки користувача.
        """

        now = deactivated_at or datetime.now(UTC)

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        target = await self.get_user_or_raise(
            user_id
        )

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

        result = (
            await self.invoke_binding_repository(
                method_names=(
                    "deactivate_all_for_user",
                    "deactivate_user_bindings",
                    "remove_all_user_bindings",
                    "unbind_user_everywhere",
                ),
                user_id=target.id,
                deactivated_by_id=actor.id,
                removed_by_id=actor.id,
                deactivated_at=now,
                removed_at=now,
                reason=normalized_reason,
            )
        )

        deactivated_count = self.result_to_count(
            result
        )

        if deactivated_count > 0:
            await self.log_user_transfer(
                actor=actor,
                target=target,
                description=(
                    "Деактивовано всі прив’язки "
                    "користувача"
                ),
                reason=normalized_reason,
                previous_values={
                    "active_bindings": (
                        deactivated_count
                    ),
                },
                current_values={
                    "active_bindings": 0,
                },
            )

        return deactivated_count

    # ==========================================
    # ПОШУК ПРИВ’ЯЗКИ
    # ==========================================

    async def get_store_binding(
        self,
        *,
        user_id: int,
        store_id: int,
        active_only: bool,
        for_update: bool,
    ) -> Any | None:
        """
        Повертає прив’язку користувача до ТТ.
        """

        return await self.invoke_binding_repository(
            method_names=(
                "get_store_binding",
                "get_user_store_binding",
                "find_store_binding",
                "get_binding_for_store",
            ),
            user_id=user_id,
            store_id=store_id,
            active_only=active_only,
            for_update=for_update,
        )

    async def get_bush_binding(
        self,
        *,
        user_id: int,
        bush_id: int,
        active_only: bool,
        for_update: bool,
    ) -> Any | None:
        """
        Повертає прив’язку користувача до куща.
        """

        return await self.invoke_binding_repository(
            method_names=(
                "get_bush_binding",
                "get_user_bush_binding",
                "find_bush_binding",
                "get_binding_for_bush",
            ),
            user_id=user_id,
            bush_id=bush_id,
            active_only=active_only,
            for_update=for_update,
        )

    # ==========================================
    # ПРАВА ДОСТУПУ
    # ==========================================

    async def ensure_can_view_user_bindings(
        self,
        *,
        actor: User,
        target: User,
    ) -> None:
        """
        Перевіряє право переглядати прив’язки.
        """

        self.access.ensure_active_user(actor)

        if actor.id == target.id:
            return

        if actor.role in {
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
        }:
            return

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

    async def ensure_can_manage_target(
        self,
        *,
        actor: User,
        target: User,
    ) -> None:
        """
        Перевіряє право керування користувачем.
        """

        self.access.ensure_active_user(actor)

        if actor.role == UserRole.ROOT_ADMIN:
            return

        if target.role == UserRole.ROOT_ADMIN:
            raise AccessDeniedError(
                "Керувати ROOT_ADMIN може "
                "лише ROOT_ADMIN."
            )

        if target.role == UserRole.DIRECTOR:
            raise AccessDeniedError(
                "Керувати директором може "
                "лише ROOT_ADMIN."
            )

        if actor.role == UserRole.DIRECTOR:
            return

        bindings = await self.get_user_binding_views(
            user_id=target.id,
            active_only=True,
        )

        for binding in bindings:
            if (
                binding.scope
                == BindingScope.STORE
                and binding.store_id is not None
            ):
                decision = (
                    await self.access.can_manage_store(
                        actor,
                        binding.store_id,
                    )
                )

                if self.decision_is_allowed(
                    decision
                ):
                    return

            if (
                binding.scope
                == BindingScope.BUSH
                and binding.bush_id is not None
            ):
                decision = (
                    await self.access.can_manage_bush(
                        actor,
                        binding.bush_id,
                    )
                )

                if self.decision_is_allowed(
                    decision
                ):
                    return

        raise AccessDeniedError(
            "Недостатньо прав для керування "
            "цим користувачем."
        )

    async def ensure_can_assign_bush_role(
        self,
        *,
        actor: User,
        target: User,
        role: UserRole,
        bush_id: int,
    ) -> None:
        """
        Перевіряє право призначити роль у кущі.
        """

        if role == UserRole.BUSH_ADMIN:
            if actor.role not in {
                UserRole.ROOT_ADMIN,
                UserRole.DIRECTOR,
            }:
                raise AccessDeniedError(
                    "Призначати адміністратора куща "
                    "може лише директор або ROOT_ADMIN."
                )

        decision = await self.access.can_manage_bush(
            actor,
            bush_id,
        )

        decision.raise_if_denied()

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

    async def ensure_can_manage_binding(
        self,
        *,
        actor: User,
        binding: Any,
        scope: BindingScope,
    ) -> None:
        """
        Перевіряє право керування прив’язкою.
        """

        if scope == BindingScope.STORE:
            store_id = self.get_int_attribute(
                binding,
                "store_id",
            )

            if store_id is None:
                raise ValueError(
                    "У прив’язці відсутній store_id."
                )

            decision = (
                await self.access.can_manage_store(
                    actor,
                    store_id,
                )
            )

            decision.raise_if_denied()
            return

        bush_id = self.get_int_attribute(
            binding,
            "bush_id",
        )

        if bush_id is None:
            raise ValueError(
                "У прив’язці відсутній bush_id."
            )

        decision = await self.access.can_manage_bush(
            actor,
            bush_id,
        )

        decision.raise_if_denied()

    # ==========================================
    # УСІ VIEW ПРИВ’ЯЗКИ КОРИСТУВАЧА
    # ==========================================

    async def get_user_binding_views(
        self,
        *,
        user_id: int,
        active_only: bool,
    ) -> list[BindingView]:
        """
        Повертає всі прив’язки без перевірки доступу.
        """

        store_result = (
            await self.invoke_binding_repository(
                method_names=(
                    "get_user_store_bindings",
                    "get_store_bindings_for_user",
                    "list_user_store_bindings",
                ),
                user_id=user_id,
                active_only=active_only,
            )
        )

        bush_result = (
            await self.invoke_binding_repository(
                method_names=(
                    "get_user_bush_bindings",
                    "get_bush_bindings_for_user",
                    "list_user_bush_bindings",
                ),
                user_id=user_id,
                active_only=active_only,
            )
        )

        result: list[BindingView] = []

        result.extend(
            self.build_binding_view(
                binding,
                scope=BindingScope.STORE,
            )
            for binding in self.as_list(
                store_result
            )
        )

        result.extend(
            self.build_binding_view(
                binding,
                scope=BindingScope.BUSH,
            )
            for binding in self.as_list(
                bush_result
            )
        )

        return result

    # ==========================================
    # МОДЕЛІ
    # ==========================================

    async def get_user_or_raise(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> User:
        """
        Повертає користувача за ID.
        """

        if user_id <= 0:
            raise ValueError(
                "ID користувача повинен бути "
                "більшим за нуль."
            )

        statement = (
            select(User)
            .where(
                User.id == user_id
            )
        )

        if for_update:
            statement = (
                statement.with_for_update()
            )

        user = await self.session.scalar(
            statement
        )

        if user is None:
            raise ValueError(
                "Користувача не знайдено."
            )

        return user

    async def get_store_or_raise(
        self,
        store_id: int,
    ) -> Store:
        """
        Повертає торгову точку.
        """

        if store_id <= 0:
            raise ValueError(
                "ID торгової точки повинен бути "
                "більшим за нуль."
            )

        store = await self.session.get(
            Store,
            store_id,
        )

        if store is None:
            raise ValueError(
                "Торгову точку не знайдено."
            )

        if not bool(
            getattr(
                store,
                "is_active",
                True,
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
        Повертає кущ.
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

    # ==========================================
    # AUDIT LOG
    # ==========================================

    async def log_binding_change(
        self,
        *,
        actor: User,
        binding: Any,
        scope: BindingScope,
        description: str,
        reason: str | None,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
        was_created: bool,
    ) -> None:
        """
        Фіксує створення або зміну прив’язки.
        """

        action = self.resolve_audit_action(
            "create" if was_created else "update",
            "created" if was_created else "changed",
        )

        entity_type = self.resolve_entity_type(
            "binding",
            "user_binding",
            "user",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=self.binding_id(
                binding
            ),
            context=AuditContext(
                actor_user_id=actor.id,
                reason=self.normalize_optional_text(
                    reason
                ),
                description=description,
                source="telegram_bot",
            ),
            old_values=previous_values,
            new_values={
                **current_values,
                "scope": scope.value,
            },
        )

    async def log_binding_deactivation(
        self,
        *,
        actor: User,
        binding: Any,
        scope: BindingScope,
        description: str,
        reason: str,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
    ) -> None:
        """
        Фіксує деактивацію прив’язки.
        """

        action = self.resolve_audit_action(
            "deactivate",
            "delete",
            "removed",
            "update",
        )

        entity_type = self.resolve_entity_type(
            "binding",
            "user_binding",
            "user",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=self.binding_id(
                binding
            ),
            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=description,
                source="telegram_bot",
            ),
            old_values=previous_values,
            new_values={
                **current_values,
                "scope": scope.value,
                "is_active": False,
            },
        )

    async def log_user_transfer(
        self,
        *,
        actor: User,
        target: User,
        description: str,
        reason: str,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
    ) -> None:
        """
        Фіксує перенесення користувача.
        """

        action = self.resolve_audit_action(
            "update",
            "changed",
            "transfer",
        )

        entity_type = self.resolve_entity_type(
            "user",
            "account",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=target.id,
            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=description,
                source="telegram_bot",
            ),
            old_values=previous_values,
            new_values=current_values,
        )

    # ==========================================
    # ПЕРЕТВОРЕННЯ ПРИВ’ЯЗКИ
    # ==========================================

    def build_binding_view(
        self,
        binding: Any,
        *,
        scope: BindingScope,
    ) -> BindingView:
        """
        Формує безпечний BindingView.
        """

        return BindingView(
            id=self.binding_id(binding),
            scope=scope,
            user_id=(
                self.get_int_attribute(
                    binding,
                    "user_id",
                )
                or 0
            ),
            store_id=self.get_int_attribute(
                binding,
                "store_id",
            ),
            bush_id=self.get_int_attribute(
                binding,
                "bush_id",
            ),
            is_active=self.binding_is_active(
                binding
            ),
            is_primary=bool(
                self.get_attribute(
                    binding,
                    "is_primary",
                    "primary",
                    default=False,
                )
            ),
            created_by_id=(
                self.get_int_attribute(
                    binding,
                    "created_by_id",
                )
            ),
            assigned_by_id=(
                self.get_int_attribute(
                    binding,
                    "assigned_by_id",
                )
            ),
            created_at=self.get_attribute(
                binding,
                "created_at",
                default=None,
            ),
            assigned_at=self.get_attribute(
                binding,
                "assigned_at",
                default=None,
            ),
            deactivated_at=self.get_attribute(
                binding,
                "deactivated_at",
                "removed_at",
                default=None,
            ),
            deactivated_by_id=(
                self.get_int_attribute(
                    binding,
                    "deactivated_by_id",
                    "removed_by_id",
                )
            ),
            raw_binding=binding,
        )

    def binding_snapshot(
        self,
        binding: Any | None,
    ) -> dict[str, Any]:
        """
        Формує знімок прив’язки.
        """

        if binding is None:
            return {}

        return {
            "id": self.binding_id(binding),
            "user_id": self.get_int_attribute(
                binding,
                "user_id",
            ),
            "store_id": self.get_int_attribute(
                binding,
                "store_id",
            ),
            "bush_id": self.get_int_attribute(
                binding,
                "bush_id",
            ),
            "is_active": (
                self.binding_is_active(
                    binding
                )
            ),
            "is_primary": bool(
                self.get_attribute(
                    binding,
                    "is_primary",
                    "primary",
                    default=False,
                )
            ),
            "created_by_id": (
                self.get_int_attribute(
                    binding,
                    "created_by_id",
                )
            ),
            "assigned_by_id": (
                self.get_int_attribute(
                    binding,
                    "assigned_by_id",
                )
            ),
            "created_at": self.datetime_text(
                self.get_attribute(
                    binding,
                    "created_at",
                    default=None,
                )
            ),
            "assigned_at": self.datetime_text(
                self.get_attribute(
                    binding,
                    "assigned_at",
                    default=None,
                )
            ),
            "deactivated_at": (
                self.datetime_text(
                    self.get_attribute(
                        binding,
                        "deactivated_at",
                        "removed_at",
                        default=None,
                    )
                )
            ),
        }

    # ==========================================
    # АДАПТЕР REPOSITORY
    # ==========================================

    async def invoke_binding_repository(
        self,
        *,
        method_names: tuple[str, ...],
        **kwargs: Any,
    ) -> Any:
        """
        Викликає перший доступний метод
        BindingRepository.
        """

        repository = self.repositories.bindings

        for method_name in method_names:
            method = getattr(
                repository,
                method_name,
                None,
            )

            if (
                method is None
                or not callable(method)
            ):
                continue

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
                accepted_kwargs = dict(kwargs)

            else:
                accepted_kwargs = {
                    key: value
                    for key, value in kwargs.items()
                    if key in signature.parameters
                }

            result = method(
                **accepted_kwargs
            )

            if inspect.isawaitable(result):
                return await result

            return result

        raise AttributeError(
            "BindingRepository не містить "
            "жодного очікуваного методу: "
            + ", ".join(method_names)
        )

    # ==========================================
    # РЕЗУЛЬТАТИ REPOSITORY
    # ==========================================

    def parse_change_result(
        self,
        result: Any,
        *,
        existing: Any | None,
    ) -> tuple[Any, bool, bool]:
        """
        Розбирає результат створення прив’язки.
        """

        binding = self.extract_binding(result)

        if binding is None:
            raise ValueError(
                "BindingRepository не повернув "
                "об’єкт прив’язки."
            )

        was_created = bool(
            self.get_attribute(
                result,
                "was_created",
                "created",
                default=(
                    existing is None
                ),
            )
        )

        was_changed = bool(
            self.get_attribute(
                result,
                "was_changed",
                "changed",
                "updated",
                default=True,
            )
        )

        if isinstance(result, tuple):
            if (
                len(result) > 1
                and isinstance(
                    result[1],
                    bool,
                )
            ):
                was_created = result[1]

            if (
                len(result) > 2
                and isinstance(
                    result[2],
                    bool,
                )
            ):
                was_changed = result[2]

        return (
            binding,
            was_created,
            was_changed,
        )

    @staticmethod
    def extract_binding(
        result: Any,
    ) -> Any | None:
        """
        Витягує модель прив’язки.
        """

        if result is None:
            return None

        if isinstance(result, tuple):
            if result:
                return result[0]

            return None

        for field_name in (
            "binding",
            "entity",
            "model",
            "result",
        ):
            value = getattr(
                result,
                field_name,
                None,
            )

            if value is not None:
                return value

        if hasattr(
            result,
            "user_id",
        ):
            return result

        return None

    @staticmethod
    def as_list(
        result: Any,
    ) -> list[Any]:
        """
        Нормалізує результат у список.
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
    def result_to_bool(
        result: Any,
        *,
        default: bool = False,
    ) -> bool:
        """
        Перетворює результат у bool.
        """

        if result is None:
            return default

        if isinstance(result, bool):
            return result

        if isinstance(result, int):
            return result > 0

        for field_name in (
            "success",
            "changed",
            "was_changed",
            "removed",
            "was_removed",
            "deactivated",
            "was_deactivated",
        ):
            value = getattr(
                result,
                field_name,
                None,
            )

            if value is not None:
                return bool(value)

        return True

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

            if value is not None:
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
    # МАСОВИЙ РЕЗУЛЬТАТ
    # ==========================================

    @staticmethod
    def build_bulk_result(
        items: list[BulkBindingItemResult],
    ) -> BulkBindingResult:
        """
        Формує підсумок масової операції.
        """

        return BulkBindingResult(
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
                item.was_changed
                for item in items
            ),
            items=tuple(items),
        )

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
            "user",
            default=None,
        )

        if result is None:
            raise ValueError(
                "У EntityType відсутнє "
                "значення user."
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
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def detect_binding_scope(
        binding: Any,
    ) -> BindingScope:
        """
        Визначає тип прив’язки.
        """

        store_id = BindingService.get_int_attribute(
            binding,
            "store_id",
        )

        if store_id is not None:
            return BindingScope.STORE

        bush_id = BindingService.get_int_attribute(
            binding,
            "bush_id",
        )

        if bush_id is not None:
            return BindingScope.BUSH

        raise ValueError(
            "Прив’язка не містить "
            "store_id або bush_id."
        )

    @staticmethod
    def binding_id(
        binding: Any,
    ) -> int | None:
        """
        Повертає ID прив’язки.
        """

        return BindingService.get_int_attribute(
            binding,
            "id",
            "binding_id",
        )

    @staticmethod
    def binding_is_active(
        binding: Any,
    ) -> bool:
        """
        Перевіряє активність прив’язки.
        """

        value = BindingService.get_attribute(
            binding,
            "is_active",
            "active",
            default=True,
        )

        return bool(value)

    @staticmethod
    def get_attribute(
        source: Any,
        *names: str,
        default: Any = None,
    ) -> Any:
        """
        Читає перший наявний атрибут.
        """

        if source is None:
            return default

        if isinstance(source, dict):
            for name in names:
                if name in source:
                    return source[name]

            return default

        for name in names:
            if hasattr(source, name):
                return getattr(
                    source,
                    name,
                )

        return default

    @classmethod
    def get_int_attribute(
        cls,
        source: Any,
        *names: str,
    ) -> int | None:
        """
        Читає цілий атрибут.
        """

        value = cls.get_attribute(
            source,
            *names,
            default=None,
        )

        if value is None:
            return None

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def set_existing_attribute(
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
    def decision_is_allowed(
        decision: Any,
    ) -> bool:
        """
        Перевіряє AccessDecision без помилки.
        """

        for field_name in (
            "allowed",
            "is_allowed",
            "granted",
        ):
            value = getattr(
                decision,
                field_name,
                None,
            )

            if value is not None:
                return bool(value)

        try:
            decision.raise_if_denied()
            return True

        except Exception:
            return False

    @staticmethod
    def resolve_active_status(
        user: User,
    ) -> Any | None:
        """
        Знаходить ACTIVE у класі поточного статусу.
        """

        current_status = getattr(
            user,
            "status",
            None,
        )

        if current_status is None:
            return None

        enum_class = type(current_status)

        if not issubclass(
            enum_class,
            Enum,
        ):
            return None

        return BindingService.resolve_enum_member(
            enum_class,
            "active",
            "enabled",
            default=current_status,
        )

    @staticmethod
    def normalize_ids(
        values: list[int] | set[int],
    ) -> list[int]:
        """
        Нормалізує список ID.
        """

        normalized: set[int] = set()

        for value in values:
            try:
                integer_value = int(value)

            except (
                TypeError,
                ValueError,
            ) as error:
                raise ValueError(
                    "У списку користувачів "
                    "є некоректний ID."
                ) from error

            if integer_value <= 0:
                raise ValueError(
                    "ID користувача повинен бути "
                    "більшим за нуль."
                )

            normalized.add(integer_value)

        if not normalized:
            raise ValueError(
                "Список користувачів порожній."
            )

        if len(normalized) > 1000:
            raise ValueError(
                "За один раз можна обробити "
                "не більше 1000 користувачів."
            )

        return sorted(normalized)

    @staticmethod
    def store_display_name(
        store: Store,
    ) -> str:
        """
        Формує назву торгової точки.
        """

        code = getattr(
            store,
            "code",
            None,
        )

        if code:
            return str(code)

        store_number = getattr(
            store,
            "store_number",
            None,
        )

        if store_number is not None:
            return f"SB-{store_number}"

        return f"ТТ #{store.id}"

    @staticmethod
    def bush_display_name(
        bush: Bush,
    ) -> str:
        """
        Формує назву куща.
        """

        name = getattr(
            bush,
            "name",
            None,
        )

        if name:
            return str(name)

        return f"Кущ #{bush.id}"

    @staticmethod
    def datetime_text(
        value: Any,
    ) -> str | None:
        """
        Форматує datetime для AuditLog.
        """

        if isinstance(value, datetime):
            return value.isoformat()

        return None

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
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

        if len(normalized_value) > 2000:
            raise ValueError(
                f"{field_name} занадто довгий."
            )

        return normalized_value

    @staticmethod
    def normalize_optional_text(
        value: str | None,
    ) -> str | None:
        """
        Нормалізує необов’язковий текст.
        """

        if value is None:
            return None

        normalized_value = " ".join(
            value.strip().split()
        )

        return normalized_value or None

    @staticmethod
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        """
        Перевіряє часовий пояс.
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

    @classmethod
    def format_binding(
        cls,
        binding: BindingView,
    ) -> str:
        """
        Формує текст прив’язки для Telegram.
        """

        status = (
            "активна ✅"
            if binding.is_active
            else "неактивна ❌"
        )

        lines = [
            (
                f"🔗 <b>Прив’язка "
                f"#{binding.id or '—'}</b>"
            ),
            (
                "👤 Користувач: "
                f"<b>#{binding.user_id}</b>"
            ),
            (
                "Статус: "
                f"<b>{status}</b>"
            ),
        ]

        if binding.store_id is not None:
            lines.append(
                "🏪 ТТ: "
                f"<b>#{binding.store_id}</b>"
            )

        if binding.bush_id is not None:
            lines.append(
                "🌿 Кущ: "
                f"<b>#{binding.bush_id}</b>"
            )

        if binding.is_primary:
            lines.append(
                "⭐ Основна прив’язка"
            )

        return "\n".join(lines)

    @staticmethod
    def format_bulk_result(
        result: BulkBindingResult,
    ) -> str:
        """
        Формує підсумок масової операції.
        """

        lines = [
            "🔗 <b>Масове призначення завершено</b>",
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
                "Помилки: "
                f"<b>{result.failed_count}</b>"
            ),
            (
                "Нових прив’язок: "
                f"<b>{result.created_count}</b>"
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
                    "⚠️ <b>Не вдалося:</b>",
                ]
            )

            for item in failed_items[:20]:
                lines.append(
                    "• Користувач "
                    f"<b>#{item.user_id}</b>: "
                    f"{escape(item.error or 'помилка')}"
                )

        return "\n".join(lines)