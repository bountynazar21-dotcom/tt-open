from __future__ import annotations

from aiogram.fsm.state import (
    State,
    StatesGroup,
)


# =========================================================
# OPENING
# =========================================================


class OpeningStates(StatesGroup):
    """
    Основний FSM-сценарій відкриття ТТ.
    """

    # -----------------------------------------------------
    # STORE
    # -----------------------------------------------------

    selecting_store = State()

    confirming_store = State()


    # -----------------------------------------------------
    # OPENING CONFIRMATION
    # -----------------------------------------------------

    confirming_opening = State()

    submitting_opening = State()


    # -----------------------------------------------------
    # RESULT
    # -----------------------------------------------------

    completed = State()


# =========================================================
# MANUAL OPENING EDIT
# =========================================================


class OpeningEditStates(StatesGroup):
    """
    Ручне коригування opening-запису
    адміністратором.
    """

    selecting_store = State()

    selecting_date = State()

    selecting_record = State()

    selecting_action = State()


    # -----------------------------------------------------
    # ACTUAL OPEN TIME
    # -----------------------------------------------------

    waiting_actual_open_time = State()

    waiting_time_change_reason = State()

    confirming_time_change = State()


    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    waiting_new_status = State()

    waiting_status_change_reason = State()

    confirming_status_change = State()


    # -----------------------------------------------------
    # MANUAL CONFIRM
    # -----------------------------------------------------

    waiting_manual_open_time = State()

    waiting_manual_reason = State()

    confirming_manual_opening = State()


# =========================================================
# OPENING DEADLINE
# =========================================================


class OpeningDeadlineStates(StatesGroup):
    """
    Службові FSM-стани для роботи
    з простроченими відкриттями.
    """

    selecting_store = State()

    selecting_record = State()

    waiting_action = State()

    confirming_action = State()


# =========================================================
# OPENING REPORT
# =========================================================


class OpeningReportStates(StatesGroup):
    """
    Перегляд opening-звітів через Telegram.
    """

    selecting_period = State()

    selecting_date = State()

    selecting_scope = State()

    selecting_bush = State()

    selecting_store = State()

    showing_report = State()


# =========================================================
# ALIASES
# =========================================================


OpeningState = OpeningStates

OpeningCorrectionStates = OpeningEditStates


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "OpeningStates",
    "OpeningEditStates",
    "OpeningDeadlineStates",
    "OpeningReportStates",

    "OpeningState",
    "OpeningCorrectionStates",
]