from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.database.models.bush import Bush
from app.database.models.enums import (
    AuditAction,
    EntityType,
    NotificationType,
    OpeningStatus,
    SummaryType,
    UserRole,
    UserStatus,
)
from app.database.models.notification import (
    NotificationLog,
)
from app.database.models.opening_checkin import (
    OpeningCheckin,
)
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories import (
    AuditContext,
    EffectiveSchedule,
    OpeningPlan,
    Repositories,
    SummaryUpdateDecision,
)
from app.services.access import AccessService


EnumType = TypeVar(
    "EnumType",
    bound=Enum,
)


@dataclass(slots=True, frozen=True)
class OpeningPreparationResult:
    """
    Результат підготовки ранкових записів.
    """

    business_date: date

    expected_stores: int
    created_records: int
    existing_records: int

    checkins: tuple[OpeningCheckin, ...]


@dataclass(slots=True, frozen=True)
class OpeningConfirmationResult:
    """
    Результат підтвердження відкриття ТТ.
    """

    store: Store
    schedule: EffectiveSchedule
    checkin: OpeningCheckin

    was_confirmed_now: bool

    lateness_minutes: int
    is_late: bool

    summary_updates: tuple[
        SummaryUpdateDecision,
        ...,
    ]


@dataclass(slots=True, frozen=True)
class OpeningDeadlineResult:
    """
    Результат перевірки пропущених дедлайнів.
    """

    business_date: date

    missed_checkins: tuple[
        OpeningCheckin,
        ...,
    ]

    notifications: tuple[
        NotificationLog,
        ...,
    ]

    created_notifications: int
    existing_notifications: int

    summary_updates: tuple[
        SummaryUpdateDecision,
        ...,
    ]

    @property
    def missed_count(self) -> int:
        return len(self.missed_checkins)


@dataclass(slots=True, frozen=True)
class OpeningManualUpdateResult:
    """
    Результат ручного коригування відкриття.
    """

    store: Store
    checkin: OpeningCheckin

    previous_values: dict[str, Any]
    current_values: dict[str, Any]

    summary_updates: tuple[
        SummaryUpdateDecision,
        ...,
    ]


