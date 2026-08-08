from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    Message,
    TelegramObject,
    Update,
)


logger = logging.getLogger(__name__)


HandlerType = Callable[
    [TelegramObject, dict[str, Any]],
    Awaitable[Any],
]


@dataclass(
    slots=True,
    frozen=True,
)
class UpdateLogContext:
    """
    Короткий контекст Telegram update.
    """

    event_type: str

    update_id: int | None

    telegram_user_id: int | None

    database_user_id: int | None

    username: str | None

    chat_id: int | None
    chat_type: str | None

    message_id: int | None

    command: str | None
    callback_data: str | None

    store_id: int | None
    bush_id: int | None

    @property
    def user_reference(self) -> str:
        """
        Людинозрозуміле посилання
        на користувача.
        """

        if self.database_user_id is not None:
            return (
                f"db_user={self.database_user_id}"
            )

        if self.telegram_user_id is not None:
            return (
                f"tg_user={self.telegram_user_id}"
            )

        return "user=unknown"


@dataclass(
    slots=True,
    frozen=True,
)
class UpdateExecutionResult:
    """
    Результат виконання update.
    """

    context: UpdateLogContext

    duration_ms: float

    success: bool

    exception_type: str | None


class LoggingMiddleware(
    BaseMiddleware
):
    """
    Middleware логування Telegram updates.

    Приклад логів:

        UPDATE START |
        event=Message |
        tg_user=123 |
        chat=123 |
        command=/start

        UPDATE OK |
        event=CallbackQuery |
        db_user=15 |
        callback=opening:confirm |
        duration=84.3ms

    Middleware не записує повний текст
    повідомлень користувача.

    Це важливо, тому що повідомлення
    можуть містити:

        - телефони;
        - ПІБ;
        - суми;
        - службову інформацію;
        - інші персональні дані.
    """

    DEFAULT_SLOW_THRESHOLD_MS = 1500.0

    MAX_CALLBACK_LENGTH = 150

    def __init__(
        self,
        *,
        log_started: bool = False,
        log_success: bool = True,
        slow_threshold_ms: float = (
            DEFAULT_SLOW_THRESHOLD_MS
        ),
    ) -> None:
        """
        log_started:
            логувати початок кожного update.

        log_success:
            логувати успішне завершення.

        slow_threshold_ms:
            після якого часу update
            позначається як SLOW.
        """

        if slow_threshold_ms < 0:
            raise ValueError(
                "slow_threshold_ms не може "
                "бути від’ємним."
            )

        self.log_started = log_started
        self.log_success = log_success

        self.slow_threshold_ms = (
            float(
                slow_threshold_ms
            )
        )

    # =====================================================
    # ENTRY
    # =====================================================

    async def __call__(
        self,
        handler: HandlerType,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        Вимірює час виконання handler.
        """

        started_at = (
            time.perf_counter()
        )

        context = self.build_context(
            event=event,
            data=data,
        )

        if self.log_started:
            logger.info(
                "UPDATE START | %s",
                self.format_context(
                    context
                ),
            )

        try:
            result = await handler(
                event,
                data,
            )

        except Exception as error:
            duration_ms = (
                self.elapsed_ms(
                    started_at
                )
            )

            self.log_failed(
                context=context,
                duration_ms=duration_ms,
                error=error,
            )

            # Помилку не ковтаємо.
            # Її повинен обробити
            # ErrorHandlerMiddleware.
            raise

        duration_ms = self.elapsed_ms(
            started_at
        )

        execution = UpdateExecutionResult(
            context=context,

            duration_ms=duration_ms,

            success=True,

            exception_type=None,
        )

        # Можна використати в handlers
        # або інших middleware.
        data[
            "update_execution"
        ] = execution

        data[
            "update_duration_ms"
        ] = duration_ms

        if (
            duration_ms
            >= self.slow_threshold_ms
        ):
            self.log_slow(
                context=context,
                duration_ms=duration_ms,
            )

        elif self.log_success:
            logger.info(
                (
                    "UPDATE OK | %s | "
                    "duration=%.1fms"
                ),
                self.format_context(
                    context
                ),
                duration_ms,
            )

        return result

    # =====================================================
    # CONTEXT
    # =====================================================

    def build_context(
        self,
        *,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> UpdateLogContext:
        """
        Формує лог-контекст.
        """

        telegram_user_id = (
            self.extract_telegram_user_id(
                event=event,
                data=data,
            )
        )

        database_user = (
            self.extract_database_user(
                data
            )
        )

        database_user_id = (
            self.safe_int(
                getattr(
                    database_user,
                    "id",
                    None,
                )
            )
        )

        username = (
            self.extract_username(
                event=event,
                data=data,
                database_user=(
                    database_user
                ),
            )
        )

        message = self.extract_message(
            event
        )

        callback = self.extract_callback(
            event
        )

        return UpdateLogContext(
            event_type=(
                self.event_type(
                    event
                )
            ),

            update_id=(
                self.extract_update_id(
                    event
                )
            ),

            telegram_user_id=(
                telegram_user_id
            ),

            database_user_id=(
                database_user_id
            ),

            username=username,

            chat_id=(
                self.extract_chat_id(
                    message=message,
                    callback=callback,
                )
            ),

            chat_type=(
                self.extract_chat_type(
                    message=message,
                    callback=callback,
                )
            ),

            message_id=(
                self.extract_message_id(
                    message=message,
                    callback=callback,
                )
            ),

            command=(
                self.extract_command(
                    message
                )
            ),

            callback_data=(
                self.extract_callback_data(
                    callback
                )
            ),

            store_id=(
                self.extract_store_id(
                    data=data,
                    database_user=(
                        database_user
                    ),
                )
            ),

            bush_id=(
                self.extract_bush_id(
                    data=data,
                    database_user=(
                        database_user
                    ),
                )
            ),
        )

    # =====================================================
    # DATABASE USER
    # =====================================================

    @staticmethod
    def extract_database_user(
        data: dict[str, Any],
    ) -> Any | None:
        """
        AuthMiddleware може класти User
        під різними ключами.

        Підтримуємо кілька варіантів.
        """

        for key in (
            "user",
            "current_user",
            "db_user",
            "authenticated_user",
        ):
            value = data.get(
                key
            )

            if value is None:
                continue

            # Не плутаємо aiogram User
            # з нашою SQLAlchemy моделлю.
            if hasattr(
                value,
                "role",
            ) or hasattr(
                value,
                "status",
            ):
                return value

        auth_context = data.get(
            "auth_context"
        )

        if auth_context is not None:
            for field_name in (
                "user",
                "db_user",
                "current_user",
            ):
                value = getattr(
                    auth_context,
                    field_name,
                    None,
                )

                if value is not None:
                    return value

        return None

    # =====================================================
    # STORE / BUSH
    # =====================================================

    @classmethod
    def extract_store_id(
        cls,
        *,
        data: dict[str, Any],
        database_user: Any | None,
    ) -> int | None:
        """
        Намагається визначити поточну ТТ.
        """

        for key in (
            "store_id",
            "current_store_id",
            "selected_store_id",
        ):
            value = cls.safe_int(
                data.get(
                    key
                )
            )

            if value is not None:
                return value

        store = data.get(
            "store"
        )

        if store is not None:
            value = cls.safe_int(
                getattr(
                    store,
                    "id",
                    None,
                )
            )

            if value is not None:
                return value

        if database_user is not None:
            for field_name in (
                "store_id",
                "primary_store_id",
            ):
                value = cls.safe_int(
                    getattr(
                        database_user,
                        field_name,
                        None,
                    )
                )

                if value is not None:
                    return value

        return None

    @classmethod
    def extract_bush_id(
        cls,
        *,
        data: dict[str, Any],
        database_user: Any | None,
    ) -> int | None:
        """
        Намагається визначити кущ.
        """

        for key in (
            "bush_id",
            "current_bush_id",
            "selected_bush_id",
        ):
            value = cls.safe_int(
                data.get(
                    key
                )
            )

            if value is not None:
                return value

        bush = data.get(
            "bush"
        )

        if bush is not None:
            value = cls.safe_int(
                getattr(
                    bush,
                    "id",
                    None,
                )
            )

            if value is not None:
                return value

        if database_user is not None:
            value = cls.safe_int(
                getattr(
                    database_user,
                    "bush_id",
                    None,
                )
            )

            if value is not None:
                return value

        return None

    # =====================================================
    # TELEGRAM USER
    # =====================================================

    @classmethod
    def extract_telegram_user_id(
        cls,
        *,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> int | None:
        """
        Telegram user_id.
        """

        event_from_user = data.get(
            "event_from_user"
        )

        if event_from_user is not None:
            value = cls.safe_int(
                getattr(
                    event_from_user,
                    "id",
                    None,
                )
            )

            if value is not None:
                return value

        if isinstance(
            event,
            Message,
        ):
            if event.from_user:
                return event.from_user.id

        if isinstance(
            event,
            CallbackQuery,
        ):
            return event.from_user.id

        if isinstance(
            event,
            Update,
        ):
            from_user = (
                cls.extract_update_user(
                    event
                )
            )

            if from_user is not None:
                return cls.safe_int(
                    getattr(
                        from_user,
                        "id",
                        None,
                    )
                )

        return None

    # =====================================================
    # USERNAME
    # =====================================================

    @classmethod
    def extract_username(
        cls,
        *,
        event: TelegramObject,
        data: dict[str, Any],
        database_user: Any | None,
    ) -> str | None:
        """
        Username без @.
        """

        if database_user is not None:
            for field_name in (
                "telegram_username",
                "username",
            ):
                value = getattr(
                    database_user,
                    field_name,
                    None,
                )

                normalized = (
                    cls.normalize_username(
                        value
                    )
                )

                if normalized:
                    return normalized

        event_from_user = data.get(
            "event_from_user"
        )

        if event_from_user is not None:
            normalized = (
                cls.normalize_username(
                    getattr(
                        event_from_user,
                        "username",
                        None,
                    )
                )
            )

            if normalized:
                return normalized

        if isinstance(
            event,
            Message,
        ):
            if event.from_user:
                return cls.normalize_username(
                    event.from_user.username
                )

        if isinstance(
            event,
            CallbackQuery,
        ):
            return cls.normalize_username(
                event.from_user.username
            )

        if isinstance(
            event,
            Update,
        ):
            from_user = (
                cls.extract_update_user(
                    event
                )
            )

            if from_user:
                return cls.normalize_username(
                    getattr(
                        from_user,
                        "username",
                        None,
                    )
                )

        return None

    # =====================================================
    # MESSAGE
    # =====================================================

    @staticmethod
    def extract_message(
        event: TelegramObject,
    ) -> Message | None:
        """
        Витягує Message.
        """

        if isinstance(
            event,
            Message,
        ):
            return event

        if isinstance(
            event,
            CallbackQuery,
        ):
            if isinstance(
                event.message,
                Message,
            ):
                return event.message

            return None

        if isinstance(
            event,
            Update,
        ):
            if event.message:
                return event.message

            if event.edited_message:
                return (
                    event.edited_message
                )

            if event.channel_post:
                return (
                    event.channel_post
                )

            if event.edited_channel_post:
                return (
                    event.edited_channel_post
                )

            if (
                event.callback_query
                and isinstance(
                    event.callback_query.message,
                    Message,
                )
            ):
                return (
                    event
                    .callback_query
                    .message
                )

        return None

    # =====================================================
    # CALLBACK
    # =====================================================

    @staticmethod
    def extract_callback(
        event: TelegramObject,
    ) -> CallbackQuery | None:
        """
        Витягує CallbackQuery.
        """

        if isinstance(
            event,
            CallbackQuery,
        ):
            return event

        if isinstance(
            event,
            Update,
        ):
            return (
                event.callback_query
            )

        return None

    # =====================================================
    # COMMAND
    # =====================================================

    @staticmethod
    def extract_command(
        message: Message | None,
    ) -> str | None:
        """
        Повертає лише Telegram-команду.

        Повний текст повідомлення
        навмисно не логуємо.
        """

        if message is None:
            return None

        text = (
            message.text
            or message.caption
        )

        if not text:
            return None

        stripped = text.strip()

        if not stripped.startswith("/"):
            return None

        command = (
            stripped.split(
                maxsplit=1
            )[0]
        )

        # /start@MyBot -> /start
        if "@" in command:
            command = command.split(
                "@",
                maxsplit=1,
            )[0]

        if len(command) > 100:
            command = command[:100]

        return command

    # =====================================================
    # CALLBACK DATA
    # =====================================================

    def extract_callback_data(
        self,
        callback: CallbackQuery | None,
    ) -> str | None:
        """
        Callback-data є технічною інформацією,
        тому її можна логувати.

        Але обмежуємо довжину.
        """

        if callback is None:
            return None

        value = callback.data

        if not value:
            return None

        value = str(
            value
        )

        if (
            len(value)
            > self.MAX_CALLBACK_LENGTH
        ):
            return (
                value[
                    : self.MAX_CALLBACK_LENGTH
                ]
                + "..."
            )

        return value

    # =====================================================
    # CHAT
    # =====================================================

    @staticmethod
    def extract_chat_id(
        *,
        message: Message | None,
        callback: CallbackQuery | None,
    ) -> int | None:
        """
        Chat ID.
        """

        if message is not None:
            return message.chat.id

        if (
            callback is not None
            and isinstance(
                callback.message,
                Message,
            )
        ):
            return (
                callback.message.chat.id
            )

        return None

    @staticmethod
    def extract_chat_type(
        *,
        message: Message | None,
        callback: CallbackQuery | None,
    ) -> str | None:
        """
        private/group/supergroup/channel
        """

        chat = None

        if message is not None:
            chat = message.chat

        elif (
            callback is not None
            and isinstance(
                callback.message,
                Message,
            )
        ):
            chat = (
                callback.message.chat
            )

        if chat is None:
            return None

        value = getattr(
            chat,
            "type",
            None,
        )

        if value is None:
            return None

        enum_value = getattr(
            value,
            "value",
            None,
        )

        if enum_value is not None:
            return str(
                enum_value
            )

        return str(
            value
        )

    # =====================================================
    # MESSAGE ID
    # =====================================================

    @staticmethod
    def extract_message_id(
        *,
        message: Message | None,
        callback: CallbackQuery | None,
    ) -> int | None:
        """
        Message ID.
        """

        if message is not None:
            return message.message_id

        if (
            callback is not None
            and isinstance(
                callback.message,
                Message,
            )
        ):
            return (
                callback.message
                .message_id
            )

        return None

    # =====================================================
    # UPDATE ID
    # =====================================================

    @staticmethod
    def extract_update_id(
        event: TelegramObject,
    ) -> int | None:
        """
        update_id доступний лише,
        якщо middleware отримав Update.
        """

        if isinstance(
            event,
            Update,
        ):
            return event.update_id

        return None

    # =====================================================
    # UPDATE USER
    # =====================================================

    @staticmethod
    def extract_update_user(
        update: Update,
    ) -> Any | None:
        """
        Витягує Telegram User
        з різних типів update.
        """

        if (
            update.message
            and update.message.from_user
        ):
            return (
                update.message.from_user
            )

        if update.callback_query:
            return (
                update.callback_query
                .from_user
            )

        if update.inline_query:
            return (
                update.inline_query
                .from_user
            )

        if update.chosen_inline_result:
            return (
                update.chosen_inline_result
                .from_user
            )

        if update.shipping_query:
            return (
                update.shipping_query
                .from_user
            )

        if update.pre_checkout_query:
            return (
                update.pre_checkout_query
                .from_user
            )

        if update.my_chat_member:
            return (
                update.my_chat_member
                .from_user
            )

        if update.chat_member:
            return (
                update.chat_member
                .from_user
            )

        if update.chat_join_request:
            return (
                update.chat_join_request
                .from_user
            )

        return None

    # =====================================================
    # EVENT TYPE
    # =====================================================

    @staticmethod
    def event_type(
        event: TelegramObject,
    ) -> str:
        """
        Зручна назва події.
        """

        if isinstance(
            event,
            Message,
        ):
            if event.photo:
                return "Message:photo"

            if event.document:
                return "Message:document"

            if event.text:
                return "Message:text"

            return "Message"

        if isinstance(
            event,
            CallbackQuery,
        ):
            return "CallbackQuery"

        if isinstance(
            event,
            Update,
        ):
            if event.message:
                return "Update:message"

            if event.callback_query:
                return (
                    "Update:callback_query"
                )

            if event.my_chat_member:
                return (
                    "Update:my_chat_member"
                )

            if event.chat_member:
                return (
                    "Update:chat_member"
                )

            return "Update"

        return type(
            event
        ).__name__

    # =====================================================
    # LOG SUCCESS
    # =====================================================

    def log_slow(
        self,
        *,
        context: UpdateLogContext,
        duration_ms: float,
    ) -> None:
        """
        Повільний update.
        """

        logger.warning(
            (
                "UPDATE SLOW | %s | "
                "duration=%.1fms | "
                "threshold=%.1fms"
            ),
            self.format_context(
                context
            ),
            duration_ms,
            self.slow_threshold_ms,
        )

    # =====================================================
    # LOG FAILURE
    # =====================================================

    def log_failed(
        self,
        *,
        context: UpdateLogContext,
        duration_ms: float,
        error: Exception,
    ) -> None:
        """
        Тут traceback не дублюємо.

        Повний traceback зробить
        ErrorHandlerMiddleware.
        """

        logger.error(
            (
                "UPDATE FAILED | %s | "
                "duration=%.1fms | "
                "exception=%s"
            ),
            self.format_context(
                context
            ),
            duration_ms,
            type(error).__name__,
        )

    # =====================================================
    # FORMAT CONTEXT
    # =====================================================

    @staticmethod
    def format_context(
        context: UpdateLogContext,
    ) -> str:
        """
        Перетворює dataclass у компактний лог.
        """

        parts = [
            (
                f"event="
                f"{context.event_type}"
            )
        ]

        if context.update_id is not None:
            parts.append(
                f"update_id="
                f"{context.update_id}"
            )

        if (
            context.database_user_id
            is not None
        ):
            parts.append(
                f"db_user="
                f"{context.database_user_id}"
            )

        if (
            context.telegram_user_id
            is not None
        ):
            parts.append(
                f"tg_user="
                f"{context.telegram_user_id}"
            )

        if context.username:
            parts.append(
                f"username="
                f"@{context.username}"
            )

        if context.chat_id is not None:
            parts.append(
                f"chat="
                f"{context.chat_id}"
            )

        if context.chat_type:
            parts.append(
                f"chat_type="
                f"{context.chat_type}"
            )

        if (
            context.message_id
            is not None
        ):
            parts.append(
                f"message_id="
                f"{context.message_id}"
            )

        if context.command:
            parts.append(
                f"command="
                f"{context.command}"
            )

        if context.callback_data:
            parts.append(
                f"callback="
                f"{context.callback_data}"
            )

        if context.store_id is not None:
            parts.append(
                f"store="
                f"{context.store_id}"
            )

        if context.bush_id is not None:
            parts.append(
                f"bush="
                f"{context.bush_id}"
            )

        return " | ".join(
            parts
        )

    # =====================================================
    # TIME
    # =====================================================

    @staticmethod
    def elapsed_ms(
        started_at: float,
    ) -> float:
        """
        perf_counter -> milliseconds.
        """

        return (
            time.perf_counter()
            - started_at
        ) * 1000.0

    # =====================================================
    # NORMALIZATION
    # =====================================================

    @staticmethod
    def normalize_username(
        value: Any,
    ) -> str | None:
        """
        Username без @.
        """

        if value is None:
            return None

        normalized = str(
            value
        ).strip().lstrip(
            "@"
        )

        if not normalized:
            return None

        if len(normalized) > 100:
            normalized = (
                normalized[:100]
            )

        return normalized

    @staticmethod
    def safe_int(
        value: Any,
    ) -> int | None:
        """
        Безпечний int.
        """

        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        try:
            return int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None


# Зручні aliases.

RequestLoggingMiddleware = (
    LoggingMiddleware
)

UpdateLoggingMiddleware = (
    LoggingMiddleware
)


__all__ = [
    "LoggingMiddleware",
    "RequestLoggingMiddleware",
    "UpdateLoggingMiddleware",
    "UpdateLogContext",
    "UpdateExecutionResult",
]