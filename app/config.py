from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AliasChoices,
    BeforeValidator,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    SettingsConfigDict,
)


BASE_DIR = Path(__file__).resolve().parent.parent


def empty_string_to_none(value: object) -> object:
    """Перетворює порожні значення з .env на None."""

    if isinstance(value, str) and not value.strip():
        return None

    return value


OptionalInt = Annotated[
    int | None,
    BeforeValidator(empty_string_to_none),
]

OptionalString = Annotated[
    str | None,
    BeforeValidator(empty_string_to_none),
]


class Settings(BaseSettings):
    """
    Головні налаштування застосунку.

    Значення завантажуються зі змінних середовища
    та файлу .env у корені проєкту.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================
    # TELEGRAM
    # ==========================================

    bot_token: SecretStr
    bot_username: str

    root_admin_ids: Annotated[
        list[int],
        NoDecode,
    ] = Field(
        default_factory=list,
    )

    # ==========================================
    # TELEGRAM REPORT GROUP
    # ==========================================

    # Одна Telegram-група,
    # всередині якої знаходяться Topics звітів.
    report_group_chat_id: OptionalInt = None

    # Вінниця
    report_topic_vinnytsia: OptionalInt = None

    # Хмельницький — перша частина
    report_topic_khmelnytskyi_1: OptionalInt = None

    # Хмельницький — друга частина
    report_topic_khmelnytskyi_2: OptionalInt = None

    # Генеральний Topic.
    # Сюди надходитиме сумарна каса всієї мережі.
    network_cash_topic_id: OptionalInt = None

    # ==========================================
    # LEGACY CLOSING GROUP
    # ==========================================

    # Залишаємо для сумісності
    # з уже написаними service/handler.
    closing_group_id: OptionalInt = None
    closing_group_topic_id: OptionalInt = None

    # ==========================================
    # DATABASE
    # ==========================================

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/chikin_bot"
    )

    database_sync_url: OptionalString = None

    database_echo: bool = False

    database_pool_size: int = Field(
        default=10,
        ge=1,
        le=100,
    )

    database_max_overflow: int = Field(
        default=20,
        ge=0,
        le=200,
    )

    database_pool_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
    )

    # ==========================================
    # APPLICATION
    # ==========================================

    app_name: str = "Chikin Bot"

    app_env: Literal[
        "development",
        "testing",
        "production",
    ] = "development"

    timezone: str = "Europe/Kyiv"

    log_level: Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    ] = "INFO"

    log_format: Literal[
        "console",
        "json",
    ] = "console"

    debug: bool = False

    # ==========================================
    # BOT MODE
    # ==========================================

    use_webhook: bool = False

    app_base_url: OptionalString = None
    webhook_url: OptionalString = None

    webhook_path: str = "/webhook"
    webhook_secret: OptionalString = None

    web_server_host: str = "0.0.0.0"

    web_server_port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        validation_alias=AliasChoices(
            "PORT",
            "WEB_SERVER_PORT",
        ),
    )

    # ==========================================
    # REGISTRATION AND ACCESS
    # ==========================================

    require_store_approval: bool = True
    allow_multiple_store_users: bool = True

    default_invite_expiration_hours: int = Field(
        default=24,
        ge=1,
        le=8760,
    )

    default_invite_max_uses: int = Field(
        default=1,
        ge=1,
        le=10_000,
    )

    # ==========================================
    # OPENING CHECK-IN
    # ==========================================

    enable_opening_reminders: bool = True

    opening_reminder_before_minutes: int = Field(
        default=10,
        ge=0,
        le=180,
    )

    opening_late_reminder_minutes: int = Field(
        default=5,
        ge=0,
        le=180,
    )

    default_opening_deadline_minutes: int = Field(
        default=10,
        ge=0,
        le=180,
    )

    scheduler_check_interval_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
    )

    # ==========================================
    # CLOSING REPORTS
    # ==========================================

    enable_closing_reminders: bool = True

    closing_reminder_before_minutes: int = Field(
        default=10,
        ge=0,
        le=180,
    )

    default_closing_deadline_minutes: int = Field(
        default=15,
        ge=0,
        le=180,
    )

    max_cash_amount: int = Field(
        default=10_000_000,
        ge=0,
    )

    require_receipt_photo: bool = True

    # ==========================================
    # REPORTS
    # ==========================================

    reports_directory: Path = Path(
        "storage/reports"
    )

    report_file_lifetime_hours: int = Field(
        default=24,
        ge=1,
        le=8760,
    )

    network_name: str = "Soska Bar"

    # ==========================================
    # SECURITY
    # ==========================================

    secret_key: SecretStr
    invite_token_salt: SecretStr

    rate_limit_requests_per_minute: int = Field(
        default=60,
        ge=1,
        le=10_000,
    )

    # ==========================================
    # SCHEDULER LOCK
    # ==========================================

    enable_scheduler_lock: bool = True

    scheduler_lock_id: int = Field(
        default=27_182_818,
        ge=1,
    )

    # ==========================================
    # VALIDATORS
    # ==========================================

    @field_validator(
        "root_admin_ids",
        mode="before",
    )
    @classmethod
    def parse_root_admin_ids(
        cls,
        value: object,
    ) -> list[int]:
        """
        Підтримує формат:

        ROOT_ADMIN_IDS=123456789
        ROOT_ADMIN_IDS=123456789,987654321
        """

        if value is None:
            return []

        if isinstance(
            value,
            int,
        ):
            return [
                value
            ]

        if isinstance(
            value,
            str,
        ):
            value = value.strip()

            if not value:
                return []

            raw_ids = [
                item.strip()
                for item in value.split(",")
                if item.strip()
            ]

            try:
                return [
                    int(item)
                    for item in raw_ids
                ]

            except ValueError as error:
                raise ValueError(
                    "ROOT_ADMIN_IDS повинен містити "
                    "Telegram ID через кому."
                ) from error

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            try:
                return [
                    int(item)
                    for item in value
                ]

            except (
                TypeError,
                ValueError,
            ) as error:
                raise ValueError(
                    "ROOT_ADMIN_IDS містить "
                    "некоректний Telegram ID."
                ) from error

        raise ValueError(
            "Непідтримуваний формат ROOT_ADMIN_IDS."
        )

    @field_validator(
        "bot_username"
    )
    @classmethod
    def normalize_bot_username(
        cls,
        value: str,
    ) -> str:
        """
        Прибирає @ на початку username.
        """

        username = (
            value
            .strip()
            .removeprefix("@")
        )

        if not username:
            raise ValueError(
                "BOT_USERNAME не може бути порожнім."
            )

        return username

    @field_validator(
        "webhook_path"
    )
    @classmethod
    def normalize_webhook_path(
        cls,
        value: str,
    ) -> str:
        path = value.strip()

        if not path:
            return "/webhook"

        if not path.startswith(
            "/"
        ):
            path = (
                f"/{path}"
            )

        return path

    @field_validator(
        "app_base_url"
    )
    @classmethod
    def normalize_app_base_url(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return (
            value
            .strip()
            .rstrip("/")
        )

    @field_validator(
        "database_sync_url",
        "webhook_url",
        "webhook_secret",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(
        cls,
        value: object,
    ) -> object:
        return empty_string_to_none(
            value
        )

    @field_validator(
        "report_group_chat_id",
        "report_topic_vinnytsia",
        "report_topic_khmelnytskyi_1",
        "report_topic_khmelnytskyi_2",
        "network_cash_topic_id",
        "closing_group_id",
        "closing_group_topic_id",
        mode="before",
    )
    @classmethod
    def normalize_optional_integers(
        cls,
        value: object,
    ) -> object:
        return empty_string_to_none(
            value
        )

    @field_validator(
        "reports_directory",
        mode="before",
    )
    @classmethod
    def make_reports_path_absolute(
        cls,
        value: object,
    ) -> Path:
        path = Path(
            str(value)
        )

        if path.is_absolute():
            return path

        return (
            BASE_DIR
            / path
        )

    # ==========================================
    # MODEL VALIDATION
    # ==========================================

    @model_validator(
        mode="after"
    )
    def validate_webhook_settings(
        self,
    ) -> Settings:
        """
        Перевіряє налаштування webhook.
        """

        if self.use_webhook:
            if (
                not self.webhook_url
                and not self.app_base_url
            ):
                raise ValueError(
                    "Для USE_WEBHOOK=true потрібно вказати "
                    "WEBHOOK_URL або APP_BASE_URL."
                )

            if not self.webhook_secret:
                raise ValueError(
                    "Для webhook-режиму потрібно вказати "
                    "WEBHOOK_SECRET."
                )

        return self

    # ==========================================
    # TELEGRAM PROPERTIES
    # ==========================================

    @property
    def telegram_webhook_url(
        self,
    ) -> str | None:
        """
        Повна адреса Telegram webhook.
        """

        if self.webhook_url:
            return (
                self.webhook_url
                .rstrip("/")
            )

        if self.app_base_url:
            return (
                f"{self.app_base_url}"
                f"{self.webhook_path}"
            )

        return None

    @property
    def bot_link(
        self,
    ) -> str:
        """
        Публічне посилання на Telegram-бота.
        """

        return (
            f"https://t.me/"
            f"{self.bot_username}"
        )

    # ==========================================
    # REPORT GROUP PROPERTIES
    # ==========================================

    @property
    def report_topics(
        self,
    ) -> dict[str, int]:
        """
        Робочі Topics для окремих
        частин мережі.

        Порожні значення автоматично
        не потрапляють у словник.
        """

        topics: dict[
            str,
            int,
        ] = {}

        if (
            self.report_topic_vinnytsia
            is not None
        ):
            topics[
                "vinnytsia"
            ] = (
                self.report_topic_vinnytsia
            )

        if (
            self.report_topic_khmelnytskyi_1
            is not None
        ):
            topics[
                "khmelnytskyi_1"
            ] = (
                self.report_topic_khmelnytskyi_1
            )

        if (
            self.report_topic_khmelnytskyi_2
            is not None
        ):
            topics[
                "khmelnytskyi_2"
            ] = (
                self.report_topic_khmelnytskyi_2
            )

        return topics

    @property
    def report_topic_ids(
        self,
    ) -> tuple[int, ...]:
        """
        IDs усіх робочих report Topics.
        """

        return tuple(
            self.report_topics.values()
        )

    @property
    def effective_closing_group_id(
        self,
    ) -> int | None:
        """
        Основна група для closing/report
        повідомлень.

        Новий REPORT_GROUP_CHAT_ID
        має пріоритет.

        CLOSING_GROUP_ID залишається
        fallback для старого коду.
        """

        return (
            self.report_group_chat_id
            or self.closing_group_id
        )

    @property
    def has_report_group(
        self,
    ) -> bool:
        """
        Чи налаштована Telegram-група
        для звітів.
        """

        return (
            self.report_group_chat_id
            is not None
        )

    @property
    def has_network_cash_topic(
        self,
    ) -> bool:
        """
        Чи налаштована генеральна гілка
        для сумарної каси.
        """

        return (
            self.report_group_chat_id
            is not None
            and self.network_cash_topic_id
            is not None
        )

    # ==========================================
    # ENVIRONMENT PROPERTIES
    # ==========================================

    @property
    def is_development(
        self,
    ) -> bool:
        return (
            self.app_env
            == "development"
        )

    @property
    def is_testing(
        self,
    ) -> bool:
        return (
            self.app_env
            == "testing"
        )

    @property
    def is_production(
        self,
    ) -> bool:
        return (
            self.app_env
            == "production"
        )

    # ==========================================
    # ADMIN
    # ==========================================

    def is_root_admin(
        self,
        telegram_id: int,
    ) -> bool:
        """
        Перевіряє роль головного
        адміністратора.
        """

        return (
            telegram_id
            in self.root_admin_ids
        )

    # ==========================================
    # DIRECTORIES
    # ==========================================

    def create_required_directories(
        self,
    ) -> None:
        """
        Створює службові папки.
        """

        self.reports_directory.mkdir(
            parents=True,
            exist_ok=True,
        )


@lru_cache(
    maxsize=1
)
def get_settings() -> Settings:
    """
    Створює і повертає налаштування.
    """

    app_settings = Settings()

    app_settings.create_required_directories()

    return app_settings


settings = get_settings()