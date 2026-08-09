from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.config import settings
from app.database.session import async_session_factory
from app.repositories import Repositories
from app.services import create_services
from app.scheduler.locks import try_scheduler_lock


logger = logging.getLogger(__name__)


def now_local() -> datetime:
    """
    Поточний час у часовій зоні проєкту.
    """

    return datetime.now(
        ZoneInfo(settings.timezone)
    )


async def prepare_opening_records_job(
    *,
    bot: Bot | None = None,
) -> None:
    """
    Створює записи відкриття для ТТ,
    які повинні працювати сьогодні.

    Job безпечний для повторного запуску:
    OpeningService створює лише відсутні записи.
    """

    async with async_session_factory() as session:
        try:
            if not await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 101
                ),
            ):
                logger.debug(
                    "prepare_opening_records_job skipped: "
                    "lock already held"
                )
                return

            repositories = Repositories(session)

            services = create_services(
                repositories,
                bot=bot,
                bot_username=settings.bot_username,
            )

            current_time = now_local()

            result = (
                await services.opening
                .prepare_daily_records(
                    business_date=current_time.date(),
                )
            )

            await session.commit()

            logger.info(
                "Opening records prepared | "
                "date=%s result=%s",
                current_time.date(),
                result,
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "prepare_opening_records_job failed"
            )

            raise


async def process_opening_deadlines_job(
    *,
    bot: Bot | None = None,
) -> None:
    """
    Перевіряє дедлайни відкриття.

    OpeningService:
    - знаходить ТТ, які не відмітили відкриття;
    - фіксує пропущений дедлайн;
    - створює notification queue;
    - готує оновлення live summary.
    """

    async with async_session_factory() as session:
        try:
            if not await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 102
                ),
            ):
                logger.debug(
                    "process_opening_deadlines_job skipped: "
                    "lock already held"
                )
                return

            repositories = Repositories(session)

            services = create_services(
                repositories,
                bot=bot,
                bot_username=settings.bot_username,
            )

            current_time = now_local()

            result = (
                await services.opening
                .process_due_deadlines(
                    current_time=current_time,
                    timezone_name=settings.timezone,
                    create_notifications=True,
                    update_summaries=True,
                )
            )

            await session.commit()

            logger.info(
                "Opening deadlines processed | "
                "date=%s missed=%s",
                current_time.date(),
                len(result.missed_checkins),
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "process_opening_deadlines_job failed"
            )

            raise


async def refresh_opening_summaries_job(
    *,
    bot: Bot | None = None,
) -> None:
    """
    Готує актуальні ранкові live summaries
    для всіх активних кущів та мережі.
    """

    async with async_session_factory() as session:
        try:
            if not await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 103
                ),
            ):
                logger.debug(
                    "refresh_opening_summaries_job skipped: "
                    "lock already held"
                )
                return

            repositories = Repositories(session)

            services = create_services(
                repositories,
                bot=bot,
                bot_username=settings.bot_username,
            )

            current_time = now_local()

            updates = (
                await services.opening
                .prepare_all_opening_summaries(
                    business_date=current_time.date(),
                    timezone_name=settings.timezone,
                )
            )

            await session.commit()

            logger.info(
                "Opening summaries prepared | "
                "date=%s updates=%s",
                current_time.date(),
                len(updates),
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "refresh_opening_summaries_job failed"
            )

            raise


__all__ = [
    "prepare_opening_records_job",
    "process_opening_deadlines_job",
    "refresh_opening_summaries_job",
]