from __future__ import annotations

from typing import Any

from aiogram.filters import Filter
from aiogram.types import (
    CallbackQuery,
    Message,
    TelegramObject,
)


class GroupChatFilter(Filter):
    """
    Пропускає події тільки з Telegram-груп.

    Підтримуються:

    - group
    - supergroup

    Приклад:

        @router.message(
            GroupChatFilter()
        )
        async def group_handler(
            message: Message,
        ):
            ...
    """

    GROUP_CHAT_TYPES = {
        "group",
        "supergroup",
    }

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
            in self.GROUP_CHAT_TYPES
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
        Визначає тип чату для різних
        Telegram update objects.
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
    # CHAT
    # =====================================================

    @staticmethod
    def get_chat(
        event: TelegramObject,
    ) -> Any | None:
        """
        Намагається знайти Chat
        у різних типах Telegram event.
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

            if message is not None:
                return getattr(
                    message,
                    "chat",
                    None,
                )

            return None

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


IsGroupChat = GroupChatFilter


__all__ = [
    "GroupChatFilter",
    "IsGroupChat",
]