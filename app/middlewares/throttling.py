from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
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


class ThrottleEventType(StrEnum):
    """
    Тип дії для throttling.
    """

    MESSAGE = "message"
    COMMAND = "command"
    CALLBACK = "callback"
    OTHER = "other"


@dataclass(
    slots=True,
    frozen=True,
)
class ThrottleRule:
    """
    Правило throttling.
    """

    name: str

    interval_seconds: float

    event_type: ThrottleEventType

    action: str


@dataclass(
    slots=True,
    frozen=True,
)
class ThrottleDecision:
    """
    Результат перевірки.
    """

    allowed: bool

    key: str

    event_type: ThrottleEventType

    action: str

    interval_seconds: float

    retry_after_seconds: float

    @property
    def throttled(self) -> bool:
        return not self.allowed


class ThrottlingMiddleware(
    BaseMiddleware
):
    """
    Антиспам middleware.

    Захищає від:

    - подвійного натискання callback;
    - швидкого повторного /start;
    - повторного підтвердження відкриття;
    - повторного підтвердження закриття;
    - подвійної відправки каси;
    - подвійного імпорту;
    - випадкових багаторазових кліків.

    Важливі операції отримують
    довший cooldown.

    Наприклад:

        opening:*     -> 2 секунди
        closing:*     -> 2 секунди
        cash:*        -> 2 секунди
        import:*      -> 3 секунди

    Звичайні callback:
        ~0.7 секунди

    Звичайні повідомлення:
        ~0.35 секунди

    Це лише перший рівень захисту.

    Критичні операції також повинні
    мати перевірки на рівні БД/сервісів.
    """

    DEFAULT_MESSAGE_INTERVAL = 0.35

    DEFAULT_COMMAND_INTERVAL = 0.80

    DEFAULT_CALLBACK_INTERVAL = 0.70

    DEFAULT_CRITICAL_CALLBACK_INTERVAL = 2.0

    DEFAULT_IMPORT_CALLBACK_INTERVAL = 3.0

    DEFAULT_CLEANUP_INTERVAL = 300.0

    DEFAULT_ENTRY_TTL = 900.0

    DEFAULT_MAX_ENTRIES = 20_000

    MAX_ACTION_LENGTH = 200

    CRITICAL_CALLBACK_PREFIXES = (
        "opening:",
        "open:",
        "checkin:",

        "closing:",
        "close:",

        "cash:",

        "binding:",
        "store:deactivate",
        "store:reactivate",

        "user:approve",
        "user:reject",
        "user:block",
        "user:unblock",

        "schedule:",
        "cluster:",
        "bush:",
    )

    IMPORT_CALLBACK_PREFIXES = (
        "import:",
        "excel:import",
        "stores:import",
    )

    def __init__(
        self,
        *,
        message_interval: float = (
            DEFAULT_MESSAGE_INTERVAL
        ),
        command_interval: float = (
            DEFAULT_COMMAND_INTERVAL
        ),
        callback_interval: float = (
            DEFAULT_CALLBACK_INTERVAL
        ),
        critical_callback_interval: float = (
            DEFAULT_CRITICAL_CALLBACK_INTERVAL
        ),
        import_callback_interval: float = (
            DEFAULT_IMPORT_CALLBACK_INTERVAL
        ),
        notify_messages: bool = False,
        cleanup_interval: float = (
            DEFAULT_CLEANUP_INTERVAL
        ),
        entry_ttl: float = (
            DEFAULT_ENTRY_TTL
        ),
        max_entries: int = (
            DEFAULT_MAX_ENTRIES
        ),
    ) -> None:
        self.validate_interval(
            message_interval,
            "message_interval",
        )

        self.validate_interval(
            command_interval,
            "command_interval",
        )

        self.validate_interval(
            callback_interval,
            "callback_interval",
        )

        self.validate_interval(
            critical_callback_interval,
            "critical_callback_interval",
        )

        self.validate_interval(
            import_callback_interval,
            "import_callback_interval",
        )

        if cleanup_interval <= 0:
            raise ValueError(
                "cleanup_interval повинен "
                "бути більшим за 0."
            )

        if entry_ttl <= 0:
            raise ValueError(
                "entry_ttl повинен "
                "бути більшим за 0."
            )

        if max_entries < 100:
            raise ValueError(
                "max_entries повинен бути "
                "не меншим за 100."
            )

        self.message_interval = float(
            message_interval
        )

        self.command_interval = float(
            command_interval
        )

        self.callback_interval = float(
            callback_interval
        )

        self.critical_callback_interval = (
            float(
                critical_callback_interval
            )
        )

        self.import_callback_interval = (
            float(
                import_callback_interval
            )
        )

        self.notify_messages = (
            notify_messages
        )

        self.cleanup_interval = float(
            cleanup_interval
        )

        self.entry_ttl = float(
            entry_ttl
        )

        self.max_entries = int(
            max_entries
        )

        # key -> monotonic timestamp
        self._hits: dict[
            str,
            float,
        ] = {}

        # Окремий cooldown повідомлень
        # "не так швидко".
        self._notices: dict[
            str,
            float,
        ] = {}

        self._last_cleanup = (
            time.monotonic()
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
        Перевіряє cooldown перед handler.
        """

        if self.should_bypass(
            data
        ):
            return await handler(
                event,
                data,
            )

        now = time.monotonic()

        self.cleanup_if_needed(
            now
        )

        decision = self.make_decision(
            event=event,
            data=data,
            now=now,
        )

        data[
            "throttle_decision"
        ] = decision

        if decision.allowed:
            return await handler(
                event,
                data,
            )

        await self.handle_throttled(
            event=event,
            decision=decision,
            now=now,
        )

        logger.debug(
            (
                "THROTTLED | "
                "key=%s | "
                "action=%s | "
                "retry_after=%.3fs"
            ),
            decision.key,
            decision.action,
            decision.retry_after_seconds,
        )

        return None

    # =====================================================
    # DECISION
    # =====================================================

    def make_decision(
        self,
        *,
        event: TelegramObject,
        data: dict[str, Any],
        now: float,
    ) -> ThrottleDecision:
        """
        Формує рішення.
        """

        user_id = (
            self.extract_user_id(
                event=event,
                data=data,
            )
        )

        # Системні updates без користувача
        # не throttling-имо.
        if user_id is None:
            return ThrottleDecision(
                allowed=True,
                key="anonymous",
                event_type=(
                    ThrottleEventType.OTHER
                ),
                action="unknown",
                interval_seconds=0.0,
                retry_after_seconds=0.0,
            )

        chat_id = self.extract_chat_id(
            event
        )

        rule = self.resolve_rule(
            event=event,
            data=data,
        )

        interval = (
            self.resolve_custom_interval(
                data=data,
                default=(
                    rule.interval_seconds
                ),
            )
        )

        key = self.build_key(
            user_id=user_id,
            chat_id=chat_id,
            event_type=rule.event_type,
            action=rule.action,
        )

        previous = self._hits.get(
            key
        )

        if previous is None:
            self._hits[
                key
            ] = now

            return ThrottleDecision(
                allowed=True,
                key=key,
                event_type=(
                    rule.event_type
                ),
                action=rule.action,
                interval_seconds=interval,
                retry_after_seconds=0.0,
            )

        elapsed = (
            now - previous
        )

        if elapsed >= interval:
            self._hits[
                key
            ] = now

            return ThrottleDecision(
                allowed=True,
                key=key,
                event_type=(
                    rule.event_type
                ),
                action=rule.action,
                interval_seconds=interval,
                retry_after_seconds=0.0,
            )

        retry_after = max(
            0.0,
            interval - elapsed,
        )

        return ThrottleDecision(
            allowed=False,
            key=key,
            event_type=(
                rule.event_type
            ),
            action=rule.action,
            interval_seconds=interval,
            retry_after_seconds=(
                retry_after
            ),
        )

    # =====================================================
    # RULE
    # =====================================================

    def resolve_rule(
        self,
        *,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> ThrottleRule:
        """
        Визначає тип дії та cooldown.
        """

        callback = self.extract_callback(
            event
        )

        if callback is not None:
            action = (
                self.normalize_action(
                    callback.data
                    or "callback"
                )
            )

            normalized_lower = (
                action.lower()
            )

            if normalized_lower.startswith(
                self.IMPORT_CALLBACK_PREFIXES
            ):
                return ThrottleRule(
                    name="import_callback",
                    interval_seconds=(
                        self.import_callback_interval
                    ),
                    event_type=(
                        ThrottleEventType.CALLBACK
                    ),
                    action=action,
                )

            if normalized_lower.startswith(
                self.CRITICAL_CALLBACK_PREFIXES
            ):
                return ThrottleRule(
                    name="critical_callback",
                    interval_seconds=(
                        self
                        .critical_callback_interval
                    ),
                    event_type=(
                        ThrottleEventType.CALLBACK
                    ),
                    action=action,
                )

            return ThrottleRule(
                name="callback",
                interval_seconds=(
                    self.callback_interval
                ),
                event_type=(
                    ThrottleEventType.CALLBACK
                ),
                action=action,
            )

        message = self.extract_message(
            event
        )

        if message is not None:
            command = (
                self.extract_command(
                    message
                )
            )

            if command is not None:
                return ThrottleRule(
                    name="command",
                    interval_seconds=(
                        self.command_interval
                    ),
                    event_type=(
                        ThrottleEventType.COMMAND
                    ),
                    action=command,
                )

            action = (
                self.message_action(
                    message
                )
            )

            return ThrottleRule(
                name="message",
                interval_seconds=(
                    self.message_interval
                ),
                event_type=(
                    ThrottleEventType.MESSAGE
                ),
                action=action,
            )

        return ThrottleRule(
            name="other",
            interval_seconds=(
                self.message_interval
            ),
            event_type=(
                ThrottleEventType.OTHER
            ),
            action=type(
                event
            ).__name__,
        )

    # =====================================================
    # HANDLER FLAGS
    # =====================================================

    def should_bypass(
        self,
        data: dict[str, Any],
    ) -> bool:
        """
        Дозволяє вимкнути throttling
        для конкретного handler.

        Варіанти:

            data["throttle_bypass"] = True

        або handler flag:

            throttle=False
        """

        if bool(
            data.get(
                "throttle_bypass",
                False,
            )
        ):
            return True

        flags = self.extract_handler_flags(
            data
        )

        throttle_flag = flags.get(
            "throttle"
        )

        if throttle_flag is False:
            return True

        throttling_flag = flags.get(
            "throttling"
        )

        if throttling_flag is False:
            return True

        return False

    def resolve_custom_interval(
        self,
        *,
        data: dict[str, Any],
        default: float,
    ) -> float:
        """
        Підтримує custom cooldown.

        Приклади handler flags:

            throttle=2

        або:

            throttle={
                "rate": 2.5
            }
        """

        direct = data.get(
            "throttle_rate"
        )

        interval = self.interval_from_value(
            direct
        )

        if interval is not None:
            return interval

        flags = self.extract_handler_flags(
            data
        )

        for flag_name in (
            "throttle",
            "throttling",
        ):
            value = flags.get(
                flag_name
            )

            interval = (
                self.interval_from_value(
                    value
                )
            )

            if interval is not None:
                return interval

        return default

    @staticmethod
    def extract_handler_flags(
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Читає flags handler-а aiogram.
        """

        handler_object = data.get(
            "handler"
        )

        if handler_object is None:
            return {}

        flags = getattr(
            handler_object,
            "flags",
            None,
        )

        if isinstance(
            flags,
            dict,
        ):
            return flags

        return {}

    @staticmethod
    def interval_from_value(
        value: Any,
    ) -> float | None:
        """
        Витягує rate з flag.
        """

        if isinstance(
            value,
            bool,
        ):
            return None

        if isinstance(
            value,
            (int, float),
        ):
            interval = float(
                value
            )

            if interval >= 0:
                return interval

            return None

        if isinstance(
            value,
            dict,
        ):
            for key in (
                "rate",
                "interval",
                "seconds",
            ):
                rate = value.get(
                    key
                )

                if isinstance(
                    rate,
                    bool,
                ):
                    continue

                if isinstance(
                    rate,
                    (int, float),
                ):
                    interval = float(
                        rate
                    )

                    if interval >= 0:
                        return interval

        return None

    # =====================================================
    # THROTTLED RESPONSE
    # =====================================================

    async def handle_throttled(
        self,
        *,
        event: TelegramObject,
        decision: ThrottleDecision,
        now: float,
    ) -> None:
        """
        Реакція на занадто швидку дію.
        """

        callback = self.extract_callback(
            event
        )

        if callback is not None:
            await self.answer_callback(
                callback=callback,
                decision=decision,
            )

            return

        if not self.notify_messages:
            return

        message = self.extract_message(
            event
        )

        if message is None:
            return

        notice_key = (
            f"notice:{decision.key}"
        )

        previous_notice = (
            self._notices.get(
                notice_key
            )
        )

        # Не спамимо повідомленнями
        # "зачекайте".
        if (
            previous_notice is not None
            and now - previous_notice < 2.0
        ):
            return

        self._notices[
            notice_key
        ] = now

        try:
            await message.answer(
                self.build_message_notice(
                    decision
                )
            )

        except TelegramAPIError:
            logger.debug(
                "Не вдалося відправити "
                "throttle notice.",
                exc_info=True,
            )

        except Exception:
            logger.debug(
                "Помилка throttle notice.",
                exc_info=True,
            )

    # =====================================================
    # CALLBACK ANSWER
    # =====================================================

    async def answer_callback(
        self,
        *,
        callback: CallbackQuery,
        decision: ThrottleDecision,
    ) -> None:
        """
        Callback не створює нове повідомлення,
        тому показуємо коротке повідомлення.
        """

        try:
            await callback.answer(
                self.build_callback_notice(
                    decision
                ),
                show_alert=False,
            )

        except TelegramAPIError:
            # Callback міг уже протухнути.
            logger.debug(
                "Не вдалося відповісти "
                "на throttled callback.",
                exc_info=True,
            )

        except Exception:
            logger.debug(
                "Помилка при відповіді "
                "на throttled callback.",
                exc_info=True,
            )

    # =====================================================
    # NOTICE TEXT
    # =====================================================

    @staticmethod
    def build_callback_notice(
        decision: ThrottleDecision,
    ) -> str:
        """
        Текст callback.answer.
        """

        retry_after = (
            decision.retry_after_seconds
        )

        if retry_after < 1:
            return (
                "⏳ Не так швидко 🙂"
            )

        seconds = max(
            1,
            int(
                retry_after + 0.99
            ),
        )

        return (
            "⏳ Зачекайте "
            f"{seconds} с."
        )

    @staticmethod
    def build_message_notice(
        decision: ThrottleDecision,
    ) -> str:
        """
        Текст звичайного повідомлення.
        """

        retry_after = (
            decision.retry_after_seconds
        )

        if retry_after < 1:
            return (
                "⏳ Зачекайте мить "
                "і повторіть дію."
            )

        seconds = max(
            1,
            int(
                retry_after + 0.99
            ),
        )

        return (
            "⏳ Зачекайте "
            f"{seconds} с. "
            "і повторіть дію."
        )

    # =====================================================
    # KEY
    # =====================================================

    @staticmethod
    def build_key(
        *,
        user_id: int,
        chat_id: int | None,
        event_type: ThrottleEventType,
        action: str,
    ) -> str:
        """
        Один користувач може виконувати
        різні дії незалежно.
        """

        return (
            f"{user_id}:"
            f"{chat_id or 0}:"
            f"{event_type.value}:"
            f"{action}"
        )

    # =====================================================
    # MESSAGE ACTION
    # =====================================================

    @staticmethod
    def message_action(
        message: Message,
    ) -> str:
        """
        Не використовуємо сам текст,
        щоб не зберігати приватні дані.
        """

        if message.photo:
            return "photo"

        if message.document:
            return "document"

        if message.contact:
            return "contact"

        if message.location:
            return "location"

        if message.voice:
            return "voice"

        if message.video:
            return "video"

        if message.sticker:
            return "sticker"

        if message.text:
            return "text"

        return "message"

    # =====================================================
    # COMMAND
    # =====================================================

    @staticmethod
    def extract_command(
        message: Message,
    ) -> str | None:
        """
        /start abc -> /start
        /start@bot abc -> /start
        """

        text = (
            message.text
            or message.caption
        )

        if not text:
            return None

        normalized = (
            text.strip()
        )

        if not normalized.startswith(
            "/"
        ):
            return None

        command = normalized.split(
            maxsplit=1
        )[0]

        if "@" in command:
            command = command.split(
                "@",
                maxsplit=1,
            )[0]

        return (
            command.lower()[:100]
        )

    # =====================================================
    # NORMALIZE ACTION
    # =====================================================

    @classmethod
    def normalize_action(
        cls,
        value: Any,
    ) -> str:
        """
        Callback data без зайвих пробілів.
        """

        normalized = " ".join(
            str(
                value or "callback"
            )
            .strip()
            .split()
        )

        if not normalized:
            normalized = "callback"

        if (
            len(normalized)
            > cls.MAX_ACTION_LENGTH
        ):
            normalized = (
                normalized[
                    : cls.MAX_ACTION_LENGTH
                ]
            )

        return normalized

    # =====================================================
    # USER
    # =====================================================

    @staticmethod
    def extract_user_id(
        *,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> int | None:
        """
        Telegram user ID.
        """

        event_from_user = data.get(
            "event_from_user"
        )

        if event_from_user is not None:
            user_id = getattr(
                event_from_user,
                "id",
                None,
            )

            if isinstance(
                user_id,
                int,
            ):
                return user_id

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
            if (
                event.message
                and event.message.from_user
            ):
                return (
                    event.message
                    .from_user
                    .id
                )

            if event.callback_query:
                return (
                    event.callback_query
                    .from_user
                    .id
                )

            if event.inline_query:
                return (
                    event.inline_query
                    .from_user
                    .id
                )

            if event.my_chat_member:
                return (
                    event.my_chat_member
                    .from_user
                    .id
                )

            if event.chat_member:
                return (
                    event.chat_member
                    .from_user
                    .id
                )

            if event.chat_join_request:
                return (
                    event.chat_join_request
                    .from_user
                    .id
                )

        return None

    # =====================================================
    # CHAT
    # =====================================================

    @staticmethod
    def extract_chat_id(
        event: TelegramObject,
    ) -> int | None:
        """
        Telegram chat ID.
        """

        if isinstance(
            event,
            Message,
        ):
            return event.chat.id

        if isinstance(
            event,
            CallbackQuery,
        ):
            message = event.message

            if message is not None:
                chat = getattr(
                    message,
                    "chat",
                    None,
                )

                if chat is not None:
                    chat_id = getattr(
                        chat,
                        "id",
                        None,
                    )

                    if isinstance(
                        chat_id,
                        int,
                    ):
                        return chat_id

        if isinstance(
            event,
            Update,
        ):
            if event.message:
                return event.message.chat.id

            if event.callback_query:
                message = (
                    event.callback_query
                    .message
                )

                if message is not None:
                    chat = getattr(
                        message,
                        "chat",
                        None,
                    )

                    if chat is not None:
                        chat_id = getattr(
                            chat,
                            "id",
                            None,
                        )

                        if isinstance(
                            chat_id,
                            int,
                        ):
                            return chat_id

        return None

    # =====================================================
    # MESSAGE EXTRACT
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
                return event.edited_message

            if event.channel_post:
                return event.channel_post

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
                    event.callback_query
                    .message
                )

        return None

    # =====================================================
    # CALLBACK EXTRACT
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
    # CLEANUP
    # =====================================================

    def cleanup_if_needed(
        self,
        now: float,
    ) -> None:
        """
        Чистить старі ключі,
        щоб словник не ріс безкінечно.
        """

        needs_cleanup = (
            (
                now
                - self._last_cleanup
                >= self.cleanup_interval
            )
            or (
                len(self._hits)
                > self.max_entries
            )
        )

        if not needs_cleanup:
            return

        cutoff = (
            now
            - self.entry_ttl
        )

        self._hits = {
            key: timestamp
            for key, timestamp
            in self._hits.items()
            if timestamp >= cutoff
        }

        self._notices = {
            key: timestamp
            for key, timestamp
            in self._notices.items()
            if timestamp >= cutoff
        }

        # Якщо навіть після TTL
        # словник завеликий —
        # залишаємо найсвіжіші записи.
        if (
            len(self._hits)
            > self.max_entries
        ):
            newest = sorted(
                self._hits.items(),
                key=lambda item: (
                    item[1]
                ),
                reverse=True,
            )[
                : self.max_entries
            ]

            self._hits = dict(
                newest
            )

        self._last_cleanup = now

    # =====================================================
    # MANUAL RESET
    # =====================================================

    def clear(
        self,
    ) -> None:
        """
        Повністю очищає throttling cache.
        """

        self._hits.clear()
        self._notices.clear()

        self._last_cleanup = (
            time.monotonic()
        )

    def reset_user(
        self,
        user_id: int,
    ) -> int:
        """
        Очищає throttling конкретного
        Telegram-користувача.

        Повертає кількість видалених ключів.
        """

        prefix = (
            f"{user_id}:"
        )

        keys = [
            key
            for key in self._hits
            if key.startswith(
                prefix
            )
        ]

        for key in keys:
            self._hits.pop(
                key,
                None,
            )

        notice_keys = [
            key
            for key in self._notices
            if (
                f"notice:{user_id}:"
                in key
            )
        ]

        for key in notice_keys:
            self._notices.pop(
                key,
                None,
            )

        return len(
            keys
        )

    # =====================================================
    # STATISTICS
    # =====================================================

    @property
    def active_keys_count(
        self,
    ) -> int:
        """
        Кількість throttling keys.
        """

        return len(
            self._hits
        )

    # =====================================================
    # VALIDATION
    # =====================================================

    @staticmethod
    def validate_interval(
        value: float,
        field_name: str,
    ) -> None:
        """
        Перевіряє cooldown.
        """

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                f"{field_name} має "
                "бути числом."
            )

        if value < 0:
            raise ValueError(
                f"{field_name} не може "
                "бути від’ємним."
            )


# Зручні aliases.

ThrottleMiddleware = (
    ThrottlingMiddleware
)

AntiSpamMiddleware = (
    ThrottlingMiddleware
)


__all__ = [
    "ThrottlingMiddleware",
    "ThrottleMiddleware",
    "AntiSpamMiddleware",
    "ThrottleEventType",
    "ThrottleRule",
    "ThrottleDecision",
]