from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.logging_config import get_logger


logger = get_logger(__name__)


engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_pre_ping=True,
)


async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Створює окрему сесію PostgreSQL.

    Використовуватимемо її:
    - у middleware Telegram-бота;
    - у FastAPI;
    - у сервісах;
    - у тестах.
    """

    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()

            logger.exception(
                "Помилка під час роботи із сесією бази даних"
            )

            raise
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """
    Перевіряє з'єднання з PostgreSQL.

    Повертає True, якщо база відповідає.
    """

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        logger.info(
            "З'єднання з PostgreSQL встановлено"
        )

        return True

    except Exception:
        logger.exception(
            "Не вдалося підключитися до PostgreSQL"
        )

        return False


async def close_database_connection() -> None:
    """
    Закриває пул з'єднань із PostgreSQL.

    Викликатиметься при завершенні роботи застосунку.
    """

    await engine.dispose()

    logger.info(
        "Пул з'єднань PostgreSQL закрито"
    )