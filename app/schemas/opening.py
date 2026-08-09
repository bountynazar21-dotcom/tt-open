from __future__ import annotations

from datetime import date, datetime, time

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.database.models.enums import OpeningStatus


# =========================================================
# BASE
# =========================================================


class OpeningBase(BaseModel):
    """
    Базові дані відкриття торгової точки.
    """

    store_id: int = Field(
        gt=0,
    )

    business_date: date

    scheduled_open_time: time

    control_deadline: time


# =========================================================
# CREATE
# =========================================================


class OpeningCreate(
    OpeningBase
):
    """
    Створення щоденного запису
    очікування відкриття ТТ.
    """

    status: OpeningStatus = (
        OpeningStatus.WAITING
    )

    source: str = Field(
        default="telegram_bot",
        min_length=1,
        max_length=50,
    )

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

        normalized = (
            value.strip()
        )

        return (
            normalized
            or "telegram_bot"
        )


# =========================================================
# CONFIRM OPENING
# =========================================================


class OpeningConfirm(BaseModel):
    """
    Дані фактичного підтвердження
    відкриття торгової точки.
    """

    store_id: int = Field(
        gt=0,
    )

    submitted_by_id: int = Field(
        gt=0,
    )

    actual_open_time: datetime

    telegram_chat_id: int | None = None

    telegram_message_id: int | None = Field(
        default=None,
        gt=0,
    )

    source: str = Field(
        default="telegram_bot",
        min_length=1,
        max_length=50,
    )

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

        normalized = (
            value.strip()
        )

        return (
            normalized
            or "telegram_bot"
        )


# =========================================================
# DEADLINE
# =========================================================


class OpeningDeadlineMissed(BaseModel):
    """
    Фіксація пропущеного
    контрольного дедлайну.
    """

    missed_deadline_at: datetime

    alert_was_sent: bool = False

    alert_sent_at: datetime | None = None


class OpeningAlertUpdate(BaseModel):
    """
    Фіксація надсилання alert
    про невідкриту ТТ.
    """

    alert_was_sent: bool = True

    alert_sent_at: datetime


# =========================================================
# MANUAL UPDATE
# =========================================================


