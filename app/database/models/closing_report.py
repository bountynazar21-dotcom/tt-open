from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
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
    Numeric,
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
from app.database.models.enums import ClosingStatus


if TYPE_CHECKING:
    from app.database.models.store import Store
    from app.database.models.user import User


class ClosingReport(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Щоденний звіт про закриття торгової точки.

    Для однієї торгової точки дозволений лише один
    фінальний звіт за одну бізнес-дату.

    Звіт містить:
    - фото касового чека;
    - суму каси;
    - час подання;
    - статус запізнення;
    - Telegram-повідомлення у загальній групі.
    """

    __tablename__ = "closing_reports"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "business_date",
            name="uq_closing_reports_store_date",
        ),
        CheckConstraint(
            "cash_amount IS NULL OR cash_amount >= 0",
            name="cash_amount_non_negative",
        ),
        Index(
            "ix_closing_reports_date_status",
            "business_date",
            "status",
        ),
        Index(
            "ix_closing_reports_store_status",
            "store_id",
            "status",
        ),
        Index(
            "ix_closing_reports_date_cash",
            "business_date",
            "cash_amount",
        ),
        Index(
            "ix_closing_reports_receipt_status",
            "has_receipt",
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
        comment="Торгова точка, яка подає звіт",
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

    scheduled_close_time: Mapped[time] = mapped_column(
        Time(timezone=False),
        nullable=False,
        comment="Плановий локальний час закриття",
    )

    control_deadline: Mapped[time] = mapped_column(
        Time(timezone=False),
        nullable=False,
        comment="Контрольний дедлайн подання звіту",
    )

    # ==========================================
    # ФАКТИЧНЕ ПОДАННЯ
    # ==========================================

    actual_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Фактичний серверний час подання звіту",
    )

    status: Mapped[ClosingStatus] = mapped_column(
        Enum(
            ClosingStatus,
            name="closing_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        default=ClosingStatus.WAITING,
        server_default=ClosingStatus.WAITING.value,
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="telegram_bot",
        server_default="telegram_bot",
        comment="Джерело подання звіту",
    )

    # ==========================================
    # КАСА
    # ==========================================

    cash_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(
            precision=14,
            scale=2,
        ),
        nullable=True,
        index=True,
        comment="Сума каси за день",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="UAH",
        server_default="UAH",
        comment="Валюта касового звіту",
    )

    # ==========================================
    # ФОТО ЧЕКА
    # ==========================================

    has_receipt: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        index=True,
    )

    receipt_file_id: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Telegram file_id фотографії чека",
    )

    receipt_file_unique_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Telegram file_unique_id фотографії",
    )

    receipt_mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="MIME-тип завантаженого файла",
    )

    receipt_file_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Назва файла, якщо фото надіслано документом",
    )

    receipt_file_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Розмір фотографії у байтах",
    )

    # ==========================================
    # ХТО ПОДАВ ЗВІТ
    # ==========================================

    submitted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Користувач, який подав звіт",
    )

    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Чат, у якому користувач подав звіт",
    )

    telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID повідомлення користувача",
    )

    # ==========================================
    # ПОВІДОМЛЕННЯ У ГРУПІ
    # ==========================================

    closing_group_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID Telegram-групи закриттів",
    )

    closing_group_topic_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID теми у Telegram-групі",
    )

    closing_group_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID повідомлення з фото у групі",
    )

    sent_to_group_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Час надсилання звіту у групу",
    )

    # ==========================================
    # ПРОПУЩЕНИЙ ДЕДЛАЙН
    # ==========================================

    deadline_alert_was_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        index=True,
    )

    deadline_alert_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    missed_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
    )

    manually_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    modification_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    original_cash_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(
            precision=14,
            scale=2,
        ),
        nullable=True,
        comment="Попередня сума каси перед редагуванням",
    )

    original_receipt_file_id: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Попереднє фото перед заміною",
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    store: Mapped[Store] = relationship(
        "Store",
        back_populates="closing_reports",
        lazy="joined",
    )

    submitted_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[submitted_by_id],
        back_populates="closing_reports",
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
        scheduled_close_time: time,
        control_deadline: time,
    ) -> ClosingReport:
        """Створює запис очікування вечірнього звіту."""

        if control_deadline < scheduled_close_time:
            raise ValueError(
                "Контрольний дедлайн не може бути "
                "раніше часу закриття."
            )

        return cls(
            store_id=store_id,
            business_date=business_date,
            scheduled_close_time=scheduled_close_time,
            control_deadline=control_deadline,
            status=ClosingStatus.WAITING,
            has_receipt=False,
            deadline_alert_was_sent=False,
        )

    # ==========================================
    # ГРОШОВІ ЗНАЧЕННЯ
    # ==========================================

    @staticmethod
    def normalize_cash_amount(
        value: Decimal | int | float | str,
    ) -> Decimal:
        """
        Перетворює значення каси у Decimal
        з двома знаками після коми.
        """

        if isinstance(value, str):
            normalized_value = (
                value.strip()
                .replace(" ", "")
                .replace(",", ".")
            )
        else:
            normalized_value = str(value)

        try:
            amount = Decimal(normalized_value)
        except Exception as error:
            raise ValueError(
                "Некоректний формат суми каси."
            ) from error

        if amount < 0:
            raise ValueError(
                "Сума каси не може бути від’ємною."
            )

        return amount.quantize(Decimal("0.01"))

    # ==========================================
    # ФОТО ЧЕКА
    # ==========================================

    def attach_receipt(
        self,
        *,
        file_id: str,
        file_unique_id: str | None = None,
        mime_type: str | None = None,
        file_name: str | None = None,
        file_size: int | None = None,
    ) -> None:
        """Прикріплює фото касового чека."""

        normalized_file_id = file_id.strip()

        if not normalized_file_id:
            raise ValueError(
                "Telegram file_id не може бути порожнім."
            )

        self.receipt_file_id = normalized_file_id
        self.receipt_file_unique_id = (
            file_unique_id.strip()
            if file_unique_id
            else None
        )

        self.receipt_mime_type = (
            mime_type.strip()
            if mime_type
            else None
        )

        self.receipt_file_name = (
            file_name.strip()
            if file_name
            else None
        )

        self.receipt_file_size = file_size
        self.has_receipt = True

    # ==========================================
    # ПІДТВЕРДЖЕННЯ ЗАКРИТТЯ
    # ==========================================

    def confirm_report(
        self,
        *,
        submitted_at: datetime,
        control_deadline_datetime: datetime,
        cash_amount: Decimal | int | float | str,
        submitted_by_id: int,
        require_receipt: bool = True,
        source: str = "telegram_bot",
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
    ) -> None:
        """
        Підтверджує фінальний вечірній звіт.

        Повторне підтвердження не дозволяється.
        """

        if self.actual_submitted_at is not None:
            raise ValueError(
                "Вечірній звіт цієї ТТ уже підтверджено."
            )

        if require_receipt and not self.has_receipt:
            raise ValueError(
                "Для закриття потрібно додати фото чека."
            )

        self.cash_amount = self.normalize_cash_amount(
            cash_amount
        )

        self.actual_submitted_at = submitted_at
        self.submitted_by_id = submitted_by_id
        self.source = source

        self.telegram_chat_id = telegram_chat_id
        self.telegram_message_id = telegram_message_id

        submitted_minute = submitted_at.replace(
            second=0,
            microsecond=0,
        )

        deadline_minute = (
            control_deadline_datetime.replace(
                second=0,
                microsecond=0,
            )
        )

        if submitted_minute <= deadline_minute:
            self.status = (
                ClosingStatus.SUBMITTED_ON_TIME
            )
        else:
            self.status = (
                ClosingStatus.SUBMITTED_LATE
            )

    # ==========================================
    # ПРОПУЩЕНИЙ ДЕДЛАЙН
    # ==========================================

    def mark_deadline_missed(
        self,
        *,
        missed_at: datetime,
        alert_sent: bool = True,
    ) -> None:
        """Фіксує відсутність звіту після дедлайну."""

        if self.actual_submitted_at is not None:
            return

        self.status = ClosingStatus.MISSED_DEADLINE
        self.missed_deadline_at = missed_at

        if alert_sent:
            self.deadline_alert_was_sent = True
            self.deadline_alert_sent_at = missed_at

    def mark_deadline_alert_sent(
        self,
        *,
        sent_at: datetime,
    ) -> None:
        """Фіксує надсилання сповіщення."""

        self.deadline_alert_was_sent = True
        self.deadline_alert_sent_at = sent_at

    # ==========================================
    # TELEGRAM-ГРУПА
    # ==========================================

    def mark_sent_to_group(
        self,
        *,
        chat_id: int,
        message_id: int,
        sent_at: datetime,
        topic_id: int | None = None,
    ) -> None:
        """Зберігає дані повідомлення у групі."""

        self.closing_group_chat_id = chat_id
        self.closing_group_topic_id = topic_id
        self.closing_group_message_id = message_id
        self.sent_to_group_at = sent_at

    # ==========================================
    # РУЧНЕ КОРИГУВАННЯ
    # ==========================================

    def modify_cash_amount(
        self,
        *,
        new_cash_amount: Decimal | int | float | str,
        modified_by_id: int,
        modified_at: datetime,
        reason: str,
    ) -> None:
        """Змінює помилково введену суму каси."""

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError(
                "Потрібно вказати причину зміни суми."
            )

        new_amount = self.normalize_cash_amount(
            new_cash_amount
        )

        self.original_cash_amount = self.cash_amount
        self.cash_amount = new_amount

        self.manually_modified_by_id = modified_by_id
        self.manually_modified_at = modified_at
        self.modification_reason = normalized_reason

    def replace_receipt(
        self,
        *,
        new_file_id: str,
        modified_by_id: int,
        modified_at: datetime,
        reason: str,
        new_file_unique_id: str | None = None,
        mime_type: str | None = None,
        file_name: str | None = None,
        file_size: int | None = None,
    ) -> None:
        """Замінює фотографію касового чека."""

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError(
                "Потрібно вказати причину заміни фото."
            )

        self.original_receipt_file_id = (
            self.receipt_file_id
        )

        self.attach_receipt(
            file_id=new_file_id,
            file_unique_id=new_file_unique_id,
            mime_type=mime_type,
            file_name=file_name,
            file_size=file_size,
        )

        self.manually_modified_by_id = modified_by_id
        self.manually_modified_at = modified_at
        self.modification_reason = normalized_reason

    def manually_confirm(
        self,
        *,
        submitted_at: datetime,
        cash_amount: Decimal | int | float | str,
        modified_by_id: int,
        modified_at: datetime,
        reason: str,
    ) -> None:
        """Ручне підтвердження звіту адміністратором."""

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError(
                "Для ручного підтвердження "
                "потрібно вказати причину."
            )

        self.cash_amount = self.normalize_cash_amount(
            cash_amount
        )

        self.actual_submitted_at = submitted_at
        self.status = ClosingStatus.MANUALLY_CONFIRMED
        self.source = "manual_admin"

        self.manually_modified_by_id = modified_by_id
        self.manually_modified_at = modified_at
        self.modification_reason = normalized_reason

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def is_submitted(self) -> bool:
        """Чи підтверджено вечірній звіт."""

        return self.actual_submitted_at is not None

    @property
    def is_waiting(self) -> bool:
        return self.status == ClosingStatus.WAITING

    @property
    def is_late(self) -> bool:
        return self.status == ClosingStatus.SUBMITTED_LATE

    @property
    def missed_deadline(self) -> bool:
        return self.status == ClosingStatus.MISSED_DEADLINE

    @property
    def cash_amount_text(self) -> str:
        """Форматує касу для Telegram-повідомлення."""

        if self.cash_amount is None:
            return "Не вказано"

        formatted = f"{self.cash_amount:,.2f}"

        formatted = (
            formatted
            .replace(",", " ")
            .replace(".", ",")
        )

        return f"{formatted} грн"

    @property
    def actual_submitted_time_text(self) -> str | None:
        """Час подання у форматі 21:04."""

        if self.actual_submitted_at is None:
            return None

        return self.actual_submitted_at.strftime(
            "%H:%M"
        )

    @property
    def scheduled_close_time_text(self) -> str:
        return self.scheduled_close_time.strftime(
            "%H:%M"
        )

    @property
    def control_deadline_text(self) -> str:
        return self.control_deadline.strftime(
            "%H:%M"
        )