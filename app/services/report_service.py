from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum, StrEnum
from html import escape
from typing import Any

from sqlalchemy import select

from app.database.models.closing_report import ClosingReport
from app.database.models.opening_checkin import OpeningCheckin
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories import Repositories
from app.services.access import AccessService


class ReportPeriodType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class ReportScopeType(StrEnum):
    NETWORK = "network"
    BUSH = "bush"
    STORE = "store"


@dataclass(slots=True, frozen=True)
class ReportScope:
    """
    Область звіту:

    - уся мережа;
    - конкретний кущ;
    - конкретна ТТ.
    """

    scope_type: ReportScopeType

    store_id: int | None = None
    bush_id: int | None = None


@dataclass(slots=True, frozen=True)
class StoreDailyReportRow:
    """
    Дані однієї торгової точки за один день.
    """

    business_date: date

    store_id: int
    store_code: str
    store_name: str

    city: str | None
    address: str | None

    bush_id: int | None
    cluster_id: int | None

    opening_checkin_id: int | None
    opening_status: str

    scheduled_open_time: time | None
    opening_control_deadline: time | None
    actual_open_time: datetime | None

    opening_lateness_minutes: int
    opening_deadline_missed: bool

    opening_submitted_by_id: int | None

    closing_report_id: int | None
    closing_status: str

    scheduled_close_time: time | None
    closing_control_deadline: time | None
    actual_closing_submitted_at: datetime | None

    closing_late: bool
    closing_deadline_missed: bool

    closing_submitted_by_id: int | None

    cash_amount: Decimal
    receipt_attached: bool

    @property
    def opening_confirmed(self) -> bool:
        return self.actual_open_time is not None

    @property
    def closing_confirmed(self) -> bool:
        return (
            self.actual_closing_submitted_at
            is not None
        )


@dataclass(slots=True, frozen=True)
class DailyReportTotals:
    """
    Загальні показники за один день.
    """

    store_count: int

    opening_expected_count: int
    opened_count: int
    opened_on_time_count: int
    opened_late_count: int
    opening_missed_count: int
    opening_waiting_count: int

    total_lateness_minutes: int
    average_lateness_minutes: float

    closing_expected_count: int
    closing_submitted_count: int
    closing_on_time_count: int
    closing_late_count: int
    closing_missed_count: int
    closing_waiting_count: int

    total_cash: Decimal
    average_cash: Decimal


@dataclass(slots=True, frozen=True)
class DailyReportResult:
    """
    Повний денний звіт.
    """

    scope: ReportScope
    business_date: date

    totals: DailyReportTotals

    rows: tuple[
        StoreDailyReportRow,
        ...,
    ]


@dataclass(slots=True, frozen=True)
class StorePeriodSummary:
    """
    Підсумок однієї ТТ за період.
    """

    store_id: int
    store_code: str
    store_name: str

    city: str | None
    address: str | None

    bush_id: int | None
    cluster_id: int | None

    opening_expected_days: int
    opened_days: int
    opened_on_time_days: int
    opened_late_days: int
    opening_missed_days: int
    opening_waiting_days: int

    total_lateness_minutes: int
    average_lateness_minutes: float

    closing_expected_days: int
    closing_submitted_days: int
    closing_on_time_days: int
    closing_late_days: int
    closing_missed_days: int
    closing_waiting_days: int

    total_cash: Decimal
    average_cash: Decimal

    @property
    def opening_completion_percent(
        self,
    ) -> float:
        if self.opening_expected_days == 0:
            return 0.0

        return round(
            self.opened_days
            / self.opening_expected_days
            * 100,
            2,
        )

    @property
    def closing_completion_percent(
        self,
    ) -> float:
        if self.closing_expected_days == 0:
            return 0.0

        return round(
            self.closing_submitted_days
            / self.closing_expected_days
            * 100,
            2,
        )


@dataclass(slots=True, frozen=True)
class PeriodReportTotals:
    """
    Загальні показники за період.
    """

    store_count: int
    calendar_days: int

    opening_expected_count: int
    opened_count: int
    opened_on_time_count: int
    opened_late_count: int
    opening_missed_count: int
    opening_waiting_count: int

    total_lateness_minutes: int
    average_lateness_minutes: float

    closing_expected_count: int
    closing_submitted_count: int
    closing_on_time_count: int
    closing_late_count: int
    closing_missed_count: int
    closing_waiting_count: int

    total_cash: Decimal
    average_cash: Decimal


@dataclass(slots=True, frozen=True)
class PeriodReportResult:
    """
    Повний звіт за період.
    """

    period_type: ReportPeriodType
    scope: ReportScope

    date_from: date
    date_to: date

    totals: PeriodReportTotals

    stores: tuple[
        StorePeriodSummary,
        ...,
    ]

    daily_rows: tuple[
        StoreDailyReportRow,
        ...,
    ]


@dataclass(slots=True, frozen=True)
class ExcelSheetData:
    """
    Дані одного Excel-аркуша.
    """

    title: str

    headers: tuple[str, ...]

    rows: tuple[
        tuple[Any, ...],
        ...,
    ]

    column_widths: tuple[float, ...]

    freeze_panes: str = "A2"
    auto_filter: bool = True


@dataclass(slots=True, frozen=True)
class ExcelReportData:
    """
    Повністю підготовлена структура
    майбутнього Excel-файлу.
    """

    filename: str
    workbook_title: str

    sheets: tuple[
        ExcelSheetData,
        ...,
    ]

    metadata: dict[str, Any]


