from __future__ import annotations

import contextvars
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.repositories import Repositories
from app.services import Services


perf_logger = logging.getLogger(
    "app.performance"
)


@dataclass(slots=True)
class _PerfTraceState:
    action: str
    started_at: float

    db_queries: int = 0
    db_total_ms: float = 0.0
    db_slowest_ms: float = 0.0
    db_slowest_sql: str = ""

    db_repeats: dict[str, int] = field(
        default_factory=dict
    )

    telegram_calls: int = 0
    telegram_total_ms: float = 0.0
    telegram_slowest_ms: float = 0.0
    telegram_slowest_method: str = ""


_perf_current: contextvars.ContextVar[
    _PerfTraceState | None
] = contextvars.ContextVar(
    "telegram_update_perf_trace",
    default=None,
)

_perf_sql_binds: set[int] = set()
_perf_telegram_sessions: set[int] = set()


def _perf_begin(
    action: str,
):
    return _perf_current.set(
        _PerfTraceState(
            action=action,
            started_at=time.perf_counter(),
        )
    )


def _perf_end(
    token,
) -> _PerfTraceState | None:
    state = _perf_current.get()

    _perf_current.reset(
        token
    )

    return state


def _perf_clean_sql(
    statement: Any,
) -> str:
    sql = " ".join(
        str(
            statement or ""
        ).split()
    )

    # ?? ??????? literal string values.
    sql = re.sub(
        r"'(?:''|[^'])*'",
        "'?'",
        sql,
    )

    sql = sql.replace(
        "|",
        "?",
    )

    if len(sql) > 260:
        sql = (
            sql[:257]
            + "..."
        )

    return sql


def _perf_before_cursor_execute(
    conn,
    cursor,
    statement,
    parameters,
    context,
    executemany,
) -> None:
    if _perf_current.get() is None:
        return

    context._perf_started_at = (
        time.perf_counter()
    )


def _perf_after_cursor_execute(
    conn,
    cursor,
    statement,
    parameters,
    context,
    executemany,
) -> None:
    state = _perf_current.get()

    started_at = getattr(
        context,
        "_perf_started_at",
        None,
    )

    if (
        state is None
        or started_at is None
    ):
        return

    elapsed_ms = (
        time.perf_counter()
        - started_at
    ) * 1000.0

    sql = _perf_clean_sql(
        statement
    )

    state.db_queries += 1
    state.db_total_ms += elapsed_ms

    state.db_repeats[sql] = (
        state.db_repeats.get(
            sql,
            0,
        )
        + 1
    )

    if (
        elapsed_ms
        > state.db_slowest_ms
    ):
        state.db_slowest_ms = (
            elapsed_ms
        )
        state.db_slowest_sql = sql


def _perf_install_sql(
    session: AsyncSession,
) -> None:
    try:
        bind = (
            session
            .sync_session
            .get_bind()
        )

        if bind is None:
            return

        key = id(
            bind
        )

        if key in _perf_sql_binds:
            return

        sqlalchemy_event.listen(
            bind,
            "before_cursor_execute",
            _perf_before_cursor_execute,
        )

        sqlalchemy_event.listen(
            bind,
            "after_cursor_execute",
            _perf_after_cursor_execute,
        )

        _perf_sql_binds.add(
            key
        )

    except Exception:
        perf_logger.exception(
            "PERF TRACE SQL INSTALL FAILED"
        )


class _TelegramPerfMiddleware:
    async def __call__(
        self,
        make_request,
        bot,
        method,
    ):
        state = (
            _perf_current.get()
        )

        if state is None:
            return await make_request(
                bot,
                method,
            )

        started_at = (
            time.perf_counter()
        )

        try:
            return await make_request(
                bot,
                method,
            )

        finally:
            elapsed_ms = (
                time.perf_counter()
                - started_at
            ) * 1000.0

            current = (
                _perf_current.get()
            )

            if current is not None:
                method_name = (
                    type(method).__name__
                )

                current.telegram_calls += 1
                current.telegram_total_ms += (
                    elapsed_ms
                )

                if (
                    elapsed_ms
                    > current.telegram_slowest_ms
                ):
                    current.telegram_slowest_ms = (
                        elapsed_ms
                    )

                    current.telegram_slowest_method = (
                        method_name
                    )


