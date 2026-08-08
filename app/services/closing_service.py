from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from html import escape
from typing import Any, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.database.models.bush import Bush
from app.database.models.closing_report import ClosingReport
from app.database.models.enums import (
    AuditAction,
    ClosingStatus,
    EntityType,
    NotificationType,
    SummaryType,
    UserRole,
    UserStatus,
)
from app.database.models.notification import NotificationLog
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories import (
    AuditContext,
    ClosingPlan,
    EffectiveSchedule,
    Repositories,
    SummaryUpdateDecision,
)
from app.services.access import AccessService


EnumType = TypeVar(
    "EnumType",
    bound=Enum,
)


@dataclass(slots=True, frozen=True)
class ClosingPreparationResult:
    """
    Результат підготовки вечірніх звітів.
    """

    business_date: date

    expected_stores: int
    created_records: int
    existing_records: int

    reports: tuple[ClosingReport, ...]


@dataclass(slots=True, frozen=True)
class ReceiptAttachmentResult:
    """
    Результат завантаження фото чека.
    """

    store: Store
    schedule: EffectiveSchedule
    report: ClosingReport

    was_replaced: bool


@dataclass(slots=True, frozen=True)
class ClosingSubmissionResult:
    """
    Результат подання вечірнього звіту.
    """

    store: Store
    schedule: EffectiveSchedule
    report: ClosingReport

    was_confirmed_now: bool

    cash_amount: Decimal
    is_late: bool

    group_notification: NotificationLog | None
    group_notification_created: bool

    summary_updates: tuple[
        SummaryUpdateDecision,
        ...,
    ]


