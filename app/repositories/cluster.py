from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.cluster import Cluster
from app.database.models.enums import StoreStatus
from app.database.models.store import Store
from app.repositories.base import BaseRepository


class ClusterRepository(BaseRepository[Cluster]):
    """
    Репозиторій часових кластерів торгових точок.

    Стандартні кластери:

    - 07:00;
    - 08:00;
    - 09:00;
    - 10:00.

    Кожен кластер має:
    - час відкриття;
    - контрольний дедлайн;
    - стандартний час закриття;
    - дедлайн вечірнього звіту.
    """

    model = Cluster

    DEFAULT_OPENING_HOURS: tuple[int, ...] = (
        7,
        8,
        9,
        10,
    )

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(session)

    # ==========================================
    # ПОШУК КЛАСТЕРА
    # ==========================================

    async def get_by_name(
        self,
        name: str,
    ) -> Cluster | None:
        """Повертає кластер за точною назвою."""

        normalized_name = self.normalize_name(
            name
        )

        statement = (
            select(Cluster)
            .where(
                func.lower(Cluster.name)
                == normalized_name.lower()
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_name_or_raise(
        self,
        name: str,
    ) -> Cluster:
        """Повертає кластер або викликає помилку."""

        cluster = await self.get_by_name(name)

        if cluster is None:
            raise ValueError(
                f"Кластер «{name.strip()}» не знайдено."
            )

        return cluster

    async def get_by_opening_time(
        self,
        opening_time: time,
    ) -> Cluster | None:
        """Повертає кластер за часом відкриття."""

        normalized_time = self.normalize_time(
            opening_time
        )

        statement = (
            select(Cluster)
            .where(
                Cluster.opening_time
                == normalized_time
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_opening_hour(
        self,
        opening_hour: int,
    ) -> Cluster | None:
        """Повертає кластер за годиною відкриття."""

        if opening_hour < 0 or opening_hour > 23:
            raise ValueError(
                "Година відкриття повинна бути "
                "в межах від 0 до 23."
            )

        return await self.get_by_opening_time(
            time(
                hour=opening_hour,
                minute=0,
            )
        )

    async def get_active_by_id(
        self,
        cluster_id: int,
    ) -> Cluster | None:
        """Повертає активний кластер за ID."""

        statement = (
            select(Cluster)
            .where(
                Cluster.id == cluster_id,
                Cluster.is_active.is_(True),
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_for_update(
        self,
        cluster_id: int,
    ) -> Cluster | None:
        """Завантажує кластер із блокуванням рядка."""

        statement = (
            select(Cluster)
            .where(
                Cluster.id == cluster_id
            )
            .with_for_update()
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    # ==========================================
    # СТВОРЕННЯ КЛАСТЕРА
    # ==========================================

    async def create_cluster(
        self,
        *,
        opening_time: time,
        opening_control_deadline: time,
        name: str | None = None,
        default_closing_time: time | None = None,
        default_closing_control_deadline: time | None = None,
        note: str | None = None,
    ) -> Cluster:
        """Створює новий часовий кластер."""

        normalized_opening_time = (
            self.normalize_time(
                opening_time
            )
        )

        normalized_opening_deadline = (
            self.normalize_time(
                opening_control_deadline
            )
        )

        normalized_closing_time = (
            self.normalize_time(
                default_closing_time
            )
            if default_closing_time is not None
            else None
        )

        normalized_closing_deadline = (
            self.normalize_time(
                default_closing_control_deadline
            )
            if (
                default_closing_control_deadline
                is not None
            )
            else None
        )

        self.validate_schedule(
            opening_time=normalized_opening_time,
            opening_control_deadline=(
                normalized_opening_deadline
            ),
            default_closing_time=(
                normalized_closing_time
            ),
            default_closing_control_deadline=(
                normalized_closing_deadline
            ),
        )

        existing_by_time = (
            await self.get_by_opening_time(
                normalized_opening_time
            )
        )

        if existing_by_time is not None:
            raise ValueError(
                "Кластер із часом відкриття "
                f"{normalized_opening_time:%H:%M} "
                "уже існує."
            )

        final_name = (
            self.normalize_name(name)
            if name is not None
            else self.build_default_name(
                normalized_opening_time
            )
        )

        existing_by_name = await self.get_by_name(
            final_name
        )

        if existing_by_name is not None:
            raise ValueError(
                f"Кластер із назвою «{final_name}» "
                "уже існує."
            )

        cluster = Cluster(
            name=final_name,
            opening_time=normalized_opening_time,
            opening_control_deadline=(
                normalized_opening_deadline
            ),
            default_closing_time=(
                normalized_closing_time
            ),
            default_closing_control_deadline=(
                normalized_closing_deadline
            ),
            is_active=True,
            note=self.normalize_optional_text(
                note
            ),
        )

        await self.add(
            cluster,
            flush=True,
        )

        return cluster

    async def create_default_clusters(
        self,
        *,
        opening_deadline_minutes: int = 10,
        default_closing_time: time | None = None,
        closing_deadline_minutes: int = 10,
    ) -> list[Cluster]:
        """
        Створює відсутні стандартні кластери:

        - 07:00;
        - 08:00;
        - 09:00;
        - 10:00.

        Уже створені кластери повторно не додаються.
        """

        if (
            opening_deadline_minutes < 0
            or opening_deadline_minutes > 180
        ):
            raise ValueError(
                "Дедлайн відкриття повинен бути "
                "в межах від 0 до 180 хвилин."
            )

        if (
            closing_deadline_minutes < 0
            or closing_deadline_minutes > 180
        ):
            raise ValueError(
                "Дедлайн закриття повинен бути "
                "в межах від 0 до 180 хвилин."
            )

        closing_deadline: time | None = None

        if default_closing_time is not None:
            closing_deadline = self.add_minutes(
                default_closing_time,
                closing_deadline_minutes,
            )

        created_clusters: list[Cluster] = []

        for opening_hour in self.DEFAULT_OPENING_HOURS:
            opening_time_value = time(
                hour=opening_hour,
                minute=0,
            )

            existing_cluster = (
                await self.get_by_opening_time(
                    opening_time_value
                )
            )

            if existing_cluster is not None:
                continue

            opening_deadline = self.add_minutes(
                opening_time_value,
                opening_deadline_minutes,
            )

            cluster = await self.create_cluster(
                name=(
                    f"Кластер "
                    f"{opening_time_value:%H:%M}"
                ),
                opening_time=opening_time_value,
                opening_control_deadline=(
                    opening_deadline
                ),
                default_closing_time=(
                    default_closing_time
                ),
                default_closing_control_deadline=(
                    closing_deadline
                ),
            )

            created_clusters.append(cluster)

        return created_clusters

    # ==========================================
    # РЕДАГУВАННЯ
    # ==========================================

    async def update_cluster(
        self,
        cluster: Cluster,
        *,
        name: str | None = None,
        opening_time: time | None = None,
        opening_control_deadline: time | None = None,
        default_closing_time: time | None = None,
        default_closing_control_deadline: time | None = None,
        note: str | None = None,
        update_closing_time: bool = False,
        update_closing_deadline: bool = False,
        update_note: bool = False,
    ) -> Cluster:
        """
        Оновлює налаштування кластера.

        update_closing_time=True дозволяє
        очистити стандартний час закриття через None.

        update_closing_deadline=True дозволяє
        очистити дедлайн закриття через None.
        """

        final_opening_time = (
            self.normalize_time(opening_time)
            if opening_time is not None
            else cluster.opening_time
        )

        final_opening_deadline = (
            self.normalize_time(
                opening_control_deadline
            )
            if opening_control_deadline is not None
            else cluster.opening_control_deadline
        )

        final_closing_time = (
            self.normalize_time(
                default_closing_time
            )
            if (
                update_closing_time
                and default_closing_time is not None
            )
            else (
                None
                if update_closing_time
                else cluster.default_closing_time
            )
        )

        final_closing_deadline = (
            self.normalize_time(
                default_closing_control_deadline
            )
            if (
                update_closing_deadline
                and default_closing_control_deadline
                is not None
            )
            else (
                None
                if update_closing_deadline
                else (
                    cluster
                    .default_closing_control_deadline
                )
            )
        )

        self.validate_schedule(
            opening_time=final_opening_time,
            opening_control_deadline=(
                final_opening_deadline
            ),
            default_closing_time=(
                final_closing_time
            ),
            default_closing_control_deadline=(
                final_closing_deadline
            ),
        )

        if opening_time is not None:
            existing_by_time = (
                await self.get_by_opening_time(
                    final_opening_time
                )
            )

            if (
                existing_by_time is not None
                and existing_by_time.id != cluster.id
            ):
                raise ValueError(
                    "Інший кластер уже використовує "
                    f"час {final_opening_time:%H:%M}."
                )

        if name is not None:
            normalized_name = self.normalize_name(
                name
            )

            existing_by_name = (
                await self.get_by_name(
                    normalized_name
                )
            )

            if (
                existing_by_name is not None
                and existing_by_name.id != cluster.id
            ):
                raise ValueError(
                    f"Назва «{normalized_name}» "
                    "уже використовується."
                )

            cluster.name = normalized_name

        cluster.opening_time = (
            final_opening_time
        )

        cluster.opening_control_deadline = (
            final_opening_deadline
        )

        if update_closing_time:
            cluster.default_closing_time = (
                final_closing_time
            )

        if update_closing_deadline:
            cluster.default_closing_control_deadline = (
                final_closing_deadline
            )

        if update_note:
            cluster.note = (
                self.normalize_optional_text(
                    note
                )
            )

        self.session.add(cluster)
        await self.session.flush()

        return cluster

    async def set_opening_deadline_minutes(
        self,
        cluster: Cluster,
        *,
        deadline_minutes: int,
    ) -> Cluster:
        """
        Встановлює дедлайн відносно часу відкриття.

        Приклад:
        08:00 + 10 хвилин = 08:10.
        """

        if (
            deadline_minutes < 0
            or deadline_minutes > 180
        ):
            raise ValueError(
                "Дедлайн повинен бути "
                "в межах від 0 до 180 хвилин."
            )

        cluster.opening_control_deadline = (
            self.add_minutes(
                cluster.opening_time,
                deadline_minutes,
            )
        )

        self.session.add(cluster)
        await self.session.flush()

        return cluster

    # ==========================================
    # АКТИВАЦІЯ І ДЕАКТИВАЦІЯ
    # ==========================================

    async def activate_cluster(
        self,
        cluster: Cluster,
    ) -> Cluster:
        """Активує часовий кластер."""

        cluster.is_active = True

        self.session.add(cluster)
        await self.session.flush()

        return cluster

    async def deactivate_cluster(
        self,
        cluster: Cluster,
        *,
        allow_with_active_stores: bool = False,
    ) -> Cluster:
        """
        Деактивує кластер.

        За замовчуванням кластер не можна вимкнути,
        доки до нього прив’язані активні ТТ.
        """

        if not allow_with_active_stores:
            stores_count = (
                await self.count_active_stores(
                    cluster.id
                )
            )

            if stores_count > 0:
                raise ValueError(
                    "Кластер не можна деактивувати, "
                    f"оскільки він містить "
                    f"{stores_count} активних ТТ."
                )

        cluster.is_active = False

        self.session.add(cluster)
        await self.session.flush()

        return cluster

    # ==========================================
    # СПИСКИ КЛАСТЕРІВ
    # ==========================================

    async def get_active_clusters(
        self,
    ) -> list[Cluster]:
        """Повертає активні кластери за часом."""

        statement = (
            select(Cluster)
            .where(
                Cluster.is_active.is_(True)
            )
            .order_by(
                Cluster.opening_time.asc(),
                Cluster.id.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_inactive_clusters(
        self,
    ) -> list[Cluster]:
        """Повертає неактивні кластери."""

        statement = (
            select(Cluster)
            .where(
                Cluster.is_active.is_(False)
            )
            .order_by(
                Cluster.opening_time.asc(),
                Cluster.id.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_clusters_with_stores(
        self,
    ) -> list[Cluster]:
        """Повертає активні кластери з активними ТТ."""

        active_store_exists = (
            select(Store.id)
            .where(
                Store.cluster_id == Cluster.id,
                Store.is_active.is_(True),
                Store.status == StoreStatus.ACTIVE,
            )
            .exists()
        )

        statement = (
            select(Cluster)
            .where(
                Cluster.is_active.is_(True),
                active_store_exists,
            )
            .order_by(
                Cluster.opening_time.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_clusters_without_stores(
        self,
    ) -> list[Cluster]:
        """Повертає активні кластери без активних ТТ."""

        active_store_exists = (
            select(Store.id)
            .where(
                Store.cluster_id == Cluster.id,
                Store.is_active.is_(True),
                Store.status == StoreStatus.ACTIVE,
            )
            .exists()
        )

        statement = (
            select(Cluster)
            .where(
                Cluster.is_active.is_(True),
                ~active_store_exists,
            )
            .order_by(
                Cluster.opening_time.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # КОНТРОЛЬ ЧАСУ
    # ==========================================

    async def get_opening_clusters_for_minute(
        self,
        *,
        local_time: time,
    ) -> list[Cluster]:
        """
        Повертає кластери, які повинні відкритися
        саме в цю хвилину.

        Секунди не враховуються.
        """

        normalized_time = self.normalize_time(
            local_time
        )

        statement = (
            select(Cluster)
            .where(
                Cluster.is_active.is_(True),
                Cluster.opening_time
                == normalized_time,
            )
            .order_by(
                Cluster.opening_time.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_deadline_clusters_for_minute(
        self,
        *,
        local_time: time,
    ) -> list[Cluster]:
        """
        Повертає кластери, у яких саме зараз
        настав контрольний дедлайн.
        """

        normalized_time = self.normalize_time(
            local_time
        )

        statement = (
            select(Cluster)
            .where(
                Cluster.is_active.is_(True),
                Cluster.opening_control_deadline
                == normalized_time,
            )
            .order_by(
                Cluster.opening_control_deadline.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_clusters_waiting_for_opening(
        self,
        *,
        local_time: time,
    ) -> list[Cluster]:
        """
        Повертає кластери, для яких уже настав
        час відкриття, але дедлайн ще не минув.
        """

        normalized_time = self.normalize_time(
            local_time
        )

        statement = (
            select(Cluster)
            .where(
                Cluster.is_active.is_(True),
                Cluster.opening_time
                <= normalized_time,
                Cluster.opening_control_deadline
                >= normalized_time,
            )
            .order_by(
                Cluster.opening_time.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_clusters_past_deadline(
        self,
        *,
        local_time: time,
    ) -> list[Cluster]:
        """
        Повертає кластери, контрольний дедлайн
        яких уже минув.
        """

        normalized_time = self.normalize_time(
            local_time
        )

        statement = (
            select(Cluster)
            .where(
                Cluster.is_active.is_(True),
                Cluster.opening_control_deadline
                < normalized_time,
            )
            .order_by(
                Cluster.opening_control_deadline.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ТОРГОВІ ТОЧКИ КЛАСТЕРА
    # ==========================================

    async def get_stores(
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

    async def count_stores(
        self,
        cluster_id: int,
        *,
        active_only: bool = False,
    ) -> int:
        """Підраховує ТТ конкретного кластера."""

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
            select(func.count(Store.id))
            .where(*conditions)
        )

        result = await self.session.scalar(
            statement
        )

        return int(result or 0)

    async def count_active_stores(
        self,
        cluster_id: int,
    ) -> int:
        """Підраховує активні ТТ кластера."""

        return await self.count_stores(
            cluster_id,
            active_only=True,
        )

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def get_statistics(
        self,
    ) -> list[dict[str, int | str | bool]]:
        """
        Повертає статистику по кластерах:

        - час відкриття;
        - дедлайн;
        - кількість активних ТТ.
        """

        stores_subquery = (
            select(
                Store.cluster_id.label(
                    "cluster_id"
                ),
                func.count(Store.id).label(
                    "stores_count"
                ),
            )
            .where(
                Store.is_active.is_(True),
                Store.status == StoreStatus.ACTIVE,
            )
            .group_by(
                Store.cluster_id
            )
            .subquery()
        )

        statement = (
            select(
                Cluster.id,
                Cluster.name,
                Cluster.opening_time,
                Cluster.opening_control_deadline,
                Cluster.is_active,
                func.coalesce(
                    stores_subquery.c.stores_count,
                    0,
                ).label("stores_count"),
            )
            .outerjoin(
                stores_subquery,
                stores_subquery.c.cluster_id
                == Cluster.id,
            )
            .order_by(
                Cluster.opening_time.asc()
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
                    "cluster_id": int(row["id"]),
                    "name": str(row["name"]),
                    "opening_time": (
                        row["opening_time"]
                        .strftime("%H:%M")
                    ),
                    "deadline": (
                        row[
                            "opening_control_deadline"
                        ].strftime("%H:%M")
                    ),
                    "stores_count": int(
                        row["stores_count"]
                    ),
                    "is_active": bool(
                        row["is_active"]
                    ),
                }
            )

        return statistics

    # ==========================================
    # ПОШУК
    # ==========================================

    async def search(
        self,
        query: str,
        *,
        active_only: bool = False,
        limit: int = 50,
    ) -> list[Cluster]:
        """Шукає кластер за назвою або приміткою."""

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
                Cluster.name.ilike(
                    search_pattern
                ),
                Cluster.note.ilike(
                    search_pattern
                ),
            )
        ]

        if active_only:
            conditions.append(
                Cluster.is_active.is_(True)
            )

        statement = (
            select(Cluster)
            .where(*conditions)
            .order_by(
                Cluster.opening_time.asc()
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
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def normalize_time(
        value: time,
    ) -> time:
        """Прибирає секунди й мікросекунди."""

        return value.replace(
            second=0,
            microsecond=0,
            tzinfo=None,
        )

    @staticmethod
    def add_minutes(
        source_time: time,
        minutes: int,
    ) -> time:
        """Додає хвилини до часу."""

        if minutes < 0:
            raise ValueError(
                "Кількість хвилин не може бути від’ємною."
            )

        normalized_time = (
            ClusterRepository.normalize_time(
                source_time
            )
        )

        base_datetime = datetime.combine(
            date(2000, 1, 1),
            normalized_time,
        )

        result_datetime = (
            base_datetime
            + timedelta(minutes=minutes)
        )

        if result_datetime.date() != base_datetime.date():
            raise ValueError(
                "Розрахований дедлайн переходить "
                "на наступну добу."
            )

        return result_datetime.time().replace(
            second=0,
            microsecond=0,
        )

    @staticmethod
    def validate_schedule(
        *,
        opening_time: time,
        opening_control_deadline: time,
        default_closing_time: time | None,
        default_closing_control_deadline: time | None,
    ) -> None:
        """Перевіряє правильність часу кластера."""

        if opening_control_deadline < opening_time:
            raise ValueError(
                "Дедлайн відкриття не може бути "
                "раніше часу відкриття."
            )

        if (
            default_closing_time is None
            and default_closing_control_deadline
            is not None
        ):
            raise ValueError(
                "Не можна вказати дедлайн закриття "
                "без часу закриття."
            )

        if (
            default_closing_time is not None
            and default_closing_control_deadline
            is None
        ):
            raise ValueError(
                "Для часу закриття потрібно вказати "
                "контрольний дедлайн."
            )

        if (
            default_closing_time is not None
            and default_closing_control_deadline
            is not None
            and default_closing_control_deadline
            < default_closing_time
        ):
            raise ValueError(
                "Дедлайн закриття не може бути "
                "раніше часу закриття."
            )

    @staticmethod
    def normalize_name(
        name: str,
    ) -> str:
        """Нормалізує назву кластера."""

        normalized_name = " ".join(
            name.strip().split()
        )

        if not normalized_name:
            raise ValueError(
                "Назва кластера не може бути порожньою."
            )

        if len(normalized_name) > 100:
            raise ValueError(
                "Назва кластера занадто довга."
            )

        return normalized_name

    @staticmethod
    def build_default_name(
        opening_time: time,
    ) -> str:
        """Створює назву на основі часу."""

        return (
            f"Кластер "
            f"{opening_time.strftime('%H:%M')}"
        )

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