def _perf_install_telegram(
    bot: Bot,
) -> None:
    try:
        session = bot.session

        key = id(
            session
        )

        if key in _perf_telegram_sessions:
            return

        session.middleware(
            _TelegramPerfMiddleware()
        )

        _perf_telegram_sessions.add(
            key
        )

    except Exception:
        perf_logger.exception(
            "PERF TRACE TELEGRAM INSTALL FAILED"
        )


def _perf_action(
    event: TelegramObject,
) -> str:
    try:
        callback = getattr(
            event,
            "callback_query",
            None,
        )

        if (
            callback is None
            and hasattr(
                event,
                "data",
            )
        ):
            callback = event

        if callback is not None:
            callback_data = getattr(
                callback,
                "data",
                None,
            )

            if callback_data:
                return (
                    "callback:"
                    + str(
                        callback_data
                    )[:140]
                )

        message = getattr(
            event,
            "message",
            None,
        )

        if (
            message is None
            and hasattr(
                event,
                "text",
            )
        ):
            message = event

        if message is not None:
            message_text = (
                getattr(
                    message,
                    "text",
                    None,
                )
                or getattr(
                    message,
                    "caption",
                    None,
                )
            )

            if (
                isinstance(
                    message_text,
                    str,
                )
                and message_text.startswith(
                    "/"
                )
            ):
                command = (
                    message_text
                    .split(
                        maxsplit=1
                    )[0]
                    .split(
                        "@",
                        1,
                    )[0]
                )

                return (
                    "command:"
                    + command[:100]
                )

            if getattr(
                message,
                "photo",
                None,
            ):
                return "message:photo"

            if getattr(
                message,
                "document",
                None,
            ):
                return "message:document"

            return "message"

    except Exception:
        pass

    return type(
        event
    ).__name__


def _perf_emit(
    state: _PerfTraceState | None,
    *,
    success: bool,
    commit_ms: float,
) -> None:
    if state is None:
        return

    try:
        total_ms = (
            time.perf_counter()
            - state.started_at
        ) * 1000.0

        other_ms = max(
            total_ms
            - state.db_total_ms
            - state.telegram_total_ms,
            0.0,
        )

        threshold_ms = float(
            os.getenv(
                "PERF_TRACE_THRESHOLD_MS",
                "500",
            )
        )

        if (
            total_ms
            < threshold_ms
            and state.db_queries < 10
        ):
            return

        repeat_sql = "-"
        repeat_count = 0

        if state.db_repeats:
            (
                repeat_sql,
                repeat_count,
            ) = max(
                state.db_repeats.items(),
                key=lambda item: item[1],
            )

        perf_logger.warning(
            (
                "PERF TRACE | "
                "action=%s | "
                "total=%.1fms | "
                "db=%.1fms | "
                "db_q=%d | "
                "tg=%.1fms | "
                "tg_calls=%d | "
                "other=%.1fms | "
                "commit=%.1fms | "
                "slow_db=%.1fms | "
                "slow_sql=%s | "
                "repeat_q=%d | "
                "repeat_sql=%s | "
                "slow_tg=%.1fms | "
                "slow_tg_method=%s | "
                "success=%d"
            ),
            state.action,
            total_ms,
            state.db_total_ms,
            state.db_queries,
            state.telegram_total_ms,
            state.telegram_calls,
            other_ms,
            commit_ms,
            state.db_slowest_ms,
            (
                state.db_slowest_sql
                or "-"
            ),
            repeat_count,
            repeat_sql,
            state.telegram_slowest_ms,
            (
                state.telegram_slowest_method
                or "-"
            ),
            1 if success else 0,
        )

    except Exception:
        perf_logger.exception(
            "PERF TRACE EMIT FAILED"
        )


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

        _perf_install_sql(
            session
        )

        perf_token = _perf_begin(
            _perf_action(
                event
            )
        )

        perf_success = False
        commit_ms = 0.0

        repositories = Repositories(
            session
        )

        bot = self.resolve_bot(
            event=event,
            data=data,
        )

        if bot is not None:
            _perf_install_telegram(
                bot
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
                commit_started_at = (
                    time.perf_counter()
                )

                await session.commit()

                commit_ms = (
                    time.perf_counter()
                    - commit_started_at
                ) * 1000.0

            perf_success = True

            return result

        except BaseException:
            if owns_session:
                await self.safe_rollback(
                    session
                )

            raise

        finally:
            perf_state = _perf_end(
                perf_token
            )

            self.restore_dependencies(
                data=data,
                previous_values=previous_values,
            )

            _perf_emit(
                perf_state,
                success=perf_success,
                commit_ms=commit_ms,
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