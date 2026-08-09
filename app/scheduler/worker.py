from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from app.bot import get_bot_and_dispatcher, shutdown_bot
from app.scheduler import (
    shutdown_scheduler,
    start_scheduler,
)


logger = logging.getLogger(__name__)


async def run_worker() -> None:
    """
    Окремий scheduler worker.

    Може використовуватись, якщо в майбутньому
    захочемо винести scheduler в окремий Railway service.

    Зараз основний застосунок запускає scheduler
    через app.main, тому цей worker окремо
    запускати не потрібно.
    """

    bot, _ = get_bot_and_dispatcher()

    scheduler = start_scheduler(
        bot=bot,
    )

    logger.info(
        "Scheduler worker started | jobs=%s",
        len(scheduler.get_jobs()),
    )

    try:
        # Тримаємо worker живим,
        # поки процес не буде зупинений.
        while True:
            await asyncio.sleep(3600)

    except asyncio.CancelledError:
        logger.info(
            "Scheduler worker cancelled"
        )

        raise

    finally:
        logger.info(
            "Stopping scheduler worker..."
        )

        with suppress(Exception):
            shutdown_scheduler()

        with suppress(Exception):
            await shutdown_bot()

        logger.info(
            "Scheduler worker stopped"
        )


def main() -> None:
    """
    Ручний запуск:

        python -m app.scheduler.worker
    """

    try:
        asyncio.run(
            run_worker()
        )

    except KeyboardInterrupt:
        logger.info(
            "Scheduler worker interrupted"
        )


if __name__ == "__main__":
    main()