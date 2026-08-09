from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.scheduler.cleanup_jobs import cleanup_job
from app.scheduler.closing_jobs import (
    prepare_closing_records_job,
    process_closing_deadlines_job,
    refresh_closing_summaries_job,
)
from app.scheduler.notification_jobs import (
    process_notifications_job,
)
from app.scheduler.opening_jobs import (
    prepare_opening_records_job,
    process_opening_deadlines_job,
    refresh_opening_summaries_job,
)
from app.scheduler.summary_jobs import (
    process_closing_summaries_job,
    process_opening_summaries_job,
    recover_pending_summaries_job,
)


logger = logging.getLogger(__name__)


_scheduler: AsyncIOScheduler | None = None


def create_scheduler(
    *,
    bot: Bot,
) -> AsyncIOScheduler:
    """
    Створює та конфігурує APScheduler.

    Scheduler запускається в тому ж asyncio loop,
    що й FastAPI + Telegram bot.
    """

    scheduler = AsyncIOScheduler(
        timezone=settings.timezone,
    )

    check_interval = (
        settings.scheduler_check_interval_seconds
    )

    # =====================================================
    # OPENING
    # =====================================================

    scheduler.add_job(
        prepare_opening_records_job,
        trigger=IntervalTrigger(
            minutes=5,
        ),
        kwargs={
            "bot": bot,
        },
        id="prepare_opening_records",
        name="Prepare daily opening records",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    scheduler.add_job(
        process_opening_deadlines_job,
        trigger=IntervalTrigger(
            seconds=check_interval,
        ),
        kwargs={
            "bot": bot,
        },
        id="process_opening_deadlines",
        name="Process opening deadlines",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    scheduler.add_job(
        refresh_opening_summaries_job,
        trigger=IntervalTrigger(
            minutes=2,
        ),
        kwargs={
            "bot": bot,
        },
        id="refresh_opening_summaries",
        name="Refresh opening summaries",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    # =====================================================
    # CLOSING
    # =====================================================

    scheduler.add_job(
        prepare_closing_records_job,
        trigger=IntervalTrigger(
            minutes=5,
        ),
        kwargs={
            "bot": bot,
        },
        id="prepare_closing_records",
        name="Prepare daily closing records",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    scheduler.add_job(
        process_closing_deadlines_job,
        trigger=IntervalTrigger(
            seconds=check_interval,
        ),
        kwargs={
            "bot": bot,
        },
        id="process_closing_deadlines",
        name="Process closing deadlines",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    scheduler.add_job(
        refresh_closing_summaries_job,
        trigger=IntervalTrigger(
            minutes=2,
        ),
        kwargs={
            "bot": bot,
        },
        id="refresh_closing_summaries",
        name="Refresh closing summaries",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    # =====================================================
    # TELEGRAM NOTIFICATION QUEUE
    # =====================================================

    scheduler.add_job(
        process_notifications_job,
        trigger=IntervalTrigger(
            seconds=check_interval,
        ),
        kwargs={
            "bot": bot,
        },
        id="process_notifications",
        name="Process notification queue",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    # =====================================================
    # LIVE SUMMARIES
    # =====================================================

    scheduler.add_job(
        process_opening_summaries_job,
        trigger=IntervalTrigger(
            minutes=1,
        ),
        kwargs={
            "bot": bot,
        },
        id="process_opening_summaries",
        name="Sync opening live summaries",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    scheduler.add_job(
        process_closing_summaries_job,
        trigger=IntervalTrigger(
            minutes=1,
        ),
        kwargs={
            "bot": bot,
        },
        id="process_closing_summaries",
        name="Sync closing live summaries",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )

    scheduler.add_job(
        recover_pending_summaries_job,
        trigger=IntervalTrigger(
            minutes=3,
        ),
        kwargs={
            "bot": bot,
        },
        id="recover_pending_summaries",
        name="Recover pending summaries",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=180,
    )

    # =====================================================
    # CLEANUP
    # =====================================================

    scheduler.add_job(
        cleanup_job,
        trigger=IntervalTrigger(
            minutes=30,
        ),
        id="scheduler_cleanup",
        name="Scheduler cleanup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    logger.info(
        "Scheduler configured | jobs=%s "
        "check_interval=%ss timezone=%s",
        len(scheduler.get_jobs()),
        check_interval,
        settings.timezone,
    )

    return scheduler


def get_scheduler(
    *,
    bot: Bot | None = None,
) -> AsyncIOScheduler:
    """
    Повертає singleton scheduler.

    При першому виклику необхідно передати bot.
    """

    global _scheduler

    if _scheduler is None:
        if bot is None:
            raise RuntimeError(
                "Scheduler is not initialized. "
                "Pass bot on first call."
            )

        _scheduler = create_scheduler(
            bot=bot,
        )

    return _scheduler


def start_scheduler(
    *,
    bot: Bot,
) -> AsyncIOScheduler:
    """
    Запускає scheduler.

    Повторний виклик не запускає
    другий scheduler.
    """

    scheduler = get_scheduler(
        bot=bot,
    )

    if scheduler.running:
        logger.warning(
            "Scheduler already running"
        )
        return scheduler

    scheduler.start()

    logger.info(
        "Scheduler started | jobs=%s",
        len(scheduler.get_jobs()),
    )

    return scheduler


def shutdown_scheduler() -> None:
    """
    Коректно зупиняє scheduler.
    """

    global _scheduler

    if _scheduler is None:
        return

    try:
        if _scheduler.running:
            _scheduler.shutdown(
                wait=False,
            )

            logger.info(
                "Scheduler stopped"
            )

    except Exception:
        logger.exception(
            "Failed to shutdown scheduler"
        )

    finally:
        _scheduler = None


__all__ = [
    "create_scheduler",
    "get_scheduler",
    "start_scheduler",
    "shutdown_scheduler",
]