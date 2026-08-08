from __future__ import annotations

from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.binding import UserBushBinding
from app.database.models.bush import Bush
from app.database.models.enums import (
    BindingStatus,
    StoreStatus,
    UserRole,
    UserStatus,
)
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories.base import BaseRepository


class BushRepository(BaseRepository[Bush]):
    """
    Репозиторій кущів торгових точок.

    Репозиторій керує:

    - основними даними куща;
    - його активністю;
    - Telegram-темою;
    - списком торгових точок;
    - адміністраторами;
    - левами;
    - статистикою.
    """

    model = Bush

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(session)

    # ==========================================
    # ПОШУК КУЩА
    # ==========================================

    async def get_by_code(
        self,
        code: str,
    ) -> Bush | None:
        """Повертає кущ за унікальним кодом."""

        normalized_code = self.normalize_code(code)

        statement = (
            select(Bush)
            .where(
                func.upper(Bush.code)
                == normalized_code.upper()
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_code_or_raise(
        self,
        code: str,
    ) -> Bush:
        """Повертає кущ за кодом або викликає помилку."""

        bush = await self.get_by_code(code)

        if bush is None:
            raise ValueError(
                f"Кущ із кодом {self.normalize_code(code)} "
                "не знайдено."
            )

        return bush

    async def get_by_name(
        self,
        name: str,
    ) -> Bush | None:
        """Повертає кущ за точною назвою."""

        normalized_name = self.normalize_name(name)

        statement = (
            select(Bush)
            .where(
                func.lower(Bush.name)
                == normalized_name.lower()
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_active_by_id(
        self,
        bush_id: int,
    ) -> Bush | None:
        """Повертає активний кущ за ID."""

        statement = (
            select(Bush)
            .where(
                Bush.id == bush_id,
                Bush.is_active.is_(True),
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_for_update(
        self,
        bush_id: int,
    ) -> Bush | None:
        """
        Завантажує кущ із блокуванням рядка.

        Використовується під час критичних змін.
        """

        statement = (
            select(Bush)
            .where(Bush.id == bush_id)
            .with_for_update()
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    # ==========================================
    # СТВОРЕННЯ
    # ==========================================

    async def create_bush(
        self,
        *,
        name: str,
        code: str,
        telegram_topic_id: int | None = None,
        note: str | None = None,
    ) -> Bush:
        """Створює новий кущ."""

        normalized_name = self.normalize_name(name)
        normalized_code = self.normalize_code(code)

        existing_by_code = await self.get_by_code(
            normalized_code
        )

        if existing_by_code is not None:
            raise ValueError(
                f"Кущ із кодом {normalized_code} "
                "уже існує."
            )

        existing_by_name = await self.get_by_name(
            normalized_name
        )

        if existing_by_name is not None:
            raise ValueError(
                f"Кущ із назвою «{normalized_name}» "
                "уже існує."
            )

        self.validate_topic_id(
            telegram_topic_id
        )

        bush = Bush(
            name=normalized_name,
            code=normalized_code,
            is_active=True,
            telegram_topic_id=telegram_topic_id,
            note=self.normalize_optional_text(note),
        )

        await self.add(
            bush,
            flush=True,
        )

        return bush

    # ==========================================
    # РЕДАГУВАННЯ
    # ==========================================

    async def update_bush(
        self,
        bush: Bush,
        *,
        name: str | None = None,
        code: str | None = None,
        telegram_topic_id: int | None = None,
        note: str | None = None,
        update_topic: bool = False,
        update_note: bool = False,
    ) -> Bush:
        """
        Оновлює дані куща.

        update_topic=True дозволяє також
        очистити telegram_topic_id через None.

        update_note=True дозволяє очистити примітку.
        """

        if name is not None:
            normalized_name = self.normalize_name(
                name
            )

            existing = await self.get_by_name(
                normalized_name
            )

            if (
                existing is not None
                and existing.id != bush.id
            ):
                raise ValueError(
                    f"Назва «{normalized_name}» "
                    "уже використовується."
                )

            bush.name = normalized_name

        if code is not None:
            normalized_code = self.normalize_code(
                code
            )

            existing = await self.get_by_code(
                normalized_code
            )

            if (
                existing is not None
                and existing.id != bush.id
            ):
                raise ValueError(
                    f"Код {normalized_code} "
                    "уже використовується."
                )

            bush.code = normalized_code

        if update_topic:
            self.validate_topic_id(
                telegram_topic_id
            )

            bush.telegram_topic_id = (
                telegram_topic_id
            )

        if update_note:
            bush.note = self.normalize_optional_text(
                note
            )

        self.session.add(bush)
        await self.session.flush()

        return bush

    async def set_telegram_topic(
        self,
        bush: Bush,
        *,
        topic_id: int | None,
    ) -> Bush:
        """Прив’язує або прибирає Telegram-тему куща."""

        self.validate_topic_id(topic_id)

        bush.telegram_topic_id = topic_id

        self.session.add(bush)
        await self.session.flush()

        return bush

    # ==========================================
    # АКТИВАЦІЯ І ДЕАКТИВАЦІЯ
    # ==========================================

    async def activate_bush(
        self,
        bush: Bush,
    ) -> Bush:
        """Активує кущ."""

        bush.is_active = True

        self.session.add(bush)
        await self.session.flush()

        return bush

    async def deactivate_bush(
        self,
        bush: Bush,
        *,
        allow_with_active_stores: bool = False,
    ) -> Bush:
        """
        Деактивує кущ без фізичного видалення.

        За замовчуванням кущ не можна деактивувати,
        доки в ньому є активні торгові точки.
        """

        if not allow_with_active_stores:
            active_stores_count = (
                await self.count_active_stores(
                    bush.id
                )
            )

            if active_stores_count > 0:
                raise ValueError(
                    "Кущ не можна деактивувати, "
                    f"оскільки до нього прив’язано "
                    f"{active_stores_count} активних ТТ."
                )

        bush.is_active = False

        self.session.add(bush)
        await self.session.flush()

        return bush

    # ==========================================
    # СПИСКИ КУЩІВ
    # ==========================================

    async def get_active_bushes(
        self,
    ) -> list[Bush]:
        """Повертає всі активні кущі."""

        statement = (
            select(Bush)
            .where(
                Bush.is_active.is_(True)
            )
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

    async def get_inactive_bushes(
        self,
    ) -> list[Bush]:
        """Повертає всі неактивні кущі."""

        statement = (
            select(Bush)
            .where(
                Bush.is_active.is_(False)
            )
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

    async def get_without_telegram_topic(
        self,
    ) -> list[Bush]:
        """Повертає активні кущі без Telegram-теми."""

        statement = (
            select(Bush)
            .where(
                Bush.is_active.is_(True),
                Bush.telegram_topic_id.is_(None),
            )
            .order_by(
                Bush.name.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ТОРГОВІ ТОЧКИ КУЩА
    # ==========================================

    async def get_stores(
        self,
        bush_id: int,
        *,
        active_only: bool = True,
        include_temporarily_closed: bool = False,
    ) -> list[Store]:
        """Повертає торгові точки куща."""

        conditions = [
            Store.bush_id == bush_id,
        ]

        if active_only:
            if include_temporarily_closed:
                conditions.extend(
                    [
                        Store.is_active.is_(True),
                        Store.status.in_(
                            {
                                StoreStatus.ACTIVE,
                                StoreStatus.TEMPORARILY_CLOSED,
                            }
                        ),
                    ]
                )
            else:
                conditions.extend(
                    [
                        Store.is_active.is_(True),
                        Store.status == StoreStatus.ACTIVE,
                    ]
                )

        statement = (
            select(Store)
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

    async def count_stores(
        self,
        bush_id: int,
        *,
        active_only: bool = False,
    ) -> int:
        """Підраховує торгові точки куща."""

        conditions = [
            Store.bush_id == bush_id,
        ]

        if active_only:
            conditions.extend(
                [
                    Store.is_active.is_(True),
                    Store.status == StoreStatus.ACTIVE,
                ]
            )

        statement = (
            select(func.count(Store.id))
            .where(*conditions)
        )

        result = await self.session.scalar(
            statement
        )

        return int(result or 0)

    async def count_active_stores(
        self,
        bush_id: int,
    ) -> int:
        """Підраховує активні ТТ куща."""

        return await self.count_stores(
            bush_id,
            active_only=True,
        )

    # ==========================================
    # АДМІНІСТРАТОРИ ТА ЛЕВИ
    # ==========================================

    async def get_management_users(
        self,
        bush_id: int,
        *,
        role: UserRole | None = None,
        active_only: bool = True,
    ) -> list[User]:
        """
        Повертає адміністраторів і левів куща.

        Якщо role=None, повертає обидві ролі.
        """

        allowed_roles = {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }

        if role is not None and role not in allowed_roles:
            raise ValueError(
                "Для куща дозволені лише ролі "
                "BUSH_ADMIN та LION."
            )

        roles = (
            {role}
            if role is not None
            else allowed_roles
        )

        conditions = [
            UserBushBinding.bush_id == bush_id,
            UserBushBinding.role.in_(roles),
            UserBushBinding.status
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
                UserBushBinding,
                UserBushBinding.user_id == User.id,
            )
            .where(*conditions)
            .order_by(
                User.role.asc(),
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

    async def get_admins(
        self,
        bush_id: int,
        *,
        active_only: bool = True,
    ) -> list[User]:
        """Повертає адміністраторів конкретного куща."""

        return await self.get_management_users(
            bush_id,
            role=UserRole.BUSH_ADMIN,
            active_only=active_only,
        )

    async def get_lions(
        self,
        bush_id: int,
        *,
        active_only: bool = True,
    ) -> list[User]:
        """Повертає левів конкретного куща."""

        return await self.get_management_users(
            bush_id,
            role=UserRole.LION,
            active_only=active_only,
        )

    async def count_management_users(
        self,
        bush_id: int,
        *,
        role: UserRole | None = None,
        active_only: bool = True,
    ) -> int:
        """Підраховує адміністраторів або левів куща."""

        allowed_roles = {
            UserRole.BUSH_ADMIN,
            UserRole.LION,
        }

        if role is not None and role not in allowed_roles:
            raise ValueError(
                "Некоректна роль для куща."
            )

        roles = (
            {role}
            if role is not None
            else allowed_roles
        )

        conditions = [
            UserBushBinding.bush_id == bush_id,
            UserBushBinding.role.in_(roles),
            UserBushBinding.status
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
            select(
                func.count(
                    func.distinct(User.id)
                )
            )
            .select_from(User)
            .join(
                UserBushBinding,
                UserBushBinding.user_id == User.id,
            )
            .where(*conditions)
        )

        result = await self.session.scalar(
            statement
        )

        return int(result or 0)

    async def get_bushes_without_admin(
        self,
    ) -> list[Bush]:
        """Повертає активні кущі без активного адміністратора."""

        active_admin_exists = (
            select(UserBushBinding.id)
            .join(
                User,
                User.id == UserBushBinding.user_id,
            )
            .where(
                UserBushBinding.bush_id == Bush.id,
                UserBushBinding.role
                == UserRole.BUSH_ADMIN,
                UserBushBinding.status
                == BindingStatus.APPROVED,
                User.status == UserStatus.ACTIVE,
                User.is_blocked.is_(False),
            )
            .exists()
        )

        statement = (
            select(Bush)
            .where(
                Bush.is_active.is_(True),
                ~active_admin_exists,
            )
            .order_by(
                Bush.name.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_bushes_without_lion(
        self,
    ) -> list[Bush]:
        """Повертає активні кущі без активного лева."""

        active_lion_exists = (
            select(UserBushBinding.id)
            .join(
                User,
                User.id == UserBushBinding.user_id,
            )
            .where(
                UserBushBinding.bush_id == Bush.id,
                UserBushBinding.role == UserRole.LION,
                UserBushBinding.status
                == BindingStatus.APPROVED,
                User.status == UserStatus.ACTIVE,
                User.is_blocked.is_(False),
            )
            .exists()
        )

        statement = (
            select(Bush)
            .where(
                Bush.is_active.is_(True),
                ~active_lion_exists,
            )
            .order_by(
                Bush.name.asc()
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
        active_only: bool = False,
        limit: int = 50,
    ) -> list[Bush]:
        """
        Шукає кущ за:

        - назвою;
        - кодом;
        - приміткою.
        """

        normalized_query = query.strip()

        if not normalized_query:
            return []

        if limit <= 0 or limit > 200:
            raise ValueError(
                "Limit пошуку повинен бути від 1 до 200."
            )

        search_pattern = (
            f"%{normalized_query}%"
        )

        conditions = [
            or_(
                Bush.name.ilike(search_pattern),
                Bush.code.ilike(search_pattern),
                Bush.note.ilike(search_pattern),
            )
        ]

        if active_only:
            conditions.append(
                Bush.is_active.is_(True)
            )

        statement = (
            select(Bush)
            .where(*conditions)
            .order_by(
                Bush.name.asc(),
                Bush.id.asc(),
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

    async def get_statistics(
        self,
        *,
        active_bushes_only: bool = True,
    ) -> list[dict[str, int | str | bool]]:
        """
        Повертає статистику по кожному кущу:

        - кількість активних ТТ;
        - кількість адміністраторів;
        - кількість левів.
        """

        bush_conditions = []

        if active_bushes_only:
            bush_conditions.append(
                Bush.is_active.is_(True)
            )

        stores_subquery = (
            select(
                Store.bush_id.label("bush_id"),
                func.count(Store.id).label(
                    "stores_count"
                ),
            )
            .where(
                Store.is_active.is_(True),
                Store.status == StoreStatus.ACTIVE,
            )
            .group_by(Store.bush_id)
            .subquery()
        )

        admins_subquery = (
            select(
                UserBushBinding.bush_id.label(
                    "bush_id"
                ),
                func.count(
                    func.distinct(
                        UserBushBinding.user_id
                    )
                ).label("admins_count"),
            )
            .join(
                User,
                User.id
                == UserBushBinding.user_id,
            )
            .where(
                UserBushBinding.role
                == UserRole.BUSH_ADMIN,
                UserBushBinding.status
                == BindingStatus.APPROVED,
                User.status == UserStatus.ACTIVE,
                User.is_blocked.is_(False),
            )
            .group_by(
                UserBushBinding.bush_id
            )
            .subquery()
        )

        lions_subquery = (
            select(
                UserBushBinding.bush_id.label(
                    "bush_id"
                ),
                func.count(
                    func.distinct(
                        UserBushBinding.user_id
                    )
                ).label("lions_count"),
            )
            .join(
                User,
                User.id
                == UserBushBinding.user_id,
            )
            .where(
                UserBushBinding.role
                == UserRole.LION,
                UserBushBinding.status
                == BindingStatus.APPROVED,
                User.status == UserStatus.ACTIVE,
                User.is_blocked.is_(False),
            )
            .group_by(
                UserBushBinding.bush_id
            )
            .subquery()
        )

        statement = (
            select(
                Bush.id,
                Bush.name,
                Bush.code,
                Bush.is_active,
                func.coalesce(
                    stores_subquery.c.stores_count,
                    0,
                ).label("stores_count"),
                func.coalesce(
                    admins_subquery.c.admins_count,
                    0,
                ).label("admins_count"),
                func.coalesce(
                    lions_subquery.c.lions_count,
                    0,
                ).label("lions_count"),
            )
            .outerjoin(
                stores_subquery,
                stores_subquery.c.bush_id
                == Bush.id,
            )
            .outerjoin(
                admins_subquery,
                admins_subquery.c.bush_id
                == Bush.id,
            )
            .outerjoin(
                lions_subquery,
                lions_subquery.c.bush_id
                == Bush.id,
            )
            .where(*bush_conditions)
            .order_by(
                Bush.name.asc()
            )
        )

        result = await self.session.execute(
            statement
        )

        statistics: list[
            dict[str, int | str | bool]
        ] = []

        for row in result.mappings().all():
            statistics.append(
                {
                    "bush_id": int(row["id"]),
                    "name": str(row["name"]),
                    "code": str(row["code"]),
                    "is_active": bool(
                        row["is_active"]
                    ),
                    "stores_count": int(
                        row["stores_count"]
                    ),
                    "admins_count": int(
                        row["admins_count"]
                    ),
                    "lions_count": int(
                        row["lions_count"]
                    ),
                }
            )

        return statistics

    # ==========================================
    # НОРМАЛІЗАЦІЯ
    # ==========================================

    @staticmethod
    def normalize_name(
        name: str,
    ) -> str:
        """Нормалізує назву куща."""

        normalized_name = " ".join(
            name.strip().split()
        )

        if not normalized_name:
            raise ValueError(
                "Назва куща не може бути порожньою."
            )

        if len(normalized_name) > 150:
            raise ValueError(
                "Назва куща занадто довга."
            )

        return normalized_name

    @staticmethod
    def normalize_code(
        code: str,
    ) -> str:
        """
        Нормалізує код куща.

        Приклад:
        vinnytsia 1 -> VINNYTSIA-1
        """

        normalized_code = (
            code.strip()
            .upper()
            .replace(" ", "-")
            .replace("_", "-")
        )

        while "--" in normalized_code:
            normalized_code = (
                normalized_code.replace(
                    "--",
                    "-",
                )
            )

        normalized_code = normalized_code.strip(
            "-"
        )

        if not normalized_code:
            raise ValueError(
                "Код куща не може бути порожнім."
            )

        allowed_characters = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789-"
        )

        if any(
            character not in allowed_characters
            for character in normalized_code
        ):
            raise ValueError(
                "Код куща може містити лише "
                "латинські літери, цифри та дефіс."
            )

        if len(normalized_code) > 50:
            raise ValueError(
                "Код куща занадто довгий."
            )

        return normalized_code

    @staticmethod
    def normalize_optional_text(
        value: str | None,
    ) -> str | None:
        """Нормалізує необов’язковий текст."""

        if value is None:
            return None

        normalized_value = " ".join(
            value.strip().split()
        )

        return normalized_value or None

    @staticmethod
    def validate_topic_id(
        topic_id: int | None,
    ) -> None:
        """Перевіряє Telegram topic ID."""

        if topic_id is not None and topic_id <= 0:
            raise ValueError(
                "Telegram topic ID повинен бути "
                "більшим за нуль."
            )