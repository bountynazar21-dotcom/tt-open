from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeAlias

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.repositories import Repositories
from app.services import Services


HandlerType: TypeAlias = Callable[
    [
        TelegramObject,
        dict[str, Any],
    ],
    Awaitable[Any],
]


@dataclass(slots=True, frozen=True)
class DatabaseMiddlewareContext:
    """
    Залежності одного Telegram update.
    """

    session: AsyncSession
    repositories: Repositories
    services: Services

    owns_session: bool


class DatabaseMiddleware(BaseMiddleware):
    """
    Middleware PostgreSQL-сесії.

    Для кожного Telegram update:

    1. Створює AsyncSession.
    2. Створює Repositories.
    3. Створює Services.
    4. Передає залежності в data.
    5. Викликає наступний middleware або handler.
    6. Робить commit після успішної обробки.
    7. Робить rollback при будь-якій помилці.
    8. Закриває сесію.

    У handler можна отримати:

        session: AsyncSession
        repositories: Repositories
        services: Services
        db_context: DatabaseMiddlewareContext
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[
            AsyncSession
        ],
        *,
        bot_username: str | None = None,
        auto_commit: bool = True,
        reuse_existing_session: bool = True,
    ) -> None:
        self.session_factory = session_factory

        self.bot_username = (
            self.normalize_bot_username(
                bot_username
            )
        )

        self.auto_commit = auto_commit

        self.reuse_existing_session = (
            reuse_existing_session
        )

    # ==========================================
    # ГОЛОВНИЙ ВИКЛИК
    # ==========================================

    async def __call__(
        self,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        Обробляє один Telegram update.
        """

        existing_session = (
            self.get_existing_session(data)
        )

        if (
            existing_session is not None
            and self.reuse_existing_session
        ):
            return await self.process_with_session(
                handler=handler,
                event=event,
                data=data,
                session=existing_session,
                owns_session=False,
            )

        async with self.session_factory() as session:
            return await self.process_with_session(
                handler=handler,
                event=event,
                data=data,
                session=session,
                owns_session=True,
            )

    # ==========================================
    # ОБРОБКА ІЗ СЕСІЄЮ
    # ==========================================

    async def process_with_session(
        self,
        *,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
        session: AsyncSession,
        owns_session: bool,
    ) -> Any:
        """
        Створює залежності та запускає handler.
        """

        repositories = Repositories(
            session
        )

        bot = self.resolve_bot(
            event=event,
            data=data,
        )

        services = Services(
            repositories,
            bot=bot,
            bot_username=(
                self.resolve_bot_username(
                    data
                )
            ),
        )

        context = DatabaseMiddlewareContext(
            session=session,
            repositories=repositories,
            services=services,
            owns_session=owns_session,
        )

        previous_values = (
            self.inject_dependencies(
                data=data,
                context=context,
            )
        )

        try:
            result = await handler(
                event,
                data,
            )

            if (
                owns_session
                and self.auto_commit
            ):
                await session.commit()

            return result

        except BaseException:
            if owns_session:
                await self.safe_rollback(
                    session
                )

            raise

        finally:
            self.restore_dependencies(
                data=data,
                previous_values=previous_values,
            )

    # ==========================================
    # ЗАЛЕЖНОСТІ HANDLER
    # ==========================================

    @staticmethod
    def inject_dependencies(
        *,
        data: dict[str, Any],
        context: DatabaseMiddlewareContext,
    ) -> dict[str, tuple[bool, Any]]:
        """
        Передає залежності в aiogram data.

        Повертає попередні значення, щоб після
        завершення update не залишити закриту сесію.
        """

        dependencies: dict[str, Any] = {
            "session": context.session,
            "db_session": context.session,
            "repositories": (
                context.repositories
            ),
            "services": context.services,
            "db_context": context,
        }

        previous_values: dict[
            str,
            tuple[bool, Any],
        ] = {}

        for key, value in dependencies.items():
            previous_values[key] = (
                key in data,
                data.get(key),
            )

            data[key] = value

        return previous_values

    @staticmethod
    def restore_dependencies(
        *,
        data: dict[str, Any],
        previous_values: dict[
            str,
            tuple[bool, Any],
        ],
    ) -> None:
        """
        Повертає aiogram data у попередній стан.
        """

        for key, (
            existed,
            previous_value,
        ) in previous_values.items():
            if existed:
                data[key] = previous_value
            else:
                data.pop(
                    key,
                    None,
                )

    # ==========================================
    # ІСНУЮЧА СЕСІЯ
    # ==========================================

    @staticmethod
    def get_existing_session(
        data: dict[str, Any],
    ) -> AsyncSession | None:
        """
        Перевіряє, чи сесія вже була створена
        зовнішнім middleware.
        """

        for key in (
            "session",
            "db_session",
        ):
            session = data.get(key)

            if isinstance(
                session,
                AsyncSession,
            ):
                return session

        return None

    # ==========================================
    # TELEGRAM BOT
    # ==========================================

    @staticmethod
    def resolve_bot(
        *,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Bot | None:
        """
        Визначає поточний об’єкт Telegram Bot.
        """

        bot = data.get("bot")

        if isinstance(bot, Bot):
            return bot

        event_bot = getattr(
            event,
            "bot",
            None,
        )

        if isinstance(event_bot, Bot):
            return event_bot

        return None

    def resolve_bot_username(
        self,
        data: dict[str, Any],
    ) -> str | None:
        """
        Визначає username Telegram-бота.

        Пріоритет:

        1. Значення з конструктора middleware.
        2. Значення з aiogram data.
        """

        if self.bot_username:
            return self.bot_username

        for key in (
            "bot_username",
            "telegram_bot_username",
        ):
            value = data.get(key)

            normalized = (
                self.normalize_bot_username(
                    value
                )
            )

            if normalized:
                return normalized

        return None

    # ==========================================
    # ТРАНЗАКЦІЯ
    # ==========================================

    @staticmethod
    async def safe_rollback(
        session: AsyncSession,
    ) -> None:
        """
        Безпечно відкочує транзакцію.

        Початкова помилка handler не буде
        замінена помилкою rollback.
        """

        try:
            await session.rollback()

        except Exception:
            pass

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def normalize_bot_username(
        value: Any,
    ) -> str | None:
        """
        Нормалізує username Telegram-бота.
        """

        if value is None:
            return None

        normalized_value = (
            str(value)
            .strip()
            .lstrip("@")
        )

        return normalized_value or None


DatabaseSessionMiddleware = (
    DatabaseMiddleware
)


__all__ = [
    "DatabaseMiddleware",
    "DatabaseSessionMiddleware",
    "DatabaseMiddlewareContext",
]