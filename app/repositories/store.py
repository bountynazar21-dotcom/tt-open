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
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import InstrumentedAttribute

from app.database.models.enums import StoreStatus
from app.database.models.store import Store
from app.repositories.base import BaseRepository


class StoreRepository(BaseRepository[Store]):
    """
    Репозиторій торгових точок.

    Відповідає за:

    - створення нових ТТ;
    - пошук за номером або кодом;
    - списки по кущах, містах і кластерах;
    - деактивацію без фізичного видалення;
    - повторну активацію;
    - тимчасове закриття;
    - переміщення між кущами;
    - зміну кластера відкриття;
    - виключення київських ТТ.
    """

    model = Store

    KYIV_CITY_NAMES: frozenset[str] = frozenset(
        {
            "київ",
            "киев",
            "kyiv",
            "kiev",
            "м київ",
            "м киев",
            "місто київ",
            "город киев",
        }
    )

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(session)

    # ==========================================
    # ПОШУК ЗА НОМЕРОМ І КОДОМ
    # ==========================================

    async def get_by_number(
        self,
        store_number: int,
    ) -> Store | None:
        """Повертає ТТ за числовим номером."""

        if store_number <= 0:
            return None

        statement = (
            select(Store)
            .where(
                Store.store_number == store_number
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_number_or_raise(
        self,
        store_number: int,
    ) -> Store:
        """Повертає ТТ або викликає помилку."""

        store = await self.get_by_number(
            store_number
        )

        if store is None:
            raise ValueError(
                f"Торгову точку SB-{store_number} не знайдено."
            )

        return store

    async def get_by_code(
        self,
        code: str,
    ) -> Store | None:
        """
        Повертає ТТ за кодом.

        Підтримує формати:
        - SB-76;
        - sb-76;
        - SB76;
        - 76.
        """

        normalized_code = self.normalize_code(
            code
        )

        statement = (
            select(Store)
            .where(
                func.upper(Store.code)
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
    ) -> Store:
        """Повертає ТТ за кодом або викликає помилку."""

        store = await self.get_by_code(code)

        if store is None:
            raise ValueError(
                f"Торгову точку {self.normalize_code(code)} "
                "не знайдено."
            )

        return store

    async def get_active_by_code(
        self,
        code: str,
    ) -> Store | None:
        """Повертає лише активну ТТ."""

        normalized_code = self.normalize_code(
            code
        )

        statement = (
            select(Store)
            .where(
                func.upper(Store.code)
                == normalized_code.upper(),
                Store.is_active.is_(True),
                Store.status == StoreStatus.ACTIVE,
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_for_update(
        self,
        store_id: int,
    ) -> Store | None:
        """
        Завантажує ТТ із блокуванням рядка.

        Використовуватиметься під час критичних змін:
        - кіку;
        - зміни куща;
        - зміни кластера;
        - підтвердження відкриття.
        """

        statement = (
            select(Store)
            .where(Store.id == store_id)
            .with_for_update()
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    # ==========================================
    # СТВОРЕННЯ ТОРГОВОЇ ТОЧКИ
    # ==========================================

    async def create_store(
        self,
        *,
        store_number: int,
        city: str,
        address: str,
        bush_id: int | None = None,
        cluster_id: int | None = None,
        name: str | None = None,
        code: str | None = None,
        phone: str | None = None,
        store_format: str | None = None,
        timezone: str = "Europe/Kyiv",
        telegram_topic_id: int | None = None,
        note: str | None = None,
        allow_kyiv: bool = False,
    ) -> Store:
        """
        Створює нову торгову точку.

        За замовчуванням торгові точки Києва
        не додаються до системи контролю.
        """

        if store_number <= 0:
            raise ValueError(
                "Номер торгової точки повинен бути "
                "більшим за нуль."
            )

        normalized_city = self.normalize_required_text(
            city,
            field_name="Місто",
        )

        normalized_address = self.normalize_required_text(
            address,
            field_name="Адреса",
        )

        if (
            not allow_kyiv
            and self.is_kyiv_city(normalized_city)
        ):
            raise ValueError(
                "Торгові точки Києва виключені "
                "із системи контролю."
            )

        final_code = (
            self.normalize_code(code)
            if code
            else self.build_store_code(store_number)
        )

        existing_by_number = await self.get_by_number(
            store_number
        )

        if existing_by_number is not None:
            raise ValueError(
                f"Торгова точка SB-{store_number} "
                "уже існує."
            )

        existing_by_code = await self.get_by_code(
            final_code
        )

        if existing_by_code is not None:
            raise ValueError(
                f"Код {final_code} уже використовується."
            )

        normalized_timezone = timezone.strip()

        if not normalized_timezone:
            raise ValueError(
                "Часовий пояс не може бути порожнім."
            )

        store = Store(
            store_number=store_number,
            code=final_code,
            name=self.normalize_optional_text(name),
            city=normalized_city,
            address=normalized_address,
            phone=self.normalize_optional_text(phone),
            format=self.normalize_optional_text(
                store_format
            ),
            timezone=normalized_timezone,
            telegram_topic_id=telegram_topic_id,
            note=self.normalize_optional_text(note),
            bush_id=bush_id,
            cluster_id=cluster_id,
            status=StoreStatus.ACTIVE,
            is_active=True,
        )

        await self.add(
            store,
            flush=True,
        )

        return store

    # ==========================================
    # ОНОВЛЕННЯ ДАНИХ ТТ
    # ==========================================

    async def update_store_details(
        self,
        store: Store,
        *,
        city: str | None = None,
        address: str | None = None,
        name: str | None = None,
        phone: str | None = None,
        store_format: str | None = None,
        timezone: str | None = None,
        telegram_topic_id: int | None = None,
        note: str | None = None,
        allow_kyiv: bool = False,
    ) -> Store:
        """Оновлює основні дані торгової точки."""

        if city is not None:
            normalized_city = (
                self.normalize_required_text(
                    city,
                    field_name="Місто",
                )
            )

            if (
                not allow_kyiv
                and self.is_kyiv_city(
                    normalized_city
                )
            ):
                raise ValueError(
                    "Торгові точки Києва виключені "
                    "із системи контролю."
                )

            store.city = normalized_city

        if address is not None:
            store.address = (
                self.normalize_required_text(
                    address,
                    field_name="Адреса",
                )
            )

        if name is not None:
            store.name = self.normalize_optional_text(
                name
            )

        if phone is not None:
            store.phone = self.normalize_optional_text(
                phone
            )

        if store_format is not None:
            store.format = (
                self.normalize_optional_text(
                    store_format
                )
            )

        if timezone is not None:
            normalized_timezone = timezone.strip()

            if not normalized_timezone:
                raise ValueError(
                    "Часовий пояс не може бути порожнім."
                )

            store.timezone = normalized_timezone

        if telegram_topic_id is not None:
            store.telegram_topic_id = (
                telegram_topic_id
            )

        if note is not None:
            store.note = self.normalize_optional_text(
                note
            )

        self.session.add(store)
        await self.session.flush()

        return store

    async def set_telegram_topic(
        self,
        store: Store,
        *,
        topic_id: int | None,
    ) -> Store:
        """Прив’язує або відв’язує Telegram-тему ТТ."""

        if topic_id is not None and topic_id <= 0:
            raise ValueError(
                "Telegram topic ID повинен бути "
                "більшим за нуль."
            )

        store.telegram_topic_id = topic_id

        self.session.add(store)
        await self.session.flush()

        return store

    # ==========================================
    # КУЩ І КЛАСТЕР
    # ==========================================

    async def move_to_bush(
        self,
        store: Store,
        *,
        bush_id: int | None,
    ) -> Store:
        """
        Переміщує ТТ до іншого куща.

        bush_id=None прибирає ТТ із поточного куща.
        """

        if bush_id is not None and bush_id <= 0:
            raise ValueError(
                "ID куща повинен бути більшим за нуль."
            )

        store.bush_id = bush_id

        self.session.add(store)
        await self.session.flush()

        return store

    async def change_cluster(
        self,
        store: Store,
        *,
        cluster_id: int | None,
    ) -> Store:
        """
        Змінює кластер відкриття.

        cluster_id=None прибирає кластер із ТТ.
        """

        if (
            cluster_id is not None
            and cluster_id <= 0
        ):
            raise ValueError(
                "ID кластера повинен бути більшим за нуль."
            )

        store.cluster_id = cluster_id

        self.session.add(store)
        await self.session.flush()

        return store

    # ==========================================
    # ДЕАКТИВАЦІЯ ТТ
    # ==========================================

    async def deactivate_store(
        self,
        store: Store,
        *,
        deactivated_at: datetime,
        deactivated_by_id: int,
        reason: str,
    ) -> Store:
        """
        Деактивує ТТ без фізичного видалення.

        Після деактивації магазин:
        - не проходить ранковий контроль;
        - не проходить вечірній контроль;
        - не потрапляє у звичайні звіти;
        - зберігається в історії.
        """

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError(
                "Для деактивації ТТ потрібно "
                "вказати причину."
            )

        if deactivated_at.tzinfo is None:
            raise ValueError(
                "deactivated_at повинен містити "
                "часовий пояс."
            )

        if store.status == StoreStatus.INACTIVE:
            raise ValueError(
                f"{store.code} уже деактивована."
            )

        store.status = StoreStatus.INACTIVE
        store.is_active = False

        self.set_optional_model_value(
            store,
            names=(
                "deactivated_at",
            ),
            value=deactivated_at,
        )

        self.set_optional_model_value(
            store,
            names=(
                "deactivated_by_id",
            ),
            value=deactivated_by_id,
        )

        self.set_optional_model_value(
            store,
            names=(
                "deactivation_reason",
            ),
            value=normalized_reason,
        )

        self.clear_temporary_closure_fields(
            store
        )

        self.session.add(store)
        await self.session.flush()

        return store

    async def activate_store(
        self,
        store: Store,
    ) -> Store:
        """Повторно активує деактивовану ТТ."""

        store.status = StoreStatus.ACTIVE
        store.is_active = True

        self.set_optional_model_value(
            store,
            names=(
                "deactivated_at",
                "deactivated_by_id",
                "deactivation_reason",
            ),
            value=None,
            set_all=True,
        )

        self.clear_temporary_closure_fields(
            store
        )

        self.session.add(store)
        await self.session.flush()

        return store

    # ==========================================
    # ТИМЧАСОВЕ ЗАКРИТТЯ
    # ==========================================

    async def temporarily_close_store(
        self,
        store: Store,
        *,
        closed_until: datetime,
        reason: str,
    ) -> Store:
        """
        Тимчасово виключає ТТ із контролю.

        Наприклад:
        - ремонт;
        - переїзд;
        - технічні проблеми;
        - відсутність електроенергії.
        """

        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError(
                "Потрібно вказати причину "
                "тимчасового закриття."
            )

        if closed_until.tzinfo is None:
            raise ValueError(
                "closed_until повинен містити часовий пояс."
            )

        if store.status == StoreStatus.INACTIVE:
            raise ValueError(
                "Не можна тимчасово закрити "
                "деактивовану ТТ."
            )

        store.status = (
            StoreStatus.TEMPORARILY_CLOSED
        )

        # ТТ існує в системі, але не проходить контроль.
        store.is_active = True

        self.set_optional_model_value(
            store,
            names=(
                "temporarily_closed_until",
                "temporary_closed_until",
                "temp_closed_until",
            ),
            value=closed_until,
        )

        self.set_optional_model_value(
            store,
            names=(
                "temporarily_closed_reason",
                "temporary_closure_reason",
                "temp_closed_reason",
            ),
            value=normalized_reason,
        )

        self.session.add(store)
        await self.session.flush()

        return store

    async def restore_temporary_store(
        self,
        store: Store,
    ) -> Store:
        """Повертає тимчасово закриту ТТ до контролю."""

        if store.status == StoreStatus.INACTIVE:
            raise ValueError(
                "Деактивовану ТТ потрібно спочатку "
                "повторно активувати."
            )

        store.status = StoreStatus.ACTIVE
        store.is_active = True

        self.clear_temporary_closure_fields(
            store
        )

        self.session.add(store)
        await self.session.flush()

        return store

    async def get_stores_due_for_restore(
        self,
        *,
        current_time: datetime,
    ) -> list[Store]:
        """
        Повертає ТТ, у яких завершився строк
        тимчасового закриття.
        """

        if current_time.tzinfo is None:
            raise ValueError(
                "current_time повинен містити часовий пояс."
            )

        closed_until_field = (
            self.get_first_model_attribute(
                "temporarily_closed_until",
                "temporary_closed_until",
                "temp_closed_until",
            )
        )

        if closed_until_field is None:
            return []

        statement = (
            select(Store)
            .where(
                Store.status
                == StoreStatus.TEMPORARILY_CLOSED,
                closed_until_field.is_not(None),
                closed_until_field <= current_time,
            )
            .order_by(
                closed_until_field.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # СПИСКИ ТОРГОВИХ ТОЧОК
    # ==========================================

    async def get_controlled_stores(
        self,
    ) -> list[Store]:
        """
        Повертає ТТ, які повинні проходити
        ранковий і вечірній контроль.
        """

        statement = (
            select(Store)
            .where(
                Store.is_active.is_(True),
                Store.status == StoreStatus.ACTIVE,
            )
            .order_by(
                Store.store_number.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        stores = list(
            result.unique().all()
        )

        return [
            store
            for store in stores
            if not self.is_kyiv_city(store.city)
        ]

    async def get_active_stores(
        self,
        *,
        include_temporarily_closed: bool = False,
    ) -> list[Store]:
        """Повертає активні записи ТТ."""

        allowed_statuses = [
            StoreStatus.ACTIVE,
        ]

        if include_temporarily_closed:
            allowed_statuses.append(
                StoreStatus.TEMPORARILY_CLOSED
            )

        statement = (
            select(Store)
            .where(
                Store.is_active.is_(True),
                Store.status.in_(allowed_statuses),
            )
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

    async def get_inactive_stores(
        self,
    ) -> list[Store]:
        """Повертає деактивовані ТТ."""

        statement = (
            select(Store)
            .where(
                or_(
                    Store.is_active.is_(False),
                    Store.status
                    == StoreStatus.INACTIVE,
                )
            )
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

    async def get_temporarily_closed_stores(
        self,
    ) -> list[Store]:
        """Повертає тимчасово закриті ТТ."""

        statement = (
            select(Store)
            .where(
                Store.status
                == StoreStatus.TEMPORARILY_CLOSED
            )
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

    async def get_by_bush(
        self,
        bush_id: int,
        *,
        active_only: bool = True,
    ) -> list[Store]:
        """Повертає ТТ конкретного куща."""

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

    async def get_by_cluster(
        self,
        cluster_id: int,
        *,
        active_only: bool = True,
    ) -> list[Store]:
        """Повертає ТТ конкретного кластера."""

        conditions = [
            Store.cluster_id == cluster_id,
        ]

        if active_only:
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

    async def get_by_city(
        self,
        city: str,
        *,
        active_only: bool = True,
    ) -> list[Store]:
        """Повертає ТТ конкретного міста."""

        normalized_city = (
            self.normalize_required_text(
                city,
                field_name="Місто",
            )
        )

        conditions = [
            func.lower(Store.city)
            == normalized_city.lower(),
        ]

        if active_only:
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

    async def get_without_bush(
        self,
        *,
        active_only: bool = True,
    ) -> list[Store]:
        """Повертає ТТ, які ще не прив’язані до куща."""

        conditions = [
            Store.bush_id.is_(None),
        ]

        if active_only:
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

    async def get_without_cluster(
        self,
        *,
        active_only: bool = True,
    ) -> list[Store]:
        """Повертає ТТ без кластера відкриття."""

        conditions = [
            Store.cluster_id.is_(None),
        ]

        if active_only:
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

    async def get_without_telegram_topic(
        self,
    ) -> list[Store]:
        """Повертає активні ТТ без Telegram-теми."""

        statement = (
            select(Store)
            .where(
                Store.is_active.is_(True),
                Store.status == StoreStatus.ACTIVE,
                Store.telegram_topic_id.is_(None),
            )
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

    # ==========================================
    # ПОШУК
    # ==========================================

    async def search(
        self,
        query: str,
        *,
        active_only: bool = False,
        bush_id: int | None = None,
        cluster_id: int | None = None,
        limit: int = 50,
    ) -> list[Store]:
        """
        Шукає ТТ за:

        - кодом;
        - номером;
        - назвою;
        - містом;
        - адресою;
        - телефоном.
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

        compact_query = (
            normalized_query
            .upper()
            .replace(" ", "")
            .replace("_", "-")
        )

        code_pattern = f"%{compact_query}%"

        conditions = [
            or_(
                Store.code.ilike(code_pattern),
                cast(
                    Store.store_number,
                    String,
                ).ilike(search_pattern),
                Store.name.ilike(search_pattern),
                Store.city.ilike(search_pattern),
                Store.address.ilike(search_pattern),
                Store.phone.ilike(search_pattern),
            )
        ]

        if active_only:
            conditions.extend(
                [
                    Store.is_active.is_(True),
                    Store.status == StoreStatus.ACTIVE,
                ]
            )

        if bush_id is not None:
            conditions.append(
                Store.bush_id == bush_id
            )

        if cluster_id is not None:
            conditions.append(
                Store.cluster_id == cluster_id
            )

        statement = (
            select(Store)
            .where(*conditions)
            .order_by(
                Store.store_number.asc()
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

    async def count_by_status(
        self,
    ) -> dict[StoreStatus, int]:
        """Кількість ТТ за статусами."""

        statement = (
            select(
                Store.status,
                func.count(Store.id),
            )
            .group_by(Store.status)
        )

        result = await self.session.execute(
            statement
        )

        counts: dict[StoreStatus, int] = {
            status: 0
            for status in StoreStatus
        }

        for status, count in result.all():
            counts[status] = int(count)

        return counts

    async def count_by_city(
        self,
        *,
        active_only: bool = True,
    ) -> dict[str, int]:
        """Кількість торгових точок по містах."""

        conditions = []

        if active_only:
            conditions.extend(
                [
                    Store.is_active.is_(True),
                    Store.status == StoreStatus.ACTIVE,
                ]
            )

        statement = (
            select(
                Store.city,
                func.count(Store.id),
            )
            .where(*conditions)
            .group_by(Store.city)
            .order_by(
                func.count(Store.id).desc(),
                Store.city.asc(),
            )
        )

        result = await self.session.execute(
            statement
        )

        return {
            str(city): int(count)
            for city, count in result.all()
            if not self.is_kyiv_city(str(city))
        }

    async def count_by_bush(
        self,
        *,
        active_only: bool = True,
    ) -> dict[int | None, int]:
        """Кількість ТТ по кущах."""

        conditions = []

        if active_only:
            conditions.extend(
                [
                    Store.is_active.is_(True),
                    Store.status == StoreStatus.ACTIVE,
                ]
            )

        statement = (
            select(
                Store.bush_id,
                func.count(Store.id),
            )
            .where(*conditions)
            .group_by(Store.bush_id)
        )

        result = await self.session.execute(
            statement
        )

        return {
            bush_id: int(count)
            for bush_id, count in result.all()
        }

    async def count_by_cluster(
        self,
        *,
        active_only: bool = True,
    ) -> dict[int | None, int]:
        """Кількість ТТ по кластерах."""

        conditions = []

        if active_only:
            conditions.extend(
                [
                    Store.is_active.is_(True),
                    Store.status == StoreStatus.ACTIVE,
                ]
            )

        statement = (
            select(
                Store.cluster_id,
                func.count(Store.id),
            )
            .where(*conditions)
            .group_by(Store.cluster_id)
        )

        result = await self.session.execute(
            statement
        )

        return {
            cluster_id: int(count)
            for cluster_id, count in result.all()
        }

    # ==========================================
    # НОРМАЛІЗАЦІЯ
    # ==========================================

    @staticmethod
    def build_store_code(
        store_number: int,
    ) -> str:
        """Створює код ТТ у форматі SB-76."""

        if store_number <= 0:
            raise ValueError(
                "Номер ТТ повинен бути більшим за нуль."
            )

        return f"SB-{store_number}"

    @classmethod
    def normalize_code(
        cls,
        code: str,
    ) -> str:
        """Нормалізує введений код магазину."""

        normalized_code = (
            str(code)
            .strip()
            .upper()
            .replace(" ", "")
            .replace("_", "-")
        )

        if not normalized_code:
            raise ValueError(
                "Код торгової точки не може бути порожнім."
            )

        if normalized_code.isdigit():
            return cls.build_store_code(
                int(normalized_code)
            )

        if normalized_code.startswith("SB"):
            number_part = (
                normalized_code
                .removeprefix("SB")
                .removeprefix("-")
            )

            if number_part.isdigit():
                return cls.build_store_code(
                    int(number_part)
                )

        return normalized_code

    @classmethod
    def is_kyiv_city(
        cls,
        city: str,
    ) -> bool:
        """Перевіряє, чи є місто Києвом."""

        normalized_city = (
            city.strip()
            .lower()
            .replace(".", "")
            .replace("-", " ")
        )

        normalized_city = " ".join(
            normalized_city.split()
        )

        return normalized_city in cls.KYIV_CITY_NAMES

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
    ) -> str:
        """Нормалізує обов’язковий текст."""

        normalized_value = " ".join(
            value.strip().split()
        )

        if not normalized_value:
            raise ValueError(
                f"{field_name} не може бути порожнім."
            )

        return normalized_value

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

    # ==========================================
    # СУМІСНІСТЬ ІЗ ПОЛЯМИ МОДЕЛІ
    # ==========================================

    @staticmethod
    def set_optional_model_value(
        store: Store,
        *,
        names: tuple[str, ...],
        value: Any,
        set_all: bool = False,
    ) -> bool:
        """
        Встановлює значення лише для полів,
        які реально присутні у моделі Store.
        """

        mapper = inspect(type(store))

        available_fields = {
            attribute.key
            for attribute in mapper.attrs
        }

        was_set = False

        for field_name in names:
            if field_name not in available_fields:
                continue

            setattr(
                store,
                field_name,
                value,
            )

            was_set = True

            if not set_all:
                break

        return was_set

    @staticmethod
    def get_first_model_attribute(
        *names: str,
    ) -> InstrumentedAttribute[Any] | None:
        """
        Повертає перше знайдене поле моделі Store.
        """

        for field_name in names:
            model_attribute = getattr(
                Store,
                field_name,
                None,
            )

            if isinstance(
                model_attribute,
                InstrumentedAttribute,
            ):
                return model_attribute

        return None

    @classmethod
    def clear_temporary_closure_fields(
        cls,
        store: Store,
    ) -> None:
        """Очищає дані тимчасового закриття."""

        cls.set_optional_model_value(
            store,
            names=(
                "temporarily_closed_until",
                "temporary_closed_until",
                "temp_closed_until",
            ),
            value=None,
            set_all=True,
        )

        cls.set_optional_model_value(
            store,
            names=(
                "temporarily_closed_reason",
                "temporary_closure_reason",
                "temp_closed_reason",
            ),
            value=None,
            set_all=True,
        )