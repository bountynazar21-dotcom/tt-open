from __future__ import annotations

from enum import StrEnum


class InviteType(StrEnum):
    """
    Тип Telegram-запрошення.

    Значення синхронізовані з
    app.database.models.enums.InviteType.
    """

    ROLE = "role"
    BUSH = "bush"
    STORE = "store"


__all__ = [
    "InviteType",
]