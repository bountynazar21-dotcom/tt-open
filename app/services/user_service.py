from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from html import escape
from typing import Any, TypeVar

from sqlalchemy import func, or_, select

from app.database.models.bush import Bush
from app.database.models.enums import (
    AuditAction,
    EntityType,
    UserRole,
    UserStatus,
)
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories import (
    AuditContext,
    Repositories,
)
from app.services.access import (
    AccessDeniedError,
    AccessService,
)


EnumType = TypeVar(
    "EnumType",
    bound=Enum,
)


class UserListFilter(StrEnum):
    """
    Швидкий фільтр списку користувачів.
    """

    ALL = "all"

    ACTIVE = "active"
    PENDING = "pending"
    BLOCKED = "blocked"
    INACTIVE = "inactive"

    STORE_USERS = "store_users"
    LIONS = "lions"
    BUSH_ADMINS = "bush_admins"
    DIRECTORS = "directors"
    ROOT_ADMINS = "root_admins"


@dataclass(slots=True, frozen=True)
class UserProfileView:
    """
    Повний профіль користувача.
    """

    id: int

    telegram_id: int | None

    username: str | None
    first_name: str | None
    last_name: str | None

    role: UserRole
    status: UserStatus

    is_active: bool
    is_blocked: bool

    store_ids: tuple[int, ...]
    bush_ids: tuple[int, ...]

    primary_store_id: int | None

    created_at: datetime | None
    updated_at: datetime | None
    last_seen_at: datetime | None

    raw_user: User

    @property
    def full_name(self) -> str:
        """
        Ім’я для Telegram.
        """

        name = " ".join(
            part
            for part in (
                self.first_name,
                self.last_name,
            )
            if part
        ).strip()

        if name:
            return name

        if self.username:
            return (
                f"@{self.username.lstrip('@')}"
            )

        if self.telegram_id:
            return (
                f"Telegram {self.telegram_id}"
            )

        return (
            f"Користувач #{self.id}"
        )

    @property
    def mention(self) -> str:
        """
        HTML mention користувача.
        """

        if self.username:
            return (
                f"@{escape(self.username.lstrip('@'))}"
            )

        if self.telegram_id:
            return (
                f'<a href="tg://user?id={self.telegram_id}">'
                f"{escape(self.full_name)}"
                "</a>"
            )

        return escape(
            self.full_name
        )


@dataclass(slots=True, frozen=True)
class UserListItem:
    """
    Скорочений користувач для списків.
    """

    id: int
    telegram_id: int | None

    display_name: str

    username: str | None

    role: UserRole
    status: UserStatus

    is_blocked: bool

    store_count: int
    bush_count: int

    last_seen_at: datetime | None


@dataclass(slots=True, frozen=True)
class UserSearchResult:
    """
    Результат пошуку.
    """

    query: str

    total_count: int

    users: tuple[
        UserListItem,
        ...,
    ]


@dataclass(slots=True, frozen=True)
class UserStatistics:
    """
    Статистика користувачів бота.
    """

    total_users: int

    active_users: int
    pending_users: int
    blocked_users: int
    inactive_users: int

    root_admins: int
    directors: int
    bush_admins: int
    lions: int
    store_users: int


@dataclass(slots=True, frozen=True)
class UserRoleUpdateResult:
    """
    Результат зміни ролі.
    """

    user: User

    previous_role: UserRole
    current_role: UserRole

    was_changed: bool

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class UserStatusUpdateResult:
    """
    Результат зміни статусу.
    """

    user: User

    previous_status: UserStatus
    current_status: UserStatus

    was_changed: bool

    changed_at: datetime
    changed_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class UserProfileUpdateResult:
    """
    Результат оновлення Telegram-профілю.
    """

    user: User

    was_changed: bool

    previous_values: dict[str, Any]
    current_values: dict[str, Any]

    changed_at: datetime


@dataclass(slots=True, frozen=True)
class UserAccessView:
    """
    Доступ користувача.
    """

    user_id: int

    store_ids: tuple[int, ...]
    bush_ids: tuple[int, ...]

    store_codes: tuple[str, ...]
    bush_names: tuple[str, ...]

    has_network_access: bool


@dataclass(slots=True, frozen=True)
class AdminUsersDashboard:
    """
    Дані головного адмінського меню.
    """

    statistics: UserStatistics

    pending_users: tuple[
        UserListItem,
        ...,
    ]

    blocked_users: tuple[
        UserListItem,
        ...,
    ]

    recent_users: tuple[
        UserListItem,
        ...,
    ]


