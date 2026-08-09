from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.database.models.enums import (
    ScheduleExceptionType,
)


# =========================================================
# BASE
# =========================================================


class ScheduleSchemaBase(BaseModel):
    """
    Базова схема графіків.

    Підтримує створення схем
    напряму із SQLAlchemy моделей.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="ignore",
    )


# =========================================================
# WEEKDAY HELPERS
# =========================================================


WEEKDAY_NAMES: dict[int, str] = {
    0: "Понеділок",
    1: "Вівторок",
    2: "Середа",
    3: "Четвер",
    4: "П’ятниця",
    5: "Субота",
    6: "Неділя",
}


def weekday_name(
    weekday: int,
) -> str:
    """
    Назва дня тижня українською.
    """

    if weekday not in WEEKDAY_NAMES:
        raise ValueError(
            "weekday повинен бути "
            "від 0 до 6."
        )

    return WEEKDAY_NAMES[
        weekday
    ]


# =========================================================
# STORE WEEKDAY SCHEDULE BASE
# =========================================================


class StoreScheduleBase(
    ScheduleSchemaBase
):
    """
    Постійний графік ТТ
    на один день тижня.

    weekday:

    0 — понеділок
    1 — вівторок
    2 — середа
    3 — четвер
    4 — п’ятниця
    5 — субота
    6 — неділя
    """

    store_id: int = Field(
        gt=0,
    )

    weekday: int = Field(
        ge=0,
        le=6,
    )

    opening_time: time | None = None

    opening_control_deadline: (
        time | None
    ) = None

    closing_time: time | None = None

    closing_control_deadline: (
        time | None
    ) = None

    is_working_day: bool = True

    note: str | None = Field(
        default=None,
        max_length=500,
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

    @model_validator(
        mode="after",
    )
    def validate_schedule(
        self,
    ) -> StoreScheduleBase:
        """
        Перевіряє логіку часу.
        """

        if not self.is_working_day:
            return self

        if self.opening_time is None:
            raise ValueError(
                "Для робочого дня потрібно "
                "вказати opening_time."
            )

        if (
            self.opening_control_deadline
            is None
        ):
            raise ValueError(
                "Для робочого дня потрібно "
                "вказати opening_control_deadline."
            )

        if (
            self.opening_control_deadline
            < self.opening_time
        ):
            raise ValueError(
                "Дедлайн відкриття не може "
                "бути раніше часу відкриття."
            )

        if (
            self.closing_time is not None
            and self.closing_control_deadline
            is None
        ):
            raise ValueError(
                "Якщо задано closing_time, "
                "потрібно вказати "
                "closing_control_deadline."
            )

        if (
            self.closing_time is not None
            and self.closing_control_deadline
            is not None
            and self.closing_control_deadline
            < self.closing_time
        ):
            raise ValueError(
                "Дедлайн закриття не може "
                "бути раніше часу закриття."
            )

        return self


# =========================================================
# STORE WEEKDAY CREATE
# =========================================================


class StoreScheduleCreate(
    StoreScheduleBase
):
    """
    Створення постійного
    графіка одного дня.
    """

    pass


# =========================================================
# STORE WEEKDAY UPDATE
# =========================================================


class StoreScheduleUpdate(
    ScheduleSchemaBase
):
    """
    Часткове оновлення
    графіка одного дня.
    """

    weekday: int | None = Field(
        default=None,
        ge=0,
        le=6,
    )

    opening_time: time | None = None

    opening_control_deadline: (
        time | None
    ) = None

    closing_time: time | None = None

    closing_control_deadline: (
        time | None
    ) = None

    is_working_day: bool | None = None

    note: str | None = Field(
        default=None,
        max_length=500,
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
# SET WORKING DAY
# =========================================================


class StoreWorkingDaySet(
    ScheduleSchemaBase
):
    """
    Встановлення робочого дня.
    """

    store_id: int = Field(
        gt=0,
    )

    weekday: int = Field(
        ge=0,
        le=6,
    )

    opening_time: time

    opening_control_deadline: time

    closing_time: time | None = None

    closing_control_deadline: (
        time | None
    ) = None

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

    @model_validator(
        mode="after",
    )
    def validate_times(
        self,
    ) -> StoreWorkingDaySet:
        if (
            self.opening_control_deadline
            < self.opening_time
        ):
            raise ValueError(
                "Дедлайн відкриття не може "
                "бути раніше часу відкриття."
            )

        if (
            self.closing_time is not None
            and self.closing_control_deadline
            is None
        ):
            raise ValueError(
                "Для closing_time потрібно "
                "вказати closing_control_deadline."
            )

        if (
            self.closing_time is not None
            and self.closing_control_deadline
            is not None
            and self.closing_control_deadline
            < self.closing_time
        ):
            raise ValueError(
                "Дедлайн закриття не може "
                "бути раніше часу закриття."
            )

        return self


# =========================================================
# SET DAY OFF
# =========================================================


class StoreDayOffSet(
    ScheduleSchemaBase
):
    """
    Постійний вихідний день ТТ.
    """

    store_id: int = Field(
        gt=0,
    )

    weekday: int = Field(
        ge=0,
        le=6,
    )

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
# COPY WEEKDAY
# =========================================================


class StoreScheduleCopy(
    ScheduleSchemaBase
):
    """
    Копіювання графіка одного дня
    на інші дні тижня.
    """

    store_id: int = Field(
        gt=0,
    )

    source_weekday: int = Field(
        ge=0,
        le=6,
    )

    target_weekdays: set[int] = Field(
        min_length=1,
    )

    reason: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "target_weekdays",
    )
    @classmethod
    def validate_target_weekdays(
        cls,
        value: set[int],
    ) -> set[int]:
        invalid = [
            item
            for item in value
            if item < 0 or item > 6
        ]

        if invalid:
            raise ValueError(
                "Усі target_weekdays повинні "
                "бути від 0 до 6."
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
# WEEKLY DEFAULT
# =========================================================


class WeeklyScheduleCreate(
    ScheduleSchemaBase
):
    """
    Створення або перезапис
    повного тижневого графіка ТТ.
    """

    store_id: int = Field(
        gt=0,
    )

    opening_time: time

    opening_control_deadline: time

    closing_time: time | None = None

    closing_control_deadline: (
        time | None
    ) = None

    working_weekdays: set[int] = Field(
        default_factory=lambda: {
            0,
            1,
            2,
            3,
            4,
            5,
            6,
        }
    )

    reason: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator(
        "working_weekdays",
    )
    @classmethod
    def validate_weekdays(
        cls,
        value: set[int],
    ) -> set[int]:
        invalid = [
            item
            for item in value
            if item < 0 or item > 6
        ]

        if invalid:
            raise ValueError(
                "working_weekdays повинні "
                "бути від 0 до 6."
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
# STORE SCHEDULE READ
# =========================================================


class StoreScheduleRead(
    StoreScheduleBase
):
    """
    StoreSchedule із PostgreSQL.
    """

    id: int

    created_at: datetime
    updated_at: datetime

    @property
    def weekday_name(
        self,
    ) -> str:
        return WEEKDAY_NAMES[
            self.weekday
        ]

    @property
    def opening_time_text(
        self,
    ) -> str | None:
        if self.opening_time is None:
            return None

        return self.opening_time.strftime(
            "%H:%M"
        )

    @property
    def closing_time_text(
        self,
    ) -> str | None:
        if self.closing_time is None:
            return None

        return self.closing_time.strftime(
            "%H:%M"
        )


# =========================================================
# WEEKLY SCHEDULE
# =========================================================


class WeeklySchedule(
    ScheduleSchemaBase
):
    """
    Повний тижневий графік ТТ.
    """

    store_id: int = Field(
        gt=0,
    )

    days: list[
        StoreScheduleRead
    ] = Field(
        default_factory=list,
    )


# =========================================================
# EXCEPTION BASE
# =========================================================


class ScheduleExceptionBase(
    ScheduleSchemaBase
):
    """
    Виняток у графіку
    на конкретну дату.

    Якщо store_id=None і bush_id=None —
    виняток діє на всю мережу.
    """

    store_id: int | None = Field(
        default=None,
        gt=0,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    exception_date: date

    exception_type: ScheduleExceptionType

    opening_time: time | None = None

    opening_control_deadline: (
        time | None
    ) = None

    closing_time: time | None = None

    closing_control_deadline: (
        time | None
    ) = None

    reason: str | None = Field(
        default=None,
        max_length=500,
    )

    is_active: bool = True

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

    @model_validator(
        mode="after",
    )
    def validate_target_and_times(
        self,
    ) -> ScheduleExceptionBase:
        if (
            self.store_id is not None
            and self.bush_id is not None
        ):
            raise ValueError(
                "ScheduleException не може "
                "одночасно належати ТТ і кущу."
            )

        if (
            self.exception_type
            == ScheduleExceptionType.CUSTOM_SCHEDULE
        ):
            if self.opening_time is None:
                raise ValueError(
                    "Для CUSTOM_SCHEDULE потрібно "
                    "вказати opening_time."
                )

            if (
                self.opening_control_deadline
                is None
            ):
                raise ValueError(
                    "Для CUSTOM_SCHEDULE потрібно "
                    "вказати opening_control_deadline."
                )

            if (
                self.opening_control_deadline
                < self.opening_time
            ):
                raise ValueError(
                    "Дедлайн відкриття не може "
                    "бути раніше часу відкриття."
                )

            if (
                self.closing_time is not None
                and self.closing_control_deadline
                is None
            ):
                raise ValueError(
                    "Для closing_time потрібно "
                    "вказати closing_control_deadline."
                )

            if (
                self.closing_time is not None
                and self.closing_control_deadline
                is not None
                and self.closing_control_deadline
                < self.closing_time
            ):
                raise ValueError(
                    "Дедлайн закриття не може "
                    "бути раніше часу закриття."
                )

        return self


# =========================================================
# EXCEPTION CREATE
# =========================================================


class ScheduleExceptionCreate(
    ScheduleExceptionBase
):
    """
    Створення винятку.
    """

    created_by_id: int | None = Field(
        default=None,
        gt=0,
    )


# =========================================================
# EXCEPTION UPDATE
# =========================================================


class ScheduleExceptionUpdate(
    ScheduleSchemaBase
):
    """
    Часткове оновлення винятку.
    """

    exception_type: (
        ScheduleExceptionType | None
    ) = None

    opening_time: time | None = None

    opening_control_deadline: (
        time | None
    ) = None

    closing_time: time | None = None

    closing_control_deadline: (
        time | None
    ) = None

    reason: str | None = Field(
        default=None,
        max_length=500,
    )

    is_active: bool | None = None

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
# EXCEPTION READ
# =========================================================


class ScheduleExceptionRead(
    ScheduleExceptionBase
):
    """
    ScheduleException із PostgreSQL.
    """

    id: int

    created_by_id: int | None = Field(
        default=None,
        gt=0,
    )

    created_at: datetime
    updated_at: datetime

    @property
    def applies_to_network(
        self,
    ) -> bool:
        return (
            self.store_id is None
            and self.bush_id is None
        )

    @property
    def is_day_off(
        self,
    ) -> bool:
        return self.exception_type in {
            ScheduleExceptionType.DAY_OFF,
            ScheduleExceptionType.HOLIDAY,
            ScheduleExceptionType.REPAIR,
            ScheduleExceptionType.TEMPORARILY_CLOSED,
        }


# =========================================================
# EXCEPTION DEACTIVATE
# =========================================================


class ScheduleExceptionStateUpdate(
    ScheduleSchemaBase
):
    """
    Активація або деактивація винятку.
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

        return normalized or None


