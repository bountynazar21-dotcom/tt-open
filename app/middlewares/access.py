from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database.models.enums import UserRole
from app.database.models.user import User
from app.repositories import Repositories
from app.services.access import AccessService


HandlerType = Callable[
    [TelegramObject, dict[str, Any]],
    Awaitable[Any],
]


@dataclass(
    slots=True,
    frozen=True,
)
class MiddlewareAccessContext:
    """
    Область доступу поточного користувача.

    has_network_access=True:
        користувач бачить всю мережу.

    bush_ids:
        доступні кущі.

    store_ids:
        доступні торгові точки.
    """

    user_id: int

    role: UserRole

    has_network_access: bool

    bush_ids: frozenset[int]

    store_ids: frozenset[int]

    primary_store_id: int | None

    @property
    def has_store_access(self) -> bool:
        return bool(
            self.store_ids
        )

    @property
    def has_bush_access(self) -> bool:
        return bool(
            self.bush_ids
        )

    @property
    def is_store_user(self) -> bool:
        return (
            self.role
            == UserRole.STORE_USER
        )

    @property
    def is_lion(self) -> bool:
        return (
            self.role
            == UserRole.LION
        )

    @property
    def is_bush_admin(self) -> bool:
        return (
            self.role
            == UserRole.BUSH_ADMIN
        )

    @property
    def is_director(self) -> bool:
        return (
            self.role
            == UserRole.DIRECTOR
        )

    @property
    def is_root_admin(self) -> bool:
        return (
            self.role
            == UserRole.ROOT_ADMIN
        )


