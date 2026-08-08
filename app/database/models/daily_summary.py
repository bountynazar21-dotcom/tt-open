from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import (
    Base,
    IntegerPrimaryKeyMixin,
    TimestampMixin,
)
from app.database.models.enums import (
    NotificationStatus,
    SummaryType,
)


if TYPE_CHECKING:
    from app.database.models.bush import Bush


class DailySummaryMessage(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Зведене повідомлення за один робочий день.

    Приклади:
    - відкриття конкретного куща;
    - відкриття всієї мережі;
    - закриття конкретного куща;
    - закриття всієї мережі.

    Бот створює повідомлення один раз, зберігає його
    Telegram message_id і надалі лише редагує текст.
    """

    __tablename__ = "daily_summary_messages"

    __table_args__ = (
        UniqueConstraint(
            "summary_key",
            name="uq_daily_summary_messages_summary_key",
        ),
        CheckConstraint(
            "expected_stores_count >= 0",
            name="expected_stores_count_non_negative",
        ),
        CheckConstraint(
            "completed_stores_count >= 0",
            name="completed_stores_count_non_negative",
        ),
        CheckConstraint(
            "pending_stores_count >= 0",
            name="pending_stores_count_non_negative",
        ),
        CheckConstraint(
            "late_stores_count >= 0",
            name="late_stores_count_non_negative",
        ),
        CheckConstraint(
            "problem_stores_count >= 0",
            name="problem_stores_count_non_negative",
        ),
        CheckConstraint(
            "total_cash >= 0",
            name="total_cash_non_negative",
        ),
        Index(
            "ix_daily_summary_messages_date_type",
            "business_date",
            "summary_type",
        ),
        Index(
            "ix_daily_summary_messages_bush_date",
            "bush_id",
            "business_date",
        ),
        Index(
            "ix_daily_summary_messages_chat_message",
            "chat_id",
            "message_id",
        ),
        Index(
            "ix_daily_summary_messages_status_updated",
            "status",
            "last_updated_at",
        ),
    )

    # ==========================================
    # ІДЕНТИФІКАЦІЯ ПІДСУМКУ
    # ==========================================

    summary_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Унікальний ключ денного підсумку",
    )

    summary_type: Mapped[SummaryType] = mapped_column(
        Enum(
            SummaryType,
            name="summary_type",
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

    business_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Робоча дата підсумку",
    )

    bush_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "bushes.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
        comment="Кущ або NULL для підсумку всієї мережі",
    )

    # ==========================================
    # TELEGRAM
    # ==========================================

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Telegram-група або приватний чат",
    )

    topic_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Тема Telegram-групи",
    )

    message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID повідомлення, яке потрібно редагувати",
    )

    status: Mapped[NotificationStatus] = mapped_column(
        Enum(
            NotificationStatus,
            name="notification_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.value,
        index=True,
    )

    message_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Остання версія тексту повідомлення",
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Час першого надсилання повідомлення",
    )

    last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Час останнього редагування",
    )

    # ==========================================
    # ОСНОВНІ ПОКАЗНИКИ
    # ==========================================

    expected_stores_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Кількість ТТ, які повинні працювати",
    )

    completed_stores_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Кількість ТТ, які виконали дію",
    )

    pending_stores_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Кількість ТТ, від яких ще очікується дія",
    )

    late_stores_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Кількість ТТ із запізненням",
    )

    problem_stores_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Невідкриті ТТ або ТТ без вечірнього звіту",
    )

    total_cash: Mapped[Decimal] = mapped_column(
        Numeric(
            precision=16,
            scale=2,
        ),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0",
        comment="Загальна каса по кущу або мережі",
    )

    # ==========================================
    # ДЕТАЛЬНІ ДАНІ
    # ==========================================

    completed_store_ids: Mapped[list[int] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="ID торгових точок, які виконали дію",
    )

    pending_store_ids: Mapped[list[int] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="ID торгових точок, від яких очікується дія",
    )

    late_store_ids: Mapped[list[int] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="ID торгових точок із запізненням",
    )

    problem_store_ids: Mapped[list[int] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="ID проблемних торгових точок",
    )

    details_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Додаткові дані для формування повідомлення",
    )

    error_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Остання помилка Telegram API",
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    bush: Mapped[Bush | None] = relationship(
        "Bush",
        back_populates="daily_summary_messages",
        lazy="joined",
    )

    # ==========================================
    # СТВОРЕННЯ ПІДСУМКУ
    # ==========================================

    @staticmethod
    def build_summary_key(
        *,
        summary_type: SummaryType,
        business_date: date,
        chat_id: int,
        bush_id: int | None = None,
        topic_id: int | None = None,
    ) -> str:
        """
        Створює унікальний ключ підсумку.

        Приклад для куща:
        bush_closing:2026-07-24:bush-3:chat--100123

        Приклад для мережі:
        network_closing:2026-07-24:network:chat--100123
        """

        scope = (
            f"bush-{bush_id}"
            if bush_id is not None
            else "network"
        )

        parts = [
            summary_type.value,
            business_date.isoformat(),
            scope,
            f"chat-{chat_id}",
        ]

        if topic_id is not None:
            parts.append(f"topic-{topic_id}")

        return ":".join(parts)

    @classmethod
    def create_pending(
        cls,
        *,
        summary_type: SummaryType,
        business_date: date,
        chat_id: int,
        bush_id: int | None = None,
        topic_id: int | None = None,
    ) -> DailySummaryMessage:
        """Створює новий денний підсумок."""

        cls.validate_scope(
            summary_type=summary_type,
            bush_id=bush_id,
        )

        summary_key = cls.build_summary_key(
            summary_type=summary_type,
            business_date=business_date,
            chat_id=chat_id,
            bush_id=bush_id,
            topic_id=topic_id,
        )

        return cls(
            summary_key=summary_key,
            summary_type=summary_type,
            business_date=business_date,
            bush_id=bush_id,
            chat_id=chat_id,
            topic_id=topic_id,
            status=NotificationStatus.PENDING,
            expected_stores_count=0,
            completed_stores_count=0,
            pending_stores_count=0,
            late_stores_count=0,
            problem_stores_count=0,
            total_cash=Decimal("0.00"),
            completed_store_ids=[],
            pending_store_ids=[],
            late_store_ids=[],
            problem_store_ids=[],
        )

    @staticmethod
    def validate_scope(
        *,
        summary_type: SummaryType,
        bush_id: int | None,
    ) -> None:
        """Перевіряє відповідність типу підсумку та куща."""

        bush_types = {
            SummaryType.BUSH_OPENING,
            SummaryType.BUSH_CLOSING,
        }

        network_types = {
            SummaryType.NETWORK_OPENING,
            SummaryType.NETWORK_CLOSING,
        }

        if summary_type in bush_types and bush_id is None:
            raise ValueError(
                "Для підсумку куща потрібно вказати bush_id."
            )

        if summary_type in network_types and bush_id is not None:
            raise ValueError(
                "Мережевий підсумок не повинен містити bush_id."
            )

    # ==========================================
    # ОНОВЛЕННЯ ПОКАЗНИКІВ
    # ==========================================

    def update_metrics(
        self,
        *,
        expected_stores_count: int,
        completed_store_ids: list[int],
        pending_store_ids: list[int],
        late_store_ids: list[int] | None = None,
        problem_store_ids: list[int] | None = None,
        total_cash: Decimal | int | float | str = Decimal("0.00"),
        details_json: dict[str, Any] | None = None,
    ) -> None:
        """Повністю оновлює показники денного підсумку."""

        if expected_stores_count < 0:
            raise ValueError(
                "Кількість торгових точок не може бути від’ємною."
            )

        completed_ids = self.normalize_ids(completed_store_ids)
        pending_ids = self.normalize_ids(pending_store_ids)
        late_ids = self.normalize_ids(late_store_ids or [])
        problem_ids = self.normalize_ids(problem_store_ids or [])

        completed_set = set(completed_ids)
        pending_set = set(pending_ids)

        if completed_set.intersection(pending_set):
            raise ValueError(
                "Одна ТТ не може одночасно бути виконаною "
                "та очікувати виконання."
            )

        if len(completed_ids) + len(pending_ids) > expected_stores_count:
            raise ValueError(
                "Сума виконаних та очікуваних ТТ перевищує "
                "загальну кількість ТТ."
            )

        self.expected_stores_count = expected_stores_count

        self.completed_store_ids = completed_ids
        self.pending_store_ids = pending_ids
        self.late_store_ids = late_ids
        self.problem_store_ids = problem_ids

        self.completed_stores_count = len(completed_ids)
        self.pending_stores_count = len(pending_ids)
        self.late_stores_count = len(late_ids)
        self.problem_stores_count = len(problem_ids)

        self.total_cash = self.normalize_cash_amount(
            total_cash
        )

        self.details_json = details_json

    @staticmethod
    def normalize_ids(values: list[int]) -> list[int]:
        """Прибирає дублікати ID і сортує список."""

        normalized_values: set[int] = set()

        for value in values:
            integer_value = int(value)

            if integer_value <= 0:
                raise ValueError(
                    "ID торгової точки повинен бути більшим за нуль."
                )

            normalized_values.add(integer_value)

        return sorted(normalized_values)

    @staticmethod
    def normalize_cash_amount(
        value: Decimal | int | float | str,
    ) -> Decimal:
        """Перетворює касу на Decimal із двома знаками."""

        normalized_value = str(value).strip().replace(
            ",",
            ".",
        )

        try:
            amount = Decimal(normalized_value)
        except Exception as error:
            raise ValueError(
                "Некоректний формат загальної каси."
            ) from error

        if amount < 0:
            raise ValueError(
                "Загальна каса не може бути від’ємною."
            )

        return amount.quantize(Decimal("0.01"))

    # ==========================================
    # TELEGRAM-ПОВІДОМЛЕННЯ
    # ==========================================

    def mark_sent(
        self,
        *,
        message_id: int,
        sent_at: datetime,
        message_text: str,
    ) -> None:
        """Фіксує перше надсилання повідомлення."""

        if message_id <= 0:
            raise ValueError(
                "Telegram message_id повинен бути більшим за нуль."
            )

        self.message_id = message_id
        self.sent_at = sent_at
        self.last_updated_at = sent_at
        self.message_text = message_text

        self.status = NotificationStatus.SENT
        self.error_text = None

    def mark_edited(
        self,
        *,
        edited_at: datetime,
        message_text: str,
    ) -> None:
        """Фіксує редагування існуючого повідомлення."""

        if self.message_id is None:
            raise ValueError(
                "Неможливо редагувати підсумок без message_id."
            )

        self.last_updated_at = edited_at
        self.message_text = message_text

        self.status = NotificationStatus.EDITED
        self.error_text = None

    def mark_failed(
        self,
        *,
        failed_at: datetime,
        error_text: str,
    ) -> None:
        """Фіксує помилку надсилання або редагування."""

        normalized_error = error_text.strip()

        if not normalized_error:
            normalized_error = "Невідома помилка Telegram API."

        self.last_updated_at = failed_at
        self.status = NotificationStatus.FAILED
        self.error_text = normalized_error

    def reset_for_retry(self) -> None:
        """Повертає підсумок у статус очікування."""

        self.status = NotificationStatus.PENDING
        self.error_text = None

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def is_network_summary(self) -> bool:
        return self.summary_type in {
            SummaryType.NETWORK_OPENING,
            SummaryType.NETWORK_CLOSING,
        }

    @property
    def is_bush_summary(self) -> bool:
        return self.summary_type in {
            SummaryType.BUSH_OPENING,
            SummaryType.BUSH_CLOSING,
        }

    @property
    def is_opening_summary(self) -> bool:
        return self.summary_type in {
            SummaryType.BUSH_OPENING,
            SummaryType.NETWORK_OPENING,
        }

    @property
    def is_closing_summary(self) -> bool:
        return self.summary_type in {
            SummaryType.BUSH_CLOSING,
            SummaryType.NETWORK_CLOSING,
        }

    @property
    def can_be_edited(self) -> bool:
        return (
            self.message_id is not None
            and self.status
            in {
                NotificationStatus.SENT,
                NotificationStatus.EDITED,
            }
        )

    @property
    def completion_percent(self) -> float:
        """Відсоток виконання відкриття або закриття."""

        if self.expected_stores_count == 0:
            return 0.0

        return round(
            (
                self.completed_stores_count
                / self.expected_stores_count
            )
            * 100,
            2,
        )

    @property
    def total_cash_text(self) -> str:
        """Форматує загальну касу для Telegram."""

        formatted = f"{self.total_cash:,.2f}"

        formatted = (
            formatted
            .replace(",", " ")
            .replace(".", ",")
        )

        return f"{formatted} грн"