# =========================================================
# EFFECTIVE SCHEDULE
# =========================================================


class EffectiveScheduleSchema(
    ScheduleSchemaBase
):
    """
    Фактичний графік ТТ
    на конкретну бізнес-дату.

    Він уже враховує:

    - виняток ТТ;
    - виняток куща;
    - виняток мережі;
    - тижневий графік;
    - кластер.
    """

    business_date: date | None = None

    is_working_day: bool

    opening_time: time | None = None

    opening_control_deadline: (
        time | None
    ) = None

    closing_time: time | None = None

    closing_control_deadline: (
        time | None
    ) = None

    source: str | None = None

    exception_type: (
        ScheduleExceptionType | None
    ) = None

    exception_id: int | None = Field(
        default=None,
        gt=0,
    )


# =========================================================
# PREVIEW
# =========================================================


class SchedulePreviewItemSchema(
    ScheduleSchemaBase
):
    """
    Один день календарного preview.
    """

    business_date: date

    weekday: int = Field(
        ge=0,
        le=6,
    )

    weekday_name: str

    schedule: EffectiveScheduleSchema


class SchedulePreviewSchema(
    ScheduleSchemaBase
):
    """
    Preview фактичного графіка
    за період.
    """

    store_id: int = Field(
        gt=0,
    )

    date_from: date

    date_to: date

    items: list[
        SchedulePreviewItemSchema
    ] = Field(
        default_factory=list,
    )

    @model_validator(
        mode="after",
    )
    def validate_dates(
        self,
    ) -> SchedulePreviewSchema:
        if self.date_to < self.date_from:
            raise ValueError(
                "date_to не може бути "
                "раніше date_from."
            )

        return self


