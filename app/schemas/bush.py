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


class BushBase(BaseModel):
    """
    Базові поля куща.
    """

    name: str = Field(
        min_length=1,
        max_length=150,
    )

    code: str = Field(
        min_length=1,
        max_length=50,
    )

    telegram_topic_id: int | None = None

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
        if not isinstance(
            value,
            str,
        ):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return normalized


    @field_validator(
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

        if not isinstance(
            value,
            str,
        ):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return (
            normalized
            or None
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
        "telegram_topic_id",
        mode="after",
    )
    @classmethod
    def validate_topic_id(
        cls,
        value: int | None,
    ) -> int | None:
        if value is None:
            return None

        if value <= 0:
            raise ValueError(
                "telegram_topic_id "
                "повинен бути більшим за нуль."
            )

        return value


# =========================================================
# CREATE
# =========================================================


class BushCreate(BushBase):
    """
    Дані для створення нового куща.
    """

    is_active: bool = True


# =========================================================
# UPDATE
# =========================================================


class BushUpdate(BaseModel):
    """
    Часткове оновлення куща.

    Усі поля optional, щоб можна було
    змінювати лише потрібні значення.
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

    is_active: bool | None = None

    telegram_topic_id: int | None = None

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

        if not isinstance(
            value,
            str,
        ):
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

        if not isinstance(
            value,
            str,
        ):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return (
            normalized
            or None
        )


    @field_validator(
        "telegram_topic_id",
        mode="after",
    )
    @classmethod
    def validate_topic_id(
        cls,
        value: int | None,
    ) -> int | None:
        if value is None:
            return None

        if value <= 0:
            raise ValueError(
                "telegram_topic_id "
                "повинен бути більшим за нуль."
            )

        return value


# =========================================================
# READ
# =========================================================


class BushRead(BushBase):
    """
    Повна схема куща з PostgreSQL.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    is_active: bool

    created_at: datetime
    updated_at: datetime


# =========================================================
# DETAILS
# =========================================================


class BushDetails(BushRead):
    """
    Розширена інформація про кущ.
    """

    active_stores_count: int = 0
    total_stores_count: int = 0


# =========================================================
# SHORT ITEM
# =========================================================


class BushShort(BaseModel):
    """
    Коротка схема для списків,
    callback-меню та селекторів.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    name: str
    code: str
    is_active: bool


# =========================================================
# STATE CHANGE
# =========================================================


class BushStateUpdate(BaseModel):
    """
    Окремий payload для
    активації / деактивації куща.
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

        if not isinstance(
            value,
            str,
        ):
            return value

        normalized = " ".join(
            value.strip().split()
        )

        return (
            normalized
            or None
        )


# =========================================================
# ALIASES
# =========================================================


BushResponse = BushRead
BushDetailResponse = BushDetails
BushListItem = BushShort


__all__ = [
    "BushBase",
    "BushCreate",
    "BushUpdate",
    "BushRead",
    "BushDetails",
    "BushShort",
    "BushStateUpdate",

    "BushResponse",
    "BushDetailResponse",
    "BushListItem",
]