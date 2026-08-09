from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.config import settings
from app.database.session import async_session_factory
from app.repositories import Repositories
from app.scheduler.locks import try_scheduler_lock
from app.services import create_services


logger = logging.getLogger(__name__)


async def expire_invites_job() -> None:
    """
    Позначає прострочені invite як expired.

    InviteService вже містить окремий
    scheduler-friendly метод
    expire_outdated_invites().
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

            repositories = Repositories(
                session
            )

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
                    "Expired invites processed | "
                    "count=%s",
                    expired_count,
                )

        except Exception:
            await session.rollback()

            logger.exception(
                "expire_invites_job failed"
            )

            raise


async def cleanup_job() -> None:
    """
    Загальний lightweight cleanup.

    Сюди поступово можна додавати
    інші безпечні scheduler cleanup-задачі.
    """

    await expire_invites_job()


__all__ = [
    "expire_invites_job",
    "cleanup_job",
]