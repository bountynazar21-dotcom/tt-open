from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.database.models.enums import (
    OpeningStatus,
    StoreStatus,
)
from app.database.models.opening_checkin import OpeningCheckin
from app.database.models.store import Store
from app.repositories.base import BaseRepository


@dataclass(slots=True, frozen=True)
class OpeningPlan:
    """
    Дані для створення ранкового запису ТТ.

    Формується на основі фактичного графіка
    торгової точки на конкретну дату.
    """

    store_id: int
    business_date: date
    scheduled_open_time: time
    control_deadline: time


class OpeningRepository(
    BaseRepository[OpeningCheckin]
):
    """
    Репозиторій ранкових відкриттів торгових точок.

    Основні правила:

    - одна ТТ має лише один запис на одну дату;
    - повторне натискання не створює другий чекін;
    - фактичний час береться із сервера;
    - запізнення розраховується автоматично;
    - пропущений дедлайн фіксується scheduler;
    - історичні записи не видаляються.
    """

    model = OpeningCheckin

    OPENED_STATUSES: frozenset[OpeningStatus] = frozenset(
        {
            OpeningStatus.OPENED_EARLY,
            OpeningStatus.OPENED_ON_TIME,
            OpeningStatus.OPENED_LATE,
            OpeningStatus.OPENED_AFTER_ALERT,
            OpeningStatus.MANUALLY_CONFIRMED,
        }
    )

    LATE_STATUSES: frozenset[OpeningStatus] = frozenset(
        {
            OpeningStatus.OPENED_LATE,
            OpeningStatus.OPENED_AFTER_ALERT,
        }
    )

    PROBLEM_STATUSES: frozenset[OpeningStatus] = frozenset(
        {
            OpeningStatus.MISSED_CONTROL_DEADLINE,
            OpeningStatus.OPENED_AFTER_ALERT,
        }
    )

    EXCLUDED_STATUSES: frozenset[OpeningStatus] = frozenset(
        {
            OpeningStatus.NOT_REQUIRED,
            OpeningStatus.DAY_OFF,
            OpeningStatus.TEMPORARILY_CLOSED,
        }
    )

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(session)

    # ==========================================
    # ПОШУК ЗАПИСУ
    # ==========================================

    async def get_by_store_date(
        self,
        *,
        store_id: int,
        business_date: date,
        for_update: bool = False,
    ) -> OpeningCheckin | None:
        """
        Повертає ранковий запис ТТ на дату.

        for_update=True блокує запис до завершення
        поточної транзакції та захищає від одночасних
        подвійних натискань.
        """

        self.validate_positive_id(
            store_id,
            field_name="ID торгової точки",
        )

        statement = (
            select(OpeningCheckin)
            .where(
                OpeningCheckin.store_id == store_id,
                OpeningCheckin.business_date
                == business_date,
            )
            .limit(1)
        )

        if for_update:
            statement = (
                statement
                .options(
                    lazyload(
                        OpeningCheckin.store
                    ),
                    lazyload(
                        OpeningCheckin.submitted_by
                    ),
                    lazyload(
                        OpeningCheckin.manually_modified_by
                    ),
                )
                .with_for_update(
                    of=OpeningCheckin
                )
            )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_by_store_date_or_raise(
        self,
        *,
        store_id: int,
        business_date: date,
        for_update: bool = False,
    ) -> OpeningCheckin:
        """Повертає запис відкриття або помилку."""

        checkin = await self.get_by_store_date(
            store_id=store_id,
            business_date=business_date,
            for_update=for_update,
        )

        if checkin is None:
            raise ValueError(
                "Запис відкриття для цієї торгової "
                "точки сьогодні не створено."
            )

        return checkin

    async def get_checkin_for_update(
        self,
        checkin_id: int,
    ) -> OpeningCheckin | None:
        """Завантажує чекін із блокуванням рядка."""

        statement = (
            select(OpeningCheckin)
            .options(
                lazyload(
                    OpeningCheckin.store
                ),
                lazyload(
                    OpeningCheckin.submitted_by
                ),
                lazyload(
                    OpeningCheckin.manually_modified_by
                ),
            )
            .where(
                OpeningCheckin.id == checkin_id
            )
            .with_for_update(
                of=OpeningCheckin
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    # ==========================================
    # СТВОРЕННЯ ЩОДЕННОГО ЗАПИСУ
    # ==========================================

    async def get_or_create_waiting(
        self,
        *,
        store_id: int,
        business_date: date,
        scheduled_open_time: time,
        control_deadline: time,
    ) -> tuple[OpeningCheckin, bool]:
        """
        Повертає існуючий або створює новий запис.

        Результат:
        - OpeningCheckin;
        - True, якщо запис створено;
        - False, якщо запис уже існував.
        """

        normalized_opening_time = (
            self.normalize_time(
                scheduled_open_time
            )
        )

        normalized_deadline = self.normalize_time(
            control_deadline
        )

        if normalized_deadline < normalized_opening_time:
            raise ValueError(
                "Дедлайн відкриття не може бути "
                "раніше часу відкриття."
            )

        existing = await self.get_by_store_date(
            store_id=store_id,
            business_date=business_date,
            for_update=True,
        )

        if existing is not None:
            return existing, False

        checkin = OpeningCheckin.create_waiting(
            store_id=store_id,
            business_date=business_date,
            scheduled_open_time=(
                normalized_opening_time
            ),
            control_deadline=normalized_deadline,
        )

        self.session.add(checkin)
        await self.session.flush()

        return checkin, True

    async def create_from_plan(
        self,
        plan: OpeningPlan,
    ) -> tuple[OpeningCheckin, bool]:
        """Створює запис із підготовленого плану."""

        return await self.get_or_create_waiting(
            store_id=plan.store_id,
            business_date=plan.business_date,
            scheduled_open_time=(
                plan.scheduled_open_time
            ),
            control_deadline=plan.control_deadline,
        )

    async def create_missing_records(
        self,
        plans: Iterable[OpeningPlan],
    ) -> list[OpeningCheckin]:
        """
        Створює відсутні ранкові записи.

        Існуючі записи не змінюються.
        """

        created_records: list[
            OpeningCheckin
        ] = []

        unique_plans: dict[
            tuple[int, date],
            OpeningPlan,
        ] = {}

        for plan in plans:
            key = (
                plan.store_id,
                plan.business_date,
            )

            unique_plans[key] = plan

        for plan in unique_plans.values():
            checkin, was_created = (
                await self.create_from_plan(
                    plan
                )
            )

            if was_created:
                created_records.append(checkin)

        return created_records

    # ==========================================
    # ПІДТВЕРДЖЕННЯ ВІДКРИТТЯ
    # ==========================================

    async def confirm_opening(
        self,
        *,
        store_id: int,
        business_date: date,
        actual_open_time: datetime,
        submitted_by_id: int,
        scheduled_open_time: time,
        control_deadline: time,
        timezone_name: str = "Europe/Kyiv",
        source: str = "telegram_bot",
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
    ) -> tuple[OpeningCheckin, bool]:
        """
        Фіксує фактичне відкриття ТТ.

        Повертає:
        - запис відкриття;
        - True, якщо відкриття зафіксовано зараз;
        - False, якщо ТТ уже була відкрита.

        False захищає від подвійного натискання кнопки.
        """

        self.validate_aware_datetime(
            actual_open_time,
            field_name="actual_open_time",
        )

        self.validate_positive_id(
            submitted_by_id,
            field_name="ID користувача",
        )

        checkin, _ = await self.get_or_create_waiting(
            store_id=store_id,
            business_date=business_date,
            scheduled_open_time=scheduled_open_time,
            control_deadline=control_deadline,
        )

        checkin = await self.get_by_store_date_or_raise(
            store_id=store_id,
            business_date=business_date,
            for_update=True,
        )

        if checkin.actual_open_time is not None:
            return checkin, False

        if checkin.status in self.EXCLUDED_STATUSES:
            raise ValueError(
                "Ця торгова точка сьогодні не повинна "
                "проходити ранковий чекін."
            )

        scheduled_datetime = (
            self.build_local_datetime(
                business_date=business_date,
                local_time=checkin.scheduled_open_time,
                timezone_name=timezone_name,
            )
        )

        deadline_datetime = (
            self.build_local_datetime(
                business_date=business_date,
                local_time=checkin.control_deadline,
                timezone_name=timezone_name,
            )
        )

        actual_utc = actual_open_time.astimezone(
            UTC
        )

        checkin.confirm_opening(
            actual_open_time=actual_utc,
            scheduled_open_datetime=(
                scheduled_datetime
            ),
            control_deadline_datetime=(
                deadline_datetime
            ),
            submitted_by_id=submitted_by_id,
            source=source,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=(
                telegram_message_id
            ),
        )

        self.session.add(checkin)
        await self.session.flush()

        return checkin, True

    # ==========================================
    # ПРОПУЩЕНИЙ ДЕДЛАЙН
    # ==========================================

    async def mark_deadline_missed(
        self,
        checkin: OpeningCheckin,
        *,
        missed_at: datetime,
        alert_sent: bool = True,
    ) -> OpeningCheckin:
        """Фіксує пропущений дедлайн однієї ТТ."""

        self.validate_aware_datetime(
            missed_at,
            field_name="missed_at",
        )

        if checkin.actual_open_time is not None:
            return checkin

        if checkin.status in self.EXCLUDED_STATUSES:
            return checkin

        checkin.mark_deadline_missed(
            missed_at=missed_at.astimezone(UTC),
            alert_sent=alert_sent,
        )

        self.session.add(checkin)
        await self.session.flush()

        return checkin

    async def mark_due_deadlines_missed(
        self,
        *,
        current_time: datetime,
        timezone_name: str = "Europe/Kyiv",
        business_date: date | None = None,
        bush_id: int | None = None,
        cluster_id: int | None = None,
        alert_sent: bool = True,
    ) -> list[OpeningCheckin]:
        """
        Фіксує всі дедлайни, які вже настали.

        Використовується scheduler. Умова <= дозволяє
        наздогнати перевірку після короткого перезапуску.
        """

        self.validate_aware_datetime(
            current_time,
            field_name="current_time",
        )

        timezone = self.get_timezone(
            timezone_name
        )

        current_local = current_time.astimezone(
            timezone
        )

        target_date = (
            business_date
            or current_local.date()
        )

        target_time = current_local.time().replace(
            second=0,
            microsecond=0,
            tzinfo=None,
        )

        conditions = [
            OpeningCheckin.business_date
            == target_date,
            OpeningCheckin.actual_open_time.is_(None),
            OpeningCheckin.control_deadline
            <= target_time,
            OpeningCheckin.status
            == OpeningStatus.WAITING,
        ]

        statement = (
            select(OpeningCheckin)
            .join(
                Store,
                Store.id
                == OpeningCheckin.store_id,
            )
            .options(
                lazyload(
                    OpeningCheckin.store
                ),
                lazyload(
                    OpeningCheckin.submitted_by
                ),
                lazyload(
                    OpeningCheckin.manually_modified_by
                ),
            )
            .where(*conditions)
            .with_for_update(
                of=OpeningCheckin,
                skip_locked=True,
            )
            .order_by(
                Store.store_number.asc()
            )
        )

        if bush_id is not None:
            statement = statement.where(
                Store.bush_id == bush_id
            )

        if cluster_id is not None:
            statement = statement.where(
                Store.cluster_id == cluster_id
            )

        result = await self.session.scalars(
            statement
        )

        checkins = list(
            result.unique().all()
        )

        missed_at = current_time.astimezone(UTC)

        for checkin in checkins:
            checkin.mark_deadline_missed(
                missed_at=missed_at,
                alert_sent=alert_sent,
            )

            self.session.add(checkin)

        if checkins:
            await self.session.flush()

        return checkins

    async def mark_alert_sent(
        self,
        checkin: OpeningCheckin,
        *,
        sent_at: datetime,
    ) -> OpeningCheckin:
        """Фіксує надсилання сповіщення про ТТ."""

        self.validate_aware_datetime(
            sent_at,
            field_name="sent_at",
        )

        checkin.mark_alert_sent(
            sent_at=sent_at.astimezone(UTC)
        )

        self.session.add(checkin)
        await self.session.flush()

        return checkin

    # ==========================================
    # РУЧНЕ ПІДТВЕРДЖЕННЯ
    # ==========================================

    async def manually_confirm(
        self,
        *,
        store_id: int,
        business_date: date,
        actual_open_time: datetime,
        modified_by_id: int,
        modified_at: datetime,
        reason: str,
        timezone_name: str = "Europe/Kyiv",
    ) -> OpeningCheckin:
        """Ручне підтвердження відкриття адміністратором."""

        self.validate_aware_datetime(
            actual_open_time,
            field_name="actual_open_time",
        )

        self.validate_aware_datetime(
            modified_at,
            field_name="modified_at",
        )

        checkin = await self.get_by_store_date_or_raise(
            store_id=store_id,
            business_date=business_date,
            for_update=True,
        )

        scheduled_datetime = (
            self.build_local_datetime(
                business_date=business_date,
                local_time=checkin.scheduled_open_time,
                timezone_name=timezone_name,
            )
        )

        checkin.manually_confirm(
            actual_open_time=(
                actual_open_time.astimezone(UTC)
            ),
            scheduled_open_datetime=(
                scheduled_datetime
            ),
            modified_by_id=modified_by_id,
            modified_at=modified_at.astimezone(UTC),
            reason=reason,
        )

        self.session.add(checkin)
        await self.session.flush()

        return checkin

    async def modify_opening_time(
        self,
        *,
        checkin_id: int,
        new_actual_open_time: datetime,
        modified_by_id: int,
        modified_at: datetime,
        reason: str,
        timezone_name: str = "Europe/Kyiv",
    ) -> OpeningCheckin:
        """Змінює помилково зафіксований час."""

        self.validate_aware_datetime(
            new_actual_open_time,
            field_name="new_actual_open_time",
        )

        self.validate_aware_datetime(
            modified_at,
            field_name="modified_at",
        )

        checkin = await self.get_checkin_for_update(
            checkin_id
        )

        if checkin is None:
            raise ValueError(
                "Запис відкриття не знайдено."
            )

        scheduled_datetime = (
            self.build_local_datetime(
                business_date=(
                    checkin.business_date
                ),
                local_time=(
                    checkin.scheduled_open_time
                ),
                timezone_name=timezone_name,
            )
        )

        deadline_datetime = (
            self.build_local_datetime(
                business_date=(
                    checkin.business_date
                ),
                local_time=checkin.control_deadline,
                timezone_name=timezone_name,
            )
        )

        checkin.modify_opening_time(
            new_actual_open_time=(
                new_actual_open_time.astimezone(UTC)
            ),
            scheduled_open_datetime=(
                scheduled_datetime
            ),
            control_deadline_datetime=(
                deadline_datetime
            ),
            modified_by_id=modified_by_id,
            modified_at=modified_at.astimezone(UTC),
            reason=reason,
        )

        self.session.add(checkin)
        await self.session.flush()

        return checkin

    # ==========================================
    # ВИХІДНІ ТА ВИКЛЮЧЕННЯ
    # ==========================================

    async def mark_not_required(
        self,
        checkin: OpeningCheckin,
    ) -> OpeningCheckin:
        """Позначає, що ранковий чекін не потрібен."""

        self.ensure_not_opened(checkin)

        checkin.status = OpeningStatus.NOT_REQUIRED
        checkin.lateness_minutes = 0

        self.session.add(checkin)
        await self.session.flush()

        return checkin

    async def mark_day_off(
        self,
        checkin: OpeningCheckin,
    ) -> OpeningCheckin:
        """Позначає вихідний день."""

        self.ensure_not_opened(checkin)

        checkin.status = OpeningStatus.DAY_OFF
        checkin.lateness_minutes = 0

        self.session.add(checkin)
        await self.session.flush()

        return checkin

    async def mark_temporarily_closed(
        self,
        checkin: OpeningCheckin,
    ) -> OpeningCheckin:
        """Позначає тимчасово закриту ТТ."""

        self.ensure_not_opened(checkin)

        checkin.status = (
            OpeningStatus.TEMPORARILY_CLOSED
        )

        checkin.lateness_minutes = 0

        self.session.add(checkin)
        await self.session.flush()

        return checkin

    # ==========================================
    # СПИСКИ ЗАПИСІВ
    # ==========================================

    async def get_for_date(
        self,
        *,
        business_date: date,
        statuses: set[OpeningStatus] | None = None,
        bush_id: int | None = None,
        cluster_id: int | None = None,
        opened_only: bool | None = None,
    ) -> list[OpeningCheckin]:
        """Повертає ранкові записи за фільтрами."""

        conditions = [
            OpeningCheckin.business_date
            == business_date,
        ]

        if statuses:
            conditions.append(
                OpeningCheckin.status.in_(statuses)
            )

        if opened_only is True:
            conditions.append(
                OpeningCheckin.actual_open_time
                .is_not(None)
            )

        elif opened_only is False:
            conditions.append(
                OpeningCheckin.actual_open_time
                .is_(None)
            )

        statement = (
            select(OpeningCheckin)
            .join(
                Store,
                Store.id
                == OpeningCheckin.store_id,
            )
            .where(*conditions)
            .order_by(
                Store.store_number.asc()
            )
        )

        if bush_id is not None:
            statement = statement.where(
                Store.bush_id == bush_id
            )

        if cluster_id is not None:
            statement = statement.where(
                Store.cluster_id == cluster_id
            )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    async def get_opened_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[OpeningCheckin]:
        """Повертає всі ТТ, які вже відкрилися."""

        return await self.get_for_date(
            business_date=business_date,
            statuses=set(self.OPENED_STATUSES),
            bush_id=bush_id,
            cluster_id=cluster_id,
            opened_only=True,
        )

    async def get_opened_early_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
    ) -> list[OpeningCheckin]:
        """Повертає ТТ, які відкрилися раніше."""

        return await self.get_for_date(
            business_date=business_date,
            statuses={
                OpeningStatus.OPENED_EARLY,
            },
            bush_id=bush_id,
        )

    async def get_opened_on_time_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
    ) -> list[OpeningCheckin]:
        """Повертає ТТ, які відкрилися вчасно."""

        return await self.get_for_date(
            business_date=business_date,
            statuses={
                OpeningStatus.OPENED_ON_TIME,
            },
            bush_id=bush_id,
        )

    async def get_late_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[OpeningCheckin]:
        """Повертає ТТ, які відкрилися із запізненням."""

        return await self.get_for_date(
            business_date=business_date,
            statuses=set(self.LATE_STATUSES),
            bush_id=bush_id,
            cluster_id=cluster_id,
        )

    async def get_waiting_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[OpeningCheckin]:
        """Повертає ТТ, від яких ще очікується чекін."""

        return await self.get_for_date(
            business_date=business_date,
            statuses={
                OpeningStatus.WAITING,
            },
            bush_id=bush_id,
            cluster_id=cluster_id,
            opened_only=False,
        )

    async def get_missed_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[OpeningCheckin]:
        """Повертає ТТ, які пропустили дедлайн."""

        return await self.get_for_date(
            business_date=business_date,
            statuses={
                OpeningStatus.MISSED_CONTROL_DEADLINE,
            },
            bush_id=bush_id,
            cluster_id=cluster_id,
            opened_only=False,
        )

    async def get_problem_records(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[OpeningCheckin]:
        """
        Повертає проблемні записи:

        - дедлайн пропущено;
        - ТТ відкрилася лише після сповіщення.
        """

        return await self.get_for_date(
            business_date=business_date,
            statuses=set(self.PROBLEM_STATUSES),
            bush_id=bush_id,
            cluster_id=cluster_id,
        )

    async def get_store_history(
        self,
        *,
        store_id: int,
        date_from: date,
        date_to: date,
    ) -> list[OpeningCheckin]:
        """Повертає історію відкриттів ТТ."""

        self.validate_date_range(
            date_from=date_from,
            date_to=date_to,
        )

        statement = (
            select(OpeningCheckin)
            .where(
                OpeningCheckin.store_id
                == store_id,
                OpeningCheckin.business_date
                >= date_from,
                OpeningCheckin.business_date
                <= date_to,
            )
            .order_by(
                OpeningCheckin.business_date.desc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ТТ БЕЗ РАНКОВОГО ЗАПИСУ
    # ==========================================

    async def get_stores_without_record(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[Store]:
        """
        Повертає активні ТТ, для яких scheduler
        не створив ранковий запис.
        """

        conditions = [
            Store.is_active.is_(True),
            Store.status == StoreStatus.ACTIVE,
            OpeningCheckin.id.is_(None),
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
            .outerjoin(
                OpeningCheckin,
                (
                    OpeningCheckin.store_id
                    == Store.id
                )
                & (
                    OpeningCheckin.business_date
                    == business_date
                ),
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

    # ==========================================
    # РЕЙТИНГ ЗАПІЗНЕНЬ
    # ==========================================

    async def get_lateness_ranking(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Повертає рейтинг ТТ за хвилинами запізнення."""

        if limit <= 0 or limit > 1000:
            raise ValueError(
                "Limit повинен бути від 1 до 1000."
            )

        conditions = [
            OpeningCheckin.business_date
            == business_date,
            OpeningCheckin.lateness_minutes > 0,
            OpeningCheckin.status.in_(
                self.LATE_STATUSES
            ),
        ]

        if bush_id is not None:
            conditions.append(
                Store.bush_id == bush_id
            )

        statement = (
            select(
                OpeningCheckin.id,
                OpeningCheckin.store_id,
                OpeningCheckin.actual_open_time,
                OpeningCheckin.lateness_minutes,
                OpeningCheckin.status,
                Store.store_number,
                Store.code,
                Store.city,
                Store.address,
                Store.bush_id,
            )
            .join(
                Store,
                Store.id
                == OpeningCheckin.store_id,
            )
            .where(*conditions)
            .order_by(
                OpeningCheckin
                .lateness_minutes
                .desc(),
                Store.store_number.asc(),
            )
            .limit(limit)
        )

        result = await self.session.execute(
            statement
        )

        ranking: list[dict[str, Any]] = []

        for position, row in enumerate(
            result.mappings().all(),
            start=1,
        ):
            ranking.append(
                {
                    "position": position,
                    "checkin_id": int(
                        row["id"]
                    ),
                    "store_id": int(
                        row["store_id"]
                    ),
                    "store_number": int(
                        row["store_number"]
                    ),
                    "store_code": str(
                        row["code"]
                    ),
                    "city": str(
                        row["city"]
                    ),
                    "address": str(
                        row["address"]
                    ),
                    "bush_id": row["bush_id"],
                    "actual_open_time": (
                        row["actual_open_time"]
                    ),
                    "lateness_minutes": int(
                        row["lateness_minutes"]
                    ),
                    "status": row["status"],
                }
            )

        return ranking

    # ==========================================
    # СТАТИСТИКА
    # ==========================================

    async def count_by_status(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> dict[OpeningStatus, int]:
        """Підраховує записи за статусами."""

        statement = (
            select(
                OpeningCheckin.status,
                func.count(
                    OpeningCheckin.id
                ),
            )
            .join(
                Store,
                Store.id
                == OpeningCheckin.store_id,
            )
            .where(
                OpeningCheckin.business_date
                == business_date
            )
        )

        if bush_id is not None:
            statement = statement.where(
                Store.bush_id == bush_id
            )

        if cluster_id is not None:
            statement = statement.where(
                Store.cluster_id == cluster_id
            )

        statement = statement.group_by(
            OpeningCheckin.status
        )

        result = await self.session.execute(
            statement
        )

        counts: dict[OpeningStatus, int] = {
            status: 0
            for status in OpeningStatus
        }

        for status, count in result.all():
            counts[status] = int(count)

        return counts

    async def get_daily_statistics(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> dict[str, int | float]:
        """Формує загальну статистику відкриття."""

        counts = await self.count_by_status(
            business_date=business_date,
            bush_id=bush_id,
            cluster_id=cluster_id,
        )

        expected_count = sum(
            count
            for status, count in counts.items()
            if status not in self.EXCLUDED_STATUSES
        )

        opened_count = sum(
            counts[status]
            for status in self.OPENED_STATUSES
        )

        late_count = sum(
            counts[status]
            for status in self.LATE_STATUSES
        )

        missed_count = counts[
            OpeningStatus.MISSED_CONTROL_DEADLINE
        ]

        waiting_count = counts[
            OpeningStatus.WAITING
        ]

        aggregate_statement = (
            select(
                func.coalesce(
                    func.sum(
                        OpeningCheckin
                        .lateness_minutes
                    ),
                    0,
                ),
                func.coalesce(
                    func.max(
                        OpeningCheckin
                        .lateness_minutes
                    ),
                    0,
                ),
                func.coalesce(
                    func.avg(
                        OpeningCheckin
                        .lateness_minutes
                    ).filter(
                        OpeningCheckin
                        .lateness_minutes > 0
                    ),
                    0,
                ),
            )
            .join(
                Store,
                Store.id
                == OpeningCheckin.store_id,
            )
            .where(
                OpeningCheckin.business_date
                == business_date
            )
        )

        if bush_id is not None:
            aggregate_statement = (
                aggregate_statement.where(
                    Store.bush_id == bush_id
                )
            )

        if cluster_id is not None:
            aggregate_statement = (
                aggregate_statement.where(
                    Store.cluster_id
                    == cluster_id
                )
            )

        aggregate_result = (
            await self.session.execute(
                aggregate_statement
            )
        )

        total_lateness, maximum_lateness, average_lateness = (
            aggregate_result.one()
        )

        completion_percent = (
            round(
                opened_count
                / expected_count
                * 100,
                2,
            )
            if expected_count > 0
            else 0.0
        )

        return {
            "expected_count": expected_count,
            "opened_count": opened_count,
            "waiting_count": waiting_count,
            "missed_count": missed_count,
            "opened_early_count": counts[
                OpeningStatus.OPENED_EARLY
            ],
            "opened_on_time_count": counts[
                OpeningStatus.OPENED_ON_TIME
            ],
            "opened_late_count": counts[
                OpeningStatus.OPENED_LATE
            ],
            "opened_after_alert_count": counts[
                OpeningStatus.OPENED_AFTER_ALERT
            ],
            "manually_confirmed_count": counts[
                OpeningStatus.MANUALLY_CONFIRMED
            ],
            "late_count": late_count,
            "total_lateness_minutes": int(
                total_lateness or 0
            ),
            "maximum_lateness_minutes": int(
                maximum_lateness or 0
            ),
            "average_lateness_minutes": round(
                float(average_lateness or 0),
                2,
            ),
            "completion_percent": (
                completion_percent
            ),
        }

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def ensure_not_opened(
        checkin: OpeningCheckin,
    ) -> None:
        """Забороняє змінювати вже відкрите ТТ."""

        if checkin.actual_open_time is not None:
            raise ValueError(
                "Не можна змінити статус, оскільки "
                "відкриття ТТ уже підтверджено."
            )

    @staticmethod
    def build_local_datetime(
        *,
        business_date: date,
        local_time: time,
        timezone_name: str,
    ) -> datetime:
        """Об’єднує локальну дату й час ТТ."""

        timezone = OpeningRepository.get_timezone(
            timezone_name
        )

        normalized_time = (
            OpeningRepository.normalize_time(
                local_time
            )
        )

        return datetime.combine(
            business_date,
            normalized_time,
            tzinfo=timezone,
        )

    @staticmethod
    def get_timezone(
        timezone_name: str,
    ) -> ZoneInfo:
        """Повертає перевірений часовий пояс."""

        normalized_timezone = (
            timezone_name.strip()
        )

        if not normalized_timezone:
            raise ValueError(
                "Назва часового поясу "
                "не може бути порожньою."
            )

        try:
            return ZoneInfo(
                normalized_timezone
            )

        except ZoneInfoNotFoundError as error:
            raise ValueError(
                "Невідомий часовий пояс: "
                f"{normalized_timezone}."
            ) from error

    @staticmethod
    def normalize_time(
        value: time,
    ) -> time:
        """Прибирає секунди, мікросекунди й timezone."""

        return value.replace(
            second=0,
            microsecond=0,
            tzinfo=None,
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

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{field_name} повинен містити "
                "часовий пояс."
            )

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