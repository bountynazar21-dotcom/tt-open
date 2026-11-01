from __future__ import annotations

import logging
from datetime import UTC, datetime

from aiogram import Bot

from app.config import settings
from app.database.session import async_session_factory
from app.repositories import Repositories
from app.scheduler.locks import scheduler_lock_guard
from app.services import create_services

logger = logging.getLogger(__name__)


async def process_notifications_job(
    *,
    bot: Bot,
) -> None:
    """
    Відправляє всі notification, які вже готові до доставки.

    Для цієї job lock утримується на окремому connection,
    тому commit кожного повідомлення не відкриває шлях
    другому Railway-інстансу до тієї ж черги.
    """

    async with scheduler_lock_guard(
        lock_id=settings.scheduler_lock_id + 301,
    ) as acquired:
        if not acquired:
            logger.debug(
                "process_notifications_job skipped: "
                "scheduler lock already held"
            )
            return

        async with async_session_factory() as session:
            try:
                repositories = Repositories(session)

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

                # Кожне повідомлення commit-иться в сервісі,
                # цей commit завершує лише залишкову транзакцію.
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