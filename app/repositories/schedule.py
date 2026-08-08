from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models.bush import Bush
from app.database.models.cluster import Cluster
from app.database.models.enums import (
    ScheduleExceptionType,
    StoreStatus,
)
from app.database.models.schedule import (
    ScheduleException,
    StoreSchedule,
)
from app.database.models.store import Store


@dataclass(slots=True)
class EffectiveSchedule:
    """
    Фактичний графік торгової точки
    на конкретну бізнес-дату.
    """

    store_id: int
    business_date: date

    is_working_day: bool
    source: str

    opening_time: time | None = None
    opening_control_deadline: time | None = None

    closing_time: time | None = None
    closing_control_deadline: time | None = None

    exception_id: int | None = None
    reason: str | None = None

    @property
    def requires_opening(self) -> bool:
        """Чи повинна ТТ проходити ранковий чекін."""

        return (
            self.is_working_day
            and self.opening_time is not None
            and self.opening_control_deadline is not None
        )

    @property
    def requires_closing(self) -> bool:
        """Чи повинна ТТ подати вечірній звіт."""

        return (
            self.is_working_day
            and self.closing_time is not None
            and self.closing_control_deadline is not None
        )

    @property
    def opening_time_text(self) -> str | None:
        if self.opening_time is None:
            return None

        return self.opening_time.strftime("%H:%M")

    @property
    def opening_deadline_text(self) -> str | None:
        if self.opening_control_deadline is None:
            return None

        return self.opening_control_deadline.strftime(
            "%H:%M"
        )

    @property
    def closing_time_text(self) -> str | None:
        if self.closing_time is None:
            return None

        return self.closing_time.strftime("%H:%M")

    @property
    def closing_deadline_text(self) -> str | None:
        if self.closing_control_deadline is None:
            return None

        return self.closing_control_deadline.strftime(
            "%H:%M"
        )


