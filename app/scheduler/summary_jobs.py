from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.config import settings
from app.database.session import async_session_factory
from app.repositories import Repositories
from app.scheduler.locks import try_scheduler_lock
from app.services import create_services


logger = logging.getLogger(__name__)


def now_local() -> datetime:
    """
    Поточний час у timezone проєкту.
    """

    return datetime.now(
        ZoneInfo(settings.timezone)
    )


async def process_opening_summaries_job(
    *,
    bot: Bot,
) -> None:
    """
    Формує та синхронізує ранкові
    live-summary повідомлення.
    """

    async with async_session_factory() as session:
        try:
            acquired = await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 401
                ),
            )

            if not acquired:
                logger.debug(
                    "process_opening_summaries_job skipped: "
                    "scheduler lock already held"
                )
                return

            repositories = Repositories(
                session
            )

            services = create_services(
                repositories,
                bot=bot,
                bot_username=settings.bot_username,
            )

            current_time = now_local()

            decisions = (
                await services.opening
                .prepare_summary_updates(
                    business_date=current_time.date(),
                    timezone_name=settings.timezone,
                )
            )

            if not decisions:
                await session.commit()

                logger.debug(
                    "No opening summary updates | date=%s",
                    current_time.date(),
                )
                return

            result = (
                await services.summaries
                .sync_decisions(
                    decisions,
                    commit_each=True,
                )
            )

            await session.commit()

            logger.info(
                "Opening summaries synced | "
                "date=%s total=%s sent=%s "
                "edited=%s recreated=%s "
                "unchanged=%s retry=%s "
                "failed=%s skipped=%s",
                current_time.date(),
                result.total_count,
                result.sent_count,
                result.edited_count,
                result.recreated_count,
                result.unchanged_count,
                result.retry_count,
                result.failed_count,
                result.skipped_count,
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "process_opening_summaries_job failed"
            )

            raise


async def process_closing_summaries_job(
    *,
    bot: Bot,
) -> None:
    """
    Формує та синхронізує вечірні
    live-summary повідомлення.
    """

    async with async_session_factory() as session:
        try:
            acquired = await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 402
                ),
            )

            if not acquired:
                logger.debug(
                    "process_closing_summaries_job skipped: "
                    "scheduler lock already held"
                )
                return

            repositories = Repositories(
                session
            )

            services = create_services(
                repositories,
                bot=bot,
                bot_username=settings.bot_username,
            )

            current_time = now_local()

            decisions = (
                await services.closing
                .prepare_summary_updates(
                    business_date=current_time.date(),
                    timezone_name=settings.timezone,
                )
            )

            if not decisions:
                await session.commit()

                logger.debug(
                    "No closing summary updates | date=%s",
                    current_time.date(),
                )
                return

            result = (
                await services.summaries
                .sync_decisions(
                    decisions,
                    commit_each=True,
                )
            )

            await session.commit()

            logger.info(
                "Closing summaries synced | "
                "date=%s total=%s sent=%s "
                "edited=%s recreated=%s "
                "unchanged=%s retry=%s "
                "failed=%s skipped=%s",
                current_time.date(),
                result.total_count,
                result.sent_count,
                result.edited_count,
                result.recreated_count,
                result.unchanged_count,
                result.retry_count,
                result.failed_count,
                result.skipped_count,
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "process_closing_summaries_job failed"
            )

            raise


async def recover_pending_summaries_job(
    *,
    bot: Bot,
) -> None:
    """
    Відновлює pending live summaries.

    Це особливо потрібно після:
    - перезапуску Railway;
    - короткого падіння Telegram API;
    - рестарту контейнера.
    """

    async with async_session_factory() as session:
        try:
            acquired = await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 403
                ),
            )

            if not acquired:
                logger.debug(
                    "recover_pending_summaries_job skipped: "
                    "scheduler lock already held"
                )
                return

            repositories = Repositories(
                session
            )

            services = create_services(
                repositories,
                bot=bot,
                bot_username=settings.bot_username,
            )

            current_time = now_local()

            result = (
                await services.summaries
                .process_pending_for_date(
                    business_date=current_time.date(),
                    limit=500,
                    commit_each=True,
                )
            )

            await session.commit()

            if result.total_count == 0:
                return

            logger.info(
                "Pending summaries recovered | "
                "date=%s total=%s sent=%s "
                "edited=%s recreated=%s "
                "unchanged=%s retry=%s "
                "failed=%s skipped=%s",
                current_time.date(),
                result.total_count,
                result.sent_count,
                result.edited_count,
                result.recreated_count,
                result.unchanged_count,
                result.retry_count,
                result.failed_count,
                result.skipped_count,
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "recover_pending_summaries_job failed"
            )

            raise


__all__ = [
    "process_opening_summaries_job",
    "process_closing_summaries_job",
    "recover_pending_summaries_job",
]