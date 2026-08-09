from __future__ import annotations

import logging
from datetime import UTC, datetime

from aiogram import Bot

from app.config import settings
from app.database.session import async_session_factory
from app.repositories import Repositories
from app.scheduler.locks import try_scheduler_lock
from app.services import create_services


logger = logging.getLogger(__name__)


async def process_notifications_job(
    *,
    bot: Bot,
) -> None:
    """
    Відправляє всі notification,
    які вже готові до доставки.

    NotificationService сам:
    - вибирає pending повідомлення;
    - відправляє їх через Telegram;
    - позначає sent;
    - планує retry;
    - фіксує failed/skipped.
    """

    async with async_session_factory() as session:
        try:
            acquired = await try_scheduler_lock(
                session,
                lock_id=(
                    settings.scheduler_lock_id
                    + 301
                ),
            )

            if not acquired:
                logger.debug(
                    "process_notifications_job skipped: "
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

            result = (
                await services.notifications
                .process_due_notifications(
                    current_time=datetime.now(UTC),
                    limit=100,
                    commit_each=True,
                )
            )

            # process_due_notifications(commit_each=True)
            # сам commit-ить кожне повідомлення,
            # але фінальний commit залишаємо
            # для безпечного завершення транзакції.
            await session.commit()

            logger.info(
                "Notifications processed | "
                "selected=%s processed=%s "
                "sent=%s retry=%s "
                "failed=%s skipped=%s",
                result.selected_count,
                result.processed_count,
                result.sent_count,
                result.retry_count,
                result.failed_count,
                result.skipped_count,
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "process_notifications_job failed"
            )

            raise


__all__ = [
    "process_notifications_job",
]