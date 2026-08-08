from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    String,
    cast,
    func,
    or_,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import InstrumentedAttribute

from app.database.models.system_setting import (
    SystemSetting,
)
from app.repositories.base import BaseRepository


@dataclass(slots=True, frozen=True)
class SettingDefinition:
    """
    Опис стандартного системного налаштування.
    """

    key: str
    default_value: Any

    description: str
    category: str

    is_public: bool = False
    is_secret: bool = False


@dataclass(slots=True, frozen=True)
class SettingUpdateResult:
    """
    Результат створення або оновлення налаштування.
    """

    setting: SystemSetting

    old_value: Any
    new_value: Any

    was_created: bool
    was_changed: bool


class SystemSettingRepository(
    BaseRepository[SystemSetting]
):
    """
    Репозиторій системних налаштувань.

    Налаштування зберігаються у PostgreSQL,
    тому їх можна змінювати без повторного
    деплою Telegram-бота.

    Приклади:

    - режим технічних робіт;
    - увімкнення ранкового контролю;
    - увімкнення вечірнього контролю;
    - Telegram-групи;
    - кількість повторних спроб;
    - часовий пояс;
    - робота живих підсумків.
    """

    model = SystemSetting

    # ==========================================
    # КЛЮЧІ НАЛАШТУВАНЬ
    # ==========================================

    BOT_ENABLED = "bot.enabled"
    MAINTENANCE_MODE = "bot.maintenance_mode"
    MAINTENANCE_MESSAGE = "bot.maintenance_message"

    DEFAULT_TIMEZONE = "bot.default_timezone"

    OPENING_CONTROL_ENABLED = (
        "opening.control_enabled"
    )

    OPENING_NOTIFICATIONS_ENABLED = (
        "opening.notifications_enabled"
    )

    OPENING_SUMMARIES_ENABLED = (
        "opening.summaries_enabled"
    )

    OPENING_DEFAULT_DEADLINE_MINUTES = (
        "opening.default_deadline_minutes"
    )

    CLOSING_CONTROL_ENABLED = (
        "closing.control_enabled"
    )

    CLOSING_NOTIFICATIONS_ENABLED = (
        "closing.notifications_enabled"
    )

    CLOSING_SUMMARIES_ENABLED = (
        "closing.summaries_enabled"
    )

    CLOSING_DEFAULT_DEADLINE_MINUTES = (
        "closing.default_deadline_minutes"
    )

    CLOSING_REQUIRE_RECEIPT = (
        "closing.require_receipt"
    )

    CONTROL_GROUP_ID = "telegram.control_group_id"
    CLOSING_GROUP_ID = "telegram.closing_group_id"

    NETWORK_SUMMARY_TOPIC_ID = (
        "telegram.network_summary_topic_id"
    )

    NOTIFICATION_MAX_ATTEMPTS = (
        "notifications.max_attempts"
    )

    NOTIFICATION_RETRY_DELAY_SECONDS = (
        "notifications.retry_delay_seconds"
    )

    LIVE_SUMMARY_UPDATES_ENABLED = (
        "summaries.live_updates_enabled"
    )

    EXCEL_REPORTS_ENABLED = (
        "reports.excel_enabled"
    )

    DAILY_REPORTS_ENABLED = (
        "reports.daily_enabled"
    )

    WEEKLY_REPORTS_ENABLED = (
        "reports.weekly_enabled"
    )

    MONTHLY_REPORTS_ENABLED = (
        "reports.monthly_enabled"
    )

    REQUIRE_STORE_APPROVAL = (
        "access.require_store_approval"
    )

    # ==========================================
    # СТАНДАРТНІ ЗНАЧЕННЯ
    # ==========================================

    DEFAULT_SETTINGS: tuple[
        SettingDefinition,
        ...,
    ] = (
        SettingDefinition(
            key=BOT_ENABLED,
            default_value=True,
            description=(
                "Глобальне увімкнення Telegram-бота"
            ),
            category="bot",
            is_public=True,
        ),
        SettingDefinition(
            key=MAINTENANCE_MODE,
            default_value=False,
            description=(
                "Режим технічного обслуговування"
            ),
            category="bot",
            is_public=True,
        ),
        SettingDefinition(
            key=MAINTENANCE_MESSAGE,
            default_value=(
                "⚙️ Бот тимчасово на технічному "
                "обслуговуванні. Спробуйте пізніше."
            ),
            description=(
                "Повідомлення під час технічних робіт"
            ),
            category="bot",
            is_public=True,
        ),
        SettingDefinition(
            key=DEFAULT_TIMEZONE,
            default_value="Europe/Kyiv",
            description=(
                "Стандартний часовий пояс системи"
            ),
            category="bot",
            is_public=True,
        ),
        SettingDefinition(
            key=OPENING_CONTROL_ENABLED,
            default_value=True,
            description=(
                "Увімкнення ранкового контролю ТТ"
            ),
            category="opening",
        ),
        SettingDefinition(
            key=OPENING_NOTIFICATIONS_ENABLED,
            default_value=True,
            description=(
                "Сповіщення про невідкриті ТТ"
            ),
            category="opening",
        ),
        SettingDefinition(
            key=OPENING_SUMMARIES_ENABLED,
            default_value=True,
            description=(
                "Живі ранкові підсумки"
            ),
            category="opening",
        ),
        SettingDefinition(
            key=OPENING_DEFAULT_DEADLINE_MINUTES,
            default_value=10,
            description=(
                "Стандартний дедлайн відкриття "
                "у хвилинах"
            ),
            category="opening",
        ),
        SettingDefinition(
            key=CLOSING_CONTROL_ENABLED,
            default_value=True,
            description=(
                "Увімкнення вечірнього контролю ТТ"
            ),
            category="closing",
        ),
        SettingDefinition(
            key=CLOSING_NOTIFICATIONS_ENABLED,
            default_value=True,
            description=(
                "Сповіщення про неподані вечірні звіти"
            ),
            category="closing",
        ),
        SettingDefinition(
            key=CLOSING_SUMMARIES_ENABLED,
            default_value=True,
            description=(
                "Живі вечірні підсумки"
            ),
            category="closing",
        ),
        SettingDefinition(
            key=CLOSING_DEFAULT_DEADLINE_MINUTES,
            default_value=10,
            description=(
                "Стандартний дедлайн вечірнього звіту "
                "у хвилинах"
            ),
            category="closing",
        ),
        SettingDefinition(
            key=CLOSING_REQUIRE_RECEIPT,
            default_value=True,
            description=(
                "Обов’язкове фото чека під час закриття"
            ),
            category="closing",
        ),
        SettingDefinition(
            key=CONTROL_GROUP_ID,
            default_value=None,
            description=(
                "Telegram ID групи ранкового контролю"
            ),
            category="telegram",
        ),
        SettingDefinition(
            key=CLOSING_GROUP_ID,
            default_value=None,
            description=(
                "Telegram ID групи вечірніх звітів"
            ),
            category="telegram",
        ),
        SettingDefinition(
            key=NETWORK_SUMMARY_TOPIC_ID,
            default_value=None,
            description=(
                "Telegram topic ID загального підсумку"
            ),
            category="telegram",
        ),
        SettingDefinition(
            key=NOTIFICATION_MAX_ATTEMPTS,
            default_value=5,
            description=(
                "Максимальна кількість спроб "
                "надсилання повідомлення"
            ),
            category="notifications",
        ),
        SettingDefinition(
            key=NOTIFICATION_RETRY_DELAY_SECONDS,
            default_value=60,
            description=(
                "Затримка між повторними спробами"
            ),
            category="notifications",
        ),
        SettingDefinition(
            key=LIVE_SUMMARY_UPDATES_ENABLED,
            default_value=True,
            description=(
                "Редагування живих Telegram-підсумків"
            ),
            category="summaries",
        ),
        SettingDefinition(
            key=EXCEL_REPORTS_ENABLED,
            default_value=True,
            description=(
                "Створення Excel-звітів"
            ),
            category="reports",
        ),
        SettingDefinition(
            key=DAILY_REPORTS_ENABLED,
            default_value=True,
            description=(
                "Щоденні звіти"
            ),
            category="reports",
        ),
        SettingDefinition(
            key=WEEKLY_REPORTS_ENABLED,
            default_value=True,
            description=(
                "Щотижневі звіти"
            ),
            category="reports",
        ),
        SettingDefinition(
            key=MONTHLY_REPORTS_ENABLED,
            default_value=True,
            description=(
                "Щомісячні звіти"
            ),
            category="reports",
        ),
        SettingDefinition(
            key=REQUIRE_STORE_APPROVAL,
            default_value=True,
            description=(
                "Підтвердження працівника "
                "перед доступом до ТТ"
            ),
            category="access",
        ),
    )

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(session)

    # ==========================================
    # ПОШУК ЗА КЛЮЧЕМ
    # ==========================================

    async def get_by_key(
        self,
        key: str,
        *,
        for_update: bool = False,
    ) -> SystemSetting | None:
        """Повертає налаштування за ключем."""

        normalized_key = self.normalize_key(key)

        statement = (
            select(SystemSetting)
            .where(
                SystemSetting.key == normalized_key
            )
            .limit(1)
        )

        if for_update:
            statement = statement.with_for_update(
                of=SystemSetting
            )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_key_or_raise(
        self,
        key: str,
        *,
        for_update: bool = False,
    ) -> SystemSetting:
        """Повертає налаштування або помилку."""

        setting = await self.get_by_key(
            key,
            for_update=for_update,
        )

        if setting is None:
            raise ValueError(
                f"Налаштування «{key}» не знайдено."
            )

        return setting

    async def exists(
        self,
        key: str,
    ) -> bool:
        """Перевіряє існування налаштування."""

        normalized_key = self.normalize_key(key)

        statement = select(
            select(SystemSetting.id)
            .where(
                SystemSetting.key
                == normalized_key
            )
            .exists()
        )

        result = await self.session.scalar(
            statement
        )

        return bool(result)

    # ==========================================
    # ОТРИМАННЯ ЗНАЧЕННЯ
    # ==========================================

    async def get_value(
        self,
        key: str,
        *,
        default: Any = None,
    ) -> Any:
        """Повертає значення або default."""

        setting = await self.get_by_key(key)

        if setting is None:
            return default

        return self.read_setting_value(
            setting
        )

    async def require_value(
        self,
        key: str,
    ) -> Any:
        """Повертає обов’язкове значення."""

        setting = await self.get_by_key_or_raise(
            key
        )

        value = self.read_setting_value(
            setting
        )

        if value is None:
            raise ValueError(
                f"Налаштування «{key}» не має значення."
            )

        return value

    async def get_bool(
        self,
        key: str,
        *,
        default: bool = False,
    ) -> bool:
        """Повертає логічне значення."""

        value = await self.get_value(
            key,
            default=default,
        )

        if isinstance(value, bool):
            return value

        if isinstance(value, int):
            return value != 0

        if isinstance(value, str):
            normalized_value = (
                value.strip().lower()
            )

            if normalized_value in {
                "true",
                "1",
                "yes",
                "on",
                "enabled",
                "так",
                "увімкнено",
            }:
                return True

            if normalized_value in {
                "false",
                "0",
                "no",
                "off",
                "disabled",
                "ні",
                "вимкнено",
            }:
                return False

        raise ValueError(
            f"Налаштування «{key}» не є "
            "логічним значенням."
        )

    async def get_int(
        self,
        key: str,
        *,
        default: int | None = None,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int | None:
        """Повертає ціле число."""

        value = await self.get_value(
            key,
            default=default,
        )

        if value is None:
            return None

        if isinstance(value, bool):
            raise ValueError(
                f"Налаштування «{key}» не є числом."
            )

        try:
            result = int(value)

        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Налаштування «{key}» не є "
                "цілим числом."
            ) from error

        if minimum is not None and result < minimum:
            raise ValueError(
                f"Значення «{key}» не може бути "
                f"меншим за {minimum}."
            )

        if maximum is not None and result > maximum:
            raise ValueError(
                f"Значення «{key}» не може бути "
                f"більшим за {maximum}."
            )

        return result

    async def get_float(
        self,
        key: str,
        *,
        default: float | None = None,
    ) -> float | None:
        """Повертає число з дробовою частиною."""

        value = await self.get_value(
            key,
            default=default,
        )

        if value is None:
            return None

        if isinstance(value, bool):
            raise ValueError(
                f"Налаштування «{key}» не є числом."
            )

        try:
            return float(value)

        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Налаштування «{key}» не є числом."
            ) from error

    async def get_string(
        self,
        key: str,
        *,
        default: str | None = None,
        allow_empty: bool = False,
    ) -> str | None:
        """Повертає текстове значення."""

        value = await self.get_value(
            key,
            default=default,
        )

        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError(
                f"Налаштування «{key}» не є текстом."
            )

        result = value.strip()

        if not result and not allow_empty:
            return default

        return result

    async def get_list(
        self,
        key: str,
        *,
        default: list[Any] | None = None,
    ) -> list[Any]:
        """Повертає список."""

        value = await self.get_value(
            key,
            default=default or [],
        )

        if not isinstance(value, list):
            raise ValueError(
                f"Налаштування «{key}» не є списком."
            )

        return value

    async def get_dict(
        self,
        key: str,
        *,
        default: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Повертає словник."""

        value = await self.get_value(
            key,
            default=default or {},
        )

        if not isinstance(value, dict):
            raise ValueError(
                f"Налаштування «{key}» не є словником."
            )

        return value

    # ==========================================
    # СТВОРЕННЯ ТА ОНОВЛЕННЯ
    # ==========================================

    async def set_value(
        self,
        *,
        key: str,
        value: Any,
        updated_by_id: int | None = None,
        description: str | None = None,
        category: str | None = None,
        is_public: bool | None = None,
        is_secret: bool | None = None,
        update_description: bool = False,
        update_category: bool = False,
    ) -> SettingUpdateResult:
        """
        Створює або оновлює налаштування.

        Сирі секрети не повинні передаватися
        у публічні налаштування.
        """

        normalized_key = self.normalize_key(key)

        if updated_by_id is not None:
            self.validate_positive_id(
                updated_by_id,
                field_name="ID користувача",
            )

        serialized_value = self.serialize_value(
            value
        )

        setting = await self.get_by_key(
            normalized_key,
            for_update=True,
        )

        if setting is not None:
            old_value = self.read_setting_value(
                setting
            )

            was_changed = (
                old_value != serialized_value
            )

            if was_changed:
                self.write_setting_value(
                    setting,
                    serialized_value,
                )

            if update_description:
                self.set_first_available_value(
                    setting,
                    names=("description",),
                    value=(
                        self.normalize_optional_text(
                            description
                        )
                    ),
                )

            if update_category:
                self.set_first_available_value(
                    setting,
                    names=("category", "group_name"),
                    value=(
                        self.normalize_optional_text(
                            category
                        )
                    ),
                )

            if is_public is not None:
                self.set_first_available_value(
                    setting,
                    names=("is_public",),
                    value=is_public,
                )

            if is_secret is not None:
                self.set_first_available_value(
                    setting,
                    names=("is_secret",),
                    value=is_secret,
                )

            if updated_by_id is not None:
                self.set_first_available_value(
                    setting,
                    names=(
                        "updated_by_id",
                        "modified_by_id",
                    ),
                    value=updated_by_id,
                )

            self.session.add(setting)
            await self.session.flush()

            return SettingUpdateResult(
                setting=setting,
                old_value=old_value,
                new_value=serialized_value,
                was_created=False,
                was_changed=was_changed,
            )

        payload: dict[str, Any] = {
            "key": normalized_key,
        }

        value_field_name = (
            self.get_value_field_name()
        )

        payload[value_field_name] = (
            self.encode_for_value_field(
                field_name=value_field_name,
                value=serialized_value,
            )
        )

        self.put_optional_payload_value(
            payload,
            names=("description",),
            value=self.normalize_optional_text(
                description
            ),
        )

        self.put_optional_payload_value(
            payload,
            names=("category", "group_name"),
            value=self.normalize_optional_text(
                category
            ),
        )

        self.put_optional_payload_value(
            payload,
            names=("is_public",),
            value=bool(is_public),
        )

        self.put_optional_payload_value(
            payload,
            names=("is_secret",),
            value=bool(is_secret),
        )

        self.put_optional_payload_value(
            payload,
            names=(
                "created_by_id",
                "updated_by_id",
                "modified_by_id",
            ),
            value=updated_by_id,
        )

        setting = SystemSetting(**payload)

        try:
            async with self.session.begin_nested():
                self.session.add(setting)
                await self.session.flush()

            return SettingUpdateResult(
                setting=setting,
                old_value=None,
                new_value=serialized_value,
                was_created=True,
                was_changed=True,
            )

        except IntegrityError:
            setting = await self.get_by_key_or_raise(
                normalized_key,
                for_update=True,
            )

            old_value = self.read_setting_value(
                setting
            )

            was_changed = (
                old_value != serialized_value
            )

            if was_changed:
                self.write_setting_value(
                    setting,
                    serialized_value,
                )

            if updated_by_id is not None:
                self.set_first_available_value(
                    setting,
                    names=(
                        "updated_by_id",
                        "modified_by_id",
                    ),
                    value=updated_by_id,
                )

            self.session.add(setting)
            await self.session.flush()

            return SettingUpdateResult(
                setting=setting,
                old_value=old_value,
                new_value=serialized_value,
                was_created=False,
                was_changed=was_changed,
            )

    async def set_bool(
        self,
        *,
        key: str,
        value: bool,
        updated_by_id: int | None = None,
    ) -> SettingUpdateResult:
        """Зберігає логічне значення."""

        return await self.set_value(
            key=key,
            value=bool(value),
            updated_by_id=updated_by_id,
        )

    async def set_int(
        self,
        *,
        key: str,
        value: int,
        updated_by_id: int | None = None,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> SettingUpdateResult:
        """Зберігає ціле число."""

        if isinstance(value, bool):
            raise ValueError(
                "Логічне значення не можна "
                "зберегти як число."
            )

        if minimum is not None and value < minimum:
            raise ValueError(
                f"Значення не може бути меншим "
                f"за {minimum}."
            )

        if maximum is not None and value > maximum:
            raise ValueError(
                f"Значення не може бути більшим "
                f"за {maximum}."
            )

        return await self.set_value(
            key=key,
            value=value,
            updated_by_id=updated_by_id,
        )

    async def toggle_bool(
        self,
        *,
        key: str,
        updated_by_id: int | None = None,
        default: bool = False,
    ) -> SettingUpdateResult:
        """Перемикає логічне налаштування."""

        current_value = await self.get_bool(
            key,
            default=default,
        )

        return await self.set_bool(
            key=key,
            value=not current_value,
            updated_by_id=updated_by_id,
        )

    # ==========================================
    # МАСОВІ ОПЕРАЦІЇ
    # ==========================================

    async def set_many(
        self,
        values: Mapping[str, Any],
        *,
        updated_by_id: int | None = None,
    ) -> list[SettingUpdateResult]:
        """Створює або оновлює декілька значень."""

        results: list[
            SettingUpdateResult
        ] = []

        for key, value in values.items():
            result = await self.set_value(
                key=key,
                value=value,
                updated_by_id=updated_by_id,
            )

            results.append(result)

        return results

    async def get_many(
        self,
        keys: Sequence[str],
        *,
        include_missing: bool = False,
    ) -> dict[str, Any]:
        """Повертає декілька налаштувань."""

        normalized_keys = {
            self.normalize_key(key)
            for key in keys
        }

        if not normalized_keys:
            return {}

        statement = (
            select(SystemSetting)
            .where(
                SystemSetting.key.in_(
                    normalized_keys
                )
            )
            .order_by(
                SystemSetting.key.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        settings = list(
            result.unique().all()
        )

        values = {
            setting.key: self.read_setting_value(
                setting
            )
            for setting in settings
        }

        if include_missing:
            for key in normalized_keys:
                values.setdefault(key, None)

        return values

    # ==========================================
    # СТАНДАРТНІ НАЛАШТУВАННЯ
    # ==========================================

    async def create_default_settings(
        self,
        *,
        created_by_id: int | None = None,
    ) -> list[SystemSetting]:
        """
        Створює відсутні стандартні налаштування.

        Уже існуючі значення не перезаписуються.
        """

        created_settings: list[
            SystemSetting
        ] = []

        for definition in self.DEFAULT_SETTINGS:
            existing = await self.get_by_key(
                definition.key
            )

            if existing is not None:
                continue

            result = await self.set_value(
                key=definition.key,
                value=definition.default_value,
                updated_by_id=created_by_id,
                description=definition.description,
                category=definition.category,
                is_public=definition.is_public,
                is_secret=definition.is_secret,
                update_description=True,
                update_category=True,
            )

            if result.was_created:
                created_settings.append(
                    result.setting
                )

        return created_settings

    async def reset_to_default(
        self,
        *,
        key: str,
        updated_by_id: int | None = None,
    ) -> SettingUpdateResult:
        """Повертає налаштування до стандарту."""

        normalized_key = self.normalize_key(key)

        definition = next(
            (
                item
                for item in self.DEFAULT_SETTINGS
                if item.key == normalized_key
            ),
            None,
        )

        if definition is None:
            raise ValueError(
                f"Для налаштування «{key}» "
                "не визначено стандартне значення."
            )

        return await self.set_value(
            key=definition.key,
            value=definition.default_value,
            updated_by_id=updated_by_id,
            description=definition.description,
            category=definition.category,
            is_public=definition.is_public,
            is_secret=definition.is_secret,
            update_description=True,
            update_category=True,
        )

    # ==========================================
    # РЕЖИМ ТЕХНІЧНИХ РОБІТ
    # ==========================================

    async def is_bot_enabled(
        self,
    ) -> bool:
        """Чи увімкнений Telegram-бот."""

        return await self.get_bool(
            self.BOT_ENABLED,
            default=True,
        )

    async def is_maintenance_mode(
        self,
    ) -> bool:
        """Чи увімкнений режим обслуговування."""

        return await self.get_bool(
            self.MAINTENANCE_MODE,
            default=False,
        )

    async def set_maintenance_mode(
        self,
        *,
        enabled: bool,
        updated_by_id: int,
        message: str | None = None,
    ) -> list[SettingUpdateResult]:
        """Вмикає або вимикає технічний режим."""

        results = [
            await self.set_bool(
                key=self.MAINTENANCE_MODE,
                value=enabled,
                updated_by_id=updated_by_id,
            )
        ]

        if message is not None:
            normalized_message = (
                self.normalize_required_text(
                    message,
                    field_name=(
                        "Повідомлення технічного режиму"
                    ),
                )
            )

            results.append(
                await self.set_value(
                    key=self.MAINTENANCE_MESSAGE,
                    value=normalized_message,
                    updated_by_id=updated_by_id,
                )
            )

        return results

    async def get_maintenance_message(
        self,
    ) -> str:
        """Повертає повідомлення технічного режиму."""

        message = await self.get_string(
            self.MAINTENANCE_MESSAGE,
            default=(
                "⚙️ Бот тимчасово на технічному "
                "обслуговуванні."
            ),
        )

        return message or (
            "⚙️ Бот тимчасово на технічному "
            "обслуговуванні."
        )

    # ==========================================
    # РОБОЧІ ПАРАМЕТРИ
    # ==========================================

    async def get_default_timezone(
        self,
    ) -> str:
        """Повертає стандартний часовий пояс."""

        timezone = await self.get_string(
            self.DEFAULT_TIMEZONE,
            default="Europe/Kyiv",
        )

        return timezone or "Europe/Kyiv"

    async def get_opening_deadline_minutes(
        self,
    ) -> int:
        """Повертає стандартний дедлайн відкриття."""

        value = await self.get_int(
            self.OPENING_DEFAULT_DEADLINE_MINUTES,
            default=10,
            minimum=0,
            maximum=180,
        )

        return value if value is not None else 10

    async def get_closing_deadline_minutes(
        self,
    ) -> int:
        """Повертає стандартний дедлайн закриття."""

        value = await self.get_int(
            self.CLOSING_DEFAULT_DEADLINE_MINUTES,
            default=10,
            minimum=0,
            maximum=180,
        )

        return value if value is not None else 10

    async def get_notification_max_attempts(
        self,
    ) -> int:
        """Повертає кількість спроб Telegram API."""

        value = await self.get_int(
            self.NOTIFICATION_MAX_ATTEMPTS,
            default=5,
            minimum=1,
            maximum=50,
        )

        return value if value is not None else 5

    async def get_notification_retry_delay(
        self,
    ) -> int:
        """Повертає затримку повторної спроби."""

        value = await self.get_int(
            self.NOTIFICATION_RETRY_DELAY_SECONDS,
            default=60,
            minimum=10,
            maximum=3600,
        )

        return value if value is not None else 60

    async def get_control_group_id(
        self,
    ) -> int | None:
        """Повертає ID групи ранкового контролю."""

        return await self.get_int(
            self.CONTROL_GROUP_ID,
            default=None,
        )

    async def get_closing_group_id(
        self,
    ) -> int | None:
        """Повертає ID групи вечірніх звітів."""

        return await self.get_int(
            self.CLOSING_GROUP_ID,
            default=None,
        )

    # ==========================================
    # ПОВНА КОНФІГУРАЦІЯ
    # ==========================================

    async def get_runtime_configuration(
        self,
    ) -> dict[str, Any]:
        """
        Повертає основні параметри для scheduler
        та Telegram-handlers.
        """

        return {
            "bot_enabled": (
                await self.is_bot_enabled()
            ),
            "maintenance_mode": (
                await self.is_maintenance_mode()
            ),
            "maintenance_message": (
                await self.get_maintenance_message()
            ),
            "timezone": (
                await self.get_default_timezone()
            ),
            "opening_control_enabled": (
                await self.get_bool(
                    self.OPENING_CONTROL_ENABLED,
                    default=True,
                )
            ),
            "opening_notifications_enabled": (
                await self.get_bool(
                    self.OPENING_NOTIFICATIONS_ENABLED,
                    default=True,
                )
            ),
            "opening_summaries_enabled": (
                await self.get_bool(
                    self.OPENING_SUMMARIES_ENABLED,
                    default=True,
                )
            ),
            "opening_deadline_minutes": (
                await self.get_opening_deadline_minutes()
            ),
            "closing_control_enabled": (
                await self.get_bool(
                    self.CLOSING_CONTROL_ENABLED,
                    default=True,
                )
            ),
            "closing_notifications_enabled": (
                await self.get_bool(
                    self.CLOSING_NOTIFICATIONS_ENABLED,
                    default=True,
                )
            ),
            "closing_summaries_enabled": (
                await self.get_bool(
                    self.CLOSING_SUMMARIES_ENABLED,
                    default=True,
                )
            ),
            "closing_deadline_minutes": (
                await self.get_closing_deadline_minutes()
            ),
            "closing_require_receipt": (
                await self.get_bool(
                    self.CLOSING_REQUIRE_RECEIPT,
                    default=True,
                )
            ),
            "control_group_id": (
                await self.get_control_group_id()
            ),
            "closing_group_id": (
                await self.get_closing_group_id()
            ),
            "notification_max_attempts": (
                await self.get_notification_max_attempts()
            ),
            "notification_retry_delay_seconds": (
                await self.get_notification_retry_delay()
            ),
            "live_summary_updates_enabled": (
                await self.get_bool(
                    self.LIVE_SUMMARY_UPDATES_ENABLED,
                    default=True,
                )
            ),
            "excel_reports_enabled": (
                await self.get_bool(
                    self.EXCEL_REPORTS_ENABLED,
                    default=True,
                )
            ),
            "require_store_approval": (
                await self.get_bool(
                    self.REQUIRE_STORE_APPROVAL,
                    default=True,
                )
            ),
        }

    # ==========================================
    # СПИСКИ
    # ==========================================

    async def get_all_settings(
        self,
        *,
        include_secret: bool = False,
    ) -> list[SystemSetting]:
        """Повертає всі системні налаштування."""

        conditions = []

        secret_field = self.get_model_attribute(
            "is_secret"
        )

        if (
            not include_secret
            and secret_field is not None
        ):
            conditions.append(
                secret_field.is_(False)
            )

        statement = (
            select(SystemSetting)
            .where(*conditions)
            .order_by(
                SystemSetting.key.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_by_prefix(
        self,
        prefix: str,
        *,
        include_secret: bool = False,
    ) -> list[SystemSetting]:
        """Повертає налаштування за префіксом."""

        normalized_prefix = (
            self.normalize_prefix(prefix)
        )

        conditions = [
            SystemSetting.key.like(
                f"{normalized_prefix}%"
            )
        ]

        secret_field = self.get_model_attribute(
            "is_secret"
        )

        if (
            not include_secret
            and secret_field is not None
        ):
            conditions.append(
                secret_field.is_(False)
            )

        statement = (
            select(SystemSetting)
            .where(*conditions)
            .order_by(
                SystemSetting.key.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_by_category(
        self,
        category: str,
        *,
        include_secret: bool = False,
    ) -> list[SystemSetting]:
        """Повертає налаштування категорії."""

        normalized_category = (
            self.normalize_required_text(
                category,
                field_name="Категорія",
            ).lower()
        )

        category_field = self.get_model_attribute(
            "category",
            "group_name",
        )

        if category_field is None:
            return await self.get_by_prefix(
                f"{normalized_category}.",
                include_secret=include_secret,
            )

        conditions = [
            func.lower(category_field)
            == normalized_category
        ]

        secret_field = self.get_model_attribute(
            "is_secret"
        )

        if (
            not include_secret
            and secret_field is not None
        ):
            conditions.append(
                secret_field.is_(False)
            )

        statement = (
            select(SystemSetting)
            .where(*conditions)
            .order_by(
                SystemSetting.key.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ПОШУК
    # ==========================================

    async def search(
        self,
        query: str,
        *,
        include_secret: bool = False,
        limit: int = 100,
    ) -> list[SystemSetting]:
        """Шукає налаштування за ключем або описом."""

        normalized_query = query.strip()

        if not normalized_query:
            return []

        self.validate_limit(
            limit,
            maximum=1000,
        )

        search_pattern = (
            f"%{normalized_query}%"
        )

        search_conditions = [
            SystemSetting.key.ilike(
                search_pattern
            )
        ]

        for field_name in (
            "description",
            "category",
            "group_name",
        ):
            field = self.get_model_attribute(
                field_name
            )

            if field is not None:
                search_conditions.append(
                    cast(field, String).ilike(
                        search_pattern
                    )
                )

        conditions = [
            or_(*search_conditions)
        ]

        secret_field = self.get_model_attribute(
            "is_secret"
        )

        if (
            not include_secret
            and secret_field is not None
        ):
            conditions.append(
                secret_field.is_(False)
            )

        statement = (
            select(SystemSetting)
            .where(*conditions)
            .order_by(
                SystemSetting.key.asc()
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ЕКСПОРТ
    # ==========================================

    async def export_values(
        self,
        *,
        include_secret: bool = False,
    ) -> dict[str, Any]:
        """Повертає налаштування у вигляді словника."""

        settings = await self.get_all_settings(
            include_secret=include_secret
        )

        result: dict[str, Any] = {}

        for setting in settings:
            is_secret = bool(
                self.get_first_available_value(
                    setting,
                    names=("is_secret",),
                    default=False,
                )
            )

            if is_secret and not include_secret:
                continue

            result[setting.key] = (
                self.read_setting_value(
                    setting
                )
            )

        return result

    # ==========================================
    # ВИДАЛЕННЯ
    # ==========================================

    async def delete_by_key(
        self,
        key: str,
    ) -> bool:
        """Видаляє нестандартне налаштування."""

        setting = await self.get_by_key(
            key,
            for_update=True,
        )

        if setting is None:
            return False

        await self.session.delete(setting)
        await self.session.flush()

        return True

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def count_all(
        self,
    ) -> int:
        """Підраховує всі налаштування."""

        result = await self.session.scalar(
            select(
                func.count(SystemSetting.id)
            )
        )

        return int(result or 0)

    async def count_by_category(
        self,
    ) -> dict[str, int]:
        """Підраховує налаштування по категоріях."""

        category_field = self.get_model_attribute(
            "category",
            "group_name",
        )

        if category_field is not None:
            statement = (
                select(
                    category_field,
                    func.count(
                        SystemSetting.id
                    ),
                )
                .group_by(category_field)
                .order_by(category_field.asc())
            )

            result = await self.session.execute(
                statement
            )

            return {
                str(category or "other"): int(count)
                for category, count in result.all()
            }

        settings = await self.get_all_settings(
            include_secret=True
        )

        counts: dict[str, int] = {}

        for setting in settings:
            category = (
                setting.key.split(".", 1)[0]
                if "." in setting.key
                else "other"
            )

            counts[category] = (
                counts.get(category, 0) + 1
            )

        return counts

    # ==========================================
    # ЧИТАННЯ ТА ЗАПИС ЗНАЧЕННЯ
    # ==========================================

    @classmethod
    def get_value_field_name(
        cls,
    ) -> str:
        """Повертає поле, де зберігається значення."""

        available_fields = (
            cls.mapped_column_names()
        )

        for field_name in (
            "value_json",
            "setting_value",
            "value",
            "payload_json",
        ):
            if field_name in available_fields:
                return field_name

        raise RuntimeError(
            "У моделі SystemSetting відсутнє "
            "поле для збереження значення."
        )

    @classmethod
    def read_setting_value(
        cls,
        setting: SystemSetting,
    ) -> Any:
        """Читає значення з моделі."""

        field_name = cls.get_value_field_name()

        raw_value = getattr(
            setting,
            field_name,
            None,
        )

        if (
            isinstance(raw_value, dict)
            and raw_value.get(
                "__system_setting__"
            )
            == 1
        ):
            return raw_value.get("value")

        if (
            isinstance(raw_value, dict)
            and set(raw_value.keys())
            == {"value"}
        ):
            return raw_value["value"]

        return raw_value

    @classmethod
    def write_setting_value(
        cls,
        setting: SystemSetting,
        value: Any,
    ) -> None:
        """Записує значення у модель."""

        field_name = cls.get_value_field_name()

        encoded_value = cls.encode_for_value_field(
            field_name=field_name,
            value=value,
        )

        setattr(
            setting,
            field_name,
            encoded_value,
        )

    @staticmethod
    def encode_for_value_field(
        *,
        field_name: str,
        value: Any,
    ) -> Any:
        """
        Для JSON-поля використовуємо оболонку.

        Це дозволяє однаково зберігати:
        - текст;
        - число;
        - bool;
        - список;
        - словник;
        - None.
        """

        if field_name.endswith("_json"):
            return {
                "__system_setting__": 1,
                "value": value,
            }

        return value

    # ==========================================
    # JSON-СЕРІАЛІЗАЦІЯ
    # ==========================================

    @classmethod
    def serialize_value(
        cls,
        value: Any,
    ) -> Any:
        """Перетворює значення у JSON-сумісний формат."""

        if value is None:
            return None

        if isinstance(
            value,
            (
                str,
                int,
                float,
                bool,
            ),
        ):
            return value

        if isinstance(value, Decimal):
            return str(value)

        if isinstance(
            value,
            (date, datetime),
        ):
            return value.isoformat()

        if isinstance(value, UUID):
            return str(value)

        if isinstance(value, Enum):
            return value.value

        if isinstance(value, Mapping):
            return {
                str(key): cls.serialize_value(
                    nested_value
                )
                for key, nested_value
                in value.items()
            }

        if isinstance(
            value,
            (set, frozenset),
        ):
            return [
                cls.serialize_value(item)
                for item in sorted(
                    value,
                    key=str,
                )
            ]

        if isinstance(value, Sequence):
            return [
                cls.serialize_value(item)
                for item in value
            ]

        raise ValueError(
            "Значення неможливо зберегти "
            f"у системних налаштуваннях: "
            f"{type(value).__name__}."
        )

    # ==========================================
    # ДИНАМІЧНІ ПОЛЯ МОДЕЛІ
    # ==========================================

    @staticmethod
    def mapped_column_names(
        ) -> set[str]:
        """Повертає назви колонок моделі."""

        mapper = inspect(SystemSetting)

        return {
            attribute.key
            for attribute in mapper.column_attrs
        }

    @classmethod
    def put_optional_payload_value(
        cls,
        payload: dict[str, Any],
        *,
        names: tuple[str, ...],
        value: Any,
    ) -> bool:
        """Записує значення у перше доступне поле."""

        available_fields = (
            cls.mapped_column_names()
        )

        for field_name in names:
            if field_name not in available_fields:
                continue

            payload[field_name] = value
            return True

        return False

    @classmethod
    def set_first_available_value(
        cls,
        setting: SystemSetting,
        *,
        names: tuple[str, ...],
        value: Any,
    ) -> bool:
        """Встановлює перше доступне поле."""

        available_fields = (
            cls.mapped_column_names()
        )

        for field_name in names:
            if field_name not in available_fields:
                continue

            setattr(
                setting,
                field_name,
                value,
            )

            return True

        return False

    @classmethod
    def get_first_available_value(
        cls,
        setting: SystemSetting,
        *,
        names: tuple[str, ...],
        default: Any = None,
    ) -> Any:
        """Читає перше доступне поле."""

        available_fields = (
            cls.mapped_column_names()
        )

        for field_name in names:
            if field_name not in available_fields:
                continue

            return getattr(
                setting,
                field_name,
                default,
            )

        return default

    @staticmethod
    def get_model_attribute(
        *names: str,
    ) -> InstrumentedAttribute[Any] | None:
        """Повертає SQLAlchemy-поле."""

        for field_name in names:
            attribute = getattr(
                SystemSetting,
                field_name,
                None,
            )

            if isinstance(
                attribute,
                InstrumentedAttribute,
            ):
                return attribute

        return None

    # ==========================================
    # ВАЛІДАЦІЯ
    # ==========================================

    @staticmethod
    def normalize_key(
        key: str,
    ) -> str:
        """Нормалізує ключ налаштування."""

        normalized_key = (
            key.strip()
            .lower()
            .replace(" ", "_")
        )

        if not normalized_key:
            raise ValueError(
                "Ключ налаштування не може "
                "бути порожнім."
            )

        if len(normalized_key) > 150:
            raise ValueError(
                "Ключ налаштування занадто довгий."
            )

        allowed_characters = set(
            "abcdefghijklmnopqrstuvwxyz"
            "0123456789._-"
        )

        if any(
            character not in allowed_characters
            for character in normalized_key
        ):
            raise ValueError(
                "Ключ може містити лише латинські "
                "літери, цифри, крапку, дефіс "
                "та нижнє підкреслення."
            )

        return normalized_key

    @staticmethod
    def normalize_prefix(
        prefix: str,
    ) -> str:
        """Нормалізує префікс ключа."""

        normalized_prefix = (
            prefix.strip()
            .lower()
            .replace(" ", "_")
        )

        if not normalized_prefix:
            raise ValueError(
                "Префікс не може бути порожнім."
            )

        return normalized_prefix

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
    ) -> str:
        """Нормалізує обов’язковий текст."""

        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError(
                f"{field_name} не може бути порожнім."
            )

        return normalized_value

    @staticmethod
    def normalize_optional_text(
        value: str | None,
    ) -> str | None:
        """Нормалізує необов’язковий текст."""

        if value is None:
            return None

        normalized_value = value.strip()

        return normalized_value or None

    @staticmethod
    def validate_positive_id(
        value: int,
        *,
        field_name: str,
    ) -> None:
        """Перевіряє внутрішній ID."""

        if value <= 0:
            raise ValueError(
                f"{field_name} повинен бути "
                "більшим за нуль."
            )

    @staticmethod
    def validate_limit(
        limit: int,
        *,
        maximum: int,
    ) -> None:
        """Перевіряє обмеження вибірки."""

        if limit <= 0 or limit > maximum:
            raise ValueError(
                f"Limit повинен бути від 1 до {maximum}."
            )