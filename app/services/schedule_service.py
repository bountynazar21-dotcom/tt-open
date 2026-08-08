from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, TypeVar

from sqlalchemy import select

from app.database.models.cluster import Cluster
from app.database.models.enums import (
    AuditAction,
    EntityType,
    ScheduleExceptionType,
)
from app.database.models.schedule import (
    ScheduleException,
    StoreSchedule,
)
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories import (
    AuditContext,
    EffectiveSchedule,
    Repositories,
)
from app.services.access import AccessService


EnumType = TypeVar(
    "EnumType",
    bound=Enum,
)


@dataclass(slots=True, frozen=True)
class WeekdayScheduleChangeResult:
    """
    Результат зміни тижневого графіка ТТ.
    """

    store: Store
    schedule: StoreSchedule

    was_created: bool

    previous_values: dict[str, Any]
    current_values: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ScheduleExceptionChangeResult:
    """
    Результат створення або зміни винятку.
    """

    exception: ScheduleException

    store: Store | None
    bush_id: int | None

    was_created: bool

    previous_values: dict[str, Any]
    current_values: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ScheduleDeletionResult:
    """
    Результат видалення графіка або винятку.
    """

    deleted: bool

    entity_id: int | None
    entity_type: str

    previous_values: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ClusterAssignmentResult:
    """
    Результат зміни кластера торгової точки.
    """

    store: Store
    cluster: Cluster | None

    previous_cluster_id: int | None
    current_cluster_id: int | None

    was_changed: bool


@dataclass(slots=True, frozen=True)
class SchedulePreviewItem:
    """
    Фактичний графік ТТ на конкретну дату.
    """

    business_date: date
    weekday: int
    weekday_name: str

    schedule: EffectiveSchedule