class ReportService:
    """
    Сервіс звітів відкриття та закриття ТТ.

    Формує:

    - денний звіт;
    - тижневий звіт;
    - місячний звіт;
    - довільний період;
    - статистику кожної ТТ;
    - дані для Excel-файлів.

    Фізичний .xlsx-файл тут не створюється.
    Сервіс готує ExcelReportData, яку далі
    оброблятиме ExcelService.
    """

    MAX_PERIOD_DAYS = 370

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
    # ДЕННИЙ ЗВІТ
    # ==========================================

    async def get_daily_report(
        self,
        *,
        user: User,
        business_date: date,
        store_id: int | None = None,
        bush_id: int | None = None,
        active_only: bool = True,
    ) -> DailyReportResult:
        """Формує звіт за один день."""

        scope, stores = (
            await self.resolve_scope_and_stores(
                user=user,
                store_id=store_id,
                bush_id=bush_id,
                active_only=active_only,
            )
        )

        rows = await self.build_daily_rows(
            stores=stores,
            date_from=business_date,
            date_to=business_date,
        )

        totals = self.calculate_daily_totals(
            rows
        )

        return DailyReportResult(
            scope=scope,
            business_date=business_date,
            totals=totals,
            rows=tuple(rows),
        )

    # ==========================================
    # ТИЖНЕВИЙ ЗВІТ
    # ==========================================

    async def get_weekly_report(
        self,
        *,
        user: User,
        reference_date: date,
        store_id: int | None = None,
        bush_id: int | None = None,
        active_only: bool = True,
    ) -> PeriodReportResult:
        """Формує звіт із понеділка до неділі."""

        date_from, date_to = self.week_bounds(
            reference_date
        )

        return await self.get_period_report(
            user=user,
            date_from=date_from,
            date_to=date_to,
            period_type=(
                ReportPeriodType.WEEKLY
            ),
            store_id=store_id,
            bush_id=bush_id,
            active_only=active_only,
        )

    # ==========================================
    # МІСЯЧНИЙ ЗВІТ
    # ==========================================

    async def get_monthly_report(
        self,
        *,
        user: User,
        year: int,
        month: int,
        store_id: int | None = None,
        bush_id: int | None = None,
        active_only: bool = True,
    ) -> PeriodReportResult:
        """Формує звіт за календарний місяць."""

        date_from, date_to = self.month_bounds(
            year=year,
            month=month,
        )

        return await self.get_period_report(
            user=user,
            date_from=date_from,
            date_to=date_to,
            period_type=(
                ReportPeriodType.MONTHLY
            ),
            store_id=store_id,
            bush_id=bush_id,
            active_only=active_only,
        )

    # ==========================================
    # ДОВІЛЬНИЙ ПЕРІОД
    # ==========================================

    async def get_period_report(
        self,
        *,
        user: User,
        date_from: date,
        date_to: date,
        period_type: ReportPeriodType = (
            ReportPeriodType.CUSTOM
        ),
        store_id: int | None = None,
        bush_id: int | None = None,
        active_only: bool = True,
    ) -> PeriodReportResult:
        """Формує звіт за довільний період."""

        self.validate_date_range(
            date_from=date_from,
            date_to=date_to,
        )

        scope, stores = (
            await self.resolve_scope_and_stores(
                user=user,
                store_id=store_id,
                bush_id=bush_id,
                active_only=active_only,
            )
        )

        rows = await self.build_daily_rows(
            stores=stores,
            date_from=date_from,
            date_to=date_to,
        )

        store_summaries = (
            self.calculate_store_period_summaries(
                stores=stores,
                rows=rows,
            )
        )

        totals = self.calculate_period_totals(
            store_summaries=store_summaries,
            date_from=date_from,
            date_to=date_to,
        )

        return PeriodReportResult(
            period_type=period_type,
            scope=scope,
            date_from=date_from,
            date_to=date_to,
            totals=totals,
            stores=tuple(store_summaries),
            daily_rows=tuple(rows),
        )

    # ==========================================
    # ДОСТУП І ТОРГОВІ ТОЧКИ
    # ==========================================

    async def resolve_scope_and_stores(
        self,
        *,
        user: User,
        store_id: int | None,
        bush_id: int | None,
        active_only: bool,
    ) -> tuple[
        ReportScope,
        list[Store],
    ]:
        """Перевіряє доступ і завантажує ТТ."""

        if (
            store_id is not None
            and bush_id is not None
        ):
            raise ValueError(
                "Не можна одночасно вказувати "
                "store_id і bush_id."
            )

        if store_id is not None:
            store = (
                await self.access
                .require_store_view(
                    user,
                    store_id,
                )
            )

            if (
                active_only
                and not bool(
                    getattr(
                        store,
                        "is_active",
                        True,
                    )
                )
            ):
                return (
                    ReportScope(
                        scope_type=(
                            ReportScopeType.STORE
                        ),
                        store_id=store.id,
                        bush_id=store.bush_id,
                    ),
                    [],
                )

            return (
                ReportScope(
                    scope_type=(
                        ReportScopeType.STORE
                    ),
                    store_id=store.id,
                    bush_id=store.bush_id,
                ),
                [store],
            )

        if bush_id is not None:
            await self.access.require_bush_view(
                user,
                bush_id,
            )

            stores = await self.load_stores(
                bush_id=bush_id,
                active_only=active_only,
            )

            return (
                ReportScope(
                    scope_type=(
                        ReportScopeType.BUSH
                    ),
                    bush_id=bush_id,
                ),
                stores,
            )

        self.access.require_network_view(user)

        stores = await self.load_stores(
            active_only=active_only,
        )

        return (
            ReportScope(
                scope_type=(
                    ReportScopeType.NETWORK
                ),
            ),
            stores,
        )

    async def load_stores(
        self,
        *,
        bush_id: int | None = None,
        active_only: bool = True,
    ) -> list[Store]:
        """Завантажує ТТ потрібної області."""

        conditions: list[Any] = []

        if bush_id is not None:
            conditions.append(
                Store.bush_id == bush_id
            )

        if (
            active_only
            and hasattr(Store, "is_active")
        ):
            conditions.append(
                Store.is_active.is_(True)
            )

        statement = (
            select(Store)
            .where(*conditions)
        )

        result = await self.session.scalars(
            statement
        )

        stores = list(
            result.unique().all()
        )

        return sorted(
            stores,
            key=self.store_sort_key,
        )

    # ==========================================
    # ЗАВАНТАЖЕННЯ ЗАПИСІВ
    # ==========================================

    async def build_daily_rows(
        self,
        *,
        stores: list[Store],
        date_from: date,
        date_to: date,
    ) -> list[StoreDailyReportRow]:
        """
        Завантажує відкриття та закриття
        двома SQL-запитами.
        """

        if not stores:
            return []

        store_ids = {
            store.id
            for store in stores
        }

        opening_statement = (
            select(OpeningCheckin)
            .where(
                OpeningCheckin.store_id.in_(
                    store_ids
                ),
                OpeningCheckin.business_date
                >= date_from,
                OpeningCheckin.business_date
                <= date_to,
            )
        )

        closing_statement = (
            select(ClosingReport)
            .where(
                ClosingReport.store_id.in_(
                    store_ids
                ),
                ClosingReport.business_date
                >= date_from,
                ClosingReport.business_date
                <= date_to,
            )
        )

        opening_result = (
            await self.session.scalars(
                opening_statement
            )
        )

        closing_result = (
            await self.session.scalars(
                closing_statement
            )
        )

        opening_map = {
            (
                checkin.business_date,
                checkin.store_id,
            ): checkin
            for checkin
            in opening_result.unique().all()
        }

        closing_map = {
            (
                report.business_date,
                report.store_id,
            ): report
            for report
            in closing_result.unique().all()
        }

        rows: list[
            StoreDailyReportRow
        ] = []

        current_date = date_from

        while current_date <= date_to:
            for store in stores:
                opening = opening_map.get(
                    (
                        current_date,
                        store.id,
                    )
                )

                closing = closing_map.get(
                    (
                        current_date,
                        store.id,
                    )
                )

                # Для звіту за період не створюємо
                # порожні рядки за вихідні дні.
                if (
                    opening is None
                    and closing is None
                    and date_from != date_to
                ):
                    continue

                rows.append(
                    self.build_daily_row(
                        business_date=(
                            current_date
                        ),
                        store=store,
                        opening=opening,
                        closing=closing,
                    )
                )

            current_date += timedelta(days=1)

        return rows

    def build_daily_row(
        self,
        *,
        business_date: date,
        store: Store,
        opening: OpeningCheckin | None,
        closing: ClosingReport | None,
    ) -> StoreDailyReportRow:
        """Формує один рядок ТТ за день."""

        opening_status = self.enum_value(
            getattr(
                opening,
                "status",
                "not_recorded",
            )
        )

        closing_status = self.enum_value(
            getattr(
                closing,
                "status",
                "not_recorded",
            )
        )

        opening_lateness = max(
            int(
                getattr(
                    opening,
                    "lateness_minutes",
                    0,
                )
                or 0
            ),
            0,
        )

        return StoreDailyReportRow(
            business_date=business_date,

            store_id=store.id,
            store_code=self.store_code(store),
            store_name=self.store_name(store),

            city=self.optional_text(
                getattr(
                    store,
                    "city",
                    None,
                )
            ),
            address=self.optional_text(
                getattr(
                    store,
                    "address",
                    None,
                )
            ),

            bush_id=getattr(
                store,
                "bush_id",
                None,
            ),
            cluster_id=getattr(
                store,
                "cluster_id",
                None,
            ),

            opening_checkin_id=getattr(
                opening,
                "id",
                None,
            ),
            opening_status=opening_status,

            scheduled_open_time=getattr(
                opening,
                "scheduled_open_time",
                None,
            ),
            opening_control_deadline=getattr(
                opening,
                "control_deadline",
                None,
            ),
            actual_open_time=getattr(
                opening,
                "actual_open_time",
                None,
            ),

            opening_lateness_minutes=(
                opening_lateness
            ),
            opening_deadline_missed=(
                self.status_is_missed(
                    opening_status
                )
            ),

            opening_submitted_by_id=getattr(
                opening,
                "submitted_by_id",
                None,
            ),

            closing_report_id=getattr(
                closing,
                "id",
                None,
            ),
            closing_status=closing_status,

            scheduled_close_time=getattr(
                closing,
                "scheduled_close_time",
                None,
            ),
            closing_control_deadline=getattr(
                closing,
                "control_deadline",
                None,
            ),
            actual_closing_submitted_at=getattr(
                closing,
                "actual_submitted_at",
                None,
            ),

            closing_late=self.status_is_late(
                closing_status
            ),
            closing_deadline_missed=(
                self.status_is_missed(
                    closing_status
                )
            ),

            closing_submitted_by_id=getattr(
                closing,
                "submitted_by_id",
                None,
            ),

            cash_amount=self.decimal_value(
                getattr(
                    closing,
                    "cash_amount",
                    None,
                )
            ),

            receipt_attached=bool(
                getattr(
                    closing,
                    "receipt_file_id",
                    None,
                )
                or getattr(
                    closing,
                    "has_receipt",
                    False,
                )
            ),
        )

    # ==========================================
    # ДЕННІ ПІДСУМКИ
    # ==========================================

    def calculate_daily_totals(
        self,
        rows: list[StoreDailyReportRow],
    ) -> DailyReportTotals:
        """Рахує загальні показники дня."""

        opening_rows = [
            row
            for row in rows
            if row.opening_checkin_id is not None
        ]

        closing_rows = [
            row
            for row in rows
            if row.closing_report_id is not None
        ]

        opened_rows = [
            row
            for row in opening_rows
            if row.opening_confirmed
        ]

        submitted_rows = [
            row
            for row in closing_rows
            if row.closing_confirmed
        ]

        late_opening_rows = [
            row
            for row in opened_rows
            if row.opening_lateness_minutes > 0
        ]

        late_closing_rows = [
            row
            for row in submitted_rows
            if row.closing_late
        ]

        total_lateness = sum(
            row.opening_lateness_minutes
            for row in opened_rows
        )

        cash_values = [
            row.cash_amount
            for row in submitted_rows
        ]

        total_cash = sum(
            cash_values,
            Decimal("0.00"),
        )

        average_cash = (
            total_cash / len(cash_values)
            if cash_values
            else Decimal("0.00")
        )

        return DailyReportTotals(
            store_count=len(rows),

            opening_expected_count=(
                len(opening_rows)
            ),
            opened_count=len(opened_rows),
            opened_on_time_count=(
                len(opened_rows)
                - len(late_opening_rows)
            ),
            opened_late_count=(
                len(late_opening_rows)
            ),
            opening_missed_count=sum(
                row.opening_deadline_missed
                for row in opening_rows
            ),
            opening_waiting_count=sum(
                not row.opening_confirmed
                and not row.opening_deadline_missed
                for row in opening_rows
            ),

            total_lateness_minutes=(
                total_lateness
            ),
            average_lateness_minutes=(
                round(
                    total_lateness
                    / len(late_opening_rows),
                    2,
                )
                if late_opening_rows
                else 0.0
            ),

            closing_expected_count=(
                len(closing_rows)
            ),
            closing_submitted_count=(
                len(submitted_rows)
            ),
            closing_on_time_count=(
                len(submitted_rows)
                - len(late_closing_rows)
            ),
            closing_late_count=(
                len(late_closing_rows)
            ),
            closing_missed_count=sum(
                row.closing_deadline_missed
                for row in closing_rows
            ),
            closing_waiting_count=sum(
                not row.closing_confirmed
                and not row.closing_deadline_missed
                for row in closing_rows
            ),

            total_cash=self.money(total_cash),
            average_cash=self.money(
                average_cash
            ),
        )

    # ==========================================
    # ПІДСУМКИ ТТ ЗА ПЕРІОД
    # ==========================================

    def calculate_store_period_summaries(
        self,
        *,
        stores: list[Store],
        rows: list[StoreDailyReportRow],
    ) -> list[StorePeriodSummary]:
        """Рахує статистику кожної ТТ."""

        rows_by_store: dict[
            int,
            list[StoreDailyReportRow],
        ] = {}

        for row in rows:
            rows_by_store.setdefault(
                row.store_id,
                [],
            ).append(row)

        summaries: list[
            StorePeriodSummary
        ] = []

        for store in stores:
            store_rows = rows_by_store.get(
                store.id,
                [],
            )

            opening_rows = [
                row
                for row in store_rows
                if (
                    row.opening_checkin_id
                    is not None
                )
            ]

            closing_rows = [
                row
                for row in store_rows
                if (
                    row.closing_report_id
                    is not None
                )
            ]

            opened_rows = [
                row
                for row in opening_rows
                if row.opening_confirmed
            ]

            submitted_rows = [
                row
                for row in closing_rows
                if row.closing_confirmed
            ]

            late_opening_rows = [
                row
                for row in opened_rows
                if (
                    row.opening_lateness_minutes
                    > 0
                )
            ]

            late_closing_rows = [
                row
                for row in submitted_rows
                if row.closing_late
            ]

            total_lateness = sum(
                row.opening_lateness_minutes
                for row in opened_rows
            )

            total_cash = sum(
                (
                    row.cash_amount
                    for row in submitted_rows
                ),
                Decimal("0.00"),
            )

            average_cash = (
                total_cash
                / len(submitted_rows)
                if submitted_rows
                else Decimal("0.00")
            )

            summaries.append(
                StorePeriodSummary(
                    store_id=store.id,
                    store_code=(
                        self.store_code(store)
                    ),
                    store_name=(
                        self.store_name(store)
                    ),

                    city=self.optional_text(
                        getattr(
                            store,
                            "city",
                            None,
                        )
                    ),
                    address=self.optional_text(
                        getattr(
                            store,
                            "address",
                            None,
                        )
                    ),

                    bush_id=getattr(
                        store,
                        "bush_id",
                        None,
                    ),
                    cluster_id=getattr(
                        store,
                        "cluster_id",
                        None,
                    ),

                    opening_expected_days=(
                        len(opening_rows)
                    ),
                    opened_days=(
                        len(opened_rows)
                    ),
                    opened_on_time_days=(
                        len(opened_rows)
                        - len(late_opening_rows)
                    ),
                    opened_late_days=(
                        len(late_opening_rows)
                    ),
                    opening_missed_days=sum(
                        row.opening_deadline_missed
                        for row in opening_rows
                    ),
                    opening_waiting_days=sum(
                        not row.opening_confirmed
                        and not (
                            row
                            .opening_deadline_missed
                        )
                        for row in opening_rows
                    ),

                    total_lateness_minutes=(
                        total_lateness
                    ),
                    average_lateness_minutes=(
                        round(
                            total_lateness
                            / len(
                                late_opening_rows
                            ),
                            2,
                        )
                        if late_opening_rows
                        else 0.0
                    ),

                    closing_expected_days=(
                        len(closing_rows)
                    ),
                    closing_submitted_days=(
                        len(submitted_rows)
                    ),
                    closing_on_time_days=(
                        len(submitted_rows)
                        - len(late_closing_rows)
                    ),
                    closing_late_days=(
                        len(late_closing_rows)
                    ),
                    closing_missed_days=sum(
                        row.closing_deadline_missed
                        for row in closing_rows
                    ),
                    closing_waiting_days=sum(
                        not row.closing_confirmed
                        and not (
                            row
                            .closing_deadline_missed
                        )
                        for row in closing_rows
                    ),

                    total_cash=self.money(
                        total_cash
                    ),
                    average_cash=self.money(
                        average_cash
                    ),
                )
            )

        return summaries

    def calculate_period_totals(
        self,
        *,
        store_summaries: list[
            StorePeriodSummary
        ],
        date_from: date,
        date_to: date,
    ) -> PeriodReportTotals:
        """Рахує загальні показники періоду."""

        opening_expected = sum(
            item.opening_expected_days
            for item in store_summaries
        )

        opened = sum(
            item.opened_days
            for item in store_summaries
        )

        opened_late = sum(
            item.opened_late_days
            for item in store_summaries
        )

        total_lateness = sum(
            item.total_lateness_minutes
            for item in store_summaries
        )

        closing_expected = sum(
            item.closing_expected_days
            for item in store_summaries
        )

        closing_submitted = sum(
            item.closing_submitted_days
            for item in store_summaries
        )

        closing_late = sum(
            item.closing_late_days
            for item in store_summaries
        )

        total_cash = sum(
            (
                item.total_cash
                for item in store_summaries
            ),
            Decimal("0.00"),
        )

        average_cash = (
            total_cash / closing_submitted
            if closing_submitted > 0
            else Decimal("0.00")
        )

        return PeriodReportTotals(
            store_count=len(
                store_summaries
            ),
            calendar_days=(
                date_to - date_from
            ).days + 1,

            opening_expected_count=(
                opening_expected
            ),
            opened_count=opened,
            opened_on_time_count=(
                opened - opened_late
            ),
            opened_late_count=(
                opened_late
            ),
            opening_missed_count=sum(
                item.opening_missed_days
                for item in store_summaries
            ),
            opening_waiting_count=sum(
                item.opening_waiting_days
                for item in store_summaries
            ),

            total_lateness_minutes=(
                total_lateness
            ),
            average_lateness_minutes=(
                round(
                    total_lateness
                    / opened_late,
                    2,
                )
                if opened_late > 0
                else 0.0
            ),

            closing_expected_count=(
                closing_expected
            ),
            closing_submitted_count=(
                closing_submitted
            ),
            closing_on_time_count=(
                closing_submitted
                - closing_late
            ),
            closing_late_count=(
                closing_late
            ),
            closing_missed_count=sum(
                item.closing_missed_days
                for item in store_summaries
            ),
            closing_waiting_count=sum(
                item.closing_waiting_days
                for item in store_summaries
            ),

            total_cash=self.money(
                total_cash
            ),
            average_cash=self.money(
                average_cash
            ),
        )

    # ==========================================
    # EXCEL: ДЕННИЙ ЗВІТ
    # ==========================================

    async def prepare_daily_excel(
        self,
        *,
        user: User,
        business_date: date,
        store_id: int | None = None,
        bush_id: int | None = None,
        active_only: bool = True,
    ) -> ExcelReportData:
        """Готує дані денного Excel-звіту."""

        await self.ensure_export_access(
            user=user,
            store_id=store_id,
            bush_id=bush_id,
        )

        report = await self.get_daily_report(
            user=user,
            business_date=business_date,
            store_id=store_id,
            bush_id=bush_id,
            active_only=active_only,
        )

        details_sheet = ExcelSheetData(
            title="Денний звіт",
            headers=(
                "Дата",
                "ТТ",
                "Назва",
                "Місто",
                "Адреса",
                "Кущ ID",
                "Кластер ID",
                "Статус відкриття",
                "План відкриття",
                "Дедлайн відкриття",
                "Фактичне відкриття",
                "Запізнення, хв",
                "Статус закриття",
                "План закриття",
                "Дедлайн звіту",
                "Звіт подано",
                "Каса, грн",
                "Фото чека",
            ),
            rows=tuple(
                self.daily_excel_row(row)
                for row in report.rows
            ),
            column_widths=(
                13,
                12,
                24,
                18,
                32,
                10,
                12,
                23,
                16,
                19,
                20,
                17,
                23,
                16,
                17,
                20,
                15,
                13,
            ),
        )

        totals_sheet = (
            self.daily_totals_sheet(
                report
            )
        )

        scope_name = self.scope_filename_part(
            report.scope
        )

        return ExcelReportData(
            filename=(
                "daily_report_"
                f"{business_date.isoformat()}_"
                f"{scope_name}.xlsx"
            ),
            workbook_title=(
                "Денний звіт "
                f"{business_date.strftime('%d.%m.%Y')}"
            ),
            sheets=(
                details_sheet,
                totals_sheet,
            ),
            metadata={
                "report_type": "daily",
                "business_date": (
                    business_date.isoformat()
                ),
                "scope": (
                    report
                    .scope
                    .scope_type
                    .value
                ),
                "store_id": (
                    report.scope.store_id
                ),
                "bush_id": (
                    report.scope.bush_id
                ),
            },
        )

    # ==========================================
    # EXCEL: ПЕРІОД
    # ==========================================

    async def prepare_period_excel(
        self,
        *,
        user: User,
        date_from: date,
        date_to: date,
        period_type: ReportPeriodType = (
            ReportPeriodType.CUSTOM
        ),
        store_id: int | None = None,
        bush_id: int | None = None,
        active_only: bool = True,
    ) -> ExcelReportData:
        """Готує Excel-звіт за період."""

        await self.ensure_export_access(
            user=user,
            store_id=store_id,
            bush_id=bush_id,
        )

        report = await self.get_period_report(
            user=user,
            date_from=date_from,
            date_to=date_to,
            period_type=period_type,
            store_id=store_id,
            bush_id=bush_id,
            active_only=active_only,
        )

        summary_sheet = ExcelSheetData(
            title="Підсумок по ТТ",
            headers=(
                "ТТ",
                "Назва",
                "Місто",
                "Адреса",
                "Кущ ID",
                "Кластер ID",
                "Очікувалось відкриттів",
                "Відкрито",
                "Вчасно",
                "Із запізненням",
                "Пропущено дедлайнів",
                "Загальне запізнення, хв",
                "Середнє запізнення, хв",
                "% відкриттів",
                "Очікувалось звітів",
                "Подано звітів",
                "Звіти вчасно",
                "Звіти із запізненням",
                "Не подано звітів",
                "% закриттів",
                "Загальна каса, грн",
                "Середня каса, грн",
            ),
            rows=tuple(
                self.period_summary_excel_row(
                    item
                )
                for item in report.stores
            ),
            column_widths=(
                12,
                24,
                18,
                32,
                10,
                12,
                23,
                12,
                12,
                18,
                22,
                26,
                25,
                16,
                21,
                18,
                16,
                23,
                20,
                16,
                22,
                20,
            ),
        )

        details_sheet = ExcelSheetData(
            title="Щоденні дані",
            headers=(
                "Дата",
                "ТТ",
                "Статус відкриття",
                "План відкриття",
                "Фактичне відкриття",
                "Запізнення, хв",
                "Статус закриття",
                "Звіт подано",
                "Каса, грн",
                "Фото чека",
            ),
            rows=tuple(
                (
                    row.business_date,
                    row.store_code,
                    self.opening_status_text(
                        row.opening_status
                    ),
                    self.time_text(
                        row.scheduled_open_time
                    ),
                    row.actual_open_time,
                    row.opening_lateness_minutes,
                    self.closing_status_text(
                        row.closing_status
                    ),
                    (
                        row
                        .actual_closing_submitted_at
                    ),
                    row.cash_amount,
                    (
                        "Так"
                        if row.receipt_attached
                        else "Ні"
                    ),
                )
                for row in report.daily_rows
            ),
            column_widths=(
                13,
                12,
                23,
                16,
                20,
                17,
                23,
                20,
                15,
                13,
            ),
        )

        totals_sheet = (
            self.period_totals_sheet(
                report
            )
        )

        scope_name = self.scope_filename_part(
            report.scope
        )

        return ExcelReportData(
            filename=(
                f"{period_type.value}_report_"
                f"{date_from.isoformat()}_"
                f"{date_to.isoformat()}_"
                f"{scope_name}.xlsx"
            ),
            workbook_title=(
                "Звіт за період "
                f"{date_from.strftime('%d.%m.%Y')}–"
                f"{date_to.strftime('%d.%m.%Y')}"
            ),
            sheets=(
                summary_sheet,
                details_sheet,
                totals_sheet,
            ),
            metadata={
                "report_type": (
                    period_type.value
                ),
                "date_from": (
                    date_from.isoformat()
                ),
                "date_to": (
                    date_to.isoformat()
                ),
                "scope": (
                    report
                    .scope
                    .scope_type
                    .value
                ),
                "store_id": (
                    report.scope.store_id
                ),
                "bush_id": (
                    report.scope.bush_id
                ),
            },
        )

    async def prepare_weekly_excel(
        self,
        *,
        user: User,
        reference_date: date,
        store_id: int | None = None,
        bush_id: int | None = None,
        active_only: bool = True,
    ) -> ExcelReportData:
        """Готує тижневий Excel-звіт."""

        date_from, date_to = self.week_bounds(
            reference_date
        )

        return await self.prepare_period_excel(
            user=user,
            date_from=date_from,
            date_to=date_to,
            period_type=(
                ReportPeriodType.WEEKLY
            ),
            store_id=store_id,
            bush_id=bush_id,
            active_only=active_only,
        )

    async def prepare_monthly_excel(
        self,
        *,
        user: User,
        year: int,
        month: int,
        store_id: int | None = None,
        bush_id: int | None = None,
        active_only: bool = True,
    ) -> ExcelReportData:
        """Готує місячний Excel-звіт."""

        date_from, date_to = self.month_bounds(
            year=year,
            month=month,
        )

        return await self.prepare_period_excel(
            user=user,
            date_from=date_from,
            date_to=date_to,
            period_type=(
                ReportPeriodType.MONTHLY
            ),
            store_id=store_id,
            bush_id=bush_id,
            active_only=active_only,
        )

    # ==========================================
    # ДОСТУП ДО ЕКСПОРТУ
    # ==========================================

    async def ensure_export_access(
        self,
        *,
        user: User,
        store_id: int | None,
        bush_id: int | None,
    ) -> None:
        """Перевіряє право створення Excel."""

        if (
            store_id is not None
            and bush_id is not None
        ):
            raise ValueError(
                "Не можна одночасно вказувати "
                "store_id і bush_id."
            )

        if store_id is not None:
            decision = (
                await self.access
                .can_manage_store(
                    user,
                    store_id,
                )
            )

            decision.raise_if_denied()
            return

        if bush_id is not None:
            decision = (
                await self.access
                .can_export_bush_reports(
                    user,
                    bush_id,
                )
            )

            decision.raise_if_denied()
            return

        decision = self.access.can_view_network(
            user
        )

        decision.raise_if_denied()

    # ==========================================
    # EXCEL-РЯДКИ
    # ==========================================

    def daily_excel_row(
        self,
        row: StoreDailyReportRow,
    ) -> tuple[Any, ...]:
        """Формує рядок денного Excel."""

        return (
            row.business_date,
            row.store_code,
            row.store_name,
            row.city or "",
            row.address or "",
            row.bush_id,
            row.cluster_id,
            self.opening_status_text(
                row.opening_status
            ),
            self.time_text(
                row.scheduled_open_time
            ),
            self.time_text(
                row.opening_control_deadline
            ),
            row.actual_open_time,
            row.opening_lateness_minutes,
            self.closing_status_text(
                row.closing_status
            ),
            self.time_text(
                row.scheduled_close_time
            ),
            self.time_text(
                row.closing_control_deadline
            ),
            row.actual_closing_submitted_at,
            row.cash_amount,
            (
                "Так"
                if row.receipt_attached
                else "Ні"
            ),
        )

    def period_summary_excel_row(
        self,
        item: StorePeriodSummary,
    ) -> tuple[Any, ...]:
        """Формує рядок підсумку ТТ."""

        return (
            item.store_code,
            item.store_name,
            item.city or "",
            item.address or "",
            item.bush_id,
            item.cluster_id,

            item.opening_expected_days,
            item.opened_days,
            item.opened_on_time_days,
            item.opened_late_days,
            item.opening_missed_days,

            item.total_lateness_minutes,
            item.average_lateness_minutes,
            item.opening_completion_percent,

            item.closing_expected_days,
            item.closing_submitted_days,
            item.closing_on_time_days,
            item.closing_late_days,
            item.closing_missed_days,
            item.closing_completion_percent,

            item.total_cash,
            item.average_cash,
        )

    def daily_totals_sheet(
        self,
        report: DailyReportResult,
    ) -> ExcelSheetData:
        """Формує аркуш підсумків дня."""

        totals = report.totals

        rows = (
            (
                "Дата",
                report.business_date,
            ),
            (
                "Кількість ТТ",
                totals.store_count,
            ),
            (
                "Очікувалось відкриттів",
                totals.opening_expected_count,
            ),
            (
                "Відкрито",
                totals.opened_count,
            ),
            (
                "Відкрито вчасно",
                totals.opened_on_time_count,
            ),
            (
                "Відкрито із запізненням",
                totals.opened_late_count,
            ),
            (
                "Пропущено дедлайнів відкриття",
                totals.opening_missed_count,
            ),
            (
                "Загальне запізнення, хв",
                totals.total_lateness_minutes,
            ),
            (
                "Середнє запізнення, хв",
                totals.average_lateness_minutes,
            ),
            (
                "Очікувалось звітів закриття",
                totals.closing_expected_count,
            ),
            (
                "Подано звітів",
                totals.closing_submitted_count,
            ),
            (
                "Звіти із запізненням",
                totals.closing_late_count,
            ),
            (
                "Не подано звітів",
                totals.closing_missed_count,
            ),
            (
                "Загальна каса",
                totals.total_cash,
            ),
            (
                "Середня каса",
                totals.average_cash,
            ),
        )

        return ExcelSheetData(
            title="Підсумок",
            headers=(
                "Показник",
                "Значення",
            ),
            rows=rows,
            column_widths=(
                42,
                22,
            ),
        )

    def period_totals_sheet(
        self,
        report: PeriodReportResult,
    ) -> ExcelSheetData:
        """Формує аркуш підсумків періоду."""

        totals = report.totals

        rows = (
            (
                "Початок періоду",
                report.date_from,
            ),
            (
                "Кінець періоду",
                report.date_to,
            ),
            (
                "Календарних днів",
                totals.calendar_days,
            ),
            (
                "Кількість ТТ",
                totals.store_count,
            ),
            (
                "Очікувалось відкриттів",
                totals.opening_expected_count,
            ),
            (
                "Відкрито",
                totals.opened_count,
            ),
            (
                "Відкрито вчасно",
                totals.opened_on_time_count,
            ),
            (
                "Відкрито із запізненням",
                totals.opened_late_count,
            ),
            (
                "Пропущено дедлайнів відкриття",
                totals.opening_missed_count,
            ),
            (
                "Загальне запізнення, хв",
                totals.total_lateness_minutes,
            ),
            (
                "Середнє запізнення, хв",
                totals.average_lateness_minutes,
            ),
            (
                "Очікувалось звітів закриття",
                totals.closing_expected_count,
            ),
            (
                "Подано звітів",
                totals.closing_submitted_count,
            ),
            (
                "Звіти вчасно",
                totals.closing_on_time_count,
            ),
            (
                "Звіти із запізненням",
                totals.closing_late_count,
            ),
            (
                "Не подано звітів",
                totals.closing_missed_count,
            ),
            (
                "Загальна каса",
                totals.total_cash,
            ),
            (
                "Середня каса",
                totals.average_cash,
            ),
        )

        return ExcelSheetData(
            title="Загальний підсумок",
            headers=(
                "Показник",
                "Значення",
            ),
            rows=rows,
            column_widths=(
                42,
                22,
            ),
        )

    # ==========================================
    # TELEGRAM-ФОРМАТУВАННЯ
    # ==========================================

    @classmethod
    def format_daily_report(
        cls,
        report: DailyReportResult,
    ) -> str:
        """Формує короткий денний звіт."""

        totals = report.totals

        lines = [
            "📊 <b>Денний звіт</b>",
            (
                "📅 "
                f"{report.business_date.strftime('%d.%m.%Y')}"
            ),
            "",
            "🌅 <b>Відкриття</b>",
            (
                "Очікувалось: "
                f"<b>{totals.opening_expected_count}</b>"
            ),
            (
                "Відкрито: "
                f"<b>{totals.opened_count}</b>"
            ),
            (
                "Із запізненням: "
                f"<b>{totals.opened_late_count}</b>"
            ),
            (
                "Пропущено дедлайнів: "
                f"<b>{totals.opening_missed_count}</b>"
            ),
            (
                "Загальне запізнення: "
                f"<b>{totals.total_lateness_minutes} хв</b>"
            ),
            "",
            "🌙 <b>Закриття</b>",
            (
                "Очікувалось звітів: "
                f"<b>{totals.closing_expected_count}</b>"
            ),
            (
                "Подано: "
                f"<b>{totals.closing_submitted_count}</b>"
            ),
            (
                "Із запізненням: "
                f"<b>{totals.closing_late_count}</b>"
            ),
            (
                "Не подано: "
                f"<b>{totals.closing_missed_count}</b>"
            ),
            "",
            (
                "💰 Загальна каса: "
                f"<b>{cls.format_money(totals.total_cash)}</b>"
            ),
        ]

        problem_rows = [
            row
            for row in report.rows
            if (
                row.opening_lateness_minutes > 0
                or row.opening_deadline_missed
                or row.closing_late
                or row.closing_deadline_missed
            )
        ]

        if problem_rows:
            lines.extend(
                [
                    "",
                    "⚠️ <b>Проблемні ТТ:</b>",
                ]
            )

            for row in problem_rows[:20]:
                problems: list[str] = []

                if row.opening_deadline_missed:
                    problems.append(
                        "не відкрилась до дедлайну"
                    )

                elif (
                    row.opening_lateness_minutes
                    > 0
                ):
                    problems.append(
                        "відкриття "
                        f"+{row.opening_lateness_minutes} хв"
                    )

                if row.closing_deadline_missed:
                    problems.append(
                        "не подано звіт"
                    )

                elif row.closing_late:
                    problems.append(
                        "звіт із запізненням"
                    )

                lines.append(
                    "• "
                    f"<b>{escape(row.store_code)}</b> — "
                    + ", ".join(problems)
                )

        return "\n".join(lines)

    @classmethod
    def format_period_report(
        cls,
        report: PeriodReportResult,
    ) -> str:
        """Формує короткий звіт за період."""

        totals = report.totals

        return "\n".join(
            [
                "📈 <b>Звіт за період</b>",
                (
                    "📅 "
                    f"{report.date_from.strftime('%d.%m.%Y')} — "
                    f"{report.date_to.strftime('%d.%m.%Y')}"
                ),
                "",
                (
                    "🏪 Торгових точок: "
                    f"<b>{totals.store_count}</b>"
                ),
                "",
                "🌅 <b>Відкриття</b>",
                (
                    "Очікувалось: "
                    f"<b>{totals.opening_expected_count}</b>"
                ),
                (
                    "Відкрито: "
                    f"<b>{totals.opened_count}</b>"
                ),
                (
                    "Із запізненням: "
                    f"<b>{totals.opened_late_count}</b>"
                ),
                (
                    "Пропущено дедлайнів: "
                    f"<b>{totals.opening_missed_count}</b>"
                ),
                (
                    "Загальне запізнення: "
                    f"<b>{totals.total_lateness_minutes} хв</b>"
                ),
                "",
                "🌙 <b>Закриття</b>",
                (
                    "Очікувалось звітів: "
                    f"<b>{totals.closing_expected_count}</b>"
                ),
                (
                    "Подано: "
                    f"<b>{totals.closing_submitted_count}</b>"
                ),
                (
                    "Із запізненням: "
                    f"<b>{totals.closing_late_count}</b>"
                ),
                (
                    "Не подано: "
                    f"<b>{totals.closing_missed_count}</b>"
                ),
                "",
                (
                    "💰 Загальна каса: "
                    f"<b>{cls.format_money(totals.total_cash)}</b>"
                ),
                (
                    "📊 Середня каса: "
                    f"<b>{cls.format_money(totals.average_cash)}</b>"
                ),
            ]
        )

    # ==========================================
    # ДАТИ
    # ==========================================

    @staticmethod
    def week_bounds(
        reference_date: date,
    ) -> tuple[date, date]:
        """
        Повертає понеділок і неділю
        вибраного тижня.
        """

        date_from = (
            reference_date
            - timedelta(
                days=reference_date.weekday()
            )
        )

        return (
            date_from,
            date_from + timedelta(days=6),
        )

    @staticmethod
    def month_bounds(
        *,
        year: int,
        month: int,
    ) -> tuple[date, date]:
        """
        Повертає перший та останній день місяця.
        """

        if year < 2000 or year > 2200:
            raise ValueError(
                "Рік повинен бути "
                "від 2000 до 2200."
            )

        if month < 1 or month > 12:
            raise ValueError(
                "Місяць повинен бути "
                "від 1 до 12."
            )

        date_from = date(
            year,
            month,
            1,
        )

        if month == 12:
            next_month = date(
                year + 1,
                1,
                1,
            )

        else:
            next_month = date(
                year,
                month + 1,
                1,
            )

        return (
            date_from,
            next_month - timedelta(days=1),
        )

    def validate_date_range(
        self,
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

        days_count = (
            date_to - date_from
        ).days + 1

        if days_count > self.MAX_PERIOD_DAYS:
            raise ValueError(
                "Період звіту не може перевищувати "
                f"{self.MAX_PERIOD_DAYS} днів."
            )

    # ==========================================
    # СТАТУСИ
    # ==========================================

    @staticmethod
    def enum_value(
        value: Any,
    ) -> str:
        """Повертає текст enum."""

        if isinstance(value, Enum):
            return str(
                value.value
            ).lower()

        return str(
            value
        ).strip().lower()

    @staticmethod
    def status_is_late(
        status: str,
    ) -> bool:
        """Чи означає статус запізнення."""

        normalized = status.lower()

        return (
            "late" in normalized
            or "after_alert" in normalized
        )

    @staticmethod
    def status_is_missed(
        status: str,
    ) -> bool:
        """Чи означає статус пропущений дедлайн."""

        normalized = status.lower()

        return (
            "missed" in normalized
            or "not_submitted" in normalized
            or "deadline_missed" in normalized
        )

    @staticmethod
    def opening_status_text(
        status: str,
    ) -> str:
        """Перекладає статус відкриття."""

        translations = {
            "not_recorded": "немає запису",
            "waiting": "очікується",
            "opened_early": "відкрито раніше",
            "opened_on_time": "відкрито вчасно",
            "opened_late": (
                "відкрито із запізненням"
            ),
            "opened_after_alert": (
                "відкрито після сповіщення"
            ),
            "missed_control_deadline": (
                "дедлайн пропущено"
            ),
            "manually_confirmed": (
                "підтверджено вручну"
            ),
            "not_required": (
                "контроль не потрібен"
            ),
            "day_off": "вихідний",
            "temporarily_closed": (
                "тимчасово закрито"
            ),
        }

        return translations.get(
            status.lower(),
            status,
        )

    @staticmethod
    def closing_status_text(
        status: str,
    ) -> str:
        """Перекладає статус закриття."""

        translations = {
            "not_recorded": "немає запису",
            "waiting": "очікується",
            "submitted_on_time": (
                "подано вчасно"
            ),
            "submitted_late": (
                "подано із запізненням"
            ),
            "missed_deadline": (
                "дедлайн пропущено"
            ),
            "manually_confirmed": (
                "підтверджено вручну"
            ),
            "not_required": (
                "звіт не потрібен"
            ),
            "day_off": "вихідний",
            "temporarily_closed": (
                "тимчасово закрито"
            ),
        }

        return translations.get(
            status.lower(),
            status,
        )

    # ==========================================
    # НАЗВИ ТОРГОВИХ ТОЧОК
    # ==========================================

    @staticmethod
    def store_code(
        store: Store,
    ) -> str:
        """Повертає код ТТ."""

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

        return f"ТТ-{store.id}"

    @classmethod
    def store_name(
        cls,
        store: Store,
    ) -> str:
        """Повертає назву ТТ."""

        for field_name in (
            "name",
            "title",
            "display_name",
        ):
            value = getattr(
                store,
                field_name,
                None,
            )

            if value:
                return str(value)

        return cls.store_code(store)

    @classmethod
    def store_sort_key(
        cls,
        store: Store,
    ) -> tuple[int, str, int]:
        """Стабільно сортує ТТ."""

        store_number = getattr(
            store,
            "store_number",
            None,
        )

        try:
            number = int(store_number)

        except (TypeError, ValueError):
            number = 1_000_000

        return (
            number,
            cls.store_code(store),
            store.id,
        )

    # ==========================================
    # ФОРМАТУВАННЯ ЗНАЧЕНЬ
    # ==========================================

    @staticmethod
    def optional_text(
        value: Any,
    ) -> str | None:
        """Нормалізує необов’язковий текст."""

        if value is None:
            return None

        normalized = str(value).strip()

        return normalized or None

    @staticmethod
    def decimal_value(
        value: Any,
    ) -> Decimal:
        """Безпечно перетворює суму в Decimal."""

        if value is None:
            return Decimal("0.00")

        try:
            return Decimal(
                str(value)
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

        except (
            InvalidOperation,
            ValueError,
            TypeError,
        ):
            return Decimal("0.00")

    @staticmethod
    def money(
        value: Decimal,
    ) -> Decimal:
        """Округлює грошове значення."""

        return value.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def time_text(
        value: time | None,
    ) -> str | None:
        """Форматує час HH:MM."""

        if value is None:
            return None

        return value.strftime("%H:%M")

    @staticmethod
    def format_money(
        value: Decimal,
    ) -> str:
        """Форматує гривні."""

        formatted = (
            f"{value:,.2f}"
            .replace(",", " ")
            .replace(".", ",")
        )

        return f"{formatted} грн"

    @staticmethod
    def scope_filename_part(
        scope: ReportScope,
    ) -> str:
        """Формує частину назви Excel-файлу."""

        if (
            scope.scope_type
            == ReportScopeType.STORE
        ):
            return (
                f"store_{scope.store_id}"
            )

        if (
            scope.scope_type
            == ReportScopeType.BUSH
        ):
            return (
                f"bush_{scope.bush_id}"
            )

        return "network"