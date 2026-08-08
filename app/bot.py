from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.handlers import get_handlers_router


logger = logging.getLogger(__name__)


_bot: Bot | None = None
_dispatcher: Dispatcher | None = None


def create_bot() -> Bot:
    """
    Створює Telegram Bot.
    """

    token = settings.bot_token.get_secret_value()

    if not token:
        raise RuntimeError(
            "BOT_TOKEN не заданий у .env"
        )

    return Bot(
        token=token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )


def create_dispatcher() -> Dispatcher:
    """
    Створює Dispatcher
    та підключає всі handlers.
    """

    dispatcher = Dispatcher()

    dispatcher.include_router(
        get_handlers_router()
    )

    return dispatcher


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

    # Якщо раніше був webhook —
    # прибираємо його перед polling.
    await bot.delete_webhook(
        drop_pending_updates=False,
    )

    await dispatcher.start_polling(
        bot,
        allowed_updates=(
            dispatcher.resolve_used_update_types()
        ),
    )


async def shutdown_bot() -> None:
    """
    Коректно закриває HTTP session Telegram Bot.
    """

    global _bot

    if _bot is None:
        return

    try:
        await _bot.session.close()

    except Exception:
        logger.exception(
            "Failed to close bot session"
        )

    finally:
        _bot = None


__all__ = [
    "create_bot",
    "create_dispatcher",
    "get_bot_and_dispatcher",
    "run_polling",
    "shutdown_bot",
]