class OpeningManualUpdate(BaseModel):
    """
    Ручне коригування відкриття
    адміністратором.
    """

    actual_open_time: datetime | None = None

    lateness_minutes: int | None = Field(
        default=None,
        ge=0,
    )

    status: OpeningStatus | None = None

    manually_modified_by_id: int = Field(
        gt=0,
    )

    manually_modified_at: datetime

    modification_reason: str = Field(
        min_length=1,
        max_length=2000,
    )

    @field_validator(
        "modification_reason",
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


class OpeningStatusUpdate(BaseModel):
    """
    Ручна зміна статусу opening-запису.
    """

    status: OpeningStatus

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


class OpeningRead(BaseModel):
    """
    Повна схема OpeningCheckin із PostgreSQL.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    store_id: int

    business_date: date

    scheduled_open_time: time

    control_deadline: time

    actual_open_time: datetime | None

    lateness_minutes: int

    status: OpeningStatus

    source: str

    submitted_by_id: int | None

    telegram_chat_id: int | None

    telegram_message_id: int | None

    alert_was_sent: bool

    alert_sent_at: datetime | None

    missed_deadline_at: datetime | None

    manually_modified_by_id: int | None

    manually_modified_at: datetime | None

    modification_reason: str | None

    created_at: datetime

    updated_at: datetime


# =========================================================
# SHORT
# =========================================================


class OpeningShort(BaseModel):
    """
    Коротка схема opening-запису
    для списків і Telegram UI.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    store_id: int

    business_date: date

    scheduled_open_time: time

    actual_open_time: datetime | None

    lateness_minutes: int

    status: OpeningStatus


# =========================================================
# DETAILS
# =========================================================


class OpeningDetails(
    OpeningRead
):
    """
    Розширена інформація
    для Telegram-картки.
    """

    is_opened: bool = False

    is_waiting: bool = False

    is_late: bool = False

    deadline_missed: bool = False

    scheduled_open_time_text: str | None = None

    control_deadline_text: str | None = None

    actual_open_time_text: str | None = None

    lateness_text: str | None = None


# =========================================================
# PREPARATION RESULT
# =========================================================


class OpeningPreparationResponse(BaseModel):
    """
    Результат підготовки ранкових записів.
    """

    business_date: date

    expected_stores: int = Field(
        ge=0,
    )

    created_records: int = Field(
        ge=0,
    )

    existing_records: int = Field(
        ge=0,
    )

    checkins: list[
        OpeningRead
    ] = Field(
        default_factory=list,
    )


# =========================================================
# CONFIRMATION RESULT
# =========================================================


class OpeningConfirmationResponse(BaseModel):
    """
    Результат підтвердження відкриття.
    """

    store_id: int = Field(
        gt=0,
    )

    checkin_id: int = Field(
        gt=0,
    )

    was_confirmed_now: bool

    lateness_minutes: int = Field(
        ge=0,
    )

    is_late: bool

    status: OpeningStatus


# =========================================================
# DEADLINE RESULT
# =========================================================


class OpeningDeadlineItem(BaseModel):
    """
    Одна ТТ, яка пропустила дедлайн.
    """

    checkin_id: int = Field(
        gt=0,
    )

    store_id: int = Field(
        gt=0,
    )

    status: OpeningStatus

    missed_deadline_at: datetime | None = None

    alert_was_sent: bool = False


class OpeningDeadlineResponse(BaseModel):
    """
    Підсумок обробки пропущених дедлайнів.
    """

    business_date: date

    missed_count: int = Field(
        default=0,
        ge=0,
    )

    created_notifications: int = Field(
        default=0,
        ge=0,
    )

    existing_notifications: int = Field(
        default=0,
        ge=0,
    )

    items: list[
        OpeningDeadlineItem
    ] = Field(
        default_factory=list,
    )


# =========================================================
# SUMMARY
# =========================================================


class OpeningSummaryItem(BaseModel):
    """
    Один рядок ранкового підсумку.
    """

    store_id: int = Field(
        gt=0,
    )

    store_code: str | None = None

    store_name: str | None = None

    status: OpeningStatus

    scheduled_open_time: time | None = None

    actual_open_time: datetime | None = None

    lateness_minutes: int = Field(
        default=0,
        ge=0,
    )

    alert_was_sent: bool = False


class OpeningSummary(BaseModel):
    """
    Підсумок відкриттів за день.
    """

    business_date: date

    total_stores: int = Field(
        default=0,
        ge=0,
    )

    opened_count: int = Field(
        default=0,
        ge=0,
    )

    on_time_count: int = Field(
        default=0,
        ge=0,
    )

    late_count: int = Field(
        default=0,
        ge=0,
    )

    waiting_count: int = Field(
        default=0,
        ge=0,
    )

    missed_count: int = Field(
        default=0,
        ge=0,
    )

    total_lateness_minutes: int = Field(
        default=0,
        ge=0,
    )

    items: list[
        OpeningSummaryItem
    ] = Field(
        default_factory=list,
    )


# =========================================================
# LATENESS / PENALTY
# =========================================================


class OpeningLatenessInfo(BaseModel):
    """
    Інформація про запізнення ТТ.
    """

    store_id: int = Field(
        gt=0,
    )

    lateness_minutes: int = Field(
        ge=0,
    )

    is_late: bool


# =========================================================
# ALIASES
# =========================================================


OpeningResponse = OpeningRead

OpeningDetailResponse = OpeningDetails

OpeningListItem = OpeningShort

OpeningCheckinSchema = OpeningRead


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "OpeningBase",
    "OpeningCreate",

    "OpeningConfirm",

    "OpeningDeadlineMissed",
    "OpeningAlertUpdate",

    "OpeningManualUpdate",
    "OpeningStatusUpdate",

    "OpeningRead",
    "OpeningShort",
    "OpeningDetails",

    "OpeningPreparationResponse",
    "OpeningConfirmationResponse",

    "OpeningDeadlineItem",
    "OpeningDeadlineResponse",

    "OpeningSummaryItem",
    "OpeningSummary",

    "OpeningLatenessInfo",

    "OpeningResponse",
    "OpeningDetailResponse",
    "OpeningListItem",
    "OpeningCheckinSchema",
]