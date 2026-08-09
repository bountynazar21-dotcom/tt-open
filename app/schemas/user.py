from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.database.models.enums import (
    UserRole,
    UserStatus,
)


# =========================================================
# BASE
# =========================================================


class UserSchemaBase(BaseModel):
    """
    Базова схема користувача.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="ignore",
    )


# =========================================================
# TELEGRAM PROFILE
# =========================================================


class TelegramProfileSchema(
    UserSchemaBase
):
    """
    Дані Telegram-профілю.
    """

    telegram_id: int = Field(
        gt=0,
    )

    username: str | None = Field(
        default=None,
        max_length=64,
    )

    full_name: str = Field(
        min_length=1,
        max_length=255,
    )

    @field_validator(
        "username",
        mode="before",
    )
    @classmethod
    def normalize_username(
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

        normalized = (
            value.strip()
            .lstrip("@")
        )

        return normalized or None

    @field_validator(
        "full_name",
        mode="before",
    )
    @classmethod
    def normalize_full_name(
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


# =========================================================
# CREATE
# =========================================================


class UserCreate(
    TelegramProfileSchema
):
    """
    Створення нового користувача.

    Зазвичай користувача створює
    AuthMiddleware після першого
    Telegram update.
    """

    phone: str | None = Field(
        default=None,
        max_length=32,
    )

    role: UserRole = (
        UserRole.STORE_USER
    )

    status: UserStatus = (
        UserStatus.PENDING
    )

    @field_validator(
        "phone",
        mode="before",
    )
    @classmethod
    def normalize_phone(
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
# UPDATE PROFILE
# =========================================================


class UserProfileUpdate(
    UserSchemaBase
):
    """
    Оновлення Telegram-профілю
    користувача.
    """

    username: str | None = Field(
        default=None,
        max_length=64,
    )

    full_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    phone: str | None = Field(
        default=None,
        max_length=32,
    )

    @field_validator(
        "username",
        mode="before",
    )
    @classmethod
    def normalize_username(
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

        normalized = (
            value.strip()
            .lstrip("@")
        )

        return normalized or None

    @field_validator(
        "full_name",
        mode="before",
    )
    @classmethod
    def normalize_full_name(
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

    @field_validator(
        "phone",
        mode="before",
    )
    @classmethod
    def normalize_phone(
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
# ROLE UPDATE
# =========================================================


class UserRoleUpdate(
    UserSchemaBase
):
    """
    Зміна ролі користувача.
    """

    role: UserRole

    reason: str = Field(
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


# =========================================================
# STATUS UPDATE
# =========================================================


class UserStatusUpdate(
    UserSchemaBase
):
    """
    Зміна статусу користувача.
    """

    status: UserStatus

    reason: str | None = Field(
        default=None,
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
# BLOCK
# =========================================================


class UserBlock(
    UserSchemaBase
):
    """
    Блокування користувача.
    """

    reason: str | None = Field(
        default=None,
        max_length=500,
    )

    blocked_at: datetime | None = None

    @field_validator(
        "reason",
        mode="before",
    )
    @classmethod
    def normalize_reason(
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
# UNBLOCK
# =========================================================


class UserUnblock(
    UserSchemaBase
):
    """
    Розблокування користувача.
    """

    reason: str | None = Field(
        default=None,
        max_length=500,
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
# PHONE
# =========================================================


class UserPhoneUpdate(
    UserSchemaBase
):
    """
    Збереження номера телефону.
    """

    phone: str = Field(
        min_length=3,
        max_length=32,
    )

    @field_validator(
        "phone",
        mode="before",
    )
    @classmethod
    def normalize_phone(
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
# READ
# =========================================================


class UserRead(
    UserSchemaBase
):
    """
    Повна схема User із PostgreSQL.
    """

    id: int

    telegram_id: int

    username: str | None

    full_name: str

    phone: str | None

    role: UserRole

    status: UserStatus

    is_blocked: bool

    blocked_at: datetime | None

    blocked_reason: str | None

    last_activity_at: datetime | None

    created_at: datetime

    updated_at: datetime


# =========================================================
# SHORT
# =========================================================


class UserShort(
    UserSchemaBase
):
    """
    Короткий користувач
    для списків та Telegram UI.
    """

    id: int

    telegram_id: int

    username: str | None

    full_name: str

    role: UserRole

    status: UserStatus

    is_blocked: bool


# =========================================================
# DETAILS
# =========================================================


class UserDetails(
    UserRead
):
    """
    Розширена картка користувача.
    """

    store_ids: list[int] = Field(
        default_factory=list,
    )

    bush_ids: list[int] = Field(
        default_factory=list,
    )

    store_codes: list[str] = Field(
        default_factory=list,
    )

    bush_names: list[str] = Field(
        default_factory=list,
    )

    primary_store_id: int | None = Field(
        default=None,
        gt=0,
    )

    @property
    def display_name(
        self,
    ) -> str:
        if self.username:
            return (
                f"{self.full_name} "
                f"(@{self.username})"
            )

        return self.full_name

    @property
    def is_active(
        self,
    ) -> bool:
        return (
            self.status
            == UserStatus.ACTIVE
            and not self.is_blocked
        )


# =========================================================
# ACCESS
# =========================================================


class UserAccessSchema(
    UserSchemaBase
):
    """
    Розрахований доступ користувача.
    """

    user_id: int = Field(
        gt=0,
    )

    role: UserRole

    status: UserStatus

    is_blocked: bool

    is_active: bool

    can_manage_network: bool = False

    can_manage_users: bool = False

    store_ids: list[int] = Field(
        default_factory=list,
    )

    bush_ids: list[int] = Field(
        default_factory=list,
    )


# =========================================================
# LIST ITEM
# =========================================================


class UserListItem(
    UserSchemaBase
):
    """
    Рядок списку користувачів.
    """

    id: int

    telegram_id: int

    full_name: str

    username: str | None = None

    phone: str | None = None

    role: UserRole

    status: UserStatus

    is_blocked: bool

    last_activity_at: datetime | None = None

    store_codes: list[str] = Field(
        default_factory=list,
    )

    bush_names: list[str] = Field(
        default_factory=list,
    )


# =========================================================
# SEARCH
# =========================================================


class UserSearch(
    UserSchemaBase
):
    """
    Пошук та фільтрація користувачів.
    """

    query: str | None = Field(
        default=None,
        max_length=255,
    )

    role: UserRole | None = None

    status: UserStatus | None = None

    is_blocked: bool | None = None

    store_id: int | None = Field(
        default=None,
        gt=0,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    limit: int = Field(
        default=50,
        ge=1,
        le=500,
    )

    offset: int = Field(
        default=0,
        ge=0,
    )

    @field_validator(
        "query",
        mode="before",
    )
    @classmethod
    def normalize_query(
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
# STATISTICS
# =========================================================


class UserStatistics(
    UserSchemaBase
):
    """
    Статистика користувачів.
    """

    total_users: int = Field(
        default=0,
        ge=0,
    )

    active_users: int = Field(
        default=0,
        ge=0,
    )

    pending_users: int = Field(
        default=0,
        ge=0,
    )

    blocked_users: int = Field(
        default=0,
        ge=0,
    )

    inactive_users: int = Field(
        default=0,
        ge=0,
    )

    root_admins: int = Field(
        default=0,
        ge=0,
    )

    directors: int = Field(
        default=0,
        ge=0,
    )

    bush_admins: int = Field(
        default=0,
        ge=0,
    )

    lions: int = Field(
        default=0,
        ge=0,
    )

    store_users: int = Field(
        default=0,
        ge=0,
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================


class UserAdminDashboard(
    UserSchemaBase
):
    """
    Дані для адмін-панелі користувачів.
    """

    statistics: UserStatistics

    pending_users: list[
        UserListItem
    ] = Field(
        default_factory=list,
    )

    blocked_users: list[
        UserListItem
    ] = Field(
        default_factory=list,
    )

    recent_users: list[
        UserListItem
    ] = Field(
        default_factory=list,
    )


# =========================================================
# ACTIVITY
# =========================================================


class UserActivityUpdate(
    UserSchemaBase
):
    """
    Оновлення last_activity_at.
    """

    last_activity_at: datetime


# =========================================================
# ALIASES
# =========================================================


UserResponse = UserRead

UserDetailResponse = UserDetails

UserListItemSchema = UserListItem

UserProfile = UserDetails

UserAccess = UserAccessSchema


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "UserSchemaBase",

    "TelegramProfileSchema",

    "UserCreate",
    "UserProfileUpdate",

    "UserRoleUpdate",
    "UserStatusUpdate",

    "UserBlock",
    "UserUnblock",
    "UserPhoneUpdate",

    "UserRead",
    "UserShort",
    "UserDetails",

    "UserAccessSchema",
    "UserListItem",

    "UserSearch",
    "UserStatistics",
    "UserAdminDashboard",

    "UserActivityUpdate",

    "UserResponse",
    "UserDetailResponse",
    "UserListItemSchema",
    "UserProfile",
    "UserAccess",
]