class UserService:
    """
    Сервіс користувачів.

    Підтримує:

    - список;
    - пошук;
    - профіль;
    - Telegram ID;
    - username;
    - статус;
    - роль;
    - блокування;
    - доступні ТТ;
    - доступні кущі;
    - статистику;
    - dashboard адміністратора;
    - AuditLog.

    Прив’язки користувача до ТТ/кущів
    змінює BindingService.

    Підтвердження / блокування /
    активацію краще робити через AuthService.

    UserService дає централізований
    read/update API для адмінських handlers.
    """

    DEFAULT_LIMIT = 100
    MAX_LIMIT = 500

    def __init__(
        self,
        repositories: Repositories,
        *,
        access_service: AccessService | None = None,
    ) -> None:
        self.repositories = repositories
        self.session = repositories.session

        self.access = (
            access_service
            or AccessService(repositories)
        )

    # ==========================================
    # USER BY ID
    # ==========================================

    async def get_user(
        self,
        *,
        actor: User,
        user_id: int,
    ) -> UserProfileView:
        """
        Повертає профіль користувача.
        """

        target = await self.get_user_or_raise(
            user_id
        )

        await self.ensure_can_view_user(
            actor=actor,
            target=target,
        )

        return await self.build_profile(
            target
        )

    # ==========================================
    # USER BY TELEGRAM ID
    # ==========================================

    async def get_by_telegram_id(
        self,
        *,
        actor: User,
        telegram_id: int,
    ) -> UserProfileView | None:
        """
        Пошук користувача за Telegram ID.
        """

        if telegram_id <= 0:
            raise ValueError(
                "Telegram ID повинен бути "
                "більшим за нуль."
            )

        statement = (
            select(User)
            .where(
                User.telegram_id
                == telegram_id
            )
            .limit(1)
        )

        target = await self.session.scalar(
            statement
        )

        if target is None:
            return None

        await self.ensure_can_view_user(
            actor=actor,
            target=target,
        )

        return await self.build_profile(
            target
        )

    # ==========================================
    # CURRENT USER
    # ==========================================

    async def get_my_profile(
        self,
        *,
        user: User,
    ) -> UserProfileView:
        """
        Повертає власний профіль.
        """

        return await self.build_profile(
            user
        )

    # ==========================================
    # LIST
    # ==========================================

    async def get_users(
        self,
        *,
        actor: User,
        filter_type: UserListFilter = (
            UserListFilter.ALL
        ),
        store_id: int | None = None,
        bush_id: int | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> list[UserListItem]:
        """
        Повертає список користувачів.
        """

        self.validate_pagination(
            limit=limit,
            offset=offset,
        )

        if (
            store_id is not None
            and bush_id is not None
        ):
            raise ValueError(
                "Не можна одночасно "
                "вказувати ТТ і кущ."
            )

        if store_id is not None:
            decision = (
                await self.access.can_manage_store(
                    actor,
                    store_id,
                )
            )

            decision.raise_if_denied()

        elif bush_id is not None:
            decision = (
                await self.access.can_manage_bush(
                    actor,
                    bush_id,
                )
            )

            decision.raise_if_denied()

        else:
            self.access.require_network_view(
                actor
            )

        statement = (
            select(User)
            .order_by(
                *self.user_order_columns()
            )
            .offset(offset)
            .limit(limit * 3)
        )

        statement = (
            self.apply_list_filter(
                statement,
                filter_type,
            )
        )

        result = await self.session.scalars(
            statement
        )

        users = list(
            result.unique().all()
        )

        items: list[
            UserListItem
        ] = []

        for user in users:
            access_view = (
                await self.get_access_internal(
                    user
                )
            )

            if (
                store_id is not None
                and store_id
                not in access_view.store_ids
                and not access_view
                .has_network_access
            ):
                continue

            if (
                bush_id is not None
                and bush_id
                not in access_view.bush_ids
                and not access_view
                .has_network_access
            ):
                continue

            try:
                await self.ensure_can_view_user(
                    actor=actor,
                    target=user,
                )

            except AccessDeniedError:
                continue

            items.append(
                self.build_list_item(
                    user,
                    access_view=access_view,
                )
            )

            if len(items) >= limit:
                break

        return items

    # ==========================================
    # SEARCH
    # ==========================================

    async def search_users(
        self,
        *,
        actor: User,
        query: str,
        limit: int = 50,
    ) -> UserSearchResult:
        """
        Шукає користувача за:

        - ID у БД;
        - Telegram ID;
        - username;
        - ім’ям;
        - прізвищем.
        """

        self.validate_pagination(
            limit=limit,
            offset=0,
        )

        self.access.ensure_active_user(
            actor
        )

        normalized_query = (
            self.normalize_required_text(
                query,
                field_name="Пошук",
                max_length=200,
            )
        )

        conditions: list[Any] = []

        search_text = (
            f"%{normalized_query}%"
        )

        for field_name in (
            "username",
            "telegram_username",
            "first_name",
            "last_name",
        ):
            column = getattr(
                User,
                field_name,
                None,
            )

            if column is not None:
                conditions.append(
                    column.ilike(
                        search_text
                    )
                )

        numeric_query = (
            self.try_int(
                normalized_query
                .replace("@", "")
            )
        )

        if numeric_query is not None:
            conditions.append(
                User.id
                == numeric_query
            )

            telegram_column = getattr(
                User,
                "telegram_id",
                None,
            )

            if telegram_column is not None:
                conditions.append(
                    telegram_column
                    == numeric_query
                )

        username_query = (
            normalized_query
            .lstrip("@")
        )

        username_column = (
            self.first_model_column(
                "username",
                "telegram_username",
            )
        )

        if (
            username_query
            and username_column is not None
        ):
            conditions.append(
                func.lower(
                    username_column
                )
                == username_query.lower()
            )

        if not conditions:
            return UserSearchResult(
                query=normalized_query,
                total_count=0,
                users=(),
            )

        statement = (
            select(User)
            .where(
                or_(*conditions)
            )
            .order_by(
                *self.user_order_columns()
            )
            .limit(limit * 2)
        )

        result = await self.session.scalars(
            statement
        )

        users = list(
            result.unique().all()
        )

        items: list[
            UserListItem
        ] = []

        for user in users:
            try:
                await self.ensure_can_view_user(
                    actor=actor,
                    target=user,
                )

            except AccessDeniedError:
                continue

            access_view = (
                await self.get_access_internal(
                    user
                )
            )

            items.append(
                self.build_list_item(
                    user,
                    access_view=access_view,
                )
            )

            if len(items) >= limit:
                break

        return UserSearchResult(
            query=normalized_query,
            total_count=len(items),
            users=tuple(items),
        )

    # ==========================================
    # PENDING
    # ==========================================

    async def get_pending_users(
        self,
        *,
        actor: User,
        limit: int = 100,
    ) -> list[UserListItem]:
        """
        Нові користувачі,
        які очікують підтвердження.
        """

        return await self.get_users(
            actor=actor,
            filter_type=(
                UserListFilter.PENDING
            ),
            limit=limit,
        )

    # ==========================================
    # BLOCKED
    # ==========================================

    async def get_blocked_users(
        self,
        *,
        actor: User,
        limit: int = 100,
    ) -> list[UserListItem]:
        """
        Заблоковані користувачі.
        """

        return await self.get_users(
            actor=actor,
            filter_type=(
                UserListFilter.BLOCKED
            ),
            limit=limit,
        )

    # ==========================================
    # ACCESS
    # ==========================================

    async def get_access(
        self,
        *,
        actor: User,
        user_id: int,
    ) -> UserAccessView:
        """
        Доступ користувача до ТТ/кущів.
        """

        target = await self.get_user_or_raise(
            user_id
        )

        await self.ensure_can_view_user(
            actor=actor,
            target=target,
        )

        return await self.get_access_internal(
            target
        )

    async def get_access_internal(
        self,
        user: User,
    ) -> UserAccessView:
        """
        Внутрішній доступ без permission check.
        """

        has_network_access = (
            self.is_global_role(
                user.role
            )
        )

        if has_network_access:
            return UserAccessView(
                user_id=user.id,
                store_ids=(),
                bush_ids=(),
                store_codes=(),
                bush_names=(),
                has_network_access=True,
            )

        store_ids = (
            await self.get_user_store_ids(
                user.id
            )
        )

        bush_ids = (
            await self.get_user_bush_ids(
                user.id
            )
        )

        store_codes = (
            await self.get_store_codes(
                store_ids
            )
        )

        bush_names = (
            await self.get_bush_names(
                bush_ids
            )
        )

        return UserAccessView(
            user_id=user.id,

            store_ids=tuple(
                sorted(store_ids)
            ),

            bush_ids=tuple(
                sorted(bush_ids)
            ),

            store_codes=tuple(
                store_codes
            ),

            bush_names=tuple(
                bush_names
            ),

            has_network_access=False,
        )

    # ==========================================
    # STORE IDS
    # ==========================================

    async def get_user_store_ids(
        self,
        user_id: int,
    ) -> set[int]:
        """
        Активні ТТ користувача.
        """

        repository = getattr(
            self.repositories,
            "bindings",
            None,
        )

        if repository is None:
            return set()

        method_names = (
            "get_user_store_ids",
            "get_accessible_store_ids",
            "list_active_store_ids_for_user",
            "list_store_ids_for_user",
        )

        for method_name in method_names:
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(method):
                continue

            result = method(
                **self.filter_method_kwargs(
                    method,
                    {
                        "user_id": user_id,
                        "active_only": True,
                    },
                )
            )

            if inspect.isawaitable(
                result
            ):
                result = await result

            return self.extract_ids(
                result,
                field_name="store_id",
            )

        # Fallback — отримуємо binding objects.

        for method_name in (
            "get_user_store_bindings",
            "get_store_bindings_for_user",
            "list_user_store_bindings",
        ):
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(method):
                continue

            result = method(
                **self.filter_method_kwargs(
                    method,
                    {
                        "user_id": user_id,
                        "active_only": True,
                    },
                )
            )

            if inspect.isawaitable(
                result
            ):
                result = await result

            return {
                store_id
                for item in self.as_list(
                    result
                )
                if (
                    store_id
                    := self.get_int_attribute(
                        item,
                        "store_id",
                    )
                )
                is not None
            }

        return set()

    # ==========================================
    # BUSH IDS
    # ==========================================

    async def get_user_bush_ids(
        self,
        user_id: int,
    ) -> set[int]:
        """
        Активні кущі користувача.
        """

        repository = getattr(
            self.repositories,
            "bindings",
            None,
        )

        if repository is None:
            return set()

        method_names = (
            "get_user_bush_ids",
            "get_accessible_bush_ids",
            "list_active_bush_ids_for_user",
            "list_bush_ids_for_user",
        )

        for method_name in method_names:
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(method):
                continue

            result = method(
                **self.filter_method_kwargs(
                    method,
                    {
                        "user_id": user_id,
                        "active_only": True,
                    },
                )
            )

            if inspect.isawaitable(
                result
            ):
                result = await result

            return self.extract_ids(
                result,
                field_name="bush_id",
            )

        for method_name in (
            "get_user_bush_bindings",
            "get_bush_bindings_for_user",
            "list_user_bush_bindings",
        ):
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(method):
                continue

            result = method(
                **self.filter_method_kwargs(
                    method,
                    {
                        "user_id": user_id,
                        "active_only": True,
                    },
                )
            )

            if inspect.isawaitable(
                result
            ):
                result = await result

            return {
                bush_id
                for item in self.as_list(
                    result
                )
                if (
                    bush_id
                    := self.get_int_attribute(
                        item,
                        "bush_id",
                    )
                )
                is not None
            }

        return set()

    # ==========================================
    # PRIMARY STORE
    # ==========================================

    async def get_primary_store_id(
        self,
        user_id: int,
    ) -> int | None:
        """
        Основна ТТ користувача.
        """

        repository = getattr(
            self.repositories,
            "bindings",
            None,
        )

        if repository is None:
            return None

        for method_name in (
            "get_primary_store_id",
            "get_primary_store",
            "get_primary_store_binding",
        ):
            method = getattr(
                repository,
                method_name,
                None,
            )

            if not callable(method):
                continue

            result = method(
                **self.filter_method_kwargs(
                    method,
                    {
                        "user_id": user_id,
                        "active_only": True,
                    },
                )
            )

            if inspect.isawaitable(
                result
            ):
                result = await result

            if isinstance(
                result,
                int,
            ):
                return result

            if isinstance(
                result,
                Store,
            ):
                return result.id

            store_id = self.get_int_attribute(
                result,
                "store_id",
            )

            if store_id is not None:
                return store_id

        return None

    # ==========================================
    # ROLE UPDATE
    # ==========================================

    async def change_role(
        self,
        *,
        actor: User,
        user_id: int,
        role: UserRole,
        reason: str,
        changed_at: datetime | None = None,
    ) -> UserRoleUpdateResult:
        """
        Змінює роль.

        Для складних змін із прив’язками
        бажано використовувати AuthService.
        """

        now = (
            changed_at
            or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        await self.ensure_can_manage_user(
            actor=actor,
            target=target,
        )

        if (
            role
            in {
                UserRole.ROOT_ADMIN,
                UserRole.DIRECTOR,
            }
        ):
            self.access.ensure_root_admin(
                actor
            )

        previous_role = (
            target.role
        )

        if previous_role == role:
            return UserRoleUpdateResult(
                user=target,
                previous_role=(
                    previous_role
                ),
                current_role=role,
                was_changed=False,
                changed_at=now,
                changed_by_id=actor.id,
                reason=normalized_reason,
            )

        target.role = role

        self.set_first_existing_attribute(
            target,
            actor.id,
            "updated_by_id",
            "modified_by_id",
        )

        self.set_first_existing_attribute(
            target,
            now,
            "updated_at",
            "modified_at",
        )

        self.session.add(
            target
        )

        await self.session.flush()

        await self.log_user_change(
            actor=actor,
            target=target,
            description=(
                "Змінено роль користувача"
            ),
            reason=normalized_reason,
            old_values={
                "role": (
                    previous_role.value
                ),
            },
            new_values={
                "role": role.value,
            },
        )

        return UserRoleUpdateResult(
            user=target,
            previous_role=(
                previous_role
            ),
            current_role=role,
            was_changed=True,
            changed_at=now,
            changed_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # STATUS UPDATE
    # ==========================================

    async def change_status(
        self,
        *,
        actor: User,
        user_id: int,
        status: UserStatus,
        reason: str,
        changed_at: datetime | None = None,
    ) -> UserStatusUpdateResult:
        """
        Змінює статус користувача.
        """

        now = (
            changed_at
            or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        target = await self.get_user_or_raise(
            user_id,
            for_update=True,
        )

        await self.ensure_can_manage_user(
            actor=actor,
            target=target,
        )

        if (
            actor.id == target.id
            and not self.status_is_active(
                status
            )
        ):
            raise AccessDeniedError(
                "Не можна вимкнути "
                "власний акаунт."
            )

        previous_status = (
            target.status
        )

        if previous_status == status:
            return UserStatusUpdateResult(
                user=target,

                previous_status=(
                    previous_status
                ),

                current_status=status,

                was_changed=False,

                changed_at=now,
                changed_by_id=actor.id,

                reason=normalized_reason,
            )

        target.status = status

        if self.status_is_active(
            status
        ):
            self.set_first_existing_attribute(
                target,
                False,
                "is_blocked",
            )

        self.set_first_existing_attribute(
            target,
            normalized_reason,
            "status_reason",
        )

        self.set_first_existing_attribute(
            target,
            actor.id,
            "status_changed_by_id",
            "updated_by_id",
        )

        self.set_first_existing_attribute(
            target,
            now,
            "status_changed_at",
            "updated_at",
        )

        self.session.add(
            target
        )

        await self.session.flush()

        await self.log_user_change(
            actor=actor,
            target=target,

            description=(
                "Змінено статус користувача"
            ),

            reason=normalized_reason,

            old_values={
                "status": (
                    previous_status.value
                ),
            },

            new_values={
                "status": (
                    status.value
                ),
            },
        )

        return UserStatusUpdateResult(
            user=target,

            previous_status=(
                previous_status
            ),

            current_status=status,

            was_changed=True,

            changed_at=now,
            changed_by_id=actor.id,

            reason=normalized_reason,
        )

    # ==========================================
    # TELEGRAM PROFILE SYNC
    # ==========================================

    async def update_telegram_profile(
        self,
        *,
        user: User,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None = None,
        is_premium: bool | None = None,
        changed_at: datetime | None = None,
    ) -> UserProfileUpdateResult:
        """
        Оновлює Telegram-поля користувача.
        """

        now = (
            changed_at
            or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        previous = (
            self.telegram_profile_snapshot(
                user
            )
        )

        normalized_username = (
            self.normalize_optional_text(
                username,
                max_length=100,
            )
        )

        if normalized_username:
            normalized_username = (
                normalized_username
                .lstrip("@")
            )

        self.set_first_existing_attribute(
            user,
            normalized_username,
            "telegram_username",
            "username",
        )

        self.set_first_existing_attribute(
            user,
            self.normalize_optional_text(
                first_name,
                max_length=255,
            ),
            "first_name",
        )

        self.set_first_existing_attribute(
            user,
            self.normalize_optional_text(
                last_name,
                max_length=255,
            ),
            "last_name",
        )

        if language_code is not None:
            self.set_first_existing_attribute(
                user,
                self.normalize_optional_text(
                    language_code,
                    max_length=20,
                ),
                "language_code",
            )

        if is_premium is not None:
            self.set_first_existing_attribute(
                user,
                bool(is_premium),
                "is_premium",
                "telegram_is_premium",
            )

        self.set_first_existing_attribute(
            user,
            now,
            "last_seen_at",
            "last_activity_at",
        )

        self.set_first_existing_attribute(
            user,
            now,
            "updated_at",
            "modified_at",
        )

        current = (
            self.telegram_profile_snapshot(
                user
            )
        )

        was_changed = (
            previous != current
        )

        if was_changed:
            self.session.add(
                user
            )

            await self.session.flush()

        return UserProfileUpdateResult(
            user=user,

            was_changed=was_changed,

            previous_values=(
                previous
            ),

            current_values=(
                current
            ),

            changed_at=now,
        )

    # ==========================================
    # TOUCH LAST SEEN
    # ==========================================

    async def touch_last_seen(
        self,
        user: User,
        *,
        seen_at: datetime | None = None,
    ) -> None:
        """
        Оновлює last_seen.
        """

        now = (
            seen_at
            or datetime.now(UTC)
        )

        self.validate_aware_datetime(
            now,
            field_name="seen_at",
        )

        changed = (
            self.set_first_existing_attribute(
                user,
                now,
                "last_seen_at",
                "last_activity_at",
            )
        )

        if changed:
            self.session.add(
                user
            )

            await self.session.flush()

    # ==========================================
    # STATISTICS
    # ==========================================

    async def get_statistics(
        self,
        *,
        actor: User,
    ) -> UserStatistics:
        """
        Статистика користувачів.
        """

        self.access.require_network_view(
            actor
        )

        result = await self.session.scalars(
            select(User)
        )

        users = list(
            result.unique().all()
        )

        return self.build_statistics(
            users
        )

    @classmethod
    def build_statistics(
        cls,
        users: list[User],
    ) -> UserStatistics:
        """
        Рахує статистику.
        """

        return UserStatistics(
            total_users=len(users),

            active_users=sum(
                cls.status_matches(
                    user.status,
                    "active",
                    "enabled",
                )
                and not bool(
                    getattr(
                        user,
                        "is_blocked",
                        False,
                    )
                )
                for user in users
            ),

            pending_users=sum(
                cls.status_matches(
                    user.status,
                    "pending",
                    "waiting_approval",
                    "unverified",
                )
                for user in users
            ),

            blocked_users=sum(
                bool(
                    getattr(
                        user,
                        "is_blocked",
                        False,
                    )
                )
                or cls.status_matches(
                    user.status,
                    "blocked",
                    "banned",
                )
                for user in users
            ),

            inactive_users=sum(
                cls.status_matches(
                    user.status,
                    "inactive",
                    "disabled",
                    "deactivated",
                    "rejected",
                )
                for user in users
            ),

            root_admins=sum(
                user.role
                == UserRole.ROOT_ADMIN
                for user in users
            ),

            directors=sum(
                user.role
                == UserRole.DIRECTOR
                for user in users
            ),

            bush_admins=sum(
                user.role
                == UserRole.BUSH_ADMIN
                for user in users
            ),

            lions=sum(
                user.role
                == UserRole.LION
                for user in users
            ),

            store_users=sum(
                user.role
                == UserRole.STORE_USER
                for user in users
            ),
        )

    # ==========================================
    # ADMIN DASHBOARD
    # ==========================================

    async def get_admin_dashboard(
        self,
        *,
        actor: User,
    ) -> AdminUsersDashboard:
        """
        Dashboard керування користувачами.
        """

        self.access.require_network_view(
            actor
        )

        statistics = (
            await self.get_statistics(
                actor=actor
            )
        )

        pending = (
            await self.get_users(
                actor=actor,
                filter_type=(
                    UserListFilter.PENDING
                ),
                limit=20,
            )
        )

        blocked = (
            await self.get_users(
                actor=actor,
                filter_type=(
                    UserListFilter.BLOCKED
                ),
                limit=20,
            )
        )

        statement = (
            select(User)
            .order_by(
                *self.recent_user_order_columns()
            )
            .limit(20)
        )

        result = await self.session.scalars(
            statement
        )

        recent_users: list[
            UserListItem
        ] = []

        for user in result.unique().all():
            try:
                await self.ensure_can_view_user(
                    actor=actor,
                    target=user,
                )

            except AccessDeniedError:
                continue

            access_view = (
                await self.get_access_internal(
                    user
                )
            )

            recent_users.append(
                self.build_list_item(
                    user,
                    access_view=access_view,
                )
            )

        return AdminUsersDashboard(
            statistics=statistics,

            pending_users=tuple(
                pending
            ),

            blocked_users=tuple(
                blocked
            ),

            recent_users=tuple(
                recent_users
            ),
        )

    # ==========================================
    # BUILD PROFILE
    # ==========================================

    async def build_profile(
        self,
        user: User,
    ) -> UserProfileView:
        """
        Формує повний профіль.
        """

        access_view = (
            await self.get_access_internal(
                user
            )
        )

        primary_store_id = (
            await self.get_primary_store_id(
                user.id
            )
        )

        return UserProfileView(
            id=user.id,

            telegram_id=self.get_int_attribute(
                user,
                "telegram_id",
            ),

            username=self.get_text_attribute(
                user,
                "telegram_username",
                "username",
            ),

            first_name=self.get_text_attribute(
                user,
                "first_name",
            ),

            last_name=self.get_text_attribute(
                user,
                "last_name",
            ),

            role=user.role,
            status=user.status,

            is_active=(
                self.status_is_active(
                    user.status
                )
            ),

            is_blocked=bool(
                getattr(
                    user,
                    "is_blocked",
                    False,
                )
            ),

            store_ids=(
                access_view.store_ids
            ),

            bush_ids=(
                access_view.bush_ids
            ),

            primary_store_id=(
                primary_store_id
            ),

            created_at=self.get_datetime_attribute(
                user,
                "created_at",
            ),

            updated_at=self.get_datetime_attribute(
                user,
                "updated_at",
                "modified_at",
            ),

            last_seen_at=self.get_datetime_attribute(
                user,
                "last_seen_at",
                "last_activity_at",
            ),

            raw_user=user,
        )

    # ==========================================
    # LIST ITEM
    # ==========================================

    def build_list_item(
        self,
        user: User,
        *,
        access_view: UserAccessView,
    ) -> UserListItem:
        """
        Формує елемент списку.
        """

        return UserListItem(
            id=user.id,

            telegram_id=self.get_int_attribute(
                user,
                "telegram_id",
            ),

            display_name=(
                self.user_display_name(
                    user
                )
            ),

            username=(
                self.get_text_attribute(
                    user,
                    "telegram_username",
                    "username",
                )
            ),

            role=user.role,
            status=user.status,

            is_blocked=bool(
                getattr(
                    user,
                    "is_blocked",
                    False,
                )
            ),

            store_count=len(
                access_view.store_ids
            ),

            bush_count=len(
                access_view.bush_ids
            ),

            last_seen_at=(
                self.get_datetime_attribute(
                    user,
                    "last_seen_at",
                    "last_activity_at",
                )
            ),
        )

    # ==========================================
    # FILTER
    # ==========================================

    @classmethod
    def apply_list_filter(
        cls,
        statement: Any,
        filter_type: UserListFilter,
    ) -> Any:
        """
        SQL-фільтр користувачів.
        """

        if filter_type == UserListFilter.ALL:
            return statement

        if filter_type == UserListFilter.STORE_USERS:
            return statement.where(
                User.role
                == UserRole.STORE_USER
            )

        if filter_type == UserListFilter.LIONS:
            return statement.where(
                User.role
                == UserRole.LION
            )

        if filter_type == UserListFilter.BUSH_ADMINS:
            return statement.where(
                User.role
                == UserRole.BUSH_ADMIN
            )

        if filter_type == UserListFilter.DIRECTORS:
            return statement.where(
                User.role
                == UserRole.DIRECTOR
            )

        if filter_type == UserListFilter.ROOT_ADMINS:
            return statement.where(
                User.role
                == UserRole.ROOT_ADMIN
            )

        statuses = list(
            UserStatus
        )

        if filter_type == UserListFilter.PENDING:
            matched = cls.find_statuses(
                statuses,
                "pending",
                "waiting_approval",
                "unverified",
            )

            if not matched:
                return statement.where(
                    User.id == -1
                )

            return statement.where(
                User.status.in_(
                    matched
                )
            )

        if filter_type == UserListFilter.INACTIVE:
            matched = cls.find_statuses(
                statuses,
                "inactive",
                "disabled",
                "deactivated",
                "rejected",
            )

            if not matched:
                return statement.where(
                    User.id == -1
                )

            return statement.where(
                User.status.in_(
                    matched
                )
            )

        if filter_type == UserListFilter.BLOCKED:
            blocked_statuses = (
                cls.find_statuses(
                    statuses,
                    "blocked",
                    "banned",
                )
            )

            conditions: list[Any] = []

            if blocked_statuses:
                conditions.append(
                    User.status.in_(
                        blocked_statuses
                    )
                )

            blocked_column = getattr(
                User,
                "is_blocked",
                None,
            )

            if blocked_column is not None:
                conditions.append(
                    blocked_column.is_(True)
                )

            if not conditions:
                return statement.where(
                    User.id == -1
                )

            return statement.where(
                or_(*conditions)
            )

        if filter_type == UserListFilter.ACTIVE:
            active_statuses = (
                cls.find_statuses(
                    statuses,
                    "active",
                    "enabled",
                )
            )

            if not active_statuses:
                return statement.where(
                    User.id == -1
                )

            statement = statement.where(
                User.status.in_(
                    active_statuses
                )
            )

            blocked_column = getattr(
                User,
                "is_blocked",
                None,
            )

            if blocked_column is not None:
                statement = statement.where(
                    or_(
                        blocked_column.is_(False),
                        blocked_column.is_(None),
                    )
                )

            return statement

        return statement

    # ==========================================
    # PERMISSIONS
    # ==========================================

    async def ensure_can_view_user(
        self,
        *,
        actor: User,
        target: User,
    ) -> None:
        """
        Чи можна переглядати профіль.
        """

        self.access.ensure_active_user(
            actor
        )

        if actor.id == target.id:
            return

        if self.is_global_role(
            actor.role
        ):
            return

        target_access = (
            await self.get_access_internal(
                target
            )
        )

        actor_access = (
            await self.get_access_internal(
                actor
            )
        )

        if (
            set(
                target_access.store_ids
            )
            .intersection(
                actor_access.store_ids
            )
        ):
            return

        if (
            set(
                target_access.bush_ids
            )
            .intersection(
                actor_access.bush_ids
            )
        ):
            return

        # Адмін куща може бачити
        # працівників ТТ свого куща.

        for store_id in (
            target_access.store_ids
        ):
            store = await self.session.get(
                Store,
                store_id,
            )

            if (
                store is not None
                and getattr(
                    store,
                    "bush_id",
                    None,
                )
                in actor_access.bush_ids
            ):
                return

        raise AccessDeniedError(
            "Недостатньо прав для перегляду "
            "цього користувача."
        )

    async def ensure_can_manage_user(
        self,
        *,
        actor: User,
        target: User,
    ) -> None:
        """
        Чи можна змінювати користувача.
        """

        self.access.ensure_active_user(
            actor
        )

        if actor.role == UserRole.ROOT_ADMIN:
            return

        if target.role == UserRole.ROOT_ADMIN:
            raise AccessDeniedError(
                "ROOT_ADMIN може змінювати "
                "лише ROOT_ADMIN."
            )

        if target.role == UserRole.DIRECTOR:
            raise AccessDeniedError(
                "Директора може змінювати "
                "лише ROOT_ADMIN."
            )

        if actor.role == UserRole.DIRECTOR:
            return

        if actor.id == target.id:
            raise AccessDeniedError(
                "Цю зміну не можна виконати "
                "для власного акаунта."
            )

        await self.ensure_can_view_user(
            actor=actor,
            target=target,
        )

    # ==========================================
    # STORE CODES
    # ==========================================

    async def get_store_codes(
        self,
        store_ids: set[int],
    ) -> list[str]:
        """
        Коди доступних ТТ.
        """

        if not store_ids:
            return []

        statement = (
            select(Store)
            .where(
                Store.id.in_(
                    store_ids
                )
            )
        )

        result = await self.session.scalars(
            statement
        )

        stores = list(
            result.unique().all()
        )

        stores.sort(
            key=lambda store: (
                self.store_number(
                    store
                )
                or 999999,
                store.id,
            )
        )

        return [
            self.store_code(
                store
            )
            for store in stores
        ]

    # ==========================================
    # BUSH NAMES
    # ==========================================

    async def get_bush_names(
        self,
        bush_ids: set[int],
    ) -> list[str]:
        """
        Назви доступних кущів.
        """

        if not bush_ids:
            return []

        statement = (
            select(Bush)
            .where(
                Bush.id.in_(
                    bush_ids
                )
            )
        )

        result = await self.session.scalars(
            statement
        )

        bushes = list(
            result.unique().all()
        )

        bushes.sort(
            key=lambda bush: (
                self.bush_name(
                    bush
                ).lower(),
                bush.id,
            )
        )

        return [
            self.bush_name(
                bush
            )
            for bush in bushes
        ]

    # ==========================================
    # GET MODEL
    # ==========================================

    async def get_user_or_raise(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> User:
        """
        User по ID.
        """

        if user_id <= 0:
            raise ValueError(
                "ID користувача повинен "
                "бути більшим за нуль."
            )

        statement = (
            select(User)
            .where(
                User.id == user_id
            )
        )

        if for_update:
            statement = (
                statement.with_for_update()
            )

        user = await self.session.scalar(
            statement
        )

        if user is None:
            raise ValueError(
                "Користувача не знайдено."
            )

        return user

    # ==========================================
    # AUDIT
    # ==========================================

    async def log_user_change(
        self,
        *,
        actor: User,
        target: User,
        description: str,
        reason: str,
        old_values: dict[str, Any],
        new_values: dict[str, Any],
    ) -> None:
        """
        AuditLog користувача.
        """

        action = (
            self.resolve_audit_action(
                "update",
                "changed",
            )
        )

        entity_type = (
            self.resolve_entity_type(
                "user",
                "account",
            )
        )

        await self.repositories.audit.log_action(
            action=action,

            entity_type=entity_type,

            entity_id=target.id,

            context=AuditContext(
                actor_user_id=actor.id,

                reason=reason,

                description=(
                    description
                ),

                source="telegram_bot",
            ),

            old_values=(
                old_values
            ),

            new_values=(
                new_values
            ),
        )

    # ==========================================
    # SNAPSHOT
    # ==========================================

    @classmethod
    def telegram_profile_snapshot(
        cls,
        user: User,
    ) -> dict[str, Any]:
        """
        Telegram-поля.
        """

        return {
            "telegram_id": (
                cls.get_int_attribute(
                    user,
                    "telegram_id",
                )
            ),

            "username": (
                cls.get_text_attribute(
                    user,
                    "telegram_username",
                    "username",
                )
            ),

            "first_name": (
                cls.get_text_attribute(
                    user,
                    "first_name",
                )
            ),

            "last_name": (
                cls.get_text_attribute(
                    user,
                    "last_name",
                )
            ),

            "language_code": (
                cls.get_text_attribute(
                    user,
                    "language_code",
                )
            ),

            "is_premium": bool(
                cls.get_attribute(
                    user,
                    "is_premium",
                    "telegram_is_premium",
                    default=False,
                )
            ),
        }

    # ==========================================
    # ROLE / STATUS
    # ==========================================

    @staticmethod
    def is_global_role(
        role: UserRole,
    ) -> bool:
        """
        Доступ до всієї мережі.
        """

        return role in {
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
        }

    @staticmethod
    def role_text(
        role: UserRole,
    ) -> str:
        """
        Українська назва ролі.
        """

        mapping = {
            UserRole.ROOT_ADMIN: (
                "ROOT ADMIN"
            ),

            UserRole.DIRECTOR: (
                "Директор"
            ),

            UserRole.BUSH_ADMIN: (
                "Адміністратор куща"
            ),

            UserRole.LION: (
                "Лев"
            ),

            UserRole.STORE_USER: (
                "Торгова точка"
            ),
        }

        return mapping.get(
            role,
            str(role.value),
        )

    @classmethod
    def status_text(
        cls,
        status: UserStatus,
    ) -> str:
        """
        Українська назва статусу.
        """

        if cls.status_matches(
            status,
            "active",
            "enabled",
        ):
            return "Активний"

        if cls.status_matches(
            status,
            "pending",
            "waiting_approval",
            "unverified",
        ):
            return "Очікує підтвердження"

        if cls.status_matches(
            status,
            "blocked",
            "banned",
        ):
            return "Заблокований"

        if cls.status_matches(
            status,
            "rejected",
            "declined",
        ):
            return "Відхилений"

        if cls.status_matches(
            status,
            "inactive",
            "disabled",
            "deactivated",
        ):
            return "Неактивний"

        return str(
            status.value
        )

    @classmethod
    def status_is_active(
        cls,
        status: UserStatus,
    ) -> bool:
        """
        ACTIVE?
        """

        return cls.status_matches(
            status,
            "active",
            "enabled",
        )

    @staticmethod
    def status_matches(
        status: UserStatus,
        *names: str,
    ) -> bool:
        """
        Порівнює UserStatus.
        """

        values = {
            status.name.lower(),
            str(
                status.value
            ).lower(),
        }

        expected = {
            name.strip().lower()
            for name in names
        }

        return bool(
            values.intersection(
                expected
            )
        )

    @classmethod
    def find_statuses(
        cls,
        statuses: list[UserStatus],
        *names: str,
    ) -> list[UserStatus]:
        """
        Знаходить UserStatus.
        """

        return [
            status
            for status in statuses
            if cls.status_matches(
                status,
                *names,
            )
        ]

    # ==========================================
    # ENUM
    # ==========================================

    @classmethod
    def resolve_audit_action(
        cls,
        *names: str,
    ) -> AuditAction:
        """
        AuditAction.
        """

        result = cls.resolve_enum_member(
            AuditAction,
            *names,
            default=None,
        )

        if result is not None:
            return result

        result = cls.resolve_enum_member(
            AuditAction,
            "update",
            default=None,
        )

        if result is None:
            raise ValueError(
                "Не знайдено AuditAction."
            )

        return result

    @classmethod
    def resolve_entity_type(
        cls,
        *names: str,
    ) -> EntityType:
        """
        EntityType.
        """

        result = cls.resolve_enum_member(
            EntityType,
            *names,
            default=None,
        )

        if result is not None:
            return result

        result = cls.resolve_enum_member(
            EntityType,
            "system",
            default=None,
        )

        if result is None:
            raise ValueError(
                "Не знайдено EntityType."
            )

        return result

    @staticmethod
    def resolve_enum_member(
        enum_class: type[EnumType],
        *names: str,
        default: EnumType | None = None,
    ) -> EnumType | None:
        """
        Enum за name/value.
        """

        expected = {
            name.strip().lower()
            for name in names
            if name.strip()
        }

        for item in enum_class:
            values = {
                item.name.lower(),
                str(
                    item.value
                ).lower(),
            }

            if values.intersection(
                expected
            ):
                return item

        return default

    # ==========================================
    # REPOSITORY RESULT
    # ==========================================

    @classmethod
    def extract_ids(
        cls,
        result: Any,
        *,
        field_name: str,
    ) -> set[int]:
        """
        Витягує ID із repository result.
        """

        values = cls.as_list(
            result
        )

        ids: set[int] = set()

        for item in values:
            if isinstance(
                item,
                int,
            ):
                if item > 0:
                    ids.add(
                        item
                    )

                continue

            value = cls.get_int_attribute(
                item,
                field_name,
                "id",
            )

            if value is not None:
                ids.add(
                    value
                )

        return ids

    @staticmethod
    def as_list(
        result: Any,
    ) -> list[Any]:
        """
        Нормалізує значення у list.
        """

        if result is None:
            return []

        if isinstance(
            result,
            list,
        ):
            return result

        if isinstance(
            result,
            tuple,
        ):
            return list(result)

        if isinstance(
            result,
            set,
        ):
            return list(result)

        try:
            return list(
                result
            )

        except TypeError:
            return [
                result
            ]

    # ==========================================
    # METHOD KWARGS
    # ==========================================

    @staticmethod
    def filter_method_kwargs(
        method: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Фільтрує kwargs.
        """

        signature = inspect.signature(
            method
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

    # ==========================================
    # GENERIC ATTRIBUTES
    # ==========================================

    @staticmethod
    def get_attribute(
        target: Any,
        *names: str,
        default: Any = None,
    ) -> Any:
        """
        Читає перший атрибут.
        """

        if target is None:
            return default

        for name in names:
            if hasattr(
                target,
                name,
            ):
                return getattr(
                    target,
                    name,
                )

        return default

    @classmethod
    def get_int_attribute(
        cls,
        target: Any,
        *names: str,
    ) -> int | None:
        """
        Int-атрибут.
        """

        value = cls.get_attribute(
            target,
            *names,
            default=None,
        )

        if value is None:
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

    @classmethod
    def get_text_attribute(
        cls,
        target: Any,
        *names: str,
    ) -> str | None:
        """
        Text-атрибут.
        """

        value = cls.get_attribute(
            target,
            *names,
            default=None,
        )

        if value is None:
            return None

        normalized = str(
            value
        ).strip()

        return (
            normalized
            or None
        )

    @classmethod
    def get_datetime_attribute(
        cls,
        target: Any,
        *names: str,
    ) -> datetime | None:
        """
        Datetime-атрибут.
        """

        value = cls.get_attribute(
            target,
            *names,
            default=None,
        )

        if isinstance(
            value,
            datetime,
        ):
            return value

        return None

    @staticmethod
    def set_first_existing_attribute(
        target: Any,
        value: Any,
        *names: str,
    ) -> bool:
        """
        Записує перший наявний атрибут.
        """

        for name in names:
            if hasattr(
                target,
                name,
            ):
                setattr(
                    target,
                    name,
                    value,
                )

                return True

        return False

    @staticmethod
    def first_model_column(
        *names: str,
    ) -> Any | None:
        """
        Перша колонка User.
        """

        for name in names:
            column = getattr(
                User,
                name,
                None,
            )

            if column is not None:
                return column

        return None

    # ==========================================
    # USER DISPLAY NAME
    # ==========================================

    @classmethod
    def user_display_name(
        cls,
        user: User,
    ) -> str:
        """
        Ім’я користувача.
        """

        first_name = (
            cls.get_text_attribute(
                user,
                "first_name",
            )
        )

        last_name = (
            cls.get_text_attribute(
                user,
                "last_name",
            )
        )

        full_name = " ".join(
            part
            for part in (
                first_name,
                last_name,
            )
            if part
        ).strip()

        if full_name:
            return full_name

        username = (
            cls.get_text_attribute(
                user,
                "telegram_username",
                "username",
            )
        )

        if username:
            return (
                f"@{username.lstrip('@')}"
            )

        telegram_id = (
            cls.get_int_attribute(
                user,
                "telegram_id",
            )
        )

        if telegram_id:
            return (
                f"TG {telegram_id}"
            )

        return (
            f"Користувач #{user.id}"
        )

    # ==========================================
    # STORE
    # ==========================================

    @staticmethod
    def store_number(
        store: Store,
    ) -> int | None:
        """
        Номер ТТ.
        """

        for field_name in (
            "store_number",
            "number",
        ):
            value = getattr(
                store,
                field_name,
                None,
            )

            if value is None:
                continue

            try:
                return int(
                    value
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

        return None

    @classmethod
    def store_code(
        cls,
        store: Store,
    ) -> str:
        """
        Код ТТ.
        """

        code = getattr(
            store,
            "code",
            None,
        )

        if code:
            return str(
                code
            )

        number = cls.store_number(
            store
        )

        if number is not None:
            return (
                f"SB-{number}"
            )

        return (
            f"ТТ-{store.id}"
        )

    # ==========================================
    # BUSH
    # ==========================================

    @classmethod
    def bush_name(
        cls,
        bush: Bush,
    ) -> str:
        """
        Назва куща.
        """

        for field_name in (
            "name",
            "title",
        ):
            value = getattr(
                bush,
                field_name,
                None,
            )

            if value:
                return str(
                    value
                )

        return (
            f"Кущ #{bush.id}"
        )

    # ==========================================
    # SORT
    # ==========================================

    @staticmethod
    def user_order_columns(
    ) -> tuple[Any, ...]:
        """
        Стабільне сортування.
        """

        first_name = getattr(
            User,
            "first_name",
            None,
        )

        last_name = getattr(
            User,
            "last_name",
            None,
        )

        columns: list[Any] = []

        if first_name is not None:
            columns.append(
                first_name.asc()
            )

        if last_name is not None:
            columns.append(
                last_name.asc()
            )

        columns.append(
            User.id.asc()
        )

        return tuple(
            columns
        )

    @staticmethod
    def recent_user_order_columns(
    ) -> tuple[Any, ...]:
        """
        Найновіші користувачі.
        """

        created_at = getattr(
            User,
            "created_at",
            None,
        )

        if created_at is not None:
            return (
                created_at.desc(),
                User.id.desc(),
            )

        return (
            User.id.desc(),
        )

    # ==========================================
    # VALIDATION
    # ==========================================

    def validate_pagination(
        self,
        *,
        limit: int,
        offset: int,
    ) -> None:
        """
        Перевіряє pagination.
        """

        if (
            limit < 1
            or limit > self.MAX_LIMIT
        ):
            raise ValueError(
                "limit повинен бути "
                f"від 1 до {self.MAX_LIMIT}."
            )

        if offset < 0:
            raise ValueError(
                "offset не може бути "
                "від’ємним."
            )

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
        max_length: int,
    ) -> str:
        """
        Обов’язковий текст.
        """

        normalized = " ".join(
            value.strip().split()
        )

        if not normalized:
            raise ValueError(
                f"{field_name} "
                "не може бути порожнім."
            )

        if len(normalized) > max_length:
            raise ValueError(
                f"{field_name} "
                "занадто довгий."
            )

        return normalized

    @staticmethod
    def normalize_optional_text(
        value: str | None,
        *,
        max_length: int,
    ) -> str | None:
        """
        Необов’язковий текст.
        """

        if value is None:
            return None

        normalized = " ".join(
            value.strip().split()
        )

        if not normalized:
            return None

        if len(normalized) > max_length:
            raise ValueError(
                "Текст занадто довгий."
            )

        return normalized

    @staticmethod
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        """
        Перевіряє timezone.
        """

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{field_name} повинен "
                "містити часовий пояс."
            )

    @staticmethod
    def try_int(
        value: Any,
    ) -> int | None:
        """
        Безпечний int.
        """

        try:
            return int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    # ==========================================
    # TELEGRAM PROFILE FORMAT
    # ==========================================

    @classmethod
    def format_profile(
        cls,
        profile: UserProfileView,
    ) -> str:
        """
        Формує профіль для Telegram.
        """

        blocked = (
            "так ❌"
            if profile.is_blocked
            else "ні ✅"
        )

        lines = [
            "👤 <b>Профіль користувача</b>",
            "",
            (
                "Ім’я: "
                f"<b>{escape(profile.full_name)}</b>"
            ),
            (
                "ID у системі: "
                f"<code>{profile.id}</code>"
            ),
        ]

        if profile.telegram_id:
            lines.append(
                "Telegram ID: "
                f"<code>{profile.telegram_id}</code>"
            )

        if profile.username:
            lines.append(
                "Username: "
                f"@{escape(profile.username.lstrip('@'))}"
            )

        lines.extend(
            [
                "",
                (
                    "Роль: "
                    "<b>"
                    f"{escape(cls.role_text(profile.role))}"
                    "</b>"
                ),
                (
                    "Статус: "
                    "<b>"
                    f"{escape(cls.status_text(profile.status))}"
                    "</b>"
                ),
                (
                    "Заблокований: "
                    f"<b>{blocked}</b>"
                ),
            ]
        )

        if profile.primary_store_id:
            lines.extend(
                [
                    "",
                    (
                        "⭐ Основна ТТ: "
                        f"<b>#{profile.primary_store_id}</b>"
                    ),
                ]
            )

        if profile.store_ids:
            lines.append(
                "🏪 Доступних ТТ: "
                f"<b>{len(profile.store_ids)}</b>"
            )

        if profile.bush_ids:
            lines.append(
                "🌿 Доступних кущів: "
                f"<b>{len(profile.bush_ids)}</b>"
            )

        if cls.is_global_role(
            profile.role
        ):
            lines.append(
                "🌐 Доступ: "
                "<b>вся мережа</b>"
            )

        if profile.last_seen_at:
            lines.extend(
                [
                    "",
                    (
                        "🕐 Остання активність: "
                        "<b>"
                        f"{profile.last_seen_at.astimezone().strftime('%d.%m.%Y %H:%M')}"
                        "</b>"
                    ),
                ]
            )

        return "\n".join(
            lines
        )

    # ==========================================
    # LIST FORMAT
    # ==========================================

    @classmethod
    def format_user_list(
        cls,
        users: list[UserListItem]
        | tuple[UserListItem, ...],
        *,
        title: str = "Користувачі",
    ) -> str:
        """
        Формує список користувачів.
        """

        if not users:
            return (
                f"👥 <b>{escape(title)}</b>\n\n"
                "Список порожній."
            )

        lines = [
            (
                f"👥 <b>{escape(title)}</b>"
            ),
            "",
        ]

        for index, user in enumerate(
            users,
            start=1,
        ):
            blocked = (
                " ❌"
                if user.is_blocked
                else ""
            )

            username = (
                f" @{escape(user.username.lstrip('@'))}"
                if user.username
                else ""
            )

            lines.append(
                (
                    f"{index}. "
                    f"<b>{escape(user.display_name)}</b>"
                    f"{username}"
                    f"{blocked}"
                )
            )

            lines.append(
                (
                    "   "
                    f"{escape(cls.role_text(user.role))} · "
                    f"{escape(cls.status_text(user.status))}"
                )
            )

        return "\n".join(
            lines
        )

    # ==========================================
    # STATISTICS FORMAT
    # ==========================================

    @staticmethod
    def format_statistics(
        statistics: UserStatistics,
    ) -> str:
        """
        Статистика для Telegram.
        """

        return "\n".join(
            [
                "👥 <b>Користувачі бота</b>",
                "",
                (
                    "Усього: "
                    f"<b>{statistics.total_users}</b>"
                ),
                (
                    "✅ Активних: "
                    f"<b>{statistics.active_users}</b>"
                ),
                (
                    "🕐 Очікують: "
                    f"<b>{statistics.pending_users}</b>"
                ),
                (
                    "❌ Заблокованих: "
                    f"<b>{statistics.blocked_users}</b>"
                ),
                (
                    "⚫ Неактивних: "
                    f"<b>{statistics.inactive_users}</b>"
                ),
                "",
                (
                    "👑 ROOT ADMIN: "
                    f"<b>{statistics.root_admins}</b>"
                ),
                (
                    "🏢 Директорів: "
                    f"<b>{statistics.directors}</b>"
                ),
                (
                    "🌿 Адмінів куща: "
                    f"<b>{statistics.bush_admins}</b>"
                ),
                (
                    "🦁 Левів: "
                    f"<b>{statistics.lions}</b>"
                ),
                (
                    "🏪 ТТ: "
                    f"<b>{statistics.store_users}</b>"
                ),
            ]
        )


__all__ = [
    "UserService",
    "UserListFilter",
    "UserProfileView",
    "UserListItem",
    "UserSearchResult",
    "UserStatistics",
    "UserRoleUpdateResult",
    "UserStatusUpdateResult",
    "UserProfileUpdateResult",
    "UserAccessView",
    "AdminUsersDashboard",
]