from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings


logger = logging.getLogger(__name__)


async def try_scheduler_lock(
    session: AsyncSession,
    *,
    lock_id: int | None = None,
) -> bool:
    """
    Намагається отримати PostgreSQL advisory lock
    на час поточної транзакції.

    Потрібно для Railway, щоб два інстанси бота
    не виконували scheduler job одночасно.

    Lock автоматично звільняється після
    commit або rollback.
    """

    if not settings.enable_scheduler_lock:
        return True

    resolved_lock_id = (
        lock_id
        if lock_id is not None
        else settings.scheduler_lock_id
    )

    result = await session.execute(
        text(
            """
            SELECT pg_try_advisory_xact_lock(
                :lock_id
            )
            """
        ),
        {
            "lock_id": resolved_lock_id,
        },
    )

    acquired = bool(
        result.scalar_one()
    )

    if not acquired:
        logger.debug(
            "Scheduler lock %s already held",
            resolved_lock_id,
        )

    return acquired


async def require_scheduler_lock(
    session: AsyncSession,
    *,
    lock_id: int | None = None,
) -> None:
    """
    Отримує scheduler lock або кидає RuntimeError.

    Використовуй тільки там, де пропуск job
    небажаний.
    """

    acquired = await try_scheduler_lock(
        session,
        lock_id=lock_id,
    )

    if acquired:
        return

    resolved_lock_id = (
        lock_id
        if lock_id is not None
        else settings.scheduler_lock_id
    )

    raise RuntimeError(
        "Scheduler lock is already held: "
        f"{resolved_lock_id}"
    )


__all__ = [
    "try_scheduler_lock",
    "require_scheduler_lock",
]