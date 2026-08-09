from __future__ import annotations

from typing import Any

from aiogram.filters import Filter
from aiogram.types import TelegramObject

from app.database.models.enums import UserRole
from app.database.models.user import User
from app.services.access import (
    AccessPermission,
    AccessService,
)


class AccessFilter(Filter):
    """
    Універсальний aiogram-фільтр доступу.

    Використовує AccessService,
    який додається через AccessMiddleware.

    Приклад:

        @router.message(
            AccessFilter(
                AccessPermission.VIEW_REPORTS
            )
        )
        async def reports_handler(...):
            ...

    Для конкретної ТТ:

        AccessFilter(
            AccessPermission.MANAGE_STORE,
            store_id=15,
        )

    Якщо store_id / bush_id не задано
    напряму, фільтр спробує взяти їх
    із handler data:

        current_store_id
        store_id

        current_bush_id
        bush_id
    """

    def __init__(
        self,
        permission: AccessPermission,
        *,
        store_id: int | None = None,
        bush_id: int | None = None,
        target_role: UserRole | None = None,
    ) -> None:
        self.permission = permission

        self.store_id = store_id
        self.bush_id = bush_id

        self.target_role = target_role

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

        access_service = (
            self.resolve_access_service(
                data
            )
        )

        if access_service is None:
            return False

        store_id = self.resolve_store_id(
            data
        )

        bush_id = self.resolve_bush_id(
            data
        )

        try:
            decision = (
                await access_service.check_permission(
                    user,
                    self.permission,
                    store_id=store_id,
                    bush_id=bush_id,
                    target_role=self.target_role,
                )
            )

        except (
            PermissionError,
            ValueError,
            TypeError,
        ):
            return False

        if not decision.allowed:
            return False

        return {
            "access_decision": decision,
        }

    # =====================================================
    # USER
    # =====================================================

    @staticmethod
    def resolve_user(
        data: dict[str, Any],
    ) -> User | None:
        """
        Шукає Database User,
        який додає AuthMiddleware.
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
    # ACCESS SERVICE
    # =====================================================

    @staticmethod
    def resolve_access_service(
        data: dict[str, Any],
    ) -> AccessService | None:
        """
        Шукає AccessService,
        який додає AccessMiddleware.
        """

        direct_service = data.get(
            "access_service"
        )

        if isinstance(
            direct_service,
            AccessService,
        ):
            return direct_service

        services = data.get(
            "services"
        )

        if services is None:
            return None

        service = getattr(
            services,
            "access",
            None,
        )

        if isinstance(
            service,
            AccessService,
        ):
            return service

        return None

    # =====================================================
    # STORE
    # =====================================================

    def resolve_store_id(
        self,
        data: dict[str, Any],
    ) -> int | None:
        """
        Визначає store_id.
        """

        if self.store_id is not None:
            return self.store_id

        for key in (
            "current_store_id",
            "store_id",
            "selected_store_id",
        ):
            value = data.get(
                key
            )

            result = self.normalize_id(
                value
            )

            if result is not None:
                return result

        store = data.get(
            "store"
        )

        if store is not None:
            result = self.normalize_id(
                getattr(
                    store,
                    "id",
                    None,
                )
            )

            if result is not None:
                return result

        return None

    # =====================================================
    # BUSH
    # =====================================================

    def resolve_bush_id(
        self,
        data: dict[str, Any],
    ) -> int | None:
        """
        Визначає bush_id.
        """

        if self.bush_id is not None:
            return self.bush_id

        for key in (
            "current_bush_id",
            "bush_id",
            "selected_bush_id",
        ):
            value = data.get(
                key
            )

            result = self.normalize_id(
                value
            )

            if result is not None:
                return result

        bush = data.get(
            "bush"
        )

        if bush is not None:
            result = self.normalize_id(
                getattr(
                    bush,
                    "id",
                    None,
                )
            )

            if result is not None:
                return result

        return None

    # =====================================================
    # ID NORMALIZATION
    # =====================================================

    @staticmethod
    def normalize_id(
        value: Any,
    ) -> int | None:
        """
        Перетворює значення у позитивний int.
        """

        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        try:
            result = int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

        if result <= 0:
            return None

        return result


# =========================================================
# SHORTCUT FILTERS
# =========================================================


class NetworkAccessFilter(
    AccessFilter
):
    """
    Доступ до всієї мережі.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            AccessPermission.VIEW_NETWORK
        )


class NetworkManagementFilter(
    AccessFilter
):
    """
    Управління всією мережею.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            AccessPermission.MANAGE_NETWORK
        )


class StoreViewFilter(
    AccessFilter
):
    """
    Перегляд ТТ.
    """

    def __init__(
        self,
        *,
        store_id: int | None = None,
    ) -> None:
        super().__init__(
            AccessPermission.VIEW_STORE,
            store_id=store_id,
        )


class StoreOperationFilter(
    AccessFilter
):
    """
    Робота від імені ТТ:

    - відкриття;
    - закриття;
    - щоденні операції.
    """

    def __init__(
        self,
        *,
        store_id: int | None = None,
    ) -> None:
        super().__init__(
            AccessPermission.OPERATE_STORE,
            store_id=store_id,
        )


class StoreManagementFilter(
    AccessFilter
):
    """
    Управління конкретною ТТ.
    """

    def __init__(
        self,
        *,
        store_id: int | None = None,
    ) -> None:
        super().__init__(
            AccessPermission.MANAGE_STORE,
            store_id=store_id,
        )


class BushViewFilter(
    AccessFilter
):
    """
    Перегляд куща.
    """

    def __init__(
        self,
        *,
        bush_id: int | None = None,
    ) -> None:
        super().__init__(
            AccessPermission.VIEW_BUSH,
            bush_id=bush_id,
        )


class BushManagementFilter(
    AccessFilter
):
    """
    Управління кущем.
    """

    def __init__(
        self,
        *,
        bush_id: int | None = None,
    ) -> None:
        super().__init__(
            AccessPermission.MANAGE_BUSH,
            bush_id=bush_id,
        )


class ReportsAccessFilter(
    AccessFilter
):
    """
    Доступ до звітів.

    Без store_id/bush_id —
    перевірка мережевого звіту.

    З store_id —
    перевірка звіту ТТ.

    З bush_id —
    перевірка звіту куща.
    """

    def __init__(
        self,
        *,
        store_id: int | None = None,
        bush_id: int | None = None,
    ) -> None:
        super().__init__(
            AccessPermission.VIEW_REPORTS,
            store_id=store_id,
            bush_id=bush_id,
        )


class ExportReportsFilter(
    AccessFilter
):
    """
    Доступ до експорту звітів.
    """

    def __init__(
        self,
        *,
        bush_id: int | None = None,
    ) -> None:
        super().__init__(
            AccessPermission.EXPORT_REPORTS,
            bush_id=bush_id,
        )


class RootSettingsFilter(
    AccessFilter
):
    """
    Доступ до критичних налаштувань.
    """

    def __init__(
        self,
    ) -> None:
        super().__init__(
            AccessPermission.MANAGE_SETTINGS
        )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "AccessFilter",

    "NetworkAccessFilter",
    "NetworkManagementFilter",

    "StoreViewFilter",
    "StoreOperationFilter",
    "StoreManagementFilter",

    "BushViewFilter",
    "BushManagementFilter",

    "ReportsAccessFilter",
    "ExportReportsFilter",

    "RootSettingsFilter",
]