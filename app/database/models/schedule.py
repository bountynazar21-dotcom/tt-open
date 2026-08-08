from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import (
    Base,
    IntegerPrimaryKeyMixin,
    TimestampMixin,
)
from app.database.models.enums import ScheduleExceptionType


if TYPE_CHECKING:
    from app.database.models.bush import Bush
    from app.database.models.store import Store
    from app.database.models.user import User


class StoreSchedule(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Постійний тижневий графік торгової точки.

    Для кожної ТТ може бути максимум один запис
    на кожен день тижня.

    weekday:
    0 — понеділок;
    1 — вівторок;
    2 — середа;
    3 — четвер;
    4 — п’ятниця;
    5 — субота;
    6 — неділя.
    """

    __tablename__ = "store_schedules"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "weekday",
            name="uq_store_schedules_store_weekday",
        ),
        CheckConstraint(
            "weekday >= 0 AND weekday <= 6",
            name="weekday_range",
        ),
        Index(
            "ix_store_schedules_store_working",
            "store_id",
            "is_working_day",
        ),
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    weekday: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="День тижня від 0 до 6",
    )

    opening_time: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
        comment="Плановий час відкриття",
    )

    opening_control_deadline: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
        comment="Контрольний дедлайн відкриття",
    )

    closing_time: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
        comment="Плановий час закриття",
    )

    closing_control_deadline: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
        comment="Дедлайн вечірнього звіту",
    )

    is_working_day: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
    )

    note: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    store: Mapped[Store] = relationship(
        "Store",
        back_populates="schedules",
        lazy="joined",
    )

    @property
    def weekday_name(self) -> str:
        """Назва дня тижня українською."""

        names = {
            0: "Понеділок",
            1: "Вівторок",
            2: "Середа",
            3: "Четвер",
            4: "П’ятниця",
            5: "Субота",
            6: "Неділя",
        }

        return names[self.weekday]

    @property
    def opening_time_text(self) -> str | None:
        if self.opening_time is None:
            return None

        return self.opening_time.strftime("%H:%M")

    @property
    def closing_time_text(self) -> str | None:
        if self.closing_time is None:
            return None

        return self.closing_time.strftime("%H:%M")

    def set_working_day(
        self,
        *,
        opening_time: time,
        opening_control_deadline: time,
        closing_time: time,
        closing_control_deadline: time,
    ) -> None:
        """Встановлює повний робочий графік на день."""

        self.validate_schedule(
            opening_time=opening_time,
            opening_control_deadline=opening_control_deadline,
            closing_time=closing_time,
            closing_control_deadline=closing_control_deadline,
        )

        self.is_working_day = True

        self.opening_time = opening_time
        self.opening_control_deadline = opening_control_deadline

        self.closing_time = closing_time
        self.closing_control_deadline = closing_control_deadline

    def set_day_off(
        self,
        note: str | None = None,
    ) -> None:
        """Позначає день як вихідний."""

        self.is_working_day = False

        self.opening_time = None
        self.opening_control_deadline = None

        self.closing_time = None
        self.closing_control_deadline = None

        self.note = note.strip() if note else None

    @staticmethod
    def validate_schedule(
        *,
        opening_time: time,
        opening_control_deadline: time,
        closing_time: time,
        closing_control_deadline: time,
    ) -> None:
        """Перевіряє правильність часу."""

        if opening_control_deadline < opening_time:
            raise ValueError(
                "Дедлайн відкриття не може бути раніше "
                "планового часу відкриття."
            )

        if closing_control_deadline < closing_time:
            raise ValueError(
                "Дедлайн закриття не може бути раніше "
                "планового часу закриття."
            )


class ScheduleException(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Виняток у графіку на конкретну дату.

    Може застосовуватися:

    1. До однієї торгової точки.
    2. До всього куща.
    3. До всієї мережі.

    Пріоритет:

    виняток ТТ > виняток куща > виняток мережі >
    тижневий графік > стандартний графік кластера.
    """

    __tablename__ = "schedule_exceptions"

    __table_args__ = (
        CheckConstraint(
            "NOT (store_id IS NOT NULL AND bush_id IS NOT NULL)",
            name="single_exception_target",
        ),
        Index(
            "ix_schedule_exceptions_date_store",
            "exception_date",
            "store_id",
        ),
        Index(
            "ix_schedule_exceptions_date_bush",
            "exception_date",
            "bush_id",
        ),
        Index(
            "ix_schedule_exceptions_active_date",
            "is_active",
            "exception_date",
        ),
    )

    store_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
        comment="Конкретна ТТ або NULL",
    )

    bush_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "bushes.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
        comment="Конкретний кущ або NULL",
    )

    exception_date: Mapped[date] = mapped_column(
        nullable=False,
        index=True,
        comment="Дата спеціального графіка",
    )

    exception_type: Mapped[ScheduleExceptionType] = mapped_column(
        Enum(
            ScheduleExceptionType,
            name="schedule_exception_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        index=True,
    )

    opening_time: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
    )

    opening_control_deadline: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
    )

    closing_time: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
    )

    closing_control_deadline: Mapped[time | None] = mapped_column(
        Time(timezone=False),
        nullable=True,
    )

    reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
    )

    store: Mapped[Store | None] = relationship(
        "Store",
        back_populates="schedule_exceptions",
        lazy="joined",
    )

    bush: Mapped[Bush | None] = relationship(
        "Bush",
        back_populates="schedule_exceptions",
        lazy="joined",
    )

    created_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[created_by_id],
        lazy="joined",
    )

    @property
    def applies_to_network(self) -> bool:
        """Чи поширюється виняток на всю мережу."""

        return (
            self.store_id is None
            and self.bush_id is None
        )

    @property
    def is_day_off(self) -> bool:
        """Чи означає виняток повний вихідний."""

        return self.exception_type in {
            ScheduleExceptionType.DAY_OFF,
            ScheduleExceptionType.HOLIDAY,
            ScheduleExceptionType.REPAIR,
            ScheduleExceptionType.TEMPORARILY_CLOSED,
        }

    @property
    def target_name(self) -> str:
        """Назва області застосування винятку."""

        if self.store is not None:
            return self.store.code

        if self.bush is not None:
            return self.bush.name

        return "Уся мережа"

    def deactivate(self) -> None:
        """Вимикає виняток без фізичного видалення."""

        self.is_active = False

    def activate(self) -> None:
        """Повторно вмикає виняток."""

        self.is_active = True

    def set_custom_schedule(
        self,
        *,
        opening_time: time,
        opening_control_deadline: time,
        closing_time: time,
        closing_control_deadline: time,
    ) -> None:
        """Встановлює спеціальний графік на конкретну дату."""

        StoreSchedule.validate_schedule(
            opening_time=opening_time,
            opening_control_deadline=opening_control_deadline,
            closing_time=closing_time,
            closing_control_deadline=closing_control_deadline,
        )

        self.exception_type = (
            ScheduleExceptionType.CUSTOM_SCHEDULE
        )

        self.opening_time = opening_time
        self.opening_control_deadline = (
            opening_control_deadline
        )

        self.closing_time = closing_time
        self.closing_control_deadline = (
            closing_control_deadline
        )

    def clear_custom_times(self) -> None:
        """Очищає спеціально встановлений час."""

        self.opening_time = None
        self.opening_control_deadline = None

        self.closing_time = None
        self.closing_control_deadline = None