from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import (
    CallbackQuery,
    Message,
    TelegramObject,
    Update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.access import AccessDeniedError


logger = logging.getLogger(__name__)


HandlerType = Callable[
    [TelegramObject, dict[str, Any]],
    Awaitable[Any],
]


@dataclass(slots=True, frozen=True)
class ErrorInfo:
    """
    Нормалізована інформація про помилку.
    """

    exception_type: str

    message: str

    user_message: str

    is_expected: bool

    should_log_traceback: bool

    occurred_at: datetime


class ErrorHandlerMiddleware(
    BaseMiddleware
):
    """
    Глобальний middleware обробки помилок.

    Основне завдання:

    - не дати одному exception
      зупинити polling;
    - зробити rollback транзакції;
    - показати користувачу зрозуміле
      повідомлення;
    - не показувати внутрішні traceback;
    - записати технічну помилку в лог.

    Очікувані помилки:

        AccessDeniedError
        ValueError
        PermissionError

    Неочікувані:

        RuntimeError
        AttributeError
        SQLAlchemy errors
        інші Exception
    """

    DEFAULT_USER_MESSAGE = (
        "⚠️ Сталася технічна помилка.\n\n"
        "Спробуйте повторити дію ще раз."
    )

    ACCESS_DENIED_MESSAGE = (
        "⛔ У вас немає доступу "
        "до цієї дії."
    )

    TELEGRAM_ERROR_MESSAGE = (
        "⚠️ Telegram тимчасово не зміг "
        "виконати цю дію.\n\n"
        "Спробуйте ще раз."
    )

    RETRY_AFTER_MESSAGE = (
        "⏳ Telegram просить трохи "
        "зачекати перед повторною дією."
    )

    def __init__(
        self,
        *,
        notify_user: bool = True,
        re_raise_unhandled: bool = False,
    ) -> None:
        """
        notify_user:
            показувати користувачу
            повідомлення про помилку.

        re_raise_unhandled:
            повторно піднімати неочікувану
            помилку після логування.

        Для production рекомендовано:

            re_raise_unhandled=False
        """

        self.notify_user = notify_user

        self.re_raise_unhandled = (
            re_raise_unhandled
        )

    # =====================================================
    # MIDDLEWARE ENTRY
    # =====================================================

    async def __call__(
        self,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        Виконує handler та перехоплює exception.
        """

        try:
            return await handler(
                event,
                data,
            )

        except asyncio.CancelledError:
            # CancelledError не можна ковтати.
            raise

        except TelegramRetryAfter as error:
            await self.rollback_database(
                data
            )

            self.log_retry_after(
                error=error,
                event=event,
                data=data,
            )

            if self.notify_user:
                await self.safe_notify(
                    event=event,
                    text=(
                        self.RETRY_AFTER_MESSAGE
                    ),
                )

            return None

        except TelegramForbiddenError as error:
            await self.rollback_database(
                data
            )

            self.log_telegram_error(
                error=error,
                event=event,
                data=data,
                level=logging.WARNING,
            )

            # Якщо користувач заблокував бота,
            # відповідати йому вже неможливо.
            return None

        except TelegramBadRequest as error:
            await self.rollback_database(
                data
            )

            self.log_telegram_error(
                error=error,
                event=event,
                data=data,
                level=logging.WARNING,
            )

            if self.notify_user:
                await self.safe_notify(
                    event=event,
                    text=(
                        self.TELEGRAM_ERROR_MESSAGE
                    ),
                )

            return None

        except (
            TelegramNetworkError,
            TelegramServerError,
        ) as error:
            await self.rollback_database(
                data
            )

            self.log_telegram_error(
                error=error,
                event=event,
                data=data,
                level=logging.ERROR,
            )

            if self.notify_user:
                await self.safe_notify(
                    event=event,
                    text=(
                        self.TELEGRAM_ERROR_MESSAGE
                    ),
                )

            return None

        except TelegramAPIError as error:
            await self.rollback_database(
                data
            )

            self.log_telegram_error(
                error=error,
                event=event,
                data=data,
                level=logging.ERROR,
            )

            if self.notify_user:
                await self.safe_notify(
                    event=event,
                    text=(
                        self.TELEGRAM_ERROR_MESSAGE
                    ),
                )

            return None

        except Exception as error:
            await self.rollback_database(
                data
            )

            info = self.normalize_error(
                error
            )

            self.log_error(
                error=error,
                info=info,
                event=event,
                data=data,
            )

            if self.notify_user:
                await self.safe_notify(
                    event=event,
                    text=info.user_message,
                )

            if (
                self.re_raise_unhandled
                and not info.is_expected
            ):
                raise

            return None

    # =====================================================
    # NORMALIZE ERROR
    # =====================================================

    def normalize_error(
        self,
        error: Exception,
    ) -> ErrorInfo:
        """
        Перетворює exception у ErrorInfo.
        """

        occurred_at = datetime.now(
            UTC
        )

        # -------------------------------------------------
        # ACCESS
        # -------------------------------------------------

        if isinstance(
            error,
            AccessDeniedError,
        ):
            message = self.clean_error_text(
                str(error)
            )

            return ErrorInfo(
                exception_type=(
                    type(error).__name__
                ),

                message=message,

                user_message=(
                    message
                    or self.ACCESS_DENIED_MESSAGE
                ),

                is_expected=True,

                should_log_traceback=False,

                occurred_at=occurred_at,
            )

        # -------------------------------------------------
        # VALUE ERROR
        # -------------------------------------------------

        if isinstance(
            error,
            ValueError,
        ):
            message = self.clean_error_text(
                str(error)
            )

            return ErrorInfo(
                exception_type=(
                    type(error).__name__
                ),

                message=message,

                user_message=(
                    f"⚠️ {message}"
                    if message
                    else (
                        "⚠️ Некоректні дані."
                    )
                ),

                is_expected=True,

                should_log_traceback=False,

                occurred_at=occurred_at,
            )

        # -------------------------------------------------
        # PERMISSION ERROR
        # -------------------------------------------------

        if isinstance(
            error,
            PermissionError,
        ):
            return ErrorInfo(
                exception_type=(
                    type(error).__name__
                ),

                message=self.clean_error_text(
                    str(error)
                ),

                user_message=(
                    self.ACCESS_DENIED_MESSAGE
                ),

                is_expected=True,

                should_log_traceback=False,

                occurred_at=occurred_at,
            )

        # -------------------------------------------------
        # FILE
        # -------------------------------------------------

        if isinstance(
            error,
            FileNotFoundError,
        ):
            return ErrorInfo(
                exception_type=(
                    type(error).__name__
                ),

                message=self.clean_error_text(
                    str(error)
                ),

                user_message=(
                    "⚠️ Файл не знайдено."
                ),

                is_expected=True,

                should_log_traceback=False,

                occurred_at=occurred_at,
            )

        # -------------------------------------------------
        # UNEXPECTED
        # -------------------------------------------------

        return ErrorInfo(
            exception_type=(
                type(error).__name__
            ),

            message=self.clean_error_text(
                str(error)
            ),

            user_message=(
                self.DEFAULT_USER_MESSAGE
            ),

            is_expected=False,

            should_log_traceback=True,

            occurred_at=occurred_at,
        )

    # =====================================================
    # DATABASE ROLLBACK
    # =====================================================

    async def rollback_database(
        self,
        data: dict[str, Any],
    ) -> None:
        """
        Робить rollback поточної AsyncSession.

        DatabaseMiddleware також має
        rollback, але тут робимо додатковий
        захист на випадок, якщо error middleware
        стоїть усередині DB middleware.
        """

        session = self.find_session(
            data
        )

        if session is None:
            return

        try:
            if session.in_transaction():
                await session.rollback()

        except Exception:
            logger.exception(
                "Не вдалося виконати "
                "rollback AsyncSession."
            )

    @staticmethod
    def find_session(
        data: dict[str, Any],
    ) -> AsyncSession | None:
        """
        Шукає AsyncSession у middleware data.
        """

        for key in (
            "session",
            "db_session",
        ):
            value = data.get(
                key
            )

            if isinstance(
                value,
                AsyncSession,
            ):
                return value

        db_context = data.get(
            "db_context"
        )

        if db_context is not None:
            value = getattr(
                db_context,
                "session",
                None,
            )

            if isinstance(
                value,
                AsyncSession,
            ):
                return value

        repositories = data.get(
            "repositories"
        )

        if repositories is not None:
            value = getattr(
                repositories,
                "session",
                None,
            )

            if isinstance(
                value,
                AsyncSession,
            ):
                return value

        return None

    # =====================================================
    # USER NOTIFICATION
    # =====================================================

    async def safe_notify(
        self,
        *,
        event: TelegramObject,
        text: str,
    ) -> bool:
        """
        Безпечно повідомляє користувача.

        Підтримує:

            Message
            CallbackQuery
            Update
        """

        message = self.extract_message(
            event
        )

        callback = self.extract_callback(
            event
        )

        # -------------------------------------------------
        # CALLBACK
        # -------------------------------------------------

        if callback is not None:
            try:
                await callback.answer(
                    self.callback_text(
                        text
                    ),
                    show_alert=True,
                )

                return True

            except TelegramAPIError:
                # Callback уже міг протухнути.
                pass

            except Exception:
                logger.debug(
                    "Не вдалося відповісти "
                    "на CallbackQuery.",
                    exc_info=True,
                )

        # -------------------------------------------------
        # MESSAGE
        # -------------------------------------------------

        if message is not None:
            try:
                await message.answer(
                    text
                )

                return True

            except TelegramForbiddenError:
                return False

            except TelegramAPIError:
                logger.debug(
                    "Не вдалося відправити "
                    "повідомлення про помилку.",
                    exc_info=True,
                )

            except Exception:
                logger.debug(
                    "Помилка під час "
                    "safe_notify.",
                    exc_info=True,
                )

        return False

    # =====================================================
    # EVENT EXTRACTORS
    # =====================================================

    @staticmethod
    def extract_message(
        event: TelegramObject,
    ) -> Message | None:
        """
        Витягує Message з event.
        """

        if isinstance(
            event,
            Message,
        ):
            return event

        if isinstance(
            event,
            CallbackQuery,
        ):
            if isinstance(
                event.message,
                Message,
            ):
                return event.message

            return None

        if isinstance(
            event,
            Update,
        ):
            if event.message:
                return event.message

            if (
                event.callback_query
                and isinstance(
                    event.callback_query.message,
                    Message,
                )
            ):
                return (
                    event
                    .callback_query
                    .message
                )

            if event.edited_message:
                return (
                    event.edited_message
                )

            if event.channel_post:
                return (
                    event.channel_post
                )

            if event.edited_channel_post:
                return (
                    event.edited_channel_post
                )

        return None

    @staticmethod
    def extract_callback(
        event: TelegramObject,
    ) -> CallbackQuery | None:
        """
        Витягує CallbackQuery.
        """

        if isinstance(
            event,
            CallbackQuery,
        ):
            return event

        if isinstance(
            event,
            Update,
        ):
            return (
                event.callback_query
            )

        return None

    # =====================================================
    # LOGGING
    # =====================================================

    def log_error(
        self,
        *,
        error: Exception,
        info: ErrorInfo,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> None:
        """
        Логує звичайний Exception.
        """

        context = self.build_log_context(
            event=event,
            data=data,
        )

        if info.is_expected:
            logger.warning(
                (
                    "Очікувана помилка "
                    "%s: %s | %s"
                ),
                info.exception_type,
                info.message,
                context,
            )

            return

        if info.should_log_traceback:
            logger.error(
                (
                    "Необроблена помилка "
                    "%s: %s | %s\n%s"
                ),
                info.exception_type,
                info.message,
                context,
                "".join(
                    traceback.format_exception(
                        type(error),
                        error,
                        error.__traceback__,
                    )
                ),
            )

        else:
            logger.error(
                (
                    "Помилка %s: %s | %s"
                ),
                info.exception_type,
                info.message,
                context,
            )

    def log_telegram_error(
        self,
        *,
        error: TelegramAPIError,
        event: TelegramObject,
        data: dict[str, Any],
        level: int,
    ) -> None:
        """
        Логує помилку Telegram API.
        """

        context = self.build_log_context(
            event=event,
            data=data,
        )

        logger.log(
            level,
            (
                "Telegram API error "
                "%s: %s | %s"
            ),
            type(error).__name__,
            self.clean_error_text(
                str(error)
            ),
            context,
        )

    def log_retry_after(
        self,
        *,
        error: TelegramRetryAfter,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> None:
        """
        Логує Telegram flood control.
        """

        context = self.build_log_context(
            event=event,
            data=data,
        )

        retry_after = getattr(
            error,
            "retry_after",
            None,
        )

        logger.warning(
            (
                "TelegramRetryAfter: "
                "retry_after=%s | %s"
            ),
            retry_after,
            context,
        )

    # =====================================================
    # LOG CONTEXT
    # =====================================================

    def build_log_context(
        self,
        *,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> str:
        """
        Формує короткий контекст update.
        """

        user_id = self.extract_user_id(
            event=event,
            data=data,
        )

        chat_id = self.extract_chat_id(
            event
        )

        update_id = self.extract_update_id(
            event
        )

        event_type = type(
            event
        ).__name__

        parts = [
            f"event={event_type}",
        ]

        if update_id is not None:
            parts.append(
                f"update_id={update_id}"
            )

        if user_id is not None:
            parts.append(
                f"user_id={user_id}"
            )

        if chat_id is not None:
            parts.append(
                f"chat_id={chat_id}"
            )

        return ", ".join(
            parts
        )

    # =====================================================
    # ID EXTRACTION
    # =====================================================

    @staticmethod
    def extract_user_id(
        *,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> int | None:
        """
        Telegram user ID.
        """

        event_user = data.get(
            "event_from_user"
        )

        if event_user is not None:
            user_id = getattr(
                event_user,
                "id",
                None,
            )

            if isinstance(
                user_id,
                int,
            ):
                return user_id

        if isinstance(
            event,
            Message,
        ):
            if event.from_user:
                return event.from_user.id

        if isinstance(
            event,
            CallbackQuery,
        ):
            return event.from_user.id

        if isinstance(
            event,
            Update,
        ):
            if (
                event.message
                and event.message.from_user
            ):
                return (
                    event.message
                    .from_user
                    .id
                )

            if event.callback_query:
                return (
                    event
                    .callback_query
                    .from_user
                    .id
                )

        return None

    @staticmethod
    def extract_chat_id(
        event: TelegramObject,
    ) -> int | None:
        """
        Telegram chat ID.
        """

        if isinstance(
            event,
            Message,
        ):
            return event.chat.id

        if isinstance(
            event,
            CallbackQuery,
        ):
            message = event.message

            if isinstance(
                message,
                Message,
            ):
                return message.chat.id

        if isinstance(
            event,
            Update,
        ):
            if event.message:
                return (
                    event.message.chat.id
                )

            if (
                event.callback_query
                and isinstance(
                    event.callback_query.message,
                    Message,
                )
            ):
                return (
                    event
                    .callback_query
                    .message
                    .chat
                    .id
                )

        return None

    @staticmethod
    def extract_update_id(
        event: TelegramObject,
    ) -> int | None:
        """
        Telegram update_id.
        """

        if isinstance(
            event,
            Update,
        ):
            return event.update_id

        return None

    # =====================================================
    # TEXT HELPERS
    # =====================================================

    @staticmethod
    def clean_error_text(
        text: str,
        *,
        max_length: int = 1000,
    ) -> str:
        """
        Нормалізує exception text.
        """

        normalized = " ".join(
            str(text or "")
            .strip()
            .split()
        )

        if len(normalized) > max_length:
            return (
                normalized[
                    : max_length - 3
                ]
                + "..."
            )

        return normalized

    @staticmethod
    def callback_text(
        text: str,
        *,
        max_length: int = 190,
    ) -> str:
        """
        Callback alert має бути коротким.
        """

        # Прибираємо прості HTML-теги,
        # щоб вони не показувались у alert.
        normalized = (
            text
            .replace("<b>", "")
            .replace("</b>", "")
            .replace("<code>", "")
            .replace("</code>", "")
        )

        normalized = " ".join(
            normalized.split()
        )

        if len(normalized) > max_length:
            return (
                normalized[
                    : max_length - 3
                ]
                + "..."
            )

        return normalized


# Зручний alias.
GlobalErrorMiddleware = (
    ErrorHandlerMiddleware
)


__all__ = [
    "ErrorHandlerMiddleware",
    "GlobalErrorMiddleware",
    "ErrorInfo",
]