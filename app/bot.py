from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.database.session import async_session_factory
from app.handlers import get_handlers_router
from app.middlewares import (
    AccessMiddleware,
    AuthMiddleware,
    DatabaseMiddleware,
    ErrorHandlerMiddleware,
    LoggingMiddleware,
    ThrottlingMiddleware,
)


logger = logging.getLogger(__name__)


_bot: Bot | None = None
_dispatcher: Dispatcher | None = None


# =========================================================
# BOT
# =========================================================


def create_bot() -> Bot:
    """
    Створює Telegram Bot.
    """

    token = settings.bot_token.get_secret_value()

    if not token:
        raise RuntimeError(
            "BOT_TOKEN не заданий."
        )

    return Bot(
        token=token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )


# =========================================================
# DISPATCHER
# =========================================================


def create_dispatcher() -> Dispatcher:
    """
    Створює Dispatcher та підключає
    middleware у правильному порядку.

    Порядок:

    Error
        ↓
    Logging
        ↓
    Throttling
        ↓
    Database
        ↓
    Auth
        ↓
    Access
        ↓
    Handlers

    Важливо:
    DatabaseMiddleware знаходиться зовні
    від Auth/Access, тому вони вже мають
    session/repositories/services.

    ErrorHandler знаходиться зовні Database,
    тому exception спочатку доходить до DB,
    де виконується rollback, і тільки після
    цього перехоплюється глобальним handler.
    """

    dispatcher = Dispatcher()

    # =====================================================
    # 1. GLOBAL ERROR HANDLER
    # =====================================================

    dispatcher.update.outer_middleware(
        ErrorHandlerMiddleware(
            notify_user=True,
            re_raise_unhandled=False,
        )
    )

    # =====================================================
    # 2. REQUEST LOGGING
    # =====================================================

    dispatcher.update.outer_middleware(
        LoggingMiddleware(
            log_started=False,
            log_success=True,
            slow_threshold_ms=1500.0,
        )
    )

    # =====================================================
    # 3. ANTI-SPAM / THROTTLING
    # =====================================================

    dispatcher.update.outer_middleware(
        ThrottlingMiddleware(
            notify_messages=False,
        )
    )

    # =====================================================
    # 4. DATABASE
    # =====================================================

    dispatcher.update.outer_middleware(
        DatabaseMiddleware(
            async_session_factory,
            bot_username=settings.bot_username,
            auto_commit=True,
            reuse_existing_session=True,
        )
    )

    # =====================================================
    # 5. AUTHENTICATION
    # =====================================================

    dispatcher.update.outer_middleware(
        AuthMiddleware(
            auto_create_users=True,
            update_profile=True,
            block_inactive_users=True,
            allow_anonymous_updates=True,
        )
    )

    # =====================================================
    # 6. ACCESS CONTEXT
    # =====================================================

    dispatcher.update.outer_middleware(
        AccessMiddleware(
            inject_empty_context=False,
        )
    )

    # =====================================================
    # HANDLERS
    # =====================================================

    dispatcher.include_router(
        get_handlers_router()
    )

    logger.info(
        "Dispatcher configured with middleware chain"
    )

    return dispatcher


# =========================================================
# SINGLETONS
# =========================================================


def get_bot_and_dispatcher() -> tuple[
    Bot,
    Dispatcher,
]:
    """
    Повертає один екземпляр Bot + Dispatcher.
    """

    global _bot
    global _dispatcher

    if _bot is None:
        _bot = create_bot()

    if _dispatcher is None:
        _dispatcher = create_dispatcher()

    return (
        _bot,
        _dispatcher,
    )


# =========================================================
# POLLING
# =========================================================


async def run_polling() -> None:
    """
    Запускає Telegram bot через polling.
    """

    bot, dispatcher = (
        get_bot_and_dispatcher()
    )

    me = await bot.get_me()

    logger.info(
        "Telegram bot started: @%s (%s)",
        me.username,
        me.id,
    )

    # Якщо раніше використовувався webhook,
    # прибираємо його перед polling.
    await bot.delete_webhook(
        drop_pending_updates=False,
    )

    allowed_updates = (
        dispatcher.resolve_used_update_types()
    )

    logger.info(
        "Starting Telegram polling | "
        "allowed_updates=%s",
        allowed_updates,
    )

    await dispatcher.start_polling(
        bot,
        allowed_updates=allowed_updates,
    )


# =========================================================
# SHUTDOWN
# =========================================================


async def shutdown_bot() -> None:
    """
    Коректно закриває Telegram HTTP session.
    """

    global _bot
    global _dispatcher

    if _bot is not None:
        try:
            await _bot.session.close()

        except Exception:
            logger.exception(
                "Failed to close bot session"
            )

    _bot = None
    _dispatcher = None

    logger.info(
        "Telegram bot resources released"
    )


__all__ = [
    "create_bot",
    "create_dispatcher",
    "get_bot_and_dispatcher",
    "run_polling",
    "shutdown_bot",
]