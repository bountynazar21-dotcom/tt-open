from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.database.models.closing_report import ClosingReport
from app.database.models.enums import (
    ClosingStatus,
    StoreStatus,
)
from app.database.models.store import Store
from app.repositories.base import BaseRepository


@dataclass(slots=True, frozen=True)
class ClosingPlan:
    """
    Дані для створення вечірнього звіту ТТ.

    Формується на основі фактичного графіка
    торгової точки на конкретну дату.
    """

    store_id: int
    business_date: date
    scheduled_close_time: time
    control_deadline: time


class ClosingRepository(
    BaseRepository[ClosingReport]
):
    """
    Репозиторій вечірніх звітів торгових точок.

    Основні правила:

    - одна ТТ має лише один звіт на одну дату;
    - звіт містить фото чека та суму каси;
    - повторне підтвердження не змінює перший звіт;
    - фактичний час береться із сервера;
    - пропущені дедлайни фіксує scheduler;
    - історичні записи не видаляються.
    """

    model = ClosingReport

    SUBMITTED_STATUSES: frozenset[ClosingStatus] = frozenset(
        {
            ClosingStatus.SUBMITTED_ON_TIME,
            ClosingStatus.SUBMITTED_LATE,
            ClosingStatus.MANUALLY_CONFIRMED,
        }
    )

    LATE_STATUSES: frozenset[ClosingStatus] = frozenset(
        {
            ClosingStatus.SUBMITTED_LATE,
        }
    )

    PROBLEM_STATUSES: frozenset[ClosingStatus] = frozenset(
        {
            ClosingStatus.SUBMITTED_LATE,
            ClosingStatus.MISSED_DEADLINE,
        }
    )

    EXCLUDED_STATUSES: frozenset[ClosingStatus] = frozenset(
        status
        for status in (
            getattr(
                ClosingStatus,
                "NOT_REQUIRED",
                None,
            ),
            getattr(
                ClosingStatus,
                "DAY_OFF",
                None,
            ),
            getattr(
                ClosingStatus,
                "TEMPORARILY_CLOSED",
                None,
            ),
        )
        if status is not None
    )

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        super().__init__(session)

    # ==========================================
    # ПОШУК ЗВІТУ
    # ==========================================

    async def get_by_store_date(
        self,
        *,
        store_id: int,
        business_date: date,
        for_update: bool = False,
    ) -> ClosingReport | None:
        """
        Повертає вечірній звіт ТТ за дату.

        for_update=True блокує запис до завершення
        транзакції та захищає від подвійного закриття.
        """

        self.validate_positive_id(
            store_id,
            field_name="ID торгової точки",
        )

        statement = (
            select(ClosingReport)
            .where(
                ClosingReport.store_id == store_id,
                ClosingReport.business_date
                == business_date,
            )
            .limit(1)
        )

        if for_update:
            statement = (
                statement
                .options(
                    lazyload(
                        ClosingReport.store
                    ),
                    lazyload(
                        ClosingReport.submitted_by
                    ),
                    lazyload(
                        ClosingReport.manually_modified_by
                    ),
                )
                .with_for_update(
                    of=ClosingReport
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
    ) -> ClosingReport:
        """Повертає звіт або викликає помилку."""

        report = await self.get_by_store_date(
            store_id=store_id,
            business_date=business_date,
            for_update=for_update,
        )

        if report is None:
            raise ValueError(
                "Вечірній звіт для цієї торгової "
                "точки сьогодні не створено."
            )

        return report

    async def get_report_for_update(
        self,
        report_id: int,
    ) -> ClosingReport | None:
        """Завантажує звіт із блокуванням рядка."""

        self.validate_positive_id(
            report_id,
            field_name="ID звіту",
        )

        statement = (
            select(ClosingReport)
            .options(
                lazyload(
                    ClosingReport.store
                ),
                lazyload(
                    ClosingReport.submitted_by
                ),
                lazyload(
                    ClosingReport.manually_modified_by
                ),
            )
            .where(
                ClosingReport.id == report_id
            )
            .with_for_update(
                of=ClosingReport
            )
            .limit(1)
        )

        result = await self.session.scalars(
            statement
        )

        return result.unique().first()

    async def get_report_for_update_or_raise(
        self,
        report_id: int,
    ) -> ClosingReport:
        """Повертає заблокований звіт або помилку."""

        report = await self.get_report_for_update(
            report_id
        )

        if report is None:
            raise ValueError(
                "Вечірній звіт не знайдено."
            )

        return report

    # ==========================================
    # СТВОРЕННЯ ЩОДЕННОГО ЗВІТУ
    # ==========================================

    async def get_or_create_waiting(
        self,
        *,
        store_id: int,
        business_date: date,
        scheduled_close_time: time,
        control_deadline: time,
    ) -> tuple[ClosingReport, bool]:
        """
        Повертає існуючий або створює новий звіт.

        Результат:
        - ClosingReport;
        - True, якщо запис створено;
        - False, якщо запис уже існував.
        """

        normalized_close_time = self.normalize_time(
            scheduled_close_time
        )

        normalized_deadline = self.normalize_time(
            control_deadline
        )

        if normalized_deadline < normalized_close_time:
            raise ValueError(
                "Дедлайн звіту не може бути "
                "раніше часу закриття."
            )

        existing = await self.get_by_store_date(
            store_id=store_id,
            business_date=business_date,
            for_update=True,
        )

        if existing is not None:
            return existing, False

        report = ClosingReport.create_waiting(
            store_id=store_id,
            business_date=business_date,
            scheduled_close_time=(
                normalized_close_time
            ),
            control_deadline=normalized_deadline,
        )

        self.session.add(report)
        await self.session.flush()

        return report, True

    async def create_from_plan(
        self,
        plan: ClosingPlan,
    ) -> tuple[ClosingReport, bool]:
        """Створює звіт із підготовленого плану."""

        return await self.get_or_create_waiting(
            store_id=plan.store_id,
            business_date=plan.business_date,
            scheduled_close_time=(
                plan.scheduled_close_time
            ),
            control_deadline=plan.control_deadline,
        )

    async def create_missing_records(
        self,
        plans: Iterable[ClosingPlan],
    ) -> list[ClosingReport]:
        """
        Створює відсутні вечірні записи.

        Уже створені звіти не змінюються.
        """

        created_reports: list[
            ClosingReport
        ] = []

        unique_plans: dict[
            tuple[int, date],
            ClosingPlan,
        ] = {}

        for plan in plans:
            unique_plans[
                (
                    plan.store_id,
                    plan.business_date,
                )
            ] = plan

        for plan in unique_plans.values():
            report, was_created = (
                await self.create_from_plan(plan)
            )

            if was_created:
                created_reports.append(report)

        return created_reports

    # ==========================================
    # ФОТО ЧЕКА
    # ==========================================

    async def attach_receipt(
        self,
        *,
        store_id: int,
        business_date: date,
        file_id: str,
        file_unique_id: str | None = None,
        mime_type: str | None = None,
        file_name: str | None = None,
        file_size: int | None = None,
    ) -> ClosingReport:
        """
        Прикріплює фото чека до незавершеного звіту.

        Зазвичай викликається на першому кроці FSM,
        а сума каси вводиться наступним повідомленням.
        """

        report = await self.get_by_store_date_or_raise(
            store_id=store_id,
            business_date=business_date,
            for_update=True,
        )

        if report.actual_submitted_at is not None:
            raise ValueError(
                "Звіт уже підтверджено. Для заміни фото "
                "використовуйте ручне коригування."
            )

        report.attach_receipt(
            file_id=file_id,
            file_unique_id=file_unique_id,
            mime_type=mime_type,
            file_name=file_name,
            file_size=file_size,
        )

        self.session.add(report)
        await self.session.flush()

        return report

    async def remove_pending_receipt(
        self,
        *,
        store_id: int,
        business_date: date,
    ) -> ClosingReport:
        """
        Прибирає фото з незавершеного звіту.

        Потрібно, якщо користувач натиснув
        «Скасувати» під час введення каси.
        """

        report = await self.get_by_store_date_or_raise(
            store_id=store_id,
            business_date=business_date,
            for_update=True,
        )

        if report.actual_submitted_at is not None:
            raise ValueError(
                "Не можна прибрати фото із вже "
                "підтвердженого звіту."
            )

        report.has_receipt = False
        report.receipt_file_id = None
        report.receipt_file_unique_id = None
        report.receipt_mime_type = None
        report.receipt_file_name = None
        report.receipt_file_size = None

        self.session.add(report)
        await self.session.flush()

        return report

    # ==========================================
    # ПІДТВЕРДЖЕННЯ ЗВІТУ
    # ==========================================

    async def confirm_report(
        self,
        *,
        store_id: int,
        business_date: date,
        submitted_at: datetime,
        submitted_by_id: int,
        cash_amount: Decimal | int | float | str,
        scheduled_close_time: time,
        control_deadline: time,
        timezone_name: str = "Europe/Kyiv",
        require_receipt: bool = True,
        source: str = "telegram_bot",
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
        receipt_file_id: str | None = None,
        receipt_file_unique_id: str | None = None,
        receipt_mime_type: str | None = None,
        receipt_file_name: str | None = None,
        receipt_file_size: int | None = None,
    ) -> tuple[ClosingReport, bool]:
        """
        Підтверджує фінальний вечірній звіт.

        Повертає:
        - звіт;
        - True, якщо звіт підтверджено зараз;
        - False, якщо його вже було підтверджено.

        Повторне натискання не змінює перший звіт.
        """

        self.validate_aware_datetime(
            submitted_at,
            field_name="submitted_at",
        )

        self.validate_positive_id(
            submitted_by_id,
            field_name="ID користувача",
        )

        await self.get_or_create_waiting(
            store_id=store_id,
            business_date=business_date,
            scheduled_close_time=(
                scheduled_close_time
            ),
            control_deadline=control_deadline,
        )

        report = await self.get_by_store_date_or_raise(
            store_id=store_id,
            business_date=business_date,
            for_update=True,
        )

        if report.actual_submitted_at is not None:
            return report, False

        if report.status in self.EXCLUDED_STATUSES:
            raise ValueError(
                "Ця торгова точка сьогодні не повинна "
                "подавати вечірній звіт."
            )

        if receipt_file_id is not None:
            report.attach_receipt(
                file_id=receipt_file_id,
                file_unique_id=(
                    receipt_file_unique_id
                ),
                mime_type=receipt_mime_type,
                file_name=receipt_file_name,
                file_size=receipt_file_size,
            )

        deadline_datetime = (
            self.build_local_datetime(
                business_date=business_date,
                local_time=report.control_deadline,
                timezone_name=timezone_name,
            )
        )

        submitted_utc = submitted_at.astimezone(
            UTC
        )

        report.confirm_report(
            submitted_at=submitted_utc,
            control_deadline_datetime=(
                deadline_datetime
            ),
            cash_amount=cash_amount,
            submitted_by_id=submitted_by_id,
            require_receipt=require_receipt,
            source=source,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=(
                telegram_message_id
            ),
        )

        self.session.add(report)
        await self.session.flush()

        return report, True

    # ==========================================
    # ПРОПУЩЕНИЙ ДЕДЛАЙН
    # ==========================================

    async def mark_deadline_missed(
        self,
        report: ClosingReport,
        *,
        missed_at: datetime,
        alert_sent: bool = True,
    ) -> ClosingReport:
        """Фіксує пропущений дедлайн однієї ТТ."""

        self.validate_aware_datetime(
            missed_at,
            field_name="missed_at",
        )

        if report.actual_submitted_at is not None:
            return report

        if report.status in self.EXCLUDED_STATUSES:
            return report

        report.mark_deadline_missed(
            missed_at=missed_at.astimezone(UTC),
            alert_sent=alert_sent,
        )

        self.session.add(report)
        await self.session.flush()

        return report

    async def mark_due_deadlines_missed(
        self,
        *,
        current_time: datetime,
        timezone_name: str = "Europe/Kyiv",
        business_date: date | None = None,
        bush_id: int | None = None,
        cluster_id: int | None = None,
        alert_sent: bool = True,
    ) -> list[ClosingReport]:
        """
        Фіксує всі вечірні дедлайни, які вже настали.

        Використовується scheduler.

        Умова <= дозволяє наздогнати перевірку
        після короткого перезапуску Railway.
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
            ClosingReport.business_date
            == target_date,
            ClosingReport.actual_submitted_at
            .is_(None),
            ClosingReport.control_deadline
            <= target_time,
            ClosingReport.status
            == ClosingStatus.WAITING,
        ]

        statement = (
            select(ClosingReport)
            .join(
                Store,
                Store.id
                == ClosingReport.store_id,
            )
            .options(
                lazyload(
                    ClosingReport.store
                ),
                lazyload(
                    ClosingReport.submitted_by
                ),
                lazyload(
                    ClosingReport.manually_modified_by
                ),
            )
            .where(*conditions)
            .with_for_update(
                of=ClosingReport,
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

        reports = list(
            result.unique().all()
        )

        missed_at = current_time.astimezone(UTC)

        for report in reports:
            report.mark_deadline_missed(
                missed_at=missed_at,
                alert_sent=alert_sent,
            )

            self.session.add(report)

        if reports:
            await self.session.flush()

        return reports

    async def mark_deadline_alert_sent(
        self,
        report: ClosingReport,
        *,
        sent_at: datetime,
    ) -> ClosingReport:
        """Фіксує надсилання повідомлення про дедлайн."""

        self.validate_aware_datetime(
            sent_at,
            field_name="sent_at",
        )

        report.mark_deadline_alert_sent(
            sent_at=sent_at.astimezone(UTC)
        )

        self.session.add(report)
        await self.session.flush()

        return report

    # ==========================================
    # TELEGRAM-ГРУПА
    # ==========================================

    async def mark_sent_to_group(
        self,
        report: ClosingReport,
        *,
        chat_id: int,
        message_id: int,
        sent_at: datetime,
        topic_id: int | None = None,
    ) -> ClosingReport:
        """
        Зберігає Telegram message_id після
        успішного надсилання звіту в групу.
        """

        self.validate_aware_datetime(
            sent_at,
            field_name="sent_at",
        )

        if report.actual_submitted_at is None:
            raise ValueError(
                "Неможливо надіслати в групу "
                "непідтверджений звіт."
            )

        if message_id <= 0:
            raise ValueError(
                "Telegram message_id повинен бути "
                "більшим за нуль."
            )

        report.mark_sent_to_group(
            chat_id=chat_id,
            message_id=message_id,
            sent_at=sent_at.astimezone(UTC),
            topic_id=topic_id,
        )

        self.session.add(report)
        await self.session.flush()

        return report

    async def get_reports_not_sent_to_group(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        limit: int = 100,
    ) -> list[ClosingReport]:
        """
        Повертає підтверджені звіти, які ще
        не були надіслані в Telegram-групу.
        """

        if limit <= 0 or limit > 1000:
            raise ValueError(
                "Limit повинен бути від 1 до 1000."
            )

        conditions = [
            ClosingReport.business_date
            == business_date,
            ClosingReport.actual_submitted_at
            .is_not(None),
            ClosingReport.status.in_(
                self.SUBMITTED_STATUSES
            ),
            ClosingReport.closing_group_message_id
            .is_(None),
        ]

        if bush_id is not None:
            conditions.append(
                Store.bush_id == bush_id
            )

        statement = (
            select(ClosingReport)
            .join(
                Store,
                Store.id
                == ClosingReport.store_id,
            )
            .where(*conditions)
            .order_by(
                ClosingReport
                .actual_submitted_at
                .asc(),
                Store.store_number.asc(),
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
    # РУЧНЕ КОРИГУВАННЯ
    # ==========================================

    async def modify_cash_amount(
        self,
        *,
        report_id: int,
        new_cash_amount: Decimal | int | float | str,
        modified_by_id: int,
        modified_at: datetime,
        reason: str,
    ) -> ClosingReport:
        """Змінює помилково введену суму каси."""

        self.validate_aware_datetime(
            modified_at,
            field_name="modified_at",
        )

        report = (
            await self.get_report_for_update_or_raise(
                report_id
            )
        )

        if report.actual_submitted_at is None:
            raise ValueError(
                "Неможливо змінити касу у "
                "непідтвердженому звіті."
            )

        report.modify_cash_amount(
            new_cash_amount=new_cash_amount,
            modified_by_id=modified_by_id,
            modified_at=modified_at.astimezone(UTC),
            reason=reason,
        )

        self.session.add(report)
        await self.session.flush()

        return report

    async def replace_receipt(
        self,
        *,
        report_id: int,
        new_file_id: str,
        modified_by_id: int,
        modified_at: datetime,
        reason: str,
        new_file_unique_id: str | None = None,
        mime_type: str | None = None,
        file_name: str | None = None,
        file_size: int | None = None,
    ) -> ClosingReport:
        """Замінює фото чека у підтвердженому звіті."""

        self.validate_aware_datetime(
            modified_at,
            field_name="modified_at",
        )

        report = (
            await self.get_report_for_update_or_raise(
                report_id
            )
        )

        if report.actual_submitted_at is None:
            raise ValueError(
                "Неможливо замінити фото у "
                "непідтвердженому звіті."
            )

        report.replace_receipt(
            new_file_id=new_file_id,
            new_file_unique_id=(
                new_file_unique_id
            ),
            mime_type=mime_type,
            file_name=file_name,
            file_size=file_size,
            modified_by_id=modified_by_id,
            modified_at=modified_at.astimezone(UTC),
            reason=reason,
        )

        self.session.add(report)
        await self.session.flush()

        return report

    async def manually_confirm(
        self,
        *,
        store_id: int,
        business_date: date,
        submitted_at: datetime,
        cash_amount: Decimal | int | float | str,
        modified_by_id: int,
        modified_at: datetime,
        reason: str,
    ) -> ClosingReport:
        """Ручне підтвердження звіту адміністратором."""

        self.validate_aware_datetime(
            submitted_at,
            field_name="submitted_at",
        )

        self.validate_aware_datetime(
            modified_at,
            field_name="modified_at",
        )

        report = await self.get_by_store_date_or_raise(
            store_id=store_id,
            business_date=business_date,
            for_update=True,
        )

        report.manually_confirm(
            submitted_at=submitted_at.astimezone(
                UTC
            ),
            cash_amount=cash_amount,
            modified_by_id=modified_by_id,
            modified_at=modified_at.astimezone(UTC),
            reason=reason,
        )

        self.session.add(report)
        await self.session.flush()

        return report

    # ==========================================
    # ВИХІДНІ ТА ВИКЛЮЧЕННЯ
    # ==========================================

    async def mark_not_required(
        self,
        report: ClosingReport,
    ) -> ClosingReport:
        """Позначає, що вечірній звіт не потрібен."""

        status = self.get_optional_status(
            "NOT_REQUIRED"
        )

        self.ensure_not_submitted(report)

        report.status = status
        report.cash_amount = None

        self.session.add(report)
        await self.session.flush()

        return report

    async def mark_day_off(
        self,
        report: ClosingReport,
    ) -> ClosingReport:
        """Позначає вихідний день."""

        status = self.get_optional_status(
            "DAY_OFF"
        )

        self.ensure_not_submitted(report)

        report.status = status
        report.cash_amount = None

        self.session.add(report)
        await self.session.flush()

        return report

    async def mark_temporarily_closed(
        self,
        report: ClosingReport,
    ) -> ClosingReport:
        """Позначає тимчасово закриту ТТ."""

        status = self.get_optional_status(
            "TEMPORARILY_CLOSED"
        )

        self.ensure_not_submitted(report)

        report.status = status
        report.cash_amount = None

        self.session.add(report)
        await self.session.flush()

        return report

    # ==========================================
    # СПИСКИ ЗВІТІВ
    # ==========================================

    async def get_for_date(
        self,
        *,
        business_date: date,
        statuses: set[ClosingStatus] | None = None,
        bush_id: int | None = None,
        cluster_id: int | None = None,
        submitted_only: bool | None = None,
    ) -> list[ClosingReport]:
        """Повертає вечірні звіти за фільтрами."""

        conditions = [
            ClosingReport.business_date
            == business_date,
        ]

        if statuses:
            conditions.append(
                ClosingReport.status.in_(statuses)
            )

        if submitted_only is True:
            conditions.append(
                ClosingReport.actual_submitted_at
                .is_not(None)
            )

        elif submitted_only is False:
            conditions.append(
                ClosingReport.actual_submitted_at
                .is_(None)
            )

        statement = (
            select(ClosingReport)
            .join(
                Store,
                Store.id
                == ClosingReport.store_id,
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

    async def get_submitted_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[ClosingReport]:
        """Повертає всі підтверджені звіти."""

        return await self.get_for_date(
            business_date=business_date,
            statuses=set(
                self.SUBMITTED_STATUSES
            ),
            bush_id=bush_id,
            cluster_id=cluster_id,
            submitted_only=True,
        )

    async def get_submitted_on_time_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
    ) -> list[ClosingReport]:
        """Повертає ТТ, що подали звіт вчасно."""

        return await self.get_for_date(
            business_date=business_date,
            statuses={
                ClosingStatus.SUBMITTED_ON_TIME,
            },
            bush_id=bush_id,
            submitted_only=True,
        )

    async def get_late_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[ClosingReport]:
        """Повертає звіти, подані із запізненням."""

        return await self.get_for_date(
            business_date=business_date,
            statuses=set(self.LATE_STATUSES),
            bush_id=bush_id,
            cluster_id=cluster_id,
            submitted_only=True,
        )

    async def get_waiting_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[ClosingReport]:
        """Повертає ТТ, від яких ще очікується звіт."""

        return await self.get_for_date(
            business_date=business_date,
            statuses={
                ClosingStatus.WAITING,
            },
            bush_id=bush_id,
            cluster_id=cluster_id,
            submitted_only=False,
        )

    async def get_missed_for_date(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[ClosingReport]:
        """Повертає ТТ, які пропустили дедлайн."""

        return await self.get_for_date(
            business_date=business_date,
            statuses={
                ClosingStatus.MISSED_DEADLINE,
            },
            bush_id=bush_id,
            cluster_id=cluster_id,
            submitted_only=False,
        )

    async def get_problem_reports(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> list[ClosingReport]:
        """
        Повертає проблемні звіти:

        - подані із запізненням;
        - не подані до дедлайну.
        """

        return await self.get_for_date(
            business_date=business_date,
            statuses=set(
                self.PROBLEM_STATUSES
            ),
            bush_id=bush_id,
            cluster_id=cluster_id,
        )

    async def get_store_history(
        self,
        *,
        store_id: int,
        date_from: date,
        date_to: date,
    ) -> list[ClosingReport]:
        """Повертає історію закриттів конкретної ТТ."""

        self.validate_date_range(
            date_from=date_from,
            date_to=date_to,
        )

        statement = (
            select(ClosingReport)
            .where(
                ClosingReport.store_id
                == store_id,
                ClosingReport.business_date
                >= date_from,
                ClosingReport.business_date
                <= date_to,
            )
            .order_by(
                ClosingReport.business_date.desc()
            )
        )

        result = await self.session.scalars(
            statement
        )

        return list(
            result.unique().all()
        )

    # ==========================================
    # ТТ БЕЗ ВЕЧІРНЬОГО ЗАПИСУ
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
        не створив вечірній запис.
        """

        conditions = [
            Store.is_active.is_(True),
            Store.status == StoreStatus.ACTIVE,
            ClosingReport.id.is_(None),
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
                ClosingReport,
                (
                    ClosingReport.store_id
                    == Store.id
                )
                & (
                    ClosingReport.business_date
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
    # КАСА
    # ==========================================

    async def get_total_cash(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        cluster_id: int | None = None,
    ) -> Decimal:
        """Повертає загальну суму каси."""

        statement = (
            select(
                func.coalesce(
                    func.sum(
                        ClosingReport.cash_amount
                    ),
                    0,
                )
            )
            .join(
                Store,
                Store.id
                == ClosingReport.store_id,
            )
            .where(
                ClosingReport.business_date
                == business_date,
                ClosingReport.status.in_(
                    self.SUBMITTED_STATUSES
                ),
                ClosingReport.cash_amount
                .is_not(None),
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

        result = await self.session.scalar(
            statement
        )

        return Decimal(
            str(result or 0)
        ).quantize(
            Decimal("0.01")
        )

    async def get_cash_by_bush(
        self,
        *,
        business_date: date,
    ) -> list[dict[str, Any]]:
        """
        Повертає касу та кількість звітів
        окремо по кожному кущу.
        """

        statement = (
            select(
                Store.bush_id,
                func.count(
                    ClosingReport.id
                ).label("reports_count"),
                func.coalesce(
                    func.sum(
                        ClosingReport.cash_amount
                    ),
                    0,
                ).label("total_cash"),
                func.coalesce(
                    func.avg(
                        ClosingReport.cash_amount
                    ),
                    0,
                ).label("average_cash"),
            )
            .join(
                Store,
                Store.id
                == ClosingReport.store_id,
            )
            .where(
                ClosingReport.business_date
                == business_date,
                ClosingReport.status.in_(
                    self.SUBMITTED_STATUSES
                ),
                ClosingReport.cash_amount
                .is_not(None),
            )
            .group_by(
                Store.bush_id
            )
            .order_by(
                func.sum(
                    ClosingReport.cash_amount
                ).desc()
            )
        )

        result = await self.session.execute(
            statement
        )

        summaries: list[dict[str, Any]] = []

        for row in result.mappings().all():
            summaries.append(
                {
                    "bush_id": row["bush_id"],
                    "reports_count": int(
                        row["reports_count"]
                    ),
                    "total_cash": Decimal(
                        str(row["total_cash"] or 0)
                    ).quantize(
                        Decimal("0.01")
                    ),
                    "average_cash": Decimal(
                        str(row["average_cash"] or 0)
                    ).quantize(
                        Decimal("0.01")
                    ),
                }
            )

        return summaries

    async def get_cash_ranking(
        self,
        *,
        business_date: date,
        bush_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Повертає рейтинг ТТ за сумою каси."""

        if limit <= 0 or limit > 1000:
            raise ValueError(
                "Limit повинен бути від 1 до 1000."
            )

        conditions = [
            ClosingReport.business_date
            == business_date,
            ClosingReport.status.in_(
                self.SUBMITTED_STATUSES
            ),
            ClosingReport.cash_amount
            .is_not(None),
        ]

        if bush_id is not None:
            conditions.append(
                Store.bush_id == bush_id
            )

        statement = (
            select(
                ClosingReport.id,
                ClosingReport.store_id,
                ClosingReport.cash_amount,
                ClosingReport.actual_submitted_at,
                ClosingReport.status,
                Store.store_number,
                Store.code,
                Store.city,
                Store.address,
                Store.bush_id,
            )
            .join(
                Store,
                Store.id
                == ClosingReport.store_id,
            )
            .where(*conditions)
            .order_by(
                ClosingReport.cash_amount.desc(),
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
                    "report_id": int(
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
                    "cash_amount": Decimal(
                        str(
                            row["cash_amount"]
                            or 0
                        )
                    ).quantize(
                        Decimal("0.01")
                    ),
                    "submitted_at": (
                        row[
                            "actual_submitted_at"
                        ]
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
    ) -> dict[ClosingStatus, int]:
        """Підраховує звіти за статусами."""

        statement = (
            select(
                ClosingReport.status,
                func.count(
                    ClosingReport.id
                ),
            )
            .join(
                Store,
                Store.id
                == ClosingReport.store_id,
            )
            .where(
                ClosingReport.business_date
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
            ClosingReport.status
        )

        result = await self.session.execute(
            statement
        )

        counts: dict[ClosingStatus, int] = {
            status: 0
            for status in ClosingStatus
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
    ) -> dict[str, int | float | Decimal]:
        """Формує повну статистику закриття."""

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

        submitted_count = sum(
            counts[status]
            for status in self.SUBMITTED_STATUSES
        )

        waiting_count = counts[
            ClosingStatus.WAITING
        ]

        late_count = counts[
            ClosingStatus.SUBMITTED_LATE
        ]

        missed_count = counts[
            ClosingStatus.MISSED_DEADLINE
        ]

        total_cash = await self.get_total_cash(
            business_date=business_date,
            bush_id=bush_id,
            cluster_id=cluster_id,
        )

        aggregate_statement = (
            select(
                func.coalesce(
                    func.avg(
                        ClosingReport.cash_amount
                    ),
                    0,
                ),
                func.coalesce(
                    func.max(
                        ClosingReport.cash_amount
                    ),
                    0,
                ),
                func.coalesce(
                    func.min(
                        ClosingReport.cash_amount
                    ),
                    0,
                ),
            )
            .join(
                Store,
                Store.id
                == ClosingReport.store_id,
            )
            .where(
                ClosingReport.business_date
                == business_date,
                ClosingReport.status.in_(
                    self.SUBMITTED_STATUSES
                ),
                ClosingReport.cash_amount
                .is_not(None),
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

        average_cash, maximum_cash, minimum_cash = (
            aggregate_result.one()
        )

        completion_percent = (
            round(
                submitted_count
                / expected_count
                * 100,
                2,
            )
            if expected_count > 0
            else 0.0
        )

        return {
            "expected_count": expected_count,
            "submitted_count": submitted_count,
            "submitted_on_time_count": counts[
                ClosingStatus.SUBMITTED_ON_TIME
            ],
            "submitted_late_count": late_count,
            "manually_confirmed_count": counts[
                ClosingStatus.MANUALLY_CONFIRMED
            ],
            "waiting_count": waiting_count,
            "missed_count": missed_count,
            "problem_count": (
                late_count + missed_count
            ),
            "total_cash": total_cash,
            "average_cash": Decimal(
                str(average_cash or 0)
            ).quantize(
                Decimal("0.01")
            ),
            "maximum_cash": Decimal(
                str(maximum_cash or 0)
            ).quantize(
                Decimal("0.01")
            ),
            "minimum_cash": Decimal(
                str(minimum_cash or 0)
            ).quantize(
                Decimal("0.01")
            ),
            "completion_percent": (
                completion_percent
            ),
        }

    # ==========================================
    # ДОПОМІЖНІ МЕТОДИ
    # ==========================================

    @staticmethod
    def ensure_not_submitted(
        report: ClosingReport,
    ) -> None:
        """Забороняє змінювати вже поданий звіт."""

        if report.actual_submitted_at is not None:
            raise ValueError(
                "Не можна змінити статус, оскільки "
                "вечірній звіт уже підтверджено."
            )

    @staticmethod
    def get_optional_status(
        status_name: str,
    ) -> ClosingStatus:
        """
        Повертає необов’язковий статус.

        Використовується для статусів вихідного дня
        та тимчасового закриття.
        """

        status = getattr(
            ClosingStatus,
            status_name,
            None,
        )

        if status is None:
            raise ValueError(
                "У ClosingStatus відсутній статус "
                f"{status_name}."
            )

        return status

    @staticmethod
    def build_local_datetime(
        *,
        business_date: date,
        local_time: time,
        timezone_name: str,
    ) -> datetime:
        """Об’єднує локальну дату та час ТТ."""

        timezone = ClosingRepository.get_timezone(
            timezone_name
        )

        normalized_time = (
            ClosingRepository.normalize_time(
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