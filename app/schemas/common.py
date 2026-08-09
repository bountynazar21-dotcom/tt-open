from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


# =========================================================
# GENERICS
# =========================================================


T = TypeVar("T")


# =========================================================
# BASE SCHEMA
# =========================================================


class SchemaBase(BaseModel):
    """
    Базова Pydantic-схема проєкту.

    Дозволяє створювати схеми
    напряму із SQLAlchemy-моделей.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="ignore",
    )


# =========================================================
# ID
# =========================================================


class IdSchema(SchemaBase):
    """
    Схема з одним ID.
    """

    id: int = Field(
        gt=0,
    )


class EntityIdSchema(SchemaBase):
    """
    Універсальний entity_id.
    """

    entity_id: int = Field(
        gt=0,
    )


# =========================================================
# MESSAGE
# =========================================================


class MessageResponse(SchemaBase):
    """
    Просте повідомлення API / сервісу.
    """

    message: str


class SuccessResponse(SchemaBase):
    """
    Стандартна відповідь про успішну операцію.
    """

    success: bool = True

    message: str | None = None


class ErrorResponse(SchemaBase):
    """
    Стандартна відповідь про помилку.
    """

    success: bool = False

    error: str

    detail: str | None = None


# =========================================================
# ACTION RESULT
# =========================================================


class ActionResult(SchemaBase):
    """
    Універсальний результат операції.
    """

    success: bool

    message: str | None = None

    entity_id: int | None = Field(
        default=None,
        gt=0,
    )

    data: dict[str, Any] | None = None


# =========================================================
# PAGINATION
# =========================================================


class PaginationParams(SchemaBase):
    """
    Параметри пагінації.
    """

    page: int = Field(
        default=1,
        ge=1,
    )

    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
    )

    @property
    def offset(self) -> int:
        return (
            self.page - 1
        ) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginationMeta(SchemaBase):
    """
    Метадані пагінації.
    """

    page: int = Field(
        ge=1,
    )

    page_size: int = Field(
        ge=1,
    )

    total_items: int = Field(
        ge=0,
    )

    total_pages: int = Field(
        ge=0,
    )

    has_previous: bool = False
    has_next: bool = False


class PaginatedResponse(
    SchemaBase,
    Generic[T],
):
    """
    Універсальна сторінка результатів.
    """

    items: list[T] = Field(
        default_factory=list,
    )

    pagination: PaginationMeta


# =========================================================
# DATE RANGE
# =========================================================


class DateRange(SchemaBase):
    """
    Діапазон бізнес-дат.
    """

    date_from: date

    date_to: date

    @field_validator(
        "date_to",
    )
    @classmethod
    def validate_date_to(
        cls,
        value: date,
        info: Any,
    ) -> date:
        date_from = (
            info.data.get(
                "date_from"
            )
        )

        if (
            date_from is not None
            and value < date_from
        ):
            raise ValueError(
                "date_to не може бути "
                "раніше date_from."
            )

        return value


# =========================================================
# DATETIME RANGE
# =========================================================


class DateTimeRange(SchemaBase):
    """
    Діапазон datetime.
    """

    datetime_from: datetime

    datetime_to: datetime

    @field_validator(
        "datetime_to",
    )
    @classmethod
    def validate_datetime_to(
        cls,
        value: datetime,
        info: Any,
    ) -> datetime:
        datetime_from = (
            info.data.get(
                "datetime_from"
            )
        )

        if (
            datetime_from is not None
            and value < datetime_from
        ):
            raise ValueError(
                "datetime_to не може бути "
                "раніше datetime_from."
            )

        return value


# =========================================================
# REASON
# =========================================================


class ReasonSchema(SchemaBase):
    """
    Причина адміністративної зміни.
    """

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


class OptionalReasonSchema(SchemaBase):
    """
    Необов'язкова причина.
    """

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
# BOOLEAN STATE
# =========================================================


class ActiveStateSchema(
    OptionalReasonSchema
):
    """
    Активація / деактивація сутності.
    """

    is_active: bool


# =========================================================
# TELEGRAM REFERENCES
# =========================================================


class TelegramUserReference(SchemaBase):
    """
    Ідентифікація Telegram-користувача.
    """

    telegram_id: int = Field(
        gt=0,
    )

    username: str | None = None

    first_name: str | None = None

    last_name: str | None = None


class TelegramMessageReference(SchemaBase):
    """
    Посилання на Telegram-повідомлення.
    """

    chat_id: int

    message_id: int = Field(
        gt=0,
    )

    topic_id: int | None = Field(
        default=None,
        gt=0,
    )


# =========================================================
# AUDIT TIMESTAMPS
# =========================================================


class TimestampSchema(SchemaBase):
    """
    created_at / updated_at.
    """

    created_at: datetime
    updated_at: datetime


# =========================================================
# SEARCH
# =========================================================


class SearchParams(SchemaBase):
    """
    Загальний пошук.
    """

    query: str | None = Field(
        default=None,
        max_length=200,
    )

    limit: int = Field(
        default=20,
        ge=1,
        le=100,
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
# EXPORTS
# =========================================================


__all__ = [
    "SchemaBase",

    "IdSchema",
    "EntityIdSchema",

    "MessageResponse",
    "SuccessResponse",
    "ErrorResponse",
    "ActionResult",

    "PaginationParams",
    "PaginationMeta",
    "PaginatedResponse",

    "DateRange",
    "DateTimeRange",

    "ReasonSchema",
    "OptionalReasonSchema",
    "ActiveStateSchema",

    "TelegramUserReference",
    "TelegramMessageReference",

    "TimestampSchema",

    "SearchParams",
]