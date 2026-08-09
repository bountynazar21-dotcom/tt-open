from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.services.report_service import (
    ReportPeriodType,
    ReportScopeType,
)


# =========================================================
# BASE
# =========================================================


class ReportSchemaBase(BaseModel):
    """
    Базова схема звітів.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="ignore",
    )


# =========================================================
# SCOPE
# =========================================================


class ReportScopeSchema(
    ReportSchemaBase
):
    """
    Область звіту.

    Може бути:
    - уся мережа;
    - конкретний кущ;
    - конкретна ТТ.
    """

    scope_type: ReportScopeType

    store_id: int | None = Field(
        default=None,
        gt=0,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )


# =========================================================
# PERIOD
# =========================================================


class ReportPeriodSchema(
    ReportSchemaBase
):
    """
    Період звіту.
    """

    period_type: ReportPeriodType

    date_from: date

    date_to: date

    @field_validator(
        "date_to",
    )
    @classmethod
    def validate_date_to(
        cls,
        value: date,
        info: Any,
    ) -> date:
        date_from = info.data.get(
            "date_from"
        )

        if (
            date_from is not None
            and value < date_from
        ):
            raise ValueError(
                "date_to не може бути "
                "раніше date_from."
            )

        return value


# =========================================================
# REPORT REQUEST
# =========================================================


class ReportRequest(
    ReportSchemaBase
):
    """
    Загальний запит на формування звіту.
    """

    period_type: ReportPeriodType = (
        ReportPeriodType.DAILY
    )

    scope_type: ReportScopeType = (
        ReportScopeType.NETWORK
    )

    date_from: date

    date_to: date | None = None

    store_id: int | None = Field(
        default=None,
        gt=0,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    include_inactive: bool = False

    @field_validator(
        "date_to",
    )
    @classmethod
    def validate_date_to(
        cls,
        value: date | None,
        info: Any,
    ) -> date | None:
        if value is None:
            return None

        date_from = info.data.get(
            "date_from"
        )

        if (
            date_from is not None
            and value < date_from
        ):
            raise ValueError(
                "date_to не може бути "
                "раніше date_from."
            )

        return value


# =========================================================
# DAILY STORE ROW
# =========================================================


class StoreDailyReportRowSchema(
    ReportSchemaBase
):
    """
    Дані однієї торгової точки
    за один робочий день.
    """

    business_date: date

    store_id: int = Field(
        gt=0,
    )

    store_code: str

    store_name: str

    city: str | None = None

    address: str | None = None

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    cluster_id: int | None = Field(
        default=None,
        gt=0,
    )

    # -----------------------------------------------------
    # OPENING
    # -----------------------------------------------------

    opening_checkin_id: int | None = Field(
        default=None,
        gt=0,
    )

    opening_status: str

    scheduled_open_time: time | None = None

    opening_control_deadline: time | None = None

    actual_open_time: datetime | None = None

    opening_lateness_minutes: int = Field(
        default=0,
        ge=0,
    )

    opening_deadline_missed: bool = False

    opening_submitted_by_id: int | None = Field(
        default=None,
        gt=0,
    )

    # -----------------------------------------------------
    # CLOSING
    # -----------------------------------------------------

    closing_report_id: int | None = Field(
        default=None,
        gt=0,
    )

    closing_status: str

    scheduled_close_time: time | None = None

    closing_control_deadline: time | None = None

    actual_closing_submitted_at: (
        datetime | None
    ) = None

    closing_late: bool = False

    closing_deadline_missed: bool = False

    closing_submitted_by_id: int | None = Field(
        default=None,
        gt=0,
    )

    # -----------------------------------------------------
    # CASH
    # -----------------------------------------------------

    cash_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0"),
    )

    receipt_attached: bool = False

    # -----------------------------------------------------
    # COMPUTED
    # -----------------------------------------------------

    @property
    def opening_confirmed(
        self,
    ) -> bool:
        return (
            self.actual_open_time
            is not None
        )

    @property
    def closing_confirmed(
        self,
    ) -> bool:
        return (
            self.actual_closing_submitted_at
            is not None
        )


# =========================================================
# DAILY TOTALS
# =========================================================


class DailyReportTotalsSchema(
    ReportSchemaBase
):
    """
    Загальні показники
    денного звіту.
    """

    store_count: int = Field(
        ge=0,
    )

    # Opening
    opening_expected_count: int = Field(
        ge=0,
    )

    opened_count: int = Field(
        ge=0,
    )

    opened_on_time_count: int = Field(
        ge=0,
    )

    opened_late_count: int = Field(
        ge=0,
    )

    opening_missed_count: int = Field(
        ge=0,
    )

    opening_waiting_count: int = Field(
        ge=0,
    )

    total_lateness_minutes: int = Field(
        ge=0,
    )

    average_lateness_minutes: float = Field(
        ge=0,
    )

    # Closing
    closing_expected_count: int = Field(
        ge=0,
    )

    closing_submitted_count: int = Field(
        ge=0,
    )

    closing_on_time_count: int = Field(
        ge=0,
    )

    closing_late_count: int = Field(
        ge=0,
    )

    closing_missed_count: int = Field(
        ge=0,
    )

    closing_waiting_count: int = Field(
        ge=0,
    )

    # Cash
    total_cash: Decimal = Field(
        ge=Decimal("0"),
    )

    average_cash: Decimal = Field(
        ge=Decimal("0"),
    )


# =========================================================
# DAILY REPORT
# =========================================================


class DailyReportSchema(
    ReportSchemaBase
):
    """
    Повний денний звіт.
    """

    scope: ReportScopeSchema

    business_date: date

    totals: DailyReportTotalsSchema

    rows: list[
        StoreDailyReportRowSchema
    ] = Field(
        default_factory=list,
    )


# =========================================================
# STORE PERIOD SUMMARY
# =========================================================


class StorePeriodSummarySchema(
    ReportSchemaBase
):
    """
    Підсумок однієї ТТ
    за вибраний період.
    """

    store_id: int = Field(
        gt=0,
    )

    store_code: str

    store_name: str

    city: str | None = None

    address: str | None = None

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    cluster_id: int | None = Field(
        default=None,
        gt=0,
    )

    # Opening
    opening_expected_days: int = Field(
        ge=0,
    )

    opened_days: int = Field(
        ge=0,
    )

    opened_on_time_days: int = Field(
        ge=0,
    )

    opened_late_days: int = Field(
        ge=0,
    )

    opening_missed_days: int = Field(
        ge=0,
    )

    opening_waiting_days: int = Field(
        ge=0,
    )

    total_lateness_minutes: int = Field(
        ge=0,
    )

    average_lateness_minutes: float = Field(
        ge=0,
    )

    # Closing
    closing_expected_days: int = Field(
        ge=0,
    )

    closing_submitted_days: int = Field(
        ge=0,
    )

    closing_on_time_days: int = Field(
        ge=0,
    )

    closing_late_days: int = Field(
        ge=0,
    )

    closing_missed_days: int = Field(
        ge=0,
    )

    closing_waiting_days: int = Field(
        ge=0,
    )

    # Cash
    total_cash: Decimal = Field(
        ge=Decimal("0"),
    )

    average_cash: Decimal = Field(
        ge=Decimal("0"),
    )

    # -----------------------------------------------------
    # COMPLETION %
    # -----------------------------------------------------

    @property
    def opening_completion_percent(
        self,
    ) -> float:
        if self.opening_expected_days == 0:
            return 0.0

        return round(
            (
                self.opened_days
                / self.opening_expected_days
            )
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
            (
                self.closing_submitted_days
                / self.closing_expected_days
            )
            * 100,
            2,
        )


# =========================================================
# PERIOD TOTALS
# =========================================================


class PeriodReportTotalsSchema(
    ReportSchemaBase
):
    """
    Загальні показники
    звіту за період.
    """

    store_count: int = Field(
        ge=0,
    )

    calendar_days: int = Field(
        ge=0,
    )

    # Opening
    opening_expected_count: int = Field(
        ge=0,
    )

    opened_count: int = Field(
        ge=0,
    )

    opened_on_time_count: int = Field(
        ge=0,
    )

    opened_late_count: int = Field(
        ge=0,
    )

    opening_missed_count: int = Field(
        ge=0,
    )

    opening_waiting_count: int = Field(
        ge=0,
    )

    total_lateness_minutes: int = Field(
        ge=0,
    )

    average_lateness_minutes: float = Field(
        ge=0,
    )

    # Closing
    closing_expected_count: int = Field(
        ge=0,
    )

    closing_submitted_count: int = Field(
        ge=0,
    )

    closing_on_time_count: int = Field(
        ge=0,
    )

    closing_late_count: int = Field(
        ge=0,
    )

    closing_missed_count: int = Field(
        ge=0,
    )

    closing_waiting_count: int = Field(
        ge=0,
    )

    # Cash
    total_cash: Decimal = Field(
        ge=Decimal("0"),
    )

    average_cash: Decimal = Field(
        ge=Decimal("0"),
    )


# =========================================================
# PERIOD REPORT
# =========================================================


class PeriodReportSchema(
    ReportSchemaBase
):
    """
    Повний звіт за період.
    """

    period_type: ReportPeriodType

    scope: ReportScopeSchema

    date_from: date

    date_to: date

    totals: PeriodReportTotalsSchema

    stores: list[
        StorePeriodSummarySchema
    ] = Field(
        default_factory=list,
    )

    daily_rows: list[
        StoreDailyReportRowSchema
    ] = Field(
        default_factory=list,
    )


# =========================================================
# EXCEL SHEET
# =========================================================


class ExcelSheetDataSchema(
    ReportSchemaBase
):
    """
    Дані одного Excel-аркуша.
    """

    title: str = Field(
        min_length=1,
        max_length=31,
    )

    headers: tuple[
        str,
        ...,
    ]

    rows: tuple[
        tuple[
            Any,
            ...,
        ],
        ...,
    ]

    column_widths: tuple[
        float,
        ...,
    ]

    freeze_panes: str = "A2"

    auto_filter: bool = True


# =========================================================
# EXCEL REPORT
# =========================================================


class ExcelReportDataSchema(
    ReportSchemaBase
):
    """
    Підготовлена структура
    Excel-звіту.
    """

    filename: str = Field(
        min_length=1,
        max_length=255,
    )

    workbook_title: str = Field(
        min_length=1,
        max_length=255,
    )

    sheets: tuple[
        ExcelSheetDataSchema,
        ...,
    ]

    metadata: dict[
        str,
        Any,
    ] = Field(
        default_factory=dict,
    )


# =========================================================
# TELEGRAM REPORT REQUEST
# =========================================================


class TelegramReportRequest(
    ReportSchemaBase
):
    """
    Запит на звіт із Telegram UI.
    """

    period_type: ReportPeriodType

    scope_type: ReportScopeType

    business_date: date | None = None

    date_from: date | None = None

    date_to: date | None = None

    store_id: int | None = Field(
        default=None,
        gt=0,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    export_excel: bool = False


# =========================================================
# EXPORT REQUEST
# =========================================================


class ReportExportRequest(
    ReportSchemaBase
):
    """
    Запит на створення Excel-файлу.
    """

    period_type: ReportPeriodType

    scope_type: ReportScopeType

    date_from: date

    date_to: date

    store_id: int | None = Field(
        default=None,
        gt=0,
    )

    bush_id: int | None = Field(
        default=None,
        gt=0,
    )

    @field_validator(
        "date_to",
    )
    @classmethod
    def validate_date_to(
        cls,
        value: date,
        info: Any,
    ) -> date:
        date_from = info.data.get(
            "date_from"
        )

        if (
            date_from is not None
            and value < date_from
        ):
            raise ValueError(
                "date_to не може бути "
                "раніше date_from."
            )

        return value


# =========================================================
# REPORT FILE
# =========================================================


class ReportFileSchema(
    ReportSchemaBase
):
    """
    Інформація про сформований файл.
    """

    filename: str

    content_type: str = (
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    )

    size: int | None = Field(
        default=None,
        ge=0,
    )


# =========================================================
# ALIASES
# =========================================================


ReportScope = ReportScopeSchema

DailyReport = DailyReportSchema

DailyReportTotals = (
    DailyReportTotalsSchema
)

StoreDailyReportRow = (
    StoreDailyReportRowSchema
)

StorePeriodSummary = (
    StorePeriodSummarySchema
)

PeriodReportTotals = (
    PeriodReportTotalsSchema
)

PeriodReport = PeriodReportSchema

ExcelSheetSchema = (
    ExcelSheetDataSchema
)

ExcelReportSchema = (
    ExcelReportDataSchema
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "ReportSchemaBase",

    "ReportScopeSchema",
    "ReportPeriodSchema",
    "ReportRequest",

    "StoreDailyReportRowSchema",
    "DailyReportTotalsSchema",
    "DailyReportSchema",

    "StorePeriodSummarySchema",
    "PeriodReportTotalsSchema",
    "PeriodReportSchema",

    "ExcelSheetDataSchema",
    "ExcelReportDataSchema",

    "TelegramReportRequest",
    "ReportExportRequest",
    "ReportFileSchema",

    "ReportScope",
    "DailyReport",
    "DailyReportTotals",
    "StoreDailyReportRow",
    "StorePeriodSummary",
    "PeriodReportTotals",
    "PeriodReport",
    "ExcelSheetSchema",
    "ExcelReportSchema",
]