from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aiogram.filters import Filter
from aiogram.types import TelegramObject

from app.database.models.enums import UserRole
from app.database.models.user import User


class RoleFilter(Filter):
    """
    Aiogram-фільтр для перевірки ролі користувача.

    Приклад:

        @router.message(
            RoleFilter(
                UserRole.ROOT_ADMIN,
                UserRole.DIRECTOR,
            )
        )
        async def admin_handler(...):
            ...

    Або:

        @router.callback_query(
            RoleFilter.from_iterable(
                {
                    UserRole.BUSH_ADMIN,
                    UserRole.LION,
                }
            )
        )
    """

    def __init__(
        self,
        *roles: UserRole | str,
    ) -> None:
        if not roles:
            raise ValueError(
                "RoleFilter потребує "
                "щонайменше одну роль."
            )

        self.roles = frozenset(
            self.normalize_role(
                role
            )
            for role in roles
        )

    async def __call__(
        self,
        event: TelegramObject,
        **data: Any,
    ) -> bool | dict[str, Any]:
        user = self.resolve_user(
            data
        )

        if user is None:
            return False

        role = self.get_user_role(
            user
        )

        if role is None:
            return False

        if role not in self.roles:
            return False

        return {
            "current_role": role,
        }

    # =====================================================
    # FACTORY
    # =====================================================

    @classmethod
    def from_iterable(
        cls,
        roles: Iterable[
            UserRole | str
        ],
    ) -> RoleFilter:
        """
        Створює RoleFilter із iterable ролей.
        """

        return cls(
            *tuple(roles)
        )

    # =====================================================
    # USER RESOLUTION
    # =====================================================

    @staticmethod
    def resolve_user(
        data: dict[str, Any],
    ) -> User | None:
        """
        Дістає Database User,
        який передає AuthMiddleware.
        """

        for key in (
            "database_user",
            "db_user",
            "current_user",
            "user",
        ):
            value = data.get(
                key
            )

            if isinstance(
                value,
                User,
            ):
                return value

        return None

    # =====================================================
    # ROLE RESOLUTION
    # =====================================================

    @classmethod
    def get_user_role(
        cls,
        user: User,
    ) -> UserRole | None:
        """
        Нормалізує роль із User.
        """

        raw_role = getattr(
            user,
            "role",
            None,
        )

        if raw_role is None:
            return None

        try:
            return cls.normalize_role(
                raw_role
            )

        except ValueError:
            return None

    @staticmethod
    def normalize_role(
        role: UserRole | str | Any,
    ) -> UserRole:
        """
        Перетворює UserRole/string у UserRole.

        Підтримує:

            UserRole.DIRECTOR
            "director"
            "DIRECTOR"
            enum-like object з .value
        """

        if isinstance(
            role,
            UserRole,
        ):
            return role

        raw_value = getattr(
            role,
            "value",
            role,
        )

        normalized = (
            str(raw_value)
            .strip()
            .lower()
        )

        for available_role in UserRole:
            if normalized in {
                available_role.name.lower(),
                str(
                    available_role.value
                ).lower(),
            }:
                return available_role

        raise ValueError(
            f"Невідома роль: {role}"
        )


# =========================================================
# SHORTCUT FILTERS
# =========================================================


class RootAdminFilter(
    RoleFilter
):
    """
    Лише ROOT_ADMIN.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            UserRole.ROOT_ADMIN
        )


class DirectorFilter(
    RoleFilter
):
    """
    ROOT_ADMIN або DIRECTOR.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
        )


class BushAdminFilter(
    RoleFilter
):
    """
    Управлінські ролі куща.

    ROOT_ADMIN
    DIRECTOR
    BUSH_ADMIN
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
            UserRole.BUSH_ADMIN,
        )


class LionFilter(
    RoleFilter
):
    """
    Ролі, які можуть працювати
    на рівні куща / контролю ТТ.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        )


class StoreUserFilter(
    RoleFilter
):
    """
    Тільки працівник торгової точки.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            UserRole.STORE_USER
        )


class ManagerFilter(
    RoleFilter
):
    """
    Ролі, які мають адміністративний доступ.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
            UserRole.BUSH_ADMIN,
        )


class StaffFilter(
    RoleFilter
):
    """
    Будь-яка робоча роль у системі.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
            UserRole.BUSH_ADMIN,
            UserRole.LION,
            UserRole.STORE_USER,
        )


# =========================================================
# ALIASES
# =========================================================


HasRole = RoleFilter
IsRootAdmin = RootAdminFilter
IsDirector = DirectorFilter
IsBushAdmin = BushAdminFilter
IsLion = LionFilter
IsStoreUser = StoreUserFilter


__all__ = [
    "RoleFilter",
    "HasRole",

    "RootAdminFilter",
    "DirectorFilter",
    "BushAdminFilter",
    "LionFilter",
    "StoreUserFilter",

    "ManagerFilter",
    "StaffFilter",

    "IsRootAdmin",
    "IsDirector",
    "IsBushAdmin",
    "IsLion",
    "IsStoreUser",
]