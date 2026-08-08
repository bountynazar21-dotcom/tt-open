from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from html import escape
from typing import Any, TypeVar

from sqlalchemy import select

from app.database.models.enums import (
    AuditAction,
    EntityType,
    NotificationType,
    UserRole,
    UserStatus,
)
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
class PendingUserView:
    """
    Користувач, який очікує підтвердження.
    """

    id: int
    telegram_id: int | None

    username: str | None
    first_name: str | None
    last_name: str | None

    requested_role: UserRole | None
    requested_store_id: int | None
    requested_bush_id: int | None

    created_at: datetime | None

    raw_user: User

    @property
    def full_name(self) -> str:
        name = " ".join(
            part
            for part in (
                self.first_name,
                self.last_name,
            )
            if part
        ).strip()

        if name:
            return name

        if self.username:
            return f"@{self.username.lstrip('@')}"

        return f"Користувач #{self.id}"


@dataclass(slots=True, frozen=True)
class UserApprovalResult:
    """
    Результат підтвердження користувача.
    """

    user: User

    previous_values: dict[str, Any]
    current_values: dict[str, Any]

    role: UserRole
    store_id: int | None
    bush_id: int | None

    binding_created: bool
    notification_created: bool

    approved_at: datetime
    approved_by_id: int


@dataclass(slots=True, frozen=True)
class UserRejectionResult:
    """
    Результат відхилення користувача.
    """

    user: User

    previous_values: dict[str, Any]
    current_values: dict[str, Any]

    rejected_at: datetime
    rejected_by_id: int

    notification_created: bool
    reason: str


@dataclass(slots=True, frozen=True)
class UserStateChangeResult:
    """
    Результат блокування, розблокування,
    активації або деактивації.
    """

    user: User

    previous_values: dict[str, Any]
    current_values: dict[str, Any]

    changed: bool
    notification_created: bool

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class UserRoleChangeResult:
    """
    Результат зміни ролі.
    """

    user: User

    previous_role: UserRole
    current_role: UserRole

    changed: bool

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class UserAssignmentResult:
    """
    Результат прив’язки користувача.
    """

    user: User

    store_id: int | None
    bush_id: int | None

    binding_created: bool
    role_changed: bool
    status_changed: bool

    assigned_at: datetime
    assigned_by_id: int


@dataclass(slots=True, frozen=True)
class RootAdminBootstrapResult:
    """
    Результат призначення першого ROOT_ADMIN.
    """

    user: User

    was_created: bool
    role_changed: bool
    status_changed: bool

    telegram_id: int
    completed_at: datetime