# =========================================================
# CHANGE RESULT
# =========================================================


class WeekdayScheduleChangeSchema(
    ScheduleSchemaBase
):
    """
    Результат зміни одного дня.
    """

    store_id: int = Field(
        gt=0,
    )

    schedule: StoreScheduleRead

    was_created: bool

    previous_values: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict,
    )

    current_values: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict,
    )


class ScheduleExceptionChangeSchema(
    ScheduleSchemaBase
):
    """
    Результат зміни винятку.
    """

    exception: ScheduleExceptionRead

    store_id: int | None = Field(
        default=None,
        gt=0,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    was_created: bool

    previous_values: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict,
    )

    current_values: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict,
    )


class ScheduleDeletionSchema(
    ScheduleSchemaBase
):
    """
    Результат видалення
    графіка або винятку.
    """

    deleted: bool

    entity_id: int | None = Field(
        default=None,
        gt=0,
    )

    entity_type: str

    previous_values: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict,
    )


# =========================================================
# CLUSTER ASSIGNMENT
# =========================================================


class ClusterAssignmentSchema(
    ScheduleSchemaBase
):
    """
    Результат зміни кластера ТТ.
    """

    store_id: int = Field(
        gt=0,
    )

    previous_cluster_id: int | None = Field(
        default=None,
        gt=0,
    )

    current_cluster_id: int | None = Field(
        default=None,
        gt=0,
    )

    was_changed: bool


