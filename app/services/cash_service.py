from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)
from enum import Enum
from html import escape
from typing import Any, TypeVar

from sqlalchemy import select

from app.database.models.closing_report import (
    ClosingReport,
)
from app.database.models.enums import (
    AuditAction,
    EntityType,
)
from app.database.models.store import Store
from app.database.models.user import User
from app.repositories import (
    AuditContext,
    Repositories,
)
from app.services.access import (
    AccessService,
)


EnumType = TypeVar(
    "EnumType",
    bound=Enum,
)


@dataclass(slots=True, frozen=True)
class CashEntryView:
    """
    Каса однієї ТТ за один день.
    """

    closing_report_id: int

    store_id: int
    store_code: str
    store_name: str

    business_date: date

    cash_amount: Decimal

    submitted_at: datetime | None
    submitted_by_id: int | None

    receipt_attached: bool

    raw_report: ClosingReport


@dataclass(slots=True, frozen=True)
class CashValidationResult:
    """
    Результат перевірки суми каси.
    """

    raw_value: Any

    normalized_amount: Decimal

    is_valid: bool
    error: str | None


@dataclass(slots=True, frozen=True)
class CashChangeResult:
    """
    Результат зміни каси.
    """

    report: ClosingReport
    view: CashEntryView

    previous_amount: Decimal
    current_amount: Decimal

    was_changed: bool

    changed_at: datetime
    changed_by_id: int

    reason: str | None


@dataclass(slots=True, frozen=True)
class CashCorrectionResult:
    """
    Результат ручного коригування каси.
    """

    report: ClosingReport

    store_id: int
    business_date: date

    previous_amount: Decimal
    corrected_amount: Decimal
    difference: Decimal

    corrected_at: datetime
    corrected_by_id: int

    reason: str


@dataclass(slots=True, frozen=True)
class CashStoreSummary:
    """
    Підсумок по одній ТТ за період.
    """

    store_id: int
    store_code: str
    store_name: str

    days_with_reports: int
    days_with_cash: int

    total_cash: Decimal
    average_cash: Decimal

    minimum_cash: Decimal
    maximum_cash: Decimal


@dataclass(slots=True, frozen=True)
class CashPeriodTotals:
    """
    Загальний підсумок каси за період.
    """

    date_from: date
    date_to: date

    store_count: int

    reports_count: int
    cash_entries_count: int

    total_cash: Decimal
    average_cash: Decimal

    minimum_cash: Decimal
    maximum_cash: Decimal


@dataclass(slots=True, frozen=True)
class CashPeriodReport:
    """
    Повний звіт каси за період.
    """

    date_from: date
    date_to: date

    totals: CashPeriodTotals

    stores: tuple[
        CashStoreSummary,
        ...,
    ]

    entries: tuple[
        CashEntryView,
        ...,
    ]


