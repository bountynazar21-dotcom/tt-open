from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

from app.config import settings


STANDARD_LOG_RECORD_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
}


class ConsoleFormatter(logging.Formatter):
    """Зручний формат логів для локальної розробки."""

    LEVEL_ICONS = {
        logging.DEBUG: "🔍",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🚨",
    }

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()

        timestamp = datetime.fromtimestamp(
            record.created,
            tz=UTC,
        ).astimezone().strftime("%Y-%m-%d %H:%M:%S")

        icon = self.LEVEL_ICONS.get(record.levelno, "•")

        base_message = (
            f"{timestamp} | "
            f"{icon} {record.levelname:<8} | "
            f"{record.name} | "
            f"{record.message}"
        )

        extra_fields = self._extract_extra_fields(record)

        if extra_fields:
            formatted_fields = " | ".join(
                f"{key}={value}"
                for key, value in extra_fields.items()
            )
            base_message = f"{base_message} | {formatted_fields}"

        if record.exc_info:
            exception_text = self.formatException(record.exc_info)
            base_message = f"{base_message}\n{exception_text}"

        if record.stack_info:
            base_message = f"{base_message}\n{record.stack_info}"

        return base_message

    @staticmethod
    def _extract_extra_fields(
        record: logging.LogRecord,
    ) -> dict[str, Any]:
        return {
            key: value
            for key, value in record.__dict__.items()
            if key not in STANDARD_LOG_RECORD_FIELDS
            and not key.startswith("_")
        }


class JsonFormatter(logging.Formatter):
    """
    JSON-формат логів для Railway та production.

    Кожен лог записується одним JSON-об'єктом.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=UTC,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }

        extra_fields = {
            key: self._serialize_value(value)
            for key, value in record.__dict__.items()
            if key not in STANDARD_LOG_RECORD_FIELDS
            and not key.startswith("_")
        }

        if extra_fields:
            log_data["extra"] = extra_fields

        if record.exc_info:
            exception_type, exception_value, exception_tb = record.exc_info

            log_data["exception"] = {
                "type": (
                    exception_type.__name__
                    if exception_type
                    else None
                ),
                "message": str(exception_value),
                "traceback": "".join(
                    traceback.format_exception(
                        exception_type,
                        exception_value,
                        exception_tb,
                    )
                ),
            }

        if record.stack_info:
            log_data["stack_info"] = record.stack_info

        return json.dumps(
            log_data,
            ensure_ascii=False,
            default=str,
        )

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(
            value,
            (
                str,
                int,
                float,
                bool,
                type(None),
            ),
        ):
            return value

        if isinstance(value, (list, tuple, set)):
            return [
                JsonFormatter._serialize_value(item)
                for item in value
            ]

        if isinstance(value, dict):
            return {
                str(key): JsonFormatter._serialize_value(item)
                for key, item in value.items()
            }

        return str(value)


class SensitiveDataFilter(logging.Filter):
    """Приховує токен бота та секрети у логах."""

    def __init__(self) -> None:
        super().__init__()

        self.sensitive_values = {
            settings.bot_token.get_secret_value(),
            settings.secret_key.get_secret_value(),
            settings.invite_token_salt.get_secret_value(),
        }

        if settings.webhook_secret:
            self.sensitive_values.add(settings.webhook_secret)

        self.sensitive_values.discard("")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        sanitized_message = self._sanitize(message)

        record.msg = sanitized_message
        record.args = ()

        for key, value in list(record.__dict__.items()):
            if key in STANDARD_LOG_RECORD_FIELDS:
                continue

            if isinstance(value, str):
                record.__dict__[key] = self._sanitize(value)

        return True

    def _sanitize(self, value: str) -> str:
        result = value

        for sensitive_value in self.sensitive_values:
            if sensitive_value:
                result = result.replace(
                    sensitive_value,
                    "***HIDDEN***",
                )

        return result


def configure_logging() -> None:
    """
    Налаштовує логування для всього застосунку.

    Викликати один раз на старті програми.
    """

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    root_logger.setLevel(
        getattr(logging, settings.log_level)
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(
        getattr(logging, settings.log_level)
    )

    if settings.log_format == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = ConsoleFormatter()

    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(SensitiveDataFilter())

    root_logger.addHandler(stream_handler)

    _configure_library_loggers()

    logging.captureWarnings(True)

    logger = logging.getLogger(__name__)
    logger.info(
        "Логування налаштовано",
        extra={
            "environment": settings.app_env,
            "level": settings.log_level,
            "format": settings.log_format,
        },
    )


def _configure_library_loggers() -> None:
    """Зменшує кількість зайвих системних повідомлень."""

    library_levels = {
        "aiogram": logging.INFO,
        "aiogram.event": logging.INFO,
        "aiogram.dispatcher": logging.INFO,
        "sqlalchemy.engine": (
            logging.INFO
            if settings.database_echo
            else logging.WARNING
        ),
        "sqlalchemy.pool": logging.WARNING,
        "alembic": logging.INFO,
        "apscheduler": logging.INFO,
        "asyncio": (
            logging.DEBUG
            if settings.debug
            else logging.WARNING
        ),
        "uvicorn": logging.INFO,
        "uvicorn.access": logging.INFO,
        "httpx": logging.WARNING,
    }

    for logger_name, level in library_levels.items():
        logging.getLogger(logger_name).setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Повертає logger для конкретного модуля."""

    return logging.getLogger(name)