# =========================================================
# ALIASES
# =========================================================


StoreScheduleSchema = (
    StoreScheduleRead
)

ScheduleExceptionSchema = (
    ScheduleExceptionRead
)

EffectiveSchedule = (
    EffectiveScheduleSchema
)

SchedulePreviewItem = (
    SchedulePreviewItemSchema
)

WeekdayScheduleChangeResultSchema = (
    WeekdayScheduleChangeSchema
)

ScheduleExceptionChangeResultSchema = (
    ScheduleExceptionChangeSchema
)

ScheduleDeletionResultSchema = (
    ScheduleDeletionSchema
)

ClusterAssignmentResultSchema = (
    ClusterAssignmentSchema
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "WEEKDAY_NAMES",
    "weekday_name",

    "ScheduleSchemaBase",

    "StoreScheduleBase",
    "StoreScheduleCreate",
    "StoreScheduleUpdate",
    "StoreWorkingDaySet",
    "StoreDayOffSet",
    "StoreScheduleCopy",
    "WeeklyScheduleCreate",
    "StoreScheduleRead",
    "WeeklySchedule",

    "ScheduleExceptionBase",
    "ScheduleExceptionCreate",
    "ScheduleExceptionUpdate",
    "ScheduleExceptionRead",
    "ScheduleExceptionStateUpdate",

    "EffectiveScheduleSchema",

    "SchedulePreviewItemSchema",
    "SchedulePreviewSchema",

    "WeekdayScheduleChangeSchema",
    "ScheduleExceptionChangeSchema",
    "ScheduleDeletionSchema",
    "ClusterAssignmentSchema",

    "StoreScheduleSchema",
    "ScheduleExceptionSchema",
    "EffectiveSchedule",
    "SchedulePreviewItem",

    "WeekdayScheduleChangeResultSchema",
    "ScheduleExceptionChangeResultSchema",
    "ScheduleDeletionResultSchema",
    "ClusterAssignmentResultSchema",
]