from __future__ import annotations

from aiogram.fsm.state import (
    State,
    StatesGroup,
)


# =========================================================
# IMPORT DATA
# =========================================================


class ImportDataStates(StatesGroup):
    """
    FSM для імпорту даних через Telegram.

    Сценарій:
    файл -> перевірка -> preview -> підтвердження -> імпорт.
    """

    # -----------------------------------------------------
    # SELECT IMPORT TYPE
    # -----------------------------------------------------

    selecting_import_type = State()


    # -----------------------------------------------------
    # FILE
    # -----------------------------------------------------

    waiting_file = State()

    reading_file = State()


    # -----------------------------------------------------
    # PREVIEW
    # -----------------------------------------------------

    validating_file = State()

    showing_preview = State()

    waiting_preview_action = State()


    # -----------------------------------------------------
    # MAPPING
    # -----------------------------------------------------

    waiting_column_mapping = State()

    waiting_sheet_selection = State()


    # -----------------------------------------------------
    # SETTINGS
    # -----------------------------------------------------

    waiting_update_existing = State()

    waiting_deactivate_missing = State()

    waiting_import_options = State()


    # -----------------------------------------------------
    # CONFIRMATION
    # -----------------------------------------------------

    waiting_confirmation = State()


    # -----------------------------------------------------
    # PROCESS
    # -----------------------------------------------------

    importing = State()


    # -----------------------------------------------------
    # RESULT
    # -----------------------------------------------------

    showing_result = State()

    completed = State()


# =========================================================
# STORE IMPORT
# =========================================================


class StoreImportStates(StatesGroup):
    """
    Окремий FSM для імпорту торгових точок.
    """

    waiting_file = State()

    validating = State()

    preview = State()

    waiting_confirmation = State()

    importing = State()

    completed = State()


# =========================================================
# USER IMPORT
# =========================================================


class UserImportStates(StatesGroup):
    """
    FSM для імпорту користувачів.
    """

    waiting_file = State()

    validating = State()

    preview = State()

    waiting_confirmation = State()

    importing = State()

    completed = State()


# =========================================================
# SCHEDULE IMPORT
# =========================================================


class ScheduleImportStates(StatesGroup):
    """
    FSM для імпорту графіків ТТ.
    """

    waiting_file = State()

    validating = State()

    preview = State()

    waiting_confirmation = State()

    importing = State()

    completed = State()


# =========================================================
# BULK ACTIONS
# =========================================================


class BulkActionStates(StatesGroup):
    """
    Масові адміністративні операції.
    """

    selecting_action = State()

    waiting_file = State()

    validating = State()

    showing_preview = State()

    waiting_confirmation = State()

    processing = State()

    completed = State()


# =========================================================
# ALIASES
# =========================================================


ImportStates = ImportDataStates

StoresImportStates = StoreImportStates


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "ImportDataStates",
    "StoreImportStates",
    "UserImportStates",
    "ScheduleImportStates",
    "BulkActionStates",

    "ImportStates",
    "StoresImportStates",
]