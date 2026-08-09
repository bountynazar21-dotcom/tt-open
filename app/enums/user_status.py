from __future__ import annotations

from enum import StrEnum


class UserStatus(StrEnum):
    """
    Статус користувача в системі.

    Значення синхронізовані з
    app.database.models.enums.UserStatus.
    """

    PENDING = "pending"

    ACTIVE = "active"

    BLOCKED = "blocked"

    INACTIVE = "inactive"


__all__ = [
    "UserStatus",
]