class CashService:
    """
    Сервіс роботи з касою ТТ.

    Підтримує:

    - перевірку суми;
    - запис каси в ClosingReport;
    - ручне коригування;
    - перегляд каси за день;
    - статистику по ТТ;
    - статистику по кущу;
    - статистику по мережі;
    - підготовку даних для Excel;
    - AuditLog усіх коригувань.

    Грошові значення зберігаються як Decimal.

    Рекомендований формат:

        Decimal("12500.50")
    """

    MIN_CASH_AMOUNT = Decimal("0.00")

    MAX_CASH_AMOUNT = Decimal(
        "10000000.00"
    )

    MONEY_QUANT = Decimal("0.01")

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
    # ПЕРЕВІРКА СУМИ
    # ==========================================

    def validate_cash_amount(
        self,
        value: Any,
    ) -> CashValidationResult:
        """
        Перевіряє введену суму каси.

        Підтримує:

            12500
            12500.50
            "12500,50"
            "12 500,50"
            Decimal(...)
        """

        try:
            amount = self.normalize_money(
                value
            )

        except ValueError as error:
            return CashValidationResult(
                raw_value=value,
                normalized_amount=(
                    Decimal("0.00")
                ),
                is_valid=False,
                error=str(error),
            )

        if amount < self.MIN_CASH_AMOUNT:
            return CashValidationResult(
                raw_value=value,
                normalized_amount=amount,
                is_valid=False,
                error=(
                    "Сума каси не може бути "
                    "від’ємною."
                ),
            )

        if amount > self.MAX_CASH_AMOUNT:
            return CashValidationResult(
                raw_value=value,
                normalized_amount=amount,
                is_valid=False,
                error=(
                    "Сума каси перевищує "
                    "допустимий ліміт."
                ),
            )

        return CashValidationResult(
            raw_value=value,
            normalized_amount=amount,
            is_valid=True,
            error=None,
        )

    # ==========================================
    # КАСА ЗА ЗВІТОМ
    # ==========================================

    async def get_cash_entry(
        self,
        *,
        user: User,
        store_id: int,
        business_date: date,
    ) -> CashEntryView | None:
        """
        Повертає касу ТТ за день.
        """

        await self.access.require_store_view(
            user,
            store_id,
        )

        report = await self.get_closing_report(
            store_id=store_id,
            business_date=business_date,
        )

        if report is None:
            return None

        store = await self.get_store_or_raise(
            store_id,
            include_inactive=True,
        )

        return self.build_cash_view(
            report=report,
            store=store,
        )

    # ==========================================
    # ЗАПИС КАСИ
    # ==========================================

    async def set_cash_amount(
        self,
        *,
        user: User,
        closing_report_id: int,
        cash_amount: Any,
        changed_at: datetime | None = None,
    ) -> CashChangeResult:
        """
        Записує касу в існуючий ClosingReport.

        Використовується під час стандартного
        сценарію закриття ТТ.
        """

        now = changed_at or datetime.now(
            UTC
        )

        self.validate_aware_datetime(
            now,
            field_name="changed_at",
        )

        validation = (
            self.validate_cash_amount(
                cash_amount
            )
        )

        if not validation.is_valid:
            raise ValueError(
                validation.error
                or "Некоректна сума каси."
            )

        report = (
            await self.get_report_or_raise(
                closing_report_id,
                for_update=True,
            )
        )

        await self.access.require_store_view(
            user,
            report.store_id,
        )

        previous_amount = (
            self.report_cash_amount(
                report
            )
        )

        current_amount = (
            validation.normalized_amount
        )

        was_changed = (
            previous_amount
            != current_amount
        )

        if was_changed:
            self.set_report_cash_amount(
                report,
                current_amount,
            )

            self.set_first_existing_attribute(
                report,
                now,
                "cash_updated_at",
                "updated_at",
                "modified_at",
            )

            self.set_first_existing_attribute(
                report,
                user.id,
                "cash_updated_by_id",
                "updated_by_id",
                "modified_by_id",
            )

            self.session.add(
                report
            )

            await self.session.flush()

        store = await self.get_store_or_raise(
            report.store_id,
            include_inactive=True,
        )

        return CashChangeResult(
            report=report,
            view=self.build_cash_view(
                report=report,
                store=store,
            ),
            previous_amount=(
                previous_amount
            ),
            current_amount=(
                current_amount
            ),
            was_changed=was_changed,
            changed_at=now,
            changed_by_id=user.id,
            reason=None,
        )

    # ==========================================
    # РУЧНЕ КОРИГУВАННЯ АДМІНОМ
    # ==========================================

    async def correct_cash(
        self,
        *,
        actor: User,
        store_id: int,
        business_date: date,
        corrected_amount: Any,
        reason: str,
        corrected_at: datetime | None = None,
    ) -> CashCorrectionResult:
        """
        Адмін вручну виправляє касу.

        Обов’язково записується AuditLog.
        """

        now = corrected_at or datetime.now(
            UTC
        )

        self.validate_aware_datetime(
            now,
            field_name="corrected_at",
        )

        normalized_reason = (
            self.normalize_required_text(
                reason,
                field_name="Причина",
                max_length=2000,
            )
        )

        validation = (
            self.validate_cash_amount(
                corrected_amount
            )
        )

        if not validation.is_valid:
            raise ValueError(
                validation.error
                or "Некоректна сума каси."
            )

        decision = (
            await self.access.can_manage_store(
                actor,
                store_id,
            )
        )

        decision.raise_if_denied()

        report = await self.get_closing_report(
            store_id=store_id,
            business_date=business_date,
            for_update=True,
        )

        if report is None:
            raise ValueError(
                "За цю дату немає "
                "звіту закриття ТТ."
            )

        previous_amount = (
            self.report_cash_amount(
                report
            )
        )

        new_amount = (
            validation.normalized_amount
        )

        difference = self.money(
            new_amount
            - previous_amount
        )

        if previous_amount != new_amount:
            self.set_report_cash_amount(
                report,
                new_amount,
            )

            self.set_first_existing_attribute(
                report,
                actor.id,
                "cash_corrected_by_id",
                "updated_by_id",
                "modified_by_id",
            )

            self.set_first_existing_attribute(
                report,
                now,
                "cash_corrected_at",
                "updated_at",
                "modified_at",
            )

            self.set_first_existing_attribute(
                report,
                normalized_reason,
                "cash_correction_reason",
                "correction_reason",
            )

            self.session.add(
                report
            )

            await self.session.flush()

            await self.log_cash_correction(
                actor=actor,
                report=report,
                reason=normalized_reason,
                previous_amount=(
                    previous_amount
                ),
                current_amount=(
                    new_amount
                ),
                difference=difference,
            )

        return CashCorrectionResult(
            report=report,
            store_id=store_id,
            business_date=business_date,
            previous_amount=(
                previous_amount
            ),
            corrected_amount=(
                new_amount
            ),
            difference=difference,
            corrected_at=now,
            corrected_by_id=actor.id,
            reason=normalized_reason,
        )

    # ==========================================
    # ЗВІТ ПО ТТ
    # ==========================================

    async def get_store_period(
        self,
        *,
        user: User,
        store_id: int,
        date_from: date,
        date_to: date,
    ) -> CashPeriodReport:
        """
        Каса однієї ТТ за період.
        """

        await self.access.require_store_view(
            user,
            store_id,
        )

        return await self.build_period_report(
            date_from=date_from,
            date_to=date_to,
            store_id=store_id,
            bush_id=None,
        )

    # ==========================================
    # ЗВІТ ПО КУЩУ
    # ==========================================

    async def get_bush_period(
        self,
        *,
        user: User,
        bush_id: int,
        date_from: date,
        date_to: date,
    ) -> CashPeriodReport:
        """
        Каса всіх ТТ куща.
        """

        await self.access.require_bush_view(
            user,
            bush_id,
        )

        return await self.build_period_report(
            date_from=date_from,
            date_to=date_to,
            store_id=None,
            bush_id=bush_id,
        )

    # ==========================================
    # ЗВІТ ПО МЕРЕЖІ
    # ==========================================

    async def get_network_period(
        self,
        *,
        user: User,
        date_from: date,
        date_to: date,
    ) -> CashPeriodReport:
        """
        Каса всієї мережі.
        """

        self.access.require_network_view(
            user
        )

        return await self.build_period_report(
            date_from=date_from,
            date_to=date_to,
            store_id=None,
            bush_id=None,
        )

    # ==========================================
    # ПОБУДОВА ЗВІТУ
    # ==========================================

    async def build_period_report(
        self,
        *,
        date_from: date,
        date_to: date,
        store_id: int | None,
        bush_id: int | None,
    ) -> CashPeriodReport:
        """
        Формує звіт каси за період.
        """

        self.validate_date_range(
            date_from=date_from,
            date_to=date_to,
        )

        stores = await self.load_stores(
            store_id=store_id,
            bush_id=bush_id,
        )

        if not stores:
            return CashPeriodReport(
                date_from=date_from,
                date_to=date_to,
                totals=CashPeriodTotals(
                    date_from=date_from,
                    date_to=date_to,
                    store_count=0,
                    reports_count=0,
                    cash_entries_count=0,
                    total_cash=(
                        Decimal("0.00")
                    ),
                    average_cash=(
                        Decimal("0.00")
                    ),
                    minimum_cash=(
                        Decimal("0.00")
                    ),
                    maximum_cash=(
                        Decimal("0.00")
                    ),
                ),
                stores=(),
                entries=(),
            )

        store_map = {
            store.id: store
            for store in stores
        }

        store_ids = set(
            store_map
        )

        statement = (
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
            .order_by(
                ClosingReport.business_date.asc(),
                ClosingReport.store_id.asc(),
            )
        )

        result = await self.session.scalars(
            statement
        )

        reports = list(
            result.unique().all()
        )

        entries: list[
            CashEntryView
        ] = []

        for report in reports:
            store = store_map.get(
                report.store_id
            )

            if store is None:
                continue

            entries.append(
                self.build_cash_view(
                    report=report,
                    store=store,
                )
            )

        summaries = (
            self.build_store_summaries(
                stores=stores,
                entries=entries,
            )
        )

        totals = self.build_totals(
            date_from=date_from,
            date_to=date_to,
            summaries=summaries,
            reports_count=len(reports),
            entries=entries,
        )

        return CashPeriodReport(
            date_from=date_from,
            date_to=date_to,
            totals=totals,
            stores=tuple(
                summaries
            ),
            entries=tuple(
                entries
            ),
        )

    # ==========================================
    # ПІДСУМКИ ПО ТТ
    # ==========================================

    def build_store_summaries(
        self,
        *,
        stores: list[Store],
        entries: list[CashEntryView],
    ) -> list[CashStoreSummary]:
        """
        Рахує підсумок кожної ТТ.
        """

        entries_by_store: dict[
            int,
            list[CashEntryView],
        ] = {}

        for entry in entries:
            entries_by_store.setdefault(
                entry.store_id,
                [],
            ).append(entry)

        result: list[
            CashStoreSummary
        ] = []

        for store in stores:
            store_entries = (
                entries_by_store.get(
                    store.id,
                    [],
                )
            )

            cash_values = [
                entry.cash_amount
                for entry in store_entries
            ]

            total_cash = sum(
                cash_values,
                Decimal("0.00"),
            )

            if cash_values:
                average_cash = (
                    total_cash
                    / len(cash_values)
                )

                minimum_cash = min(
                    cash_values
                )

                maximum_cash = max(
                    cash_values
                )

            else:
                average_cash = (
                    Decimal("0.00")
                )

                minimum_cash = (
                    Decimal("0.00")
                )

                maximum_cash = (
                    Decimal("0.00")
                )

            result.append(
                CashStoreSummary(
                    store_id=store.id,
                    store_code=(
                        self.store_code(
                            store
                        )
                    ),
                    store_name=(
                        self.store_name(
                            store
                        )
                    ),
                    days_with_reports=len(
                        store_entries
                    ),
                    days_with_cash=sum(
                        entry.cash_amount
                        >= Decimal("0.00")
                        for entry
                        in store_entries
                    ),
                    total_cash=self.money(
                        total_cash
                    ),
                    average_cash=self.money(
                        average_cash
                    ),
                    minimum_cash=self.money(
                        minimum_cash
                    ),
                    maximum_cash=self.money(
                        maximum_cash
                    ),
                )
            )

        return result

    # ==========================================
    # ЗАГАЛЬНИЙ ПІДСУМОК
    # ==========================================

    def build_totals(
        self,
        *,
        date_from: date,
        date_to: date,
        summaries: list[
            CashStoreSummary
        ],
        reports_count: int,
        entries: list[CashEntryView],
    ) -> CashPeriodTotals:
        """
        Рахує загальний підсумок.
        """

        values = [
            entry.cash_amount
            for entry in entries
        ]

        total_cash = sum(
            values,
            Decimal("0.00"),
        )

        if values:
            average_cash = (
                total_cash
                / len(values)
            )

            minimum_cash = min(
                values
            )

            maximum_cash = max(
                values
            )

        else:
            average_cash = (
                Decimal("0.00")
            )

            minimum_cash = (
                Decimal("0.00")
            )

            maximum_cash = (
                Decimal("0.00")
            )

        return CashPeriodTotals(
            date_from=date_from,
            date_to=date_to,
            store_count=len(
                summaries
            ),
            reports_count=(
                reports_count
            ),
            cash_entries_count=len(
                values
            ),
            total_cash=self.money(
                total_cash
            ),
            average_cash=self.money(
                average_cash
            ),
            minimum_cash=self.money(
                minimum_cash
            ),
            maximum_cash=self.money(
                maximum_cash
            ),
        )

    # ==========================================
    # EXCEL ROWS
    # ==========================================

    @staticmethod
    def prepare_excel_rows(
        report: CashPeriodReport,
    ) -> tuple[
        tuple[Any, ...],
        ...,
    ]:
        """
        Готує рядки для ExcelService.
        """

        return tuple(
            (
                entry.business_date,
                entry.store_code,
                entry.store_name,
                entry.cash_amount,
                entry.receipt_attached,
                entry.submitted_at,
                entry.submitted_by_id,
            )
            for entry in report.entries
        )

    @staticmethod
    def prepare_excel_summary_rows(
        report: CashPeriodReport,
    ) -> tuple[
        tuple[Any, ...],
        ...,
    ]:
        """
        Готує підсумок ТТ для Excel.
        """

        return tuple(
            (
                item.store_code,
                item.store_name,
                item.days_with_reports,
                item.days_with_cash,
                item.total_cash,
                item.average_cash,
                item.minimum_cash,
                item.maximum_cash,
            )
            for item in report.stores
        )

    # ==========================================
    # CLOSING REPORT
    # ==========================================

    async def get_closing_report(
        self,
        *,
        store_id: int,
        business_date: date,
        for_update: bool = False,
    ) -> ClosingReport | None:
        """
        Повертає ClosingReport ТТ за день.
        """

        statement = (
            select(ClosingReport)
            .where(
                ClosingReport.store_id
                == store_id,
                ClosingReport.business_date
                == business_date,
            )
            .limit(1)
        )

        if for_update:
            statement = (
                statement.with_for_update()
            )

        return await self.session.scalar(
            statement
        )

    async def get_report_or_raise(
        self,
        report_id: int,
        *,
        for_update: bool = False,
    ) -> ClosingReport:
        """
        Повертає ClosingReport за ID.
        """

        if report_id <= 0:
            raise ValueError(
                "ID звіту повинен бути "
                "більшим за нуль."
            )

        statement = (
            select(ClosingReport)
            .where(
                ClosingReport.id
                == report_id
            )
        )

        if for_update:
            statement = (
                statement.with_for_update()
            )

        report = (
            await self.session.scalar(
                statement
            )
        )

        if report is None:
            raise ValueError(
                "Звіт закриття не знайдено."
            )

        return report

    # ==========================================
    # STORES
    # ==========================================

    async def load_stores(
        self,
        *,
        store_id: int | None,
        bush_id: int | None,
    ) -> list[Store]:
        """
        Завантажує ТТ для звіту.
        """

        if (
            store_id is not None
            and bush_id is not None
        ):
            raise ValueError(
                "Не можна одночасно "
                "вказувати store_id "
                "і bush_id."
            )

        conditions: list[Any] = []

        if store_id is not None:
            conditions.append(
                Store.id == store_id
            )

        if bush_id is not None:
            conditions.append(
                Store.bush_id == bush_id
            )

        statement = (
            select(Store)
            .where(*conditions)
            .order_by(
                *self.store_order_columns()
            )
        )

        result = (
            await self.session.scalars(
                statement
            )
        )

        return list(
            result.unique().all()
        )

    async def get_store_or_raise(
        self,
        store_id: int,
        *,
        include_inactive: bool = False,
    ) -> Store:
        """
        Повертає ТТ.
        """

        if store_id <= 0:
            raise ValueError(
                "ID ТТ повинен бути "
                "більшим за нуль."
            )

        store = await self.session.get(
            Store,
            store_id,
        )

        if store is None:
            raise ValueError(
                "Торгову точку не знайдено."
            )

        if (
            not include_inactive
            and not bool(
                getattr(
                    store,
                    "is_active",
                    True,
                )
            )
        ):
            raise ValueError(
                "Торгова точка неактивна."
            )

        return store

    # ==========================================
    # CASH VIEW
    # ==========================================

    def build_cash_view(
        self,
        *,
        report: ClosingReport,
        store: Store,
    ) -> CashEntryView:
        """
        Формує CashEntryView.
        """

        return CashEntryView(
            closing_report_id=(
                report.id
            ),

            store_id=store.id,

            store_code=self.store_code(
                store
            ),

            store_name=self.store_name(
                store
            ),

            business_date=(
                report.business_date
            ),

            cash_amount=(
                self.report_cash_amount(
                    report
                )
            ),

            submitted_at=(
                self.get_datetime_attribute(
                    report,
                    "actual_submitted_at",
                    "submitted_at",
                    "created_at",
                )
            ),

            submitted_by_id=(
                self.get_int_attribute(
                    report,
                    "submitted_by_id",
                    "user_id",
                    "created_by_id",
                )
            ),

            receipt_attached=bool(
                self.get_attribute(
                    report,
                    "receipt_file_id",
                    "receipt_file_unique_id",
                    "receipt_path",
                    default=None,
                )
                or self.get_attribute(
                    report,
                    "has_receipt",
                    default=False,
                )
            ),

            raw_report=report,
        )

    # ==========================================
    # CASH FIELD
    # ==========================================

    @classmethod
    def report_cash_amount(
        cls,
        report: ClosingReport,
    ) -> Decimal:
        """
        Повертає суму каси зі звіту.
        """

        value = cls.get_attribute(
            report,
            "cash_amount",
            "cash_total",
            "cash",
            default=Decimal("0.00"),
        )

        try:
            return cls.normalize_money(
                value
            )

        except ValueError:
            return Decimal("0.00")

    @staticmethod
    def set_report_cash_amount(
        report: ClosingReport,
        amount: Decimal,
    ) -> None:
        """
        Записує суму каси в модель.
        """

        for field_name in (
            "cash_amount",
            "cash_total",
            "cash",
        ):
            if hasattr(
                report,
                field_name,
            ):
                setattr(
                    report,
                    field_name,
                    amount,
                )

                return

        raise AttributeError(
            "У ClosingReport відсутнє "
            "поле для суми каси."
        )

    # ==========================================
    # AUDIT
    # ==========================================

    async def log_cash_correction(
        self,
        *,
        actor: User,
        report: ClosingReport,
        reason: str,
        previous_amount: Decimal,
        current_amount: Decimal,
        difference: Decimal,
    ) -> None:
        """
        Записує коригування каси в AuditLog.
        """

        action = (
            self.resolve_audit_action(
                "update",
                "changed",
                "correction",
            )
        )

        entity_type = (
            self.resolve_entity_type(
                "closing_report",
                "closing",
                "report",
            )
        )

        await self.repositories.audit.log_action(
            action=action,

            entity_type=entity_type,

            entity_id=report.id,

            context=AuditContext(
                actor_user_id=actor.id,

                reason=reason,

                description=(
                    "Виконано ручне "
                    "коригування каси"
                ),

                source="telegram_bot",
            ),

            old_values={
                "store_id": (
                    report.store_id
                ),

                "business_date": (
                    report.business_date
                    .isoformat()
                ),

                "cash_amount": str(
                    previous_amount
                ),
            },

            new_values={
                "store_id": (
                    report.store_id
                ),

                "business_date": (
                    report.business_date
                    .isoformat()
                ),

                "cash_amount": str(
                    current_amount
                ),

                "difference": str(
                    difference
                ),
            },
        )

    # ==========================================
    # MONEY
    # ==========================================

    @classmethod
    def normalize_money(
        cls,
        value: Any,
    ) -> Decimal:
        """
        Нормалізує грошове значення.
        """

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "Некоректна сума каси."
            )

        if value is None:
            raise ValueError(
                "Вкажіть суму каси."
            )

        if isinstance(
            value,
            Decimal,
        ):
            amount = value

        elif isinstance(
            value,
            (int, float),
        ):
            amount = Decimal(
                str(value)
            )

        else:
            normalized = (
                str(value)
                .strip()
                .replace(" ", "")
                .replace("\u00a0", "")
                .replace("грн", "")
                .replace("₴", "")
                .replace(",", ".")
            )

            if not normalized:
                raise ValueError(
                    "Вкажіть суму каси."
                )

            try:
                amount = Decimal(
                    normalized
                )

            except InvalidOperation as error:
                raise ValueError(
                    "Не вдалося розпізнати "
                    "суму каси."
                ) from error

        if not amount.is_finite():
            raise ValueError(
                "Некоректна сума каси."
            )

        return amount.quantize(
            cls.MONEY_QUANT,
            rounding=ROUND_HALF_UP,
        )

    @classmethod
    def money(
        cls,
        value: Decimal,
    ) -> Decimal:
        """
        Округлює гроші до копійок.
        """

        return value.quantize(
            cls.MONEY_QUANT,
            rounding=ROUND_HALF_UP,
        )

    # ==========================================
    # DATE RANGE
    # ==========================================

    def validate_date_range(
        self,
        *,
        date_from: date,
        date_to: date,
    ) -> None:
        """
        Перевіряє період.
        """

        if date_to < date_from:
            raise ValueError(
                "Кінцева дата не може "
                "бути раніше початкової."
            )

        days_count = (
            date_to - date_from
        ).days + 1

        if (
            days_count
            > self.MAX_PERIOD_DAYS
        ):
            raise ValueError(
                "Період не може "
                "перевищувати "
                f"{self.MAX_PERIOD_DAYS} днів."
            )

    # ==========================================
    # ENUM
    # ==========================================

    @classmethod
    def resolve_audit_action(
        cls,
        *names: str,
    ) -> AuditAction:
        """
        Повертає AuditAction.
        """

        result = (
            cls.resolve_enum_member(
                AuditAction,
                *names,
                default=None,
            )
        )

        if result is not None:
            return result

        result = (
            cls.resolve_enum_member(
                AuditAction,
                "update",
                "changed",
                default=None,
            )
        )

        if result is None:
            raise ValueError(
                "Не знайдено AuditAction."
            )

        return result

    @classmethod
    def resolve_entity_type(
        cls,
        *names: str,
    ) -> EntityType:
        """
        Повертає EntityType.
        """

        result = (
            cls.resolve_enum_member(
                EntityType,
                *names,
                default=None,
            )
        )

        if result is not None:
            return result

        result = (
            cls.resolve_enum_member(
                EntityType,
                "system",
                default=None,
            )
        )

        if result is None:
            raise ValueError(
                "Не знайдено EntityType."
            )

        return result

    @staticmethod
    def resolve_enum_member(
        enum_class: type[EnumType],
        *names: str,
        default: EnumType | None = None,
    ) -> EnumType | None:
        """
        Шукає enum за name/value.
        """

        normalized_names = {
            name.strip().lower()
            for name in names
            if name.strip()
        }

        for enum_item in enum_class:
            candidates = {
                enum_item.name.lower(),
                str(
                    enum_item.value
                ).lower(),
            }

            if candidates.intersection(
                normalized_names
            ):
                return enum_item

        return default

    # ==========================================
    # GENERIC ATTRIBUTES
    # ==========================================

    @staticmethod
    def get_attribute(
        target: Any,
        *names: str,
        default: Any = None,
    ) -> Any:
        """
        Повертає перший наявний атрибут.
        """

        if target is None:
            return default

        for name in names:
            if hasattr(
                target,
                name,
            ):
                return getattr(
                    target,
                    name,
                )

        return default

    @classmethod
    def get_int_attribute(
        cls,
        target: Any,
        *names: str,
    ) -> int | None:
        """
        Повертає int-атрибут.
        """

        value = cls.get_attribute(
            target,
            *names,
            default=None,
        )

        if value is None:
            return None

        try:
            return int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    @classmethod
    def get_datetime_attribute(
        cls,
        target: Any,
        *names: str,
    ) -> datetime | None:
        """
        Повертає datetime-атрибут.
        """

        value = cls.get_attribute(
            target,
            *names,
            default=None,
        )

        if isinstance(
            value,
            datetime,
        ):
            return value

        return None

    @staticmethod
    def set_first_existing_attribute(
        target: Any,
        value: Any,
        *names: str,
    ) -> bool:
        """
        Записує перший існуючий атрибут.
        """

        for name in names:
            if hasattr(
                target,
                name,
            ):
                setattr(
                    target,
                    name,
                    value,
                )

                return True

        return False

    # ==========================================
    # STORE HELPERS
    # ==========================================

    @staticmethod
    def store_code(
        store: Store,
    ) -> str:
        """
        Повертає код ТТ.
        """

        code = getattr(
            store,
            "code",
            None,
        )

        if code:
            return str(
                code
            )

        number = getattr(
            store,
            "store_number",
            None,
        )

        if number is not None:
            return f"SB-{number}"

        return f"ТТ-{store.id}"

    @classmethod
    def store_name(
        cls,
        store: Store,
    ) -> str:
        """
        Повертає назву ТТ.
        """

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
                return str(
                    value
                )

        return cls.store_code(
            store
        )

    @staticmethod
    def store_order_columns(
    ) -> tuple[Any, ...]:
        """
        Сортування ТТ.
        """

        number_column = getattr(
            Store,
            "store_number",
            None,
        )

        if number_column is not None:
            return (
                number_column.asc(),
                Store.id.asc(),
            )

        return (
            Store.id.asc(),
        )

    # ==========================================
    # VALIDATION
    # ==========================================

    @staticmethod
    def normalize_required_text(
        value: str,
        *,
        field_name: str,
        max_length: int,
    ) -> str:
        """
        Нормалізує обов’язковий текст.
        """

        normalized = " ".join(
            value.strip().split()
        )

        if not normalized:
            raise ValueError(
                f"{field_name} "
                "не може бути порожнім."
            )

        if len(normalized) > max_length:
            raise ValueError(
                f"{field_name} "
                "занадто довгий."
            )

        return normalized

    @staticmethod
    def validate_aware_datetime(
        value: datetime,
        *,
        field_name: str,
    ) -> None:
        """
        Перевіряє timezone.
        """

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{field_name} повинен "
                "містити часовий пояс."
            )

    # ==========================================
    # TELEGRAM FORMAT
    # ==========================================

    @classmethod
    def format_cash_entry(
        cls,
        entry: CashEntryView,
    ) -> str:
        """
        Формує касу ТТ для Telegram.
        """

        receipt = (
            "є ✅"
            if entry.receipt_attached
            else "немає ❌"
        )

        return "\n".join(
            [
                (
                    "💰 <b>Каса "
                    f"{escape(entry.store_code)}</b>"
                ),
                "",
                (
                    "📅 Дата: "
                    "<b>"
                    f"{entry.business_date.strftime('%d.%m.%Y')}"
                    "</b>"
                ),
                (
                    "💵 Сума: "
                    "<b>"
                    f"{cls.format_money(entry.cash_amount)}"
                    "</b>"
                ),
                (
                    "🧾 Фото чека: "
                    f"<b>{receipt}</b>"
                ),
            ]
        )

    @classmethod
    def format_period_report(
        cls,
        report: CashPeriodReport,
    ) -> str:
        """
        Формує підсумок каси.
        """

        totals = report.totals

        lines = [
            "💰 <b>Звіт по касі</b>",
            (
                "📅 "
                f"{report.date_from.strftime('%d.%m.%Y')} — "
                f"{report.date_to.strftime('%d.%m.%Y')}"
            ),
            "",
            (
                "🏪 ТТ: "
                f"<b>{totals.store_count}</b>"
            ),
            (
                "📄 Звітів: "
                f"<b>{totals.reports_count}</b>"
            ),
            "",
            (
                "💵 Загальна каса: "
                "<b>"
                f"{cls.format_money(totals.total_cash)}"
                "</b>"
            ),
            (
                "📊 Середня каса: "
                "<b>"
                f"{cls.format_money(totals.average_cash)}"
                "</b>"
            ),
            (
                "⬇️ Мінімальна: "
                "<b>"
                f"{cls.format_money(totals.minimum_cash)}"
                "</b>"
            ),
            (
                "⬆️ Максимальна: "
                "<b>"
                f"{cls.format_money(totals.maximum_cash)}"
                "</b>"
            ),
        ]

        return "\n".join(
            lines
        )

    @classmethod
    def format_correction(
        cls,
        result: CashCorrectionResult,
    ) -> str:
        """
        Формує повідомлення про коригування.
        """

        difference_prefix = (
            "+"
            if result.difference > 0
            else ""
        )

        return "\n".join(
            [
                "✏️ <b>Касу скориговано</b>",
                "",
                (
                    "Було: "
                    "<b>"
                    f"{cls.format_money(result.previous_amount)}"
                    "</b>"
                ),
                (
                    "Стало: "
                    "<b>"
                    f"{cls.format_money(result.corrected_amount)}"
                    "</b>"
                ),
                (
                    "Різниця: "
                    "<b>"
                    f"{difference_prefix}"
                    f"{cls.format_money(result.difference)}"
                    "</b>"
                ),
                "",
                (
                    "Причина: "
                    f"{escape(result.reason)}"
                ),
            ]
        )

    @staticmethod
    def format_money(
        value: Decimal,
    ) -> str:
        """
        Форматує суму в гривнях.
        """

        text = (
            f"{value:,.2f}"
            .replace(",", " ")
            .replace(".", ",")
        )

        return f"{text} грн"