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
    Поточний timezone-aware час проєкту.
    """

    return datetime.now(
        ZoneInfo(settings.timezone)
    )


async def prepare_closing_records_job(
    *,
    bot: Bot | None = None,
) -> None:
    """
    Створює вечірні записи для всіх ТТ,
    які повинні закриватися сьогодні.

    Існуючі записи ClosingService
    повторно не створює.
    """

    async with async_session_factory() as session:
        try:
            acquired = await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 201
                ),
            )

            if not acquired:
                logger.debug(
                    "prepare_closing_records_job skipped: "
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
                await services.closing
                .prepare_daily_records(
                    business_date=(
                        current_time.date()
                    ),
                )
            )

            await session.commit()

            logger.info(
                "Closing records prepared | "
                "date=%s result=%s",
                current_time.date(),
                result,
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "prepare_closing_records_job failed"
            )

            raise


async def process_closing_deadlines_job(
    *,
    bot: Bot | None = None,
) -> None:
    """
    Обробляє прострочені дедлайни закриття.

    ClosingService сам:
    - створює відсутні closing records;
    - знаходить ТТ без вечірнього звіту;
    - позначає deadline як missed;
    - створює notification records;
    - формує оновлення summary.
    """

    async with async_session_factory() as session:
        try:
            acquired = await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 202
                ),
            )

            if not acquired:
                logger.debug(
                    "process_closing_deadlines_job skipped: "
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
                await services.closing
                .process_due_deadlines(
                    current_time=current_time,
                    timezone_name=settings.timezone,
                    create_notifications=True,
                    update_summaries=True,
                )
            )

            await session.commit()

            logger.info(
                "Closing deadlines processed | "
                "date=%s missed=%s "
                "created_notifications=%s",
                result.business_date,
                len(result.missed_reports),
                result.created_notifications,
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "process_closing_deadlines_job failed"
            )

            raise


async def refresh_closing_summaries_job(
    *,
    bot: Bot | None = None,
) -> None:
    """
    Перераховує вечірні live summaries
    усіх активних кущів та мережі.
    """

    async with async_session_factory() as session:
        try:
            acquired = await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 203
                ),
            )

            if not acquired:
                logger.debug(
                    "refresh_closing_summaries_job skipped: "
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

            updates = (
                await services.closing
                .prepare_all_closing_summaries(
                    business_date=(
                        current_time.date()
                    ),
                    timezone_name=settings.timezone,
                )
            )

            await session.commit()

            logger.info(
                "Closing summaries prepared | "
                "date=%s updates=%s",
                current_time.date(),
                len(updates),
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "refresh_closing_summaries_job failed"
            )

            raise


__all__ = [
    "prepare_closing_records_job",
    "process_closing_deadlines_job",
    "refresh_closing_summaries_job",
]