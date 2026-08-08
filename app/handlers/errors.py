from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any
from uuid import uuid4

from aiogram import Router
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import (
    CallbackQuery,
    Message,
)
from aiogram.types.error_event import (
    ErrorEvent,
)
from pydantic import ValidationError
from sqlalchemy.exc import (
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
)

from app.handlers.common import (
    get_database_user,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="errors",
)


# =========================================================
# CONSTANTS
# =========================================================


IGNORABLE_BAD_REQUEST_MESSAGES = (
    "message is not modified",
    "message to edit not found",
    "message can't be edited",
    "message can not be edited",
    "query is too old",
    "query id is invalid",
    "message to delete not found",
)


# =========================================================
# ERROR CODE
# =========================================================


def generate_error_code() -> str:
    """
    Короткий ID помилки для логів.

    Наприклад:
        A31F04B2

    Користувач може передати його
    адміністратору, якщо проблема
    повторюється.
    """

    return (
        uuid4()
        .hex[
            :8
        ]
        .upper()
    )


# =========================================================
# EXCEPTION TEXT
# =========================================================


def exception_text(
    exception: BaseException,
) -> str:
    """
    Безпечний текст exception.
    """

    try:
        return str(
            exception
        ).strip()

    except Exception:
        return (
            exception
            .__class__
            .__name__
        )


def normalized_exception_text(
    exception: BaseException,
) -> str:
    """
    Lowercase exception text.
    """

    return exception_text(
        exception
    ).lower()


# =========================================================
# TELEGRAM UPDATE CONTEXT
# =========================================================


def extract_callback(
    event: ErrorEvent,
) -> CallbackQuery | None:
    """
    CallbackQuery із Update.
    """

    update = getattr(
        event,
        "update",
        None,
    )

    if update is None:
        return None

    callback = getattr(
        update,
        "callback_query",
        None,
    )

    if isinstance(
        callback,
        CallbackQuery,
    ):
        return callback

    return None


def extract_message(
    event: ErrorEvent,
) -> Message | None:
    """
    Message із Update.

    Перевіряємо кілька типів
    Telegram update.
    """

    update = getattr(
        event,
        "update",
        None,
    )

    if update is None:
        return None

    for attr_name in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
    ):
        value = getattr(
            update,
            attr_name,
            None,
        )

        if isinstance(
            value,
            Message,
        ):
            return value

    callback = extract_callback(
        event
    )

    if callback is not None:
        callback_message = getattr(
            callback,
            "message",
            None,
        )

        if isinstance(
            callback_message,
            Message,
        ):
            return callback_message

    return None


def extract_telegram_user_id(
    event: ErrorEvent,
) -> int | None:
    """
    Telegram user ID, якщо доступний.
    """

    callback = extract_callback(
        event
    )

    if (
        callback is not None
        and callback.from_user is not None
    ):
        return callback.from_user.id

    message = extract_message(
        event
    )

    if (
        message is not None
        and message.from_user is not None
    ):
        return message.from_user.id

    update = getattr(
        event,
        "update",
        None,
    )

    if update is None:
        return None

    for attr_name in (
        "inline_query",
        "chosen_inline_result",
        "shipping_query",
        "pre_checkout_query",
        "my_chat_member",
        "chat_member",
    ):
        obj = getattr(
            update,
            attr_name,
            None,
        )

        user = getattr(
            obj,
            "from_user",
            None,
        )

        if user is not None:
            return getattr(
                user,
                "id",
                None,
            )

    return None


def extract_chat_id(
    event: ErrorEvent,
) -> int | None:
    """
    Chat ID.
    """

    message = extract_message(
        event
    )

    if (
        message is not None
        and message.chat is not None
    ):
        return message.chat.id

    callback = extract_callback(
        event
    )

    if callback is not None:
        callback_message = getattr(
            callback,
            "message",
            None,
        )

        chat = getattr(
            callback_message,
            "chat",
            None,
        )

        if chat is not None:
            return getattr(
                chat,
                "id",
                None,
            )

    return None


def extract_update_id(
    event: ErrorEvent,
) -> int | None:
    """
    Telegram update_id.
    """

    update = getattr(
        event,
        "update",
        None,
    )

    if update is None:
        return None

    return getattr(
        update,
        "update_id",
        None,
    )


# =========================================================
# DB USER CONTEXT
# =========================================================


