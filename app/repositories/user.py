from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    String,
    cast,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models.enums import (
    UserRole,
    UserStatus,
)
from app.database.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """
    Репозиторій Telegram-користувачів.

    Репозиторій працює лише з даними та SQLAlchemy.
    Остаточний commit виконується у сервісі або handler.
    """

    model = User

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(session)

    # ==========================================
    # ПОШУК ЗА TELEGRAM ID
    # ==========================================

    async def get_by_telegram_id(
        self,
        telegram_id: int,
    ) -> User | None:
        """Повертає користувача за Telegram ID."""

        statement = (
            select(User)
            .where(
                User.telegram_id == telegram_id
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_telegram_id_or_raise(
        self,
        telegram_id: int,
    ) -> User:
        """Повертає користувача або викликає помилку."""

        user = await self.get_by_telegram_id(
            telegram_id
        )

        if user is None:
            raise ValueError(
                "Користувача не знайдено в системі."
            )

        return user

    async def get_active_by_telegram_id(
        self,
        telegram_id: int,
    ) -> User | None:
        """
        Повертає лише активного та незаблокованого
        користувача.
        """

        statement = (
            select(User)
            .where(
                User.telegram_id == telegram_id,
                User.status == UserStatus.ACTIVE,
                User.is_blocked.is_(False),
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    # ==========================================
    # СТВОРЕННЯ З TELEGRAM
    # ==========================================

    async def get_or_create_from_telegram(
        self,
        *,
        telegram_id: int,
        full_name: str,
        username: str | None = None,
        phone: str | None = None,
        activity_at: datetime | None = None,
    ) -> tuple[User, bool]:
        """
        Знаходить або створює користувача після /start.

        Повертає:
        - об’єкт User;
        - True, якщо користувача створено;
        - False, якщо користувач уже існував.

        ROOT_ADMIN автоматично визначається
        за ROOT_ADMIN_IDS із .env.
        """

        if telegram_id <= 0:
            raise ValueError(
                "Telegram ID повинен бути більшим за нуль."
            )

        normalized_full_name = full_name.strip()

        if not normalized_full_name:
            raise ValueError(
                "Ім’я користувача не може бути порожнім."
            )

        normalized_username = self.normalize_username(
            username
        )

        normalized_phone = self.normalize_phone(
            phone
        )

        existing_user = await self.get_by_telegram_id(
            telegram_id
        )

        if existing_user is not None:
            await self.update_telegram_profile(
                existing_user,
                full_name=normalized_full_name,
                username=normalized_username,
                phone=normalized_phone,
                activity_at=activity_at,
            )

            await self.ensure_root_role(
                existing_user
            )

            return existing_user, False

        is_root_admin = settings.is_root_admin(
            telegram_id
        )

        if is_root_admin:
            role = UserRole.ROOT_ADMIN
            status = UserStatus.ACTIVE
        else:
            role = UserRole.STORE_USER

            status = (
                UserStatus.PENDING
                if settings.require_store_approval
                else UserStatus.ACTIVE
            )

        user = User(
            telegram_id=telegram_id,
            username=normalized_username,
            full_name=normalized_full_name,
            phone=normalized_phone,
            role=role,
            status=status,
            is_blocked=False,
            last_activity_at=activity_at,
        )

        await self.add(
            user,
            flush=True,
        )

        return user, True

    async def ensure_root_role(
        self,
        user: User,
    ) -> bool:
        """
        Синхронізує роль користувача з ROOT_ADMIN_IDS.

        Повертає True, якщо роль або статус було змінено.
        """

        should_be_root = settings.is_root_admin(
            user.telegram_id
        )

        if not should_be_root:
            return False

        changed = False

        if user.role != UserRole.ROOT_ADMIN:
            user.role = UserRole.ROOT_ADMIN
            changed = True

        if user.status != UserStatus.ACTIVE:
            user.status = UserStatus.ACTIVE
            changed = True

        if user.is_blocked:
            user.is_blocked = False
            user.blocked_at = None
            user.blocked_reason = None
            changed = True

        if changed:
            self.session.add(user)
            await self.session.flush()

        return changed

    async def synchronize_root_admins(
        self,
    ) -> list[User]:
        """
        Синхронізує вже зареєстрованих користувачів
        із ROOT_ADMIN_IDS.

        Користувачі повинні хоча б один раз запустити бота,
        щоб запис з’явився у базі.
        """

        if not settings.root_admin_ids:
            return []

        statement = select(User).where(
            User.telegram_id.in_(
                settings.root_admin_ids
            )
        )

        result = await self.session.scalars(
            statement
        )

        users = list(
            result.unique().all()
        )

        changed_users: list[User] = []

        for user in users:
            changed = await self.ensure_root_role(
                user
            )

            if changed:
                changed_users.append(user)

        return changed_users

    # ==========================================
    # ОНОВЛЕННЯ TELEGRAM-ПРОФІЛЮ
    # ==========================================

    async def update_telegram_profile(
        self,
        user: User,
        *,
        full_name: str,
        username: str | None,
        phone: str | None = None,
        activity_at: datetime | None = None,
    ) -> User:
        """
        Оновлює Telegram-дані при кожному /start.

        Це потрібно, бо користувач може:
        - змінити username;
        - змінити ім’я;
        - змінити номер телефону.
        """

        normalized_full_name = full_name.strip()

        if not normalized_full_name:
            raise ValueError(
                "Ім’я користувача не може бути порожнім."
            )

        user.full_name = normalized_full_name
        user.username = self.normalize_username(
            username
        )

        if phone is not None:
            user.phone = self.normalize_phone(
                phone
            )

        if activity_at is not None:
            user.last_activity_at = activity_at

        self.session.add(user)
        await self.session.flush()

        return user

    async def update_phone(
        self,
        user: User,
        *,
        phone: str,
    ) -> User:
        """Оновлює номер телефону користувача."""

        normalized_phone = self.normalize_phone(
            phone
        )

        if normalized_phone is None:
            raise ValueError(
                "Номер телефону не може бути порожнім."
            )

        user.phone = normalized_phone

        self.session.add(user)
        await self.session.flush()

        return user

    async def touch_activity(
        self,
        user: User,
        *,
        activity_at: datetime,
    ) -> User:
        """Оновлює час останньої активності."""

        if activity_at.tzinfo is None:
            raise ValueError(
                "activity_at повинен містити часовий пояс."
            )

        user.last_activity_at = activity_at

        self.session.add(user)
        await self.session.flush()

        return user

    # ==========================================
    # РОЛІ
    # ==========================================

    async def assign_role(
        self,
        user: User,
        *,
        role: UserRole,
    ) -> User:
        """Призначає користувачу нову роль."""

        if (
            role == UserRole.ROOT_ADMIN
            and not settings.is_root_admin(
                user.telegram_id
            )
        ):
            raise ValueError(
                "ROOT_ADMIN можна призначити лише через "
                "ROOT_ADMIN_IDS у змінних середовища."
            )

        user.role = role

        if role in {
            UserRole.ROOT_ADMIN,
            UserRole.DIRECTOR,
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }:
            user.status = UserStatus.ACTIVE
            user.is_blocked = False
            user.blocked_at = None
            user.blocked_reason = None

        self.session.add(user)
        await self.session.flush()

        return user

    async def remove_management_role(
        self,
        user: User,
    ) -> User:
        """
        Забирає управлінську роль і переводить
        користувача у звичайного користувача ТТ.
        """

        if user.role == UserRole.ROOT_ADMIN:
            raise ValueError(
                "Не можна зняти роль ROOT_ADMIN через бота. "
                "Спочатку видаліть Telegram ID із ROOT_ADMIN_IDS."
            )

        user.role = UserRole.STORE_USER

        self.session.add(user)
        await self.session.flush()

        return user

    # ==========================================
    # ПІДТВЕРДЖЕННЯ І СТАТУС
    # ==========================================

    async def activate_user(
        self,
        user: User,
    ) -> User:
        """Активує користувача."""

        user.status = UserStatus.ACTIVE
        user.is_blocked = False
        user.blocked_at = None
        user.blocked_reason = None

        self.session.add(user)
        await self.session.flush()

        return user

    async def set_pending(
        self,
        user: User,
    ) -> User:
        """Переводить користувача у статус очікування."""

        if user.role == UserRole.ROOT_ADMIN:
            raise ValueError(
                "ROOT_ADMIN не можна перевести "
                "у статус очікування."
            )

        user.status = UserStatus.PENDING
        user.is_blocked = False

        self.session.add(user)
        await self.session.flush()

        return user

    async def deactivate_user(
        self,
        user: User,
    ) -> User:
        """
        Деактивує користувача без фізичного видалення.
        """

        if user.role == UserRole.ROOT_ADMIN:
            raise ValueError(
                "ROOT_ADMIN не можна деактивувати через бота."
            )

        user.status = UserStatus.INACTIVE
        user.is_blocked = False

        self.session.add(user)
        await self.session.flush()

        return user

    # ==========================================
    # БЛОКУВАННЯ
    # ==========================================

    async def block_user(
        self,
        user: User,
        *,
        blocked_at: datetime,
        reason: str | None = None,
    ) -> User:
        """Блокує користувача в Telegram-боті."""

        if user.role == UserRole.ROOT_ADMIN:
            raise ValueError(
                "ROOT_ADMIN не можна заблокувати через бота."
            )

        if blocked_at.tzinfo is None:
            raise ValueError(
                "blocked_at повинен містити часовий пояс."
            )

        user.block(
            blocked_at=blocked_at,
            reason=reason,
        )

        self.session.add(user)
        await self.session.flush()

        return user

    async def unblock_user(
        self,
        user: User,
    ) -> User:
        """Розблоковує користувача."""

        user.unblock()

        self.session.add(user)
        await self.session.flush()

        return user

    # ==========================================
    # СПИСКИ КОРИСТУВАЧІВ
    # ==========================================

    async def get_by_role(
        self,
        role: UserRole,
        *,
        active_only: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[User]:
        """Повертає користувачів із конкретною роллю."""

        conditions = [
            User.role == role,
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
            .where(*conditions)
            .order_by(
                User.full_name.asc(),
                User.id.asc(),
            )
            .offset(offset)
        )

        if limit is not None:
            if limit <= 0:
                raise ValueError(
                    "Limit повинен бути більшим за нуль."
                )

            statement = statement.limit(limit)

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_root_admins(
        self,
        *,
        active_only: bool = True,
    ) -> list[User]:
        return await self.get_by_role(
            UserRole.ROOT_ADMIN,
            active_only=active_only,
        )

    async def get_directors(
        self,
        *,
        active_only: bool = True,
    ) -> list[User]:
        return await self.get_by_role(
            UserRole.DIRECTOR,
            active_only=active_only,
        )

    async def get_bush_admins(
        self,
        *,
        active_only: bool = True,
    ) -> list[User]:
        return await self.get_by_role(
            UserRole.BUSH_ADMIN,
            active_only=active_only,
        )

    async def get_lions(
        self,
        *,
        active_only: bool = True,
    ) -> list[User]:
        return await self.get_by_role(
            UserRole.LION,
            active_only=active_only,
        )

    async def get_store_users(
        self,
        *,
        active_only: bool = False,
    ) -> list[User]:
        return await self.get_by_role(
            UserRole.STORE_USER,
            active_only=active_only,
        )

    async def get_pending_users(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[User]:
        """Повертає користувачів, які очікують підтвердження."""

        statement = (
            select(User)
            .where(
                User.status == UserStatus.PENDING,
                User.is_blocked.is_(False),
            )
            .order_by(
                User.created_at.asc(),
            )
            .offset(offset)
        )

        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_blocked_users(
        self,
    ) -> list[User]:
        """Повертає заблокованих користувачів."""

        statement = (
            select(User)
            .where(
                or_(
                    User.is_blocked.is_(True),
                    User.status == UserStatus.BLOCKED,
                )
            )
            .order_by(
                User.blocked_at.desc().nullslast(),
                User.full_name.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ПОШУК
    # ==========================================

    async def search(
        self,
        query: str,
        *,
        role: UserRole | None = None,
        active_only: bool = False,
        limit: int = 30,
    ) -> list[User]:
        """
        Шукає користувача за:

        - ім’ям;
        - username;
        - телефоном;
        - Telegram ID.
        """

        normalized_query = query.strip()

        if not normalized_query:
            return []

        if limit <= 0 or limit > 100:
            raise ValueError(
                "Limit пошуку повинен бути від 1 до 100."
            )

        search_pattern = (
            f"%{normalized_query}%"
        )

        conditions = [
            or_(
                User.full_name.ilike(
                    search_pattern
                ),
                User.username.ilike(
                    search_pattern
                ),
                User.phone.ilike(
                    search_pattern
                ),
                cast(
                    User.telegram_id,
                    String,
                ).ilike(
                    search_pattern
                ),
            )
        ]

        if role is not None:
            conditions.append(
                User.role == role
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
            .where(*conditions)
            .order_by(
                User.full_name.asc(),
            )
            .limit(limit)
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def count_by_role(
        self,
    ) -> dict[UserRole, int]:
        """Повертає кількість користувачів по ролях."""

        statement = (
            select(
                User.role,
                func.count(User.id),
            )
            .group_by(User.role)
        )

        result = await self.session.execute(
            statement
        )

        counts: dict[UserRole, int] = {
            role: 0
            for role in UserRole
        }

        for role, count in result.all():
            counts[role] = int(count)

        return counts

    async def count_by_status(
        self,
    ) -> dict[UserStatus, int]:
        """Повертає кількість користувачів по статусах."""

        statement = (
            select(
                User.status,
                func.count(User.id),
            )
            .group_by(User.status)
        )

        result = await self.session.execute(
            statement
        )

        counts: dict[UserStatus, int] = {
            status: 0
            for status in UserStatus
        }

        for status, count in result.all():
            counts[status] = int(count)

        return counts

    # ==========================================
    # НОРМАЛІЗАЦІЯ
    # ==========================================

    @staticmethod
    def normalize_username(
        username: str | None,
    ) -> str | None:
        """Прибирає @ із Telegram username."""

        if username is None:
            return None

        normalized_username = (
            username.strip().removeprefix("@")
        )

        if not normalized_username:
            return None

        if len(normalized_username) > 64:
            raise ValueError(
                "Telegram username занадто довгий."
            )

        return normalized_username

    @staticmethod
    def normalize_phone(
        phone: str | None,
    ) -> str | None:
        """
        Нормалізує номер телефону.

        Залишає:
        - цифри;
        - знак + на початку.
        """

        if phone is None:
            return None

        raw_phone = phone.strip()

        if not raw_phone:
            return None

        has_plus = raw_phone.startswith("+")

        digits = "".join(
            character
            for character in raw_phone
            if character.isdigit()
        )

        if not digits:
            raise ValueError(
                "Номер телефону не містить цифр."
            )

        normalized_phone = (
            f"+{digits}"
            if has_plus
            else digits
        )

        if len(digits) < 7:
            raise ValueError(
                "Номер телефону занадто короткий."
            )

        if len(digits) > 15:
            raise ValueError(
                "Номер телефону занадто довгий."
            )

        return normalized_phone