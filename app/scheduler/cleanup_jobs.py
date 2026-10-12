from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from app.config import settings
from app.database.models.closing_report import ClosingReport
from app.database.models.daily_summary import DailySummaryMessage
from app.database.models.notification import NotificationLog
from app.database.models.opening_checkin import OpeningCheckin
from app.database.session import async_session_factory
from app.repositories import Repositories
from app.scheduler.locks import try_scheduler_lock
from app.services import create_services


logger = logging.getLogger(__name__)

HISTORY_RETENTION_DAYS = 14


async def expire_invites_job() -> None:
    """
    ???????? ??????????? invite ?? expired.
    """

    async with async_session_factory() as session:
        try:
            acquired = await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 501
                ),
            )

            if not acquired:
                logger.debug(
                    "expire_invites_job skipped: "
                    "scheduler lock already held"
                )
                return

            repositories = Repositories(session)

            services = create_services(
                repositories,
                bot=None,
                bot_username=settings.bot_username,
            )

            expired_count = (
                await services.invites
                .expire_outdated_invites(
                    current_time=datetime.now(UTC),
                    limit=1000,
                )
            )

            await session.commit()

            if expired_count:
                logger.info(
                    "Expired invites processed | count=%s",
                    expired_count,
                )

        except Exception:
            await session.rollback()

            logger.exception(
                "expire_invites_job failed"
            )

            raise


async def cleanup_history_job() -> None:
    """
    ???????? ?????? ??????? 14 ???????????
    ???? ??????????? ???????.
    """

    async with async_session_factory() as session:
        try:
            acquired = await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 502
                ),
            )

            if not acquired:
                logger.debug(
                    "cleanup_history_job skipped: "
                    "scheduler lock already held"
                )
                return

            today = datetime.now(
                ZoneInfo(settings.timezone)
            ).date()

            cutoff_date = (
                today
                - timedelta(
                    days=HISTORY_RETENTION_DAYS - 1
                )
            )

            targets = (
                (
                    "notifications",
                    NotificationLog,
                ),
                (
                    "daily_summaries",
                    DailySummaryMessage,
                ),
                (
                    "opening_checkins",
                    OpeningCheckin,
                ),
                (
                    "closing_reports",
                    ClosingReport,
                ),
            )

            deleted: dict[str, int] = {}

            for name, model in targets:
                result = await session.execute(
                    delete(model).where(
                        model.business_date
                        < cutoff_date
                    )
                )

                deleted[name] = int(
                    result.rowcount or 0
                )

            await session.commit()

            total = sum(
                deleted.values()
            )

            if total:
                logger.info(
                    "History cleanup completed | "
                    "cutoff=%s retention_days=%s "
                    "deleted=%s total=%s",
                    cutoff_date,
                    HISTORY_RETENTION_DAYS,
                    deleted,
                    total,
                )

        except Exception:
            await session.rollback()

            logger.exception(
                "cleanup_history_job failed"
            )

            raise


async def cleanup_job() -> None:
    """
    ????????? scheduler cleanup.
    """

    await expire_invites_job()
    await cleanup_history_job()


__all__ = [
    "HISTORY_RETENTION_DAYS",
    "expire_invites_job",
    "cleanup_history_job",
    "cleanup_job",
]