class AccessMiddleware(
    BaseMiddleware
):
    """
    Middleware області доступу.

    Працює після:

        DatabaseMiddleware
        AuthMiddleware

    AuthMiddleware визначає,
    хто користувач.

    AccessMiddleware визначає,
    що цей користувач може бачити.

    У handler data додаються:

        access_service
        access_context
        access_scope

        accessible_store_ids
        accessible_bush_ids

        has_network_access
        primary_store_id

    Наприклад handler може отримати:

        async def handler(
            message: Message,
            access_context: MiddlewareAccessContext,
        ):
            ...
    """

    def __init__(
        self,
        *,
        inject_empty_context: bool = False,
    ) -> None:
        """
        inject_empty_context:

        False:
            для неавторизованого користувача
            просто пропускаємо middleware.

        True:
            можна буде додати окремий
            anonymous context у майбутньому.
        """

        self.inject_empty_context = (
            inject_empty_context
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
        Формує access context.
        """

        user = self.extract_database_user(
            data
        )

        if user is None:
            return await handler(
                event,
                data,
            )

        repositories = (
            self.extract_repositories(
                data
            )
        )

        services = data.get(
            "services"
        )

        if services is not None:
            access_service = getattr(
                services,
                "access",
                None,
            )

        else:
            access_service = None

        if not isinstance(
            access_service,
            AccessService,
        ):
            access_service = AccessService(
                repositories
            )

        context = await self.build_context(
            user=user,
            repositories=repositories,
            access_service=access_service,
        )

        # -------------------------------------------------
        # INJECT
        # -------------------------------------------------

        data[
            "access_service"
        ] = access_service

        data[
            "access_context"
        ] = context

        # Alias — зручно для handlers.
        data[
            "access_scope"
        ] = context

        data[
            "accessible_store_ids"
        ] = set(
            context.store_ids
        )

        data[
            "accessible_bush_ids"
        ] = set(
            context.bush_ids
        )

        data[
            "has_network_access"
        ] = (
            context.has_network_access
        )

        data[
            "primary_store_id"
        ] = (
            context.primary_store_id
        )

        # Якщо користувач має лише одну ТТ,
        # одразу можемо вважати її поточною.
        if (
            not context.has_network_access
            and len(context.store_ids) == 1
            and data.get(
                "current_store_id"
            )
            is None
        ):
            only_store_id = next(
                iter(
                    context.store_ids
                )
            )

            data[
                "current_store_id"
            ] = only_store_id

        # Те саме для одного куща.
        if (
            not context.has_network_access
            and len(context.bush_ids) == 1
            and data.get(
                "current_bush_id"
            )
            is None
        ):
            only_bush_id = next(
                iter(
                    context.bush_ids
                )
            )

            data[
                "current_bush_id"
            ] = only_bush_id

        return await handler(
            event,
            data,
        )

    # =====================================================
    # BUILD CONTEXT
    # =====================================================

    async def build_context(
        self,
        *,
        user: User,
        repositories: Repositories,
        access_service: AccessService,
    ) -> MiddlewareAccessContext:
        """
        Формує область доступу.
        """

        # ROOT_ADMIN та DIRECTOR
        # бачать всю мережу.
        if self.is_global_role(
            user.role
        ):
            return MiddlewareAccessContext(
                user_id=user.id,
                role=user.role,

                has_network_access=True,

                bush_ids=frozenset(),
                store_ids=frozenset(),

                primary_store_id=None,
            )

        # -------------------------------------------------
        # TRY ACCESS SERVICE
        # -------------------------------------------------

        service_scope = (
            await self.try_service_scope(
                access_service=access_service,
                user=user,
            )
        )

        if service_scope is not None:
            bush_ids = (
                self.extract_id_collection(
                    service_scope,
                    "bush_ids",
                    "accessible_bush_ids",
                )
            )

            store_ids = (
                self.extract_id_collection(
                    service_scope,
                    "store_ids",
                    "accessible_store_ids",
                )
            )

            has_network_access = bool(
                getattr(
                    service_scope,
                    "has_network_access",
                    False,
                )
                or getattr(
                    service_scope,
                    "network_access",
                    False,
                )
                or getattr(
                    service_scope,
                    "is_global",
                    False,
                )
            )

            primary_store_id = (
                self.extract_int(
                    service_scope,
                    "primary_store_id",
                    "store_id",
                )
            )

            if (
                primary_store_id is None
            ):
                primary_store_id = (
                    await self.get_primary_store_id(
                        repositories=repositories,
                        user_id=user.id,
                    )
                )

            return MiddlewareAccessContext(
                user_id=user.id,
                role=user.role,

                has_network_access=(
                    has_network_access
                ),

                bush_ids=frozenset(
                    bush_ids
                ),

                store_ids=frozenset(
                    store_ids
                ),

                primary_store_id=(
                    primary_store_id
                ),
            )

        # -------------------------------------------------
        # FALLBACK VIA BINDINGS
        # -------------------------------------------------

        store_ids = (
            await self.get_store_ids(
                repositories=repositories,
                user_id=user.id,
            )
        )

        bush_ids = (
            await self.get_bush_ids(
                repositories=repositories,
                user_id=user.id,
            )
        )

        primary_store_id = (
            await self.get_primary_store_id(
                repositories=repositories,
                user_id=user.id,
            )
        )

        return MiddlewareAccessContext(
            user_id=user.id,
            role=user.role,

            has_network_access=False,

            bush_ids=frozenset(
                bush_ids
            ),

            store_ids=frozenset(
                store_ids
            ),

            primary_store_id=(
                primary_store_id
            ),
        )

    # =====================================================
    # ACCESS SERVICE SCOPE
    # =====================================================

    async def try_service_scope(
        self,
        *,
        access_service: AccessService,
        user: User,
    ) -> Any | None:
        """
        Пробує отримати scope через AccessService.

        Підтримує кілька можливих назв,
        щоб не прив’язувати middleware
        до одного конкретного методу.
        """

        for method_name in (
            "get_user_scope",
            "get_access_scope",
            "resolve_user_scope",
            "resolve_access_scope",
        ):
            method = getattr(
                access_service,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            try:
                result = method(
                    user
                )

            except TypeError:
                try:
                    result = method(
                        user=user
                    )

                except TypeError:
                    continue

            if inspect.isawaitable(
                result
            ):
                result = await result

            if result is not None:
                return result

        return None

    # =====================================================
    # STORE IDS
    # =====================================================

    async def get_store_ids(
        self,
        *,
        repositories: Repositories,
        user_id: int,
    ) -> set[int]:
        """
        Активні ТТ користувача.
        """

        bindings = getattr(
            repositories,
            "bindings",
            None,
        )

        if bindings is None:
            return set()

        # -------------------------------------------------
        # METHODS RETURNING IDS
        # -------------------------------------------------

        for method_name in (
            "get_user_store_ids",
            "get_accessible_store_ids",
            "list_active_store_ids_for_user",
            "list_store_ids_for_user",
        ):
            method = getattr(
                bindings,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            result = await self.call_repository_method(
                method,
                {
                    "user_id": user_id,
                    "active_only": True,
                },
            )

            return self.result_to_ids(
                result,
                field_name="store_id",
            )

        # -------------------------------------------------
        # METHODS RETURNING BINDINGS
        # -------------------------------------------------

        for method_name in (
            "get_user_store_bindings",
            "get_store_bindings_for_user",
            "list_user_store_bindings",
            "list_store_bindings_for_user",
        ):
            method = getattr(
                bindings,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            result = await self.call_repository_method(
                method,
                {
                    "user_id": user_id,
                    "active_only": True,
                },
            )

            return self.result_to_ids(
                result,
                field_name="store_id",
            )

        return set()

    # =====================================================
    # BUSH IDS
    # =====================================================

    async def get_bush_ids(
        self,
        *,
        repositories: Repositories,
        user_id: int,
    ) -> set[int]:
        """
        Активні кущі користувача.
        """

        bindings = getattr(
            repositories,
            "bindings",
            None,
        )

        if bindings is None:
            return set()

        for method_name in (
            "get_user_bush_ids",
            "get_accessible_bush_ids",
            "list_active_bush_ids_for_user",
            "list_bush_ids_for_user",
        ):
            method = getattr(
                bindings,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            result = await self.call_repository_method(
                method,
                {
                    "user_id": user_id,
                    "active_only": True,
                },
            )

            return self.result_to_ids(
                result,
                field_name="bush_id",
            )

        for method_name in (
            "get_user_bush_bindings",
            "get_bush_bindings_for_user",
            "list_user_bush_bindings",
            "list_bush_bindings_for_user",
        ):
            method = getattr(
                bindings,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            result = await self.call_repository_method(
                method,
                {
                    "user_id": user_id,
                    "active_only": True,
                },
            )

            return self.result_to_ids(
                result,
                field_name="bush_id",
            )

        return set()

    # =====================================================
    # PRIMARY STORE
    # =====================================================

    async def get_primary_store_id(
        self,
        *,
        repositories: Repositories,
        user_id: int,
    ) -> int | None:
        """
        Основна ТТ користувача.
        """

        bindings = getattr(
            repositories,
            "bindings",
            None,
        )

        if bindings is None:
            return None

        for method_name in (
            "get_primary_store_id",
            "get_primary_store",
            "get_primary_store_binding",
        ):
            method = getattr(
                bindings,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            result = await self.call_repository_method(
                method,
                {
                    "user_id": user_id,
                    "active_only": True,
                },
            )

            if isinstance(
                result,
                int,
            ):
                return (
                    result
                    if result > 0
                    else None
                )

            result_id = self.extract_int(
                result,
                "store_id",
                "id",
            )

            if result_id is not None:
                return result_id

        return None

    # =====================================================
    # REPOSITORY CALL
    # =====================================================

    async def call_repository_method(
        self,
        method: Any,
        payload: dict[str, Any],
    ) -> Any:
        """
        Викликає repository method
        із сумісними kwargs.
        """

        kwargs = self.filter_method_kwargs(
            method,
            payload,
        )

        result = method(
            **kwargs
        )

        if inspect.isawaitable(
            result
        ):
            result = await result

        return result

    # =====================================================
    # DB USER
    # =====================================================

    @staticmethod
    def extract_database_user(
        data: dict[str, Any],
    ) -> User | None:
        """
        Витягує користувача,
        створеного AuthMiddleware.
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

            if isinstance(
                value,
                User,
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

                if isinstance(
                    value,
                    User,
                ):
                    return value

        return None

    # =====================================================
    # REPOSITORIES
    # =====================================================

    @staticmethod
    def extract_repositories(
        data: dict[str, Any],
    ) -> Repositories:
        """
        Дістає Repositories,
        створений DatabaseMiddleware.
        """

        repositories = data.get(
            "repositories"
        )

        if isinstance(
            repositories,
            Repositories,
        ):
            return repositories

        db_context = data.get(
            "db_context"
        )

        if db_context is not None:
            repositories = getattr(
                db_context,
                "repositories",
                None,
            )

            if isinstance(
                repositories,
                Repositories,
            ):
                return repositories

        raise RuntimeError(
            "AccessMiddleware не знайшов "
            "Repositories. Перевір порядок "
            "підключення middleware."
        )

    # =====================================================
    # GLOBAL ROLES
    # =====================================================

    @staticmethod
    def is_global_role(
        role: UserRole,
    ) -> bool:
        """
        Ролі з доступом до всієї мережі.
        """

        return role in {
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
        }

    # =====================================================
    # COLLECTION
    # =====================================================

    @classmethod
    def extract_id_collection(
        cls,
        target: Any,
        *field_names: str,
    ) -> set[int]:
        """
        Дістає set[int] із scope object.
        """

        if target is None:
            return set()

        for field_name in field_names:
            value = getattr(
                target,
                field_name,
                None,
            )

            if value is None:
                continue

            return cls.result_to_ids(
                value,
                field_name="id",
            )

        return set()

    @classmethod
    def result_to_ids(
        cls,
        result: Any,
        *,
        field_name: str,
    ) -> set[int]:
        """
        Repository може повернути:

            list[int]
            set[int]
            list[Binding]
            tuple[...]

        Нормалізуємо все до set[int].
        """

        if result is None:
            return set()

        if isinstance(
            result,
            int,
        ):
            return {
                result
            } if result > 0 else set()

        if isinstance(
            result,
            (
                list,
                tuple,
                set,
                frozenset,
            ),
        ):
            values = result

        else:
            try:
                values = list(
                    result
                )

            except TypeError:
                values = [
                    result
                ]

        result_ids: set[int] = set()

        for item in values:
            if isinstance(
                item,
                bool,
            ):
                continue

            if isinstance(
                item,
                int,
            ):
                if item > 0:
                    result_ids.add(
                        item
                    )

                continue

            item_id = cls.extract_int(
                item,
                field_name,
            )

            if item_id is not None:
                result_ids.add(
                    item_id
                )

        return result_ids

    # =====================================================
    # EXTRACT INT
    # =====================================================

    @staticmethod
    def extract_int(
        target: Any,
        *field_names: str,
    ) -> int | None:
        """
        Дістає int-атрибут.
        """

        if target is None:
            return None

        for field_name in field_names:
            value = getattr(
                target,
                field_name,
                None,
            )

            if value is None:
                continue

            if isinstance(
                value,
                bool,
            ):
                continue

            try:
                result = int(
                    value
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if result > 0:
                return result

        return None

    # =====================================================
    # METHOD KWARGS
    # =====================================================

    @staticmethod
    def filter_method_kwargs(
        method: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Фільтрує kwargs за сигнатурою.
        """

        try:
            signature = inspect.signature(
                method
            )

        except (
            TypeError,
            ValueError,
        ):
            return dict(
                payload
            )

        accepts_kwargs = any(
            parameter.kind
            == inspect.Parameter.VAR_KEYWORD
            for parameter
            in signature.parameters.values()
        )

        if accepts_kwargs:
            return dict(
                payload
            )

        return {
            key: value
            for key, value
            in payload.items()
            if key
            in signature.parameters
        }


# Зручні aliases.

UserAccessMiddleware = (
    AccessMiddleware
)

PermissionMiddleware = (
    AccessMiddleware
)


__all__ = [
    "AccessMiddleware",
    "UserAccessMiddleware",
    "PermissionMiddleware",
    "MiddlewareAccessContext",
]