class OpeningService:
    """
    Сервіс ранкового відкриття торгових точок.

    Об’єднує:

    - права доступу;
    - фактичний графік ТТ;
    - створення щоденних чекінів;
    - фіксацію відкриття;
    - розрахунок запізнення;
    - пропущені дедлайни;
    - Telegram-сповіщення;
    - AuditLog;
    - живі підсумки кущів і мережі.

    Telegram API тут безпосередньо не викликається.

    Сервіс:
    - створює записи повідомлень у черзі;
    - готує рішення для живих підсумків;
    - повертає результат у handler або scheduler.
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
    # ПІДГОТОВКА РАНКОВИХ ЗАПИСІВ
    # ==========================================

    async def prepare_daily_records(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> OpeningPreparationResult:
        """
        Створює ранкові записи для всіх ТТ,
        які повинні відкритися цього дня.

        Існуючі записи не змінюються.
        """

        scheduled_stores = (
            await self.repositories.schedules
            .get_stores_requiring_opening(
                business_date=business_date,
                bush_id=bush_id,
                cluster_id=cluster_id,
            )
        )

        plans = [
            OpeningPlan(
                store_id=store.id,
                business_date=business_date,
                scheduled_open_time=(
                    schedule.opening_time
                ),
                control_deadline=(
                    schedule
                    .opening_control_deadline
                ),
            )
            for store, schedule in scheduled_stores
            if (
                schedule.opening_time is not None
                and schedule
                .opening_control_deadline
                is not None
            )
        ]

        created_checkins = (
            await self.repositories.openings
            .create_missing_records(plans)
        )

        all_checkins = (
            await self.repositories.openings
            .get_for_date(
                business_date=business_date,
                bush_id=bush_id,
                cluster_id=cluster_id,
            )
        )

        return OpeningPreparationResult(
            business_date=business_date,
            expected_stores=len(plans),
            created_records=len(created_checkins),
            existing_records=(
                len(plans)
                - len(created_checkins)
            ),
            checkins=tuple(all_checkins),
        )

    async def prepare_store_record(
        self,
        *,
        store: Store,
        business_date: date,
    ) -> tuple[
        OpeningCheckin,
        EffectiveSchedule,
        bool,
    ]:
        """
        Створює ранковий запис конкретної ТТ.
        """

        schedule = (
            await self.repositories.schedules
            .get_effective_schedule(
                store=store,
                business_date=business_date,
            )
        )

        self.ensure_opening_required(
            schedule
        )

        checkin, was_created = (
            await self.repositories.openings
            .get_or_create_waiting(
                store_id=store.id,
                business_date=business_date,
                scheduled_open_time=(
                    schedule.opening_time
                ),
                control_deadline=(
                    schedule
                    .opening_control_deadline
                ),
            )
        )

        return (
            checkin,
            schedule,
            was_created,
        )

    # ==========================================
    # ЗВИЧАЙНЕ ПІДТВЕРДЖЕННЯ ВІДКРИТТЯ
    # ==========================================

    async def confirm_opening(
        self,
        *,
        user: User,
        store_id: int,
        current_time: datetime,
        timezone_name: str | None = None,
        source: str = "telegram_bot",
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
        update_summaries: bool = True,
    ) -> OpeningConfirmationResult:
        """
        Фіксує відкриття ТТ працівником.

        Час відкриття береться із сервера,
        а не з повідомлення користувача.
        """

        self.validate_aware_datetime(
            current_time,
            field_name="current_time",
        )

        store = (
            await self.access
            .require_store_operation(
                user,
                store_id,
            )
        )

        resolved_timezone = (
            timezone_name
            or await self.get_timezone_name()
        )

        local_time = current_time.astimezone(
            self.get_timezone(
                resolved_timezone
            )
        )

        business_date = local_time.date()

        _, schedule, _ = (
            await self.prepare_store_record(
                store=store,
                business_date=business_date,
            )
        )

        checkin, was_confirmed_now = (
            await self.repositories.openings
            .confirm_opening(
                store_id=store.id,
                business_date=business_date,
                actual_open_time=current_time,
                submitted_by_id=user.id,
                scheduled_open_time=(
                    schedule.opening_time
                ),
                control_deadline=(
                    schedule
                    .opening_control_deadline
                ),
                timezone_name=resolved_timezone,
                source=source,
                telegram_chat_id=(
                    telegram_chat_id
                ),
                telegram_message_id=(
                    telegram_message_id
                ),
            )
        )

        if was_confirmed_now:
            await self.log_opening_confirmation(
                user=user,
                store=store,
                checkin=checkin,
                schedule=schedule,
                business_date=business_date,
                source=source,
                telegram_chat_id=(
                    telegram_chat_id
                ),
                telegram_message_id=(
                    telegram_message_id
                ),
            )

        summary_updates: list[
            SummaryUpdateDecision
        ] = []

        if (
            was_confirmed_now
            and update_summaries
        ):
            summary_updates = (
                await self.prepare_summary_updates(
                    business_date=business_date,
                    changed_store=store,
                    timezone_name=resolved_timezone,
                )
            )

        lateness_minutes = int(
            getattr(
                checkin,
                "lateness_minutes",
                0,
            )
            or 0
        )

        return OpeningConfirmationResult(
            store=store,
            schedule=schedule,
            checkin=checkin,
            was_confirmed_now=(
                was_confirmed_now
            ),
            lateness_minutes=lateness_minutes,
            is_late=lateness_minutes > 0,
            summary_updates=tuple(
                summary_updates
            ),
        )

    # ==========================================
    # РУЧНЕ ПІДТВЕРДЖЕННЯ
    # ==========================================

    async def manually_confirm_opening(
        self,
        *,
        actor: User,
        store_id: int,
        business_date: date,
        actual_open_time: datetime,
        reason: str,
        modified_at: datetime,
        timezone_name: str | None = None,
        update_summaries: bool = True,
    ) -> OpeningManualUpdateResult:
        """
        Ручне підтвердження відкриття.

        Доступне:
        - ROOT_ADMIN;
        - директору;
        - адміністратору відповідного куща.
        """

        self.validate_aware_datetime(
            actual_open_time,
            field_name="actual_open_time",
        )

        self.validate_aware_datetime(
            modified_at,
            field_name="modified_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        decision = (
            await self.access
            .can_manually_confirm_opening(
                actor,
                store_id,
            )
        )

        decision.raise_if_denied()

        store = await self.access.get_store_or_raise(
            store_id
        )

        resolved_timezone = (
            timezone_name
            or await self.get_timezone_name()
        )

        checkin, _, _ = (
            await self.prepare_store_record(
                store=store,
                business_date=business_date,
            )
        )

        previous_values = (
            self.opening_snapshot(checkin)
        )

        checkin = (
            await self.repositories.openings
            .manually_confirm(
                store_id=store.id,
                business_date=business_date,
                actual_open_time=(
                    actual_open_time
                ),
                modified_by_id=actor.id,
                modified_at=modified_at,
                reason=normalized_reason,
                timezone_name=resolved_timezone,
            )
        )

        current_values = (
            self.opening_snapshot(checkin)
        )

        await self.log_manual_confirmation(
            actor=actor,
            store=store,
            checkin=checkin,
            previous_values=previous_values,
            current_values=current_values,
            reason=normalized_reason,
            business_date=business_date,
        )

        summary_updates: list[
            SummaryUpdateDecision
        ] = []

        if update_summaries:
            summary_updates = (
                await self.prepare_summary_updates(
                    business_date=business_date,
                    changed_store=store,
                    timezone_name=resolved_timezone,
                )
            )

        return OpeningManualUpdateResult(
            store=store,
            checkin=checkin,
            previous_values=previous_values,
            current_values=current_values,
            summary_updates=tuple(
                summary_updates
            ),
        )

    # ==========================================
    # КОРИГУВАННЯ ЧАСУ ВІДКРИТТЯ
    # ==========================================

    async def modify_opening_time(
        self,
        *,
        actor: User,
        checkin_id: int,
        new_actual_open_time: datetime,
        modified_at: datetime,
        reason: str,
        timezone_name: str | None = None,
        update_summaries: bool = True,
    ) -> OpeningManualUpdateResult:
        """Змінює помилково зафіксований час."""

        self.validate_aware_datetime(
            new_actual_open_time,
            field_name="new_actual_open_time",
        )

        self.validate_aware_datetime(
            modified_at,
            field_name="modified_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        checkin = (
            await self.repositories.openings
            .get_checkin_for_update(
                checkin_id
            )
        )

        if checkin is None:
            raise ValueError(
                "Запис відкриття не знайдено."
            )

        decision = (
            await self.access
            .can_manually_confirm_opening(
                actor,
                checkin.store_id,
            )
        )

        decision.raise_if_denied()

        store = await self.access.get_store_or_raise(
            checkin.store_id
        )

        previous_values = (
            self.opening_snapshot(checkin)
        )

        resolved_timezone = (
            timezone_name
            or await self.get_timezone_name()
        )

        checkin = (
            await self.repositories.openings
            .modify_opening_time(
                checkin_id=checkin.id,
                new_actual_open_time=(
                    new_actual_open_time
                ),
                modified_by_id=actor.id,
                modified_at=modified_at,
                reason=normalized_reason,
                timezone_name=resolved_timezone,
            )
        )

        current_values = (
            self.opening_snapshot(checkin)
        )

        await self.log_opening_modification(
            actor=actor,
            store=store,
            checkin=checkin,
            previous_values=previous_values,
            current_values=current_values,
            reason=normalized_reason,
        )

        summary_updates: list[
            SummaryUpdateDecision
        ] = []

        if update_summaries:
            summary_updates = (
                await self.prepare_summary_updates(
                    business_date=(
                        checkin.business_date
                    ),
                    changed_store=store,
                    timezone_name=resolved_timezone,
                )
            )

        return OpeningManualUpdateResult(
            store=store,
            checkin=checkin,
            previous_values=previous_values,
            current_values=current_values,
            summary_updates=tuple(
                summary_updates
            ),
        )

    # ==========================================
    # ПЕРЕВІРКА ДЕДЛАЙНІВ
    # ==========================================

    async def process_due_deadlines(
        self,
        *,
        current_time: datetime,
        timezone_name: str | None = None,
        bush_id: int | None = None,
        cluster_id: int | None = None,
        create_notifications: bool = True,
        update_summaries: bool = True,
    ) -> OpeningDeadlineResult:
        """
        Фіксує ТТ, які не відкрилися до дедлайну.

        Метод призначений для APScheduler.
        """

        self.validate_aware_datetime(
            current_time,
            field_name="current_time",
        )

        opening_enabled = (
            await self.repositories.settings
            .get_bool(
                self.repositories.settings
                .OPENING_CONTROL_ENABLED,
                default=True,
            )
        )

        resolved_timezone = (
            timezone_name
            or await self.get_timezone_name()
        )

        timezone = self.get_timezone(
            resolved_timezone
        )

        business_date = (
            current_time
            .astimezone(timezone)
            .date()
        )

        if not opening_enabled:
            return OpeningDeadlineResult(
                business_date=business_date,
                missed_checkins=(),
                notifications=(),
                created_notifications=0,
                existing_notifications=0,
                summary_updates=(),
            )

        await self.prepare_daily_records(
            business_date=business_date,
            bush_id=bush_id,
            cluster_id=cluster_id,
        )

        missed_checkins = (
            await self.repositories.openings
            .mark_due_deadlines_missed(
                current_time=current_time,
                timezone_name=resolved_timezone,
                business_date=business_date,
                bush_id=bush_id,
                cluster_id=cluster_id,
                alert_sent=False,
            )
        )

        notifications: list[
            NotificationLog
        ] = []

        created_notifications = 0
        existing_notifications = 0

        notifications_enabled = (
            await self.repositories.settings
            .get_bool(
                self.repositories.settings
                .OPENING_NOTIFICATIONS_ENABLED,
                default=True,
            )
        )

        if (
            create_notifications
            and notifications_enabled
        ):
            for checkin in missed_checkins:
                store = (
                    await self.access
                    .get_store_or_raise(
                        checkin.store_id
                    )
                )

                queued, created_count = (
                    await self.queue_missed_notifications(
                        store=store,
                        checkin=checkin,
                        queued_at=current_time,
                        timezone_name=(
                            resolved_timezone
                        ),
                    )
                )

                notifications.extend(queued)
                created_notifications += (
                    created_count
                )

                existing_notifications += (
                    len(queued)
                    - created_count
                )

        for checkin in missed_checkins:
            store = (
                await self.access
                .get_store_or_raise(
                    checkin.store_id
                )
            )

            await self.log_missed_deadline(
                store=store,
                checkin=checkin,
                business_date=business_date,
            )

        summary_updates: list[
            SummaryUpdateDecision
        ] = []

        if (
            missed_checkins
            and update_summaries
        ):
            changed_bush_ids = {
                store.bush_id
                for store in await self.load_stores(
                    {
                        checkin.store_id
                        for checkin
                        in missed_checkins
                    }
                )
                if store.bush_id is not None
            }

            summary_updates = (
                await self.prepare_summary_updates(
                    business_date=business_date,
                    bush_ids=changed_bush_ids,
                    timezone_name=resolved_timezone,
                )
            )

        return OpeningDeadlineResult(
            business_date=business_date,
            missed_checkins=tuple(
                missed_checkins
            ),
            notifications=tuple(
                notifications
            ),
            created_notifications=(
                created_notifications
            ),
            existing_notifications=(
                existing_notifications
            ),
            summary_updates=tuple(
                summary_updates
            ),
        )

    # ==========================================
    # СПОВІЩЕННЯ ПРО ПРОПУЩЕНИЙ ДЕДЛАЙН
    # ==========================================

    async def queue_missed_notifications(
        self,
        *,
        store: Store,
        checkin: OpeningCheckin,
        queued_at: datetime,
        timezone_name: str,
    ) -> tuple[list[NotificationLog], int]:
        """
        Створює повідомлення для:

        - працівників ТТ;
        - адміністратора куща;
        - левів куща;
        - директора;
        - ROOT_ADMIN.
        """

        recipients = await self.get_alert_recipients(
            store
        )

        if not recipients:
            return [], 0

        notification_type = (
            self.resolve_notification_type(
                "opening_missed",
                "opening_deadline_missed",
                "opening_alert",
                "store_not_opened",
            )
        )

        message_text = (
            self.build_missed_notification_text(
                store=store,
                checkin=checkin,
                timezone_name=timezone_name,
            )
        )

        notifications: list[
            NotificationLog
        ] = []

        created_count = 0

        for recipient in recipients:
            if recipient.telegram_id is None:
                continue

            notification, was_created = (
                await self.repositories.notifications
                .get_or_create_from_parts(
                    notification_type=(
                        notification_type
                    ),
                    business_date=(
                        checkin.business_date
                    ),
                    recipient_user_id=(
                        recipient.id
                    ),
                    store_id=store.id,
                    bush_id=store.bush_id,
                    chat_id=(
                        recipient.telegram_id
                    ),
                    suffix=(
                        "opening-deadline-missed"
                    ),
                    scheduled_for=queued_at,
                    message_text=message_text,
                    payload_json={
                        "checkin_id": (
                            checkin.id
                        ),
                        "store_id": store.id,
                        "store_code": (
                            store.code
                        ),
                        "business_date": (
                            checkin
                            .business_date
                            .isoformat()
                        ),
                        "scheduled_open_time": (
                            checkin
                            .scheduled_open_time
                            .strftime("%H:%M")
                        ),
                        "control_deadline": (
                            checkin
                            .control_deadline
                            .strftime("%H:%M")
                        ),
                        "recipient_role": (
                            recipient.role.value
                        ),
                    },
                )
            )

            notifications.append(
                notification
            )

            if was_created:
                created_count += 1

        return notifications, created_count

    async def get_alert_recipients(
        self,
        store: Store,
    ) -> list[User]:
        """Повертає отримувачів ранкового сповіщення."""

        recipients: dict[int, User] = {}

        store_users = (
            await self.repositories.bindings
            .get_users_for_store(
                store.id,
                active_only=True,
            )
        )

        for user in store_users:
            recipients[user.id] = user

        if store.bush_id is not None:
            bush_users = (
                await self.repositories.bindings
                .get_users_for_bush(
                    store.bush_id,
                    active_only=True,
                )
            )

            for user in bush_users:
                recipients[user.id] = user

        global_statement = (
            select(User)
            .where(
                User.role.in_(
                    {
                        UserRole.ROOT_ADMIN,
                        UserRole.DIRECTOR,
                    }
                ),
                User.status == UserStatus.ACTIVE,
                User.is_blocked.is_(False),
            )
            .order_by(User.id.asc())
        )

        global_result = (
            await self.session.scalars(
                global_statement
            )
        )

        for user in global_result.unique().all():
            recipients[user.id] = user

        return list(recipients.values())

    # ==========================================
    # ЖИВІ ПІДСУМКИ
    # ==========================================

    async def prepare_summary_updates(
        self,
        *,
        business_date: date,
        changed_store: Store | None = None,
        bush_ids: set[int] | None = None,
        timezone_name: str | None = None,
    ) -> list[SummaryUpdateDecision]:
        """
        Готує оновлення живих підсумків.

        Повертає рішення:
        - надіслати нове повідомлення;
        - відредагувати існуюче;
        - нічого не робити.
        """

        summaries_enabled = (
            await self.repositories.settings
            .get_bool(
                self.repositories.settings
                .OPENING_SUMMARIES_ENABLED,
                default=True,
            )
        )

        live_updates_enabled = (
            await self.repositories.settings
            .get_bool(
                self.repositories.settings
                .LIVE_SUMMARY_UPDATES_ENABLED,
                default=True,
            )
        )

        if (
            not summaries_enabled
            or not live_updates_enabled
        ):
            return []

        control_group_id = (
            await self.repositories.settings
            .get_control_group_id()
        )

        if control_group_id is None:
            return []

        resolved_timezone = (
            timezone_name
            or await self.get_timezone_name()
        )

        target_bush_ids = set(
            bush_ids or set()
        )

        if (
            changed_store is not None
            and changed_store.bush_id is not None
        ):
            target_bush_ids.add(
                changed_store.bush_id
            )

        decisions: list[
            SummaryUpdateDecision
        ] = []

        bush_summary_type = (
            self.resolve_summary_type(
                "opening_bush",
                "bush_opening",
                "opening_bush_summary",
                "bush_opening_summary",
            )
        )

        for bush_id in sorted(
            target_bush_ids
        ):
            bush = await self.session.get(
                Bush,
                bush_id,
            )

            if bush is None:
                continue

            message_text, snapshot = (
                await self.build_bush_summary(
                    bush=bush,
                    business_date=business_date,
                    timezone_name=(
                        resolved_timezone
                    ),
                )
            )

            topic_id = self.get_bush_topic_id(
                bush
            )

            decision = (
                await self.repositories
                .daily_summaries
                .prepare_update(
                    summary_type=(
                        bush_summary_type
                    ),
                    business_date=(
                        business_date
                    ),
                    chat_id=control_group_id,
                    bush_id=bush.id,
                    topic_id=topic_id,
                    message_text=message_text,
                    snapshot_json=snapshot,
                )
            )

            decisions.append(decision)

        network_summary_type = (
            self.resolve_summary_type(
                "opening_network",
                "network_opening",
                "opening_network_summary",
                "network_opening_summary",
            )
        )

        network_text, network_snapshot = (
            await self.build_network_summary(
                business_date=business_date,
                timezone_name=resolved_timezone,
            )
        )

        network_topic_id = (
            await self.repositories.settings
            .get_int(
                self.repositories.settings
                .NETWORK_SUMMARY_TOPIC_ID,
                default=None,
            )
        )

        network_decision = (
            await self.repositories
            .daily_summaries
            .prepare_update(
                summary_type=network_summary_type,
                business_date=business_date,
                chat_id=control_group_id,
                bush_id=None,
                topic_id=network_topic_id,
                message_text=network_text,
                snapshot_json=(
                    network_snapshot
                ),
            )
        )

        decisions.append(network_decision)

        return decisions

    async def prepare_all_opening_summaries(
        self,
        *,
        business_date: date,
        timezone_name: str | None = None,
    ) -> list[SummaryUpdateDecision]:
        """Готує підсумки всіх активних кущів."""

        statement = (
            select(Bush.id)
            .where(
                Bush.is_active.is_(True)
            )
            .order_by(Bush.id.asc())
        )

        result = await self.session.scalars(
            statement
        )

        bush_ids = {
            int(bush_id)
            for bush_id in result.all()
        }

        return await self.prepare_summary_updates(
            business_date=business_date,
            bush_ids=bush_ids,
            timezone_name=timezone_name,
        )

    async def build_bush_summary(
        self,
        *,
        bush: Bush,
        business_date: date,
        timezone_name: str,
    ) -> tuple[str, dict[str, Any]]:
        """Формує текст ранкового підсумку куща."""

        statistics = (
            await self.repositories.openings
            .get_daily_statistics(
                business_date=business_date,
                bush_id=bush.id,
            )
        )

        problem_checkins = (
            await self.repositories.openings
            .get_problem_records(
                business_date=business_date,
                bush_id=bush.id,
            )
        )

        waiting_checkins = (
            await self.repositories.openings
            .get_waiting_for_date(
                business_date=business_date,
                bush_id=bush.id,
            )
        )

        problem_lines = (
            await self.build_checkin_lines(
                problem_checkins,
                timezone_name=timezone_name,
            )
        )

        waiting_lines = (
            await self.build_checkin_lines(
                waiting_checkins,
                timezone_name=timezone_name,
            )
        )

        title = getattr(
            bush,
            "name",
            f"Кущ №{bush.id}",
        )

        lines = [
            f"🌅 <b>Відкриття ТТ — {title}</b>",
            (
                f"📅 {business_date.strftime('%d.%m.%Y')}"
            ),
            "",
            (
                "🏪 Очікується: "
                f"<b>{statistics['expected_count']}</b>"
            ),
            (
                "✅ Відкрито: "
                f"<b>{statistics['opened_count']}</b>"
            ),
            (
                "⏰ Із запізненням: "
                f"<b>{statistics['late_count']}</b>"
            ),
            (
                "🚨 Пропустили дедлайн: "
                f"<b>{statistics['missed_count']}</b>"
            ),
            (
                "⌛ Очікуємо: "
                f"<b>{statistics['waiting_count']}</b>"
            ),
            (
                "📊 Виконання: "
                f"<b>{statistics['completion_percent']}%</b>"
            ),
        ]

        if problem_lines:
            lines.extend(
                [
                    "",
                    "⚠️ <b>Проблемні ТТ:</b>",
                    *problem_lines[:20],
                ]
            )

        if waiting_lines:
            lines.extend(
                [
                    "",
                    "⌛ <b>Ще не відкрилися:</b>",
                    *waiting_lines[:20],
                ]
            )

        snapshot = {
            **statistics,
            "bush_id": bush.id,
            "business_date": (
                business_date.isoformat()
            ),
            "problem_checkin_ids": [
                checkin.id
                for checkin
                in problem_checkins
            ],
            "waiting_checkin_ids": [
                checkin.id
                for checkin
                in waiting_checkins
            ],
        }

        return "\n".join(lines), snapshot

    async def build_network_summary(
        self,
        *,
        business_date: date,
        timezone_name: str,
    ) -> tuple[str, dict[str, Any]]:
        """Формує загальний ранковий підсумок мережі."""

        statistics = (
            await self.repositories.openings
            .get_daily_statistics(
                business_date=business_date
            )
        )

        problem_checkins = (
            await self.repositories.openings
            .get_problem_records(
                business_date=business_date
            )
        )

        problem_lines = (
            await self.build_checkin_lines(
                problem_checkins,
                timezone_name=timezone_name,
            )
        )

        lines = [
            "🌅 <b>Відкриття всієї мережі</b>",
            (
                f"📅 {business_date.strftime('%d.%m.%Y')}"
            ),
            "",
            (
                "🏪 Очікується: "
                f"<b>{statistics['expected_count']}</b>"
            ),
            (
                "✅ Відкрито: "
                f"<b>{statistics['opened_count']}</b>"
            ),
            (
                "🕘 Раніше графіка: "
                f"<b>{statistics['opened_early_count']}</b>"
            ),
            (
                "🟢 Вчасно: "
                f"<b>{statistics['opened_on_time_count']}</b>"
            ),
            (
                "⏰ Із запізненням: "
                f"<b>{statistics['late_count']}</b>"
            ),
            (
                "🚨 Пропустили дедлайн: "
                f"<b>{statistics['missed_count']}</b>"
            ),
            (
                "⌛ Очікуємо: "
                f"<b>{statistics['waiting_count']}</b>"
            ),
            (
                "📊 Виконання: "
                f"<b>{statistics['completion_percent']}%</b>"
            ),
            "",
            (
                "⏱ Загальне запізнення: "
                f"<b>{statistics['total_lateness_minutes']} хв</b>"
            ),
            (
                "📈 Середнє запізнення: "
                f"<b>{statistics['average_lateness_minutes']} хв</b>"
            ),
        ]

        if problem_lines:
            lines.extend(
                [
                    "",
                    "⚠️ <b>Проблемні ТТ:</b>",
                    *problem_lines[:30],
                ]
            )

        snapshot = {
            **statistics,
            "business_date": (
                business_date.isoformat()
            ),
            "problem_checkin_ids": [
                checkin.id
                for checkin
                in problem_checkins
            ],
        }

        return "\n".join(lines), snapshot

    # ==========================================
    # РЯДКИ ТОРГОВИХ ТОЧОК
    # ==========================================

    async def build_checkin_lines(
        self,
        checkins: list[OpeningCheckin],
        *,
        timezone_name: str,
    ) -> list[str]:
        """Формує короткі рядки ТТ для підсумку."""

        if not checkins:
            return []

        store_map = {
            store.id: store
            for store in await self.load_stores(
                {
                    checkin.store_id
                    for checkin in checkins
                }
            )
        }

        timezone = self.get_timezone(
            timezone_name
        )

        lines: list[str] = []

        sorted_checkins = sorted(
            checkins,
            key=lambda item: (
                -int(
                    getattr(
                        item,
                        "lateness_minutes",
                        0,
                    )
                    or 0
                ),
                item.store_id,
            ),
        )

        for checkin in sorted_checkins:
            store = store_map.get(
                checkin.store_id
            )

            store_name = (
                self.store_display_name(store)
                if store is not None
                else f"ТТ #{checkin.store_id}"
            )

            status_name = self.opening_status_text(
                checkin.status
            )

            details: list[str] = [
                status_name
            ]

            lateness_minutes = int(
                getattr(
                    checkin,
                    "lateness_minutes",
                    0,
                )
                or 0
            )

            if lateness_minutes > 0:
                details.append(
                    f"+{lateness_minutes} хв"
                )

            actual_open_time = getattr(
                checkin,
                "actual_open_time",
                None,
            )

            if actual_open_time is not None:
                local_open_time = (
                    actual_open_time
                    .astimezone(timezone)
                    .strftime("%H:%M")
                )

                details.append(local_open_time)

            lines.append(
                "• "
                f"<b>{store_name}</b> — "
                + ", ".join(details)
            )

        return lines

    # ==========================================
    # AUDIT LOG
    # ==========================================

    async def log_opening_confirmation(
        self,
        *,
        user: User,
        store: Store,
        checkin: OpeningCheckin,
        schedule: EffectiveSchedule,
        business_date: date,
        source: str,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> None:
        """Фіксує звичайне відкриття ТТ."""

        action = self.resolve_audit_action(
            "update",
            "confirm",
            "opening_confirmed",
        )

        entity_type = self.resolve_entity_type(
            "opening_checkin",
            "opening",
            "store_opening",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=checkin.id,
            context=AuditContext(
                actor_user_id=user.id,
                business_date=business_date,
                description=(
                    f"{self.store_display_name(store)} "
                    "підтвердила відкриття"
                ),
                telegram_chat_id=(
                    telegram_chat_id
                ),
                telegram_message_id=(
                    telegram_message_id
                ),
                source=source,
            ),
            new_values={
                "store_id": store.id,
                "status": (
                    checkin.status.value
                ),
                "scheduled_open_time": (
                    schedule.opening_time_text
                ),
                "actual_open_time": (
                    checkin.actual_open_time
                    .isoformat()
                    if checkin.actual_open_time
                    is not None
                    else None
                ),
                "lateness_minutes": (
                    checkin.lateness_minutes
                ),
            },
        )

    async def log_missed_deadline(
        self,
        *,
        store: Store,
        checkin: OpeningCheckin,
        business_date: date,
    ) -> None:
        """Фіксує пропущений дедлайн."""

        action = self.resolve_audit_action(
            "update",
            "deadline_missed",
            "opening_missed",
        )

        entity_type = self.resolve_entity_type(
            "opening_checkin",
            "opening",
            "store_opening",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=checkin.id,
            context=AuditContext(
                actor_user_id=None,
                business_date=business_date,
                description=(
                    f"{self.store_display_name(store)} "
                    "не відкрилася до дедлайну"
                ),
                source="scheduler",
            ),
            new_values={
                "store_id": store.id,
                "status": (
                    checkin.status.value
                ),
                "control_deadline": (
                    checkin.control_deadline
                    .strftime("%H:%M")
                ),
                "deadline_missed_at": (
                    getattr(
                        checkin,
                        "deadline_missed_at",
                        None,
                    ).isoformat()
                    if getattr(
                        checkin,
                        "deadline_missed_at",
                        None,
                    )
                    is not None
                    else None
                ),
            },
        )

    async def log_manual_confirmation(
        self,
        *,
        actor: User,
        store: Store,
        checkin: OpeningCheckin,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
        reason: str,
        business_date: date,
    ) -> None:
        """Фіксує ручне підтвердження."""

        action = self.resolve_audit_action(
            "update",
            "manual_confirm",
            "opening_manual_confirm",
        )

        entity_type = self.resolve_entity_type(
            "opening_checkin",
            "opening",
            "store_opening",
        )

        await self.repositories.audit.log_update(
            action=action,
            entity_type=entity_type,
            entity_id=checkin.id,
            old_values=previous_values,
            new_values=current_values,
            context=AuditContext(
                actor_user_id=actor.id,
                business_date=business_date,
                reason=reason,
                description=(
                    f"Ручне підтвердження відкриття "
                    f"{self.store_display_name(store)}"
                ),
                source="telegram_bot",
            ),
            skip_if_unchanged=False,
        )

    async def log_opening_modification(
        self,
        *,
        actor: User,
        store: Store,
        checkin: OpeningCheckin,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
        reason: str,
    ) -> None:
        """Фіксує зміну часу відкриття."""

        action = self.resolve_audit_action(
            "update",
            "edit",
            "opening_time_changed",
        )

        entity_type = self.resolve_entity_type(
            "opening_checkin",
            "opening",
            "store_opening",
        )

        await self.repositories.audit.log_update(
            action=action,
            entity_type=entity_type,
            entity_id=checkin.id,
            old_values=previous_values,
            new_values=current_values,
            context=AuditContext(
                actor_user_id=actor.id,
                business_date=(
                    checkin.business_date
                ),
                reason=reason,
                description=(
                    f"Змінено час відкриття "
                    f"{self.store_display_name(store)}"
                ),
                source="telegram_bot",
            ),
            skip_if_unchanged=False,
        )

    # ==========================================
    # ДОПОМІЖНІ ЗАПИТИ
    # ==========================================

    async def load_stores(
        self,
        store_ids: set[int],
    ) -> list[Store]:
        """Завантажує список ТТ одним SQL-запитом."""

        if not store_ids:
            return []

        statement = (
            select(Store)
            .where(
                Store.id.in_(store_ids)
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

    async def get_timezone_name(
        self,
    ) -> str:
        """Повертає часовий пояс системи."""

        return (
            await self.repositories.settings
            .get_default_timezone()
        )

    # ==========================================
    # ТЕКСТ СПОВІЩЕННЯ
    # ==========================================

    @classmethod
    def build_missed_notification_text(
        cls,
        *,
        store: Store,
        checkin: OpeningCheckin,
        timezone_name: str,
    ) -> str:
        """Формує повідомлення про невідкриту ТТ."""

        return "\n".join(
            [
                "🚨 <b>ТТ не відкрилася вчасно</b>",
                "",
                (
                    "🏪 "
                    f"<b>{cls.store_display_name(store)}</b>"
                ),
                (
                    "🕘 Час відкриття: "
                    f"<b>{checkin.scheduled_open_time.strftime('%H:%M')}</b>"
                ),
                (
                    "⏰ Дедлайн: "
                    f"<b>{checkin.control_deadline.strftime('%H:%M')}</b>"
                ),
                (
                    "📅 Дата: "
                    f"<b>{checkin.business_date.strftime('%d.%m.%Y')}</b>"
                ),
                "",
                (
                    "Потрібно перевірити, "
                    "чи працює магазин."
                ),
            ]
        )

    # ==========================================
    # ЗНІМОК ЧЕКІНА
    # ==========================================

    @staticmethod
    def opening_snapshot(
        checkin: OpeningCheckin,
    ) -> dict[str, Any]:
        """Створює знімок ранкового запису."""

        return {
            "status": (
                checkin.status.value
            ),
            "actual_open_time": (
                checkin.actual_open_time.isoformat()
                if checkin.actual_open_time
                is not None
                else None
            ),
            "lateness_minutes": int(
                checkin.lateness_minutes or 0
            ),
            "submitted_by_id": (
                checkin.submitted_by_id
            ),
            "manually_modified_by_id": (
                getattr(
                    checkin,
                    "manually_modified_by_id",
                    None,
                )
            ),
            "manual_reason": getattr(
                checkin,
                "manual_reason",
                None,
            ),
        }

    # ==========================================
    # ENUM-РЕЗОЛВЕРИ
    # ==========================================

    @classmethod
    def resolve_notification_type(
        cls,
        *names: str,
    ) -> NotificationType:
        """Знаходить тип ранкового повідомлення."""

        return cls.resolve_enum_member(
            NotificationType,
            *names,
        )

    @classmethod
    def resolve_summary_type(
        cls,
        *names: str,
    ) -> SummaryType:
        """Знаходить тип ранкового підсумку."""

        return cls.resolve_enum_member(
            SummaryType,
            *names,
        )

    @classmethod
    def resolve_audit_action(
        cls,
        *names: str,
    ) -> AuditAction:
        """Знаходить тип AuditLog-дії."""

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
        """Знаходить тип об’єкта AuditLog."""

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
            candidates = {
                enum_item.name.lower(),
                str(enum_item.value).lower(),
            }

            if candidates.intersection(
                normalized_names
            ):
                return enum_item

        raise ValueError(
            f"У {enum_class.__name__} відсутнє "
            f"значення: {sorted(normalized_names)}."
        )

    # ==========================================
    # СТАТУСИ ТА НАЗВИ
    # ==========================================

    @staticmethod
    def opening_status_text(
        status: OpeningStatus,
    ) -> str:
        """Повертає зрозумілий текст статусу."""

        texts = {
            OpeningStatus.WAITING: (
                "очікується"
            ),
            OpeningStatus.OPENED_EARLY: (
                "відкрито раніше"
            ),
            OpeningStatus.OPENED_ON_TIME: (
                "відкрито вчасно"
            ),
            OpeningStatus.OPENED_LATE: (
                "відкрито із запізненням"
            ),
            OpeningStatus.OPENED_AFTER_ALERT: (
                "відкрито після сповіщення"
            ),
            OpeningStatus.MISSED_CONTROL_DEADLINE: (
                "дедлайн пропущено"
            ),
            OpeningStatus.MANUALLY_CONFIRMED: (
                "підтверджено вручну"
            ),
            OpeningStatus.NOT_REQUIRED: (
                "контроль не потрібен"
            ),
            OpeningStatus.DAY_OFF: (
                "вихідний"
            ),
            OpeningStatus.TEMPORARILY_CLOSED: (
                "тимчасово закрито"
            ),
        }

        return texts.get(
            status,
            str(status.value),
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
    def get_bush_topic_id(
        bush: Bush,
    ) -> int | None:
        """Повертає Telegram topic_id куща."""

        for field_name in (
            "telegram_topic_id",
            "topic_id",
            "control_topic_id",
        ):
            value = getattr(
                bush,
                field_name,
                None,
            )

            if (
                isinstance(value, int)
                and value > 0
            ):
                return value

        return None

    # ==========================================
    # ПЕРЕВІРКА ГРАФІКА
    # ==========================================

    @staticmethod
    def ensure_opening_required(
        schedule: EffectiveSchedule,
    ) -> None:
        """Перевіряє необхідність ранкового чекіну."""

        if not schedule.is_working_day:
            raise ValueError(
                schedule.reason
                or (
                    "Сьогодні для цієї ТТ "
                    "встановлено вихідний."
                )
            )

        if not schedule.requires_opening:
            raise ValueError(
                "Для цієї торгової точки не "
                "налаштовано контроль відкриття."
            )

        if schedule.opening_time is None:
            raise ValueError(
                "Не вказано час відкриття ТТ."
            )

        if (
            schedule.opening_control_deadline
            is None
        ):
            raise ValueError(
                "Не вказано дедлайн відкриття ТТ."
            )

    # ==========================================
    # ЧАСОВИЙ ПОЯС
    # ==========================================

    @staticmethod
    def get_timezone(
        timezone_name: str,
    ) -> ZoneInfo:
        """Повертає перевірений часовий пояс."""

        normalized_name = (
            timezone_name.strip()
        )

        if not normalized_name:
            raise ValueError(
                "Назва часового поясу "
                "не може бути порожньою."
            )

        try:
            return ZoneInfo(
                normalized_name
            )

        except ZoneInfoNotFoundError as error:
            raise ValueError(
                "Невідомий часовий пояс: "
                f"{normalized_name}."
            ) from error

    # ==========================================
    # ВАЛІДАЦІЯ
    # ==========================================

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

        if len(normalized_value) > 2000:
            raise ValueError(
                f"{field_name} занадто довгий."
            )

        return normalized_value