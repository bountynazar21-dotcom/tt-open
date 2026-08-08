from __future__ import annotations

import hashlib
from datetime import date, datetime
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
    NotificationType,
)


if TYPE_CHECKING:
    from app.database.models.bush import Bush
    from app.database.models.store import Store
    from app.database.models.user import User


class NotificationLog(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Журнал Telegram-повідомлень.

    Використовується для:

    - ранкових нагадувань;
    - повідомлень про запізнення;
    - списків невідкритих ТТ;
    - нагадувань про закриття;
    - списків ТТ без вечірнього звіту;
    - підсумків по кущах;
    - підсумків по всій мережі;
    - запобігання дублюванню повідомлень.

    Кожне логічне повідомлення має унікальний dedupe_key.
    """

    __tablename__ = "notification_logs"

    __table_args__ = (
        UniqueConstraint(
            "dedupe_key",
            name="uq_notification_logs_dedupe_key",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="attempt_count_non_negative",
        ),
        Index(
            "ix_notification_logs_date_type",
            "business_date",
            "notification_type",
        ),
        Index(
            "ix_notification_logs_status_scheduled",
            "status",
            "scheduled_for",
        ),
        Index(
            "ix_notification_logs_store_date",
            "store_id",
            "business_date",
        ),
        Index(
            "ix_notification_logs_bush_date",
            "bush_id",
            "business_date",
        ),
        Index(
            "ix_notification_logs_user_date",
            "recipient_user_id",
            "business_date",
        ),
        Index(
            "ix_notification_logs_chat_message",
            "chat_id",
            "message_id",
        ),
    )

    # ==========================================
    # ТИП І СТАТУС
    # ==========================================

    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(
            NotificationType,
            name="notification_type",
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

    # ==========================================
    # ЗАХИСТ ВІД ДУБЛІКАТІВ
    # ==========================================

    dedupe_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Унікальний ключ логічного повідомлення",
    )

    idempotency_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA-256 хеш ключа ідемпотентності",
    )

    # ==========================================
    # БІЗНЕС-ДАТА І ЧАС
    # ==========================================

    business_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
        comment="Робоча дата повідомлення",
    )

    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Запланований час надсилання",
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Фактичний час успішного надсилання",
    )

    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Час останнього редагування повідомлення",
    )

    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Час останньої спроби надсилання",
    )

    # ==========================================
    # ОБ’ЄКТИ СИСТЕМИ
    # ==========================================

    recipient_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Конкретний одержувач повідомлення",
    )

    store_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Торгова точка, якої стосується повідомлення",
    )

    bush_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "bushes.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Кущ, якого стосується повідомлення",
    )

    # ==========================================
    # TELEGRAM
    # ==========================================

    chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="Telegram chat ID одержувача або групи",
    )

    topic_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram topic ID",
    )

    message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID надісланого Telegram-повідомлення",
    )

    reply_to_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID повідомлення, на яке була відповідь",
    )

    # ==========================================
    # ВМІСТ ПОВІДОМЛЕННЯ
    # ==========================================

    message_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Останній текст повідомлення",
    )

    payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Службові дані для повторного надсилання",
    )

    # ==========================================
    # СПРОБИ ТА ПОМИЛКИ
    # ==========================================

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Кількість спроб надсилання",
    )

    error_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Остання технічна помилка",
    )

    telegram_error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Код помилки Telegram API",
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    recipient_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[recipient_user_id],
        lazy="joined",
    )

    store: Mapped[Store | None] = relationship(
        "Store",
        foreign_keys=[store_id],
        back_populates="notification_logs",
        lazy="joined",
    )

    bush: Mapped[Bush | None] = relationship(
        "Bush",
        foreign_keys=[bush_id],
        lazy="joined",
    )

    # ==========================================
    # СТВОРЕННЯ КЛЮЧІВ
    # ==========================================

    @staticmethod
    def create_hash(value: str) -> str:
        """Створює SHA-256 хеш рядка."""

        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError(
                "Значення для хешування не може бути порожнім."
            )

        return hashlib.sha256(
            normalized_value.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def build_dedupe_key(
        *,
        notification_type: NotificationType,
        business_date: date | None = None,
        recipient_user_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        chat_id: int | None = None,
        suffix: str | None = None,
    ) -> str:
        """
        Створює стабільний ключ повідомлення.

        Приклад:

        opening_reminder:2026-07-24:store-12:user-5

        Scheduler може перевірити цей ключ перед надсиланням
        і не створити повторне повідомлення.
        """

        parts: list[str] = [
            notification_type.value,
        ]

        if business_date is not None:
            parts.append(
                business_date.isoformat()
            )

        if store_id is not None:
            parts.append(
                f"store-{store_id}"
            )

        if bush_id is not None:
            parts.append(
                f"bush-{bush_id}"
            )

        if recipient_user_id is not None:
            parts.append(
                f"user-{recipient_user_id}"
            )

        if chat_id is not None:
            parts.append(
                f"chat-{chat_id}"
            )

        if suffix:
            normalized_suffix = suffix.strip()

            if normalized_suffix:
                parts.append(
                    normalized_suffix
                )

        return ":".join(parts)

    @classmethod
    def create_pending(
        cls,
        *,
        notification_type: NotificationType,
        dedupe_key: str,
        business_date: date | None = None,
        scheduled_for: datetime | None = None,
        recipient_user_id: int | None = None,
        store_id: int | None = None,
        bush_id: int | None = None,
        chat_id: int | None = None,
        topic_id: int | None = None,
        message_text: str | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> NotificationLog:
        """Створює запис очікування надсилання."""

        normalized_key = dedupe_key.strip()

        if not normalized_key:
            raise ValueError(
                "Ключ дедуплікації не може бути порожнім."
            )

        return cls(
            notification_type=notification_type,
            status=NotificationStatus.PENDING,
            dedupe_key=normalized_key,
            idempotency_hash=cls.create_hash(
                normalized_key
            ),
            business_date=business_date,
            scheduled_for=scheduled_for,
            recipient_user_id=recipient_user_id,
            store_id=store_id,
            bush_id=bush_id,
            chat_id=chat_id,
            topic_id=topic_id,
            message_text=message_text,
            payload_json=payload_json,
            attempt_count=0,
        )

    # ==========================================
    # СТАН ПОВІДОМЛЕННЯ
    # ==========================================

    def register_attempt(
        self,
        *,
        attempted_at: datetime,
    ) -> None:
        """Фіксує нову спробу надсилання."""

        self.attempt_count += 1
        self.last_attempt_at = attempted_at

    def mark_sent(
        self,
        *,
        sent_at: datetime,
        chat_id: int,
        message_id: int,
        topic_id: int | None = None,
        message_text: str | None = None,
    ) -> None:
        """Позначає повідомлення як успішно надіслане."""

        self.status = NotificationStatus.SENT

        self.sent_at = sent_at
        self.last_attempt_at = sent_at

        self.chat_id = chat_id
        self.topic_id = topic_id
        self.message_id = message_id

        if message_text is not None:
            self.message_text = message_text

        self.error_text = None
        self.telegram_error_code = None

    def mark_edited(
        self,
        *,
        edited_at: datetime,
        message_text: str | None = None,
    ) -> None:
        """Фіксує успішне редагування повідомлення."""

        if self.message_id is None:
            raise ValueError(
                "Неможливо позначити повідомлення відредагованим "
                "без Telegram message_id."
            )

        self.status = NotificationStatus.EDITED
        self.edited_at = edited_at
        self.last_attempt_at = edited_at

        if message_text is not None:
            self.message_text = message_text

        self.error_text = None
        self.telegram_error_code = None

    def mark_failed(
        self,
        *,
        failed_at: datetime,
        error_text: str,
        telegram_error_code: str | None = None,
    ) -> None:
        """Фіксує помилку надсилання."""

        normalized_error = error_text.strip()

        if not normalized_error:
            normalized_error = (
                "Невідома помилка надсилання повідомлення."
            )

        self.status = NotificationStatus.FAILED
        self.last_attempt_at = failed_at

        self.error_text = normalized_error
        self.telegram_error_code = telegram_error_code

    def mark_skipped(
        self,
        *,
        skipped_at: datetime,
        reason: str,
    ) -> None:
        """
        Позначає повідомлення пропущеним.

        Наприклад, якщо ТТ уже відкрилася
        до моменту фактичного надсилання нагадування.
        """

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError(
                "Потрібно вказати причину пропуску."
            )

        self.status = NotificationStatus.SKIPPED
        self.last_attempt_at = skipped_at
        self.error_text = normalized_reason

    def reset_for_retry(self) -> None:
        """Повертає невдале повідомлення у чергу."""

        if self.status not in {
            NotificationStatus.FAILED,
            NotificationStatus.SKIPPED,
        }:
            raise ValueError(
                "Повторно поставити в чергу можна лише "
                "невдале або пропущене повідомлення."
            )

        self.status = NotificationStatus.PENDING
        self.error_text = None
        self.telegram_error_code = None

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def was_delivered(self) -> bool:
        """Чи було повідомлення успішно надіслано."""

        return self.status in {
            NotificationStatus.SENT,
            NotificationStatus.EDITED,
        }

    @property
    def can_be_edited(self) -> bool:
        """Чи є дані для редагування Telegram-повідомлення."""

        return (
            self.chat_id is not None
            and self.message_id is not None
            and self.status
            in {
                NotificationStatus.SENT,
                NotificationStatus.EDITED,
            }
        )

    @property
    def should_retry(self) -> bool:
        """Чи можна повторити надсилання."""

        return self.status == NotificationStatus.FAILED