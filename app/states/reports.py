from __future__ import annotations

from aiogram.fsm.state import (
    State,
    StatesGroup,
)


# =========================================================
# REPORTS
# =========================================================


class ReportStates(StatesGroup):
    """
    Основний FSM формування звітів.
    """

    # -----------------------------------------------------
    # PERIOD
    # -----------------------------------------------------

    selecting_period = State()

    selecting_date = State()

    selecting_date_from = State()

    selecting_date_to = State()


    # -----------------------------------------------------
    # SCOPE
    # -----------------------------------------------------

    selecting_scope = State()

    selecting_bush = State()

    selecting_store = State()


    # -----------------------------------------------------
    # BUILD
    # -----------------------------------------------------

    building_report = State()

    showing_report = State()


    # -----------------------------------------------------
    # EXPORT
    # -----------------------------------------------------

    selecting_export_format = State()

    generating_export = State()

    sending_export = State()


# =========================================================
# DAILY REPORT
# =========================================================


class DailyReportStates(StatesGroup):
    """
    FSM денного звіту.
    """

    selecting_date = State()

    selecting_scope = State()

    selecting_bush = State()

    selecting_store = State()

    building = State()

    showing = State()


# =========================================================
# PERIOD REPORT
# =========================================================


class PeriodReportStates(StatesGroup):
    """
    FSM звіту за довільний період.
    """

    selecting_period = State()

    selecting_date_from = State()

    selecting_date_to = State()

    selecting_scope = State()

    selecting_bush = State()

    selecting_store = State()

    building = State()

    showing = State()


# =========================================================
# EXCEL EXPORT
# =========================================================


class ReportExportStates(StatesGroup):
    """
    FSM Excel-експорту.
    """

    selecting_period = State()

    selecting_date = State()

    selecting_date_from = State()

    selecting_date_to = State()

    selecting_scope = State()

    selecting_bush = State()

    selecting_store = State()

    confirming_export = State()

    generating_file = State()

    sending_file = State()


# =========================================================
# REPORT SETTINGS
# =========================================================


class ReportSettingsStates(StatesGroup):
    """
    FSM адміністративних налаштувань звітів.
    """

    selecting_setting = State()

    waiting_value = State()

    confirming_change = State()


# =========================================================
# ALIASES
# =========================================================


ReportsStates = ReportStates

ReportState = ReportStates

ExcelReportStates = ReportExportStates


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "ReportStates",
    "DailyReportStates",
    "PeriodReportStates",
    "ReportExportStates",
    "ReportSettingsStates",

    "ReportsStates",
    "ReportState",
    "ExcelReportStates",
]