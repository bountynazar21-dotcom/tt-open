from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from contextlib import suppress

import uvicorn
from fastapi import FastAPI
from sqlalchemy import text

from app.database.session import engine

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
    # TEMP: PRODUCTION AUDIT SCHEMA DIAGNOSTIC
    # =====================================================

    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    '''
                    SELECT
                        ordinal_position,
                        column_name,
                        data_type,
                        udt_name,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'audit_logs'
                    ORDER BY ordinal_position
                    '''
                )
            )

            rows = result.fetchall()

            logger.warning(
                "AUDIT_SCHEMA_BEGIN"
            )

            if not rows:
                logger.warning(
                    "AUDIT_SCHEMA_TABLE_NOT_FOUND"
                )

            for row in rows:
                logger.warning(
                    "AUDIT_SCHEMA_COLUMN | "
                    "position=%s | "
                    "name=%s | "
                    "type=%s | "
                    "udt=%s | "
                    "nullable=%s | "
                    "default=%s",
                    row.ordinal_position,
                    row.column_name,
                    row.data_type,
                    row.udt_name,
                    row.is_nullable,
                    row.column_default,
                )

            result = await connection.execute(
                text(
                    '''
                    SELECT
                        con.conname,
                        pg_get_constraintdef(con.oid)
                    FROM pg_constraint AS con
                    JOIN pg_class AS rel
                      ON rel.oid = con.conrelid
                    JOIN pg_namespace AS nsp
                      ON nsp.oid = rel.relnamespace
                    WHERE nsp.nspname = 'public'
                      AND rel.relname = 'audit_logs'
                    ORDER BY con.conname
                    '''
                )
            )

            for row in result:
                logger.warning(
                    "AUDIT_SCHEMA_CONSTRAINT | "
                    "name=%s | definition=%s",
                    row[0],
                    row[1],
                )

            logger.warning(
                "AUDIT_SCHEMA_END"
            )

    except Exception:
        logger.exception(
            "AUDIT_SCHEMA_DIAGNOSTIC_FAILED"
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