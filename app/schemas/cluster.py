from __future__ import annotations

from datetime import datetime, time

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


# =========================================================
# BASE
# =========================================================


class ClusterBase(BaseModel):
    """
    Базові поля кластера відкриття ТТ.
    """

    name: str = Field(
        min_length=1,
        max_length=150,
    )

    code: str = Field(
        min_length=1,
        max_length=50,
    )

    opening_time: time

    opening_deadline_minutes: int = Field(
        default=10,
        ge=0,
        le=180,
    )

    is_active: bool = True

    note: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "name",
        "code",
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
        "code",
        mode="after",
    )
    @classmethod
    def normalize_code(
        cls,
        value: str,
    ) -> str:
        return (
            value.strip()
            .upper()
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

        if not isinstance(value, str):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized or None


# =========================================================
# CREATE
# =========================================================


class ClusterCreate(
    ClusterBase
):
    """
    Створення нового кластера.
    """

    pass


# =========================================================
# UPDATE
# =========================================================


class ClusterUpdate(BaseModel):
    """
    Часткове оновлення кластера.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    opening_time: time | None = None

    opening_deadline_minutes: int | None = Field(
        default=None,
        ge=0,
        le=180,
    )

    is_active: bool | None = None

    note: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "name",
        "code",
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
        "code",
        mode="after",
    )
    @classmethod
    def normalize_code(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return (
            value.strip()
            .upper()
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

        if not isinstance(value, str):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized or None


# =========================================================
# READ
# =========================================================


class ClusterRead(
    ClusterBase
):
    """
    Повна схема кластера з БД.
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


class ClusterShort(BaseModel):
    """
    Короткий формат для меню.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    name: str
    code: str

    opening_time: time

    is_active: bool


# =========================================================
# DETAILS
# =========================================================


class ClusterDetails(
    ClusterRead
):
    """
    Розширена інформація про кластер.
    """

    stores_count: int = Field(
        default=0,
        ge=0,
    )

    active_stores_count: int = Field(
        default=0,
        ge=0,
    )

    opening_time_text: str | None = None

    deadline_time_text: str | None = None


# =========================================================
# DEADLINE INFO
# =========================================================


class ClusterDeadlineInfo(BaseModel):
    """
    Розраховані часові параметри кластера.
    """

    cluster_id: int

    opening_time: time

    deadline_minutes: int = Field(
        ge=0,
    )

    deadline_time: time


# =========================================================
# STATE UPDATE
# =========================================================


class ClusterStateUpdate(BaseModel):
    """
    Активація / деактивація кластера.
    """

    is_active: bool

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

        if not isinstance(value, str):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized or None


# =========================================================
# ALIASES
# =========================================================


ClusterResponse = ClusterRead
ClusterDetailResponse = ClusterDetails
ClusterListItem = ClusterShort


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "ClusterBase",
    "ClusterCreate",
    "ClusterUpdate",
    "ClusterRead",
    "ClusterShort",
    "ClusterDetails",
    "ClusterDeadlineInfo",
    "ClusterStateUpdate",

    "ClusterResponse",
    "ClusterDetailResponse",
    "ClusterListItem",
]