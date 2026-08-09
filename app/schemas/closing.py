from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.database.models.enums import ClosingStatus


# =========================================================
# BASE
# =========================================================


class ClosingBase(BaseModel):
    """
    Базові дані вечірнього звіту ТТ.
    """

    store_id: int = Field(
        gt=0,
    )

    business_date: date

    scheduled_close_time: time
    control_deadline: time

    currency: str = Field(
        default="UAH",
        min_length=3,
        max_length=3,
    )


    @field_validator(
        "currency",
        mode="before",
    )
    @classmethod
    def normalize_currency(
        cls,
        value: object,
    ) -> object:
        if not isinstance(
            value,
            str,
        ):
            return value

        return (
            value.strip()
            .upper()
        )


# =========================================================
# CREATE WAITING
# =========================================================


class ClosingCreate(BaseModel):
    """
    Створення запису очікування
    вечірнього звіту.
    """

    store_id: int = Field(
        gt=0,
    )

    business_date: date

    scheduled_close_time: time

    control_deadline: time


# =========================================================
# RECEIPT
# =========================================================


class ClosingReceipt(BaseModel):
    """
    Дані Telegram-файлу касового чека.
    """

    file_id: str = Field(
        min_length=1,
        max_length=512,
    )

    file_unique_id: str | None = Field(
        default=None,
        max_length=255,
    )

    mime_type: str | None = Field(
        default=None,
        max_length=100,
    )

    file_name: str | None = Field(
        default=None,
        max_length=255,
    )

    file_size: int | None = Field(
        default=None,
        ge=0,
    )


    @field_validator(
        "file_id",
        mode="before",
    )
    @classmethod
    def normalize_file_id(
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
        "file_unique_id",
        "mime_type",
        "file_name",
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

        normalized = (
            value.strip()
        )

        return (
            normalized
            or None
        )


# =========================================================
# CASH
# =========================================================


class ClosingCash(BaseModel):
    """
    Сума каси.
    """

    cash_amount: Decimal = Field(
        ge=Decimal("0"),
        decimal_places=2,
        max_digits=14,
    )

    currency: str = Field(
        default="UAH",
        min_length=3,
        max_length=3,
    )


    @field_validator(
        "cash_amount",
        mode="before",
    )
    @classmethod
    def normalize_cash_amount(
        cls,
        value: object,
    ) -> object:
        if isinstance(
            value,
            str,
        ):
            normalized = (
                value.strip()
                .replace(" ", "")
                .replace(",", ".")
            )

            return normalized

        return value


    @field_validator(
        "currency",
        mode="before",
    )
    @classmethod
    def normalize_currency(
        cls,
        value: object,
    ) -> object:
        if not isinstance(
            value,
            str,
        ):
            return value

        return (
            value.strip()
            .upper()
        )


# =========================================================
# SUBMIT
# =========================================================


class ClosingSubmit(
    ClosingCash
):
    """
    Дані для фінального подання
    вечірнього звіту.
    """

    submitted_by_id: int = Field(
        gt=0,
    )

    submitted_at: datetime

    source: str = Field(
        default="telegram_bot",
        min_length=1,
        max_length=50,
    )

    telegram_chat_id: int | None = None

    telegram_message_id: int | None = None


    @field_validator(
        "source",
        mode="before",
    )
    @classmethod
    def normalize_source(
        cls,
        value: object,
    ) -> object:
        if not isinstance(
            value,
            str,
        ):
            return value

        return (
            value.strip()
            or "telegram_bot"
        )


# =========================================================
# GROUP MESSAGE
# =========================================================


class ClosingGroupMessage(BaseModel):
    """
    Дані повідомлення,
    яке було відправлене у Telegram-групу.
    """

    chat_id: int

    message_id: int

    topic_id: int | None = None

    sent_at: datetime


# =========================================================
# DEADLINE
# =========================================================


class ClosingDeadlineMissed(BaseModel):
    """
    Фіксація пропущеного дедлайну.
    """

    missed_at: datetime

    alert_sent: bool = True


class ClosingDeadlineAlert(BaseModel):
    """
    Фіксація окремого повідомлення
    про пропущений дедлайн.
    """

    sent_at: datetime


# =========================================================
# CASH MODIFICATION
# =========================================================


class ClosingCashUpdate(BaseModel):
    """
    Ручне виправлення суми каси.
    """

    new_cash_amount: Decimal = Field(
        ge=Decimal("0"),
        decimal_places=2,
        max_digits=14,
    )

    modified_by_id: int = Field(
        gt=0,
    )

    modified_at: datetime

    reason: str = Field(
        min_length=1,
        max_length=2000,
    )


    @field_validator(
        "new_cash_amount",
        mode="before",
    )
    @classmethod
    def normalize_cash(
        cls,
        value: object,
    ) -> object:
        if isinstance(
            value,
            str,
        ):
            return (
                value.strip()
                .replace(" ", "")
                .replace(",", ".")
            )

        return value


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
# RECEIPT REPLACEMENT
# =========================================================


class ClosingReceiptUpdate(BaseModel):
    """
    Ручна заміна фото чека.
    """

    new_file_id: str = Field(
        min_length=1,
        max_length=512,
    )

    new_file_unique_id: str | None = Field(
        default=None,
        max_length=255,
    )

    mime_type: str | None = Field(
        default=None,
        max_length=100,
    )

    file_name: str | None = Field(
        default=None,
        max_length=255,
    )

    file_size: int | None = Field(
        default=None,
        ge=0,
    )

    modified_by_id: int = Field(
        gt=0,
    )

    modified_at: datetime

    reason: str = Field(
        min_length=1,
        max_length=2000,
    )


    @field_validator(
        "new_file_id",
        mode="before",
    )
    @classmethod
    def normalize_file_id(
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
        "new_file_unique_id",
        "mime_type",
        "file_name",
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

        return (
            normalized
            or None
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
# MANUAL CONFIRM
# =========================================================


class ClosingManualConfirm(
    ClosingCash
):
    """
    Ручне підтвердження закриття
    адміністратором.
    """

    submitted_at: datetime

    modified_by_id: int = Field(
        gt=0,
    )

    modified_at: datetime

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
# READ
# =========================================================


class ClosingRead(BaseModel):
    """
    Повний ClosingReport із PostgreSQL.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    store_id: int

    business_date: date

    scheduled_close_time: time

    control_deadline: time

    actual_submitted_at: datetime | None

    status: ClosingStatus

    source: str

    cash_amount: Decimal | None

    currency: str

    has_receipt: bool

    receipt_file_id: str | None
    receipt_file_unique_id: str | None
    receipt_mime_type: str | None
    receipt_file_name: str | None
    receipt_file_size: int | None

    submitted_by_id: int | None

    telegram_chat_id: int | None
    telegram_message_id: int | None

    closing_group_chat_id: int | None
    closing_group_topic_id: int | None
    closing_group_message_id: int | None

    sent_to_group_at: datetime | None

    deadline_alert_was_sent: bool
    deadline_alert_sent_at: datetime | None

    missed_deadline_at: datetime | None

    manually_modified_by_id: int | None
    manually_modified_at: datetime | None

    modification_reason: str | None

    original_cash_amount: Decimal | None

    original_receipt_file_id: str | None

    created_at: datetime
    updated_at: datetime


# =========================================================
# DETAILS
# =========================================================


class ClosingDetails(
    ClosingRead
):
    """
    Розширена схема,
    яку зручно використовувати
    у Telegram UI та звітах.
    """

    is_submitted: bool = False

    is_waiting: bool = False

    is_late: bool = False

    missed_deadline: bool = False

    cash_amount_text: str | None = None

    actual_submitted_time_text: str | None = None

    scheduled_close_time_text: str | None = None

    control_deadline_text: str | None = None


# =========================================================
# SHORT
# =========================================================


class ClosingShort(BaseModel):
    """
    Короткий запис для списків.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    store_id: int

    business_date: date

    status: ClosingStatus

    cash_amount: Decimal | None

    actual_submitted_at: datetime | None

    has_receipt: bool


# =========================================================
# SUMMARY ITEM
# =========================================================


class ClosingSummaryItem(BaseModel):
    """
    Один рядок вечірнього підсумку.
    """

    store_id: int

    store_code: str | None = None

    store_name: str | None = None

    status: ClosingStatus

    cash_amount: Decimal | None = None

    scheduled_close_time: time | None = None

    actual_submitted_at: datetime | None = None

    has_receipt: bool = False


# =========================================================
# SUMMARY
# =========================================================


class ClosingSummary(BaseModel):
    """
    Підсумок закриттів за день.
    """

    business_date: date

    total_stores: int = Field(
        default=0,
        ge=0,
    )

    submitted_count: int = Field(
        default=0,
        ge=0,
    )

    waiting_count: int = Field(
        default=0,
        ge=0,
    )

    late_count: int = Field(
        default=0,
        ge=0,
    )

    missed_count: int = Field(
        default=0,
        ge=0,
    )

    total_cash: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0"),
    )

    items: list[
        ClosingSummaryItem
    ] = Field(
        default_factory=list,
    )


# =========================================================
# ALIASES
# =========================================================


ClosingResponse = ClosingRead
ClosingDetailResponse = ClosingDetails
ClosingListItem = ClosingShort
ClosingReportSchema = ClosingRead


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "ClosingBase",
    "ClosingCreate",

    "ClosingReceipt",
    "ClosingCash",
    "ClosingSubmit",

    "ClosingGroupMessage",

    "ClosingDeadlineMissed",
    "ClosingDeadlineAlert",

    "ClosingCashUpdate",
    "ClosingReceiptUpdate",
    "ClosingManualConfirm",

    "ClosingRead",
    "ClosingDetails",
    "ClosingShort",

    "ClosingSummaryItem",
    "ClosingSummary",

    "ClosingResponse",
    "ClosingDetailResponse",
    "ClosingListItem",
    "ClosingReportSchema",
]