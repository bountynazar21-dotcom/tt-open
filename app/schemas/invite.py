from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.database.models.enums import UserRole
from app.services.invite_service import InviteScope


# =========================================================
# BASE
# =========================================================


class InviteBase(BaseModel):
    """
    Базова схема Telegram-запрошення.
    """

    target_role: UserRole

    scope: InviteScope

    store_id: int | None = Field(
        default=None,
        gt=0,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    expires_at: datetime | None = None

    max_uses: int = Field(
        default=1,
        ge=1,
        le=1000,
    )

    note: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "note",
        mode="before",
    )
    @classmethod
    def normalize_note(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized or None


# =========================================================
# CREATE STORE INVITE
# =========================================================


class StoreInviteCreate(BaseModel):
    """
    Створення invite для працівника ТТ.
    """

    store_id: int = Field(
        gt=0,
    )

    expires_at: datetime | None = None

    max_uses: int = Field(
        default=1,
        ge=1,
        le=1000,
    )

    note: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "note",
        mode="before",
    )
    @classmethod
    def normalize_note(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized or None


# =========================================================
# CREATE BUSH INVITE
# =========================================================


class BushInviteCreate(BaseModel):
    """
    Створення invite для куща.

    Доступні ролі:
    - BUSH_ADMIN
    - LION
    """

    bush_id: int = Field(
        gt=0,
    )

    target_role: UserRole

    expires_at: datetime | None = None

    max_uses: int = Field(
        default=1,
        ge=1,
        le=1000,
    )

    note: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "target_role",
    )
    @classmethod
    def validate_target_role(
        cls,
        value: UserRole,
    ) -> UserRole:
        if value not in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            raise ValueError(
                "Для куща дозволені лише "
                "BUSH_ADMIN або LION."
            )

        return value

    @field_validator(
        "note",
        mode="before",
    )
    @classmethod
    def normalize_note(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized or None


# =========================================================
# CREATE DIRECTOR INVITE
# =========================================================


class DirectorInviteCreate(BaseModel):
    """
    Створення invite директора.
    """

    expires_at: datetime | None = None

    max_uses: int = Field(
        default=1,
        ge=1,
        le=1000,
    )

    note: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "note",
        mode="before",
    )
    @classmethod
    def normalize_note(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized or None


# =========================================================
# GENERIC CREATE
# =========================================================


class InviteCreate(InviteBase):
    """
    Універсальна схема створення invite.
    """

    pass


# =========================================================
# CREATED RESULT
# =========================================================


class InviteCreated(BaseModel):
    """
    Результат створення Telegram invite.
    """

    token: str

    deep_link: str

    target_role: UserRole

    scope: InviteScope

    store_id: int | None = None

    bush_id: int | None = None

    expires_at: datetime | None = None

    max_uses: int = Field(
        ge=1,
    )

    @field_validator(
        "token",
        "deep_link",
        mode="before",
    )
    @classmethod
    def normalize_required_text(
        cls,
        value: object,
    ) -> object:
        if not isinstance(
            value,
            str,
        ):
            return value

        return value.strip()


# =========================================================
# PAYLOAD
# =========================================================


class InvitePayloadSchema(BaseModel):
    """
    Telegram /start payload.
    """

    raw_payload: str

    token: str

    @field_validator(
        "raw_payload",
        "token",
        mode="before",
    )
    @classmethod
    def normalize_text(
        cls,
        value: object,
    ) -> object:
        if not isinstance(
            value,
            str,
        ):
            return value

        return value.strip()


# =========================================================
# ACTIVATION REQUEST
# =========================================================


class InviteActivate(BaseModel):
    """
    Дані для активації invite.
    """

    token_or_payload: str = Field(
        min_length=1,
        max_length=2048,
    )

    telegram_username: str | None = Field(
        default=None,
        max_length=64,
    )

    first_name: str | None = Field(
        default=None,
        max_length=255,
    )

    last_name: str | None = Field(
        default=None,
        max_length=255,
    )

    telegram_chat_id: int | None = None

    telegram_message_id: int | None = Field(
        default=None,
        gt=0,
    )

    @field_validator(
        "token_or_payload",
        mode="before",
    )
    @classmethod
    def normalize_token(
        cls,
        value: object,
    ) -> object:
        if not isinstance(
            value,
            str,
        ):
            return value

        return value.strip()

    @field_validator(
        "telegram_username",
        "first_name",
        "last_name",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            return value

        normalized = value.strip()

        return normalized or None


# =========================================================
# ACTIVATION RESULT
# =========================================================


class InviteActivationResponse(BaseModel):
    """
    Результат активації invite.
    """

    success: bool

    token: str

    user_id: int = Field(
        gt=0,
    )

    target_role: UserRole | None = None

    store_id: int | None = None

    bush_id: int | None = None

    requires_approval: bool = False

    message: str


# =========================================================
# INSPECT
# =========================================================


class InviteInspectRequest(BaseModel):
    """
    Перевірка invite без використання.
    """

    token_or_payload: str = Field(
        min_length=1,
        max_length=2048,
    )

    @field_validator(
        "token_or_payload",
        mode="before",
    )
    @classmethod
    def normalize_token(
        cls,
        value: object,
    ) -> object:
        if not isinstance(
            value,
            str,
        ):
            return value

        return value.strip()


class InviteInspectResponse(BaseModel):
    """
    Результат перевірки invite.
    """

    valid: bool

    invite_id: int | None = None

    target_role: UserRole | None = None

    store_id: int | None = None

    bush_id: int | None = None

    expires_at: datetime | None = None

    max_uses: int | None = None

    use_count: int | None = None

    is_active: bool | None = None

    reason: str | None = None


# =========================================================
# REVOKE
# =========================================================


class InviteRevoke(BaseModel):
    """
    Відкликання invite.
    """

    invite_id: int = Field(
        gt=0,
    )

    reason: str = Field(
        default="Відкликано через Telegram",
        min_length=1,
        max_length=2000,
    )

    @field_validator(
        "reason",
        mode="before",
    )
    @classmethod
    def normalize_reason(
        cls,
        value: object,
    ) -> object:
        if not isinstance(
            value,
            str,
        ):
            return value

        return " ".join(
            value.strip().split()
        )


class InviteRevokeResponse(BaseModel):
    """
    Результат відкликання.
    """

    invite_id: int

    success: bool

    revoked_at: datetime

    revoked_by_id: int

    reason: str


# =========================================================
# DATABASE READ
# =========================================================


class InviteRead(BaseModel):
    """
    Універсальна схема Invite-моделі з БД.

    Поля зроблені сумісними з поточним
    InviteRepository / InviteService.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    created_by_id: int | None = None

    target_role: UserRole | None = None

    store_id: int | None = None

    bush_id: int | None = None

    expires_at: datetime | None = None

    max_uses: int = 1

    use_count: int = 0

    is_active: bool = True

    revoked_at: datetime | None = None

    revoked_by_id: int | None = None

    note: str | None = None

    created_at: datetime | None = None

    updated_at: datetime | None = None


# =========================================================
# SHORT
# =========================================================


class InviteShort(BaseModel):
    """
    Короткий invite для Telegram-списків.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    target_role: UserRole | None = None

    store_id: int | None = None

    bush_id: int | None = None

    expires_at: datetime | None = None

    max_uses: int = 1

    use_count: int = 0

    is_active: bool = True


# =========================================================
# DETAILS
# =========================================================


class InviteDetails(
    InviteRead
):
    """
    Розширена картка invite.
    """

    scope: InviteScope | None = None

    deep_link: str | None = None

    remaining_uses: int | None = None

    is_expired: bool = False

    is_revoked: bool = False

    can_be_used: bool = False


# =========================================================
# LIST FILTER
# =========================================================


class InviteListFilter(BaseModel):
    """
    Фільтри списку invite.
    """

    active_only: bool = False

    include_expired: bool = True

    include_revoked: bool = True

    store_id: int | None = Field(
        default=None,
        gt=0,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    target_role: UserRole | None = None

    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
    )


# =========================================================
# ALIASES
# =========================================================


InviteResponse = InviteRead

InviteDetailResponse = InviteDetails

InviteListItem = InviteShort

InviteCreationResponse = InviteCreated

InviteActivationResultSchema = (
    InviteActivationResponse
)

InviteRevocationResultSchema = (
    InviteRevokeResponse
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "InviteBase",

    "StoreInviteCreate",
    "BushInviteCreate",
    "DirectorInviteCreate",
    "InviteCreate",

    "InviteCreated",

    "InvitePayloadSchema",

    "InviteActivate",
    "InviteActivationResponse",

    "InviteInspectRequest",
    "InviteInspectResponse",

    "InviteRevoke",
    "InviteRevokeResponse",

    "InviteRead",
    "InviteShort",
    "InviteDetails",

    "InviteListFilter",

    "InviteResponse",
    "InviteDetailResponse",
    "InviteListItem",

    "InviteCreationResponse",
    "InviteActivationResultSchema",
    "InviteRevocationResultSchema",
]