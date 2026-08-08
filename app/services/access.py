from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select

from app.database.models.bush import Bush
from app.database.models.enums import (
    StoreStatus,
    UserRole,
    UserStatus,
)
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories import Repositories


class AccessPermission(StrEnum):
    """
    Доступні системні дозволи.

    Використовуються в handlers і services,
    щоб усі перевірки доступу працювали однаково.
    """

    VIEW_NETWORK = "view_network"
    MANAGE_NETWORK = "manage_network"

    VIEW_BUSH = "view_bush"
    MANAGE_BUSH = "manage_bush"

    VIEW_STORE = "view_store"
    OPERATE_STORE = "operate_store"
    MANAGE_STORE = "manage_store"

    APPROVE_STORE_BINDING = (
        "approve_store_binding"
    )

    MANAGE_STORE_SCHEDULE = (
        "manage_store_schedule"
    )

    MANUALLY_CONFIRM_OPENING = (
        "manually_confirm_opening"
    )

    MANUALLY_CONFIRM_CLOSING = (
        "manually_confirm_closing"
    )

    VIEW_REPORTS = "view_reports"
    EXPORT_REPORTS = "export_reports"

    CREATE_STORE_INVITE = (
        "create_store_invite"
    )

    CREATE_BUSH_INVITE = (
        "create_bush_invite"
    )

    CREATE_DIRECTOR_INVITE = (
        "create_director_invite"
    )

    MANAGE_USERS = "manage_users"
    MANAGE_SETTINGS = "manage_settings"

    VIEW_AUDIT = "view_audit"


class AccessDeniedError(PermissionError):
    """
    Помилка відсутності прав доступу.

    Її зручно перехоплювати окремим middleware
    та показувати користувачу зрозумілий текст.
    """

    def __init__(
        self,
        message: str,
        *,
        permission: AccessPermission | None = None,
    ) -> None:
        super().__init__(message)

        self.permission = permission


@dataclass(slots=True, frozen=True)
class AccessDecision:
    """
    Результат перевірки дозволу.
    """

    allowed: bool
    permission: AccessPermission
    reason: str

    user_id: int | None = None
    store_id: int | None = None
    bush_id: int | None = None

    def raise_if_denied(self) -> None:
        """Викликає AccessDeniedError за відмови."""

        if self.allowed:
            return

        raise AccessDeniedError(
            self.reason,
            permission=self.permission,
        )


@dataclass(slots=True, frozen=True)
class UserAccessScope:
    """
    Повна область видимості користувача.
    """

    user_id: int
    role: UserRole

    has_network_access: bool

    bush_ids: frozenset[int]
    store_ids: frozenset[int]

    @property
    def is_global(self) -> bool:
        return self.has_network_access

    def contains_bush(
        self,
        bush_id: int,
    ) -> bool:
        return (
            self.has_network_access
            or bush_id in self.bush_ids
        )

    def contains_store(
        self,
        store_id: int,
    ) -> bool:
        return (
            self.has_network_access
            or store_id in self.store_ids
        )


