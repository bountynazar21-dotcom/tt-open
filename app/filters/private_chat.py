from __future__ import annotations

from typing import Any

from aiogram.filters import Filter
from aiogram.types import (
    CallbackQuery,
    Message,
    TelegramObject,
)


class PrivateChatFilter(Filter):
    """
    Пропускає події тільки з приватного Telegram-чату.

    Підходить для:

    - реєстрації;
    - особистих меню;
    - invite deep-link;
    - персональних дій користувача.

    Приклад:

        @router.message(
            PrivateChatFilter()
        )
        async def private_handler(
            message: Message,
        ) -> None:
            ...
    """

    PRIVATE_CHAT_TYPE = "private"

    async def __call__(
        self,
        event: TelegramObject,
        **data: Any,
    ) -> bool:
        chat_type = self.get_chat_type(
            event
        )

        return (
            chat_type
            == self.PRIVATE_CHAT_TYPE
        )

    # =====================================================
    # CHAT TYPE
    # =====================================================

    @classmethod
    def get_chat_type(
        cls,
        event: TelegramObject,
    ) -> str | None:
        """
        Визначає тип Telegram-чату.
        """

        chat = cls.get_chat(
            event
        )

        if chat is None:
            return None

        chat_type = getattr(
            chat,
            "type",
            None,
        )

        if chat_type is None:
            return None

        value = getattr(
            chat_type,
            "value",
            chat_type,
        )

        return str(
            value
        ).lower()

    # =====================================================
    # CHAT RESOLUTION
    # =====================================================

    @staticmethod
    def get_chat(
        event: TelegramObject,
    ) -> Any | None:
        """
        Дістає Chat із різних Telegram event.

        Підтримує:
        - Message;
        - CallbackQuery;
        - об'єкти з .chat;
        - об'єкти з .message.chat.
        """

        if isinstance(
            event,
            Message,
        ):
            return event.chat

        if isinstance(
            event,
            CallbackQuery,
        ):
            message = event.message

            if message is None:
                return None

            return getattr(
                message,
                "chat",
                None,
            )

        chat = getattr(
            event,
            "chat",
            None,
        )

        if chat is not None:
            return chat

        message = getattr(
            event,
            "message",
            None,
        )

        if message is not None:
            return getattr(
                message,
                "chat",
                None,
            )

        return None


# =========================================================
# ALIAS
# =========================================================


IsPrivateChat = PrivateChatFilter


__all__ = [
    "PrivateChatFilter",
    "IsPrivateChat",
]