class AuthService:
    """
    Сервіс управління користувачами.

    Відповідає за:

    - список нових користувачів;
    - підтвердження працівників;
    - відхилення заявок;
    - призначення ролей;
    - прив’язку до ТТ;
    - прив’язку до куща;
    - блокування;
    - розблокування;
    - активацію;
    - деактивацію;
    - створення першого ROOT_ADMIN;
    - сповіщення користувачів;
    - AuditLog усіх змін.

    Telegram API безпосередньо не викликається.
    Повідомлення записуються в NotificationLog.
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
    # СПИСОК НОВИХ КОРИСТУВАЧІВ
    # ==========================================

    async def get_pending_users(
        self,
        *,
        actor: User,
        store_id: int | None = None,
        bush_id: int | None = None,
        limit: int = 200,
    ) -> list[PendingUserView]:
        """
        Повертає користувачів, які очікують
        підтвердження.
        """

        if limit < 1 or limit > 1000:
            raise ValueError(
                "Ліміт повинен бути від 1 до 1000."
            )

        if (
            store_id is not None
            and bush_id is not None
        ):
            raise ValueError(
                "Не можна одночасно вказувати "
                "store_id і bush_id."
            )

        if store_id is not None:
            decision = (
                await self.access.can_manage_store(
                    actor,
                    store_id,
                )
            )

            decision.raise_if_denied()

        elif bush_id is not None:
            decision = (
                await self.access.can_manage_bush(
                    actor,
                    bush_id,
                )
            )

            decision.raise_if_denied()

        else:
            self.access.require_network_management(
                actor
            )

        pending_status = self.resolve_user_status(
            "pending",
            "waiting_approval",
            "unverified",
            default=None,
        )

        if pending_status is None:
            return []

        statement = (
            select(User)
            .where(
                User.status == pending_status
            )
            .order_by(
                User.id.asc()
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        users = list(
            result.unique().all()
        )

        views: list[PendingUserView] = []

        for user in users:
            requested_store_id = (
                self.get_int_attribute(
                    user,
                    "requested_store_id",
                    "pending_store_id",
                    "store_id",
                )
            )

            requested_bush_id = (
                self.get_int_attribute(
                    user,
                    "requested_bush_id",
                    "pending_bush_id",
                    "bush_id",
                )
            )

            if (
                store_id is not None
                and requested_store_id != store_id
            ):
                continue

            if (
                bush_id is not None
                and requested_bush_id != bush_id
            ):
                continue

            requested_role = (
                self.get_user_role_attribute(
                    user,
                    "requested_role",
                    "pending_role",
                    "role",
                )
            )

            views.append(
                PendingUserView(
                    id=user.id,
                    telegram_id=getattr(
                        user,
                        "telegram_id",
                        None,
                    ),
                    username=self.get_text_attribute(
                        user,
                        "telegram_username",
                        "username",
                    ),
                    first_name=self.get_text_attribute(
                        user,
                        "first_name",
                    ),
                    last_name=self.get_text_attribute(
                        user,
                        "last_name",
                    ),
                    requested_role=requested_role,
                    requested_store_id=(
                        requested_store_id
                    ),
                    requested_bush_id=(
                        requested_bush_id
                    ),
                    created_at=getattr(
                        user,
                        "created_at",
                        None,
                    ),
                    raw_user=user,
                )
            )

        return views

    # ==========================================
    # ПІДТВЕРДЖЕННЯ КОРИСТУВАЧА
    # ==========================================

    async def approve_user(
        self,
        *,
        actor: User,
        user_id: int,
        role: UserRole | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        reason: str | None = None,
        approved_at: datetime | None = None,
    ) -> UserApprovalResult:
        """
        Підтверджує користувача та відкриває доступ.

        Для STORE_USER потрібна ТТ.

        Для BUSH_ADMIN або LION потрібен кущ.

        Для DIRECTOR прив’язка не потрібна.
        """

        now = approved_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="approved_at",
        )

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        resolved_role = (
            role
            or self.get_user_role_attribute(
                target,
                "requested_role",
                "pending_role",
                "role",
            )
            or UserRole.STORE_USER
        )

        resolved_store_id = (
            store_id
            if store_id is not None
            else self.get_int_attribute(
                target,
                "requested_store_id",
                "pending_store_id",
                "store_id",
            )
        )

        resolved_bush_id = (
            bush_id
            if bush_id is not None
            else self.get_int_attribute(
                target,
                "requested_bush_id",
                "pending_bush_id",
                "bush_id",
            )
        )

        self.validate_role_scope(
            role=resolved_role,
            store_id=resolved_store_id,
            bush_id=resolved_bush_id,
        )

        await self.ensure_can_assign_role(
            actor=actor,
            target=target,
            role=resolved_role,
            store_id=resolved_store_id,
            bush_id=resolved_bush_id,
        )

        previous_values = self.user_snapshot(
            target
        )

        active_status = self.resolve_user_status(
            "active",
            "enabled",
        )

        self.set_existing_attribute(
            target,
            resolved_role,
            "role",
        )

        self.set_existing_attribute(
            target,
            active_status,
            "status",
        )

        self.set_existing_attribute(
            target,
            False,
            "is_blocked",
        )

        self.set_existing_attribute(
            target,
            actor.id,
            "approved_by_id",
            "verified_by_id",
        )

        self.set_existing_attribute(
            target,
            now,
            "approved_at",
            "verified_at",
        )

        self.set_existing_attribute(
            target,
            now,
            "updated_at",
            "modified_at",
        )

        self.clear_pending_fields(target)

        self.session.add(target)
        await self.session.flush()

        binding_created = False

        if resolved_store_id is not None:
            binding_created = (
                await self.create_store_binding(
                    actor=actor,
                    user=target,
                    store_id=resolved_store_id,
                    assigned_at=now,
                )
            )

        elif resolved_bush_id is not None:
            binding_created = (
                await self.create_bush_binding(
                    actor=actor,
                    user=target,
                    bush_id=resolved_bush_id,
                    assigned_at=now,
                )
            )

        current_values = self.user_snapshot(
            target
        )

        await self.log_user_change(
            actor=actor,
            target=target,
            description=(
                "Підтверджено користувача"
            ),
            reason=reason,
            old_values=previous_values,
            new_values={
                **current_values,
                "store_id": resolved_store_id,
                "bush_id": resolved_bush_id,
            },
        )

        notification_created = (
            await self.queue_user_notification(
                user=target,
                notification_names=(
                    "user_approved",
                    "account_approved",
                    "approval_completed",
                ),
                message_text=(
                    self.build_approval_message(
                        role=resolved_role,
                        store_id=resolved_store_id,
                        bush_id=resolved_bush_id,
                    )
                ),
                suffix=(
                    f"user-approved-{target.id}"
                ),
                scheduled_for=now,
            )
        )

        return UserApprovalResult(
            user=target,
            previous_values=previous_values,
            current_values=current_values,
            role=resolved_role,
            store_id=resolved_store_id,
            bush_id=resolved_bush_id,
            binding_created=binding_created,
            notification_created=(
                notification_created
            ),
            approved_at=now,
            approved_by_id=actor.id,
        )

    # ==========================================
    # ВІДХИЛЕННЯ ЗАЯВКИ
    # ==========================================

    async def reject_user(
        self,
        *,
        actor: User,
        user_id: int,
        reason: str,
        rejected_at: datetime | None = None,
    ) -> UserRejectionResult:
        """Відхиляє заявку нового користувача."""

        now = rejected_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="rejected_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

        previous_values = self.user_snapshot(
            target
        )

        rejected_status = self.resolve_user_status(
            "rejected",
            "declined",
            "inactive",
            "disabled",
        )

        self.set_existing_attribute(
            target,
            rejected_status,
            "status",
        )

        self.set_existing_attribute(
            target,
            actor.id,
            "rejected_by_id",
        )

        self.set_existing_attribute(
            target,
            now,
            "rejected_at",
        )

        self.set_existing_attribute(
            target,
            normalized_reason,
            "rejection_reason",
            "status_reason",
        )

        self.set_existing_attribute(
            target,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(target)
        await self.session.flush()

        current_values = self.user_snapshot(
            target
        )

        await self.log_user_change(
            actor=actor,
            target=target,
            description=(
                "Відхилено заявку користувача"
            ),
            reason=normalized_reason,
            old_values=previous_values,
            new_values=current_values,
        )

        notification_created = (
            await self.queue_user_notification(
                user=target,
                notification_names=(
                    "user_rejected",
                    "account_rejected",
                    "approval_rejected",
                ),
                message_text=(
                    "❌ <b>Заявку відхилено</b>\n\n"
                    f"Причина: {escape(normalized_reason)}"
                ),
                suffix=(
                    f"user-rejected-{target.id}"
                ),
                scheduled_for=now,
            )
        )

        return UserRejectionResult(
            user=target,
            previous_values=previous_values,
            current_values=current_values,
            rejected_at=now,
            rejected_by_id=actor.id,
            notification_created=(
                notification_created
            ),
            reason=normalized_reason,
        )

    # ==========================================
    # ЗМІНА РОЛІ
    # ==========================================

    async def change_role(
        self,
        *,
        actor: User,
        user_id: int,
        new_role: UserRole,
        reason: str,
        changed_at: datetime | None = None,
    ) -> UserRoleChangeResult:
        """Змінює роль користувача."""

        now = changed_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        previous_role = target.role

        await self.ensure_can_assign_role(
            actor=actor,
            target=target,
            role=new_role,
            store_id=None,
            bush_id=None,
            allow_missing_scope=True,
        )

        if previous_role == new_role:
            return UserRoleChangeResult(
                user=target,
                previous_role=previous_role,
                current_role=new_role,
                changed=False,
                changed_at=now,
                changed_by_id=actor.id,
                reason=normalized_reason,
            )

        previous_values = self.user_snapshot(
            target
        )

        target.role = new_role

        self.set_existing_attribute(
            target,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(target)
        await self.session.flush()

        await self.log_user_change(
            actor=actor,
            target=target,
            description=(
                "Змінено роль користувача"
            ),
            reason=normalized_reason,
            old_values=previous_values,
            new_values=self.user_snapshot(
                target
            ),
        )

        await self.queue_user_notification(
            user=target,
            notification_names=(
                "user_role_changed",
                "role_changed",
            ),
            message_text=(
                "🔄 <b>Вашу роль змінено</b>\n\n"
                "Нова роль: "
                f"<b>{escape(self.role_text(new_role))}</b>"
            ),
            suffix=(
                f"role-change-{target.id}-"
                f"{new_role.value}"
            ),
            scheduled_for=now,
        )

        return UserRoleChangeResult(
            user=target,
            previous_role=previous_role,
            current_role=new_role,
            changed=True,
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # БЛОКУВАННЯ
    # ==========================================

    async def block_user(
        self,
        *,
        actor: User,
        user_id: int,
        reason: str,
        changed_at: datetime | None = None,
    ) -> UserStateChangeResult:
        """Блокує доступ користувача."""

        return await self.set_blocked_state(
            actor=actor,
            user_id=user_id,
            blocked=True,
            reason=reason,
            changed_at=changed_at,
        )

    async def unblock_user(
        self,
        *,
        actor: User,
        user_id: int,
        reason: str,
        changed_at: datetime | None = None,
    ) -> UserStateChangeResult:
        """Розблоковує користувача."""

        return await self.set_blocked_state(
            actor=actor,
            user_id=user_id,
            blocked=False,
            reason=reason,
            changed_at=changed_at,
        )

    async def set_blocked_state(
        self,
        *,
        actor: User,
        user_id: int,
        blocked: bool,
        reason: str,
        changed_at: datetime | None,
    ) -> UserStateChangeResult:
        """Встановлює стан блокування."""

        now = changed_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

        if actor.id == target.id and blocked:
            raise AccessDeniedError(
                "Не можна заблокувати власний акаунт."
            )

        previous_values = self.user_snapshot(
            target
        )

        current_blocked = bool(
            getattr(
                target,
                "is_blocked",
                False,
            )
        )

        changed = current_blocked != blocked

        self.set_existing_attribute(
            target,
            blocked,
            "is_blocked",
        )

        if blocked:
            blocked_status = (
                self.resolve_user_status(
                    "blocked",
                    "banned",
                    default=None,
                )
            )

            if blocked_status is not None:
                target.status = blocked_status

            self.set_existing_attribute(
                target,
                actor.id,
                "blocked_by_id",
            )

            self.set_existing_attribute(
                target,
                now,
                "blocked_at",
            )

            self.set_existing_attribute(
                target,
                normalized_reason,
                "block_reason",
                "status_reason",
            )

        else:
            active_status = (
                self.resolve_user_status(
                    "active",
                    "enabled",
                )
            )

            target.status = active_status

            self.set_existing_attribute(
                target,
                None,
                "blocked_by_id",
            )

            self.set_existing_attribute(
                target,
                None,
                "blocked_at",
            )

            self.set_existing_attribute(
                target,
                None,
                "block_reason",
            )

        self.set_existing_attribute(
            target,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(target)
        await self.session.flush()

        current_values = self.user_snapshot(
            target
        )

        if changed:
            await self.log_user_change(
                actor=actor,
                target=target,
                description=(
                    "Заблоковано користувача"
                    if blocked
                    else "Розблоковано користувача"
                ),
                reason=normalized_reason,
                old_values=previous_values,
                new_values=current_values,
            )

        notification_created = False

        if changed and not blocked:
            notification_created = (
                await self.queue_user_notification(
                    user=target,
                    notification_names=(
                        "user_unblocked",
                        "account_unblocked",
                    ),
                    message_text=(
                        "✅ <b>Доступ до бота відновлено</b>"
                    ),
                    suffix=(
                        f"user-unblocked-{target.id}"
                    ),
                    scheduled_for=now,
                )
            )

        return UserStateChangeResult(
            user=target,
            previous_values=previous_values,
            current_values=current_values,
            changed=changed,
            notification_created=(
                notification_created
            ),
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # АКТИВАЦІЯ ТА ДЕАКТИВАЦІЯ
    # ==========================================

    async def activate_user(
        self,
        *,
        actor: User,
        user_id: int,
        reason: str,
        changed_at: datetime | None = None,
    ) -> UserStateChangeResult:
        """Активує користувача."""

        active_status = self.resolve_user_status(
            "active",
            "enabled",
        )

        return await self.set_user_status(
            actor=actor,
            user_id=user_id,
            new_status=active_status,
            reason=reason,
            changed_at=changed_at,
            notification_text=(
                "✅ <b>Ваш акаунт активовано</b>"
            ),
            notification_names=(
                "user_activated",
                "account_activated",
            ),
        )

    async def deactivate_user(
        self,
        *,
        actor: User,
        user_id: int,
        reason: str,
        changed_at: datetime | None = None,
    ) -> UserStateChangeResult:
        """Деактивує користувача."""

        inactive_status = self.resolve_user_status(
            "inactive",
            "deactivated",
            "disabled",
        )

        return await self.set_user_status(
            actor=actor,
            user_id=user_id,
            new_status=inactive_status,
            reason=reason,
            changed_at=changed_at,
            notification_text=None,
            notification_names=(
                "user_deactivated",
                "account_deactivated",
            ),
        )

    async def set_user_status(
        self,
        *,
        actor: User,
        user_id: int,
        new_status: UserStatus,
        reason: str,
        changed_at: datetime | None,
        notification_text: str | None,
        notification_names: tuple[str, ...],
    ) -> UserStateChangeResult:
        """Змінює статус користувача."""

        now = changed_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
        )

        if (
            actor.id == target.id
            and self.status_matches(
                new_status,
                "inactive",
                "deactivated",
                "disabled",
            )
        ):
            raise AccessDeniedError(
                "Не можна деактивувати власний акаунт."
            )

        previous_values = self.user_snapshot(
            target
        )

        changed = target.status != new_status

        target.status = new_status

        if self.status_matches(
            new_status,
            "active",
            "enabled",
        ):
            self.set_existing_attribute(
                target,
                False,
                "is_blocked",
            )

        self.set_existing_attribute(
            target,
            actor.id,
            "status_changed_by_id",
        )

        self.set_existing_attribute(
            target,
            now,
            "status_changed_at",
        )

        self.set_existing_attribute(
            target,
            normalized_reason,
            "status_reason",
        )

        self.set_existing_attribute(
            target,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(target)
        await self.session.flush()

        current_values = self.user_snapshot(
            target
        )

        if changed:
            await self.log_user_change(
                actor=actor,
                target=target,
                description=(
                    "Змінено статус користувача"
                ),
                reason=normalized_reason,
                old_values=previous_values,
                new_values=current_values,
            )

        notification_created = False

        if changed and notification_text:
            notification_created = (
                await self.queue_user_notification(
                    user=target,
                    notification_names=(
                        notification_names
                    ),
                    message_text=(
                        notification_text
                    ),
                    suffix=(
                        f"user-status-{target.id}-"
                        f"{new_status.value}"
                    ),
                    scheduled_for=now,
                )
            )

        return UserStateChangeResult(
            user=target,
            previous_values=previous_values,
            current_values=current_values,
            changed=changed,
            notification_created=(
                notification_created
            ),
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # ПРИВ’ЯЗКА ДО ТТ
    # ==========================================

    async def assign_store(
        self,
        *,
        actor: User,
        user_id: int,
        store_id: int,
        activate: bool = True,
        set_store_role: bool = True,
        assigned_at: datetime | None = None,
    ) -> UserAssignmentResult:
        """Прив’язує користувача до ТТ."""

        now = assigned_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="assigned_at",
        )

        decision = (
            await self.access.can_manage_store(
                actor,
                store_id,
            )
        )

        decision.raise_if_denied()

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        await self.ensure_can_manage_target(
            actor=actor,
            target=target,
            store_id=store_id,
        )

        previous_role = target.role
        previous_status = target.status

        role_changed = False
        status_changed = False

        if (
            set_store_role
            and target.role
            != UserRole.STORE_USER
        ):
            target.role = UserRole.STORE_USER
            role_changed = True

        if activate:
            active_status = (
                self.resolve_user_status(
                    "active",
                    "enabled",
                )
            )

            if target.status != active_status:
                target.status = active_status
                status_changed = True

        self.set_existing_attribute(
            target,
            False,
            "is_blocked",
        )

        self.session.add(target)
        await self.session.flush()

        binding_created = (
            await self.create_store_binding(
                actor=actor,
                user=target,
                store_id=store_id,
                assigned_at=now,
            )
        )

        await self.log_user_change(
            actor=actor,
            target=target,
            description=(
                "Користувача прив’язано до ТТ"
            ),
            reason=None,
            old_values={
                "role": previous_role.value,
                "status": previous_status.value,
                "store_id": None,
            },
            new_values={
                "role": target.role.value,
                "status": target.status.value,
                "store_id": store_id,
            },
        )

        return UserAssignmentResult(
            user=target,
            store_id=store_id,
            bush_id=None,
            binding_created=binding_created,
            role_changed=role_changed,
            status_changed=status_changed,
            assigned_at=now,
            assigned_by_id=actor.id,
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
        activate: bool = True,
        assigned_at: datetime | None = None,
    ) -> UserAssignmentResult:
        """Прив’язує адміністратора або лева до куща."""

        if role not in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            raise ValueError(
                "Для куща доступні лише ролі "
                "BUSH_ADMIN або LION."
            )

        now = assigned_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="assigned_at",
        )

        decision = (
            await self.access.can_manage_bush(
                actor,
                bush_id,
            )
        )

        decision.raise_if_denied()

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        await self.ensure_can_assign_role(
            actor=actor,
            target=target,
            role=role,
            store_id=None,
            bush_id=bush_id,
        )

        previous_role = target.role
        previous_status = target.status

        role_changed = target.role != role
        status_changed = False

        target.role = role

        if activate:
            active_status = (
                self.resolve_user_status(
                    "active",
                    "enabled",
                )
            )

            status_changed = (
                target.status != active_status
            )

            target.status = active_status

        self.set_existing_attribute(
            target,
            False,
            "is_blocked",
        )

        self.session.add(target)
        await self.session.flush()

        binding_created = (
            await self.create_bush_binding(
                actor=actor,
                user=target,
                bush_id=bush_id,
                assigned_at=now,
            )
        )

        await self.log_user_change(
            actor=actor,
            target=target,
            description=(
                "Користувача прив’язано до куща"
            ),
            reason=None,
            old_values={
                "role": previous_role.value,
                "status": previous_status.value,
                "bush_id": None,
            },
            new_values={
                "role": target.role.value,
                "status": target.status.value,
                "bush_id": bush_id,
            },
        )

        return UserAssignmentResult(
            user=target,
            store_id=None,
            bush_id=bush_id,
            binding_created=binding_created,
            role_changed=role_changed,
            status_changed=status_changed,
            assigned_at=now,
            assigned_by_id=actor.id,
        )

    # ==========================================
    # ВИДАЛЕННЯ ПРИВ’ЯЗКИ
    # ==========================================

    async def remove_store_assignment(
        self,
        *,
        actor: User,
        user_id: int,
        store_id: int,
        reason: str,
        removed_at: datetime | None = None,
    ) -> bool:
        """Видаляє або деактивує прив’язку до ТТ."""

        now = removed_at or datetime.now(UTC)

        decision = (
            await self.access.can_manage_store(
                actor,
                store_id,
            )
        )

        decision.raise_if_denied()

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        removed = await self.invoke_binding_method(
            method_names=(
                "remove_store_binding",
                "deactivate_store_binding",
                "unbind_user_from_store",
                "remove_user_from_store",
            ),
            user_id=target.id,
            store_id=store_id,
            removed_by_id=actor.id,
            deactivated_by_id=actor.id,
            removed_at=now,
            deactivated_at=now,
            reason=reason,
        )

        removed_bool = self.result_to_bool(
            removed
        )

        if removed_bool:
            await self.log_user_change(
                actor=actor,
                target=target,
                description=(
                    "Видалено прив’язку користувача до ТТ"
                ),
                reason=reason,
                old_values={
                    "store_id": store_id,
                    "binding_active": True,
                },
                new_values={
                    "store_id": store_id,
                    "binding_active": False,
                },
            )

        return removed_bool

    async def remove_bush_assignment(
        self,
        *,
        actor: User,
        user_id: int,
        bush_id: int,
        reason: str,
        removed_at: datetime | None = None,
    ) -> bool:
        """Видаляє або деактивує прив’язку до куща."""

        now = removed_at or datetime.now(UTC)

        decision = (
            await self.access.can_manage_bush(
                actor,
                bush_id,
            )
        )

        decision.raise_if_denied()

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        removed = await self.invoke_binding_method(
            method_names=(
                "remove_bush_binding",
                "deactivate_bush_binding",
                "unbind_user_from_bush",
                "remove_user_from_bush",
            ),
            user_id=target.id,
            bush_id=bush_id,
            removed_by_id=actor.id,
            deactivated_by_id=actor.id,
            removed_at=now,
            deactivated_at=now,
            reason=reason,
        )

        removed_bool = self.result_to_bool(
            removed
        )

        if removed_bool:
            await self.log_user_change(
                actor=actor,
                target=target,
                description=(
                    "Видалено прив’язку користувача до куща"
                ),
                reason=reason,
                old_values={
                    "bush_id": bush_id,
                    "binding_active": True,
                },
                new_values={
                    "bush_id": bush_id,
                    "binding_active": False,
                },
            )

        return removed_bool

    # ==========================================
    # ПЕРШИЙ ROOT_ADMIN
    # ==========================================

    async def bootstrap_root_admin(
        self,
        *,
        telegram_id: int,
        first_name: str = "ROOT",
        username: str | None = None,
        actor: User | None = None,
        create_if_missing: bool = True,
        completed_at: datetime | None = None,
    ) -> RootAdminBootstrapResult:
        """
        Створює або призначає першого ROOT_ADMIN.

        Якщо ROOT_ADMIN уже існує, операцію може
        виконати лише інший ROOT_ADMIN.
        """

        if telegram_id <= 0:
            raise ValueError(
                "Telegram ID повинен бути "
                "більшим за нуль."
            )

        now = completed_at or datetime.now(UTC)

        root_role = UserRole.ROOT_ADMIN

        root_statement = (
            select(User)
            .where(
                User.role == root_role
            )
            .limit(1)
        )

        existing_root = await self.session.scalar(
            root_statement
        )

        if existing_root is not None:
            if actor is None:
                raise AccessDeniedError(
                    "ROOT_ADMIN уже існує."
                )

            self.access.ensure_root_admin(actor)

        user_statement = (
            select(User)
            .where(
                User.telegram_id == telegram_id
            )
            .limit(1)
        )

        target = await self.session.scalar(
            user_statement
        )

        was_created = False

        if target is None:
            if not create_if_missing:
                raise ValueError(
                    "Користувача з таким Telegram ID "
                    "не знайдено."
                )

            target = self.create_minimal_user(
                telegram_id=telegram_id,
                first_name=first_name,
                username=username,
                created_at=now,
            )

            self.session.add(target)
            await self.session.flush()

            was_created = True

        previous_role = target.role
        previous_status = target.status

        active_status = self.resolve_user_status(
            "active",
            "enabled",
        )

        role_changed = (
            target.role != root_role
        )

        status_changed = (
            target.status != active_status
        )

        target.role = root_role
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

        await self.log_user_change(
            actor=actor,
            target=target,
            description=(
                "Призначено ROOT_ADMIN"
            ),
            reason=(
                "Початкова конфігурація системи"
            ),
            old_values={
                "role": previous_role.value,
                "status": previous_status.value,
            },
            new_values={
                "role": root_role.value,
                "status": active_status.value,
            },
            source="bootstrap",
        )

        return RootAdminBootstrapResult(
            user=target,
            was_created=was_created,
            role_changed=role_changed,
            status_changed=status_changed,
            telegram_id=telegram_id,
            completed_at=now,
        )

    # ==========================================
    # СТВОРЕННЯ ПРИВ’ЯЗОК
    # ==========================================

    async def create_store_binding(
        self,
        *,
        actor: User,
        user: User,
        store_id: int,
        assigned_at: datetime,
    ) -> bool:
        """Створює активну прив’язку до ТТ."""

        result = await self.invoke_binding_method(
            method_names=(
                "bind_user_to_store",
                "create_store_binding",
                "upsert_store_binding",
                "assign_store",
                "add_user_to_store",
            ),
            user_id=user.id,
            store_id=store_id,
            created_by_id=actor.id,
            assigned_by_id=actor.id,
            created_at=assigned_at,
            assigned_at=assigned_at,
            is_active=True,
        )

        return self.result_to_bool(
            result,
            default=True,
        )

    async def create_bush_binding(
        self,
        *,
        actor: User,
        user: User,
        bush_id: int,
        assigned_at: datetime,
    ) -> bool:
        """Створює активну прив’язку до куща."""

        result = await self.invoke_binding_method(
            method_names=(
                "bind_user_to_bush",
                "create_bush_binding",
                "upsert_bush_binding",
                "assign_bush",
                "add_user_to_bush",
            ),
            user_id=user.id,
            bush_id=bush_id,
            created_by_id=actor.id,
            assigned_by_id=actor.id,
            created_at=assigned_at,
            assigned_at=assigned_at,
            is_active=True,
        )

        return self.result_to_bool(
            result,
            default=True,
        )

    # ==========================================
    # ПРАВА ДОСТУПУ
    # ==========================================

    async def ensure_can_assign_role(
        self,
        *,
        actor: User,
        target: User,
        role: UserRole,
        store_id: int | None,
        bush_id: int | None,
        allow_missing_scope: bool = False,
    ) -> None:
        """Перевіряє право призначення ролі."""

        self.access.ensure_active_user(actor)

        if role == UserRole.ROOT_ADMIN:
            self.access.ensure_root_admin(actor)
            return

        if role == UserRole.DIRECTOR:
            self.access.ensure_root_admin(actor)
            return

        if role in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            if bush_id is None:
                if allow_missing_scope:
                    self.access.require_network_management(
                        actor
                    )
                    return

                raise ValueError(
                    "Для цієї ролі потрібно вказати кущ."
                )

            decision = (
                await self.access.can_manage_bush(
                    actor,
                    bush_id,
                )
            )

            decision.raise_if_denied()
            return

        if role == UserRole.STORE_USER:
            if store_id is None:
                if allow_missing_scope:
                    await self.ensure_can_manage_target(
                        actor=actor,
                        target=target,
                    )
                    return

                raise ValueError(
                    "Для працівника потрібно вказати ТТ."
                )

            decision = (
                await self.access.can_manage_store(
                    actor,
                    store_id,
                )
            )

            decision.raise_if_denied()
            return

        raise AccessDeniedError(
            "Призначення цієї ролі не підтримується."
        )

    async def ensure_can_manage_target(
        self,
        *,
        actor: User,
        target: User,
        store_id: int | None = None,
        bush_id: int | None = None,
    ) -> None:
        """Перевіряє право керування користувачем."""

        self.access.ensure_active_user(actor)

        if actor.role == UserRole.ROOT_ADMIN:
            return

        if target.role == UserRole.ROOT_ADMIN:
            raise AccessDeniedError(
                "Керувати ROOT_ADMIN може лише ROOT_ADMIN."
            )

        if target.role == UserRole.DIRECTOR:
            raise AccessDeniedError(
                "Керувати директором може лише ROOT_ADMIN."
            )

        if actor.role == UserRole.DIRECTOR:
            return

        resolved_store_id = (
            store_id
            or self.get_int_attribute(
                target,
                "requested_store_id",
                "pending_store_id",
                "store_id",
            )
        )

        resolved_bush_id = (
            bush_id
            or self.get_int_attribute(
                target,
                "requested_bush_id",
                "pending_bush_id",
                "bush_id",
            )
        )

        if resolved_store_id is not None:
            decision = (
                await self.access.can_manage_store(
                    actor,
                    resolved_store_id,
                )
            )

            decision.raise_if_denied()
            return

        if resolved_bush_id is not None:
            decision = (
                await self.access.can_manage_bush(
                    actor,
                    resolved_bush_id,
                )
            )

            decision.raise_if_denied()
            return

        raise AccessDeniedError(
            "Недостатньо прав для керування "
            "цим користувачем."
        )

    # ==========================================
    # СПОВІЩЕННЯ
    # ==========================================

    async def queue_user_notification(
        self,
        *,
        user: User,
        notification_names: tuple[str, ...],
        message_text: str,
        suffix: str,
        scheduled_for: datetime,
    ) -> bool:
        """Додає персональне повідомлення у чергу."""

        telegram_id = getattr(
            user,
            "telegram_id",
            None,
        )

        if telegram_id is None:
            return False

        notification_type = (
            self.resolve_enum_member(
                NotificationType,
                *notification_names,
                default=None,
            )
        )

        if notification_type is None:
            return False

        _, was_created = (
            await self.repositories.notifications
            .get_or_create_from_parts(
                notification_type=(
                    notification_type
                ),
                recipient_user_id=user.id,
                chat_id=int(telegram_id),
                suffix=suffix,
                scheduled_for=scheduled_for,
                message_text=message_text,
                payload_json={
                    "send_method": "message",
                    "text": message_text,
                    "parse_mode": "HTML",
                },
            )
        )

        return was_created

    # ==========================================
    # AUDIT LOG
    # ==========================================

    async def log_user_change(
        self,
        *,
        actor: User | None,
        target: User,
        description: str,
        reason: str | None,
        old_values: dict[str, Any],
        new_values: dict[str, Any],
        source: str = "telegram_bot",
    ) -> None:
        """Фіксує зміну користувача."""

        action = self.resolve_audit_action(
            "update",
            "changed",
            "edit",
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
                actor_user_id=(
                    actor.id
                    if actor is not None
                    else None
                ),
                reason=reason,
                description=description,
                source=source,
            ),
            old_values=old_values,
            new_values=new_values,
        )

    # ==========================================
    # ОТРИМАННЯ КОРИСТУВАЧА
    # ==========================================

    async def get_user_or_raise(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> User:
        """Повертає користувача за ID."""

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
            statement = statement.with_for_update()

        user = await self.session.scalar(
            statement
        )

        if user is None:
            raise ValueError(
                "Користувача не знайдено."
            )

        return user

    # ==========================================
    # АДАПТЕР BINDING REPOSITORY
    # ==========================================

    async def invoke_binding_method(
        self,
        *,
        method_names: tuple[str, ...],
        **kwargs: Any,
    ) -> Any:
        """Викликає доступний метод BindingRepository."""

        repository = self.repositories.bindings

        for method_name in method_names:
            method = getattr(
                repository,
                method_name,
                None,
            )

            if method is None or not callable(method):
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

            accepted_kwargs = (
                dict(kwargs)
                if accepts_kwargs
                else {
                    key: value
                    for key, value in kwargs.items()
                    if key in signature.parameters
                }
            )

            result = method(
                **accepted_kwargs
            )

            if inspect.isawaitable(result):
                return await result

            return result

        raise AttributeError(
            "BindingRepository не містить "
            "очікуваного методу: "
            + ", ".join(method_names)
        )

    # ==========================================
    # ЗНІМОК КОРИСТУВАЧА
    # ==========================================

    @staticmethod
    def user_snapshot(
        user: User,
    ) -> dict[str, Any]:
        """Формує знімок користувача."""

        role = getattr(
            user,
            "role",
            None,
        )

        status = getattr(
            user,
            "status",
            None,
        )

        return {
            "id": user.id,
            "telegram_id": getattr(
                user,
                "telegram_id",
                None,
            ),
            "role": (
                role.value
                if isinstance(role, Enum)
                else role
            ),
            "status": (
                status.value
                if isinstance(status, Enum)
                else status
            ),
            "is_blocked": bool(
                getattr(
                    user,
                    "is_blocked",
                    False,
                )
            ),
            "requested_store_id": (
                AuthService.get_int_attribute(
                    user,
                    "requested_store_id",
                    "pending_store_id",
                )
            ),
            "requested_bush_id": (
                AuthService.get_int_attribute(
                    user,
                    "requested_bush_id",
                    "pending_bush_id",
                )
            ),
        }

    # ==========================================
    # СТВОРЕННЯ ROOT-КОРИСТУВАЧА
    # ==========================================

    def create_minimal_user(
        self,
        *,
        telegram_id: int,
        first_name: str,
        username: str | None,
        created_at: datetime,
    ) -> User:
        """Створює мінімальний запис користувача."""

        columns = {
            column.key
            for column in User.__mapper__.columns
        }

        active_status = self.resolve_user_status(
            "active",
            "enabled",
        )

        payload = {
            "telegram_id": telegram_id,
            "first_name": first_name,
            "telegram_username": username,
            "username": username,
            "role": UserRole.ROOT_ADMIN,
            "status": active_status,
            "is_blocked": False,
            "created_at": created_at,
            "updated_at": created_at,
        }

        return User(
            **{
                key: value
                for key, value in payload.items()
                if (
                    key in columns
                    and value is not None
                )
            }
        )

    # ==========================================
    # ТЕКСТИ
    # ==========================================

    @classmethod
    def build_approval_message(
        cls,
        *,
        role: UserRole,
        store_id: int | None,
        bush_id: int | None,
    ) -> str:
        """Формує повідомлення про підтвердження."""

        lines = [
            "✅ <b>Ваш акаунт підтверджено!</b>",
            "",
            (
                "Роль: "
                f"<b>{escape(cls.role_text(role))}</b>"
            ),
        ]

        if store_id is not None:
            lines.append(
                f"🏪 Торгова точка: <b>#{store_id}</b>"
            )

        if bush_id is not None:
            lines.append(
                f"🌿 Кущ: <b>#{bush_id}</b>"
            )

        lines.extend(
            [
                "",
                "Тепер вам доступне головне меню бота.",
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def role_text(
        role: UserRole,
    ) -> str:
        """Повертає назву ролі."""

        translations = {
            UserRole.ROOT_ADMIN: "ROOT_ADMIN",
            UserRole.DIRECTOR: "директор",
            UserRole.BUSH_ADMIN: (
                "адміністратор куща"
            ),
            UserRole.LION: "лев",
            UserRole.STORE_USER: (
                "працівник торгової точки"
            ),
        }

        return translations.get(
            role,
            str(role.value),
        )

    # ==========================================
    # ВАЛІДАЦІЯ ОБЛАСТІ РОЛІ
    # ==========================================

    @staticmethod
    def validate_role_scope(
        *,
        role: UserRole,
        store_id: int | None,
        bush_id: int | None,
    ) -> None:
        """Перевіряє роль і прив’язку."""

        if (
            store_id is not None
            and bush_id is not None
        ):
            raise ValueError(
                "Не можна одночасно прив’язувати "
                "користувача до ТТ і куща."
            )

        if (
            role == UserRole.STORE_USER
            and store_id is None
        ):
            raise ValueError(
                "Для працівника потрібно вибрати ТТ."
            )

        if (
            role
            in {
                UserRole.BUSH_ADMIN,
                UserRole.LION,
            }
            and bush_id is None
        ):
            raise ValueError(
                "Для адміністратора або лева "
                "потрібно вибрати кущ."
            )

        if (
            role
            in {
                UserRole.ROOT_ADMIN,
                UserRole.DIRECTOR,
            }
            and (
                store_id is not None
                or bush_id is not None
            )
        ):
            raise ValueError(
                "ROOT_ADMIN і DIRECTOR не потребують "
                "прив’язки до ТТ або куща."
            )

    # ==========================================
    # ENUM
    # ==========================================

    @classmethod
    def resolve_user_status(
        cls,
        *names: str,
        default: UserStatus | None = None,
    ) -> UserStatus:
        """Знаходить статус користувача."""

        result = cls.resolve_enum_member(
            UserStatus,
            *names,
            default=default,
        )

        if result is None:
            raise ValueError(
                "У UserStatus відсутнє потрібне "
                f"значення: {', '.join(names)}."
            )

        return result

    @classmethod
    def resolve_audit_action(
        cls,
        *names: str,
    ) -> AuditAction:
        """Знаходить AuditAction."""

        result = cls.resolve_enum_member(
            AuditAction,
            *names,
            default=None,
        )

        if result is not None:
            return result

        return cls.resolve_enum_member(
            AuditAction,
            "update",
            "changed",
        )

    @classmethod
    def resolve_entity_type(
        cls,
        *names: str,
    ) -> EntityType:
        """Знаходить EntityType."""

        result = cls.resolve_enum_member(
            EntityType,
            *names,
            default=None,
        )

        if result is None:
            raise ValueError(
                "У EntityType відсутнє значення user."
            )

        return result

    @staticmethod
    def resolve_enum_member(
        enum_class: type[EnumType],
        *names: str,
        default: EnumType | None = None,
    ) -> EnumType | None:
        """Шукає enum за назвою або значенням."""

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

    @staticmethod
    def status_matches(
        status: UserStatus,
        *names: str,
    ) -> bool:
        """Перевіряє статус за псевдонімами."""

        values = {
            status.name.lower(),
            str(status.value).lower(),
        }

        return bool(
            values.intersection(
                {
                    name.lower()
                    for name in names
                }
            )
        )

    # ==========================================
    # АТРИБУТИ
    # ==========================================

    @staticmethod
    def set_existing_attribute(
        target: Any,
        value: Any,
        *names: str,
    ) -> bool:
        """Записує перший наявний атрибут."""

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
        """Повертає перший цілий атрибут."""

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

            except (TypeError, ValueError):
                continue

        return None

    @staticmethod
    def get_text_attribute(
        target: Any,
        *names: str,
    ) -> str | None:
        """Повертає перший текстовий атрибут."""

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

    @classmethod
    def get_user_role_attribute(
        cls,
        target: Any,
        *names: str,
    ) -> UserRole | None:
        """Повертає роль з атрибута."""

        for name in names:
            value = getattr(
                target,
                name,
                None,
            )

            if isinstance(value, UserRole):
                return value

            if isinstance(value, str):
                result = cls.resolve_enum_member(
                    UserRole,
                    value,
                    default=None,
                )

                if result is not None:
                    return result

        return None

    @staticmethod
    def clear_pending_fields(
        user: User,
    ) -> None:
        """Очищає поля очікуваної прив’язки."""

        for field_name in (
            "requested_role",
            "pending_role",
            "requested_store_id",
            "pending_store_id",
            "requested_bush_id",
            "pending_bush_id",
        ):
            if hasattr(user, field_name):
                setattr(
                    user,
                    field_name,
                    None,
                )

    # ==========================================
    # РЕЗУЛЬТАТИ РЕПОЗИТОРІЮ
    # ==========================================

    @staticmethod
    def result_to_bool(
        result: Any,
        *,
        default: bool = False,
    ) -> bool:
        """Перетворює результат репозиторію у bool."""

        if result is None:
            return default

        if isinstance(result, bool):
            return result

        if isinstance(result, int):
            return result > 0

        for name in (
            "was_created",
            "created",
            "was_changed",
            "changed",
            "success",
            "removed",
            "was_removed",
        ):
            value = getattr(
                result,
                name,
                None,
            )

            if value is not None:
                return bool(value)

        return True

    # ==========================================
    # ВАЛІДАЦІЯ
    # ==========================================

    @staticmethod
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        """Перевіряє наявність часового поясу."""

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{field_name} повинен містити "
                "часовий пояс."
            )

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
    ) -> str:
        """Нормалізує обов’язковий текст."""

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