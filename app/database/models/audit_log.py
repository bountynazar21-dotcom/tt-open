from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import (
    Base,
    IntegerPrimaryKeyMixin,
    TimestampMixin,
)
from app.database.models.enums import (
    AuditAction,
    EntityType,
)


if TYPE_CHECKING:
    from app.database.models.user import User


class AuditLog(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Журнал адміністративних і критичних дій.

    Записи аудиту не повинні редагуватися або видалятися
    через звичайне меню бота.

    AuditLog зберігає:

    - хто виконав дію;
    - яку дію виконав;
    - над яким об’єктом;
    - старе значення;
    - нове значення;
    - причину;
    - Telegram-контекст;
    - точний час дії.
    """

    __tablename__ = "audit_logs"

    __table_args__ = (
        Index(
            "ix_audit_logs_actor_created",
            "actor_user_id",
            "created_at",
        ),
        Index(
            "ix_audit_logs_entity_created",
            "entity_type",
            "entity_id",
            "created_at",
        ),
        Index(
            "ix_audit_logs_action_created",
            "action",
            "created_at",
        ),
        Index(
            "ix_audit_logs_store_number",
            "store_number",
            "created_at",
        ),
        Index(
            "ix_audit_logs_telegram_user",
            "actor_telegram_id",
            "created_at",
        ),
    )

    # ==========================================
    # ХТО ВИКОНАВ ДІЮ
    # ==========================================

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Користувач системи, який виконав дію",
    )

    actor_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="Telegram ID користувача на момент дії",
    )

    actor_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Ім’я користувача на момент дії",
    )

    actor_role: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Роль користувача на момент дії",
    )

    # ==========================================
    # ДІЯ
    # ==========================================

    action: Mapped[AuditAction] = mapped_column(
        Enum(
            AuditAction,
            name="audit_action",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        index=True,
        comment="Тип виконаної дії",
    )

    entity_type: Mapped[EntityType] = mapped_column(
        Enum(
            EntityType,
            name="entity_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum_class: [
                item.value
                for item in enum_class
            ],
        ),
        nullable=False,
        index=True,
        comment="Тип об’єкта, який було змінено",
    )

    entity_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="Внутрішній ID об’єкта",
    )

    entity_label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Зрозуміла назва об’єкта, наприклад SB-76",
    )

    # ==========================================
    # ДАНІ ТОРГОВОЇ ТОЧКИ
    # ==========================================

    store_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="Номер ТТ, якщо дія стосується магазину",
    )

    bush_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="ID куща на момент дії",
    )

    bush_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        comment="Назва куща на момент дії",
    )

    # ==========================================
    # СТАРІ ТА НОВІ ЗНАЧЕННЯ
    # ==========================================

    old_value_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Стан об’єкта до зміни",
    )

    new_value_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Стан об’єкта після зміни",
    )

    changed_fields: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Список полів, які були змінені",
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Причина адміністративної дії",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Додатковий опис дії",
    )

    # ==========================================
    # TELEGRAM-КОНТЕКСТ
    # ==========================================

    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram chat ID, де виконано дію",
    )

    telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram message ID",
    )

    telegram_callback_data: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Callback data натиснутої кнопки",
    )

    # ==========================================
    # ТЕХНІЧНИЙ КОНТЕКСТ
    # ==========================================

    request_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Унікальний ID запиту або операції",
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="telegram_bot",
        server_default="telegram_bot",
        comment="Джерело виконання дії",
    )

    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Точний час виконання дії",
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    actor: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[actor_user_id],
        back_populates="audit_actions",
        lazy="joined",
    )

    # ==========================================
    # СТВОРЕННЯ ЗАПИСУ
    # ==========================================

    @classmethod
    def create(
        cls,
        *,
        action: AuditAction,
        entity_type: EntityType,
        performed_at: datetime,
        actor_user_id: int | None = None,
        actor_telegram_id: int | None = None,
        actor_name: str | None = None,
        actor_role: str | None = None,
        entity_id: int | None = None,
        entity_label: str | None = None,
        store_number: int | None = None,
        bush_id: int | None = None,
        bush_name: str | None = None,
        old_value_json: dict[str, Any] | None = None,
        new_value_json: dict[str, Any] | None = None,
        reason: str | None = None,
        description: str | None = None,
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
        telegram_callback_data: str | None = None,
        request_id: str | None = None,
        source: str = "telegram_bot",
    ) -> AuditLog:
        """Створює новий запис журналу аудиту."""

        if performed_at.tzinfo is None:
            raise ValueError(
                "performed_at повинен містити часовий пояс."
            )

        normalized_source = source.strip()

        if not normalized_source:
            raise ValueError(
                "Джерело дії не може бути порожнім."
            )

        changed_fields = cls.detect_changed_fields(
            old_value=old_value_json,
            new_value=new_value_json,
        )

        return cls(
            actor_user_id=actor_user_id,
            actor_telegram_id=actor_telegram_id,
            actor_name=(
                actor_name.strip()
                if actor_name
                else None
            ),
            actor_role=(
                actor_role.strip()
                if actor_role
                else None
            ),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=(
                entity_label.strip()
                if entity_label
                else None
            ),
            store_number=store_number,
            bush_id=bush_id,
            bush_name=(
                bush_name.strip()
                if bush_name
                else None
            ),
            old_value_json=old_value_json,
            new_value_json=new_value_json,
            changed_fields=changed_fields,
            reason=(
                reason.strip()
                if reason
                else None
            ),
            description=(
                description.strip()
                if description
                else None
            ),
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            telegram_callback_data=telegram_callback_data,
            request_id=request_id,
            source=normalized_source,
            performed_at=performed_at,
        )

    # ==========================================
    # ВИЗНАЧЕННЯ ЗМІН
    # ==========================================

    @staticmethod
    def detect_changed_fields(
        *,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
    ) -> list[str]:
        """
        Порівнює старий і новий стани об’єкта.

        Повертає список змінених полів.
        """

        if old_value is None and new_value is None:
            return []

        old_data = old_value or {}
        new_data = new_value or {}

        all_fields = set(old_data) | set(new_data)

        changed_fields = [
            field_name
            for field_name in all_fields
            if old_data.get(field_name)
            != new_data.get(field_name)
        ]

        return sorted(changed_fields)

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @classmethod
    def create_store_deactivation(
        cls,
        *,
        performed_at: datetime,
        actor_user_id: int,
        actor_telegram_id: int,
        actor_name: str,
        actor_role: str,
        store_id: int,
        store_number: int,
        store_code: str,
        city: str,
        address: str,
        reason: str,
        bush_id: int | None = None,
        bush_name: str | None = None,
    ) -> AuditLog:
        """Створює аудит кіку торгової точки."""

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError(
                "Для деактивації ТТ потрібно вказати причину."
            )

        return cls.create(
            action=AuditAction.DEACTIVATED,
            entity_type=EntityType.STORE,
            performed_at=performed_at,
            actor_user_id=actor_user_id,
            actor_telegram_id=actor_telegram_id,
            actor_name=actor_name,
            actor_role=actor_role,
            entity_id=store_id,
            entity_label=store_code,
            store_number=store_number,
            bush_id=bush_id,
            bush_name=bush_name,
            old_value_json={
                "status": "active",
                "is_active": True,
                "city": city,
                "address": address,
            },
            new_value_json={
                "status": "inactive",
                "is_active": False,
                "city": city,
                "address": address,
            },
            reason=normalized_reason,
            description=(
                f"Торгову точку {store_code} "
                f"деактивовано та виключено з контролю."
            ),
        )

    @classmethod
    def create_cash_modification(
        cls,
        *,
        performed_at: datetime,
        actor_user_id: int,
        actor_telegram_id: int,
        actor_name: str,
        actor_role: str,
        closing_report_id: int,
        store_number: int,
        store_code: str,
        old_cash_amount: str,
        new_cash_amount: str,
        reason: str,
    ) -> AuditLog:
        """Створює аудит зміни касової суми."""

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError(
                "Для зміни каси потрібно вказати причину."
            )

        return cls.create(
            action=AuditAction.CASH_AMOUNT_MODIFIED,
            entity_type=EntityType.CLOSING_REPORT,
            performed_at=performed_at,
            actor_user_id=actor_user_id,
            actor_telegram_id=actor_telegram_id,
            actor_name=actor_name,
            actor_role=actor_role,
            entity_id=closing_report_id,
            entity_label=store_code,
            store_number=store_number,
            old_value_json={
                "cash_amount": old_cash_amount,
            },
            new_value_json={
                "cash_amount": new_cash_amount,
            },
            reason=normalized_reason,
            description=(
                f"Змінено суму каси для {store_code}: "
                f"{old_cash_amount} → {new_cash_amount}."
            ),
        )

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def has_changes(self) -> bool:
        """Чи містить запис змінені поля."""

        return bool(self.changed_fields)

    @property
    def actor_display_name(self) -> str:
        """Зручне ім’я виконавця дії."""

        if self.actor_name:
            return self.actor_name

        if self.actor_telegram_id:
            return f"Telegram ID {self.actor_telegram_id}"

        return "Система"

    @property
    def entity_display_name(self) -> str:
        """Зручна назва зміненого об’єкта."""

        if self.entity_label:
            return self.entity_label

        if self.entity_id is not None:
            return (
                f"{self.entity_type.value} "
                f"#{self.entity_id}"
            )

        return self.entity_type.value

    @property
    def action_summary(self) -> str:
        """Короткий опис для адмін-меню."""

        return (
            f"{self.actor_display_name}: "
            f"{self.action.value} — "
            f"{self.entity_display_name}"
        )