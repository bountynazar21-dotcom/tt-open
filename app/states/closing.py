from __future__ import annotations

from aiogram.fsm.state import (
    State,
    StatesGroup,
)


# =========================================================
# CLOSING
# =========================================================


class ClosingStates(StatesGroup):
    """
    Основний FSM-сценарій закриття ТТ.
    """

    # -----------------------------------------------------
    # START / STORE
    # -----------------------------------------------------

    selecting_store = State()

    confirming_store = State()


    # -----------------------------------------------------
    # CASH
    # -----------------------------------------------------

    waiting_cash_amount = State()

    confirming_cash_amount = State()


    # -----------------------------------------------------
    # RECEIPT
    # -----------------------------------------------------

    waiting_receipt = State()

    confirming_receipt = State()


    # -----------------------------------------------------
    # FINAL CONFIRMATION
    # -----------------------------------------------------

    confirming_submission = State()

    submitting_report = State()


    # -----------------------------------------------------
    # RESULT
    # -----------------------------------------------------

    completed = State()


# =========================================================
# CLOSING EDIT
# =========================================================


class ClosingEditStates(StatesGroup):
    """
    Ручне коригування вже поданого
    вечірнього звіту.
    """

    selecting_report = State()

    selecting_action = State()


    # -----------------------------------------------------
    # CASH EDIT
    # -----------------------------------------------------

    waiting_new_cash_amount = State()

    waiting_cash_change_reason = State()

    confirming_cash_change = State()


    # -----------------------------------------------------
    # RECEIPT EDIT
    # -----------------------------------------------------

    waiting_new_receipt = State()

    waiting_receipt_change_reason = State()

    confirming_receipt_change = State()


    # -----------------------------------------------------
    # STATUS EDIT
    # -----------------------------------------------------

    waiting_new_status = State()

    waiting_status_change_reason = State()

    confirming_status_change = State()


    # -----------------------------------------------------
    # MANUAL CONFIRM
    # -----------------------------------------------------

    waiting_manual_cash_amount = State()

    waiting_manual_receipt = State()

    waiting_manual_submit_time = State()

    waiting_manual_reason = State()

    confirming_manual_submission = State()


# =========================================================
# CLOSING REPORT DELIVERY
# =========================================================


class ClosingDeliveryStates(StatesGroup):
    """
    Службові стани для повторної
    відправки closing-звіту в групу.
    """

    selecting_report = State()

    confirming_resend = State()

    resending = State()


# =========================================================
# ALIASES
# =========================================================


ClosingState = ClosingStates

ClosingCorrectionStates = ClosingEditStates


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "ClosingStates",
    "ClosingEditStates",
    "ClosingDeliveryStates",

    "ClosingState",
    "ClosingCorrectionStates",
]