class ScheduleService:
    """
    Сервіс управління графіками торгових точок.

    Відповідає за:

    - тижневий графік ТТ;
    - робочі та вихідні дні;
    - копіювання графіка між днями;
    - індивідуальні винятки на дату;
    - винятки для цілого куща;
    - тимчасове закриття;
    - особливий час роботи;
    - призначення часового кластера;
    - перегляд фактичного графіка;
    - AuditLog усіх змін.

    Commit виконується у handler, middleware
    або вищому сервісі.
    """

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
    # ОТРИМАННЯ ГРАФІКА
    # ==========================================

    async def get_store_weekly_schedule(
        self,
        *,
        user: User,
        store_id: int,
    ) -> list[StoreSchedule]:
        """Повертає тижневий графік доступної ТТ."""

        store = await self.access.require_store_view(
            user,
            store_id,
        )

        return (
            await self.repositories.schedules
            .get_weekly_schedule(store.id)
        )

    async def get_effective_schedule(
        self,
        *,
        user: User,
        store_id: int,
        business_date: date,
    ) -> EffectiveSchedule:
        """Повертає фактичний графік ТТ на дату."""

        store = await self.access.require_store_view(
            user,
            store_id,
        )

        return (
            await self.repositories.schedules
            .get_effective_schedule(
                store=store,
                business_date=business_date,
            )
        )

    async def preview_store_schedule(
        self,
        *,
        user: User,
        store_id: int,
        date_from: date,
        date_to: date,
        maximum_days: int = 370,
    ) -> list[SchedulePreviewItem]:
        """
        Формує календар фактичного графіка ТТ.

        Ураховуються:

        - статус ТТ;
        - виняток ТТ;
        - виняток куща;
        - тижневий графік;
        - графік кластера.
        """

        self.validate_date_range(
            date_from=date_from,
            date_to=date_to,
        )

        days_count = (
            date_to - date_from
        ).days + 1

        if days_count > maximum_days:
            raise ValueError(
                "Період перегляду не може "
                f"перевищувати {maximum_days} днів."
            )

        store = await self.access.require_store_view(
            user,
            store_id,
        )

        items: list[SchedulePreviewItem] = []

        current_date = date_from

        while current_date <= date_to:
            effective_schedule = (
                await self.repositories.schedules
                .get_effective_schedule(
                    store=store,
                    business_date=current_date,
                )
            )

            weekday = current_date.weekday()

            items.append(
                SchedulePreviewItem(
                    business_date=current_date,
                    weekday=weekday,
                    weekday_name=(
                        self.repositories.schedules
                        .weekday_name(weekday)
                    ),
                    schedule=effective_schedule,
                )
            )

            current_date += timedelta(days=1)

        return items

    # ==========================================
    # ЗМІНА ОДНОГО ДНЯ ТИЖНЯ
    # ==========================================

    async def set_store_weekday(
        self,
        *,
        actor: User,
        store_id: int,
        weekday: int,
        is_working_day: bool,
        opening_time: time | None = None,
        opening_control_deadline: time | None = None,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        reason: str | None = None,
    ) -> WeekdayScheduleChangeResult:
        """
        Створює або змінює графік одного дня.

        weekday:

        0 — понеділок;
        1 — вівторок;
        2 — середа;
        3 — четвер;
        4 — п’ятниця;
        5 — субота;
        6 — неділя.
        """

        store = (
            await self.access
            .require_schedule_management(
                actor,
                store_id,
            )
        )

        existing = (
            await self.repositories.schedules
            .get_weekday_schedule(
                store_id=store.id,
                weekday=weekday,
                for_update=True,
            )
        )

        previous_values = (
            self.weekday_schedule_snapshot(
                existing
            )
        )

        schedule, was_created = (
            await self.repositories.schedules
            .upsert_weekday_schedule(
                store_id=store.id,
                weekday=weekday,
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
        )

        current_values = (
            self.weekday_schedule_snapshot(
                schedule
            )
        )

        await self.log_weekday_change(
            actor=actor,
            store=store,
            schedule=schedule,
            previous_values=previous_values,
            current_values=current_values,
            reason=reason,
            was_created=was_created,
        )

        return WeekdayScheduleChangeResult(
            store=store,
            schedule=schedule,
            was_created=was_created,
            previous_values=previous_values,
            current_values=current_values,
        )

    async def set_store_day_off(
        self,
        *,
        actor: User,
        store_id: int,
        weekday: int,
        reason: str | None = None,
    ) -> WeekdayScheduleChangeResult:
        """Встановлює постійний вихідний день."""

        return await self.set_store_weekday(
            actor=actor,
            store_id=store_id,
            weekday=weekday,
            is_working_day=False,
            reason=reason,
        )

    async def set_store_working_day(
        self,
        *,
        actor: User,
        store_id: int,
        weekday: int,
        opening_time: time,
        opening_control_deadline: time,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        reason: str | None = None,
    ) -> WeekdayScheduleChangeResult:
        """Встановлює постійний робочий день."""

        return await self.set_store_weekday(
            actor=actor,
            store_id=store_id,
            weekday=weekday,
            is_working_day=True,
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

    # ==========================================
    # КОПІЮВАННЯ ДНЯ
    # ==========================================

    async def copy_store_weekday(
        self,
        *,
        actor: User,
        store_id: int,
        source_weekday: int,
        target_weekdays: set[int],
        reason: str | None = None,
    ) -> list[WeekdayScheduleChangeResult]:
        """Копіює графік одного дня на інші дні."""

        store = (
            await self.access
            .require_schedule_management(
                actor,
                store_id,
            )
        )

        normalized_targets = sorted(
            set(target_weekdays)
        )

        previous_snapshots: dict[
            int,
            dict[str, Any],
        ] = {}

        for weekday in normalized_targets:
            previous = (
                await self.repositories.schedules
                .get_weekday_schedule(
                    store_id=store.id,
                    weekday=weekday,
                    for_update=True,
                )
            )

            previous_snapshots[weekday] = (
                self.weekday_schedule_snapshot(
                    previous
                )
            )

        schedules = (
            await self.repositories.schedules
            .copy_weekday_schedule(
                store_id=store.id,
                source_weekday=source_weekday,
                target_weekdays=normalized_targets,
            )
        )

        results: list[
            WeekdayScheduleChangeResult
        ] = []

        for schedule in schedules:
            previous_values = (
                previous_snapshots.get(
                    schedule.weekday,
                    {},
                )
            )

            current_values = (
                self.weekday_schedule_snapshot(
                    schedule
                )
            )

            was_created = not bool(
                previous_values
            )

            await self.log_weekday_change(
                actor=actor,
                store=store,
                schedule=schedule,
                previous_values=previous_values,
                current_values=current_values,
                reason=(
                    reason
                    or (
                        "Копіювання графіка "
                        f"з дня {source_weekday}"
                    )
                ),
                was_created=was_created,
            )

            results.append(
                WeekdayScheduleChangeResult(
                    store=store,
                    schedule=schedule,
                    was_created=was_created,
                    previous_values=previous_values,
                    current_values=current_values,
                )
            )

        return results

    # ==========================================
    # ПОВНИЙ ТИЖНЕВИЙ ГРАФІК
    # ==========================================

    async def create_default_weekly_schedule(
        self,
        *,
        actor: User,
        store_id: int,
        opening_time: time,
        opening_control_deadline: time,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        working_weekdays: set[int] | None = None,
        reason: str | None = None,
    ) -> list[WeekdayScheduleChangeResult]:
        """Створює або перезаписує весь тиждень."""

        store = (
            await self.access
            .require_schedule_management(
                actor,
                store_id,
            )
        )

        previous_schedules = (
            await self.repositories.schedules
            .get_weekly_schedule(store.id)
        )

        previous_by_weekday = {
            schedule.weekday: (
                self.weekday_schedule_snapshot(
                    schedule
                )
            )
            for schedule in previous_schedules
        }

        schedules = (
            await self.repositories.schedules
            .create_default_weekly_schedule(
                store_id=store.id,
                opening_time=opening_time,
                opening_control_deadline=(
                    opening_control_deadline
                ),
                closing_time=closing_time,
                closing_control_deadline=(
                    closing_control_deadline
                ),
                working_weekdays=working_weekdays,
            )
        )

        results: list[
            WeekdayScheduleChangeResult
        ] = []

        for schedule in schedules:
            previous_values = (
                previous_by_weekday.get(
                    schedule.weekday,
                    {},
                )
            )

            current_values = (
                self.weekday_schedule_snapshot(
                    schedule
                )
            )

            was_created = not bool(
                previous_values
            )

            await self.log_weekday_change(
                actor=actor,
                store=store,
                schedule=schedule,
                previous_values=previous_values,
                current_values=current_values,
                reason=(
                    reason
                    or "Оновлення тижневого графіка"
                ),
                was_created=was_created,
            )

            results.append(
                WeekdayScheduleChangeResult(
                    store=store,
                    schedule=schedule,
                    was_created=was_created,
                    previous_values=previous_values,
                    current_values=current_values,
                )
            )

        return results

    # ==========================================
    # ВИДАЛЕННЯ ТИЖНЕВОГО ГРАФІКА
    # ==========================================

    async def delete_store_weekday(
        self,
        *,
        actor: User,
        store_id: int,
        weekday: int,
        reason: str,
    ) -> ScheduleDeletionResult:
        """
        Видаляє індивідуальний графік дня.

        Після видалення система використовуватиме
        стандартний графік кластера.
        """

        store = (
            await self.access
            .require_schedule_management(
                actor,
                store_id,
            )
        )

        schedule = (
            await self.repositories.schedules
            .get_weekday_schedule(
                store_id=store.id,
                weekday=weekday,
                for_update=True,
            )
        )

        if schedule is None:
            return ScheduleDeletionResult(
                deleted=False,
                entity_id=None,
                entity_type="store_schedule",
                previous_values={},
            )

        schedule_id = schedule.id

        previous_values = (
            self.weekday_schedule_snapshot(
                schedule
            )
        )

        deleted = (
            await self.repositories.schedules
            .delete_weekday_schedule(
                store_id=store.id,
                weekday=weekday,
            )
        )

        if deleted:
            await self.log_schedule_deletion(
                actor=actor,
                store=store,
                entity_id=schedule_id,
                previous_values=previous_values,
                reason=reason,
            )

        return ScheduleDeletionResult(
            deleted=deleted,
            entity_id=schedule_id,
            entity_type="store_schedule",
            previous_values=previous_values,
        )

    async def delete_store_weekly_schedule(
        self,
        *,
        actor: User,
        store_id: int,
        reason: str,
    ) -> int:
        """
        Видаляє весь індивідуальний графік ТТ.

        Після цього використовується графік кластера.
        """

        store = (
            await self.access
            .require_schedule_management(
                actor,
                store_id,
            )
        )

        schedules = (
            await self.repositories.schedules
            .get_weekly_schedule(store.id)
        )

        if not schedules:
            return 0

        snapshots = [
            self.weekday_schedule_snapshot(
                schedule
            )
            for schedule in schedules
        ]

        deleted_count = (
            await self.repositories.schedules
            .delete_store_weekly_schedule(
                store_id=store.id
            )
        )

        if deleted_count > 0:
            action = self.resolve_audit_action(
                "delete",
                "removed",
                "deactivate",
            )

            entity_type = self.resolve_entity_type(
                "store_schedule",
                "schedule",
                "store",
            )

            await self.repositories.audit.log_action(
                action=action,
                entity_type=entity_type,
                entity_id=store.id,
                context=AuditContext(
                    actor_user_id=actor.id,
                    reason=reason,
                    description=(
                        "Видалено індивідуальний "
                        f"тижневий графік "
                        f"{self.store_display_name(store)}"
                    ),
                    source="telegram_bot",
                ),
                old_values={
                    "schedules": snapshots,
                },
                new_values={
                    "schedules": [],
                    "fallback": "cluster_default",
                },
            )

        return deleted_count

    # ==========================================
    # ВИНЯТОК ДЛЯ ТТ
    # ==========================================

    async def create_store_day_off(
        self,
        *,
        actor: User,
        store_id: int,
        exception_date: date,
        reason: str,
    ) -> ScheduleExceptionChangeResult:
        """Створює разовий вихідний для ТТ."""

        return await self.set_store_exception(
            actor=actor,
            store_id=store_id,
            exception_date=exception_date,
            exception_type=(
                self.resolve_exception_type(
                    "day_off"
                )
            ),
            reason=reason,
        )

    async def create_store_custom_hours(
        self,
        *,
        actor: User,
        store_id: int,
        exception_date: date,
        opening_time: time,
        opening_control_deadline: time,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        reason: str | None = None,
    ) -> ScheduleExceptionChangeResult:
        """Створює особливий графік ТТ на дату."""

        return await self.set_store_exception(
            actor=actor,
            store_id=store_id,
            exception_date=exception_date,
            exception_type=(
                self.resolve_exception_type(
                    "custom_hours"
                )
            ),
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

    async def create_store_temporary_closure(
        self,
        *,
        actor: User,
        store_id: int,
        exception_date: date,
        reason: str,
    ) -> ScheduleExceptionChangeResult:
        """Тимчасово виключає ТТ із контролю на дату."""

        return await self.set_store_exception(
            actor=actor,
            store_id=store_id,
            exception_date=exception_date,
            exception_type=(
                self.resolve_exception_type(
                    "temporarily_closed"
                )
            ),
            reason=reason,
        )

    async def set_store_exception(
        self,
        *,
        actor: User,
        store_id: int,
        exception_date: date,
        exception_type: ScheduleExceptionType,
        opening_time: time | None = None,
        opening_control_deadline: time | None = None,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        reason: str | None = None,
    ) -> ScheduleExceptionChangeResult:
        """Створює або змінює виняток конкретної ТТ."""

        store = (
            await self.access
            .require_schedule_management(
                actor,
                store_id,
            )
        )

        existing = (
            await self.repositories.schedules
            .get_store_exception(
                store_id=store.id,
                exception_date=exception_date,
                for_update=True,
            )
        )

        previous_values = (
            self.exception_snapshot(existing)
        )

        exception, was_created = (
            await self.repositories.schedules
            .upsert_exception(
                store_id=store.id,
                exception_date=exception_date,
                exception_type=exception_type,
                created_by_id=actor.id,
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
        )

        current_values = (
            self.exception_snapshot(
                exception
            )
        )

        await self.log_exception_change(
            actor=actor,
            exception=exception,
            previous_values=previous_values,
            current_values=current_values,
            was_created=was_created,
            store=store,
            bush_id=None,
            reason=reason,
        )

        return ScheduleExceptionChangeResult(
            exception=exception,
            store=store,
            bush_id=None,
            was_created=was_created,
            previous_values=previous_values,
            current_values=current_values,
        )

    # ==========================================
    # ВИНЯТОК ДЛЯ КУЩА
    # ==========================================

    async def create_bush_day_off(
        self,
        *,
        actor: User,
        bush_id: int,
        exception_date: date,
        reason: str,
    ) -> ScheduleExceptionChangeResult:
        """Створює вихідний для всього куща."""

        return await self.set_bush_exception(
            actor=actor,
            bush_id=bush_id,
            exception_date=exception_date,
            exception_type=(
                self.resolve_exception_type(
                    "day_off"
                )
            ),
            reason=reason,
        )

    async def create_bush_custom_hours(
        self,
        *,
        actor: User,
        bush_id: int,
        exception_date: date,
        opening_time: time,
        opening_control_deadline: time,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        reason: str | None = None,
    ) -> ScheduleExceptionChangeResult:
        """Створює особливий графік для куща."""

        return await self.set_bush_exception(
            actor=actor,
            bush_id=bush_id,
            exception_date=exception_date,
            exception_type=(
                self.resolve_exception_type(
                    "custom_hours"
                )
            ),
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

    async def set_bush_exception(
        self,
        *,
        actor: User,
        bush_id: int,
        exception_date: date,
        exception_type: ScheduleExceptionType,
        opening_time: time | None = None,
        opening_control_deadline: time | None = None,
        closing_time: time | None = None,
        closing_control_deadline: time | None = None,
        reason: str | None = None,
    ) -> ScheduleExceptionChangeResult:
        """Створює або змінює виняток цілого куща."""

        bush = (
            await self.access
            .require_bush_management(
                actor,
                bush_id,
            )
        )

        existing = (
            await self.repositories.schedules
            .get_bush_exception(
                bush_id=bush.id,
                exception_date=exception_date,
                for_update=True,
            )
        )

        previous_values = (
            self.exception_snapshot(existing)
        )

        exception, was_created = (
            await self.repositories.schedules
            .upsert_exception(
                bush_id=bush.id,
                exception_date=exception_date,
                exception_type=exception_type,
                created_by_id=actor.id,
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
        )

        current_values = (
            self.exception_snapshot(
                exception
            )
        )

        await self.log_exception_change(
            actor=actor,
            exception=exception,
            previous_values=previous_values,
            current_values=current_values,
            was_created=was_created,
            store=None,
            bush_id=bush.id,
            reason=reason,
        )

        return ScheduleExceptionChangeResult(
            exception=exception,
            store=None,
            bush_id=bush.id,
            was_created=was_created,
            previous_values=previous_values,
            current_values=current_values,
        )

    # ==========================================
    # ВИДАЛЕННЯ ВИНЯТКУ
    # ==========================================

    async def delete_exception(
        self,
        *,
        actor: User,
        exception_id: int,
        reason: str,
    ) -> ScheduleDeletionResult:
        """Видаляє виняток графіка."""

        exception = (
            await self.repositories.schedules
            .get_exception_by_id_or_raise(
                exception_id,
                for_update=True,
            )
        )

        store: Store | None = None

        if exception.store_id is not None:
            store = (
                await self.access
                .require_schedule_management(
                    actor,
                    exception.store_id,
                )
            )

        elif exception.bush_id is not None:
            await self.access.require_bush_management(
                actor,
                exception.bush_id,
            )

        else:
            raise ValueError(
                "Виняток не прив’язаний "
                "ні до ТТ, ні до куща."
            )

        previous_values = (
            self.exception_snapshot(
                exception
            )
        )

        await self.repositories.schedules.delete_exception(
            exception
        )

        action = self.resolve_audit_action(
            "delete",
            "removed",
            "deactivate",
        )

        entity_type = self.resolve_entity_type(
            "schedule_exception",
            "schedule",
            "store",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=exception_id,
            context=AuditContext(
                actor_user_id=actor.id,
                business_date=(
                    exception.exception_date
                ),
                reason=reason,
                description=(
                    "Видалено виняток графіка"
                    + (
                        f" {self.store_display_name(store)}"
                        if store is not None
                        else (
                            f" куща №{exception.bush_id}"
                        )
                    )
                ),
                source="telegram_bot",
            ),
            old_values=previous_values,
            new_values={},
        )

        return ScheduleDeletionResult(
            deleted=True,
            entity_id=exception_id,
            entity_type="schedule_exception",
            previous_values=previous_values,
        )

    # ==========================================
    # СПИСКИ ВИНЯТКІВ
    # ==========================================

    async def get_store_exceptions(
        self,
        *,
        user: User,
        store_id: int,
        date_from: date,
        date_to: date,
    ) -> list[ScheduleException]:
        """Повертає винятки доступної ТТ."""

        self.validate_date_range(
            date_from=date_from,
            date_to=date_to,
        )

        store = await self.access.require_store_view(
            user,
            store_id,
        )

        return (
            await self.repositories.schedules
            .get_store_exceptions_between(
                store_id=store.id,
                date_from=date_from,
                date_to=date_to,
            )
        )

    async def get_exceptions_for_date(
        self,
        *,
        user: User,
        exception_date: date,
        store_id: int | None = None,
        bush_id: int | None = None,
    ) -> list[ScheduleException]:
        """Повертає доступні винятки на дату."""

        if store_id is not None:
            await self.access.require_store_view(
                user,
                store_id,
            )

        elif bush_id is not None:
            await self.access.require_bush_view(
                user,
                bush_id,
            )

        else:
            self.access.require_network_view(user)

        return (
            await self.repositories.schedules
            .get_exceptions_for_date(
                exception_date,
                store_id=store_id,
                bush_id=bush_id,
            )
        )

    # ==========================================
    # ПРИЗНАЧЕННЯ КЛАСТЕРА
    # ==========================================

    async def assign_store_cluster(
        self,
        *,
        actor: User,
        store_id: int,
        cluster_id: int,
        reason: str,
    ) -> ClusterAssignmentResult:
        """Призначає ТТ часовий кластер."""

        store = (
            await self.access
            .require_schedule_management(
                actor,
                store_id,
            )
        )

        cluster = await self.session.get(
            Cluster,
            cluster_id,
        )

        if cluster is None:
            raise ValueError(
                "Часовий кластер не знайдено."
            )

        if not cluster.is_active:
            raise ValueError(
                "Не можна призначити "
                "неактивний кластер."
            )

        previous_cluster_id = store.cluster_id

        if previous_cluster_id == cluster.id:
            return ClusterAssignmentResult(
                store=store,
                cluster=cluster,
                previous_cluster_id=(
                    previous_cluster_id
                ),
                current_cluster_id=cluster.id,
                was_changed=False,
            )

        store.cluster_id = cluster.id

        self.session.add(store)
        await self.session.flush()

        await self.log_cluster_assignment(
            actor=actor,
            store=store,
            previous_cluster_id=(
                previous_cluster_id
            ),
            current_cluster_id=cluster.id,
            reason=reason,
        )

        return ClusterAssignmentResult(
            store=store,
            cluster=cluster,
            previous_cluster_id=(
                previous_cluster_id
            ),
            current_cluster_id=cluster.id,
            was_changed=True,
        )

    async def remove_store_cluster(
        self,
        *,
        actor: User,
        store_id: int,
        reason: str,
    ) -> ClusterAssignmentResult:
        """
        Прибирає кластер із ТТ.

        Після цього ТТ повинна мати
        індивідуальний тижневий графік.
        """

        store = (
            await self.access
            .require_schedule_management(
                actor,
                store_id,
            )
        )

        previous_cluster_id = store.cluster_id

        if previous_cluster_id is None:
            return ClusterAssignmentResult(
                store=store,
                cluster=None,
                previous_cluster_id=None,
                current_cluster_id=None,
                was_changed=False,
            )

        weekly_schedule = (
            await self.repositories.schedules
            .get_weekly_schedule(store.id)
        )

        if not weekly_schedule:
            raise ValueError(
                "Перед видаленням кластера потрібно "
                "налаштувати індивідуальний графік ТТ."
            )

        store.cluster_id = None

        self.session.add(store)
        await self.session.flush()

        await self.log_cluster_assignment(
            actor=actor,
            store=store,
            previous_cluster_id=(
                previous_cluster_id
            ),
            current_cluster_id=None,
            reason=reason,
        )

        return ClusterAssignmentResult(
            store=store,
            cluster=None,
            previous_cluster_id=(
                previous_cluster_id
            ),
            current_cluster_id=None,
            was_changed=True,
        )

    async def get_active_clusters(
        self,
    ) -> list[Cluster]:
        """Повертає активні часові кластери."""

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

    # ==========================================
    # AUDIT: ТИЖНЕВИЙ ГРАФІК
    # ==========================================

    async def log_weekday_change(
        self,
        *,
        actor: User,
        store: Store,
        schedule: StoreSchedule,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
        reason: str | None,
        was_created: bool,
    ) -> None:
        """Фіксує створення або зміну дня."""

        action = self.resolve_audit_action(
            "create" if was_created else "update",
            "created" if was_created else "changed",
        )

        entity_type = self.resolve_entity_type(
            "store_schedule",
            "schedule",
            "store",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=schedule.id,
            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=(
                    f"Змінено графік "
                    f"{self.store_display_name(store)}: "
                    f"{self.repositories.schedules.weekday_name(schedule.weekday)}"
                ),
                source="telegram_bot",
            ),
            old_values=previous_values,
            new_values=current_values,
        )

    async def log_schedule_deletion(
        self,
        *,
        actor: User,
        store: Store,
        entity_id: int,
        previous_values: dict[str, Any],
        reason: str,
    ) -> None:
        """Фіксує видалення графіка дня."""

        action = self.resolve_audit_action(
            "delete",
            "removed",
            "deactivate",
        )

        entity_type = self.resolve_entity_type(
            "store_schedule",
            "schedule",
            "store",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=(
                    "Видалено індивідуальний "
                    f"графік дня "
                    f"{self.store_display_name(store)}"
                ),
                source="telegram_bot",
            ),
            old_values=previous_values,
            new_values={},
        )

    # ==========================================
    # AUDIT: ВИНЯТКИ
    # ==========================================

    async def log_exception_change(
        self,
        *,
        actor: User,
        exception: ScheduleException,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
        was_created: bool,
        store: Store | None,
        bush_id: int | None,
        reason: str | None,
    ) -> None:
        """Фіксує створення або зміну винятку."""

        action = self.resolve_audit_action(
            "create" if was_created else "update",
            "created" if was_created else "changed",
        )

        entity_type = self.resolve_entity_type(
            "schedule_exception",
            "schedule",
            "store",
        )

        target_name = (
            self.store_display_name(store)
            if store is not None
            else f"кущ №{bush_id}"
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=exception.id,
            context=AuditContext(
                actor_user_id=actor.id,
                business_date=(
                    exception.exception_date
                ),
                reason=reason,
                description=(
                    f"Змінено виняток графіка: "
                    f"{target_name}"
                ),
                source="telegram_bot",
            ),
            old_values=previous_values,
            new_values=current_values,
        )

    # ==========================================
    # AUDIT: КЛАСТЕР
    # ==========================================

    async def log_cluster_assignment(
        self,
        *,
        actor: User,
        store: Store,
        previous_cluster_id: int | None,
        current_cluster_id: int | None,
        reason: str,
    ) -> None:
        """Фіксує зміну кластера ТТ."""

        action = self.resolve_audit_action(
            "update",
            "changed",
            "edit",
        )

        entity_type = self.resolve_entity_type(
            "store",
            "shop",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=store.id,
            context=AuditContext(
                actor_user_id=actor.id,
                reason=reason,
                description=(
                    f"Змінено часовий кластер "
                    f"{self.store_display_name(store)}"
                ),
                source="telegram_bot",
            ),
            old_values={
                "cluster_id": (
                    previous_cluster_id
                ),
            },
            new_values={
                "cluster_id": (
                    current_cluster_id
                ),
            },
        )

    # ==========================================
    # ЗНІМКИ ОБ’ЄКТІВ
    # ==========================================

    @staticmethod
    def weekday_schedule_snapshot(
        schedule: StoreSchedule | None,
    ) -> dict[str, Any]:
        """Створює знімок тижневого графіка."""

        if schedule is None:
            return {}

        return {
            "id": schedule.id,
            "store_id": schedule.store_id,
            "weekday": schedule.weekday,
            "is_working_day": (
                schedule.is_working_day
            ),
            "opening_time": (
                ScheduleService.time_to_text(
                    schedule.opening_time
                )
            ),
            "opening_control_deadline": (
                ScheduleService.time_to_text(
                    schedule
                    .opening_control_deadline
                )
            ),
            "closing_time": (
                ScheduleService.time_to_text(
                    schedule.closing_time
                )
            ),
            "closing_control_deadline": (
                ScheduleService.time_to_text(
                    schedule
                    .closing_control_deadline
                )
            ),
        }

    @staticmethod
    def exception_snapshot(
        exception: ScheduleException | None,
    ) -> dict[str, Any]:
        """Створює знімок винятку графіка."""

        if exception is None:
            return {}

        return {
            "id": exception.id,
            "store_id": exception.store_id,
            "bush_id": exception.bush_id,
            "exception_date": (
                exception.exception_date
                .isoformat()
            ),
            "exception_type": (
                exception.exception_type.value
            ),
            "opening_time": (
                ScheduleService.time_to_text(
                    exception.opening_time
                )
            ),
            "opening_control_deadline": (
                ScheduleService.time_to_text(
                    exception
                    .opening_control_deadline
                )
            ),
            "closing_time": (
                ScheduleService.time_to_text(
                    exception.closing_time
                )
            ),
            "closing_control_deadline": (
                ScheduleService.time_to_text(
                    exception
                    .closing_control_deadline
                )
            ),
            "reason": exception.reason,
            "created_by_id": (
                exception.created_by_id
            ),
        }

    # ==========================================
    # ФОРМАТУВАННЯ
    # ==========================================

    @staticmethod
    def format_effective_schedule(
        schedule: EffectiveSchedule,
    ) -> str:
        """Формує короткий текст графіка."""

        if not schedule.is_working_day:
            return (
                schedule.reason
                or "Вихідний день"
            )

        parts: list[str] = []

        if schedule.opening_time is not None:
            parts.append(
                "відкриття "
                f"{schedule.opening_time.strftime('%H:%M')}"
            )

        if (
            schedule.opening_control_deadline
            is not None
        ):
            parts.append(
                "дедлайн відкриття "
                f"{schedule.opening_control_deadline.strftime('%H:%M')}"
            )

        if schedule.closing_time is not None:
            parts.append(
                "закриття "
                f"{schedule.closing_time.strftime('%H:%M')}"
            )

        if (
            schedule.closing_control_deadline
            is not None
        ):
            parts.append(
                "дедлайн звіту "
                f"{schedule.closing_control_deadline.strftime('%H:%M')}"
            )

        return ", ".join(parts) or (
            "Графік не налаштований"
        )

    @staticmethod
    def store_display_name(
        store: Store | None,
    ) -> str:
        """Формує коротку назву ТТ."""

        if store is None:
            return "Невідома ТТ"

        code = getattr(
            store,
            "code",
            None,
        )

        if code:
            return str(code)

        store_number = getattr(
            store,
            "store_number",
            None,
        )

        if store_number is not None:
            return f"SB-{store_number}"

        return f"ТТ #{store.id}"

    @staticmethod
    def time_to_text(
        value: time | None,
    ) -> str | None:
        """Перетворює час у HH:MM."""

        if value is None:
            return None

        return value.strftime("%H:%M")

    # ==========================================
    # ENUM-РЕЗОЛВЕРИ
    # ==========================================

    def resolve_exception_type(
        self,
        requested_type: str,
    ) -> ScheduleExceptionType:
        """Знаходить тип винятку графіка."""

        return (
            self.repositories.schedules
            .resolve_exception_type(
                requested_type
            )
        )

    @classmethod
    def resolve_audit_action(
        cls,
        *names: str,
    ) -> AuditAction:
        """Знаходить AuditAction."""

        try:
            return cls.resolve_enum_member(
                AuditAction,
                *names,
            )

        except ValueError:
            return cls.resolve_enum_member(
                AuditAction,
                "update",
                "updated",
                "change",
                "changed",
            )

    @classmethod
    def resolve_entity_type(
        cls,
        *names: str,
    ) -> EntityType:
        """Знаходить EntityType."""

        return cls.resolve_enum_member(
            EntityType,
            *names,
        )

    @staticmethod
    def resolve_enum_member(
        enum_class: type[EnumType],
        *names: str,
    ) -> EnumType:
        """Шукає enum за назвою або значенням."""

        normalized_names = {
            name.strip().lower()
            for name in names
            if name.strip()
        }

        for enum_item in enum_class:
            values = {
                enum_item.name.lower(),
                str(enum_item.value).lower(),
            }

            if values.intersection(
                normalized_names
            ):
                return enum_item

        raise ValueError(
            f"У {enum_class.__name__} відсутнє "
            f"значення: {sorted(normalized_names)}."
        )

    # ==========================================
    # ВАЛІДАЦІЯ
    # ==========================================

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
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        """Перевіряє часовий пояс."""

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{field_name} повинен містити "
                "часовий пояс."
            )