from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """
    Ролі користувачів у системі.

    Значення синхронізовані з
    app.database.models.enums.UserRole.
    """

    ROOT_ADMIN = "root_admin"

    DIRECTOR = "director"

    BUSH_ADMIN = "bush_admin"

    LION = "lion"

    STORE_USER = "store_user"


# Короткий alias для місць,
# де зручніше використовувати Role.
Role = UserRole


__all__ = [
    "UserRole",
    "Role",
]