class ScheduleRepository:
    """
    Репозиторій графіків торгових точок.

    Пріоритет визначення графіка:

    1. Деактивована або тимчасово закрита ТТ.
    2. Виняток для конкретної ТТ.
    3. Виняток для куща.
    4. Тижневий графік конкретної ТТ.
    5. Стандартний графік кластера.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    # ==========================================
    # ТИЖНЕВИЙ ГРАФІК
    # ==========================================

    async def get_weekday_schedule(
        self,
        *,
        store_id: int,
        weekday: int,
        for_update: bool = False,
    ) -> StoreSchedule | None:
        """
        Повертає тижневий графік ТТ.

        weekday:
        0 — понеділок;
        1 — вівторок;
        2 — середа;
        3 — четвер;
        4 — п’ятниця;
        5 — субота;
        6 — неділя.
        """

        self.validate_weekday(weekday)

        statement = (
            select(StoreSchedule)
            .where(
                StoreSchedule.store_id == store_id,
                StoreSchedule.weekday == weekday,
            )
            .limit(1)
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_weekly_schedule(
        self,
        store_id: int,
    ) -> list[StoreSchedule]:
        """Повертає весь тижневий графік ТТ."""

        statement = (
            select(StoreSchedule)
            .where(
                StoreSchedule.store_id == store_id
            )
            .order_by(
                StoreSchedule.weekday.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def upsert_weekday_schedule(
        self,
        *,
        store_id: int,
        weekday: int,
        is_working_day: bool,
        opening_time: time | None = None,
        opening_control_deadline: time | None = None,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
    ) -> tuple[StoreSchedule, bool]:
        """
        Створює або оновлює графік одного дня.

        Повертає:
        - графік;
        - True, якщо запис створено;
        - False, якщо запис оновлено.
        """

        self.validate_weekday(weekday)

        normalized_values = self.validate_schedule_values(
            is_working_day=is_working_day,
            opening_time=opening_time,
            opening_control_deadline=(
                opening_control_deadline
            ),
            closing_time=closing_time,
            closing_control_deadline=(
                closing_control_deadline
            ),
        )

        schedule = await self.get_weekday_schedule(
            store_id=store_id,
            weekday=weekday,
            for_update=True,
        )

        was_created = schedule is None

        if schedule is None:
            schedule = StoreSchedule(
                store_id=store_id,
                weekday=weekday,
                is_working_day=is_working_day,
                opening_time=normalized_values[
                    "opening_time"
                ],
                opening_control_deadline=(
                    normalized_values[
                        "opening_control_deadline"
                    ]
                ),
                closing_time=normalized_values[
                    "closing_time"
                ],
                closing_control_deadline=(
                    normalized_values[
                        "closing_control_deadline"
                    ]
                ),
            )

            self.session.add(schedule)

        else:
            schedule.is_working_day = (
                is_working_day
            )

            schedule.opening_time = (
                normalized_values["opening_time"]
            )

            schedule.opening_control_deadline = (
                normalized_values[
                    "opening_control_deadline"
                ]
            )

            schedule.closing_time = (
                normalized_values["closing_time"]
            )

            schedule.closing_control_deadline = (
                normalized_values[
                    "closing_control_deadline"
                ]
            )

            self.session.add(schedule)

        await self.session.flush()

        return schedule, was_created

    async def set_weekday_as_day_off(
        self,
        *,
        store_id: int,
        weekday: int,
    ) -> tuple[StoreSchedule, bool]:
        """Встановлює постійний вихідний день."""

        return await self.upsert_weekday_schedule(
            store_id=store_id,
            weekday=weekday,
            is_working_day=False,
        )

    async def copy_weekday_schedule(
        self,
        *,
        store_id: int,
        source_weekday: int,
        target_weekdays: Iterable[int],
    ) -> list[StoreSchedule]:
        """
        Копіює графік одного дня на інші дні.

        Наприклад, графік понеділка можна
        скопіювати на вівторок–п’ятницю.
        """

        self.validate_weekday(
            source_weekday
        )

        source = await self.get_weekday_schedule(
            store_id=store_id,
            weekday=source_weekday,
        )

        if source is None:
            raise ValueError(
                "Графік вихідного дня для копіювання "
                "не знайдено."
            )

        normalized_target_days = sorted(
            set(target_weekdays)
        )

        if not normalized_target_days:
            return []

        schedules: list[StoreSchedule] = []

        for weekday in normalized_target_days:
            self.validate_weekday(weekday)

            if weekday == source_weekday:
                continue

            schedule, _ = (
                await self.upsert_weekday_schedule(
                    store_id=store_id,
                    weekday=weekday,
                    is_working_day=(
                        source.is_working_day
                    ),
                    opening_time=(
                        source.opening_time
                    ),
                    opening_control_deadline=(
                        source
                        .opening_control_deadline
                    ),
                    closing_time=(
                        source.closing_time
                    ),
                    closing_control_deadline=(
                        source
                        .closing_control_deadline
                    ),
                )
            )

            schedules.append(schedule)

        return schedules

    async def delete_weekday_schedule(
        self,
        *,
        store_id: int,
        weekday: int,
    ) -> bool:
        """Фізично видаляє запис тижневого графіка."""

        self.validate_weekday(weekday)

        schedule = await self.get_weekday_schedule(
            store_id=store_id,
            weekday=weekday,
            for_update=True,
        )

        if schedule is None:
            return False

        await self.session.delete(schedule)
        await self.session.flush()

        return True

    async def delete_store_weekly_schedule(
        self,
        *,
        store_id: int,
    ) -> int:
        """Видаляє весь індивідуальний графік ТТ."""

        statement = delete(
            StoreSchedule
        ).where(
            StoreSchedule.store_id == store_id
        )

        result = await self.session.execute(
            statement
        )

        await self.session.flush()

        return int(result.rowcount or 0)

    # ==========================================
    # ВИНЯТКИ ГРАФІКА
    # ==========================================

    async def get_store_exception(
        self,
        *,
        store_id: int,
        exception_date: date,
        for_update: bool = False,
    ) -> ScheduleException | None:
        """Повертає виняток конкретної ТТ на дату."""

        statement = (
            select(ScheduleException)
            .where(
                ScheduleException.store_id == store_id,
                ScheduleException.exception_date
                == exception_date,
            )
            .limit(1)
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_bush_exception(
        self,
        *,
        bush_id: int,
        exception_date: date,
        for_update: bool = False,
    ) -> ScheduleException | None:
        """Повертає виняток цілого куща на дату."""

        statement = (
            select(ScheduleException)
            .where(
                ScheduleException.bush_id == bush_id,
                ScheduleException.exception_date
                == exception_date,
                ScheduleException.store_id.is_(None),
            )
            .limit(1)
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_exception_by_id(
        self,
        exception_id: int,
        *,
        for_update: bool = False,
    ) -> ScheduleException | None:
        """Повертає виняток за внутрішнім ID."""

        statement = (
            select(ScheduleException)
            .options(
                selectinload(
                    ScheduleException.store
                ),
                selectinload(
                    ScheduleException.bush
                ),
            )
            .where(
                ScheduleException.id
                == exception_id
            )
            .limit(1)
        )

        if for_update:
            statement = statement.with_for_update()

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_exception_by_id_or_raise(
        self,
        exception_id: int,
        *,
        for_update: bool = False,
    ) -> ScheduleException:
        """Повертає виняток або викликає помилку."""

        exception = await self.get_exception_by_id(
            exception_id,
            for_update=for_update,
        )

        if exception is None:
            raise ValueError(
                "Виняток графіка не знайдено."
            )

        return exception

    async def upsert_exception(
        self,
        *,
        exception_date: date,
        exception_type: ScheduleExceptionType,
        created_by_id: int,
        store_id: int | None = None,
        bush_id: int | None = None,
        opening_time: time | None = None,
        opening_control_deadline: time | None = None,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        reason: str | None = None,
    ) -> tuple[ScheduleException, bool]:
        """
        Створює або оновлює виняток графіка.

        Виняток повинен стосуватися:
        - або конкретної ТТ;
        - або цілого куща.
        """

        self.validate_exception_scope(
            store_id=store_id,
            bush_id=bush_id,
        )

        normalized_reason = (
            self.normalize_optional_text(reason)
        )

        exception_kind = (
            self.get_exception_kind(
                exception_type
            )
        )

        if exception_kind in {
            "day_off",
            "temporarily_closed",
        }:
            normalized_values = {
                "opening_time": None,
                "opening_control_deadline": None,
                "closing_time": None,
                "closing_control_deadline": None,
            }

        else:
            normalized_values = (
                self.validate_schedule_values(
                    is_working_day=True,
                    opening_time=opening_time,
                    opening_control_deadline=(
                        opening_control_deadline
                    ),
                    closing_time=closing_time,
                    closing_control_deadline=(
                        closing_control_deadline
                    ),
                )
            )

        if store_id is not None:
            exception = await self.get_store_exception(
                store_id=store_id,
                exception_date=exception_date,
                for_update=True,
            )
        else:
            exception = await self.get_bush_exception(
                bush_id=int(bush_id),
                exception_date=exception_date,
                for_update=True,
            )

        was_created = exception is None

        if exception is None:
            exception = ScheduleException(
                store_id=store_id,
                bush_id=bush_id,
                exception_date=exception_date,
                exception_type=exception_type,
                opening_time=normalized_values[
                    "opening_time"
                ],
                opening_control_deadline=(
                    normalized_values[
                        "opening_control_deadline"
                    ]
                ),
                closing_time=normalized_values[
                    "closing_time"
                ],
                closing_control_deadline=(
                    normalized_values[
                        "closing_control_deadline"
                    ]
                ),
                reason=normalized_reason,
                created_by_id=created_by_id,
            )

            self.session.add(exception)

        else:
            exception.exception_type = (
                exception_type
            )

            exception.opening_time = (
                normalized_values["opening_time"]
            )

            exception.opening_control_deadline = (
                normalized_values[
                    "opening_control_deadline"
                ]
            )

            exception.closing_time = (
                normalized_values["closing_time"]
            )

            exception.closing_control_deadline = (
                normalized_values[
                    "closing_control_deadline"
                ]
            )

            exception.reason = normalized_reason
            exception.created_by_id = created_by_id

            self.session.add(exception)

        await self.session.flush()

        return exception, was_created

    async def create_store_day_off(
        self,
        *,
        store_id: int,
        exception_date: date,
        created_by_id: int,
        reason: str,
    ) -> tuple[ScheduleException, bool]:
        """Створює вихідний для конкретної ТТ."""

        return await self.upsert_exception(
            store_id=store_id,
            exception_date=exception_date,
            exception_type=(
                self.resolve_exception_type(
                    "day_off"
                )
            ),
            created_by_id=created_by_id,
            reason=reason,
        )

    async def create_bush_day_off(
        self,
        *,
        bush_id: int,
        exception_date: date,
        created_by_id: int,
        reason: str,
    ) -> tuple[ScheduleException, bool]:
        """Створює вихідний для цілого куща."""

        return await self.upsert_exception(
            bush_id=bush_id,
            exception_date=exception_date,
            exception_type=(
                self.resolve_exception_type(
                    "day_off"
                )
            ),
            created_by_id=created_by_id,
            reason=reason,
        )

    async def create_store_custom_hours(
        self,
        *,
        store_id: int,
        exception_date: date,
        created_by_id: int,
        opening_time: time,
        opening_control_deadline: time,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        reason: str | None = None,
    ) -> tuple[ScheduleException, bool]:
        """Встановлює особливий графік ТТ на дату."""

        return await self.upsert_exception(
            store_id=store_id,
            exception_date=exception_date,
            exception_type=(
                self.resolve_exception_type(
                    "custom_hours"
                )
            ),
            created_by_id=created_by_id,
            opening_time=opening_time,
            opening_control_deadline=(
                opening_control_deadline
            ),
            closing_time=closing_time,
            closing_control_deadline=(
                closing_control_deadline
            ),
            reason=reason,
        )

    async def create_bush_custom_hours(
        self,
        *,
        bush_id: int,
        exception_date: date,
        created_by_id: int,
        opening_time: time,
        opening_control_deadline: time,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        reason: str | None = None,
    ) -> tuple[ScheduleException, bool]:
        """Встановлює особливий графік куща на дату."""

        return await self.upsert_exception(
            bush_id=bush_id,
            exception_date=exception_date,
            exception_type=(
                self.resolve_exception_type(
                    "custom_hours"
                )
            ),
            created_by_id=created_by_id,
            opening_time=opening_time,
            opening_control_deadline=(
                opening_control_deadline
            ),
            closing_time=closing_time,
            closing_control_deadline=(
                closing_control_deadline
            ),
            reason=reason,
        )

    async def create_temporary_closure(
        self,
        *,
        store_id: int,
        exception_date: date,
        created_by_id: int,
        reason: str,
    ) -> tuple[ScheduleException, bool]:
        """Тимчасово виключає ТТ із контролю на дату."""

        return await self.upsert_exception(
            store_id=store_id,
            exception_date=exception_date,
            exception_type=(
                self.resolve_exception_type(
                    "temporarily_closed"
                )
            ),
            created_by_id=created_by_id,
            reason=reason,
        )

    async def delete_exception(
        self,
        exception: ScheduleException,
    ) -> None:
        """Видаляє виняток графіка."""

        await self.session.delete(exception)
        await self.session.flush()

    async def delete_exception_by_id(
        self,
        exception_id: int,
    ) -> bool:
        """Видаляє виняток за ID."""

        exception = await self.get_exception_by_id(
            exception_id,
            for_update=True,
        )

        if exception is None:
            return False

        await self.delete_exception(exception)

        return True

    async def get_exceptions_for_date(
        self,
        exception_date: date,
        *,
        store_id: int | None = None,
        bush_id: int | None = None,
    ) -> list[ScheduleException]:
        """Повертає винятки на конкретну дату."""

        conditions = [
            ScheduleException.exception_date
            == exception_date,
        ]

        if store_id is not None:
            conditions.append(
                ScheduleException.store_id
                == store_id
            )

        if bush_id is not None:
            conditions.append(
                ScheduleException.bush_id
                == bush_id
            )

        statement = (
            select(ScheduleException)
            .options(
                selectinload(
                    ScheduleException.store
                ),
                selectinload(
                    ScheduleException.bush
                ),
            )
            .where(*conditions)
            .order_by(
                ScheduleException.bush_id.asc().nullsfirst(),
                ScheduleException.store_id.asc().nullsfirst(),
                ScheduleException.id.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_store_exceptions_between(
        self,
        *,
        store_id: int,
        date_from: date,
        date_to: date,
    ) -> list[ScheduleException]:
        """Повертає винятки ТТ у діапазоні дат."""

        self.validate_date_range(
            date_from=date_from,
            date_to=date_to,
        )

        statement = (
            select(ScheduleException)
            .where(
                ScheduleException.store_id
                == store_id,
                ScheduleException.exception_date
                >= date_from,
                ScheduleException.exception_date
                <= date_to,
            )
            .order_by(
                ScheduleException.exception_date.asc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ФАКТИЧНИЙ ГРАФІК
    # ==========================================

    async def get_effective_schedule(
        self,
        *,
        store: Store,
        business_date: date,
    ) -> EffectiveSchedule:
        """
        Визначає остаточний графік ТТ на дату.

        Пріоритет:

        1. Статус ТТ.
        2. Виняток конкретної ТТ.
        3. Виняток куща.
        4. Тижневий графік.
        5. Графік кластера.
        """

        if (
            not store.is_active
            or store.status == StoreStatus.INACTIVE
        ):
            return EffectiveSchedule(
                store_id=store.id,
                business_date=business_date,
                is_working_day=False,
                source="store_inactive",
                reason="Торгова точка деактивована",
            )

        if (
            store.status
            == StoreStatus.TEMPORARILY_CLOSED
        ):
            return EffectiveSchedule(
                store_id=store.id,
                business_date=business_date,
                is_working_day=False,
                source="store_temporarily_closed",
                reason="Торгова точка тимчасово закрита",
            )

        store_exception = (
            await self.get_store_exception(
                store_id=store.id,
                exception_date=business_date,
            )
        )

        if store_exception is not None:
            return self.schedule_from_exception(
                store=store,
                business_date=business_date,
                exception=store_exception,
                source="store_exception",
            )

        if store.bush_id is not None:
            bush_exception = (
                await self.get_bush_exception(
                    bush_id=store.bush_id,
                    exception_date=business_date,
                )
            )

            if bush_exception is not None:
                return self.schedule_from_exception(
                    store=store,
                    business_date=business_date,
                    exception=bush_exception,
                    source="bush_exception",
                )

        weekday_schedule = (
            await self.get_weekday_schedule(
                store_id=store.id,
                weekday=business_date.weekday(),
            )
        )

        if weekday_schedule is not None:
            return EffectiveSchedule(
                store_id=store.id,
                business_date=business_date,
                is_working_day=(
                    weekday_schedule.is_working_day
                ),
                source="store_weekly_schedule",
                opening_time=(
                    weekday_schedule.opening_time
                    if weekday_schedule.is_working_day
                    else None
                ),
                opening_control_deadline=(
                    weekday_schedule
                    .opening_control_deadline
                    if weekday_schedule.is_working_day
                    else None
                ),
                closing_time=(
                    weekday_schedule.closing_time
                    if weekday_schedule.is_working_day
                    else None
                ),
                closing_control_deadline=(
                    weekday_schedule
                    .closing_control_deadline
                    if weekday_schedule.is_working_day
                    else None
                ),
                reason=(
                    None
                    if weekday_schedule.is_working_day
                    else "Постійний вихідний день"
                ),
            )

        if store.cluster_id is not None:
            cluster = await self.session.get(
                Cluster,
                store.cluster_id,
            )

            if (
                cluster is not None
                and cluster.is_active
            ):
                return EffectiveSchedule(
                    store_id=store.id,
                    business_date=business_date,
                    is_working_day=True,
                    source="cluster_default",
                    opening_time=(
                        cluster.opening_time
                    ),
                    opening_control_deadline=(
                        cluster
                        .opening_control_deadline
                    ),
                    closing_time=(
                        cluster.default_closing_time
                    ),
                    closing_control_deadline=(
                        cluster
                        .default_closing_control_deadline
                    ),
                )

        return EffectiveSchedule(
            store_id=store.id,
            business_date=business_date,
            is_working_day=False,
            source="schedule_missing",
            reason=(
                "Для торгової точки не налаштовано "
                "графік або часовий кластер"
            ),
        )

    def schedule_from_exception(
        self,
        *,
        store: Store,
        business_date: date,
        exception: ScheduleException,
        source: str,
    ) -> EffectiveSchedule:
        """Формує фактичний графік із винятку."""

        exception_kind = self.get_exception_kind(
            exception.exception_type
        )

        if exception_kind in {
            "day_off",
            "temporarily_closed",
        }:
            return EffectiveSchedule(
                store_id=store.id,
                business_date=business_date,
                is_working_day=False,
                source=source,
                exception_id=exception.id,
                reason=(
                    exception.reason
                    or "Вихідний або тимчасове закриття"
                ),
            )

        return EffectiveSchedule(
            store_id=store.id,
            business_date=business_date,
            is_working_day=True,
            source=source,
            opening_time=exception.opening_time,
            opening_control_deadline=(
                exception.opening_control_deadline
            ),
            closing_time=exception.closing_time,
            closing_control_deadline=(
                exception.closing_control_deadline
            ),
            exception_id=exception.id,
            reason=exception.reason,
        )

    # ==========================================
    # СПИСКИ ТТ ЗА ФАКТИЧНИМ ГРАФІКОМ
    # ==========================================

    async def get_controlled_stores(
        self,
    ) -> list[Store]:
        """Повертає активні ТТ для перевірки графіка."""

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

        return list(
            result.unique().all()
        )

    async def get_stores_requiring_opening(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[
        tuple[Store, EffectiveSchedule]
    ]:
        """Повертає ТТ, які повинні відкритися."""

        stores = await self.get_filtered_stores(
            bush_id=bush_id,
            cluster_id=cluster_id,
        )

        result: list[
            tuple[Store, EffectiveSchedule]
        ] = []

        for store in stores:
            schedule = await self.get_effective_schedule(
                store=store,
                business_date=business_date,
            )

            if schedule.requires_opening:
                result.append(
                    (store, schedule)
                )

        return result

    async def get_stores_requiring_closing(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[
        tuple[Store, EffectiveSchedule]
    ]:
        """Повертає ТТ, які повинні подати звіт."""

        stores = await self.get_filtered_stores(
            bush_id=bush_id,
            cluster_id=cluster_id,
        )

        result: list[
            tuple[Store, EffectiveSchedule]
        ] = []

        for store in stores:
            schedule = await self.get_effective_schedule(
                store=store,
                business_date=business_date,
            )

            if schedule.requires_closing:
                result.append(
                    (store, schedule)
                )

        return result

    async def get_opening_stores_for_minute(
        self,
        *,
        business_date: date,
        local_time: time,
    ) -> list[
        tuple[Store, EffectiveSchedule]
    ]:
        """Повертає ТТ, які відкриваються зараз."""

        target_time = self.normalize_time(
            local_time
        )

        stores = await self.get_stores_requiring_opening(
            business_date=business_date
        )

        return [
            (store, schedule)
            for store, schedule in stores
            if schedule.opening_time
            == target_time
        ]

    async def get_opening_deadlines_for_minute(
        self,
        *,
        business_date: date,
        local_time: time,
    ) -> list[
        tuple[Store, EffectiveSchedule]
    ]:
        """Повертає ТТ, у яких зараз дедлайн відкриття."""

        target_time = self.normalize_time(
            local_time
        )

        stores = await self.get_stores_requiring_opening(
            business_date=business_date
        )

        return [
            (store, schedule)
            for store, schedule in stores
            if schedule.opening_control_deadline
            == target_time
        ]

    async def get_closing_stores_for_minute(
        self,
        *,
        business_date: date,
        local_time: time,
    ) -> list[
        tuple[Store, EffectiveSchedule]
    ]:
        """Повертає ТТ, які закриваються зараз."""

        target_time = self.normalize_time(
            local_time
        )

        stores = await self.get_stores_requiring_closing(
            business_date=business_date
        )

        return [
            (store, schedule)
            for store, schedule in stores
            if schedule.closing_time
            == target_time
        ]

    async def get_closing_deadlines_for_minute(
        self,
        *,
        business_date: date,
        local_time: time,
    ) -> list[
        tuple[Store, EffectiveSchedule]
    ]:
        """Повертає ТТ, у яких зараз дедлайн звіту."""

        target_time = self.normalize_time(
            local_time
        )

        stores = await self.get_stores_requiring_closing(
            business_date=business_date
        )

        return [
            (store, schedule)
            for store, schedule in stores
            if schedule.closing_control_deadline
            == target_time
        ]

    async def get_filtered_stores(
        self,
        *,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[Store]:
        """Повертає активні ТТ за фільтрами."""

        conditions = [
            Store.is_active.is_(True),
            Store.status == StoreStatus.ACTIVE,
        ]

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
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # МАСОВЕ НАЛАШТУВАННЯ
    # ==========================================

    async def create_default_weekly_schedule(
        self,
        *,
        store_id: int,
        opening_time: time,
        opening_control_deadline: time,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        working_weekdays: set[int] | None = None,
    ) -> list[StoreSchedule]:
        """
        Створює повний тижневий графік ТТ.

        За замовчуванням усі сім днів робочі.
        """

        active_days = (
            set(range(7))
            if working_weekdays is None
            else set(working_weekdays)
        )

        for weekday in active_days:
            self.validate_weekday(weekday)

        schedules: list[StoreSchedule] = []

        for weekday in range(7):
            is_working_day = (
                weekday in active_days
            )

            schedule, _ = (
                await self.upsert_weekday_schedule(
                    store_id=store_id,
                    weekday=weekday,
                    is_working_day=(
                        is_working_day
                    ),
                    opening_time=(
                        opening_time
                        if is_working_day
                        else None
                    ),
                    opening_control_deadline=(
                        opening_control_deadline
                        if is_working_day
                        else None
                    ),
                    closing_time=(
                        closing_time
                        if is_working_day
                        else None
                    ),
                    closing_control_deadline=(
                        closing_control_deadline
                        if is_working_day
                        else None
                    ),
                )
            )

            schedules.append(schedule)

        return schedules

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def validate_weekday(
        weekday: int,
    ) -> None:
        """Перевіряє номер дня тижня."""

        if weekday < 0 or weekday > 6:
            raise ValueError(
                "День тижня повинен бути "
                "в межах від 0 до 6."
            )

    @classmethod
    def validate_schedule_values(
        cls,
        *,
        is_working_day: bool,
        opening_time: time | None,
        opening_control_deadline: time | None,
        closing_time: time | None,
        closing_control_deadline: time | None,
    ) -> dict[str, time | None]:
        """Перевіряє час відкриття та закриття."""

        if not is_working_day:
            return {
                "opening_time": None,
                "opening_control_deadline": None,
                "closing_time": None,
                "closing_control_deadline": None,
            }

        if opening_time is None:
            raise ValueError(
                "Для робочого дня потрібно вказати "
                "час відкриття."
            )

        if opening_control_deadline is None:
            raise ValueError(
                "Для робочого дня потрібно вказати "
                "дедлайн відкриття."
            )

        normalized_opening_time = (
            cls.normalize_time(
                opening_time
            )
        )

        normalized_opening_deadline = (
            cls.normalize_time(
                opening_control_deadline
            )
        )

        if (
            normalized_opening_deadline
            < normalized_opening_time
        ):
            raise ValueError(
                "Дедлайн відкриття не може бути "
                "раніше часу відкриття."
            )

        if (
            closing_time is None
            and closing_control_deadline is not None
        ):
            raise ValueError(
                "Не можна вказати дедлайн закриття "
                "без часу закриття."
            )

        if (
            closing_time is not None
            and closing_control_deadline is None
        ):
            raise ValueError(
                "Для часу закриття потрібно вказати "
                "контрольний дедлайн."
            )

        normalized_closing_time: time | None = None
        normalized_closing_deadline: time | None = None

        if closing_time is not None:
            normalized_closing_time = (
                cls.normalize_time(
                    closing_time
                )
            )

            normalized_closing_deadline = (
                cls.normalize_time(
                    closing_control_deadline
                )
            )

            if (
                normalized_closing_deadline
                < normalized_closing_time
            ):
                raise ValueError(
                    "Дедлайн закриття не може бути "
                    "раніше часу закриття."
                )

        return {
            "opening_time": normalized_opening_time,
            "opening_control_deadline": (
                normalized_opening_deadline
            ),
            "closing_time": normalized_closing_time,
            "closing_control_deadline": (
                normalized_closing_deadline
            ),
        }

    @staticmethod
    def validate_exception_scope(
        *,
        store_id: int | None,
        bush_id: int | None,
    ) -> None:
        """Перевіряє ціль винятку графіка."""

        if (
            store_id is None
            and bush_id is None
        ):
            raise ValueError(
                "Потрібно вказати торгову точку "
                "або кущ."
            )

        if (
            store_id is not None
            and bush_id is not None
        ):
            raise ValueError(
                "Виняток не може одночасно "
                "стосуватися ТТ і куща."
            )

        if store_id is not None and store_id <= 0:
            raise ValueError(
                "ID торгової точки повинен бути "
                "більшим за нуль."
            )

        if bush_id is not None and bush_id <= 0:
            raise ValueError(
                "ID куща повинен бути "
                "більшим за нуль."
            )

    @staticmethod
    def resolve_exception_type(
        requested_type: str,
    ) -> ScheduleExceptionType:
        """
        Знаходить enum винятку незалежно
        від регістру назви або значення.
        """

        aliases = {
            "day_off": {
                "day_off",
                "dayoff",
                "holiday",
                "closed",
                "вихідний",
            },
            "custom_hours": {
                "custom_hours",
                "changed_hours",
                "special_hours",
                "custom_schedule",
                "working_day",
            },
            "temporarily_closed": {
                "temporarily_closed",
                "temporary_closed",
                "temporary_closure",
                "temp_closed",
            },
        }

        normalized_request = (
            requested_type.strip().lower()
        )

        accepted_values = aliases.get(
            normalized_request,
            {normalized_request},
        )

        for enum_item in ScheduleExceptionType:
            enum_name = enum_item.name.lower()
            enum_value = str(
                enum_item.value
            ).lower()

            if (
                enum_name in accepted_values
                or enum_value in accepted_values
            ):
                return enum_item

        raise ValueError(
            "У ScheduleExceptionType відсутній "
            f"тип «{requested_type}»."
        )

    @staticmethod
    def get_exception_kind(
        exception_type: ScheduleExceptionType,
    ) -> str:
        """Визначає логічний вид винятку."""

        normalized_values = {
            exception_type.name.lower(),
            str(exception_type.value).lower(),
        }

        day_off_values = {
            "day_off",
            "dayoff",
            "holiday",
            "closed",
        }

        temporarily_closed_values = {
            "temporarily_closed",
            "temporary_closed",
            "temporary_closure",
            "temp_closed",
        }

        if normalized_values.intersection(
            day_off_values
        ):
            return "day_off"

        if normalized_values.intersection(
            temporarily_closed_values
        ):
            return "temporarily_closed"

        return "custom_hours"

    @staticmethod
    def normalize_time(
        value: time | None,
    ) -> time:
        """Прибирає секунди, мікросекунди та timezone."""

        if value is None:
            raise ValueError(
                "Час не може бути порожнім."
            )

        return value.replace(
            second=0,
            microsecond=0,
            tzinfo=None,
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

    @staticmethod
    def validate_date_range(
        *,
        date_from: date,
        date_to: date,
    ) -> None:
        """Перевіряє діапазон дат."""

        if date_to < date_from:
            raise ValueError(
                "Кінцева дата не може бути "
                "раніше початкової."
            )

    @staticmethod
    def weekday_name(
        weekday: int,
    ) -> str:
        """Повертає українську назву дня."""

        names = {
            0: "Понеділок",
            1: "Вівторок",
            2: "Середа",
            3: "Четвер",
            4: "П’ятниця",
            5: "Субота",
            6: "Неділя",
        }

        ScheduleRepository.validate_weekday(
            weekday
        )

        return names[weekday]