from __future__ import annotations

from aiogram import Bot

from app.scheduler.cleanup_jobs import (
    cleanup_job,
)
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


async def run_minute_jobs(
    *,
    bot: Bot,
) -> None:
    """
    Основний набір частих scheduler jobs.

    Може використовуватись окремим worker,
    ручним запуском або тестами.
    """

    await prepare_opening_records_job(
        bot=bot,
    )

    await process_opening_deadlines_job(
        bot=bot,
    )

    await prepare_closing_records_job(
        bot=bot,
    )

    await process_closing_deadlines_job(
        bot=bot,
    )

    await process_notifications_job(
        bot=bot,
    )

    await process_opening_summaries_job(
        bot=bot,
    )

    await process_closing_summaries_job(
        bot=bot,
    )


async def run_recovery_jobs(
    *,
    bot: Bot,
) -> None:
    """
    Відновлення стану після рестарту.
    """

    await refresh_opening_summaries_job(
        bot=bot,
    )

    await refresh_closing_summaries_job(
        bot=bot,
    )

    await recover_pending_summaries_job(
        bot=bot,
    )


async def run_cleanup_jobs() -> None:
    """
    Періодичний cleanup.
    """

    await cleanup_job()


__all__ = [
    "run_minute_jobs",
    "run_recovery_jobs",
    "run_cleanup_jobs",
]