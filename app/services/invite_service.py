from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum, StrEnum
from typing import Any, TypeVar
from urllib.parse import quote

from app.database.models.enums import (
    AuditAction,
    EntityType,
    UserRole,
)
from app.database.models.user import User
from app.repositories import (
    AuditContext,
    CreatedInvite,
    InviteActivationResult,
    Repositories,
)
from app.services.access import AccessService


EnumType = TypeVar(
    "EnumType",
    bound=Enum,
)


class InviteScope(StrEnum):
    """
    Область дії запрошення.
    """

    STORE = "store"
    BUSH = "bush"
    NETWORK = "network"


@dataclass(slots=True, frozen=True)
class InviteCreationServiceResult:
    """
    Результат створення запрошення.
    """

    created_invite: CreatedInvite

    token: str
    deep_link: str

    target_role: UserRole
    scope: InviteScope

    store_id: int | None
    bush_id: int | None

    expires_at: datetime | None
    max_uses: int

    @property
    def invite(self) -> Any:
        """
        Повертає модель запрошення,
        якщо вона міститься у CreatedInvite.
        """

        return InviteService.extract_invite_object(
            self.created_invite
        )

    @property
    def success(self) -> bool:
        """
        Compatibility flag для handlers.
        """

        return True

    @property
    def created(self) -> bool:
        """
        Compatibility alias.
        """

        return True


@dataclass(slots=True, frozen=True)
class InviteActivationServiceResult:
    """
    Результат активації запрошення.
    """

    activation: InviteActivationResult

    token: str
    user: User

    target_role: UserRole | None

    store_id: int | None
    bush_id: int | None

    requires_approval: bool
    was_activated: bool

    message: str

    @property
    def success(self) -> bool:
        """
        Compatibility flag для handlers.
        """

        return self.was_activated

    @property
    def activated(self) -> bool:
        """
        Compatibility alias.
        """

        return self.was_activated


@dataclass(slots=True, frozen=True)
class InviteRevocationResult:
    """
    Результат відкликання запрошення.
    """

    invite_id: int
    was_revoked: bool

    revoked_at: datetime
    revoked_by_id: int

    reason: str

    @property
    def success(self) -> bool:
        """
        Compatibility flag для handlers.
        """

        return self.was_revoked

    @property
    def revoked(self) -> bool:
        """
        Compatibility alias.
        """

        return self.was_revoked


@dataclass(slots=True, frozen=True)
class InvitePayload:
    """
    Розібраний Telegram start payload.
    """

    raw_payload: str
    token: str