def extract_database_user_id(
    data: dict[str, Any],
) -> int | None:
    """
    Internal database user ID.

    Якщо error виник до AuthMiddleware,
    просто поверне None.
    """

    try:
        user = get_database_user(
            data
        )

    except Exception:
        return None

    if user is None:
        return None

    value = getattr(
        user,
        "id",
        None,
    )

    try:
        return (
            int(value)
            if value is not None
            else None
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


# =========================================================
# LOGGING
# =========================================================


def log_exception(
    *,
    event: ErrorEvent,
    exception: BaseException,
    error_code: str,
    data: dict[str, Any],
    level: int = logging.ERROR,
) -> None:
    """
    Повний traceback у лог.

    Користувачу traceback
    ніколи не показуємо.
    """

    context = {
        "error_code":
            error_code,

        "exception":
            exception
            .__class__
            .__name__,

        "update_id":
            extract_update_id(
                event
            ),

        "telegram_user_id":
            extract_telegram_user_id(
                event
            ),

        "db_user_id":
            extract_database_user_id(
                data
            ),

        "chat_id":
            extract_chat_id(
                event
            ),
    }

    logger.log(
        level,
        (
            "Unhandled bot error | "
            "code=%s "
            "type=%s "
            "update_id=%s "
            "telegram_user_id=%s "
            "db_user_id=%s "
            "chat_id=%s | %s"
        ),
        context[
            "error_code"
        ],
        context[
            "exception"
        ],
        context[
            "update_id"
        ],
        context[
            "telegram_user_id"
        ],
        context[
            "db_user_id"
        ],
        context[
            "chat_id"
        ],
        exception_text(
            exception
        ),
        exc_info=(
            type(
                exception
            ),
            exception,
            exception.__traceback__,
        ),
    )


# =========================================================
# DATABASE ROLLBACK
# =========================================================


async def rollback_object(
    target: Any,
) -> bool:
    """
    Пробує викликати rollback()
    на конкретному object.
    """

    if target is None:
        return False

    rollback = getattr(
        target,
        "rollback",
        None,
    )

    if not callable(
        rollback
    ):
        return False

    try:
        result = rollback()

        if inspect.isawaitable(
            result
        ):
            await result

        return True

    except Exception:
        logger.exception(
            "Failed to rollback database "
            "transaction"
        )

        return False


async def rollback_database(
    data: dict[str, Any],
) -> bool:
    """
    Після SQLAlchemy exception session
    може залишитись у failed state.

    Тому перед наступним update
    робимо rollback.
    """

    # -----------------------------------------------------
    # DIRECT SESSION
    # -----------------------------------------------------

    for key in (
        "session",
        "db_session",
        "database_session",
    ):
        session = data.get(
            key
        )

        if await rollback_object(
            session
        ):
            return True

    # -----------------------------------------------------
    # REPOSITORIES CONTAINER
    # -----------------------------------------------------

    repositories = data.get(
        "repositories"
    )

    if repositories is not None:
        if await rollback_object(
            repositories
        ):
            return True

        for attr_name in (
            "session",
            "db_session",
        ):
            session = getattr(
                repositories,
                attr_name,
                None,
            )

            if await rollback_object(
                session
            ):
                return True

    return False


# =========================================================
# USER NOTIFICATION
# =========================================================


async def safe_callback_answer(
    callback: CallbackQuery,
    *,
    text: str,
    show_alert: bool = True,
) -> bool:
    """
    Callback може бути вже старим,
    тому callback.answer теж
    іноді кидає TelegramBadRequest.
    """

    try:
        await callback.answer(
            text=text,
            show_alert=show_alert,
        )

        return True

    except (
        TelegramBadRequest,
        TelegramForbiddenError,
    ):
        return False

    except Exception:
        logger.debug(
            "Could not answer callback "
            "after handler error",
            exc_info=True,
        )

        return False


async def safe_message_answer(
    message: Message,
    *,
    text: str,
) -> bool:
    """
    Безпечна відповідь у чат.
    """

    try:
        await message.answer(
            text
        )

        return True

    except (
        TelegramBadRequest,
        TelegramForbiddenError,
    ):
        return False

    except Exception:
        logger.debug(
            "Could not send error message",
            exc_info=True,
        )

        return False


async def notify_user(
    event: ErrorEvent,
    *,
    text: str,
) -> bool:
    """
    Показує користувачу коротке
    повідомлення.

    Пріоритет:
        callback alert
        message.answer
    """

    callback = extract_callback(
        event
    )

    if callback is not None:
        sent = await safe_callback_answer(
            callback,
            text=text,
            show_alert=True,
        )

        if sent:
            return True

    message = extract_message(
        event
    )

    if message is not None:
        return await safe_message_answer(
            message,
            text=text,
        )

    return False


# =========================================================
# IGNORABLE TELEGRAM ERRORS
# =========================================================


def is_ignorable_bad_request(
    exception: TelegramBadRequest,
) -> bool:
    """
    Telegram errors, які не є
    реальною аварією.

    Наприклад:
        message is not modified
    """

    text = normalized_exception_text(
        exception
    )

    return any(
        phrase in text
        for phrase
        in IGNORABLE_BAD_REQUEST_MESSAGES
    )


# =========================================================
# ERROR MESSAGE BUILDERS
# =========================================================


def generic_user_error_text(
    error_code: str,
) -> str:
    """
    Загальна помилка.
    """

    return (
        "⚠️ Сталася технічна помилка.\n\n"
        "Спробуйте повторити дію.\n"
        f"Код: {error_code}"
    )


def database_user_error_text(
    error_code: str,
) -> str:
    """
    Database failure.
    """

    return (
        "⚠️ Не вдалося зберегти "
        "або отримати дані.\n\n"
        "Спробуйте ще раз.\n"
        f"Код: {error_code}"
    )


def conflict_user_error_text(
    error_code: str,
) -> str:
    """
    IntegrityError.
    """

    return (
        "⚠️ Дані конфліктують "
        "з уже існуючим записом.\n\n"
        "Оновіть сторінку або меню "
        "та спробуйте ще раз.\n"
        f"Код: {error_code}"
    )


def telegram_retry_text(
    retry_after: Any,
) -> str:
    """
    Telegram flood control.
    """

    try:
        seconds = max(
            1,
            int(
                retry_after
            ),
        )

    except (
        TypeError,
        ValueError,
    ):
        seconds = 1

    return (
        "⏳ Telegram тимчасово "
        "обмежив кількість запитів.\n\n"
        f"Повторіть дію через "
        f"{seconds} сек."
    )


# =========================================================
# GLOBAL ERROR HANDLER
# =========================================================


@router.error()
async def global_error_handler(
    event: ErrorEvent,
    **data: Any,
) -> bool:
    """
    Глобальний Aiogram error handler.

    Важливо:
        - не показує traceback;
        - не валить polling;
        - rollback БД;
        - Telegram benign errors
          не спамлять користувача.
    """

    exception = event.exception

    # -----------------------------------------------------
    # CANCELLED
    # -----------------------------------------------------
    #
    # Під час нормального shutdown
    # asyncio може скасувати task.
    # Таку подію НЕ потрібно
    # перетворювати на bot error.
    # -----------------------------------------------------

    if isinstance(
        exception,
        asyncio.CancelledError,
    ):
        raise exception

    error_code = generate_error_code()

    # =====================================================
    # TELEGRAM BAD REQUEST
    # =====================================================

    if isinstance(
        exception,
        TelegramBadRequest,
    ):
        if is_ignorable_bad_request(
            exception
        ):
            logger.debug(
                (
                    "Ignored TelegramBadRequest | "
                    "update_id=%s | %s"
                ),
                extract_update_id(
                    event
                ),
                exception_text(
                    exception
                ),
            )

            return True

        log_exception(
            event=event,
            exception=exception,
            error_code=error_code,
            data=data,
            level=logging.WARNING,
        )

        await notify_user(
            event,
            text=(
                "⚠️ Telegram не зміг "
                "виконати цю дію.\n\n"
                "Оновіть меню та "
                "спробуйте ще раз.\n"
                f"Код: {error_code}"
            ),
        )

        return True

    # =====================================================
    # BOT BLOCKED / NO ACCESS
    # =====================================================

    if isinstance(
        exception,
        TelegramForbiddenError,
    ):
        log_exception(
            event=event,
            exception=exception,
            error_code=error_code,
            data=data,
            level=logging.WARNING,
        )

        # Тут часто неможливо
        # написати користувачу,
        # бо саме причина помилки —
        # бот заблокований або
        # видалений із групи.
        return True

    # =====================================================
    # TELEGRAM RATE LIMIT
    # =====================================================

    if isinstance(
        exception,
        TelegramRetryAfter,
    ):
        log_exception(
            event=event,
            exception=exception,
            error_code=error_code,
            data=data,
            level=logging.WARNING,
        )

        retry_after = getattr(
            exception,
            "retry_after",
            1,
        )

        await notify_user(
            event,
            text=telegram_retry_text(
                retry_after
            ),
        )

        # Не робимо автоматичний retry,
        # бо handler міг уже змінити БД,
        # і повтор міг би створити дубль.
        return True

    # =====================================================
    # TELEGRAM NETWORK / SERVER
    # =====================================================

    if isinstance(
        exception,
        (
            TelegramNetworkError,
            TelegramServerError,
        ),
    ):
        log_exception(
            event=event,
            exception=exception,
            error_code=error_code,
            data=data,
            level=logging.WARNING,
        )

        await notify_user(
            event,
            text=(
                "🌐 Тимчасова проблема "
                "зі зв'язком із Telegram.\n\n"
                "Спробуйте ще раз "
                "через кілька секунд.\n"
                f"Код: {error_code}"
            ),
        )

        return True

    # =====================================================
    # DATABASE INTEGRITY
    # =====================================================

    if isinstance(
        exception,
        IntegrityError,
    ):
        await rollback_database(
            data
        )

        log_exception(
            event=event,
            exception=exception,
            error_code=error_code,
            data=data,
        )

        await notify_user(
            event,
            text=conflict_user_error_text(
                error_code
            ),
        )

        return True

    # =====================================================
    # DATABASE CONNECTION / OPERATIONAL
    # =====================================================

    if isinstance(
        exception,
        OperationalError,
    ):
        await rollback_database(
            data
        )

        log_exception(
            event=event,
            exception=exception,
            error_code=error_code,
            data=data,
        )

        await notify_user(
            event,
            text=(
                "🗄 Тимчасово не вдалося "
                "підключитися до бази даних.\n\n"
                "Спробуйте ще раз "
                "через кілька секунд.\n"
                f"Код: {error_code}"
            ),
        )

        return True

    # =====================================================
    # OTHER SQLALCHEMY
    # =====================================================

    if isinstance(
        exception,
        SQLAlchemyError,
    ):
        await rollback_database(
            data
        )

        log_exception(
            event=event,
            exception=exception,
            error_code=error_code,
            data=data,
        )

        await notify_user(
            event,
            text=database_user_error_text(
                error_code
            ),
        )

        return True

    # =====================================================
    # PYDANTIC / CALLBACK DATA / DTO
    # =====================================================

    if isinstance(
        exception,
        ValidationError,
    ):
        log_exception(
            event=event,
            exception=exception,
            error_code=error_code,
            data=data,
        )

        await notify_user(
            event,
            text=(
                "⚠️ Отримано некоректні "
                "дані від старої кнопки "
                "або меню.\n\n"
                "Поверніться в головне меню "
                "та відкрийте розділ заново.\n"
                f"Код: {error_code}"
            ),
        )

        return True

    # =====================================================
    # VALUE / LOOKUP
    # =====================================================

    if isinstance(
        exception,
        (
            ValueError,
            LookupError,
        ),
    ):
        log_exception(
            event=event,
            exception=exception,
            error_code=error_code,
            data=data,
        )

        await notify_user(
            event,
            text=(
                "⚠️ Не вдалося обробити "
                "отримані дані.\n\n"
                "Оновіть меню та "
                "спробуйте ще раз.\n"
                f"Код: {error_code}"
            ),
        )

        return True

    # =====================================================
    # UNKNOWN
    # =====================================================

    # Якщо exception стався після
    # DB operation, rollback зайвим
    # не буде. Якщо transaction чиста,
    # SQLAlchemy просто нічого не змінить.
    await rollback_database(
        data
    )

    log_exception(
        event=event,
        exception=exception,
        error_code=error_code,
        data=data,
    )

    await notify_user(
        event,
        text=generic_user_error_text(
            error_code
        ),
    )

    return True


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "router",

    "IGNORABLE_BAD_REQUEST_MESSAGES",

    "generate_error_code",

    "exception_text",
    "normalized_exception_text",

    "extract_callback",
    "extract_message",

    "extract_telegram_user_id",
    "extract_chat_id",
    "extract_update_id",

    "extract_database_user_id",

    "log_exception",

    "rollback_object",
    "rollback_database",

    "safe_callback_answer",
    "safe_message_answer",
    "notify_user",

    "is_ignorable_bad_request",

    "generic_user_error_text",
    "database_user_error_text",
    "conflict_user_error_text",
    "telegram_retry_text",

    "global_error_handler",
]