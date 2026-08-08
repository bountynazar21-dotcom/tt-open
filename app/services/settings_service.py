from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.database.models.enums import (
    AuditAction,
    EntityType,
)
from app.database.models.system_setting import (
    SystemSetting,
)
from app.database.models.user import User
from app.repositories import (
    AuditContext,
    Repositories,
    SettingUpdateResult,
    SystemSettingRepository,
)
from app.services.access import AccessService


EnumType = TypeVar(
    "EnumType",
    bound=Enum,
)


@dataclass(slots=True, frozen=True)
class SettingView:
    """
    Безпечне представлення системного налаштування.
    """

    id: int
    key: str
    value: Any

    description: str | None
    category: str | None

    is_public: bool
    is_secret: bool

    updated_at: datetime | None
    updated_by_id: int | None


@dataclass(slots=True, frozen=True)
class SettingsChangeResult:
    """
    Результат зміни одного налаштування.
    """

    setting: SystemSetting

    key: str

    old_value: Any
    new_value: Any

    was_created: bool
    was_changed: bool

    audit_created: bool


@dataclass(slots=True, frozen=True)
class BulkSettingsChangeResult:
    """
    Результат масової зміни налаштувань.
    """

    changed_count: int
    unchanged_count: int
    created_count: int

    results: tuple[
        SettingsChangeResult,
        ...,
    ]


@dataclass(slots=True, frozen=True)
class SettingsDashboard:
    """
    Головні робочі параметри бота.
    """

    bot_enabled: bool
    maintenance_mode: bool
    maintenance_message: str

    timezone: str

    opening_control_enabled: bool
    opening_notifications_enabled: bool
    opening_summaries_enabled: bool
    opening_deadline_minutes: int

    closing_control_enabled: bool
    closing_notifications_enabled: bool
    closing_summaries_enabled: bool
    closing_deadline_minutes: int
    closing_require_receipt: bool

    control_group_id: int | None
    closing_group_id: int | None
    network_summary_topic_id: int | None

    notification_max_attempts: int
    notification_retry_delay_seconds: int

    live_summary_updates_enabled: bool
    excel_reports_enabled: bool

    daily_reports_enabled: bool
    weekly_reports_enabled: bool
    monthly_reports_enabled: bool

    require_store_approval: bool