class InviteService:
    """
    Сервіс Telegram-запрошень.

    Підтримує:

    - запрошення працівника до ТТ;
    - запрошення адміністратора куща;
    - запрошення лева;
    - запрошення директора;
    - Telegram deep-link;
    - одноразові та багаторазові посилання;
    - строк дії запрошення;
    - активацію ролі;
    - прив’язку до ТТ або куща;
    - відкликання посилання;
    - AuditLog.

    Приклад посилання:

    https://t.me/bot_username?start=invite_AbCd123
    """

    START_PREFIX = "invite_"

    TOKEN_PATTERN = re.compile(
        r"^[A-Za-z0-9_-]{8,256}$"
    )

    def __init__(
        self,
        repositories: Repositories,
        *,
        bot_username: str,
        access_service: AccessService | None = None,
    ) -> None:
        self.repositories = repositories
        self.session = repositories.session

        self.access = (
            access_service
            or AccessService(repositories)
        )

        self.bot_username = (
            self.normalize_bot_username(
                bot_username
            )
        )

    # ==========================================
    # ЗАПРОШЕННЯ ДО ТОРГОВОЇ ТОЧКИ
    # ==========================================

    async def create_store_invite(
        self,
        *,
        actor: User,
        store_id: int,
        expires_in: timedelta | None = None,
        expires_at: datetime | None = None,
        max_uses: int = 1,
        note: str | None = None,
        created_at: datetime | None = None,
    ) -> InviteCreationServiceResult:
        """
        Створює запрошення працівника ТТ.

        Після активації користувач отримує роль
        STORE_USER і прив’язку до конкретної ТТ.
        """

        decision = (
            await self.access
            .can_create_store_invite(
                actor,
                store_id,
            )
        )

        decision.raise_if_denied()

        store = await self.access.get_store_or_raise(
            store_id
        )

        now = created_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="created_at",
        )

        resolved_expires_at = (
            self.resolve_expiration(
                current_time=now,
                expires_in=expires_in,
                expires_at=expires_at,
            )
        )

        self.validate_max_uses(max_uses)

        created_invite = (
            await self.invoke_repository(
                method_names=(
                    "create_store_invite",
                    "create_for_store",
                    "create_invite",
                    "create",
                ),
                created_by_id=actor.id,
                actor_user_id=actor.id,
                target_role=UserRole.STORE_USER,
                role=UserRole.STORE_USER,
                store_id=store.id,
                bush_id=store.bush_id,
                expires_at=resolved_expires_at,
                max_uses=max_uses,
                note=self.normalize_optional_text(
                    note
                ),
                created_at=now,
            )
        )

        result = self.build_creation_result(
            created_invite=created_invite,
            target_role=UserRole.STORE_USER,
            scope=InviteScope.STORE,
            store_id=store.id,
            bush_id=store.bush_id,
            expires_at=resolved_expires_at,
            max_uses=max_uses,
        )

        await self.log_invite_creation(
            actor=actor,
            result=result,
            description=(
                "Створено запрошення "
                f"працівника для ТТ {store.code}"
            ),
        )

        return result

    # ==========================================
    # ЗАПРОШЕННЯ ДО КУЩА
    # ==========================================

    async def create_bush_invite(
        self,
        *,
        actor: User,
        bush_id: int,
        target_role: UserRole,
        expires_in: timedelta | None = None,
        expires_at: datetime | None = None,
        max_uses: int = 1,
        note: str | None = None,
        created_at: datetime | None = None,
    ) -> InviteCreationServiceResult:
        """
        Створює запрошення адміністратора
        або лева до конкретного куща.
        """

        if target_role not in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            raise ValueError(
                "Для куща можна створити запрошення "
                "лише адміністратора або лева."
            )

        decision = (
            await self.access
            .can_create_bush_invite(
                actor,
                bush_id=bush_id,
                target_role=target_role,
            )
        )

        decision.raise_if_denied()

        bush = await self.access.get_bush_or_raise(
            bush_id
        )

        now = created_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="created_at",
        )

        resolved_expires_at = (
            self.resolve_expiration(
                current_time=now,
                expires_in=expires_in,
                expires_at=expires_at,
            )
        )

        self.validate_max_uses(max_uses)

        created_invite = (
            await self.invoke_repository(
                method_names=(
                    "create_bush_invite",
                    "create_for_bush",
                    "create_invite",
                    "create",
                ),
                created_by_id=actor.id,
                actor_user_id=actor.id,
                target_role=target_role,
                role=target_role,
                bush_id=bush.id,
                store_id=None,
                expires_at=resolved_expires_at,
                max_uses=max_uses,
                note=self.normalize_optional_text(
                    note
                ),
                created_at=now,
            )
        )

        result = self.build_creation_result(
            created_invite=created_invite,
            target_role=target_role,
            scope=InviteScope.BUSH,
            store_id=None,
            bush_id=bush.id,
            expires_at=resolved_expires_at,
            max_uses=max_uses,
        )

        await self.log_invite_creation(
            actor=actor,
            result=result,
            description=(
                "Створено запрошення "
                f"{self.role_text(target_role)} "
                f"до куща {bush.name}"
            ),
        )

        return result

    # ==========================================
    # ЗАПРОШЕННЯ ДИРЕКТОРА
    # ==========================================

    async def create_director_invite(
        self,
        *,
        actor: User,
        expires_in: timedelta | None = None,
        expires_at: datetime | None = None,
        max_uses: int = 1,
        note: str | None = None,
        created_at: datetime | None = None,
    ) -> InviteCreationServiceResult:
        """
        Створює запрошення директора.

        Доступне лише ROOT_ADMIN.
        """

        decision = (
            self.access
            .can_create_director_invite(actor)
        )

        decision.raise_if_denied()

        now = created_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="created_at",
        )

        resolved_expires_at = (
            self.resolve_expiration(
                current_time=now,
                expires_in=expires_in,
                expires_at=expires_at,
            )
        )

        self.validate_max_uses(max_uses)

        created_invite = (
            await self.invoke_repository(
                method_names=(
                    "create_director_invite",
                    "create_network_invite",
                    "create_invite",
                    "create",
                ),
                created_by_id=actor.id,
                actor_user_id=actor.id,
                target_role=UserRole.DIRECTOR,
                role=UserRole.DIRECTOR,
                store_id=None,
                bush_id=None,
                expires_at=resolved_expires_at,
                max_uses=max_uses,
                note=self.normalize_optional_text(
                    note
                ),
                created_at=now,
            )
        )

        result = self.build_creation_result(
            created_invite=created_invite,
            target_role=UserRole.DIRECTOR,
            scope=InviteScope.NETWORK,
            store_id=None,
            bush_id=None,
            expires_at=resolved_expires_at,
            max_uses=max_uses,
        )

        await self.log_invite_creation(
            actor=actor,
            result=result,
            description=(
                "Створено запрошення директора"
            ),
        )

        return result

    # ==========================================
    # УНІВЕРСАЛЬНИЙ CREATE ADAPTER
    # ==========================================

    async def create_invite(
        self,
        *,
        actor: User,
        invite_type: str | None = None,
        scope: str | None = None,
        invite_scope: str | None = None,
        target_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        role: UserRole | str | None = None,
        target_role: UserRole | str | None = None,
        user_role: UserRole | str | None = None,
        expires_in: timedelta | None = None,
        expires_at: datetime | None = None,
        expiration: timedelta | None = None,
        max_uses: int | None = None,
        single_use: bool | None = None,
        is_single_use: bool | None = None,
        note: str | None = None,
        created_at: datetime | None = None,
        **_: Any,
    ) -> InviteCreationServiceResult:
        """
        Compatibility adapter для handlers/invites.py.
        """

        resolved_type = (
            invite_type
            or scope
            or invite_scope
            or ""
        ).strip().lower()

        if resolved_type == "network":
            resolved_type = "director"

        resolved_expires_in = (
            expiration
            if expiration is not None
            else expires_in
        )

        if expires_at is not None:
            resolved_expires_in = None

        resolved_single_use = (
            single_use
            if single_use is not None
            else is_single_use
        )

        if max_uses is None:
            max_uses = (
                1
                if resolved_single_use is not False
                else 1000
            )

        if resolved_type == "store":
            resolved_store_id = (
                store_id
                or target_id
            )

            if not resolved_store_id:
                raise ValueError(
                    "Для invite ТТ не вказано store_id."
                )

            return await self.create_store_invite(
                actor=actor,
                store_id=int(resolved_store_id),
                expires_in=resolved_expires_in,
                expires_at=expires_at,
                max_uses=max_uses,
                note=note,
                created_at=created_at,
            )

        if resolved_type == "bush":
            resolved_bush_id = (
                bush_id
                or target_id
            )

            if not resolved_bush_id:
                raise ValueError(
                    "Для invite куща не вказано bush_id."
                )

            resolved_role = self.resolve_user_role(
                target_role
                or role
                or user_role
                or UserRole.LION
            )

            if resolved_role not in {
                UserRole.BUSH_ADMIN,
                UserRole.LION,
            }:
                raise ValueError(
                    "Invite куща підтримує лише "
                    "BUSH_ADMIN або LION."
                )

            return await self.create_bush_invite(
                actor=actor,
                bush_id=int(resolved_bush_id),
                target_role=resolved_role,
                expires_in=resolved_expires_in,
                expires_at=expires_at,
                max_uses=max_uses,
                note=note,
                created_at=created_at,
            )

        resolved_role = self.resolve_user_role(
            target_role
            or role
            or user_role
            or (
                UserRole.DIRECTOR
                if resolved_type == "director"
                else None
            )
        )

        if (
            resolved_type == "director"
            or resolved_role == UserRole.DIRECTOR
        ):
            return await self.create_director_invite(
                actor=actor,
                expires_in=resolved_expires_in,
                expires_at=expires_at,
                max_uses=max_uses,
                note=note,
                created_at=created_at,
            )

        raise ValueError(
            "Невідомий тип invite: "
            f"{resolved_type or 'не вказано'}."
        )

    # ==========================================
    # АКТИВАЦІЯ ЗАПРОШЕННЯ
    # ==========================================

    async def activate_invite(
        self,
        *,
        user: User,
        token_or_payload: str,
        activated_at: datetime | None = None,
        telegram_username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
    ) -> InviteActivationServiceResult:
        """
        Активує запрошення після /start.
        """

        payload = self.parse_start_payload(
            token_or_payload
        )

        now = activated_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="activated_at",
        )

        activation = (
            await self.invoke_repository(
                method_names=(
                    "activate_invite",
                    "activate",
                    "consume_invite",
                    "consume",
                ),
                token=payload.token,
                raw_token=payload.token,
                user_id=user.id,
                telegram_id=user.telegram_id,
                telegram_username=(
                    self.normalize_optional_text(
                        telegram_username
                    )
                ),
                username=(
                    self.normalize_optional_text(
                        telegram_username
                    )
                ),
                first_name=(
                    self.normalize_optional_text(
                        first_name
                    )
                ),
                last_name=(
                    self.normalize_optional_text(
                        last_name
                    )
                ),
                activated_at=now,
                used_at=now,
            )
        )

        target_role = self.extract_role(
            activation
        )

        store_id = self.extract_int_attribute(
            activation,
            "store_id",
            "target_store_id",
        )

        bush_id = self.extract_int_attribute(
            activation,
            "bush_id",
            "target_bush_id",
        )

        requires_approval = bool(
            self.extract_attribute(
                activation,
                "requires_approval",
                "approval_required",
                default=False,
            )
        )

        was_activated = bool(
            self.extract_attribute(
                activation,
                "was_activated",
                "activated",
                "success",
                default=True,
            )
        )

        message = self.build_activation_message(
            target_role=target_role,
            store_id=store_id,
            bush_id=bush_id,
            requires_approval=requires_approval,
            was_activated=was_activated,
        )

        result = InviteActivationServiceResult(
            activation=activation,
            token=payload.token,
            user=user,
            target_role=target_role,
            store_id=store_id,
            bush_id=bush_id,
            requires_approval=requires_approval,
            was_activated=was_activated,
            message=message,
        )

        await self.log_invite_activation(
            user=user,
            result=result,
            activated_at=now,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=(
                telegram_message_id
            ),
        )

        return result

    # ==========================================
    # ПЕРЕВІРКА ЗАПРОШЕННЯ
    # ==========================================

    async def inspect_invite(
        self,
        *,
        token_or_payload: str,
        current_time: datetime | None = None,
    ) -> Any:
        """
        Перевіряє запрошення без активації.
        """

        payload = self.parse_start_payload(
            token_or_payload
        )

        now = current_time or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="current_time",
        )

        return await self.invoke_repository(
            method_names=(
                "validate_invite",
                "inspect_invite",
                "get_active_by_token",
                "get_by_token",
            ),
            token=payload.token,
            raw_token=payload.token,
            current_time=now,
            checked_at=now,
        )

    # ==========================================
    # ВІДКЛИКАННЯ
    # ==========================================

    async def revoke_invite(
        self,
        *,
        actor: User,
        invite_id: int,
        reason: str = "Відкликано через Telegram",
        revoked_at: datetime | None = None,
    ) -> InviteRevocationResult:
        """
        Відкликає активне запрошення.
        """

        if invite_id <= 0:
            raise ValueError(
                "ID запрошення повинен бути "
                "більшим за нуль."
            )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        now = revoked_at or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="revoked_at",
        )

        invite = await self.invoke_repository(
            method_names=(
                "get_by_id_or_raise",
                "get_invite_by_id_or_raise",
                "get_by_id",
            ),
            invite_id=invite_id,
            entity_id=invite_id,
            for_update=True,
        )

        await self.ensure_can_manage_invite(
            actor=actor,
            invite=invite,
        )

        revoked = await self.invoke_repository(
            method_names=(
                "revoke_invite",
                "revoke",
                "deactivate",
            ),
            invite_id=invite_id,
            entity_id=invite_id,
            revoked_by_id=actor.id,
            actor_user_id=actor.id,
            revoked_at=now,
            reason=normalized_reason,
        )

        was_revoked = bool(
            self.extract_attribute(
                revoked,
                "was_revoked",
                "revoked",
                "success",
                default=True,
            )
        )

        if was_revoked:
            await self.log_invite_revocation(
                actor=actor,
                invite=invite,
                invite_id=invite_id,
                reason=normalized_reason,
                revoked_at=now,
            )

        return InviteRevocationResult(
            invite_id=invite_id,
            was_revoked=was_revoked,
            revoked_at=now,
            revoked_by_id=actor.id,
            reason=normalized_reason,
        )

    async def ensure_can_manage_invite(
        self,
        *,
        actor: User,
        invite: Any,
    ) -> None:
        store_id = self.extract_int_attribute(
            invite,
            "store_id",
            "target_store_id",
        )

        bush_id = self.extract_int_attribute(
            invite,
            "bush_id",
            "target_bush_id",
        )

        target_role = self.extract_role(invite)

        if store_id is not None:
            decision = (
                await self.access
                .can_manage_store(
                    actor,
                    store_id,
                )
            )

            decision.raise_if_denied()
            return

        if bush_id is not None:
            decision = (
                await self.access
                .can_manage_bush(
                    actor,
                    bush_id,
                )
            )

            decision.raise_if_denied()
            return

        if target_role == UserRole.DIRECTOR:
            decision = (
                self.access
                .can_create_director_invite(
                    actor
                )
            )

            decision.raise_if_denied()
            return

        self.access.require_network_management(
            actor
        )

    # ==========================================
    # СПИСКИ ЗАПРОШЕНЬ
    # ==========================================

    async def get_store_invites(
        self,
        *,
        user: User,
        store_id: int,
        active_only: bool = False,
        limit: int = 100,
    ) -> list[Any]:
        await self.access.require_store_view(
            user,
            store_id,
        )

        result = await self.invoke_repository(
            method_names=(
                "get_store_invites",
                "list_for_store",
                "get_for_store",
            ),
            store_id=store_id,
            active_only=active_only,
            limit=limit,
        )

        return list(result or [])

    async def get_bush_invites(
        self,
        *,
        user: User,
        bush_id: int,
        active_only: bool = False,
        limit: int = 100,
    ) -> list[Any]:
        await self.access.require_bush_view(
            user,
            bush_id,
        )

        result = await self.invoke_repository(
            method_names=(
                "get_bush_invites",
                "list_for_bush",
                "get_for_bush",
            ),
            bush_id=bush_id,
            active_only=active_only,
            limit=limit,
        )

        return list(result or [])

    async def get_created_invites(
        self,
        *,
        user: User,
        active_only: bool = False,
        limit: int = 100,
    ) -> list[Any]:
        result = await self.invoke_repository(
            method_names=(
                "get_created_by_user",
                "list_created_by",
                "get_by_creator",
            ),
            user_id=user.id,
            created_by_id=user.id,
            active_only=active_only,
            limit=limit,
        )

        return list(result or [])

    async def list_invites(
        self,
        *,
        actor: User | None = None,
        user: User | None = None,
        active_only: bool = False,
        include_expired: bool = True,
        include_revoked: bool = True,
        limit: int = 100,
        **_: Any,
    ) -> list[Any]:
        """
        Compatibility adapter для handlers.
        """

        resolved_user = (
            actor
            or user
        )

        if resolved_user is None:
            raise ValueError(
                "Не вказано користувача."
            )

        return await self.get_created_invites(
            user=resolved_user,
            active_only=active_only,
            limit=limit,
        )

    async def get_invite(
        self,
        *,
        actor: User | None = None,
        user: User | None = None,
        invite_id: int | None = None,
        id: int | None = None,
        **_: Any,
    ) -> Any | None:
        """
        Compatibility adapter для картки invite.
        """

        resolved_user = (
            actor
            or user
        )

        if resolved_user is None:
            raise ValueError(
                "Не вказано користувача."
            )

        resolved_id = (
            invite_id
            if invite_id is not None
            else id
        )

        if resolved_id is None or resolved_id <= 0:
            raise ValueError(
                "Некоректний ID invite."
            )

        invite = await self.invoke_repository(
            method_names=(
                "get_by_id",
                "get_invite_by_id",
                "find_by_id",
            ),
            invite_id=resolved_id,
            entity_id=resolved_id,
        )

        if invite is None:
            return None

        await self.ensure_can_manage_invite(
            actor=resolved_user,
            invite=invite,
        )

        return invite

    # ==========================================
    # ОЧИЩЕННЯ ПРОСТРОЧЕНИХ
    # ==========================================

    async def expire_outdated_invites(
        self,
        *,
        current_time: datetime | None = None,
        limit: int = 1000,
    ) -> int:
        now = current_time or datetime.now(UTC)

        self.validate_aware_datetime(
            now,
            field_name="current_time",
        )

        result = await self.invoke_repository(
            method_names=(
                "expire_outdated",
                "expire_invites",
                "mark_expired",
                "cleanup_expired",
            ),
            current_time=now,
            expired_at=now,
            limit=limit,
        )

        if isinstance(result, int):
            return result

        if result is None:
            return 0

        try:
            return len(result)

        except TypeError:
            return int(
                self.extract_attribute(
                    result,
                    "count",
                    "expired_count",
                    default=0,
                )
            )

    # ==========================================
    # TELEGRAM DEEP-LINK
    # ==========================================

    def build_deep_link(
        self,
        token: str,
    ) -> str:
        normalized_token = self.normalize_token(
            token
        )

        payload = (
            f"{self.START_PREFIX}"
            f"{normalized_token}"
        )

        return (
            f"https://t.me/{self.bot_username}"
            f"?start={quote(payload)}"
        )

    def parse_start_payload(
        self,
        payload_or_token: str,
    ) -> InvitePayload:
        normalized_value = (
            self.normalize_required_text(
                payload_or_token,
                field_name=(
                    "Токен або Telegram payload"
                ),
            )
        )

        if "start=" in normalized_value:
            normalized_value = (
                normalized_value
                .split("start=", maxsplit=1)[1]
                .split("&", maxsplit=1)[0]
            )

        for prefix in (
            self.START_PREFIX,
            "inv_",
            "invite-",
        ):
            if normalized_value.startswith(prefix):
                normalized_value = (
                    normalized_value[
                        len(prefix):
                    ]
                )

                break

        token = self.normalize_token(
            normalized_value
        )

        return InvitePayload(
            raw_payload=payload_or_token,
            token=token,
        )

    # ==========================================
    # CREATION RESULT
    # ==========================================

    def build_creation_result(
        self,
        *,
        created_invite: CreatedInvite,
        target_role: UserRole,
        scope: InviteScope,
        store_id: int | None,
        bush_id: int | None,
        expires_at: datetime | None,
        max_uses: int,
    ) -> InviteCreationServiceResult:
        token = self.extract_token(
            created_invite
        )

        return InviteCreationServiceResult(
            created_invite=created_invite,
            token=token,
            deep_link=self.build_deep_link(token),
            target_role=target_role,
            scope=scope,
            store_id=store_id,
            bush_id=bush_id,
            expires_at=expires_at,
            max_uses=max_uses,
        )

    # ==========================================
    # ACTIVATION MESSAGE
    # ==========================================

    @classmethod
    def build_activation_message(
        cls,
        *,
        target_role: UserRole | None,
        store_id: int | None,
        bush_id: int | None,
        requires_approval: bool,
        was_activated: bool,
    ) -> str:
        if not was_activated:
            return (
                "Не вдалося активувати запрошення. "
                "Можливо, воно прострочене або вже "
                "використане."
            )

        if requires_approval:
            return (
                "✅ Запрошення прийнято.\n\n"
                "Заявку передано відповідальному "
                "адміністратору. Після підтвердження "
                "бот відкриє доступ до торгової точки."
            )

        role_name = cls.role_text(
            target_role
        )

        target_text = ""

        if store_id is not None:
            target_text = (
                f"\n🏪 Торгова точка: #{store_id}"
            )

        elif bush_id is not None:
            target_text = (
                f"\n🌿 Кущ: #{bush_id}"
            )

        return (
            "✅ <b>Запрошення активовано!</b>\n\n"
            f"Ваша роль: <b>{role_name}</b>"
            f"{target_text}"
        )

    # ==========================================
    # AUDIT LOG
    # ==========================================

    async def log_invite_creation(
        self,
        *,
        actor: User,
        result: InviteCreationServiceResult,
        description: str,
    ) -> None:
        invite = result.invite

        invite_id = self.extract_int_attribute(
            invite,
            "id",
        )

        action = self.resolve_audit_action(
            "create",
            "created",
            "add",
        )

        entity_type = self.resolve_entity_type(
            "invite",
            "invitation",
            "user",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=invite_id,
            context=AuditContext(
                actor_user_id=actor.id,
                description=description,
                source="telegram_bot",
            ),
            new_values={
                "target_role":
                    result.target_role.value,
                "scope":
                    result.scope.value,
                "store_id":
                    result.store_id,
                "bush_id":
                    result.bush_id,
                "expires_at": (
                    result.expires_at.isoformat()
                    if result.expires_at is not None
                    else None
                ),
                "max_uses":
                    result.max_uses,
            },
        )

    async def log_invite_activation(
        self,
        *,
        user: User,
        result: InviteActivationServiceResult,
        activated_at: datetime,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> None:
        action = self.resolve_audit_action(
            "update",
            "activate",
            "activated",
        )

        entity_type = self.resolve_entity_type(
            "invite",
            "invitation",
            "user",
        )

        activation_id = (
            self.extract_int_attribute(
                result.activation,
                "invite_id",
                "id",
            )
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=activation_id,
            context=AuditContext(
                actor_user_id=user.id,
                description=(
                    "Користувач активував "
                    "Telegram-запрошення"
                ),
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=(
                    telegram_message_id
                ),
                source="telegram_bot",
            ),
            new_values={
                "user_id":
                    user.id,
                "target_role": (
                    result.target_role.value
                    if result.target_role
                    is not None
                    else None
                ),
                "store_id":
                    result.store_id,
                "bush_id":
                    result.bush_id,
                "requires_approval":
                    result.requires_approval,
                "was_activated":
                    result.was_activated,
                "activated_at":
                    activated_at.isoformat(),
            },
        )

    async def log_invite_revocation(
        self,
        *,
        actor: User,
        invite: Any,
        invite_id: int,
        reason: str,
        revoked_at: datetime,
    ) -> None:
        action = self.resolve_audit_action(
            "update",
            "revoke",
            "deactivate",
        )

        entity_type = self.resolve_entity_type(
            "invite",
            "invitation",
            "user",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=invite_id,
            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=(
                    "Відкликано Telegram-запрошення"
                ),
                source="telegram_bot",
            ),
            old_values={
                "is_active": True,
                "revoked_at": None,
            },
            new_values={
                "is_active": False,
                "revoked_at":
                    revoked_at.isoformat(),
                "store_id":
                    self.extract_int_attribute(
                        invite,
                        "store_id",
                        "target_store_id",
                    ),
                "bush_id":
                    self.extract_int_attribute(
                        invite,
                        "bush_id",
                        "target_bush_id",
                    ),
            },
        )

    # ==========================================
    # REPOSITORY ADAPTER
    # ==========================================

    async def invoke_repository(
        self,
        *,
        method_names: tuple[str, ...],
        **kwargs: Any,
    ) -> Any:
        repository = self.repositories.invites

        for method_name in method_names:
            method = getattr(
                repository,
                method_name,
                None,
            )

            if method is None or not callable(method):
                continue

            signature = inspect.signature(method)

            accepts_kwargs = any(
                parameter.kind
                == inspect.Parameter.VAR_KEYWORD
                for parameter
                in signature.parameters.values()
            )

            if accepts_kwargs:
                accepted_kwargs = kwargs

            else:
                accepted_kwargs = {
                    name: value
                    for name, value
                    in kwargs.items()
                    if name in signature.parameters
                }

            result = method(
                **accepted_kwargs
            )

            if inspect.isawaitable(result):
                return await result

            return result

        raise AttributeError(
            "InviteRepository не містить "
            "жодного очікуваного методу: "
            + ", ".join(method_names)
        )

    # ==========================================
    # DATA EXTRACTION
    # ==========================================

    @staticmethod
    def extract_invite_object(
        created_invite: Any,
    ) -> Any:
        for field_name in (
            "invite",
            "invite_link",
            "entity",
            "model",
        ):
            value = getattr(
                created_invite,
                field_name,
                None,
            )

            if value is not None:
                return value

        return created_invite

    @classmethod
    def extract_token(
        cls,
        created_invite: Any,
    ) -> str:
        invite = cls.extract_invite_object(
            created_invite
        )

        for source in (
            created_invite,
            invite,
        ):
            for field_name in (
                "token",
                "raw_token",
                "plain_token",
                "invite_token",
            ):
                value = getattr(
                    source,
                    field_name,
                    None,
                )

                if (
                    isinstance(value, str)
                    and value.strip()
                ):
                    return cls.normalize_token(
                        value
                    )

        raise ValueError(
            "Репозиторій не повернув "
            "відкритий токен запрошення."
        )

    @classmethod
    def extract_role(
        cls,
        source: Any,
    ) -> UserRole | None:
        raw_role = cls.extract_attribute(
            source,
            "target_role",
            "role",
            "user_role",
            default=None,
        )

        if raw_role is None:
            nested = cls.extract_attribute(
                source,
                "invite",
                "entity",
                default=None,
            )

            if nested is not None:
                raw_role = cls.extract_attribute(
                    nested,
                    "target_role",
                    "role",
                    default=None,
                )

        if isinstance(raw_role, UserRole):
            return raw_role

        if isinstance(raw_role, str):
            normalized_value = (
                raw_role.strip().lower()
            )

            for role in UserRole:
                if normalized_value in {
                    role.name.lower(),
                    str(role.value).lower(),
                }:
                    return role

        return None

    @staticmethod
    def extract_attribute(
        source: Any,
        *field_names: str,
        default: Any = None,
    ) -> Any:
        if source is None:
            return default

        if isinstance(source, dict):
            for field_name in field_names:
                if field_name in source:
                    return source[field_name]

            return default

        for field_name in field_names:
            if hasattr(source, field_name):
                return getattr(
                    source,
                    field_name,
                )

        return default

    @classmethod
    def extract_int_attribute(
        cls,
        source: Any,
        *field_names: str,
    ) -> int | None:
        value = cls.extract_attribute(
            source,
            *field_names,
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

    # ==========================================
    # ENUM
    # ==========================================

    @classmethod
    def resolve_audit_action(
        cls,
        *names: str,
    ) -> AuditAction:
        try:
            return cls.resolve_enum_member(
                AuditAction,
                *names,
            )

        except ValueError:
            return cls.resolve_enum_member(
                AuditAction,
                "update",
                "updated",
                "change",
                "changed",
            )

    @classmethod
    def resolve_entity_type(
        cls,
        *names: str,
    ) -> EntityType:
        return cls.resolve_enum_member(
            EntityType,
            *names,
        )

    @staticmethod
    def resolve_enum_member(
        enum_class: type[EnumType],
        *names: str,
    ) -> EnumType:
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

        raise ValueError(
            f"У {enum_class.__name__} відсутнє "
            f"значення: {sorted(normalized_names)}."
        )

    # ==========================================
    # USER ROLE
    # ==========================================

    @staticmethod
    def resolve_user_role(
        value: UserRole | str | None,
    ) -> UserRole | None:
        if value is None:
            return None

        if isinstance(
            value,
            UserRole,
        ):
            return value

        normalized = (
            str(value)
            .strip()
            .lower()
        )

        for role in UserRole:
            if normalized in {
                role.name.lower(),
                str(role.value).lower(),
            }:
                return role

        raise ValueError(
            f"Невідома роль користувача: {value}."
        )

    # ==========================================
    # FORMATTING
    # ==========================================

    @staticmethod
    def role_text(
        role: UserRole | None,
    ) -> str:
        translations = {
            UserRole.ROOT_ADMIN:
                "ROOT_ADMIN",

            UserRole.DIRECTOR:
                "директор",

            UserRole.BUSH_ADMIN:
                "адміністратор куща",

            UserRole.LION:
                "лев",

            UserRole.STORE_USER:
                "працівник торгової точки",
        }

        if role is None:
            return "користувач"

        return translations.get(
            role,
            str(role.value),
        )

    # ==========================================
    # VALIDATION
    # ==========================================

    @classmethod
    def normalize_token(
        cls,
        token: str,
    ) -> str:
        normalized_token = token.strip()

        if not normalized_token:
            raise ValueError(
                "Токен запрошення порожній."
            )

        if not cls.TOKEN_PATTERN.fullmatch(
            normalized_token
        ):
            raise ValueError(
                "Токен запрошення має "
                "некоректний формат."
            )

        return normalized_token

    @staticmethod
    def normalize_bot_username(
        bot_username: str,
    ) -> str:
        normalized_username = (
            bot_username
            .strip()
            .lstrip("@")
        )

        if not normalized_username:
            raise ValueError(
                "Username Telegram-бота "
                "не може бути порожнім."
            )

        if not re.fullmatch(
            r"[A-Za-z0-9_]{5,64}",
            normalized_username,
        ):
            raise ValueError(
                "Username Telegram-бота "
                "має некоректний формат."
            )

        return normalized_username

    @staticmethod
    def resolve_expiration(
        *,
        current_time: datetime,
        expires_in: timedelta | None,
        expires_at: datetime | None,
    ) -> datetime | None:
        if (
            expires_in is not None
            and expires_at is not None
        ):
            raise ValueError(
                "Потрібно вказати або expires_in, "
                "або expires_at, але не обидва."
            )

        if expires_in is not None:
            if expires_in <= timedelta(0):
                raise ValueError(
                    "Строк дії повинен бути "
                    "більшим за нуль."
                )

            if expires_in > timedelta(days=365):
                raise ValueError(
                    "Запрошення не може діяти "
                    "довше 365 днів."
                )

            return current_time + expires_in

        if expires_at is not None:
            InviteService.validate_aware_datetime(
                expires_at,
                field_name="expires_at",
            )

            if expires_at <= current_time:
                raise ValueError(
                    "Дата завершення дії повинна "
                    "бути в майбутньому."
                )

        return expires_at

    @staticmethod
    def validate_max_uses(
        max_uses: int,
    ) -> None:
        if isinstance(max_uses, bool):
            raise ValueError(
                "Кількість використань "
                "повинна бути числом."
            )

        if max_uses < 1 or max_uses > 1000:
            raise ValueError(
                "Кількість використань повинна "
                "бути від 1 до 1000."
            )

    @staticmethod
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
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
        if value is None:
            return None

        normalized_value = " ".join(
            value.strip().split()
        )

        return normalized_value or None