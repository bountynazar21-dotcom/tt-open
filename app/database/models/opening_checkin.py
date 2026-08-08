from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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
from app.database.models.enums import OpeningStatus


if TYPE_CHECKING:
    from app.database.models.store import Store
    from app.database.models.user import User


class OpeningCheckin(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Щоденний запис відкриття торгової точки.

    Для однієї торгової точки дозволений лише один
    запис відкриття на одну бізнес-дату.

    Бізнес-дата визначається за часовим поясом
    торгової точки, а всі datetime зберігаються
    у базі з часовим поясом.
    """

    __tablename__ = "opening_checkins"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "business_date",
            name="uq_opening_checkins_store_date",
        ),
        CheckConstraint(
            "lateness_minutes >= 0",
            name="lateness_minutes_non_negative",
        ),
        Index(
            "ix_opening_checkins_date_status",
            "business_date",
            "status",
        ),
        Index(
            "ix_opening_checkins_store_status",
            "store_id",
            "status",
        ),
        Index(
            "ix_opening_checkins_date_lateness",
            "business_date",
            "lateness_minutes",
        ),
        Index(
            "ix_opening_checkins_alert_status",
            "alert_was_sent",
            "status",
        ),
    )

    # ==========================================
    # ТОРГОВА ТОЧКА І ДАТА
    # ==========================================

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
        comment="Торгова точка, яка відкривається",
    )

    business_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Робоча дата у часовому поясі ТТ",
    )

    # ==========================================
    # ПЛАНОВИЙ ГРАФІК
    # ==========================================

    scheduled_open_time: Mapped[time] = mapped_column(
        Time(timezone=False),
        nullable=False,
        comment="Плановий локальний час відкриття",
    )

    control_deadline: Mapped[time] = mapped_column(
        Time(timezone=False),
        nullable=False,
        comment="Локальний контрольний дедлайн",
    )

    # ==========================================
    # ФАКТИЧНЕ ВІДКРИТТЯ
    # ==========================================

    actual_open_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Фактичний серверний час відкриття",
    )

    lateness_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        index=True,
        comment="Кількість хвилин запізнення",
    )

    status: Mapped[OpeningStatus] = mapped_column(
        Enum(
            OpeningStatus,
            name="opening_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        default=OpeningStatus.WAITING,
        server_default=OpeningStatus.WAITING.value,
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="telegram_bot",
        server_default="telegram_bot",
        comment="Джерело чекіну",
    )

    # ==========================================
    # ХТО ВІДКРИВ ТТ
    # ==========================================

    submitted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Користувач, який підтвердив відкриття",
    )

    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram chat ID, звідки виконано чекін",
    )

    telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram message ID підтвердження",
    )

    # ==========================================
    # СПОВІЩЕННЯ ПРО НЕВІДКРИТУ ТТ
    # ==========================================

    alert_was_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        index=True,
        comment="Чи було надіслано сповіщення про невідкриття",
    )

    alert_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Час надсилання сповіщення",
    )

    missed_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Час фіксації пропущеного дедлайну",
    )

    # ==========================================
    # РУЧНЕ КОРИГУВАННЯ
    # ==========================================

    manually_modified_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Адміністратор, який змінив запис",
    )

    manually_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    modification_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Причина ручного коригування",
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    store: Mapped[Store] = relationship(
        "Store",
        back_populates="opening_checkins",
        lazy="joined",
    )

    submitted_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[submitted_by_id],
        back_populates="opening_checkins",
        lazy="joined",
    )

    manually_modified_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[manually_modified_by_id],
        lazy="joined",
    )

    # ==========================================
    # СТВОРЕННЯ ЗАПИСУ
    # ==========================================

    @classmethod
    def create_waiting(
        cls,
        *,
        store_id: int,
        business_date: date,
        scheduled_open_time: time,
        control_deadline: time,
    ) -> OpeningCheckin:
        """
        Створює запис очікування відкриття.

        Такий запис може створювати scheduler
        перед початком робочого дня.
        """

        if control_deadline < scheduled_open_time:
            raise ValueError(
                "Контрольний дедлайн не може бути "
                "раніше часу відкриття."
            )

        return cls(
            store_id=store_id,
            business_date=business_date,
            scheduled_open_time=scheduled_open_time,
            control_deadline=control_deadline,
            status=OpeningStatus.WAITING,
            lateness_minutes=0,
            alert_was_sent=False,
        )

    # ==========================================
    # РОЗРАХУНОК ЧАСУ
    # ==========================================

    @staticmethod
    def normalize_to_minute(
        value: datetime,
    ) -> datetime:
        """
        Прибирає секунди та мікросекунди.

        Наприклад:
        08:00:45 вважається 08:00,
        а 08:01:00 — уже 08:01.
        """

        return value.replace(
            second=0,
            microsecond=0,
        )

    @classmethod
    def calculate_lateness_minutes(
        cls,
        *,
        actual_open_time: datetime,
        scheduled_open_datetime: datetime,
    ) -> int:
        """
        Розраховує кількість повних хвилин запізнення.

        Результат не може бути від’ємним.
        """

        actual = cls.normalize_to_minute(
            actual_open_time
        )

        scheduled = cls.normalize_to_minute(
            scheduled_open_datetime
        )

        difference_seconds = (
            actual - scheduled
        ).total_seconds()

        if difference_seconds <= 0:
            return 0

        return int(difference_seconds // 60)

    @classmethod
    def determine_status(
        cls,
        *,
        actual_open_time: datetime,
        scheduled_open_datetime: datetime,
        control_deadline_datetime: datetime,
        alert_was_sent: bool,
    ) -> OpeningStatus:
        """Визначає статус фактичного відкриття."""

        actual = cls.normalize_to_minute(
            actual_open_time
        )

        scheduled = cls.normalize_to_minute(
            scheduled_open_datetime
        )

        control_deadline = cls.normalize_to_minute(
            control_deadline_datetime
        )

        if actual < scheduled:
            return OpeningStatus.OPENED_EARLY

        if actual == scheduled:
            return OpeningStatus.OPENED_ON_TIME

        if (
            alert_was_sent
            or actual > control_deadline
        ):
            return OpeningStatus.OPENED_AFTER_ALERT

        return OpeningStatus.OPENED_LATE

    # ==========================================
    # ПІДТВЕРДЖЕННЯ ВІДКРИТТЯ
    # ==========================================

    def confirm_opening(
        self,
        *,
        actual_open_time: datetime,
        scheduled_open_datetime: datetime,
        control_deadline_datetime: datetime,
        submitted_by_id: int,
        source: str = "telegram_bot",
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
    ) -> None:
        """
        Підтверджує відкриття торгової точки.

        Повторне підтвердження не дозволяється.
        """

        if self.actual_open_time is not None:
            raise ValueError(
                "Торгову точку вже відкрито сьогодні."
            )

        self.actual_open_time = actual_open_time

        self.lateness_minutes = (
            self.calculate_lateness_minutes(
                actual_open_time=actual_open_time,
                scheduled_open_datetime=(
                    scheduled_open_datetime
                ),
            )
        )

        self.status = self.determine_status(
            actual_open_time=actual_open_time,
            scheduled_open_datetime=(
                scheduled_open_datetime
            ),
            control_deadline_datetime=(
                control_deadline_datetime
            ),
            alert_was_sent=self.alert_was_sent,
        )

        self.submitted_by_id = submitted_by_id
        self.source = source

        self.telegram_chat_id = telegram_chat_id
        self.telegram_message_id = telegram_message_id

    # ==========================================
    # ПРОПУЩЕНИЙ ДЕДЛАЙН
    # ==========================================

    def mark_deadline_missed(
        self,
        *,
        missed_at: datetime,
        alert_sent: bool = True,
    ) -> None:
        """
        Позначає ТТ як таку, що не відкрилася
        до контрольного дедлайну.
        """

        if self.actual_open_time is not None:
            return

        self.status = (
            OpeningStatus.MISSED_CONTROL_DEADLINE
        )

        self.missed_deadline_at = missed_at

        if alert_sent:
            self.alert_was_sent = True
            self.alert_sent_at = missed_at

    def mark_alert_sent(
        self,
        *,
        sent_at: datetime,
    ) -> None:
        """Фіксує надсилання сповіщення."""

        self.alert_was_sent = True
        self.alert_sent_at = sent_at

    # ==========================================
    # РУЧНЕ ПІДТВЕРДЖЕННЯ
    # ==========================================

    def manually_confirm(
        self,
        *,
        actual_open_time: datetime,
        scheduled_open_datetime: datetime,
        modified_by_id: int,
        modified_at: datetime,
        reason: str,
    ) -> None:
        """
        Ручне підтвердження відкриття адміністратором.
        """

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError(
                "Для ручного підтвердження "
                "потрібно вказати причину."
            )

        self.actual_open_time = actual_open_time

        self.lateness_minutes = (
            self.calculate_lateness_minutes(
                actual_open_time=actual_open_time,
                scheduled_open_datetime=(
                    scheduled_open_datetime
                ),
            )
        )

        self.status = (
            OpeningStatus.MANUALLY_CONFIRMED
        )

        self.manually_modified_by_id = (
            modified_by_id
        )

        self.manually_modified_at = modified_at
        self.modification_reason = normalized_reason

        self.source = "manual_admin"

    def modify_opening_time(
        self,
        *,
        new_actual_open_time: datetime,
        scheduled_open_datetime: datetime,
        control_deadline_datetime: datetime,
        modified_by_id: int,
        modified_at: datetime,
        reason: str,
    ) -> None:
        """Змінює помилково зафіксований час відкриття."""

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError(
                "Потрібно вказати причину зміни часу."
            )

        self.actual_open_time = new_actual_open_time

        self.lateness_minutes = (
            self.calculate_lateness_minutes(
                actual_open_time=new_actual_open_time,
                scheduled_open_datetime=(
                    scheduled_open_datetime
                ),
            )
        )

        self.status = self.determine_status(
            actual_open_time=new_actual_open_time,
            scheduled_open_datetime=(
                scheduled_open_datetime
            ),
            control_deadline_datetime=(
                control_deadline_datetime
            ),
            alert_was_sent=self.alert_was_sent,
        )

        self.manually_modified_by_id = (
            modified_by_id
        )

        self.manually_modified_at = modified_at
        self.modification_reason = normalized_reason

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def is_opened(self) -> bool:
        """Чи підтверджено відкриття."""

        return self.actual_open_time is not None

    @property
    def is_waiting(self) -> bool:
        return self.status == OpeningStatus.WAITING

    @property
    def is_late(self) -> bool:
        return self.status in {
            OpeningStatus.OPENED_LATE,
            OpeningStatus.OPENED_AFTER_ALERT,
        }

    @property
    def missed_deadline(self) -> bool:
        return (
            self.status
            == OpeningStatus.MISSED_CONTROL_DEADLINE
        )

    @property
    def actual_open_time_text(self) -> str | None:
        """Фактичний час у форматі 08:03."""

        if self.actual_open_time is None:
            return None

        return self.actual_open_time.strftime("%H:%M")

    @property
    def scheduled_open_time_text(self) -> str:
        return self.scheduled_open_time.strftime(
            "%H:%M"
        )

    @property
    def control_deadline_text(self) -> str:
        return self.control_deadline.strftime(
            "%H:%M"
        )

    @property
    def lateness_text(self) -> str:
        """Текст запізнення для Telegram-повідомлення."""

        if self.lateness_minutes <= 0:
            return "Без запізнення"

        return (
            f"Запізнення: "
            f"{self.lateness_minutes} хв."
        )