from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
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


if TYPE_CHECKING:
    from app.database.models.user import User


class SystemSetting(
    IntegerPrimaryKeyMixin,
    TimestampMixin,
    Base,
):
    """
    Налаштування системи, які зберігаються у базі даних.

    Змінні середовища .env використовуються для:
    - токена Telegram-бота;
    - підключення до PostgreSQL;
    - секретних ключів;
    - базових параметрів запуску.

    SystemSetting використовується для параметрів,
    які ROOT_ADMIN може змінювати через меню бота.
    """

    __tablename__ = "system_settings"

    __table_args__ = (
        Index(
            "ix_system_settings_category_active",
            "category",
            "is_active",
        ),
        Index(
            "ix_system_settings_editable_active",
            "is_editable",
            "is_active",
        ),
        Index(
            "ix_system_settings_updated_by",
            "updated_by_id",
            "updated_at",
        ),
    )

    # ==========================================
    # ІДЕНТИФІКАЦІЯ НАЛАШТУВАННЯ
    # ==========================================

    key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True,
        index=True,
        comment="Унікальний системний ключ",
    )

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="general",
        server_default="general",
        index=True,
        comment="Категорія налаштування",
    )

    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Назва для меню ROOT_ADMIN",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Пояснення призначення налаштування",
    )

    # ==========================================
    # ЗНАЧЕННЯ
    # ==========================================

    value_json: Mapped[Any] = mapped_column(
        JSON,
        nullable=False,
        comment="Поточне значення налаштування",
    )

    default_value_json: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Стандартне значення налаштування",
    )

    value_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="string",
        server_default="string",
        comment=(
            "Тип значення: string, integer, float, "
            "boolean, list, dict або nullable_integer"
        ),
    )

    validation_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "Правила перевірки: min, max, choices, "
            "allow_none та інші параметри"
        ),
    )

    # ==========================================
    # ДОСТУП І СТАТУС
    # ==========================================

    is_editable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
        comment="Чи можна редагувати через Telegram-бота",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
        comment="Чи використовується налаштування",
    )

    is_secret: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Чи потрібно приховувати значення в інтерфейсі",
    )

    requires_restart: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Чи потрібен перезапуск після зміни",
    )

    # ==========================================
    # ХТО ЗМІНИВ
    # ==========================================

    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Користувач, який востаннє змінив значення",
    )

    value_changed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Час останньої зміни значення",
    )

    change_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Причина останньої зміни",
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    updated_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[updated_by_id],
        lazy="joined",
    )

    # ==========================================
    # СТВОРЕННЯ НАЛАШТУВАННЯ
    # ==========================================

    @classmethod
    def create(
        cls,
        *,
        key: str,
        display_name: str,
        value: Any,
        value_type: str,
        category: str = "general",
        description: str | None = None,
        default_value: Any | None = None,
        validation: dict[str, Any] | None = None,
        is_editable: bool = True,
        is_secret: bool = False,
        requires_restart: bool = False,
    ) -> SystemSetting:
        """Створює нове системне налаштування."""

        normalized_key = cls.normalize_key(key)
        normalized_type = value_type.strip().lower()
        normalized_category = category.strip().lower()

        if not display_name.strip():
            raise ValueError(
                "Назва налаштування не може бути порожньою."
            )

        if not normalized_category:
            raise ValueError(
                "Категорія налаштування не може бути порожньою."
            )

        cls.validate_value(
            value=value,
            value_type=normalized_type,
            validation=validation,
        )

        if default_value is not None:
            cls.validate_value(
                value=default_value,
                value_type=normalized_type,
                validation=validation,
            )

        return cls(
            key=normalized_key,
            category=normalized_category,
            display_name=display_name.strip(),
            description=(
                description.strip()
                if description
                else None
            ),
            value_json=deepcopy(value),
            default_value_json=deepcopy(default_value),
            value_type=normalized_type,
            validation_json=deepcopy(validation),
            is_editable=is_editable,
            is_active=True,
            is_secret=is_secret,
            requires_restart=requires_restart,
        )

    # ==========================================
    # НОРМАЛІЗАЦІЯ
    # ==========================================

    @staticmethod
    def normalize_key(key: str) -> str:
        """
        Нормалізує ключ налаштування.

        Приклад:
        Opening Reminder Minutes
        -> opening_reminder_minutes
        """

        normalized_key = (
            key.strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
        )

        while "__" in normalized_key:
            normalized_key = normalized_key.replace(
                "__",
                "_",
            )

        normalized_key = normalized_key.strip("_")

        if not normalized_key:
            raise ValueError(
                "Ключ налаштування не може бути порожнім."
            )

        allowed_characters = set(
            "abcdefghijklmnopqrstuvwxyz0123456789_"
        )

        if any(
            character not in allowed_characters
            for character in normalized_key
        ):
            raise ValueError(
                "Ключ налаштування може містити лише "
                "латинські літери, цифри та нижнє підкреслення."
            )

        return normalized_key

    # ==========================================
    # ПЕРЕВІРКА ЗНАЧЕННЯ
    # ==========================================

    @classmethod
    def validate_value(
        cls,
        *,
        value: Any,
        value_type: str,
        validation: dict[str, Any] | None = None,
    ) -> None:
        """Перевіряє тип і допустимі межі значення."""

        supported_types = {
            "string",
            "integer",
            "nullable_integer",
            "float",
            "boolean",
            "list",
            "dict",
        }

        if value_type not in supported_types:
            raise ValueError(
                f"Непідтримуваний тип налаштування: {value_type}."
            )

        rules = validation or {}
        allow_none = bool(rules.get("allow_none", False))

        if value is None:
            if (
                allow_none
                or value_type == "nullable_integer"
            ):
                return

            raise ValueError(
                "Значення налаштування не може бути порожнім."
            )

        if value_type == "string":
            if not isinstance(value, str):
                raise ValueError(
                    "Значення повинно бути текстом."
                )

        elif value_type in {
            "integer",
            "nullable_integer",
        }:
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
            ):
                raise ValueError(
                    "Значення повинно бути цілим числом."
                )

        elif value_type == "float":
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
            ):
                raise ValueError(
                    "Значення повинно бути числом."
                )

        elif value_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(
                    "Значення повинно бути true або false."
                )

        elif value_type == "list":
            if not isinstance(value, list):
                raise ValueError(
                    "Значення повинно бути списком."
                )

        elif value_type == "dict":
            if not isinstance(value, dict):
                raise ValueError(
                    "Значення повинно бути словником."
                )

        cls.validate_rules(
            value=value,
            validation=rules,
        )

    @staticmethod
    def validate_rules(
        *,
        value: Any,
        validation: dict[str, Any],
    ) -> None:
        """Перевіряє min, max, choices і довжину."""

        if not validation:
            return

        minimum = validation.get("min")
        maximum = validation.get("max")
        choices = validation.get("choices")
        min_length = validation.get("min_length")
        max_length = validation.get("max_length")

        if (
            minimum is not None
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value < minimum
        ):
            raise ValueError(
                f"Значення не може бути меншим за {minimum}."
            )

        if (
            maximum is not None
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > maximum
        ):
            raise ValueError(
                f"Значення не може бути більшим за {maximum}."
            )

        if choices is not None and value not in choices:
            raise ValueError(
                "Значення відсутнє у списку дозволених варіантів."
            )

        if (
            min_length is not None
            and hasattr(value, "__len__")
            and len(value) < min_length
        ):
            raise ValueError(
                f"Мінімальна довжина: {min_length}."
            )

        if (
            max_length is not None
            and hasattr(value, "__len__")
            and len(value) > max_length
        ):
            raise ValueError(
                f"Максимальна довжина: {max_length}."
            )

    # ==========================================
    # ЗМІНА ЗНАЧЕННЯ
    # ==========================================

    def set_value(
        self,
        *,
        value: Any,
        updated_by_id: int,
        changed_at: datetime,
        reason: str | None = None,
    ) -> None:
        """Змінює поточне значення налаштування."""

        if not self.is_editable:
            raise ValueError(
                "Це налаштування заборонено редагувати."
            )

        if not self.is_active:
            raise ValueError(
                "Неактивне налаштування не можна змінювати."
            )

        if changed_at.tzinfo is None:
            raise ValueError(
                "changed_at повинен містити часовий пояс."
            )

        self.validate_value(
            value=value,
            value_type=self.value_type,
            validation=self.validation_json,
        )

        self.value_json = deepcopy(value)
        self.updated_by_id = updated_by_id
        self.value_changed_at = changed_at
        self.change_reason = (
            reason.strip()
            if reason
            else None
        )

    def reset_to_default(
        self,
        *,
        updated_by_id: int,
        changed_at: datetime,
        reason: str | None = None,
    ) -> None:
        """Повертає стандартне значення."""

        if self.default_value_json is None:
            raise ValueError(
                "Для цього налаштування немає стандартного значення."
            )

        self.set_value(
            value=deepcopy(
                self.default_value_json
            ),
            updated_by_id=updated_by_id,
            changed_at=changed_at,
            reason=(
                reason
                or "Повернення стандартного значення"
            ),
        )

    # ==========================================
    # АКТИВАЦІЯ
    # ==========================================

    def activate(self) -> None:
        """Активує налаштування."""

        self.is_active = True

    def deactivate(self) -> None:
        """Вимикає налаштування без видалення."""

        self.is_active = False

    # ==========================================
    # ОТРИМАННЯ ЗНАЧЕННЯ
    # ==========================================

    def get_value(self) -> Any:
        """Повертає копію поточного значення."""

        return deepcopy(self.value_json)

    def get_public_value(self) -> Any:
        """Повертає значення для адмін-інтерфейсу."""

        if self.is_secret:
            return "••••••••"

        return self.get_value()

    # ==========================================
    # PROPERTIES
    # ==========================================

    @property
    def display_value(self) -> str:
        """Форматує значення для Telegram."""

        if self.is_secret:
            return "••••••••"

        value = self.value_json

        if value is None:
            return "Не вказано"

        if isinstance(value, bool):
            return "Увімкнено" if value else "Вимкнено"

        if isinstance(value, list):
            if not value:
                return "Порожній список"

            return ", ".join(
                str(item)
                for item in value
            )

        if isinstance(value, dict):
            if not value:
                return "Порожній словник"

            return "; ".join(
                f"{key}: {item}"
                for key, item in value.items()
            )

        return str(value)

    @property
    def category_display_name(self) -> str:
        """Назва категорії українською."""

        names = {
            "general": "Загальні",
            "opening": "Відкриття",
            "closing": "Закриття",
            "notifications": "Сповіщення",
            "reports": "Звіти",
            "telegram": "Telegram",
            "access": "Доступ",
            "security": "Безпека",
        }

        return names.get(
            self.category,
            self.category.capitalize(),
        )

    @property
    def requires_restart_text(self) -> str:
        if self.requires_restart:
            return "Потрібен перезапуск"

        return "Застосовується одразу"