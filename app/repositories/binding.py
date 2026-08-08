from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models.binding import (
    UserBushBinding,
    UserStoreBinding,
)
from app.database.models.bush import Bush
from app.database.models.enums import (
    BindingStatus,
    StoreStatus,
    UserRole,
    UserStatus,
)
from app.database.models.store import Store
from app.database.models.user import User


class BindingRepository:
    """
    Репозиторій прив’язок користувачів.

    Містить два типи прив’язок:

    1. UserStoreBinding:
       працівник прив’язується до конкретної ТТ.

    2. UserBushBinding:
       адміністратор або лев прив’язується до куща.

    Commit виконується у сервісі або handler.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    # ==========================================
    # ПРИВ’ЯЗКИ КОРИСТУВАЧІВ ДО ТТ
    # ==========================================

    async def get_store_binding(
        self,
        *,
        user_id: int,
        store_id: int,
        for_update: bool = False,
    ) -> UserStoreBinding | None:
        """Повертає прив’язку користувача до ТТ."""

        statement = (
            select(UserStoreBinding)
            .options(
                selectinload(
                    UserStoreBinding.user
                ),
                selectinload(
                    UserStoreBinding.store
                ),
            )
            .where(
                UserStoreBinding.user_id == user_id,
                UserStoreBinding.store_id == store_id,
            )
            .limit(1)
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_store_binding_by_id(
        self,
        binding_id: int,
        *,
        for_update: bool = False,
    ) -> UserStoreBinding | None:
        """Повертає прив’язку до ТТ за ID."""

        statement = (
            select(UserStoreBinding)
            .options(
                selectinload(
                    UserStoreBinding.user
                ),
                selectinload(
                    UserStoreBinding.store
                ),
            )
            .where(
                UserStoreBinding.id == binding_id
            )
            .limit(1)
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_store_binding_by_id_or_raise(
        self,
        binding_id: int,
        *,
        for_update: bool = False,
    ) -> UserStoreBinding:
        """Повертає прив’язку або викликає помилку."""

        binding = await self.get_store_binding_by_id(
            binding_id,
            for_update=for_update,
        )

        if binding is None:
            raise ValueError(
                "Заявку на прив’язку до ТТ не знайдено."
            )

        return binding

    async def create_store_request(
        self,
        *,
        user_id: int,
        store_id: int,
        requested_at: datetime,
    ) -> tuple[UserStoreBinding, bool]:
        """
        Створює заявку користувача на конкретну ТТ.

        Повертає:
        - прив’язку;
        - True, якщо створено новий запис;
        - False, якщо використано попередній запис.
        """

        self.validate_positive_id(
            user_id,
            field_name="ID користувача",
        )

        self.validate_positive_id(
            store_id,
            field_name="ID торгової точки",
        )

        self.validate_aware_datetime(
            requested_at,
            field_name="requested_at",
        )

        existing_binding = await self.get_store_binding(
            user_id=user_id,
            store_id=store_id,
            for_update=True,
        )

        if existing_binding is not None:
            if (
                existing_binding.status
                == BindingStatus.APPROVED
            ):
                raise ValueError(
                    "Користувач уже прив’язаний "
                    "до цієї торгової точки."
                )

            if (
                existing_binding.status
                == BindingStatus.PENDING
            ):
                return existing_binding, False

            existing_binding.reopen(
                requested_at=requested_at
            )

            self.session.add(existing_binding)
            await self.session.flush()

            return existing_binding, False

        binding = UserStoreBinding(
            user_id=user_id,
            store_id=store_id,
            status=BindingStatus.PENDING,
            requested_at=requested_at,
        )

        self.session.add(binding)
        await self.session.flush()

        return binding, True

    async def approve_store_binding(
        self,
        binding: UserStoreBinding,
        *,
        approved_by_id: int,
        approved_at: datetime,
        activate_user: bool = True,
    ) -> UserStoreBinding:
        """Підтверджує прив’язку користувача до ТТ."""

        self.validate_aware_datetime(
            approved_at,
            field_name="approved_at",
        )

        if (
            binding.status
            == BindingStatus.APPROVED
        ):
            raise ValueError(
                "Цю прив’язку вже підтверджено."
            )

        binding.approve(
            approved_by_id=approved_by_id,
            approved_at=approved_at,
        )

        if activate_user:
            user = await self.session.get(
                User,
                binding.user_id,
            )

            if user is not None:
                if user.role not in {
                    UserRole.ROOT_ADMIN,
                    UserRole.DIRECTOR,
                    UserRole.BUSH_ADMIN,
                    UserRole.LION,
                }:
                    user.role = UserRole.STORE_USER

                user.status = UserStatus.ACTIVE
                user.is_blocked = False
                user.blocked_at = None
                user.blocked_reason = None

                self.session.add(user)

        self.session.add(binding)
        await self.session.flush()

        return binding

    async def reject_store_binding(
        self,
        binding: UserStoreBinding,
        *,
        rejected_by_id: int,
        rejected_at: datetime,
        reason: str,
    ) -> UserStoreBinding:
        """Відхиляє заявку на прив’язку до ТТ."""

        self.validate_aware_datetime(
            rejected_at,
            field_name="rejected_at",
        )

        normalized_reason = self.normalize_reason(
            reason
        )

        binding.reject(
            rejected_by_id=rejected_by_id,
            rejected_at=rejected_at,
            reason=normalized_reason,
        )

        self.session.add(binding)
        await self.session.flush()

        return binding

    async def revoke_store_binding(
        self,
        binding: UserStoreBinding,
        *,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str,
    ) -> UserStoreBinding:
        """Відкликає доступ користувача до ТТ."""

        self.validate_aware_datetime(
            revoked_at,
            field_name="revoked_at",
        )

        normalized_reason = self.normalize_reason(
            reason
        )

        binding.revoke(
            revoked_by_id=revoked_by_id,
            revoked_at=revoked_at,
            reason=normalized_reason,
        )

        self.session.add(binding)
        await self.session.flush()

        return binding

    async def reopen_store_binding(
        self,
        binding: UserStoreBinding,
        *,
        requested_at: datetime,
    ) -> UserStoreBinding:
        """Повторно відкриває заявку користувача."""

        self.validate_aware_datetime(
            requested_at,
            field_name="requested_at",
        )

        if (
            binding.status
            == BindingStatus.APPROVED
        ):
            raise ValueError(
                "Підтверджену прив’язку не потрібно "
                "відкривати повторно."
            )

        binding.reopen(
            requested_at=requested_at
        )

        self.session.add(binding)
        await self.session.flush()

        return binding

    # ==========================================
    # ЗАЯВКИ НА ПІДТВЕРДЖЕННЯ
    # ==========================================

    async def get_pending_store_bindings(
        self,
        *,
        store_id: int | None = None,
        bush_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[UserStoreBinding]:
        """
        Повертає заявки, які очікують підтвердження.

        Можна обмежити:
        - конкретною ТТ;
        - конкретним кущем.
        """

        if offset < 0:
            raise ValueError(
                "Offset не може бути від’ємним."
            )

        conditions = [
            UserStoreBinding.status
            == BindingStatus.PENDING,
        ]

        if store_id is not None:
            conditions.append(
                UserStoreBinding.store_id
                == store_id
            )

        statement = (
            select(UserStoreBinding)
            .options(
                selectinload(
                    UserStoreBinding.user
                ),
                selectinload(
                    UserStoreBinding.store
                ),
            )
            .join(
                Store,
                Store.id
                == UserStoreBinding.store_id,
            )
            .where(*conditions)
        )

        if bush_id is not None:
            statement = statement.where(
                Store.bush_id == bush_id
            )

        statement = (
            statement
            .order_by(
                UserStoreBinding.requested_at.asc(),
                UserStoreBinding.id.asc(),
            )
            .offset(offset)
        )

        if limit is not None:
            if limit <= 0 or limit > 500:
                raise ValueError(
                    "Limit повинен бути від 1 до 500."
                )

            statement = statement.limit(limit)

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def count_pending_store_bindings(
        self,
        *,
        store_id: int | None = None,
        bush_id: int | None = None,
    ) -> int:
        """Підраховує заявки на прив’язку до ТТ."""

        conditions = [
            UserStoreBinding.status
            == BindingStatus.PENDING,
        ]

        statement = (
            select(
                func.count(
                    UserStoreBinding.id
                )
            )
            .select_from(UserStoreBinding)
            .join(
                Store,
                Store.id
                == UserStoreBinding.store_id,
            )
            .where(*conditions)
        )

        if store_id is not None:
            statement = statement.where(
                UserStoreBinding.store_id
                == store_id
            )

        if bush_id is not None:
            statement = statement.where(
                Store.bush_id == bush_id
            )

        result = await self.session.scalar(
            statement
        )

        return int(result or 0)

    # ==========================================
    # ТТ КОРИСТУВАЧА
    # ==========================================

    async def get_store_bindings_for_user(
        self,
        user_id: int,
        *,
        approved_only: bool = True,
    ) -> list[UserStoreBinding]:
        """Повертає прив’язки користувача до ТТ."""

        conditions = [
            UserStoreBinding.user_id == user_id,
        ]

        if approved_only:
            conditions.append(
                UserStoreBinding.status
                == BindingStatus.APPROVED
            )

        statement = (
            select(UserStoreBinding)
            .options(
                selectinload(
                    UserStoreBinding.store
                ),
            )
            .where(*conditions)
            .order_by(
                UserStoreBinding.id.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_stores_for_user(
        self,
        user_id: int,
        *,
        controlled_only: bool = True,
    ) -> list[Store]:
        """Повертає ТТ, доступні користувачу."""

        conditions = [
            UserStoreBinding.user_id == user_id,
            UserStoreBinding.status
            == BindingStatus.APPROVED,
        ]

        if controlled_only:
            conditions.extend(
                [
                    Store.is_active.is_(True),
                    Store.status == StoreStatus.ACTIVE,
                ]
            )

        statement = (
            select(Store)
            .join(
                UserStoreBinding,
                UserStoreBinding.store_id
                == Store.id,
            )
            .where(*conditions)
            .order_by(
                Store.store_number.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_users_for_store(
        self,
        store_id: int,
        *,
        active_only: bool = True,
    ) -> list[User]:
        """Повертає користувачів конкретної ТТ."""

        conditions = [
            UserStoreBinding.store_id == store_id,
            UserStoreBinding.status
            == BindingStatus.APPROVED,
        ]

        if active_only:
            conditions.extend(
                [
                    User.status == UserStatus.ACTIVE,
                    User.is_blocked.is_(False),
                ]
            )

        statement = (
            select(User)
            .join(
                UserStoreBinding,
                UserStoreBinding.user_id
                == User.id,
            )
            .where(*conditions)
            .order_by(
                User.full_name.asc(),
                User.id.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def user_has_store_access(
        self,
        *,
        user_id: int,
        store_id: int,
    ) -> bool:
        """Перевіряє доступ користувача до конкретної ТТ."""

        statement = select(
            select(UserStoreBinding.id)
            .where(
                UserStoreBinding.user_id == user_id,
                UserStoreBinding.store_id == store_id,
                UserStoreBinding.status
                == BindingStatus.APPROVED,
            )
            .exists()
        )

        result = await self.session.scalar(
            statement
        )

        return bool(result)

    async def user_has_any_store_access(
        self,
        user_id: int,
    ) -> bool:
        """Чи має користувач хоча б одну активну ТТ."""

        statement = select(
            select(UserStoreBinding.id)
            .join(
                Store,
                Store.id
                == UserStoreBinding.store_id,
            )
            .where(
                UserStoreBinding.user_id == user_id,
                UserStoreBinding.status
                == BindingStatus.APPROVED,
                Store.is_active.is_(True),
                Store.status == StoreStatus.ACTIVE,
            )
            .exists()
        )

        result = await self.session.scalar(
            statement
        )

        return bool(result)

    # ==========================================
    # МАСОВЕ ВІДКЛИКАННЯ ДОСТУПУ ДО ТТ
    # ==========================================

    async def revoke_all_store_bindings(
        self,
        *,
        store_id: int,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str,
    ) -> list[UserStoreBinding]:
        """Відкликає всі активні прив’язки до ТТ."""

        normalized_reason = self.normalize_reason(
            reason
        )

        self.validate_aware_datetime(
            revoked_at,
            field_name="revoked_at",
        )

        statement = (
            select(UserStoreBinding)
            .where(
                UserStoreBinding.store_id == store_id,
                UserStoreBinding.status.in_(
                    {
                        BindingStatus.PENDING,
                        BindingStatus.APPROVED,
                    }
                ),
            )
            .with_for_update()
        )

        result = await self.session.scalars(
            statement
        )

        bindings = list(
            result.unique().all()
        )

        for binding in bindings:
            binding.revoke(
                revoked_by_id=revoked_by_id,
                revoked_at=revoked_at,
                reason=normalized_reason,
            )

            self.session.add(binding)

        if bindings:
            await self.session.flush()

        return bindings

    # ==========================================
    # ПРИВ’ЯЗКИ ДО КУЩІВ
    # ==========================================

    async def get_bush_binding(
        self,
        *,
        user_id: int,
        bush_id: int,
        role: UserRole,
        for_update: bool = False,
    ) -> UserBushBinding | None:
        """Повертає управлінську прив’язку до куща."""

        self.validate_bush_role(role)

        statement = (
            select(UserBushBinding)
            .options(
                selectinload(
                    UserBushBinding.user
                ),
                selectinload(
                    UserBushBinding.bush
                ),
            )
            .where(
                UserBushBinding.user_id == user_id,
                UserBushBinding.bush_id == bush_id,
                UserBushBinding.role == role,
            )
            .limit(1)
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_bush_binding_by_id(
        self,
        binding_id: int,
        *,
        for_update: bool = False,
    ) -> UserBushBinding | None:
        """Повертає прив’язку до куща за ID."""

        statement = (
            select(UserBushBinding)
            .options(
                selectinload(
                    UserBushBinding.user
                ),
                selectinload(
                    UserBushBinding.bush
                ),
            )
            .where(
                UserBushBinding.id == binding_id
            )
            .limit(1)
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_bush_binding_by_id_or_raise(
        self,
        binding_id: int,
        *,
        for_update: bool = False,
    ) -> UserBushBinding:
        """Повертає управлінську прив’язку або помилку."""

        binding = await self.get_bush_binding_by_id(
            binding_id,
            for_update=for_update,
        )

        if binding is None:
            raise ValueError(
                "Прив’язку до куща не знайдено."
            )

        return binding

    async def assign_bush_role(
        self,
        *,
        user_id: int,
        bush_id: int,
        role: UserRole,
        assigned_by_id: int,
        assigned_at: datetime,
    ) -> tuple[UserBushBinding, bool]:
        """
        Призначає адміністратора або лева на кущ.

        Повертає:
        - прив’язку;
        - True, якщо створено новий запис;
        - False, якщо відновлено старий.
        """

        self.validate_bush_role(role)

        self.validate_aware_datetime(
            assigned_at,
            field_name="assigned_at",
        )

        existing_binding = await self.get_bush_binding(
            user_id=user_id,
            bush_id=bush_id,
            role=role,
            for_update=True,
        )

        if existing_binding is not None:
            if (
                existing_binding.status
                == BindingStatus.APPROVED
            ):
                raise ValueError(
                    "Користувач уже має цю роль "
                    "у вибраному кущі."
                )

            existing_binding.restore(
                assigned_by_id=assigned_by_id,
                assigned_at=assigned_at,
            )

            binding = existing_binding
            was_created = False

        else:
            binding = UserBushBinding(
                user_id=user_id,
                bush_id=bush_id,
                role=role,
                status=BindingStatus.APPROVED,
                assigned_by_id=assigned_by_id,
                assigned_at=assigned_at,
            )

            self.session.add(binding)
            was_created = True

        user = await self.session.get(
            User,
            user_id,
        )

        if user is None:
            raise ValueError(
                "Користувача для призначення ролі не знайдено."
            )

        if user.role not in {
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
        }:
            await self.sync_management_user_role(
                user,
                additional_role=role,
            )

        user.status = UserStatus.ACTIVE
        user.is_blocked = False
        user.blocked_at = None
        user.blocked_reason = None

        self.session.add(user)
        self.session.add(binding)

        await self.session.flush()

        return binding, was_created

    async def revoke_bush_role(
        self,
        binding: UserBushBinding,
        *,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str,
        synchronize_user_role: bool = True,
    ) -> UserBushBinding:
        """Відкликає роль користувача у кущі."""

        self.validate_aware_datetime(
            revoked_at,
            field_name="revoked_at",
        )

        normalized_reason = self.normalize_reason(
            reason
        )

        binding.revoke(
            revoked_by_id=revoked_by_id,
            revoked_at=revoked_at,
            reason=normalized_reason,
        )

        self.session.add(binding)
        await self.session.flush()

        if synchronize_user_role:
            user = await self.session.get(
                User,
                binding.user_id,
            )

            if user is not None:
                await self.sync_management_user_role(
                    user
                )

        return binding

    async def restore_bush_role(
        self,
        binding: UserBushBinding,
        *,
        assigned_by_id: int,
        assigned_at: datetime,
    ) -> UserBushBinding:
        """Відновлює відкликану роль користувача."""

        self.validate_aware_datetime(
            assigned_at,
            field_name="assigned_at",
        )

        binding.restore(
            assigned_by_id=assigned_by_id,
            assigned_at=assigned_at,
        )

        user = await self.session.get(
            User,
            binding.user_id,
        )

        if user is None:
            raise ValueError(
                "Користувача не знайдено."
            )

        if user.role not in {
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
        }:
            await self.sync_management_user_role(
                user,
                additional_role=binding.role,
            )

        user.status = UserStatus.ACTIVE
        user.is_blocked = False

        self.session.add(binding)
        self.session.add(user)

        await self.session.flush()

        return binding

    # ==========================================
    # КУЩІ КОРИСТУВАЧА
    # ==========================================

    async def get_bush_bindings_for_user(
        self,
        user_id: int,
        *,
        role: UserRole | None = None,
        approved_only: bool = True,
    ) -> list[UserBushBinding]:
        """Повертає прив’язки користувача до кущів."""

        conditions = [
            UserBushBinding.user_id == user_id,
        ]

        if role is not None:
            self.validate_bush_role(role)

            conditions.append(
                UserBushBinding.role == role
            )

        if approved_only:
            conditions.append(
                UserBushBinding.status
                == BindingStatus.APPROVED
            )

        statement = (
            select(UserBushBinding)
            .options(
                selectinload(
                    UserBushBinding.bush
                ),
            )
            .where(*conditions)
            .order_by(
                UserBushBinding.role.asc(),
                UserBushBinding.id.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_bushes_for_user(
        self,
        user_id: int,
        *,
        role: UserRole | None = None,
        active_only: bool = True,
    ) -> list[Bush]:
        """Повертає кущі, доступні користувачу."""

        conditions = [
            UserBushBinding.user_id == user_id,
            UserBushBinding.status
            == BindingStatus.APPROVED,
        ]

        if role is not None:
            self.validate_bush_role(role)

            conditions.append(
                UserBushBinding.role == role
            )

        if active_only:
            conditions.append(
                Bush.is_active.is_(True)
            )

        statement = (
            select(Bush)
            .join(
                UserBushBinding,
                UserBushBinding.bush_id
                == Bush.id,
            )
            .where(*conditions)
            .order_by(
                Bush.name.asc(),
                Bush.id.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_users_for_bush(
        self,
        bush_id: int,
        *,
        role: UserRole | None = None,
        active_only: bool = True,
    ) -> list[User]:
        """Повертає адміністраторів і левів куща."""

        conditions = [
            UserBushBinding.bush_id == bush_id,
            UserBushBinding.status
            == BindingStatus.APPROVED,
        ]

        if role is not None:
            self.validate_bush_role(role)

            conditions.append(
                UserBushBinding.role == role
            )
        else:
            conditions.append(
                UserBushBinding.role.in_(
                    {
                        UserRole.BUSH_ADMIN,
                        UserRole.LION,
                    }
                )
            )

        if active_only:
            conditions.extend(
                [
                    User.status == UserStatus.ACTIVE,
                    User.is_blocked.is_(False),
                ]
            )

        statement = (
            select(User)
            .join(
                UserBushBinding,
                UserBushBinding.user_id
                == User.id,
            )
            .where(*conditions)
            .order_by(
                User.role.asc(),
                User.full_name.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def user_has_bush_access(
        self,
        *,
        user_id: int,
        bush_id: int,
        roles: set[UserRole] | None = None,
    ) -> bool:
        """Перевіряє управлінський доступ до куща."""

        allowed_roles = roles or {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }

        for role in allowed_roles:
            self.validate_bush_role(role)

        statement = select(
            select(UserBushBinding.id)
            .where(
                UserBushBinding.user_id == user_id,
                UserBushBinding.bush_id == bush_id,
                UserBushBinding.role.in_(
                    allowed_roles
                ),
                UserBushBinding.status
                == BindingStatus.APPROVED,
            )
            .exists()
        )

        result = await self.session.scalar(
            statement
        )

        return bool(result)

    async def user_manages_store(
        self,
        *,
        user_id: int,
        store_id: int,
        roles: set[UserRole] | None = None,
    ) -> bool:
        """
        Перевіряє, чи керує користувач кущем,
        до якого належить ТТ.
        """

        allowed_roles = roles or {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }

        for role in allowed_roles:
            self.validate_bush_role(role)

        statement = select(
            select(UserBushBinding.id)
            .join(
                Store,
                Store.bush_id
                == UserBushBinding.bush_id,
            )
            .where(
                UserBushBinding.user_id == user_id,
                UserBushBinding.role.in_(
                    allowed_roles
                ),
                UserBushBinding.status
                == BindingStatus.APPROVED,
                Store.id == store_id,
            )
            .exists()
        )

        result = await self.session.scalar(
            statement
        )

        return bool(result)

    # ==========================================
    # СИНХРОНІЗАЦІЯ ГОЛОВНОЇ РОЛІ
    # ==========================================

    async def sync_management_user_role(
        self,
        user: User,
        *,
        additional_role: UserRole | None = None,
    ) -> User:
        """
        Синхронізує основну роль User з активними
        прив’язками до кущів.

        Пріоритет:

        BUSH_ADMIN → LION → STORE_USER
        """

        if user.role in {
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
        }:
            return user

        statement = select(
            UserBushBinding.role
        ).where(
            UserBushBinding.user_id == user.id,
            UserBushBinding.status
            == BindingStatus.APPROVED,
        )

        result = await self.session.scalars(
            statement
        )

        active_roles = set(
            result.all()
        )

        if additional_role is not None:
            self.validate_bush_role(
                additional_role
            )

            active_roles.add(
                additional_role
            )

        if UserRole.BUSH_ADMIN in active_roles:
            user.role = UserRole.BUSH_ADMIN

        elif UserRole.LION in active_roles:
            user.role = UserRole.LION

        else:
            user.role = UserRole.STORE_USER

        self.session.add(user)
        await self.session.flush()

        return user

    # ==========================================
    # ВІДКЛИКАННЯ ДОСТУПУ КОРИСТУВАЧА
    # ==========================================

    async def revoke_all_user_bindings(
        self,
        *,
        user_id: int,
        revoked_by_id: int,
        revoked_at: datetime,
        reason: str,
    ) -> dict[str, list[int]]:
        """
        Відкликає всі магазинні й кущові прив’язки
        конкретного користувача.
        """

        normalized_reason = self.normalize_reason(
            reason
        )

        self.validate_aware_datetime(
            revoked_at,
            field_name="revoked_at",
        )

        store_statement = (
            select(UserStoreBinding)
            .where(
                UserStoreBinding.user_id == user_id,
                UserStoreBinding.status.in_(
                    {
                        BindingStatus.PENDING,
                        BindingStatus.APPROVED,
                    }
                ),
            )
            .with_for_update()
        )

        store_result = await self.session.scalars(
            store_statement
        )

        store_bindings = list(
            store_result.unique().all()
        )

        bush_statement = (
            select(UserBushBinding)
            .where(
                UserBushBinding.user_id == user_id,
                UserBushBinding.status
                == BindingStatus.APPROVED,
            )
            .with_for_update()
        )

        bush_result = await self.session.scalars(
            bush_statement
        )

        bush_bindings = list(
            bush_result.unique().all()
        )

        for binding in store_bindings:
            binding.revoke(
                revoked_by_id=revoked_by_id,
                revoked_at=revoked_at,
                reason=normalized_reason,
            )

            self.session.add(binding)

        for binding in bush_bindings:
            binding.revoke(
                revoked_by_id=revoked_by_id,
                revoked_at=revoked_at,
                reason=normalized_reason,
            )

            self.session.add(binding)

        await self.session.flush()

        user = await self.session.get(
            User,
            user_id,
        )

        if user is not None:
            await self.sync_management_user_role(
                user
            )

        return {
            "store_binding_ids": [
                binding.id
                for binding in store_bindings
            ],
            "bush_binding_ids": [
                binding.id
                for binding in bush_bindings
            ],
        }

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def count_store_bindings_by_status(
        self,
    ) -> dict[BindingStatus, int]:
        """Кількість прив’язок до ТТ за статусами."""

        statement = (
            select(
                UserStoreBinding.status,
                func.count(
                    UserStoreBinding.id
                ),
            )
            .group_by(
                UserStoreBinding.status
            )
        )

        result = await self.session.execute(
            statement
        )

        counts = {
            status: 0
            for status in BindingStatus
        }

        for status, count in result.all():
            counts[status] = int(count)

        return counts

    async def count_bush_bindings_by_role(
        self,
    ) -> dict[UserRole, int]:
        """Кількість активних прив’язок за ролями."""

        statement = (
            select(
                UserBushBinding.role,
                func.count(
                    UserBushBinding.id
                ),
            )
            .where(
                UserBushBinding.status
                == BindingStatus.APPROVED
            )
            .group_by(
                UserBushBinding.role
            )
        )

        result = await self.session.execute(
            statement
        )

        counts = {
            UserRole.BUSH_ADMIN: 0,
            UserRole.LION: 0,
        }

        for role, count in result.all():
            counts[role] = int(count)

        return counts

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def validate_bush_role(
        role: UserRole,
    ) -> None:
        """Перевіряє роль для прив’язки до куща."""

        if role not in {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            raise ValueError(
                "До куща можна прив’язати лише "
                "адміністратора куща або лева."
            )

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
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        """Перевіряє наявність часового поясу."""

        if value.tzinfo is None:
            raise ValueError(
                f"{field_name} повинен містити "
                "часовий пояс."
            )

    @staticmethod
    def normalize_reason(
        reason: str,
    ) -> str:
        """Нормалізує причину адміністративної дії."""

        normalized_reason = " ".join(
            reason.strip().split()
        )

        if not normalized_reason:
            raise ValueError(
                "Причина не може бути порожньою."
            )

        if len(normalized_reason) > 1000:
            raise ValueError(
                "Причина занадто довга."
            )

        return normalized_reason