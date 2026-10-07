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


async def _sync_closing_summaries_in_order(
    *,
    services,
    business_date,
):
    """
    Спочатку всі кущі.
    Потім загальний результат мережі.
    """

    bush_decisions = (
        await services.closing
        .prepare_all_closing_summaries(
            business_date=(
                business_date
            ),
            timezone_name=(
                settings.timezone
            ),
            include_network=False,
            force=True,
        )
    )

    bush_result = None

    if bush_decisions:
        bush_result = (
            await services.summaries
            .sync_decisions(
                bush_decisions,
                commit_each=True,
            )
        )

    network_decisions = (
        await services.closing
        .prepare_summary_updates(
            business_date=(
                business_date
            ),
            bush_ids=set(),
            timezone_name=(
                settings.timezone
            ),
            include_network=True,
            include_diagnostics=True,
            force=True,
        )
    )

    network_result = None

    if network_decisions:
        network_result = (
            await services.summaries
            .sync_decisions(
                network_decisions,
                commit_each=True,
            )
        )

    return (
        bush_result,
        network_result,
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
    """Lightweight live closing summary."""

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
                return

            repositories = Repositories(session)

            services = create_services(
                repositories,
                bot=bot,
                bot_username=settings.bot_username,
            )

            current_time = now_local()

            # Live mode:
            # network only, no all-bush recount,
            # no bush diagnostics.
            decisions = (
                await services.closing
                .prepare_summary_updates(
                    business_date=current_time.date(),
                    bush_ids=set(),
                    timezone_name=settings.timezone,
                    include_network=True,
                    include_diagnostics=False,
                )
            )

            if not decisions:
                await session.commit()
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
                "Closing lightweight live summary | "
                "date=%s total=%s failed=%s",
                current_time.date(),
                result.total_count,
                result.failed_count,
            )

        except Exception:
            await session.rollback()
            logger.exception(
                "process_closing_summaries_job failed"
            )
            raise


async def final_closing_recount_job(
    *,
    bot: Bot,
) -> None:
    """
    Контрольний перерахунок о 22:22.

    Фінальний контрольний перерахунок:
    - обробляємо дедлайни;
    - перераховуємо всі кущі по фактично зданих ТТ;
    - після цього завжди перераховуємо мережу.
    """

    async with async_session_factory() as session:
        try:
            acquired = (
                await try_scheduler_lock(
                    session,
                    lock_id=(
                        settings.scheduler_lock_id
                        + 404
                    ),
                )
            )

            if not acquired:
                logger.info(
                    "final_closing_recount_job "
                    "skipped: closing sync "
                    "already running"
                )
                return

            repositories = Repositories(
                session
            )

            services = create_services(
                repositories,
                bot=bot,
                bot_username=(
                    settings.bot_username
                ),
            )

            current_time = now_local()

            business_date = (
                current_time.date()
            )

            await (
                services.closing
                .prepare_daily_records(
                    business_date=(
                        business_date
                    )
                )
            )

            await (
                services.closing
                .process_due_deadlines(
                    current_time=(
                        current_time
                    ),
                    timezone_name=(
                        settings.timezone
                    ),
                    create_notifications=True,
                    update_summaries=False,
                )
            )

            stats = (
                await repositories
                .closings
                .get_daily_statistics(
                    business_date=(
                        business_date
                    )
                )
            )

            expected = int(
                stats[
                    "expected_count"
                ]
            )

            submitted = int(
                stats[
                    "submitted_count"
                ]
            )

            missing = max(
                expected - submitted,
                0,
            )

            (
                bush_result,
                network_result,
            ) = (
                await
                _sync_closing_summaries_in_order(
                    services=services,
                    business_date=(
                        business_date
                    ),
                )
            )

            await session.commit()

            logger.warning(
                "22:22 recount completed | "
                "date=%s expected=%s "
                "submitted=%s missing=%s "
                "bushes=%s "
                "bush_failed=%s "
                "network=%s "
                "network_failed=%s",
                business_date,
                expected,
                submitted,
                missing,
                (
                    bush_result.total_count
                    if bush_result
                    else 0
                ),
                (
                    bush_result.failed_count
                    if bush_result
                    else 0
                ),
                (
                    network_result.total_count
                    if network_result
                    else 0
                ),
                (
                    network_result.failed_count
                    if network_result
                    else 0
                ),
            )

        except Exception:
            await session.rollback()

            logger.exception(
                "final_closing_recount_job failed"
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
    "final_closing_recount_job",
    "recover_pending_summaries_job",
]
