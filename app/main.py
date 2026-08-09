from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from contextlib import suppress

import uvicorn
from fastapi import FastAPI

from app.bot import (
    get_bot_and_dispatcher,
    run_polling,
    shutdown_bot,
)
from app.config import settings
from app.scheduler import (
    shutdown_scheduler,
    start_scheduler,
)


logger = logging.getLogger(__name__)


bot_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    """
    Startup / shutdown застосунку.

    Тут запускаються:
    - Telegram bot;
    - APScheduler;
    - FastAPI.
    """

    global bot_task

    logger.info(
        "Starting %s",
        settings.app_name,
    )

    # =====================================================
    # BOT INSTANCE
    # =====================================================

    bot, _ = get_bot_and_dispatcher()

    # =====================================================
    # SCHEDULER
    # =====================================================

    try:
        start_scheduler(
            bot=bot,
        )

        logger.info(
            "Scheduler startup completed"
        )

    except Exception:
        logger.exception(
            "Scheduler startup failed"
        )

        raise

    # =====================================================
    # TELEGRAM
    # =====================================================

    if not settings.use_webhook:
        bot_task = asyncio.create_task(
            run_polling(),
            name="telegram-polling",
        )

        logger.info(
            "Telegram polling task created"
        )

    else:
        logger.info(
            "USE_WEBHOOK=true. "
            "Polling disabled."
        )

    try:
        yield

    finally:
        logger.info(
            "Stopping application..."
        )

        # =================================================
        # STOP SCHEDULER FIRST
        # =================================================

        try:
            shutdown_scheduler()

        except Exception:
            logger.exception(
                "Scheduler shutdown failed"
            )

        # =================================================
        # STOP TELEGRAM POLLING
        # =================================================

        if bot_task is not None:
            bot_task.cancel()

            with suppress(
                asyncio.CancelledError
            ):
                await bot_task

            bot_task = None

        # =================================================
        # CLOSE TELEGRAM HTTP SESSION
        # =================================================

        await shutdown_bot()

        logger.info(
            "Application stopped"
        )


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "ok",
        "app": settings.app_name,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "healthy",
    }


def run() -> None:
    """
    Локальний запуск:
        python -m app.main
    """

    uvicorn.run(
        "app.main:app",
        host=settings.web_server_host,
        port=settings.web_server_port,
        reload=False,
    )


if __name__ == "__main__":
    run()