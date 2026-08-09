from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


# =========================================================
# BASE
# =========================================================


class StoreBase(BaseModel):
    """
    Базові поля торгової точки.
    """

    store_number: int = Field(
        gt=0,
    )

    code: str = Field(
        min_length=1,
        max_length=50,
    )

    name: str = Field(
        min_length=1,
        max_length=200,
    )

    city: str = Field(
        min_length=1,
        max_length=150,
    )

    address: str | None = Field(
        default=None,
        max_length=300,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    cluster_id: int | None = Field(
        default=None,
        gt=0,
    )

    is_active: bool = True

    note: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "code",
        mode="before",
    )
    @classmethod
    def normalize_code(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, str):
            return value

        return (
            value.strip()
            .upper()
        )

    @field_validator(
        "name",
        "city",
        mode="before",
    )
    @classmethod
    def normalize_required_text(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, str):
            return value

        return " ".join(
            value.strip().split()
        )

    @field_validator(
        "address",
        "note",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized or None


# =========================================================
# CREATE
# =========================================================


class StoreCreate(
    StoreBase
):
    """
    Створення нової ТТ.
    """

    pass


# =========================================================
# UPDATE
# =========================================================


class StoreUpdate(BaseModel):
    """
    Часткове оновлення ТТ.
    """

    store_number: int | None = Field(
        default=None,
        gt=0,
    )

    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    city: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    address: str | None = Field(
        default=None,
        max_length=300,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    cluster_id: int | None = Field(
        default=None,
        gt=0,
    )

    is_active: bool | None = None

    note: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "code",
        mode="before",
    )
    @classmethod
    def normalize_code(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        return (
            value.strip()
            .upper()
        )

    @field_validator(
        "name",
        "city",
        mode="before",
    )
    @classmethod
    def normalize_required_text(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        return " ".join(
            value.strip().split()
        )

    @field_validator(
        "address",
        "note",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized or None


# =========================================================
# STATE UPDATE
# =========================================================


class StoreStateUpdate(BaseModel):
    """
    Активація / деактивація ТТ.
    """

    is_active: bool

    reason: str | None = Field(
        default=None,
        max_length=2000,
    )

    deactivate_bindings: bool = False

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

        if not isinstance(value, str):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized or None


# =========================================================
# BUSH CHANGE
# =========================================================


class StoreBushUpdate(BaseModel):
    """
    Перенесення ТТ в інший кущ.
    """

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

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
        if not isinstance(value, str):
            return value

        return " ".join(
            value.strip().split()
        )


# =========================================================
# CLUSTER CHANGE
# =========================================================


class StoreClusterUpdate(BaseModel):
    """
    Зміна кластера ТТ.
    """

    cluster_id: int | None = Field(
        default=None,
        gt=0,
    )

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
        if not isinstance(value, str):
            return value

        return " ".join(
            value.strip().split()
        )


# =========================================================
# READ
# =========================================================


class StoreRead(
    StoreBase
):
    """
    Повна схема ТТ із PostgreSQL.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    created_at: datetime
    updated_at: datetime


# =========================================================
# SHORT
# =========================================================


class StoreShort(BaseModel):
    """
    Коротка схема ТТ для списків
    та Telegram-кнопок.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    store_number: int

    code: str

    name: str

    city: str

    is_active: bool

    bush_id: int | None = None

    cluster_id: int | None = None


# =========================================================
# DETAILS
# =========================================================


class StoreDetails(
    StoreRead
):
    """
    Розширена картка ТТ.
    """

    bush_name: str | None = None

    cluster_name: str | None = None

    cluster_opening_time: str | None = None

    active_users_count: int = Field(
        default=0,
        ge=0,
    )

    has_schedule: bool = False

    has_active_exception: bool = False


# =========================================================
# SELECT ITEM
# =========================================================


class StoreSelectItem(BaseModel):
    """
    Дані ТТ для меню вибору.
    """

    id: int

    code: str

    name: str

    city: str

    label: str | None = None

    @property
    def display_name(
        self,
    ) -> str:
        if self.label:
            return self.label

        return (
            f"{self.code} — "
            f"{self.name}"
        )


# =========================================================
# BINDING INFO
# =========================================================


class StoreBindingInfo(BaseModel):
    """
    Інформація про кількість
    активних користувачів ТТ.
    """

    store_id: int = Field(
        gt=0,
    )

    active_bindings: int = Field(
        default=0,
        ge=0,
    )

    total_bindings: int = Field(
        default=0,
        ge=0,
    )


# =========================================================
# IMPORT PREVIEW
# =========================================================


class StoreImportPreviewItem(BaseModel):
    """
    Один рядок preview імпорту ТТ.
    """

    row_number: int = Field(
        gt=0,
    )

    status: str

    store_number: int | None = None

    code: str | None = None

    name: str | None = None

    city: str | None = None

    address: str | None = None

    bush_id: int | None = None

    cluster_id: int | None = None

    is_active: bool | None = None

    existing_store_id: int | None = None

    issues: list[str] = Field(
        default_factory=list,
    )


# =========================================================
# IMPORT RESULT
# =========================================================


class StoreImportResult(BaseModel):
    """
    Підсумок імпорту ТТ.
    """

    file_name: str

    total_rows: int = Field(
        ge=0,
    )

    created_count: int = Field(
        ge=0,
    )

    updated_count: int = Field(
        ge=0,
    )

    unchanged_count: int = Field(
        ge=0,
    )

    ignored_count: int = Field(
        ge=0,
    )

    invalid_count: int = Field(
        ge=0,
    )

    failed_count: int = Field(
        default=0,
        ge=0,
    )


# =========================================================
# ALIASES
# =========================================================


StoreResponse = StoreRead

StoreDetailResponse = StoreDetails

StoreListItem = StoreShort


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "StoreBase",
    "StoreCreate",
    "StoreUpdate",

    "StoreStateUpdate",
    "StoreBushUpdate",
    "StoreClusterUpdate",

    "StoreRead",
    "StoreShort",
    "StoreDetails",
    "StoreSelectItem",

    "StoreBindingInfo",

    "StoreImportPreviewItem",
    "StoreImportResult",

    "StoreResponse",
    "StoreDetailResponse",
    "StoreListItem",
]