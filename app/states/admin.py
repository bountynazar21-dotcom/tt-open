from __future__ import annotations

from aiogram.fsm.state import (
    State,
    StatesGroup,
)


# =========================================================
# ADMIN
# =========================================================


class AdminStates(StatesGroup):
    """
    Загальні FSM-стани адміністративної панелі.
    """

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    waiting_search_query = State()

    waiting_user_search = State()

    waiting_store_search = State()

    waiting_bush_search = State()


    # -----------------------------------------------------
    # USER MANAGEMENT
    # -----------------------------------------------------

    waiting_user_id = State()

    waiting_user_role = State()

    waiting_user_status = State()

    waiting_user_phone = State()

    waiting_user_block_reason = State()

    waiting_user_unblock_reason = State()


    # -----------------------------------------------------
    # STORE MANAGEMENT
    # -----------------------------------------------------

    waiting_store_number = State()

    waiting_store_code = State()

    waiting_store_name = State()

    waiting_store_city = State()

    waiting_store_address = State()

    waiting_store_bush = State()

    waiting_store_cluster = State()

    waiting_store_note = State()

    waiting_store_deactivation_reason = State()

    waiting_store_activation_reason = State()


    # -----------------------------------------------------
    # BUSH MANAGEMENT
    # -----------------------------------------------------

    waiting_bush_name = State()

    waiting_bush_code = State()

    waiting_bush_topic_id = State()

    waiting_bush_note = State()

    waiting_bush_deactivation_reason = State()

    waiting_bush_activation_reason = State()


    # -----------------------------------------------------
    # CLUSTER MANAGEMENT
    # -----------------------------------------------------

    waiting_cluster_name = State()

    waiting_cluster_code = State()

    waiting_cluster_opening_time = State()

    waiting_cluster_deadline = State()

    waiting_cluster_note = State()


    # -----------------------------------------------------
    # BINDINGS
    # -----------------------------------------------------

    waiting_binding_user = State()

    waiting_binding_store = State()

    waiting_binding_bush = State()

    waiting_binding_role = State()

    waiting_unbind_confirmation = State()


    # -----------------------------------------------------
    # INVITES
    # -----------------------------------------------------

    waiting_invite_store = State()

    waiting_invite_bush = State()

    waiting_invite_role = State()

    waiting_invite_expiration = State()

    waiting_invite_max_uses = State()

    waiting_invite_note = State()

    waiting_invite_revoke_reason = State()


    # -----------------------------------------------------
    # SCHEDULE
    # -----------------------------------------------------

    waiting_schedule_store = State()

    waiting_schedule_weekday = State()

    waiting_opening_time = State()

    waiting_opening_deadline = State()

    waiting_closing_time = State()

    waiting_closing_deadline = State()

    waiting_schedule_reason = State()


    # -----------------------------------------------------
    # EXCEPTIONS
    # -----------------------------------------------------

    waiting_exception_scope = State()

    waiting_exception_store = State()

    waiting_exception_bush = State()

    waiting_exception_date = State()

    waiting_exception_type = State()

    waiting_exception_opening_time = State()

    waiting_exception_opening_deadline = State()

    waiting_exception_closing_time = State()

    waiting_exception_closing_deadline = State()

    waiting_exception_reason = State()


    # -----------------------------------------------------
    # MANUAL OPENING EDIT
    # -----------------------------------------------------

    waiting_opening_store = State()

    waiting_opening_date = State()

    waiting_opening_actual_time = State()

    waiting_opening_status = State()

    waiting_opening_edit_reason = State()


    # -----------------------------------------------------
    # MANUAL CLOSING EDIT
    # -----------------------------------------------------

    waiting_closing_store = State()

    waiting_closing_date = State()

    waiting_closing_cash = State()

    waiting_closing_receipt = State()

    waiting_closing_status = State()

    waiting_closing_edit_reason = State()


    # -----------------------------------------------------
    # CONFIRMATIONS
    # -----------------------------------------------------

    waiting_confirmation = State()

    waiting_delete_confirmation = State()

    waiting_deactivate_confirmation = State()


# =========================================================
# ROOT ADMIN
# =========================================================


class RootAdminStates(StatesGroup):
    """
    FSM-стани операцій,
    доступних ROOT_ADMIN.
    """

    waiting_import_file = State()

    waiting_import_confirmation = State()

    waiting_seed_confirmation = State()

    waiting_system_setting = State()

    waiting_system_setting_value = State()


# =========================================================
# ALIASES
# =========================================================


AdminState = AdminStates

RootStates = RootAdminStates


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "AdminStates",
    "RootAdminStates",

    "AdminState",
    "RootStates",
]