class SettingsService:
    """
    Сервіс системних налаштувань Telegram-бота.

    Усі зміни доступні лише ROOT_ADMIN.

    Через цей сервіс можна без нового деплою:

    - вимикати або вмикати бота;
    - вмикати технічний режим;
    - змінювати Telegram-групи;
    - змінювати дедлайни;
    - вмикати ранковий контроль;
    - вмикати вечірній контроль;
    - вимикати сповіщення;
    - керувати живими підсумками;
    - змінювати правила фото чека;
    - керувати Excel-звітами;
    - змінювати кількість повторних спроб;
    - змінювати часовий пояс;
    - повертати значення до стандартних;
    - записувати всі зміни в AuditLog.

    Commit виконується у handler або middleware.
    """

    REDACTED_VALUE = "••••••••"

    def __init__(
        self,
        repositories: Repositories,
        *,
        access_service: AccessService | None = None,
    ) -> None:
        self.repositories = repositories
        self.session = repositories.session

        self.access = (
            access_service
            or AccessService(repositories)
        )

    # ==========================================
    # ІНІЦІАЛІЗАЦІЯ
    # ==========================================

    async def initialize_defaults(
        self,
        *,
        actor: User,
    ) -> list[SystemSetting]:
        """
        Створює всі відсутні стандартні параметри.

        Існуючі значення не перезаписуються.
        """

        self.access.require_settings_management(
            actor
        )

        created_settings = (
            await self.repositories.settings
            .create_default_settings(
                created_by_id=actor.id
            )
        )

        for setting in created_settings:
            await self.log_setting_creation(
                actor=actor,
                setting=setting,
                new_value=(
                    self.repositories.settings
                    .read_setting_value(setting)
                ),
                reason=(
                    "Створення стандартного "
                    "системного налаштування"
                ),
            )

        return created_settings

    # ==========================================
    # ГОЛОВНА ПАНЕЛЬ
    # ==========================================

    async def get_dashboard(
        self,
        *,
        user: User,
    ) -> SettingsDashboard:
        """Повертає головні параметри системи."""

        self.access.require_settings_management(
            user
        )

        settings = self.repositories.settings

        return SettingsDashboard(
            bot_enabled=(
                await settings.is_bot_enabled()
            ),
            maintenance_mode=(
                await settings.is_maintenance_mode()
            ),
            maintenance_message=(
                await settings
                .get_maintenance_message()
            ),
            timezone=(
                await settings
                .get_default_timezone()
            ),
            opening_control_enabled=(
                await settings.get_bool(
                    settings.OPENING_CONTROL_ENABLED,
                    default=True,
                )
            ),
            opening_notifications_enabled=(
                await settings.get_bool(
                    settings
                    .OPENING_NOTIFICATIONS_ENABLED,
                    default=True,
                )
            ),
            opening_summaries_enabled=(
                await settings.get_bool(
                    settings
                    .OPENING_SUMMARIES_ENABLED,
                    default=True,
                )
            ),
            opening_deadline_minutes=(
                await settings
                .get_opening_deadline_minutes()
            ),
            closing_control_enabled=(
                await settings.get_bool(
                    settings.CLOSING_CONTROL_ENABLED,
                    default=True,
                )
            ),
            closing_notifications_enabled=(
                await settings.get_bool(
                    settings
                    .CLOSING_NOTIFICATIONS_ENABLED,
                    default=True,
                )
            ),
            closing_summaries_enabled=(
                await settings.get_bool(
                    settings
                    .CLOSING_SUMMARIES_ENABLED,
                    default=True,
                )
            ),
            closing_deadline_minutes=(
                await settings
                .get_closing_deadline_minutes()
            ),
            closing_require_receipt=(
                await settings.get_bool(
                    settings.CLOSING_REQUIRE_RECEIPT,
                    default=True,
                )
            ),
            control_group_id=(
                await settings
                .get_control_group_id()
            ),
            closing_group_id=(
                await settings
                .get_closing_group_id()
            ),
            network_summary_topic_id=(
                await settings.get_int(
                    settings
                    .NETWORK_SUMMARY_TOPIC_ID,
                    default=None,
                )
            ),
            notification_max_attempts=(
                await settings
                .get_notification_max_attempts()
            ),
            notification_retry_delay_seconds=(
                await settings
                .get_notification_retry_delay()
            ),
            live_summary_updates_enabled=(
                await settings.get_bool(
                    settings
                    .LIVE_SUMMARY_UPDATES_ENABLED,
                    default=True,
                )
            ),
            excel_reports_enabled=(
                await settings.get_bool(
                    settings.EXCEL_REPORTS_ENABLED,
                    default=True,
                )
            ),
            daily_reports_enabled=(
                await settings.get_bool(
                    settings.DAILY_REPORTS_ENABLED,
                    default=True,
                )
            ),
            weekly_reports_enabled=(
                await settings.get_bool(
                    settings.WEEKLY_REPORTS_ENABLED,
                    default=True,
                )
            ),
            monthly_reports_enabled=(
                await settings.get_bool(
                    settings.MONTHLY_REPORTS_ENABLED,
                    default=True,
                )
            ),
            require_store_approval=(
                await settings.get_bool(
                    settings.REQUIRE_STORE_APPROVAL,
                    default=True,
                )
            ),
        )

    # ==========================================
    # ПЕРЕГЛЯД НАЛАШТУВАНЬ
    # ==========================================

    async def get_setting(
        self,
        *,
        user: User,
        key: str,
        reveal_secret: bool = False,
    ) -> SettingView:
        """Повертає одне налаштування."""

        self.access.require_settings_management(
            user
        )

        setting = (
            await self.repositories.settings
            .get_by_key_or_raise(key)
        )

        return self.build_setting_view(
            setting,
            reveal_secret=reveal_secret,
        )

    async def get_all_settings(
        self,
        *,
        user: User,
        include_secret: bool = False,
        reveal_secret_values: bool = False,
    ) -> list[SettingView]:
        """Повертає всі системні налаштування."""

        self.access.require_settings_management(
            user
        )

        settings = (
            await self.repositories.settings
            .get_all_settings(
                include_secret=include_secret
            )
        )

        return [
            self.build_setting_view(
                setting,
                reveal_secret=(
                    reveal_secret_values
                ),
            )
            for setting in settings
        ]

    async def get_category(
        self,
        *,
        user: User,
        category: str,
        include_secret: bool = False,
    ) -> list[SettingView]:
        """Повертає налаштування категорії."""

        self.access.require_settings_management(
            user
        )

        settings = (
            await self.repositories.settings
            .get_by_category(
                category,
                include_secret=include_secret,
            )
        )

        return [
            self.build_setting_view(
                setting,
                reveal_secret=False,
            )
            for setting in settings
        ]

    async def search_settings(
        self,
        *,
        user: User,
        query: str,
        include_secret: bool = False,
        limit: int = 100,
    ) -> list[SettingView]:
        """Шукає налаштування за ключем або описом."""

        self.access.require_settings_management(
            user
        )

        settings = (
            await self.repositories.settings
            .search(
                query,
                include_secret=include_secret,
                limit=limit,
            )
        )

        return [
            self.build_setting_view(
                setting,
                reveal_secret=False,
            )
            for setting in settings
        ]

    # ==========================================
    # УНІВЕРСАЛЬНА ЗМІНА
    # ==========================================

    async def set_setting(
        self,
        *,
        actor: User,
        key: str,
        value: Any,
        reason: str,
        description: str | None = None,
        category: str | None = None,
        is_public: bool | None = None,
        is_secret: bool | None = None,
        update_description: bool = False,
        update_category: bool = False,
    ) -> SettingsChangeResult:
        """Створює або змінює налаштування."""

        self.access.require_settings_management(
            actor
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        result = (
            await self.repositories.settings
            .set_value(
                key=key,
                value=value,
                updated_by_id=actor.id,
                description=description,
                category=category,
                is_public=is_public,
                is_secret=is_secret,
                update_description=(
                    update_description
                ),
                update_category=(
                    update_category
                ),
            )
        )

        audit_created = False

        if result.was_created:
            await self.log_setting_creation(
                actor=actor,
                setting=result.setting,
                new_value=result.new_value,
                reason=normalized_reason,
            )

            audit_created = True

        elif result.was_changed:
            await self.log_setting_update(
                actor=actor,
                setting=result.setting,
                old_value=result.old_value,
                new_value=result.new_value,
                reason=normalized_reason,
            )

            audit_created = True

        return SettingsChangeResult(
            setting=result.setting,
            key=result.setting.key,
            old_value=result.old_value,
            new_value=result.new_value,
            was_created=result.was_created,
            was_changed=result.was_changed,
            audit_created=audit_created,
        )

    async def set_many(
        self,
        *,
        actor: User,
        values: dict[str, Any],
        reason: str,
    ) -> BulkSettingsChangeResult:
        """Змінює декілька параметрів."""

        self.access.require_settings_management(
            actor
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        results: list[
            SettingsChangeResult
        ] = []

        for key, value in values.items():
            result = await self.set_setting(
                actor=actor,
                key=key,
                value=value,
                reason=normalized_reason,
            )

            results.append(result)

        return BulkSettingsChangeResult(
            changed_count=sum(
                result.was_changed
                for result in results
            ),
            unchanged_count=sum(
                not result.was_changed
                for result in results
            ),
            created_count=sum(
                result.was_created
                for result in results
            ),
            results=tuple(results),
        )

    # ==========================================
    # УВІМКНЕННЯ БОТА
    # ==========================================

    async def set_bot_enabled(
        self,
        *,
        actor: User,
        enabled: bool,
        reason: str,
    ) -> SettingsChangeResult:
        """Повністю вмикає або вимикає бота."""

        return await self.set_setting(
            actor=actor,
            key=(
                self.repositories.settings
                .BOT_ENABLED
            ),
            value=bool(enabled),
            reason=reason,
        )

    # ==========================================
    # ТЕХНІЧНИЙ РЕЖИМ
    # ==========================================

    async def set_maintenance_mode(
        self,
        *,
        actor: User,
        enabled: bool,
        reason: str,
        message: str | None = None,
    ) -> BulkSettingsChangeResult:
        """Вмикає або вимикає технічний режим."""

        values: dict[str, Any] = {
            self.repositories.settings
            .MAINTENANCE_MODE: bool(enabled),
        }

        if message is not None:
            values[
                self.repositories.settings
                .MAINTENANCE_MESSAGE
            ] = self.normalize_required_text(
                message,
                field_name=(
                    "Повідомлення технічного режиму"
                ),
            )

        return await self.set_many(
            actor=actor,
            values=values,
            reason=reason,
        )

    # ==========================================
    # ЧАСОВИЙ ПОЯС
    # ==========================================

    async def set_timezone(
        self,
        *,
        actor: User,
        timezone_name: str,
        reason: str,
    ) -> SettingsChangeResult:
        """Змінює часовий пояс системи."""

        normalized_timezone = (
            self.validate_timezone(
                timezone_name
            )
        )

        return await self.set_setting(
            actor=actor,
            key=(
                self.repositories.settings
                .DEFAULT_TIMEZONE
            ),
            value=normalized_timezone,
            reason=reason,
        )

    # ==========================================
    # РАНКОВИЙ КОНТРОЛЬ
    # ==========================================

    async def set_opening_control(
        self,
        *,
        actor: User,
        control_enabled: bool,
        notifications_enabled: bool | None = None,
        summaries_enabled: bool | None = None,
        deadline_minutes: int | None = None,
        reason: str,
    ) -> BulkSettingsChangeResult:
        """Змінює параметри ранкового контролю."""

        settings = self.repositories.settings

        values: dict[str, Any] = {
            settings.OPENING_CONTROL_ENABLED: (
                bool(control_enabled)
            ),
        }

        if notifications_enabled is not None:
            values[
                settings
                .OPENING_NOTIFICATIONS_ENABLED
            ] = bool(notifications_enabled)

        if summaries_enabled is not None:
            values[
                settings.OPENING_SUMMARIES_ENABLED
            ] = bool(summaries_enabled)

        if deadline_minutes is not None:
            self.validate_deadline_minutes(
                deadline_minutes
            )

            values[
                settings
                .OPENING_DEFAULT_DEADLINE_MINUTES
            ] = deadline_minutes

        return await self.set_many(
            actor=actor,
            values=values,
            reason=reason,
        )

    async def set_opening_deadline(
        self,
        *,
        actor: User,
        minutes: int,
        reason: str,
    ) -> SettingsChangeResult:
        """Змінює стандартний дедлайн відкриття."""

        self.validate_deadline_minutes(minutes)

        return await self.set_setting(
            actor=actor,
            key=(
                self.repositories.settings
                .OPENING_DEFAULT_DEADLINE_MINUTES
            ),
            value=minutes,
            reason=reason,
        )

    # ==========================================
    # ВЕЧІРНІЙ КОНТРОЛЬ
    # ==========================================

    async def set_closing_control(
        self,
        *,
        actor: User,
        control_enabled: bool,
        notifications_enabled: bool | None = None,
        summaries_enabled: bool | None = None,
        deadline_minutes: int | None = None,
        require_receipt: bool | None = None,
        reason: str,
    ) -> BulkSettingsChangeResult:
        """Змінює параметри вечірнього контролю."""

        settings = self.repositories.settings

        values: dict[str, Any] = {
            settings.CLOSING_CONTROL_ENABLED: (
                bool(control_enabled)
            ),
        }

        if notifications_enabled is not None:
            values[
                settings
                .CLOSING_NOTIFICATIONS_ENABLED
            ] = bool(notifications_enabled)

        if summaries_enabled is not None:
            values[
                settings.CLOSING_SUMMARIES_ENABLED
            ] = bool(summaries_enabled)

        if require_receipt is not None:
            values[
                settings.CLOSING_REQUIRE_RECEIPT
            ] = bool(require_receipt)

        if deadline_minutes is not None:
            self.validate_deadline_minutes(
                deadline_minutes
            )

            values[
                settings
                .CLOSING_DEFAULT_DEADLINE_MINUTES
            ] = deadline_minutes

        return await self.set_many(
            actor=actor,
            values=values,
            reason=reason,
        )

    async def set_closing_deadline(
        self,
        *,
        actor: User,
        minutes: int,
        reason: str,
    ) -> SettingsChangeResult:
        """Змінює стандартний дедлайн звіту."""

        self.validate_deadline_minutes(minutes)

        return await self.set_setting(
            actor=actor,
            key=(
                self.repositories.settings
                .CLOSING_DEFAULT_DEADLINE_MINUTES
            ),
            value=minutes,
            reason=reason,
        )

    async def set_receipt_required(
        self,
        *,
        actor: User,
        required: bool,
        reason: str,
    ) -> SettingsChangeResult:
        """Вмикає або вимикає обов’язкове фото чека."""

        return await self.set_setting(
            actor=actor,
            key=(
                self.repositories.settings
                .CLOSING_REQUIRE_RECEIPT
            ),
            value=bool(required),
            reason=reason,
        )

    # ==========================================
    # TELEGRAM-ГРУПИ
    # ==========================================

    async def set_control_group(
        self,
        *,
        actor: User,
        chat_id: int | None,
        reason: str,
    ) -> SettingsChangeResult:
        """Змінює групу ранкового контролю."""

        self.validate_optional_chat_id(chat_id)

        return await self.set_setting(
            actor=actor,
            key=(
                self.repositories.settings
                .CONTROL_GROUP_ID
            ),
            value=chat_id,
            reason=reason,
        )

    async def set_closing_group(
        self,
        *,
        actor: User,
        chat_id: int | None,
        reason: str,
    ) -> SettingsChangeResult:
        """Змінює групу вечірніх звітів."""

        self.validate_optional_chat_id(chat_id)

        return await self.set_setting(
            actor=actor,
            key=(
                self.repositories.settings
                .CLOSING_GROUP_ID
            ),
            value=chat_id,
            reason=reason,
        )

    async def set_network_summary_topic(
        self,
        *,
        actor: User,
        topic_id: int | None,
        reason: str,
    ) -> SettingsChangeResult:
        """Змінює тему загального підсумку."""

        self.validate_optional_topic_id(
            topic_id
        )

        return await self.set_setting(
            actor=actor,
            key=(
                self.repositories.settings
                .NETWORK_SUMMARY_TOPIC_ID
            ),
            value=topic_id,
            reason=reason,
        )

    async def set_telegram_destinations(
        self,
        *,
        actor: User,
        control_group_id: int | None,
        closing_group_id: int | None,
        network_summary_topic_id: int | None,
        reason: str,
    ) -> BulkSettingsChangeResult:
        """Змінює всі головні Telegram-напрямки."""

        self.validate_optional_chat_id(
            control_group_id
        )

        self.validate_optional_chat_id(
            closing_group_id
        )

        self.validate_optional_topic_id(
            network_summary_topic_id
        )

        settings = self.repositories.settings

        return await self.set_many(
            actor=actor,
            values={
                settings.CONTROL_GROUP_ID: (
                    control_group_id
                ),
                settings.CLOSING_GROUP_ID: (
                    closing_group_id
                ),
                settings
                .NETWORK_SUMMARY_TOPIC_ID: (
                    network_summary_topic_id
                ),
            },
            reason=reason,
        )

    # ==========================================
    # СПОВІЩЕННЯ
    # ==========================================

    async def set_notification_policy(
        self,
        *,
        actor: User,
        max_attempts: int,
        retry_delay_seconds: int,
        reason: str,
    ) -> BulkSettingsChangeResult:
        """Змінює політику повторних спроб."""

        self.validate_notification_attempts(
            max_attempts
        )

        self.validate_retry_delay(
            retry_delay_seconds
        )

        settings = self.repositories.settings

        return await self.set_many(
            actor=actor,
            values={
                settings
                .NOTIFICATION_MAX_ATTEMPTS: (
                    max_attempts
                ),
                settings
                .NOTIFICATION_RETRY_DELAY_SECONDS: (
                    retry_delay_seconds
                ),
            },
            reason=reason,
        )

    # ==========================================
    # ЖИВІ ПІДСУМКИ
    # ==========================================

    async def set_live_summaries_enabled(
        self,
        *,
        actor: User,
        enabled: bool,
        reason: str,
    ) -> SettingsChangeResult:
        """Вмикає або вимикає редагування підсумків."""

        return await self.set_setting(
            actor=actor,
            key=(
                self.repositories.settings
                .LIVE_SUMMARY_UPDATES_ENABLED
            ),
            value=bool(enabled),
            reason=reason,
        )

    # ==========================================
    # ЗВІТИ
    # ==========================================

    async def set_report_settings(
        self,
        *,
        actor: User,
        excel_enabled: bool | None = None,
        daily_enabled: bool | None = None,
        weekly_enabled: bool | None = None,
        monthly_enabled: bool | None = None,
        reason: str,
    ) -> BulkSettingsChangeResult:
        """Змінює параметри автоматичних звітів."""

        settings = self.repositories.settings

        values: dict[str, Any] = {}

        if excel_enabled is not None:
            values[
                settings.EXCEL_REPORTS_ENABLED
            ] = bool(excel_enabled)

        if daily_enabled is not None:
            values[
                settings.DAILY_REPORTS_ENABLED
            ] = bool(daily_enabled)

        if weekly_enabled is not None:
            values[
                settings.WEEKLY_REPORTS_ENABLED
            ] = bool(weekly_enabled)

        if monthly_enabled is not None:
            values[
                settings.MONTHLY_REPORTS_ENABLED
            ] = bool(monthly_enabled)

        if not values:
            raise ValueError(
                "Не вказано жодного параметра звітів."
            )

        return await self.set_many(
            actor=actor,
            values=values,
            reason=reason,
        )

    # ==========================================
    # ПІДТВЕРДЖЕННЯ ПРАЦІВНИКІВ
    # ==========================================

    async def set_store_approval_required(
        self,
        *,
        actor: User,
        required: bool,
        reason: str,
    ) -> SettingsChangeResult:
        """Змінює правило підтвердження працівників."""

        return await self.set_setting(
            actor=actor,
            key=(
                self.repositories.settings
                .REQUIRE_STORE_APPROVAL
            ),
            value=bool(required),
            reason=reason,
        )

    # ==========================================
    # СКИДАННЯ ДО СТАНДАРТУ
    # ==========================================

    async def reset_to_default(
        self,
        *,
        actor: User,
        key: str,
        reason: str,
    ) -> SettingsChangeResult:
        """Повертає налаштування до стандарту."""

        self.access.require_settings_management(
            actor
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        result = (
            await self.repositories.settings
            .reset_to_default(
                key=key,
                updated_by_id=actor.id,
            )
        )

        audit_created = False

        if result.was_changed:
            await self.log_setting_update(
                actor=actor,
                setting=result.setting,
                old_value=result.old_value,
                new_value=result.new_value,
                reason=normalized_reason,
                details={
                    "reset_to_default": True,
                },
            )

            audit_created = True

        return SettingsChangeResult(
            setting=result.setting,
            key=result.setting.key,
            old_value=result.old_value,
            new_value=result.new_value,
            was_created=result.was_created,
            was_changed=result.was_changed,
            audit_created=audit_created,
        )

    # ==========================================
    # ВИДАЛЕННЯ НЕСТАНДАРТНОГО ПАРАМЕТРА
    # ==========================================

    async def delete_setting(
        self,
        *,
        actor: User,
        key: str,
        reason: str,
    ) -> bool:
        """Видаляє системне налаштування."""

        self.access.require_settings_management(
            actor
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        setting = (
            await self.repositories.settings
            .get_by_key(
                key,
                for_update=True,
            )
        )

        if setting is None:
            return False

        previous_value = (
            self.repositories.settings
            .read_setting_value(setting)
        )

        setting_id = setting.id
        setting_key = setting.key

        deleted = (
            await self.repositories.settings
            .delete_by_key(setting_key)
        )

        if deleted:
            await self.log_setting_deletion(
                actor=actor,
                setting_id=setting_id,
                setting_key=setting_key,
                previous_value=previous_value,
                reason=normalized_reason,
            )

        return deleted

    # ==========================================
    # ЕКСПОРТ
    # ==========================================

    async def export_settings(
        self,
        *,
        user: User,
        include_secret: bool = False,
    ) -> dict[str, Any]:
        """Експортує системні налаштування."""

        self.access.require_settings_management(
            user
        )

        values = (
            await self.repositories.settings
            .export_values(
                include_secret=include_secret
            )
        )

        if include_secret:
            return values

        return dict(values)

    # ==========================================
    # ФОРМАТУВАННЯ ДЛЯ TELEGRAM
    # ==========================================

    async def format_dashboard(
        self,
        *,
        user: User,
    ) -> str:
        """Формує текст головної панелі."""

        dashboard = await self.get_dashboard(
            user=user
        )

        return "\n".join(
            [
                "⚙️ <b>Системні налаштування</b>",
                "",
                (
                    "🤖 Бот: "
                    f"<b>{self.bool_text(dashboard.bot_enabled)}</b>"
                ),
                (
                    "🛠 Технічний режим: "
                    f"<b>{self.bool_text(dashboard.maintenance_mode)}</b>"
                ),
                (
                    "🌍 Часовий пояс: "
                    f"<b>{dashboard.timezone}</b>"
                ),
                "",
                "🌅 <b>Відкриття</b>",
                (
                    "Контроль: "
                    f"<b>{self.bool_text(dashboard.opening_control_enabled)}</b>"
                ),
                (
                    "Сповіщення: "
                    f"<b>{self.bool_text(dashboard.opening_notifications_enabled)}</b>"
                ),
                (
                    "Підсумки: "
                    f"<b>{self.bool_text(dashboard.opening_summaries_enabled)}</b>"
                ),
                (
                    "Дедлайн: "
                    f"<b>{dashboard.opening_deadline_minutes} хв</b>"
                ),
                "",
                "🌙 <b>Закриття</b>",
                (
                    "Контроль: "
                    f"<b>{self.bool_text(dashboard.closing_control_enabled)}</b>"
                ),
                (
                    "Сповіщення: "
                    f"<b>{self.bool_text(dashboard.closing_notifications_enabled)}</b>"
                ),
                (
                    "Підсумки: "
                    f"<b>{self.bool_text(dashboard.closing_summaries_enabled)}</b>"
                ),
                (
                    "Фото чека: "
                    f"<b>{self.bool_text(dashboard.closing_require_receipt)}</b>"
                ),
                (
                    "Дедлайн: "
                    f"<b>{dashboard.closing_deadline_minutes} хв</b>"
                ),
                "",
                "📨 <b>Telegram</b>",
                (
                    "Група відкриття: "
                    f"<code>{dashboard.control_group_id or 'не вказано'}</code>"
                ),
                (
                    "Група закриття: "
                    f"<code>{dashboard.closing_group_id or 'не вказано'}</code>"
                ),
                (
                    "Тема мережі: "
                    f"<code>{dashboard.network_summary_topic_id or 'не вказано'}</code>"
                ),
                "",
                "📊 <b>Звіти</b>",
                (
                    "Excel: "
                    f"<b>{self.bool_text(dashboard.excel_reports_enabled)}</b>"
                ),
                (
                    "Щоденні: "
                    f"<b>{self.bool_text(dashboard.daily_reports_enabled)}</b>"
                ),
                (
                    "Щотижневі: "
                    f"<b>{self.bool_text(dashboard.weekly_reports_enabled)}</b>"
                ),
                (
                    "Щомісячні: "
                    f"<b>{self.bool_text(dashboard.monthly_reports_enabled)}</b>"
                ),
            ]
        )

    # ==========================================
    # AUDIT LOG
    # ==========================================

    async def log_setting_creation(
        self,
        *,
        actor: User,
        setting: SystemSetting,
        new_value: Any,
        reason: str,
    ) -> None:
        """Фіксує створення налаштування."""

        action = self.resolve_audit_action(
            "create",
            "created",
            "add",
        )

        entity_type = self.resolve_entity_type(
            "system_setting",
            "setting",
            "system",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=setting.id,
            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=(
                    "Створено системне налаштування "
                    f"{setting.key}"
                ),
                source="telegram_bot",
            ),
            new_values={
                "key": setting.key,
                "value": self.audit_value(
                    setting,
                    new_value,
                ),
            },
        )

    async def log_setting_update(
        self,
        *,
        actor: User,
        setting: SystemSetting,
        old_value: Any,
        new_value: Any,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Фіксує зміну налаштування."""

        action = self.resolve_audit_action(
            "update",
            "changed",
            "edit",
        )

        entity_type = self.resolve_entity_type(
            "system_setting",
            "setting",
            "system",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=setting.id,
            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=(
                    "Змінено системне налаштування "
                    f"{setting.key}"
                ),
                source="telegram_bot",
            ),
            old_values={
                "key": setting.key,
                "value": self.audit_value(
                    setting,
                    old_value,
                ),
            },
            new_values={
                "key": setting.key,
                "value": self.audit_value(
                    setting,
                    new_value,
                ),
            },
            details=details,
        )

    async def log_setting_deletion(
        self,
        *,
        actor: User,
        setting_id: int,
        setting_key: str,
        previous_value: Any,
        reason: str,
    ) -> None:
        """Фіксує видалення налаштування."""

        action = self.resolve_audit_action(
            "delete",
            "removed",
            "deactivate",
        )

        entity_type = self.resolve_entity_type(
            "system_setting",
            "setting",
            "system",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=setting_id,
            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=(
                    "Видалено системне налаштування "
                    f"{setting_key}"
                ),
                source="telegram_bot",
            ),
            old_values={
                "key": setting_key,
                "value": previous_value,
            },
            new_values={},
        )

    # ==========================================
    # БЕЗПЕЧНЕ ВІДОБРАЖЕННЯ
    # ==========================================

    def build_setting_view(
        self,
        setting: SystemSetting,
        *,
        reveal_secret: bool,
    ) -> SettingView:
        """Формує безпечне представлення."""

        repository = self.repositories.settings

        is_secret = bool(
            repository.get_first_available_value(
                setting,
                names=("is_secret",),
                default=False,
            )
        )

        value = repository.read_setting_value(
            setting
        )

        if is_secret and not reveal_secret:
            value = self.REDACTED_VALUE

        return SettingView(
            id=setting.id,
            key=setting.key,
            value=value,
            description=(
                repository
                .get_first_available_value(
                    setting,
                    names=("description",),
                    default=None,
                )
            ),
            category=(
                repository
                .get_first_available_value(
                    setting,
                    names=(
                        "category",
                        "group_name",
                    ),
                    default=None,
                )
            ),
            is_public=bool(
                repository
                .get_first_available_value(
                    setting,
                    names=("is_public",),
                    default=False,
                )
            ),
            is_secret=is_secret,
            updated_at=(
                repository
                .get_first_available_value(
                    setting,
                    names=(
                        "updated_at",
                        "modified_at",
                    ),
                    default=None,
                )
            ),
            updated_by_id=(
                repository
                .get_first_available_value(
                    setting,
                    names=(
                        "updated_by_id",
                        "modified_by_id",
                    ),
                    default=None,
                )
            ),
        )

    def audit_value(
        self,
        setting: SystemSetting,
        value: Any,
    ) -> Any:
        """Приховує секретне значення в AuditLog."""

        is_secret = bool(
            self.repositories.settings
            .get_first_available_value(
                setting,
                names=("is_secret",),
                default=False,
            )
        )

        if is_secret:
            return self.REDACTED_VALUE

        return value

    # ==========================================
    # ENUM-РЕЗОЛВЕРИ
    # ==========================================

    @classmethod
    def resolve_audit_action(
        cls,
        *names: str,
    ) -> AuditAction:
        """Знаходить AuditAction."""

        try:
            return cls.resolve_enum_member(
                AuditAction,
                *names,
            )

        except ValueError:
            return cls.resolve_enum_member(
                AuditAction,
                "update",
                "updated",
                "change",
                "changed",
            )

    @classmethod
    def resolve_entity_type(
        cls,
        *names: str,
    ) -> EntityType:
        """Знаходить EntityType."""

        return cls.resolve_enum_member(
            EntityType,
            *names,
        )

    @staticmethod
    def resolve_enum_member(
        enum_class: type[EnumType],
        *names: str,
    ) -> EnumType:
        """Шукає enum за назвою або значенням."""

        normalized_names = {
            name.strip().lower()
            for name in names
            if name.strip()
        }

        for enum_item in enum_class:
            candidates = {
                enum_item.name.lower(),
                str(enum_item.value).lower(),
            }

            if candidates.intersection(
                normalized_names
            ):
                return enum_item

        raise ValueError(
            f"У {enum_class.__name__} відсутнє "
            f"значення: {sorted(normalized_names)}."
        )

    # ==========================================
    # ВАЛІДАЦІЯ
    # ==========================================

    @staticmethod
    def validate_timezone(
        timezone_name: str,
    ) -> str:
        """Перевіряє часовий пояс."""

        normalized_name = (
            timezone_name.strip()
        )

        if not normalized_name:
            raise ValueError(
                "Часовий пояс не може бути порожнім."
            )

        try:
            ZoneInfo(normalized_name)

        except ZoneInfoNotFoundError as error:
            raise ValueError(
                "Невідомий часовий пояс: "
                f"{normalized_name}."
            ) from error

        return normalized_name

    @staticmethod
    def validate_deadline_minutes(
        minutes: int,
    ) -> None:
        """Перевіряє дедлайн у хвилинах."""

        if isinstance(minutes, bool):
            raise ValueError(
                "Дедлайн повинен бути числом."
            )

        if minutes < 0 or minutes > 180:
            raise ValueError(
                "Дедлайн повинен бути "
                "від 0 до 180 хвилин."
            )

    @staticmethod
    def validate_notification_attempts(
        attempts: int,
    ) -> None:
        """Перевіряє кількість спроб."""

        if isinstance(attempts, bool):
            raise ValueError(
                "Кількість спроб повинна бути числом."
            )

        if attempts < 1 or attempts > 50:
            raise ValueError(
                "Кількість спроб повинна бути "
                "від 1 до 50."
            )

    @staticmethod
    def validate_retry_delay(
        seconds: int,
    ) -> None:
        """Перевіряє затримку повторної спроби."""

        if isinstance(seconds, bool):
            raise ValueError(
                "Затримка повинна бути числом."
            )

        if seconds < 10 or seconds > 3600:
            raise ValueError(
                "Затримка повинна бути "
                "від 10 до 3600 секунд."
            )

    @staticmethod
    def validate_optional_chat_id(
        chat_id: int | None,
    ) -> None:
        """Перевіряє Telegram chat_id."""

        if chat_id is None:
            return

        if not isinstance(chat_id, int):
            raise ValueError(
                "Telegram chat_id повинен бути числом."
            )

        if chat_id == 0:
            raise ValueError(
                "Telegram chat_id не може "
                "дорівнювати нулю."
            )

    @staticmethod
    def validate_optional_topic_id(
        topic_id: int | None,
    ) -> None:
        """Перевіряє Telegram topic_id."""

        if topic_id is None:
            return

        if not isinstance(topic_id, int):
            raise ValueError(
                "Telegram topic_id повинен бути числом."
            )

        if topic_id <= 0:
            raise ValueError(
                "Telegram topic_id повинен бути "
                "більшим за нуль."
            )

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
    ) -> str:
        """Нормалізує обов’язковий текст."""

        normalized_value = " ".join(
            value.strip().split()
        )

        if not normalized_value:
            raise ValueError(
                f"{field_name} не може бути порожнім."
            )

        if len(normalized_value) > 2000:
            raise ValueError(
                f"{field_name} занадто довгий."
            )

        return normalized_value

    @staticmethod
    def bool_text(
        value: bool,
    ) -> str:
        """Формує текст логічного параметра."""

        return (
            "увімкнено ✅"
            if value
            else "вимкнено ❌"
        )