@dataclass(slots=True, frozen=True)
class ClosingDeadlineResult:
    """
    Результат перевірки вечірніх дедлайнів.
    """

    business_date: date

    missed_reports: tuple[
        ClosingReport,
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
        return len(self.missed_reports)


@dataclass(slots=True, frozen=True)
class ClosingManualUpdateResult:
    """
    Результат ручного редагування звіту.
    """

    store: Store
    report: ClosingReport

    previous_values: dict[str, Any]
    current_values: dict[str, Any]

    summary_updates: tuple[
        SummaryUpdateDecision,
        ...,
    ]


class ClosingService:
    """
    Сервіс вечірнього закриття торгових точок.

    Об’єднує:

    - перевірку прав доступу;
    - фактичний графік ТТ;
    - створення вечірнього запису;
    - завантаження фото чека;
    - введення суми каси;
    - захист від повторного закриття;
    - контроль дедлайнів;
    - сповіщення відповідальних осіб;
    - надсилання звіту в Telegram-групу;
    - AuditLog;
    - живі підсумки кущів і всієї мережі.

    Telegram API безпосередньо тут не викликається.

    Повідомлення створюються у черзі
    NotificationLog, а окремий worker їх надсилає.
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
    # ПІДГОТОВКА ВЕЧІРНІХ ЗАПИСІВ
    # ==========================================

    async def prepare_daily_records(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> ClosingPreparationResult:
        """
        Створює вечірні записи для всіх ТТ,
        які повинні подати звіт цього дня.

        Існуючі записи не змінюються.
        """

        scheduled_stores = (
            await self.repositories.schedules
            .get_stores_requiring_closing(
                business_date=business_date,
                bush_id=bush_id,
                cluster_id=cluster_id,
            )
        )

        plans = [
            ClosingPlan(
                store_id=store.id,
                business_date=business_date,
                scheduled_close_time=(
                    schedule.closing_time
                ),
                control_deadline=(
                    schedule
                    .closing_control_deadline
                ),
            )
            for store, schedule in scheduled_stores
            if (
                schedule.closing_time is not None
                and schedule
                .closing_control_deadline
                is not None
            )
        ]

        created_reports = (
            await self.repositories.closings
            .create_missing_records(plans)
        )

        all_reports = (
            await self.repositories.closings
            .get_for_date(
                business_date=business_date,
                bush_id=bush_id,
                cluster_id=cluster_id,
            )
        )

        return ClosingPreparationResult(
            business_date=business_date,
            expected_stores=len(plans),
            created_records=len(created_reports),
            existing_records=(
                len(plans)
                - len(created_reports)
            ),
            reports=tuple(all_reports),
        )

    async def prepare_store_report(
        self,
        *,
        store: Store,
        business_date: date,
    ) -> tuple[
        ClosingReport,
        EffectiveSchedule,
        bool,
    ]:
        """
        Створює вечірній запис конкретної ТТ.
        """

        schedule = (
            await self.repositories.schedules
            .get_effective_schedule(
                store=store,
                business_date=business_date,
            )
        )

        self.ensure_closing_required(schedule)

        report, was_created = (
            await self.repositories.closings
            .get_or_create_waiting(
                store_id=store.id,
                business_date=business_date,
                scheduled_close_time=(
                    schedule.closing_time
                ),
                control_deadline=(
                    schedule
                    .closing_control_deadline
                ),
            )
        )

        return report, schedule, was_created

    # ==========================================
    # ФОТО ЧЕКА
    # ==========================================

    async def attach_receipt(
        self,
        *,
        user: User,
        store_id: int,
        current_time: datetime,
        file_id: str,
        file_unique_id: str | None = None,
        mime_type: str | None = None,
        file_name: str | None = None,
        file_size: int | None = None,
        timezone_name: str | None = None,
    ) -> ReceiptAttachmentResult:
        """
        Зберігає фото чека перед введенням каси.

        Зазвичай це перший крок FSM:

        1. Працівник надсилає фото.
        2. Бот просить суму каси.
        3. Після суми звіт підтверджується.
        """

        self.validate_aware_datetime(
            current_time,
            field_name="current_time",
        )

        normalized_file_id = (
            self.normalize_required_text(
                file_id,
                field_name="Telegram file_id",
            )
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

        business_date = (
            current_time
            .astimezone(
                self.get_timezone(
                    resolved_timezone
                )
            )
            .date()
        )

        report, schedule, _ = (
            await self.prepare_store_report(
                store=store,
                business_date=business_date,
            )
        )

        previous_file_id = getattr(
            report,
            "receipt_file_id",
            None,
        )

        report = (
            await self.repositories.closings
            .attach_receipt(
                store_id=store.id,
                business_date=business_date,
                file_id=normalized_file_id,
                file_unique_id=file_unique_id,
                mime_type=mime_type,
                file_name=file_name,
                file_size=file_size,
            )
        )

        return ReceiptAttachmentResult(
            store=store,
            schedule=schedule,
            report=report,
            was_replaced=(
                previous_file_id is not None
                and previous_file_id
                != normalized_file_id
            ),
        )

    async def cancel_pending_receipt(
        self,
        *,
        user: User,
        store_id: int,
        current_time: datetime,
        timezone_name: str | None = None,
    ) -> ClosingReport:
        """
        Прибирає фото з незавершеного звіту.

        Використовується після натискання
        кнопки «Скасувати».
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

        business_date = (
            current_time
            .astimezone(
                self.get_timezone(
                    resolved_timezone
                )
            )
            .date()
        )

        return (
            await self.repositories.closings
            .remove_pending_receipt(
                store_id=store.id,
                business_date=business_date,
            )
        )

    # ==========================================
    # ПОДАННЯ ВЕЧІРНЬОГО ЗВІТУ
    # ==========================================

    async def submit_report(
        self,
        *,
        user: User,
        store_id: int,
        current_time: datetime,
        cash_amount: Decimal | int | float | str,
        timezone_name: str | None = None,
        receipt_file_id: str | None = None,
        receipt_file_unique_id: str | None = None,
        receipt_mime_type: str | None = None,
        receipt_file_name: str | None = None,
        receipt_file_size: int | None = None,
        source: str = "telegram_bot",
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
        queue_group_message: bool = True,
        update_summaries: bool = True,
    ) -> ClosingSubmissionResult:
        """
        Підтверджує вечірній звіт працівника.

        Час подання береться із сервера.
        """

        self.validate_aware_datetime(
            current_time,
            field_name="current_time",
        )

        normalized_cash = (
            self.normalize_cash_amount(
                cash_amount
            )
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

        timezone = self.get_timezone(
            resolved_timezone
        )

        business_date = (
            current_time
            .astimezone(timezone)
            .date()
        )

        _, schedule, _ = (
            await self.prepare_store_report(
                store=store,
                business_date=business_date,
            )
        )

        require_receipt = (
            await self.repositories.settings
            .get_bool(
                self.repositories.settings
                .CLOSING_REQUIRE_RECEIPT,
                default=True,
            )
        )

        report, was_confirmed_now = (
            await self.repositories.closings
            .confirm_report(
                store_id=store.id,
                business_date=business_date,
                submitted_at=current_time,
                submitted_by_id=user.id,
                cash_amount=normalized_cash,
                scheduled_close_time=(
                    schedule.closing_time
                ),
                control_deadline=(
                    schedule
                    .closing_control_deadline
                ),
                timezone_name=resolved_timezone,
                require_receipt=require_receipt,
                source=source,
                telegram_chat_id=(
                    telegram_chat_id
                ),
                telegram_message_id=(
                    telegram_message_id
                ),
                receipt_file_id=receipt_file_id,
                receipt_file_unique_id=(
                    receipt_file_unique_id
                ),
                receipt_mime_type=(
                    receipt_mime_type
                ),
                receipt_file_name=(
                    receipt_file_name
                ),
                receipt_file_size=(
                    receipt_file_size
                ),
            )
        )

        if was_confirmed_now:
            await self.log_report_submission(
                user=user,
                store=store,
                report=report,
                schedule=schedule,
                source=source,
                telegram_chat_id=(
                    telegram_chat_id
                ),
                telegram_message_id=(
                    telegram_message_id
                ),
            )

        group_notification: (
            NotificationLog | None
        ) = None

        group_notification_created = False

        if (
            was_confirmed_now
            and queue_group_message
        ):
            (
                group_notification,
                group_notification_created,
            ) = await self.queue_report_to_group(
                store=store,
                report=report,
                queued_at=current_time,
                timezone_name=resolved_timezone,
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

        return ClosingSubmissionResult(
            store=store,
            schedule=schedule,
            report=report,
            was_confirmed_now=(
                was_confirmed_now
            ),
            cash_amount=Decimal(
                str(report.cash_amount)
            ).quantize(
                Decimal("0.01")
            ),
            is_late=self.is_late_report(
                report
            ),
            group_notification=(
                group_notification
            ),
            group_notification_created=(
                group_notification_created
            ),
            summary_updates=tuple(
                summary_updates
            ),
        )

    # ==========================================
    # НАДСИЛАННЯ ЗВІТУ В ГРУПУ
    # ==========================================

    async def queue_report_to_group(
        self,
        *,
        store: Store,
        report: ClosingReport,
        queued_at: datetime,
        timezone_name: str,
    ) -> tuple[
        NotificationLog | None,
        bool,
    ]:
        """
        Ставить підтверджений звіт у чергу
        для Telegram-групи закриттів.
        """

        group_id = (
            await self.repositories.settings
            .get_closing_group_id()
        )

        if group_id is None:
            return None, False

        notification_type = (
            self.resolve_notification_type(
                "closing_report",
                "closing_submitted",
                "closing_report_submitted",
                "store_closed",
            )
        )

        message_text = (
            self.build_group_report_text(
                store=store,
                report=report,
                timezone_name=timezone_name,
            )
        )

        topic_id = self.get_bush_closing_topic_id(
            await self.get_store_bush(store)
        )

        receipt_file_id = getattr(
            report,
            "receipt_file_id",
            None,
        )

        notification, was_created = (
            await self.repositories.notifications
            .get_or_create_from_parts(
                notification_type=(
                    notification_type
                ),
                business_date=(
                    report.business_date
                ),
                store_id=store.id,
                bush_id=store.bush_id,
                chat_id=group_id,
                topic_id=topic_id,
                suffix="closing-report-group",
                scheduled_for=queued_at,
                message_text=message_text,
                payload_json={
                    "send_method": (
                        "photo"
                        if receipt_file_id
                        else "message"
                    ),
                    "report_id": report.id,
                    "store_id": store.id,
                    "store_code": (
                        self.store_display_name(
                            store
                        )
                    ),
                    "business_date": (
                        report.business_date
                        .isoformat()
                    ),
                    "cash_amount": str(
                        report.cash_amount
                    ),
                    "receipt_file_id": (
                        receipt_file_id
                    ),
                    "caption": message_text,
                    "parse_mode": "HTML",
                },
            )
        )

        return notification, was_created

    async def mark_group_delivery(
        self,
        *,
        report_id: int,
        chat_id: int,
        message_id: int,
        sent_at: datetime,
        topic_id: int | None = None,
    ) -> ClosingReport:
        """
        Фіксує успішне надсилання звіту
        в Telegram-групу.
        """

        self.validate_aware_datetime(
            sent_at,
            field_name="sent_at",
        )

        report = (
            await self.repositories.closings
            .get_report_for_update_or_raise(
                report_id
            )
        )

        return (
            await self.repositories.closings
            .mark_sent_to_group(
                report,
                chat_id=chat_id,
                message_id=message_id,
                sent_at=sent_at,
                topic_id=topic_id,
            )
        )

    # ==========================================
    # РУЧНЕ ПІДТВЕРДЖЕННЯ
    # ==========================================

    async def manually_confirm_report(
        self,
        *,
        actor: User,
        store_id: int,
        business_date: date,
        submitted_at: datetime,
        cash_amount: Decimal | int | float | str,
        modified_at: datetime,
        reason: str,
        timezone_name: str | None = None,
        queue_group_message: bool = True,
        update_summaries: bool = True,
    ) -> ClosingManualUpdateResult:
        """
        Ручне підтвердження звіту адміністратором.
        """

        self.validate_aware_datetime(
            submitted_at,
            field_name="submitted_at",
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

        normalized_cash = (
            self.normalize_cash_amount(
                cash_amount
            )
        )

        decision = (
            await self.access
            .can_manually_confirm_closing(
                actor,
                store_id,
            )
        )

        decision.raise_if_denied()

        store = await self.access.get_store_or_raise(
            store_id
        )

        report, _, _ = (
            await self.prepare_store_report(
                store=store,
                business_date=business_date,
            )
        )

        previous_values = (
            self.closing_snapshot(report)
        )

        report = (
            await self.repositories.closings
            .manually_confirm(
                store_id=store.id,
                business_date=business_date,
                submitted_at=submitted_at,
                cash_amount=normalized_cash,
                modified_by_id=actor.id,
                modified_at=modified_at,
                reason=normalized_reason,
            )
        )

        current_values = (
            self.closing_snapshot(report)
        )

        await self.log_manual_confirmation(
            actor=actor,
            store=store,
            report=report,
            previous_values=previous_values,
            current_values=current_values,
            reason=normalized_reason,
        )

        resolved_timezone = (
            timezone_name
            or await self.get_timezone_name()
        )

        if queue_group_message:
            await self.queue_report_to_group(
                store=store,
                report=report,
                queued_at=modified_at,
                timezone_name=resolved_timezone,
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

        return ClosingManualUpdateResult(
            store=store,
            report=report,
            previous_values=previous_values,
            current_values=current_values,
            summary_updates=tuple(
                summary_updates
            ),
        )

    # ==========================================
    # КОРИГУВАННЯ КАСИ
    # ==========================================

    async def modify_cash_amount(
        self,
        *,
        actor: User,
        report_id: int,
        new_cash_amount: Decimal | int | float | str,
        modified_at: datetime,
        reason: str,
        timezone_name: str | None = None,
        update_summaries: bool = True,
    ) -> ClosingManualUpdateResult:
        """Змінює помилково введену суму каси."""

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

        normalized_cash = (
            self.normalize_cash_amount(
                new_cash_amount
            )
        )

        report = (
            await self.repositories.closings
            .get_report_for_update_or_raise(
                report_id
            )
        )

        decision = (
            await self.access
            .can_manually_confirm_closing(
                actor,
                report.store_id,
            )
        )

        decision.raise_if_denied()

        store = await self.access.get_store_or_raise(
            report.store_id
        )

        previous_values = (
            self.closing_snapshot(report)
        )

        report = (
            await self.repositories.closings
            .modify_cash_amount(
                report_id=report.id,
                new_cash_amount=normalized_cash,
                modified_by_id=actor.id,
                modified_at=modified_at,
                reason=normalized_reason,
            )
        )

        current_values = (
            self.closing_snapshot(report)
        )

        await self.log_report_modification(
            actor=actor,
            store=store,
            report=report,
            previous_values=previous_values,
            current_values=current_values,
            reason=normalized_reason,
            description=(
                "Змінено суму каси"
            ),
        )

        resolved_timezone = (
            timezone_name
            or await self.get_timezone_name()
        )

        summary_updates: list[
            SummaryUpdateDecision
        ] = []

        if update_summaries:
            summary_updates = (
                await self.prepare_summary_updates(
                    business_date=(
                        report.business_date
                    ),
                    changed_store=store,
                    timezone_name=resolved_timezone,
                )
            )

        return ClosingManualUpdateResult(
            store=store,
            report=report,
            previous_values=previous_values,
            current_values=current_values,
            summary_updates=tuple(
                summary_updates
            ),
        )

    # ==========================================
    # ЗАМІНА ФОТО ЧЕКА
    # ==========================================

    async def replace_receipt(
        self,
        *,
        actor: User,
        report_id: int,
        new_file_id: str,
        modified_at: datetime,
        reason: str,
        new_file_unique_id: str | None = None,
        mime_type: str | None = None,
        file_name: str | None = None,
        file_size: int | None = None,
    ) -> ClosingManualUpdateResult:
        """Замінює фото чека у поданому звіті."""

        self.validate_aware_datetime(
            modified_at,
            field_name="modified_at",
        )

        normalized_file_id = (
            self.normalize_required_text(
                new_file_id,
                field_name="Telegram file_id",
            )
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
            )
        )

        report = (
            await self.repositories.closings
            .get_report_for_update_or_raise(
                report_id
            )
        )

        decision = (
            await self.access
            .can_manually_confirm_closing(
                actor,
                report.store_id,
            )
        )

        decision.raise_if_denied()

        store = await self.access.get_store_or_raise(
            report.store_id
        )

        previous_values = (
            self.closing_snapshot(report)
        )

        report = (
            await self.repositories.closings
            .replace_receipt(
                report_id=report.id,
                new_file_id=normalized_file_id,
                new_file_unique_id=(
                    new_file_unique_id
                ),
                mime_type=mime_type,
                file_name=file_name,
                file_size=file_size,
                modified_by_id=actor.id,
                modified_at=modified_at,
                reason=normalized_reason,
            )
        )

        current_values = (
            self.closing_snapshot(report)
        )

        await self.log_report_modification(
            actor=actor,
            store=store,
            report=report,
            previous_values=previous_values,
            current_values=current_values,
            reason=normalized_reason,
            description=(
                "Замінено фото чека"
            ),
        )

        return ClosingManualUpdateResult(
            store=store,
            report=report,
            previous_values=previous_values,
            current_values=current_values,
            summary_updates=(),
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
    ) -> ClosingDeadlineResult:
        """
        Фіксує ТТ, які не подали вечірній звіт.

        Метод призначений для APScheduler.
        """

        self.validate_aware_datetime(
            current_time,
            field_name="current_time",
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

        control_enabled = (
            await self.repositories.settings
            .get_bool(
                self.repositories.settings
                .CLOSING_CONTROL_ENABLED,
                default=True,
            )
        )

        if not control_enabled:
            return ClosingDeadlineResult(
                business_date=business_date,
                missed_reports=(),
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

        missed_reports = (
            await self.repositories.closings
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
                .CLOSING_NOTIFICATIONS_ENABLED,
                default=True,
            )
        )

        if (
            create_notifications
            and notifications_enabled
        ):
            for report in missed_reports:
                store = (
                    await self.access
                    .get_store_or_raise(
                        report.store_id
                    )
                )

                queued, created_count = (
                    await self
                    .queue_missed_notifications(
                        store=store,
                        report=report,
                        queued_at=current_time,
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

        for report in missed_reports:
            store = (
                await self.access
                .get_store_or_raise(
                    report.store_id
                )
            )

            await self.log_missed_deadline(
                store=store,
                report=report,
            )

        summary_updates: list[
            SummaryUpdateDecision
        ] = []

        if (
            missed_reports
            and update_summaries
        ):
            stores = await self.load_stores(
                {
                    report.store_id
                    for report in missed_reports
                }
            )

            bush_ids = {
                store.bush_id
                for store in stores
                if store.bush_id is not None
            }

            summary_updates = (
                await self.prepare_summary_updates(
                    business_date=business_date,
                    bush_ids=bush_ids,
                    timezone_name=resolved_timezone,
                )
            )

        return ClosingDeadlineResult(
            business_date=business_date,
            missed_reports=tuple(
                missed_reports
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
    # СПОВІЩЕННЯ ПРО НЕПОДАНИЙ ЗВІТ
    # ==========================================

    async def queue_missed_notifications(
        self,
        *,
        store: Store,
        report: ClosingReport,
        queued_at: datetime,
    ) -> tuple[list[NotificationLog], int]:
        """
        Створює повідомлення для:

        - працівників ТТ;
        - адміністратора куща;
        - левів;
        - директорів;
        - ROOT_ADMIN.
        """

        recipients = await self.get_alert_recipients(
            store
        )

        if not recipients:
            return [], 0

        notification_type = (
            self.resolve_notification_type(
                "closing_missed",
                "closing_deadline_missed",
                "closing_alert",
                "report_not_submitted",
            )
        )

        message_text = (
            self.build_missed_notification_text(
                store=store,
                report=report,
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
                        report.business_date
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
                        "closing-deadline-missed"
                    ),
                    scheduled_for=queued_at,
                    message_text=message_text,
                    payload_json={
                        "report_id": report.id,
                        "store_id": store.id,
                        "store_code": (
                            self.store_display_name(
                                store
                            )
                        ),
                        "business_date": (
                            report.business_date
                            .isoformat()
                        ),
                        "scheduled_close_time": (
                            report
                            .scheduled_close_time
                            .strftime("%H:%M")
                        ),
                        "control_deadline": (
                            report
                            .control_deadline
                            .strftime("%H:%M")
                        ),
                        "recipient_role": (
                            recipient.role.value
                        ),
                        "parse_mode": "HTML",
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
        """Повертає отримувачів вечірнього сповіщення."""

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

        statement = (
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

        result = await self.session.scalars(
            statement
        )

        for user in result.unique().all():
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
        Готує оновлення вечірніх підсумків.

        Повертає рішення для Telegram worker:

        - надіслати нове повідомлення;
        - відредагувати існуюче;
        - нічого не робити.
        """

        summaries_enabled = (
            await self.repositories.settings
            .get_bool(
                self.repositories.settings
                .CLOSING_SUMMARIES_ENABLED,
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

        closing_group_id = (
            await self.repositories.settings
            .get_closing_group_id()
        )

        if closing_group_id is None:
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
                "closing_bush",
                "bush_closing",
                "closing_bush_summary",
                "bush_closing_summary",
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
                    chat_id=closing_group_id,
                    bush_id=bush.id,
                    topic_id=(
                        self
                        .get_bush_closing_topic_id(
                            bush
                        )
                    ),
                    message_text=message_text,
                    snapshot_json=snapshot,
                )
            )

            decisions.append(decision)

        network_summary_type = (
            self.resolve_summary_type(
                "closing_network",
                "network_closing",
                "closing_network_summary",
                "network_closing_summary",
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
                summary_type=(
                    network_summary_type
                ),
                business_date=business_date,
                chat_id=closing_group_id,
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

    async def prepare_all_closing_summaries(
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
        """Формує вечірній підсумок куща."""

        statistics = (
            await self.repositories.closings
            .get_daily_statistics(
                business_date=business_date,
                bush_id=bush.id,
            )
        )

        problem_reports = (
            await self.repositories.closings
            .get_problem_reports(
                business_date=business_date,
                bush_id=bush.id,
            )
        )

        waiting_reports = (
            await self.repositories.closings
            .get_waiting_for_date(
                business_date=business_date,
                bush_id=bush.id,
            )
        )

        problem_lines = (
            await self.build_report_lines(
                problem_reports,
                timezone_name=timezone_name,
            )
        )

        waiting_lines = (
            await self.build_report_lines(
                waiting_reports,
                timezone_name=timezone_name,
            )
        )

        bush_name = escape(
            str(
                getattr(
                    bush,
                    "name",
                    f"Кущ №{bush.id}",
                )
            )
        )

        lines = [
            (
                "🌙 <b>Закриття ТТ — "
                f"{bush_name}</b>"
            ),
            (
                f"📅 {business_date.strftime('%d.%m.%Y')}"
            ),
            "",
            (
                "🏪 Очікується звітів: "
                f"<b>{statistics['expected_count']}</b>"
            ),
            (
                "✅ Подано: "
                f"<b>{statistics['submitted_count']}</b>"
            ),
            (
                "🟢 Вчасно: "
                f"<b>{statistics['submitted_on_time_count']}</b>"
            ),
            (
                "⏰ Із запізненням: "
                f"<b>{statistics['submitted_late_count']}</b>"
            ),
            (
                "🚨 Не подано: "
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
                "💰 Загальна каса: "
                f"<b>{self.format_money(statistics['total_cash'])}</b>"
            ),
            (
                "📈 Середня каса: "
                f"<b>{self.format_money(statistics['average_cash'])}</b>"
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
                    "⌛ <b>Ще не подали звіт:</b>",
                    *waiting_lines[:20],
                ]
            )

        snapshot = {
            **statistics,
            "total_cash": str(
                statistics["total_cash"]
            ),
            "average_cash": str(
                statistics["average_cash"]
            ),
            "maximum_cash": str(
                statistics["maximum_cash"]
            ),
            "minimum_cash": str(
                statistics["minimum_cash"]
            ),
            "bush_id": bush.id,
            "business_date": (
                business_date.isoformat()
            ),
            "problem_report_ids": [
                report.id
                for report in problem_reports
            ],
            "waiting_report_ids": [
                report.id
                for report in waiting_reports
            ],
        }

        return "\n".join(lines), snapshot

    async def build_network_summary(
        self,
        *,
        business_date: date,
        timezone_name: str,
    ) -> tuple[str, dict[str, Any]]:
        """Формує вечірній підсумок усієї мережі."""

        statistics = (
            await self.repositories.closings
            .get_daily_statistics(
                business_date=business_date
            )
        )

        problem_reports = (
            await self.repositories.closings
            .get_problem_reports(
                business_date=business_date
            )
        )

        problem_lines = (
            await self.build_report_lines(
                problem_reports,
                timezone_name=timezone_name,
            )
        )

        lines = [
            "🌙 <b>Закриття всієї мережі</b>",
            (
                f"📅 {business_date.strftime('%d.%m.%Y')}"
            ),
            "",
            (
                "🏪 Очікується звітів: "
                f"<b>{statistics['expected_count']}</b>"
            ),
            (
                "✅ Подано: "
                f"<b>{statistics['submitted_count']}</b>"
            ),
            (
                "🟢 Вчасно: "
                f"<b>{statistics['submitted_on_time_count']}</b>"
            ),
            (
                "⏰ Із запізненням: "
                f"<b>{statistics['submitted_late_count']}</b>"
            ),
            (
                "🛠 Підтверджено вручну: "
                f"<b>{statistics['manually_confirmed_count']}</b>"
            ),
            (
                "🚨 Не подано: "
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
                "💰 Загальна каса мережі: "
                f"<b>{self.format_money(statistics['total_cash'])}</b>"
            ),
            (
                "📈 Середня каса: "
                f"<b>{self.format_money(statistics['average_cash'])}</b>"
            ),
            (
                "🔝 Найбільша каса: "
                f"<b>{self.format_money(statistics['maximum_cash'])}</b>"
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
            "total_cash": str(
                statistics["total_cash"]
            ),
            "average_cash": str(
                statistics["average_cash"]
            ),
            "maximum_cash": str(
                statistics["maximum_cash"]
            ),
            "minimum_cash": str(
                statistics["minimum_cash"]
            ),
            "business_date": (
                business_date.isoformat()
            ),
            "problem_report_ids": [
                report.id
                for report in problem_reports
            ],
        }

        return "\n".join(lines), snapshot

    # ==========================================
    # РЯДКИ ТОРГОВИХ ТОЧОК
    # ==========================================

    async def build_report_lines(
        self,
        reports: list[ClosingReport],
        *,
        timezone_name: str,
    ) -> list[str]:
        """Формує короткі рядки звітів."""

        if not reports:
            return []

        stores = await self.load_stores(
            {
                report.store_id
                for report in reports
            }
        )

        store_map = {
            store.id: store
            for store in stores
        }

        timezone = self.get_timezone(
            timezone_name
        )

        lines: list[str] = []

        sorted_reports = sorted(
            reports,
            key=lambda report: (
                0
                if self.is_missed_report(report)
                else 1,
                report.store_id,
            ),
        )

        for report in sorted_reports:
            store = store_map.get(
                report.store_id
            )

            store_name = escape(
                self.store_display_name(
                    store
                )
            )

            details = [
                self.closing_status_text(
                    report.status
                )
            ]

            submitted_at = getattr(
                report,
                "actual_submitted_at",
                None,
            )

            if submitted_at is not None:
                details.append(
                    submitted_at
                    .astimezone(timezone)
                    .strftime("%H:%M")
                )

            cash_amount = getattr(
                report,
                "cash_amount",
                None,
            )

            if cash_amount is not None:
                details.append(
                    self.format_money(
                        cash_amount
                    )
                )

            lines.append(
                "• "
                f"<b>{store_name}</b> — "
                + ", ".join(details)
            )

        return lines

    # ==========================================
    # AUDIT LOG
    # ==========================================

    async def log_report_submission(
        self,
        *,
        user: User,
        store: Store,
        report: ClosingReport,
        schedule: EffectiveSchedule,
        source: str,
        telegram_chat_id: int | None,
        telegram_message_id: int | None,
    ) -> None:
        """Фіксує звичайне подання звіту."""

        action = self.resolve_audit_action(
            "update",
            "confirm",
            "closing_submitted",
        )

        entity_type = self.resolve_entity_type(
            "closing_report",
            "closing",
            "store_closing",
            "store",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=report.id,
            context=AuditContext(
                actor_user_id=user.id,
                business_date=(
                    report.business_date
                ),
                description=(
                    f"{self.store_display_name(store)} "
                    "подала вечірній звіт"
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
                    report.status.value
                ),
                "scheduled_close_time": (
                    schedule.closing_time_text
                ),
                "actual_submitted_at": (
                    report.actual_submitted_at
                    .isoformat()
                    if report.actual_submitted_at
                    is not None
                    else None
                ),
                "cash_amount": str(
                    report.cash_amount
                ),
                "has_receipt": bool(
                    getattr(
                        report,
                        "has_receipt",
                        False,
                    )
                ),
            },
        )

    async def log_missed_deadline(
        self,
        *,
        store: Store,
        report: ClosingReport,
    ) -> None:
        """Фіксує пропущений дедлайн звіту."""

        action = self.resolve_audit_action(
            "update",
            "deadline_missed",
            "closing_missed",
        )

        entity_type = self.resolve_entity_type(
            "closing_report",
            "closing",
            "store_closing",
            "store",
        )

        await self.repositories.audit.log_action(
            action=action,
            entity_type=entity_type,
            entity_id=report.id,
            context=AuditContext(
                actor_user_id=None,
                business_date=(
                    report.business_date
                ),
                description=(
                    f"{self.store_display_name(store)} "
                    "не подала вечірній звіт"
                ),
                source="scheduler",
            ),
            new_values={
                "store_id": store.id,
                "status": (
                    report.status.value
                ),
                "control_deadline": (
                    report.control_deadline
                    .strftime("%H:%M")
                ),
                "deadline_missed_at": (
                    self.datetime_to_iso(
                        getattr(
                            report,
                            "deadline_missed_at",
                            None,
                        )
                    )
                ),
            },
        )

    async def log_manual_confirmation(
        self,
        *,
        actor: User,
        store: Store,
        report: ClosingReport,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
        reason: str,
    ) -> None:
        """Фіксує ручне підтвердження звіту."""

        action = self.resolve_audit_action(
            "update",
            "manual_confirm",
            "closing_manual_confirm",
        )

        entity_type = self.resolve_entity_type(
            "closing_report",
            "closing",
            "store_closing",
            "store",
        )

        await self.repositories.audit.log_update(
            action=action,
            entity_type=entity_type,
            entity_id=report.id,
            old_values=previous_values,
            new_values=current_values,
            context=AuditContext(
                actor_user_id=actor.id,
                business_date=(
                    report.business_date
                ),
                reason=reason,
                description=(
                    "Ручне підтвердження звіту "
                    f"{self.store_display_name(store)}"
                ),
                source="telegram_bot",
            ),
            skip_if_unchanged=False,
        )

    async def log_report_modification(
        self,
        *,
        actor: User,
        store: Store,
        report: ClosingReport,
        previous_values: dict[str, Any],
        current_values: dict[str, Any],
        reason: str,
        description: str,
    ) -> None:
        """Фіксує зміну каси або фото чека."""

        action = self.resolve_audit_action(
            "update",
            "edit",
            "changed",
        )

        entity_type = self.resolve_entity_type(
            "closing_report",
            "closing",
            "store_closing",
            "store",
        )

        await self.repositories.audit.log_update(
            action=action,
            entity_type=entity_type,
            entity_id=report.id,
            old_values=previous_values,
            new_values=current_values,
            context=AuditContext(
                actor_user_id=actor.id,
                business_date=(
                    report.business_date
                ),
                reason=reason,
                description=(
                    f"{description}: "
                    f"{self.store_display_name(store)}"
                ),
                source="telegram_bot",
            ),
            skip_if_unchanged=False,
        )

    # ==========================================
    # ТЕКСТИ ПОВІДОМЛЕНЬ
    # ==========================================

    @classmethod
    def build_group_report_text(
        cls,
        *,
        store: Store,
        report: ClosingReport,
        timezone_name: str,
    ) -> str:
        """Формує підпис до фото чека."""

        timezone = cls.get_timezone(
            timezone_name
        )

        submitted_at = getattr(
            report,
            "actual_submitted_at",
            None,
        )

        submitted_time_text = (
            submitted_at
            .astimezone(timezone)
            .strftime("%H:%M")
            if submitted_at is not None
            else "не вказано"
        )

        return "\n".join(
            [
                "🌙 <b>Вечірній звіт ТТ</b>",
                "",
                (
                    "🏪 Торгова точка: "
                    f"<b>{escape(cls.store_display_name(store))}</b>"
                ),
                (
                    "📅 Дата: "
                    f"<b>{report.business_date.strftime('%d.%m.%Y')}</b>"
                ),
                (
                    "🕘 Подано о: "
                    f"<b>{submitted_time_text}</b>"
                ),
                (
                    "💰 Каса: "
                    f"<b>{cls.format_money(report.cash_amount)}</b>"
                ),
                (
                    "📊 Статус: "
                    f"<b>{escape(cls.closing_status_text(report.status))}</b>"
                ),
            ]
        )

    @classmethod
    def build_missed_notification_text(
        cls,
        *,
        store: Store,
        report: ClosingReport,
    ) -> str:
        """Формує повідомлення про неподаний звіт."""

        return "\n".join(
            [
                "🚨 <b>ТТ не подала вечірній звіт</b>",
                "",
                (
                    "🏪 "
                    f"<b>{escape(cls.store_display_name(store))}</b>"
                ),
                (
                    "🌙 Час закриття: "
                    f"<b>{report.scheduled_close_time.strftime('%H:%M')}</b>"
                ),
                (
                    "⏰ Дедлайн звіту: "
                    f"<b>{report.control_deadline.strftime('%H:%M')}</b>"
                ),
                (
                    "📅 Дата: "
                    f"<b>{report.business_date.strftime('%d.%m.%Y')}</b>"
                ),
                "",
                (
                    "Потрібно перевірити роботу "
                    "торгової точки."
                ),
            ]
        )

    # ==========================================
    # ЗНІМОК ЗВІТУ
    # ==========================================

    @staticmethod
    def closing_snapshot(
        report: ClosingReport,
    ) -> dict[str, Any]:
        """Створює знімок вечірнього звіту."""

        return {
            "status": (
                report.status.value
            ),
            "actual_submitted_at": (
                report.actual_submitted_at
                .isoformat()
                if report.actual_submitted_at
                is not None
                else None
            ),
            "cash_amount": (
                str(report.cash_amount)
                if report.cash_amount is not None
                else None
            ),
            "has_receipt": bool(
                getattr(
                    report,
                    "has_receipt",
                    False,
                )
            ),
            "receipt_file_id": getattr(
                report,
                "receipt_file_id",
                None,
            ),
            "submitted_by_id": getattr(
                report,
                "submitted_by_id",
                None,
            ),
            "manually_modified_by_id": getattr(
                report,
                "manually_modified_by_id",
                None,
            ),
            "manual_reason": getattr(
                report,
                "manual_reason",
                None,
            ),
        }

    # ==========================================
    # ДОПОМІЖНІ ЗАПИТИ
    # ==========================================

    async def load_stores(
        self,
        store_ids: set[int],
    ) -> list[Store]:
        """Завантажує ТТ одним SQL-запитом."""

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

    async def get_store_bush(
        self,
        store: Store,
    ) -> Bush | None:
        """Повертає кущ торгової точки."""

        if store.bush_id is None:
            return None

        return await self.session.get(
            Bush,
            store.bush_id,
        )

    async def get_timezone_name(
        self,
    ) -> str:
        """Повертає системний часовий пояс."""

        return (
            await self.repositories.settings
            .get_default_timezone()
        )

    # ==========================================
    # СТАТУСИ
    # ==========================================

    @staticmethod
    def is_late_report(
        report: ClosingReport,
    ) -> bool:
        """Чи поданий звіт із запізненням."""

        status_values = {
            report.status.name.lower(),
            str(report.status.value).lower(),
        }

        return bool(
            status_values.intersection(
                {
                    "submitted_late",
                    "late",
                    "closed_late",
                }
            )
        )

    @staticmethod
    def is_missed_report(
        report: ClosingReport,
    ) -> bool:
        """Чи пропущений дедлайн звіту."""

        status_values = {
            report.status.name.lower(),
            str(report.status.value).lower(),
        }

        return bool(
            status_values.intersection(
                {
                    "missed_deadline",
                    "deadline_missed",
                    "not_submitted",
                }
            )
        )

    @staticmethod
    def closing_status_text(
        status: ClosingStatus,
    ) -> str:
        """Повертає зрозумілий текст статусу."""

        values = {
            status.name.lower(),
            str(status.value).lower(),
        }

        translations = (
            (
                {
                    "waiting",
                    "pending",
                },
                "очікується",
            ),
            (
                {
                    "submitted_on_time",
                    "on_time",
                },
                "подано вчасно",
            ),
            (
                {
                    "submitted_late",
                    "late",
                    "closed_late",
                },
                "подано із запізненням",
            ),
            (
                {
                    "missed_deadline",
                    "deadline_missed",
                    "not_submitted",
                },
                "дедлайн пропущено",
            ),
            (
                {
                    "manually_confirmed",
                    "manual_confirmed",
                },
                "підтверджено вручну",
            ),
            (
                {
                    "not_required",
                },
                "звіт не потрібен",
            ),
            (
                {
                    "day_off",
                },
                "вихідний",
            ),
            (
                {
                    "temporarily_closed",
                    "temporary_closed",
                },
                "тимчасово закрито",
            ),
        )

        for aliases, text in translations:
            if values.intersection(aliases):
                return text

        return str(status.value)

    # ==========================================
    # ENUM-РЕЗОЛВЕРИ
    # ==========================================

    @classmethod
    def resolve_notification_type(
        cls,
        *names: str,
    ) -> NotificationType:
        """Знаходить тип повідомлення."""

        return cls.resolve_enum_member(
            NotificationType,
            *names,
        )

    @classmethod
    def resolve_summary_type(
        cls,
        *names: str,
    ) -> SummaryType:
        """Знаходить тип підсумку."""

        return cls.resolve_enum_member(
            SummaryType,
            *names,
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
        """
        Шукає enum за назвою або значенням.
        """

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
    # ГРАФІК
    # ==========================================

    @staticmethod
    def ensure_closing_required(
        schedule: EffectiveSchedule,
    ) -> None:
        """Перевіряє необхідність вечірнього звіту."""

        if not schedule.is_working_day:
            raise ValueError(
                schedule.reason
                or (
                    "Сьогодні для цієї ТТ "
                    "встановлено вихідний."
                )
            )

        if not schedule.requires_closing:
            raise ValueError(
                "Для цієї торгової точки не "
                "налаштовано вечірній контроль."
            )

        if schedule.closing_time is None:
            raise ValueError(
                "Не вказано час закриття ТТ."
            )

        if (
            schedule.closing_control_deadline
            is None
        ):
            raise ValueError(
                "Не вказано дедлайн вечірнього звіту."
            )

    # ==========================================
    # НАЗВИ ТТ І TELEGRAM-ТЕМИ
    # ==========================================

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
    def get_bush_closing_topic_id(
        bush: Bush | None,
    ) -> int | None:
        """Повертає Telegram topic_id закриттів."""

        if bush is None:
            return None

        for field_name in (
            "closing_topic_id",
            "telegram_closing_topic_id",
            "telegram_topic_id",
            "topic_id",
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
    # КАСА
    # ==========================================

    @staticmethod
    def normalize_cash_amount(
        value: Decimal | int | float | str,
    ) -> Decimal:
        """
        Нормалізує суму каси.

        Підтримуються формати:

        15420
        15420.50
        15420,50
        15 420,50 грн
        """

        if isinstance(value, bool):
            raise ValueError(
                "Сума каси вказана некоректно."
            )

        if isinstance(value, Decimal):
            amount = value

        elif isinstance(value, int):
            amount = Decimal(value)

        elif isinstance(value, float):
            amount = Decimal(str(value))

        elif isinstance(value, str):
            normalized_value = (
                value.strip()
                .replace("\u00a0", "")
                .replace(" ", "")
                .replace(",", ".")
            )

            normalized_value = re.sub(
                r"[^0-9.\-]",
                "",
                normalized_value,
            )

            if normalized_value.count(".") > 1:
                raise ValueError(
                    "Сума каси має некоректний формат."
                )

            if not normalized_value:
                raise ValueError(
                    "Вкажіть суму каси."
                )

            try:
                amount = Decimal(
                    normalized_value
                )

            except InvalidOperation as error:
                raise ValueError(
                    "Суму каси не вдалося розпізнати."
                ) from error

        else:
            raise ValueError(
                "Сума каси має непідтримуваний формат."
            )

        if not amount.is_finite():
            raise ValueError(
                "Сума каси повинна бути звичайним числом."
            )

        if amount < 0:
            raise ValueError(
                "Сума каси не може бути від’ємною."
            )

        if amount > Decimal("1000000000"):
            raise ValueError(
                "Сума каси перевищує допустимий ліміт."
            )

        return amount.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def format_money(
        value: Decimal | int | float | str,
    ) -> str:
        """Форматує суму у гривнях."""

        try:
            amount = Decimal(
                str(value or 0)
            ).quantize(
                Decimal("0.01")
            )

        except InvalidOperation:
            return "0,00 грн"

        formatted = (
            f"{amount:,.2f}"
            .replace(",", " ")
            .replace(".", ",")
        )

        return f"{formatted} грн"

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
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def datetime_to_iso(
        value: datetime | None,
    ) -> str | None:
        """Перетворює datetime у ISO-рядок."""

        if value is None:
            return None

        return value.isoformat()

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