class AccessService:
    """
    Центральний сервіс прав доступу.

    Ієрархія:

    ROOT_ADMIN
        Повний доступ до системи.

    DIRECTOR
        Доступ до всієї мережі, крім критичних
        ROOT_ADMIN-налаштувань.

    BUSH_ADMIN
        Управління призначеними кущами та їх ТТ.

    LION
        Перегляд призначених кущів, отримання
        сповіщень і перегляд звітів.

    STORE_USER
        Звичайне відкриття та закриття лише
        прив’язаних торгових точок.
    """

    GLOBAL_ROLES: frozenset[UserRole] = frozenset(
        {
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
        }
    )

    BUSH_VIEW_ROLES: frozenset[
        UserRole
    ] = frozenset(
        {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }
    )

    BUSH_MANAGEMENT_ROLES: frozenset[
        UserRole
    ] = frozenset(
        {
            UserRole.BUSH_ADMIN,
        }
    )

    MANAGEMENT_ROLES: frozenset[
        UserRole
    ] = frozenset(
        {
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
            UserRole.BUSH_ADMIN,
        }
    )

    def __init__(
        self,
        repositories: Repositories,
    ) -> None:
        self.repositories = repositories
        self.session = repositories.session

    # ==========================================
    # БАЗОВІ ПЕРЕВІРКИ КОРИСТУВАЧА
    # ==========================================

    @staticmethod
    def is_root_admin(
        user: User,
    ) -> bool:
        """Чи є користувач ROOT_ADMIN."""

        return user.role == UserRole.ROOT_ADMIN

    @classmethod
    def is_global_manager(
        cls,
        user: User,
    ) -> bool:
        """Чи має користувач доступ до всієї мережі."""

        return user.role in cls.GLOBAL_ROLES

    @staticmethod
    def is_active_user(
        user: User,
    ) -> bool:
        """Чи може користувач працювати з ботом."""

        return (
            user.status == UserStatus.ACTIVE
            and not user.is_blocked
        )

    @classmethod
    def ensure_active_user(
        cls,
        user: User,
    ) -> None:
        """Перевіряє загальний доступ до бота."""

        if user.is_blocked:
            raise AccessDeniedError(
                "Ваш доступ до бота заблоковано."
            )

        if user.status == UserStatus.BLOCKED:
            raise AccessDeniedError(
                "Ваш обліковий запис заблоковано."
            )

        if user.status == UserStatus.PENDING:
            raise AccessDeniedError(
                "Ваш обліковий запис ще очікує "
                "підтвердження."
            )

        if user.status == UserStatus.INACTIVE:
            raise AccessDeniedError(
                "Ваш обліковий запис неактивний."
            )

        if user.status != UserStatus.ACTIVE:
            raise AccessDeniedError(
                "Користувач не має доступу до бота."
            )

    @classmethod
    def ensure_root_admin(
        cls,
        user: User,
    ) -> None:
        """Дозволяє дію лише ROOT_ADMIN."""

        cls.ensure_active_user(user)

        if not cls.is_root_admin(user):
            raise AccessDeniedError(
                "Ця дія доступна лише ROOT_ADMIN.",
                permission=(
                    AccessPermission.MANAGE_SETTINGS
                ),
            )

    # ==========================================
    # ЗАВАНТАЖЕННЯ ОБ’ЄКТІВ
    # ==========================================

    async def get_store_or_raise(
        self,
        store_id: int,
    ) -> Store:
        """Повертає ТТ або викликає помилку."""

        self.validate_positive_id(
            store_id,
            field_name="ID торгової точки",
        )

        store = await self.session.get(
            Store,
            store_id,
        )

        if store is None:
            raise ValueError(
                "Торгову точку не знайдено."
            )

        return store

    async def get_bush_or_raise(
        self,
        bush_id: int,
    ) -> Bush:
        """Повертає кущ або викликає помилку."""

        self.validate_positive_id(
            bush_id,
            field_name="ID куща",
        )

        bush = await self.session.get(
            Bush,
            bush_id,
        )

        if bush is None:
            raise ValueError(
                "Кущ не знайдено."
            )

        return bush

    # ==========================================
    # МЕРЕЖА
    # ==========================================

    def can_view_network(
        self,
        user: User,
    ) -> AccessDecision:
        """Перевіряє перегляд усієї мережі."""

        permission = (
            AccessPermission.VIEW_NETWORK
        )

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
            )

        if self.is_global_manager(user):
            return self.allow(
                permission,
                "Користувач має глобальний доступ.",
                user=user,
            )

        return self.deny(
            permission,
            "Перегляд усієї мережі доступний лише "
            "директору або ROOT_ADMIN.",
            user=user,
        )

    def can_manage_network(
        self,
        user: User,
    ) -> AccessDecision:
        """Перевіряє управління всією мережею."""

        permission = (
            AccessPermission.MANAGE_NETWORK
        )

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
            )

        if self.is_global_manager(user):
            return self.allow(
                permission,
                "Користувач має право керувати мережею.",
                user=user,
            )

        return self.deny(
            permission,
            "Управління всією мережею доступне лише "
            "директору або ROOT_ADMIN.",
            user=user,
        )

    def require_network_view(
        self,
        user: User,
    ) -> None:
        """Вимагає доступ до всієї мережі."""

        self.can_view_network(
            user
        ).raise_if_denied()

    def require_network_management(
        self,
        user: User,
    ) -> None:
        """Вимагає управління мережею."""

        self.can_manage_network(
            user
        ).raise_if_denied()

    # ==========================================
    # КУЩ
    # ==========================================

    async def can_view_bush(
        self,
        user: User,
        bush_id: int,
    ) -> AccessDecision:
        """Перевіряє перегляд конкретного куща."""

        permission = AccessPermission.VIEW_BUSH

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
                bush_id=bush_id,
            )

        if self.is_global_manager(user):
            return self.allow(
                permission,
                "Користувач має глобальний доступ.",
                user=user,
                bush_id=bush_id,
            )

        if user.role not in self.BUSH_VIEW_ROLES:
            return self.deny(
                permission,
                "Користувач не має доступу до кущів.",
                user=user,
                bush_id=bush_id,
            )

        has_access = (
            await self.repositories.bindings
            .user_has_bush_access(
                user_id=user.id,
                bush_id=bush_id,
                roles={user.role},
            )
        )

        if has_access:
            return self.allow(
                permission,
                "Кущ закріплений за користувачем.",
                user=user,
                bush_id=bush_id,
            )

        return self.deny(
            permission,
            "Цей кущ не закріплений за користувачем.",
            user=user,
            bush_id=bush_id,
        )

    async def can_manage_bush(
        self,
        user: User,
        bush_id: int,
    ) -> AccessDecision:
        """Перевіряє управління конкретним кущем."""

        permission = AccessPermission.MANAGE_BUSH

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
                bush_id=bush_id,
            )

        if self.is_global_manager(user):
            return self.allow(
                permission,
                "Користувач має глобальні права.",
                user=user,
                bush_id=bush_id,
            )

        if user.role not in self.BUSH_MANAGEMENT_ROLES:
            return self.deny(
                permission,
                "Керувати кущем може лише його "
                "адміністратор, директор або ROOT_ADMIN.",
                user=user,
                bush_id=bush_id,
            )

        has_access = (
            await self.repositories.bindings
            .user_has_bush_access(
                user_id=user.id,
                bush_id=bush_id,
                roles={
                    UserRole.BUSH_ADMIN,
                },
            )
        )

        if has_access:
            return self.allow(
                permission,
                "Користувач є адміністратором куща.",
                user=user,
                bush_id=bush_id,
            )

        return self.deny(
            permission,
            "Адміністратор не закріплений "
            "за цим кущем.",
            user=user,
            bush_id=bush_id,
        )

    async def require_bush_view(
        self,
        user: User,
        bush_id: int,
    ) -> Bush:
        """Вимагає доступ до перегляду куща."""

        bush = await self.get_bush_or_raise(
            bush_id
        )

        decision = await self.can_view_bush(
            user,
            bush.id,
        )

        decision.raise_if_denied()

        return bush

    async def require_bush_management(
        self,
        user: User,
        bush_id: int,
    ) -> Bush:
        """Вимагає права керування кущем."""

        bush = await self.get_bush_or_raise(
            bush_id
        )

        decision = await self.can_manage_bush(
            user,
            bush.id,
        )

        decision.raise_if_denied()

        return bush

    # ==========================================
    # ПЕРЕГЛЯД ТОРГОВОЇ ТОЧКИ
    # ==========================================

    async def can_view_store(
        self,
        user: User,
        store_id: int,
    ) -> AccessDecision:
        """Перевіряє перегляд конкретної ТТ."""

        permission = AccessPermission.VIEW_STORE

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
                store_id=store_id,
            )

        if self.is_global_manager(user):
            return self.allow(
                permission,
                "Користувач має глобальний доступ.",
                user=user,
                store_id=store_id,
            )

        store = await self.get_store_or_raise(
            store_id
        )

        if (
            user.role in self.BUSH_VIEW_ROLES
            and store.bush_id is not None
        ):
            bush_decision = await self.can_view_bush(
                user,
                store.bush_id,
            )

            if bush_decision.allowed:
                return self.allow(
                    permission,
                    "ТТ належить доступному кущу.",
                    user=user,
                    store_id=store.id,
                    bush_id=store.bush_id,
                )

        has_direct_access = (
            await self.repositories.bindings
            .user_has_store_access(
                user_id=user.id,
                store_id=store.id,
            )
        )

        if has_direct_access:
            return self.allow(
                permission,
                "Користувач прив’язаний до цієї ТТ.",
                user=user,
                store_id=store.id,
                bush_id=store.bush_id,
            )

        return self.deny(
            permission,
            "Користувач не має доступу до цієї ТТ.",
            user=user,
            store_id=store.id,
            bush_id=store.bush_id,
        )

    # ==========================================
    # ЗВИЧАЙНЕ ВІДКРИТТЯ ТА ЗАКРИТТЯ
    # ==========================================

    async def can_operate_store(
        self,
        user: User,
        store_id: int,
    ) -> AccessDecision:
        """
        Перевіряє право натиснути:

        - «Магазин відкрито»;
        - «Закрити магазин»;
        - подати фото чека;
        - ввести суму каси.

        Для звичайної операції потрібна пряма
        підтверджена прив’язка до ТТ.
        """

        permission = (
            AccessPermission.OPERATE_STORE
        )

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
                store_id=store_id,
            )

        store = await self.get_store_or_raise(
            store_id
        )

        if (
            not store.is_active
            or store.status != StoreStatus.ACTIVE
        ):
            return self.deny(
                permission,
                "Торгова точка неактивна або "
                "тимчасово закрита.",
                user=user,
                store_id=store.id,
                bush_id=store.bush_id,
            )

        has_direct_access = (
            await self.repositories.bindings
            .user_has_store_access(
                user_id=user.id,
                store_id=store.id,
            )
        )

        if has_direct_access:
            return self.allow(
                permission,
                "Користувач безпосередньо "
                "прив’язаний до ТТ.",
                user=user,
                store_id=store.id,
                bush_id=store.bush_id,
            )

        return self.deny(
            permission,
            "Підтвердити відкриття або закриття "
            "може лише працівник, прив’язаний до ТТ.",
            user=user,
            store_id=store.id,
            bush_id=store.bush_id,
        )

    async def require_store_operation(
        self,
        user: User,
        store_id: int,
    ) -> Store:
        """Вимагає право відкрити або закрити ТТ."""

        store = await self.get_store_or_raise(
            store_id
        )

        decision = await self.can_operate_store(
            user,
            store.id,
        )

        decision.raise_if_denied()

        return store

    # ==========================================
    # УПРАВЛІННЯ ТОРГОВОЮ ТОЧКОЮ
    # ==========================================

    async def can_manage_store(
        self,
        user: User,
        store_id: int,
    ) -> AccessDecision:
        """Перевіряє управління конкретною ТТ."""

        permission = AccessPermission.MANAGE_STORE

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
                store_id=store_id,
            )

        if self.is_global_manager(user):
            return self.allow(
                permission,
                "Користувач має глобальні права.",
                user=user,
                store_id=store_id,
            )

        store = await self.get_store_or_raise(
            store_id
        )

        if (
            user.role == UserRole.BUSH_ADMIN
            and store.bush_id is not None
        ):
            bush_decision = await self.can_manage_bush(
                user,
                store.bush_id,
            )

            if bush_decision.allowed:
                return self.allow(
                    permission,
                    "Адміністратор керує кущем цієї ТТ.",
                    user=user,
                    store_id=store.id,
                    bush_id=store.bush_id,
                )

        return self.deny(
            permission,
            "Керувати цією ТТ може директор, "
            "ROOT_ADMIN або адміністратор її куща.",
            user=user,
            store_id=store.id,
            bush_id=store.bush_id,
        )

    async def require_store_view(
        self,
        user: User,
        store_id: int,
    ) -> Store:
        """Вимагає право перегляду ТТ."""

        store = await self.get_store_or_raise(
            store_id
        )

        decision = await self.can_view_store(
            user,
            store.id,
        )

        decision.raise_if_denied()

        return store

    async def require_store_management(
        self,
        user: User,
        store_id: int,
    ) -> Store:
        """Вимагає право управління ТТ."""

        store = await self.get_store_or_raise(
            store_id
        )

        decision = await self.can_manage_store(
            user,
            store.id,
        )

        decision.raise_if_denied()

        return store

    # ==========================================
    # ПІДТВЕРДЖЕННЯ ЗАЯВОК
    # ==========================================

    async def can_approve_store_binding(
        self,
        user: User,
        store_id: int,
    ) -> AccessDecision:
        """Перевіряє підтвердження працівника ТТ."""

        permission = (
            AccessPermission.APPROVE_STORE_BINDING
        )

        management_decision = (
            await self.can_manage_store(
                user,
                store_id,
            )
        )

        if management_decision.allowed:
            return self.allow(
                permission,
                "Користувач може підтверджувати "
                "працівників цієї ТТ.",
                user=user,
                store_id=store_id,
                bush_id=(
                    management_decision.bush_id
                ),
            )

        return self.deny(
            permission,
            "Користувач не може підтверджувати "
            "працівників цієї ТТ.",
            user=user,
            store_id=store_id,
            bush_id=management_decision.bush_id,
        )

    async def require_store_binding_approval(
        self,
        user: User,
        store_id: int,
    ) -> Store:
        """Вимагає право підтвердження заявки."""

        store = await self.get_store_or_raise(
            store_id
        )

        decision = (
            await self.can_approve_store_binding(
                user,
                store.id,
            )
        )

        decision.raise_if_denied()

        return store

    # ==========================================
    # ГРАФІКИ
    # ==========================================

    async def can_manage_store_schedule(
        self,
        user: User,
        store_id: int,
    ) -> AccessDecision:
        """Перевіряє зміну графіка ТТ."""

        permission = (
            AccessPermission.MANAGE_STORE_SCHEDULE
        )

        management_decision = (
            await self.can_manage_store(
                user,
                store_id,
            )
        )

        if management_decision.allowed:
            return self.allow(
                permission,
                "Користувач може змінювати "
                "графік цієї ТТ.",
                user=user,
                store_id=store_id,
                bush_id=management_decision.bush_id,
            )

        return self.deny(
            permission,
            "Користувач не має права змінювати "
            "графік цієї ТТ.",
            user=user,
            store_id=store_id,
            bush_id=management_decision.bush_id,
        )

    async def require_schedule_management(
        self,
        user: User,
        store_id: int,
    ) -> Store:
        """Вимагає право зміни графіка."""

        store = await self.get_store_or_raise(
            store_id
        )

        decision = (
            await self.can_manage_store_schedule(
                user,
                store.id,
            )
        )

        decision.raise_if_denied()

        return store

    # ==========================================
    # РУЧНЕ ПІДТВЕРДЖЕННЯ
    # ==========================================

    async def can_manually_confirm_opening(
        self,
        user: User,
        store_id: int,
    ) -> AccessDecision:
        """Перевіряє ручне підтвердження відкриття."""

        permission = (
            AccessPermission.MANUALLY_CONFIRM_OPENING
        )

        management_decision = (
            await self.can_manage_store(
                user,
                store_id,
            )
        )

        if management_decision.allowed:
            return self.allow(
                permission,
                "Користувач може вручну підтвердити "
                "відкриття цієї ТТ.",
                user=user,
                store_id=store_id,
                bush_id=management_decision.bush_id,
            )

        return self.deny(
            permission,
            "Користувач не може вручну підтвердити "
            "відкриття цієї ТТ.",
            user=user,
            store_id=store_id,
            bush_id=management_decision.bush_id,
        )

    async def can_manually_confirm_closing(
        self,
        user: User,
        store_id: int,
    ) -> AccessDecision:
        """Перевіряє ручне підтвердження закриття."""

        permission = (
            AccessPermission.MANUALLY_CONFIRM_CLOSING
        )

        management_decision = (
            await self.can_manage_store(
                user,
                store_id,
            )
        )

        if management_decision.allowed:
            return self.allow(
                permission,
                "Користувач може вручну підтвердити "
                "вечірній звіт.",
                user=user,
                store_id=store_id,
                bush_id=management_decision.bush_id,
            )

        return self.deny(
            permission,
            "Користувач не може вручну підтвердити "
            "вечірній звіт цієї ТТ.",
            user=user,
            store_id=store_id,
            bush_id=management_decision.bush_id,
        )

    # ==========================================
    # ЗВІТИ
    # ==========================================

    async def can_view_bush_reports(
        self,
        user: User,
        bush_id: int,
    ) -> AccessDecision:
        """Перевіряє перегляд звітів куща."""

        permission = AccessPermission.VIEW_REPORTS

        bush_decision = await self.can_view_bush(
            user,
            bush_id,
        )

        if bush_decision.allowed:
            return self.allow(
                permission,
                "Користувач може переглядати "
                "звіти цього куща.",
                user=user,
                bush_id=bush_id,
            )

        return self.deny(
            permission,
            "Користувач не має доступу "
            "до звітів цього куща.",
            user=user,
            bush_id=bush_id,
        )

    async def can_view_store_reports(
        self,
        user: User,
        store_id: int,
    ) -> AccessDecision:
        """Перевіряє перегляд звітів ТТ."""

        permission = AccessPermission.VIEW_REPORTS

        store_decision = await self.can_view_store(
            user,
            store_id,
        )

        if store_decision.allowed:
            return self.allow(
                permission,
                "Користувач може переглядати "
                "звіти цієї ТТ.",
                user=user,
                store_id=store_id,
                bush_id=store_decision.bush_id,
            )

        return self.deny(
            permission,
            "Користувач не має доступу "
            "до звітів цієї ТТ.",
            user=user,
            store_id=store_id,
            bush_id=store_decision.bush_id,
        )

    async def can_export_bush_reports(
        self,
        user: User,
        bush_id: int,
    ) -> AccessDecision:
        """Перевіряє створення Excel-звіту куща."""

        permission = AccessPermission.EXPORT_REPORTS

        management_decision = (
            await self.can_manage_bush(
                user,
                bush_id,
            )
        )

        if management_decision.allowed:
            return self.allow(
                permission,
                "Користувач може експортувати "
                "звіти цього куща.",
                user=user,
                bush_id=bush_id,
            )

        return self.deny(
            permission,
            "Експорт звітів доступний директору, "
            "ROOT_ADMIN або адміністратору куща.",
            user=user,
            bush_id=bush_id,
        )

    def can_view_network_reports(
        self,
        user: User,
    ) -> AccessDecision:
        """Перевіряє загальні звіти мережі."""

        network_decision = self.can_view_network(
            user
        )

        if network_decision.allowed:
            return self.allow(
                AccessPermission.VIEW_REPORTS,
                "Користувач може переглядати "
                "звіти всієї мережі.",
                user=user,
            )

        return self.deny(
            AccessPermission.VIEW_REPORTS,
            "Загальні звіти мережі доступні лише "
            "директору або ROOT_ADMIN.",
            user=user,
        )

    # ==========================================
    # ЗАПРОШЕННЯ
    # ==========================================

    async def can_create_store_invite(
        self,
        user: User,
        store_id: int,
    ) -> AccessDecision:
        """Перевіряє створення посилання для ТТ."""

        permission = (
            AccessPermission.CREATE_STORE_INVITE
        )

        management_decision = (
            await self.can_manage_store(
                user,
                store_id,
            )
        )

        if management_decision.allowed:
            return self.allow(
                permission,
                "Користувач може створювати "
                "запрошення для цієї ТТ.",
                user=user,
                store_id=store_id,
                bush_id=management_decision.bush_id,
            )

        return self.deny(
            permission,
            "Користувач не може створити "
            "запрошення для цієї ТТ.",
            user=user,
            store_id=store_id,
            bush_id=management_decision.bush_id,
        )

    async def can_create_bush_invite(
        self,
        user: User,
        *,
        bush_id: int,
        target_role: UserRole,
    ) -> AccessDecision:
        """Перевіряє запрошення адміністратора або лева."""

        permission = (
            AccessPermission.CREATE_BUSH_INVITE
        )

        if target_role not in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            return self.deny(
                permission,
                "Некоректна роль запрошення.",
                user=user,
                bush_id=bush_id,
            )

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
                bush_id=bush_id,
            )

        if self.is_global_manager(user):
            return self.allow(
                permission,
                "Користувач має глобальні права.",
                user=user,
                bush_id=bush_id,
            )

        if (
            user.role == UserRole.BUSH_ADMIN
            and target_role == UserRole.LION
        ):
            management_decision = (
                await self.can_manage_bush(
                    user,
                    bush_id,
                )
            )

            if management_decision.allowed:
                return self.allow(
                    permission,
                    "Адміністратор може запросити "
                    "лева у свій кущ.",
                    user=user,
                    bush_id=bush_id,
                )

        return self.deny(
            permission,
            "Запросити адміністратора куща може "
            "директор або ROOT_ADMIN. Адміністратор "
            "може запросити лише лева у свій кущ.",
            user=user,
            bush_id=bush_id,
        )

    def can_create_director_invite(
        self,
        user: User,
    ) -> AccessDecision:
        """Перевіряє створення запрошення директора."""

        permission = (
            AccessPermission.CREATE_DIRECTOR_INVITE
        )

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
            )

        if self.is_root_admin(user):
            return self.allow(
                permission,
                "ROOT_ADMIN може запросити директора.",
                user=user,
            )

        return self.deny(
            permission,
            "Запросити директора може лише ROOT_ADMIN.",
            user=user,
        )

    # ==========================================
    # КЕРУВАННЯ РОЛЯМИ
    # ==========================================

    async def can_assign_role(
        self,
        user: User,
        *,
        target_role: UserRole,
        bush_id: int | None = None,
    ) -> AccessDecision:
        """Перевіряє призначення ролі."""

        permission = AccessPermission.MANAGE_USERS

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
                bush_id=bush_id,
            )

        if target_role == UserRole.ROOT_ADMIN:
            return self.deny(
                permission,
                "Роль ROOT_ADMIN не можна "
                "призначити через Telegram-бота.",
                user=user,
                bush_id=bush_id,
            )

        if self.is_root_admin(user):
            return self.allow(
                permission,
                "ROOT_ADMIN може призначити цю роль.",
                user=user,
                bush_id=bush_id,
            )

        if user.role == UserRole.DIRECTOR:
            if target_role in {
                UserRole.BUSH_ADMIN,
                UserRole.LION,
                UserRole.STORE_USER,
            }:
                return self.allow(
                    permission,
                    "Директор може призначити цю роль.",
                    user=user,
                    bush_id=bush_id,
                )

        if user.role == UserRole.BUSH_ADMIN:
            if bush_id is None:
                return self.deny(
                    permission,
                    "Для призначення ролі потрібно "
                    "вказати кущ.",
                    user=user,
                )

            if target_role not in {
                UserRole.LION,
                UserRole.STORE_USER,
            }:
                return self.deny(
                    permission,
                    "Адміністратор куща може "
                    "призначати лише лева або "
                    "працівника ТТ.",
                    user=user,
                    bush_id=bush_id,
                )

            management_decision = (
                await self.can_manage_bush(
                    user,
                    bush_id,
                )
            )

            if management_decision.allowed:
                return self.allow(
                    permission,
                    "Адміністратор може призначити "
                    "роль у своєму кущі.",
                    user=user,
                    bush_id=bush_id,
                )

        return self.deny(
            permission,
            "Користувач не має права "
            "призначати цю роль.",
            user=user,
            bush_id=bush_id,
        )

    async def can_manage_target_user(
        self,
        actor: User,
        target: User,
        *,
        bush_id: int | None = None,
    ) -> AccessDecision:
        """
        Перевіряє блокування, деактивацію
        або зміну ролі користувача.
        """

        permission = AccessPermission.MANAGE_USERS

        if actor.id == target.id:
            return self.deny(
                permission,
                "Не можна виконувати цю дію "
                "зі своїм обліковим записом.",
                user=actor,
                bush_id=bush_id,
            )

        if not self.is_active_user(actor):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=actor,
                bush_id=bush_id,
            )

        if target.role == UserRole.ROOT_ADMIN:
            return self.deny(
                permission,
                "Обліковим записом ROOT_ADMIN "
                "не можна керувати через бота.",
                user=actor,
                bush_id=bush_id,
            )

        if self.is_root_admin(actor):
            return self.allow(
                permission,
                "ROOT_ADMIN може керувати користувачем.",
                user=actor,
                bush_id=bush_id,
            )

        if actor.role == UserRole.DIRECTOR:
            if target.role != UserRole.DIRECTOR:
                return self.allow(
                    permission,
                    "Директор може керувати "
                    "підлеглим користувачем.",
                    user=actor,
                    bush_id=bush_id,
                )

            return self.deny(
                permission,
                "Директор не може керувати "
                "іншим директором.",
                user=actor,
                bush_id=bush_id,
            )

        if actor.role == UserRole.BUSH_ADMIN:
            if target.role not in {
                UserRole.LION,
                UserRole.STORE_USER,
            }:
                return self.deny(
                    permission,
                    "Адміністратор куща може "
                    "керувати лише левами та "
                    "працівниками ТТ.",
                    user=actor,
                    bush_id=bush_id,
                )

            if bush_id is None:
                return self.deny(
                    permission,
                    "Для перевірки потрібно "
                    "вказати кущ користувача.",
                    user=actor,
                )

            management_decision = (
                await self.can_manage_bush(
                    actor,
                    bush_id,
                )
            )

            if management_decision.allowed:
                return self.allow(
                    permission,
                    "Користувач належить до куща "
                    "цього адміністратора.",
                    user=actor,
                    bush_id=bush_id,
                )

        return self.deny(
            permission,
            "Користувач не має права керувати "
            "цим обліковим записом.",
            user=actor,
            bush_id=bush_id,
        )

    # ==========================================
    # СИСТЕМНІ НАЛАШТУВАННЯ
    # ==========================================

    def can_manage_settings(
        self,
        user: User,
    ) -> AccessDecision:
        """Перевіряє системні налаштування."""

        permission = (
            AccessPermission.MANAGE_SETTINGS
        )

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
            )

        if self.is_root_admin(user):
            return self.allow(
                permission,
                "ROOT_ADMIN має доступ "
                "до системних налаштувань.",
                user=user,
            )

        return self.deny(
            permission,
            "Системні налаштування доступні "
            "лише ROOT_ADMIN.",
            user=user,
        )

    def require_settings_management(
        self,
        user: User,
    ) -> None:
        """Вимагає доступ до налаштувань."""

        self.can_manage_settings(
            user
        ).raise_if_denied()

    # ==========================================
    # AUDIT LOG
    # ==========================================

    async def can_view_audit(
        self,
        user: User,
        *,
        bush_id: int | None = None,
    ) -> AccessDecision:
        """Перевіряє перегляд журналу дій."""

        permission = AccessPermission.VIEW_AUDIT

        if not self.is_active_user(user):
            return self.deny(
                permission,
                "Користувач неактивний або заблокований.",
                user=user,
                bush_id=bush_id,
            )

        if self.is_global_manager(user):
            return self.allow(
                permission,
                "Користувач може переглядати "
                "повний журнал дій.",
                user=user,
                bush_id=bush_id,
            )

        if (
            user.role == UserRole.BUSH_ADMIN
            and bush_id is not None
        ):
            management_decision = (
                await self.can_manage_bush(
                    user,
                    bush_id,
                )
            )

            if management_decision.allowed:
                return self.allow(
                    permission,
                    "Адміністратор може переглядати "
                    "журнал свого куща.",
                    user=user,
                    bush_id=bush_id,
                )

        return self.deny(
            permission,
            "Користувач не має доступу "
            "до журналу дій.",
            user=user,
            bush_id=bush_id,
        )

    # ==========================================
    # ОБЛАСТЬ ВИДИМОСТІ
    # ==========================================

    async def get_access_scope(
        self,
        user: User,
        *,
        active_only: bool = True,
    ) -> UserAccessScope:
        """Повертає всі доступні кущі та ТТ."""

        self.ensure_active_user(user)

        if self.is_global_manager(user):
            bush_conditions = []

            if active_only:
                bush_conditions.append(
                    Bush.is_active.is_(True)
                )

            bush_statement = (
                select(Bush.id)
                .where(*bush_conditions)
                .order_by(Bush.id.asc())
            )

            bush_result = await self.session.scalars(
                bush_statement
            )

            store_conditions = []

            if active_only:
                store_conditions.extend(
                    [
                        Store.is_active.is_(True),
                        Store.status
                        == StoreStatus.ACTIVE,
                    ]
                )

            store_statement = (
                select(Store.id)
                .where(*store_conditions)
                .order_by(Store.id.asc())
            )

            store_result = await self.session.scalars(
                store_statement
            )

            return UserAccessScope(
                user_id=user.id,
                role=user.role,
                has_network_access=True,
                bush_ids=frozenset(
                    int(item)
                    for item in bush_result.all()
                ),
                store_ids=frozenset(
                    int(item)
                    for item in store_result.all()
                ),
            )

        bush_ids: set[int] = set()
        store_ids: set[int] = set()

        if user.role in self.BUSH_VIEW_ROLES:
            bushes = (
                await self.repositories.bindings
                .get_bushes_for_user(
                    user.id,
                    role=user.role,
                    active_only=active_only,
                )
            )

            bush_ids.update(
                bush.id
                for bush in bushes
            )

            if bush_ids:
                store_conditions = [
                    Store.bush_id.in_(bush_ids),
                ]

                if active_only:
                    store_conditions.extend(
                        [
                            Store.is_active.is_(True),
                            Store.status
                            == StoreStatus.ACTIVE,
                        ]
                    )

                store_statement = (
                    select(Store.id)
                    .where(*store_conditions)
                )

                store_result = (
                    await self.session.scalars(
                        store_statement
                    )
                )

                store_ids.update(
                    int(item)
                    for item in store_result.all()
                )

        directly_bound_stores = (
            await self.repositories.bindings
            .get_stores_for_user(
                user.id,
                controlled_only=active_only,
            )
        )

        store_ids.update(
            store.id
            for store in directly_bound_stores
        )

        for store in directly_bound_stores:
            if store.bush_id is not None:
                bush_ids.add(store.bush_id)

        return UserAccessScope(
            user_id=user.id,
            role=user.role,
            has_network_access=False,
            bush_ids=frozenset(bush_ids),
            store_ids=frozenset(store_ids),
        )

    async def get_visible_store_ids(
        self,
        user: User,
        *,
        active_only: bool = True,
    ) -> set[int]:
        """Повертає ID усіх доступних ТТ."""

        scope = await self.get_access_scope(
            user,
            active_only=active_only,
        )

        return set(scope.store_ids)

    async def get_visible_bush_ids(
        self,
        user: User,
        *,
        active_only: bool = True,
    ) -> set[int]:
        """Повертає ID усіх доступних кущів."""

        scope = await self.get_access_scope(
            user,
            active_only=active_only,
        )

        return set(scope.bush_ids)

    async def filter_visible_stores(
        self,
        user: User,
        stores: Iterable[Store],
        *,
        active_only: bool = True,
    ) -> list[Store]:
        """Залишає лише доступні користувачу ТТ."""

        scope = await self.get_access_scope(
            user,
            active_only=active_only,
        )

        if scope.has_network_access:
            return [
                store
                for store in stores
                if (
                    not active_only
                    or (
                        store.is_active
                        and store.status
                        == StoreStatus.ACTIVE
                    )
                )
            ]

        return [
            store
            for store in stores
            if store.id in scope.store_ids
        ]

    # ==========================================
    # УНІВЕРСАЛЬНА ПЕРЕВІРКА
    # ==========================================

    async def check_permission(
        self,
        user: User,
        permission: AccessPermission,
        *,
        store_id: int | None = None,
        bush_id: int | None = None,
        target_role: UserRole | None = None,
    ) -> AccessDecision:
        """Універсальна перевірка дозволу."""

        if permission == AccessPermission.VIEW_NETWORK:
            return self.can_view_network(user)

        if permission == AccessPermission.MANAGE_NETWORK:
            return self.can_manage_network(user)

        if permission == AccessPermission.VIEW_BUSH:
            self.require_scope_id(
                bush_id,
                name="bush_id",
            )

            return await self.can_view_bush(
                user,
                int(bush_id),
            )

        if permission == AccessPermission.MANAGE_BUSH:
            self.require_scope_id(
                bush_id,
                name="bush_id",
            )

            return await self.can_manage_bush(
                user,
                int(bush_id),
            )

        if permission == AccessPermission.VIEW_STORE:
            self.require_scope_id(
                store_id,
                name="store_id",
            )

            return await self.can_view_store(
                user,
                int(store_id),
            )

        if permission == AccessPermission.OPERATE_STORE:
            self.require_scope_id(
                store_id,
                name="store_id",
            )

            return await self.can_operate_store(
                user,
                int(store_id),
            )

        if permission == AccessPermission.MANAGE_STORE:
            self.require_scope_id(
                store_id,
                name="store_id",
            )

            return await self.can_manage_store(
                user,
                int(store_id),
            )

        if (
            permission
            == AccessPermission.APPROVE_STORE_BINDING
        ):
            self.require_scope_id(
                store_id,
                name="store_id",
            )

            return await self.can_approve_store_binding(
                user,
                int(store_id),
            )

        if (
            permission
            == AccessPermission.MANAGE_STORE_SCHEDULE
        ):
            self.require_scope_id(
                store_id,
                name="store_id",
            )

            return await self.can_manage_store_schedule(
                user,
                int(store_id),
            )

        if (
            permission
            == AccessPermission.MANUALLY_CONFIRM_OPENING
        ):
            self.require_scope_id(
                store_id,
                name="store_id",
            )

            return await self.can_manually_confirm_opening(
                user,
                int(store_id),
            )

        if (
            permission
            == AccessPermission.MANUALLY_CONFIRM_CLOSING
        ):
            self.require_scope_id(
                store_id,
                name="store_id",
            )

            return await self.can_manually_confirm_closing(
                user,
                int(store_id),
            )

        if permission == AccessPermission.CREATE_STORE_INVITE:
            self.require_scope_id(
                store_id,
                name="store_id",
            )

            return await self.can_create_store_invite(
                user,
                int(store_id),
            )

        if permission == AccessPermission.CREATE_BUSH_INVITE:
            self.require_scope_id(
                bush_id,
                name="bush_id",
            )

            if target_role is None:
                raise ValueError(
                    "Для створення запрошення "
                    "потрібно вказати target_role."
                )

            return await self.can_create_bush_invite(
                user,
                bush_id=int(bush_id),
                target_role=target_role,
            )

        if (
            permission
            == AccessPermission.CREATE_DIRECTOR_INVITE
        ):
            return self.can_create_director_invite(
                user
            )

        if permission == AccessPermission.MANAGE_SETTINGS:
            return self.can_manage_settings(user)

        if permission == AccessPermission.VIEW_AUDIT:
            return await self.can_view_audit(
                user,
                bush_id=bush_id,
            )

        if permission == AccessPermission.VIEW_REPORTS:
            if store_id is not None:
                return await self.can_view_store_reports(
                    user,
                    store_id,
                )

            if bush_id is not None:
                return await self.can_view_bush_reports(
                    user,
                    bush_id,
                )

            return self.can_view_network_reports(
                user
            )

        if permission == AccessPermission.EXPORT_REPORTS:
            if bush_id is not None:
                return await self.can_export_bush_reports(
                    user,
                    bush_id,
                )

            network_decision = self.can_view_network(
                user
            )

            if network_decision.allowed:
                return self.allow(
                    permission,
                    "Користувач може експортувати "
                    "звіти всієї мережі.",
                    user=user,
                )

            return self.deny(
                permission,
                "Користувач не має права "
                "експортувати цей звіт.",
                user=user,
            )

        return self.deny(
            permission,
            "Перевірка цього дозволу "
            "ще не реалізована.",
            user=user,
            store_id=store_id,
            bush_id=bush_id,
        )

    async def require_permission(
        self,
        user: User,
        permission: AccessPermission,
        *,
        store_id: int | None = None,
        bush_id: int | None = None,
        target_role: UserRole | None = None,
    ) -> AccessDecision:
        """Перевіряє дозвіл або викликає помилку."""

        decision = await self.check_permission(
            user,
            permission,
            store_id=store_id,
            bush_id=bush_id,
            target_role=target_role,
        )

        decision.raise_if_denied()

        return decision

    # ==========================================
    # ФОРМУВАННЯ РІШЕННЯ
    # ==========================================

    @staticmethod
    def allow(
        permission: AccessPermission,
        reason: str,
        *,
        user: User,
        store_id: int | None = None,
        bush_id: int | None = None,
    ) -> AccessDecision:
        """Формує позитивне рішення."""

        return AccessDecision(
            allowed=True,
            permission=permission,
            reason=reason,
            user_id=user.id,
            store_id=store_id,
            bush_id=bush_id,
        )

    @staticmethod
    def deny(
        permission: AccessPermission,
        reason: str,
        *,
        user: User,
        store_id: int | None = None,
        bush_id: int | None = None,
    ) -> AccessDecision:
        """Формує відмову."""

        return AccessDecision(
            allowed=False,
            permission=permission,
            reason=reason,
            user_id=user.id,
            store_id=store_id,
            bush_id=bush_id,
        )

    # ==========================================
    # ВАЛІДАЦІЯ
    # ==========================================

    @staticmethod
    def validate_positive_id(
        value: int,
        *,
        field_name: str,
    ) -> None:
        """Перевіряє внутрішній ID."""

        if value <= 0:
            raise ValueError(
                f"{field_name} повинен бути "
                "більшим за нуль."
            )

    @staticmethod
    def require_scope_id(
        value: int | None,
        *,
        name: str,
    ) -> None:
        """Перевіряє обов’язковий ID області."""

        if value is None:
            raise ValueError(
                f"Для перевірки дозволу "
                f"потрібно вказати {name}."
            )

        if value <= 0:
            raise ValueError(
                f"{name} повинен бути "
                "більшим за нуль."
            )