from __future__ import annotations

# =========================================================
# MODULES
# =========================================================

from app.keyboards import (
    bush_admin,
    callbacks,
    common,
    director,
    invites,
    lion,
    registration,
    reports,
    root_admin,
    store,
)

# =========================================================
# CALLBACKS
# =========================================================

from app.keyboards.callbacks import (
    AdminAction,
    AdminCallback,
    AuditActionCallback,
    AuditCallback,
    BindingAction,
    BindingCallback,
    BushAction,
    BushCallback,
    BushSelectAction,
    BushSelectCallback,
    CashAction,
    CashCallback,
    ClosingAction,
    ClosingCallback,
    ClusterAction,
    ClusterCallback,
    ClusterSelectAction,
    ClusterSelectCallback,
    CommonAction,
    ConfirmAction,
    ConfirmCallback,
    GroupAction,
    GroupCallback,
    ImportAction,
    ImportCallback,
    InviteAction,
    InviteCallback,
    MainMenuAction,
    MainMenuCallback,
    OpeningAction,
    OpeningCallback,
    PaginationCallback,
    RefreshCallback,
    ReportAction,
    ReportCallback,
    ReportDateAction,
    ReportDateCallback,
    ScheduleAction,
    ScheduleCallback,
    SettingsAction,
    SettingsCallback,
    StoreAction,
    StoreCallback,
    StoreSelectAction,
    StoreSelectCallback,
    UserAction,
    UserCallback,
    UserRoleAction,
    UserRoleCallback,
    callback_length,
    ensure_callback_size,
    pack_checked,
)

# =========================================================
# COMMON
# =========================================================

from app.keyboards.common import (
    CallbackValue,
    InlineButtonSpec,
    actions_back_keyboard,
    back_button,
    back_cancel_keyboard,
    back_home_keyboard,
    back_keyboard,
    build_keyboard,
    button_from_spec,
    cancel_button,
    cancel_keyboard,
    cancel_to_home_keyboard,
    confirm_button,
    confirm_cancel_keyboard,
    confirmation_keyboard,
    dangerous_confirmation_keyboard,
    decline_button,
    empty_keyboard,
    home_button,
    home_keyboard,
    inline_button,
    paginated_items_keyboard,
    pagination_buttons,
    pagination_keyboard,
    refresh_back_keyboard,
    refresh_button,
    refresh_home_keyboard,
    refresh_keyboard,
    resolve_callback,
    single_button_keyboard,
    two_actions_keyboard,
    url_keyboard,
)

# =========================================================
# REGISTRATION
# =========================================================

from app.keyboards.registration import (
    RegistrationAction,
    RegistrationCallback,
    blocked_registration_keyboard,
    contact_request_keyboard,
    contact_retry_keyboard,
    inactive_registration_keyboard,
    invite_activated_keyboard,
    pending_registration_keyboard,
    registration_button,
    registration_cancel_keyboard,
    registration_completed_keyboard,
    registration_help_keyboard,
    registration_refresh_keyboard,
    registration_retry_cancel_keyboard,
    registration_start_keyboard,
    registration_status_keyboard,
    rejected_registration_keyboard,
    remove_registration_reply_keyboard,
)

# =========================================================
# STORE
# =========================================================

from app.keyboards.store import (
    StoreDayState,
    StoreMenuState,
    cash_confirmation_keyboard,
    cash_input_keyboard,
    closing_already_done_keyboard,
    closing_button,
    closing_confirmation_keyboard,
    closing_prepare_keyboard,
    closing_status_button,
    closing_status_keyboard,
    closing_success_keyboard,
    opening_already_done_keyboard,
    opening_button,
    opening_late_keyboard,
    opening_prepare_keyboard,
    opening_status_button,
    opening_status_keyboard,
    opening_success_keyboard,
    receipt_received_keyboard,
    receipt_request_keyboard,
    select_store_keyboard,
    store_back_keyboard,
    store_info_keyboard,
    store_main_keyboard,
    store_today_report_keyboard,
    store_unavailable_keyboard,
)

# =========================================================
# LION
# =========================================================

from app.keyboards.lion import (
    LionAction,
    LionCallback,
    LionDashboardState,
    LionStoreItem,
    LionStoreState,
    append_pagination as append_lion_pagination,
    lion_back_keyboard,
    lion_bush_keyboard,
    lion_button,
    lion_closing_keyboard,
    lion_late_keyboard,
    lion_main_keyboard,
    lion_missing_closing_keyboard,
    lion_missing_opening_keyboard,
    lion_no_stores_keyboard,
    lion_opening_keyboard,
    lion_reports_keyboard,
    lion_select_bush_keyboard,
    lion_store_keyboard,
    lion_stores_keyboard,
    store_state_icon as lion_store_state_icon,
    store_state_text as lion_store_state_text,
)

# =========================================================
# BUSH ADMIN
# =========================================================

from app.keyboards.bush_admin import (
    BushAdminAction,
    BushAdminCallback,
    BushAdminDashboardState,
    BushAdminStoreItem,
    BushAdminStoreState,
    BushAdminUserItem,
    append_pagination as append_bush_admin_pagination,
    bush_admin_back_keyboard,
    bush_admin_button,
    bush_admin_closing_control_keyboard,
    bush_admin_closing_keyboard,
    bush_admin_invites_keyboard,
    bush_admin_late_keyboard,
    bush_admin_lions_keyboard,
    bush_admin_main_keyboard,
    bush_admin_missing_closing_keyboard,
    bush_admin_missing_opening_keyboard,
    bush_admin_move_store_keyboard,
    bush_admin_no_stores_keyboard,
    bush_admin_opening_control_keyboard,
    bush_admin_opening_keyboard,
    bush_admin_reports_keyboard,
    bush_admin_schedules_keyboard,
    bush_admin_select_bush_keyboard,
    bush_admin_store_keyboard,
    bush_admin_store_schedule_keyboard,
    bush_admin_stores_keyboard,
    bush_admin_user_keyboard,
    bush_admin_users_keyboard,
    store_button_text as bush_admin_store_button_text,
    store_state_icon as bush_admin_store_state_icon,
)

# =========================================================
# DIRECTOR
# =========================================================

from app.keyboards.director import (
    DirectorAction,
    DirectorBushItem,
    DirectorCallback,
    DirectorDashboardState,
    DirectorStoreItem,
    DirectorStoreState,
    DirectorUserItem,
    append_pagination as append_director_pagination,
    director_back_keyboard,
    director_bush_keyboard,
    director_bushes_keyboard,
    director_button,
    director_closing_keyboard,
    director_home_keyboard,
    director_invites_keyboard,
    director_late_keyboard,
    director_main_keyboard,
    director_missing_closing_keyboard,
    director_missing_opening_keyboard,
    director_no_bushes_keyboard,
    director_no_stores_keyboard,
    director_opening_keyboard,
    director_reports_keyboard,
    director_store_keyboard,
    director_stores_keyboard,
    director_user_keyboard,
    director_users_keyboard,
    store_button_text as director_store_button_text,
    store_state_icon as director_store_state_icon,
)

# =========================================================
# ROOT ADMIN
# =========================================================

from app.keyboards.root_admin import (
    RootAdminAction,
    RootAdminCallback,
    RootAdminDashboardState,
    RootBushItem,
    RootClusterItem,
    RootStoreItem,
    RootStoreState,
    RootUserItem,
    append_root_pagination,
    root_admin_audit_keyboard,
    root_admin_back_keyboard,
    root_admin_bush_keyboard,
    root_admin_bushes_keyboard,
    root_admin_button,
    root_admin_closing_keyboard,
    root_admin_cluster_keyboard,
    root_admin_clusters_keyboard,
    root_admin_groups_keyboard,
    root_admin_home_keyboard,
    root_admin_import_keyboard,
    root_admin_import_preview_keyboard,
    root_admin_invites_keyboard,
    root_admin_late_keyboard,
    root_admin_main_keyboard,
    root_admin_missing_closing_keyboard,
    root_admin_missing_opening_keyboard,
    root_admin_network_group_keyboard,
    root_admin_opening_keyboard,
    root_admin_pending_user_keyboard,
    root_admin_pending_users_keyboard,
    root_admin_profile_keyboard,
    root_admin_reports_keyboard,
    root_admin_role_keyboard,
    root_admin_settings_keyboard,
    root_admin_store_keyboard,
    root_admin_stores_keyboard,
    root_admin_system_keyboard,
    root_admin_user_keyboard,
    root_admin_users_keyboard,
    root_store_button_text,
    root_store_state_icon,
)

# =========================================================
# REPORTS
# =========================================================

from app.keyboards.reports import (
    ReportBushItem,
    ReportPeriod,
    ReportResultState,
    ReportScope,
    ReportStoreItem,
    ReportStoreResultItem,
    ReportUIAction,
    ReportUICallback,
    append_report_pagination,
    custom_period_cancel_keyboard,
    direct_daily_report_keyboard,
    empty_report_keyboard,
    network_report_period_keyboard,
    normalize_scope,
    report_bush_selector_keyboard,
    report_cash_keyboard,
    report_closing_keyboard,
    report_error_keyboard,
    report_excel_keyboard,
    report_excel_ready_keyboard,
    report_late_keyboard,
    report_opening_keyboard,
    report_period_keyboard,
    report_result_keyboard,
    report_store_details_keyboard,
    report_store_selector_keyboard,
    report_ui_button,
    reports_back_keyboard,
    reports_home_keyboard,
    reports_main_keyboard,
    store_report_card_keyboard,
)

# =========================================================
# INVITES
# =========================================================

from app.keyboards.invites import (
    InviteBushItem,
    InviteCreateState,
    InviteExpiration,
    InviteListItem,
    InviteStatus,
    InviteStoreItem,
    InviteType,
    InviteUIAction,
    InviteUICallback,
    active_invites_keyboard,
    append_invite_pagination,
    bush_invite_create_keyboard,
    created_invite_keyboard,
    director_invite_create_keyboard,
    invite_activation_error_keyboard,
    invite_activation_success_keyboard,
    invite_card_keyboard,
    invite_create_cancel_keyboard,
    invite_expiration_keyboard,
    invite_expired_keyboard,
    invite_no_access_keyboard,
    invite_revoked_keyboard,
    invite_store_selector_keyboard,
    invite_bush_selector_keyboard,
    invite_ui_button,
    invite_used_keyboard,
    invites_back_keyboard,
    invites_main_keyboard,
    revoke_invite_confirmation_keyboard,
    store_invite_create_keyboard,
)


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    # -----------------------------------------------------
    # MODULES
    # -----------------------------------------------------

    "callbacks",
    "common",
    "registration",
    "store",
    "lion",
    "bush_admin",
    "director",
    "root_admin",
    "reports",
    "invites",

    # -----------------------------------------------------
    # CALLBACKS
    # -----------------------------------------------------

    "CommonAction",

    "MainMenuAction",
    "MainMenuCallback",

    "PaginationCallback",

    "OpeningAction",
    "OpeningCallback",

    "ClosingAction",
    "ClosingCallback",

    "CashAction",
    "CashCallback",

    "StoreAction",
    "StoreCallback",
    "StoreSelectAction",
    "StoreSelectCallback",

    "BushAction",
    "BushCallback",
    "BushSelectAction",
    "BushSelectCallback",

    "ClusterAction",
    "ClusterCallback",
    "ClusterSelectAction",
    "ClusterSelectCallback",

    "UserAction",
    "UserCallback",

    "UserRoleAction",
    "UserRoleCallback",

    "BindingAction",
    "BindingCallback",

    "ReportAction",
    "ReportCallback",

    "ReportDateAction",
    "ReportDateCallback",

    "ScheduleAction",
    "ScheduleCallback",

    "ImportAction",
    "ImportCallback",

    "SettingsAction",
    "SettingsCallback",

    "GroupAction",
    "GroupCallback",

    "InviteAction",
    "InviteCallback",

    "AuditActionCallback",
    "AuditCallback",

    "AdminAction",
    "AdminCallback",

    "ConfirmAction",
    "ConfirmCallback",

    "RefreshCallback",

    "callback_length",
    "ensure_callback_size",
    "pack_checked",

    # -----------------------------------------------------
    # COMMON
    # -----------------------------------------------------

    "CallbackValue",
    "InlineButtonSpec",

    "resolve_callback",

    "inline_button",
    "button_from_spec",

    "build_keyboard",
    "empty_keyboard",
    "single_button_keyboard",

    "home_button",
    "home_keyboard",

    "back_button",
    "back_keyboard",

    "cancel_button",
    "cancel_keyboard",

    "back_home_keyboard",
    "back_cancel_keyboard",

    "refresh_button",
    "refresh_keyboard",
    "refresh_back_keyboard",
    "refresh_home_keyboard",

    "confirm_button",
    "decline_button",
    "confirmation_keyboard",
    "confirm_cancel_keyboard",
    "dangerous_confirmation_keyboard",

    "pagination_buttons",
    "pagination_keyboard",
    "paginated_items_keyboard",

    "url_keyboard",

    "two_actions_keyboard",
    "actions_back_keyboard",
    "cancel_to_home_keyboard",

    # -----------------------------------------------------
    # REGISTRATION
    # -----------------------------------------------------

    "RegistrationAction",
    "RegistrationCallback",

    "registration_button",

    "registration_start_keyboard",

    "contact_request_keyboard",
    "contact_retry_keyboard",
    "remove_registration_reply_keyboard",

    "pending_registration_keyboard",
    "registration_status_keyboard",
    "rejected_registration_keyboard",
    "blocked_registration_keyboard",
    "inactive_registration_keyboard",

    "registration_cancel_keyboard",
    "registration_retry_cancel_keyboard",
    "registration_refresh_keyboard",
    "registration_help_keyboard",

    "registration_completed_keyboard",
    "invite_activated_keyboard",

    # -----------------------------------------------------
    # STORE
    # -----------------------------------------------------

    "StoreDayState",
    "StoreMenuState",

    "store_main_keyboard",

    "select_store_keyboard",

    "opening_button",
    "opening_status_button",

    "closing_button",
    "closing_status_button",

    "opening_prepare_keyboard",
    "opening_success_keyboard",
    "opening_late_keyboard",
    "opening_already_done_keyboard",
    "opening_status_keyboard",

    "closing_prepare_keyboard",
    "closing_confirmation_keyboard",
    "closing_status_keyboard",
    "closing_success_keyboard",
    "closing_already_done_keyboard",

    "cash_input_keyboard",
    "cash_confirmation_keyboard",

    "receipt_request_keyboard",
    "receipt_received_keyboard",

    "store_today_report_keyboard",
    "store_info_keyboard",
    "store_unavailable_keyboard",
    "store_back_keyboard",

    # -----------------------------------------------------
    # LION
    # -----------------------------------------------------

    "LionAction",
    "LionCallback",

    "LionStoreState",
    "LionStoreItem",
    "LionDashboardState",

    "lion_button",

    "lion_store_state_icon",
    "lion_store_state_text",

    "lion_main_keyboard",

    "lion_stores_keyboard",
    "lion_store_keyboard",

    "lion_opening_keyboard",
    "lion_late_keyboard",
    "lion_missing_opening_keyboard",

    "lion_closing_keyboard",
    "lion_missing_closing_keyboard",

    "lion_reports_keyboard",

    "lion_bush_keyboard",
    "lion_select_bush_keyboard",

    "lion_no_stores_keyboard",

    "append_lion_pagination",

    "lion_back_keyboard",

    # -----------------------------------------------------
    # BUSH ADMIN
    # -----------------------------------------------------

    "BushAdminAction",
    "BushAdminCallback",

    "BushAdminStoreState",
    "BushAdminDashboardState",
    "BushAdminStoreItem",
    "BushAdminUserItem",

    "bush_admin_button",

    "bush_admin_store_state_icon",
    "bush_admin_store_button_text",

    "bush_admin_main_keyboard",

    "bush_admin_stores_keyboard",
    "bush_admin_store_keyboard",
    "bush_admin_no_stores_keyboard",
    "bush_admin_move_store_keyboard",

    "bush_admin_opening_keyboard",
    "bush_admin_late_keyboard",
    "bush_admin_missing_opening_keyboard",
    "bush_admin_opening_control_keyboard",

    "bush_admin_closing_keyboard",
    "bush_admin_missing_closing_keyboard",
    "bush_admin_closing_control_keyboard",

    "bush_admin_users_keyboard",
    "bush_admin_lions_keyboard",
    "bush_admin_user_keyboard",

    "bush_admin_schedules_keyboard",
    "bush_admin_store_schedule_keyboard",

    "bush_admin_reports_keyboard",

    "bush_admin_invites_keyboard",

    "bush_admin_select_bush_keyboard",

    "append_bush_admin_pagination",

    "bush_admin_back_keyboard",

    # -----------------------------------------------------
    # DIRECTOR
    # -----------------------------------------------------

    "DirectorAction",
    "DirectorCallback",

    "DirectorStoreState",
    "DirectorDashboardState",
    "DirectorBushItem",
    "DirectorStoreItem",
    "DirectorUserItem",

    "director_button",

    "director_store_state_icon",
    "director_store_button_text",

    "director_main_keyboard",

    "director_bushes_keyboard",
    "director_bush_keyboard",
    "director_no_bushes_keyboard",

    "director_stores_keyboard",
    "director_store_keyboard",
    "director_no_stores_keyboard",

    "director_opening_keyboard",
    "director_late_keyboard",
    "director_missing_opening_keyboard",

    "director_closing_keyboard",
    "director_missing_closing_keyboard",

    "director_users_keyboard",
    "director_user_keyboard",

    "director_reports_keyboard",

    "director_invites_keyboard",

    "append_director_pagination",

    "director_back_keyboard",
    "director_home_keyboard",

    # -----------------------------------------------------
    # ROOT ADMIN
    # -----------------------------------------------------

    "RootAdminAction",
    "RootAdminCallback",

    "RootStoreState",
    "RootAdminDashboardState",
    "RootStoreItem",
    "RootBushItem",
    "RootClusterItem",
    "RootUserItem",

    "root_admin_button",

    "root_store_state_icon",
    "root_store_button_text",

    "root_admin_main_keyboard",

    "root_admin_stores_keyboard",
    "root_admin_store_keyboard",

    "root_admin_bushes_keyboard",
    "root_admin_bush_keyboard",

    "root_admin_clusters_keyboard",
    "root_admin_cluster_keyboard",

    "root_admin_users_keyboard",
    "root_admin_pending_users_keyboard",
    "root_admin_pending_user_keyboard",
    "root_admin_user_keyboard",
    "root_admin_role_keyboard",

    "root_admin_opening_keyboard",
    "root_admin_late_keyboard",
    "root_admin_missing_opening_keyboard",

    "root_admin_closing_keyboard",
    "root_admin_missing_closing_keyboard",

    "root_admin_reports_keyboard",

    "root_admin_import_keyboard",
    "root_admin_import_preview_keyboard",

    "root_admin_invites_keyboard",

    "root_admin_settings_keyboard",
    "root_admin_system_keyboard",

    "root_admin_groups_keyboard",
    "root_admin_network_group_keyboard",

    "root_admin_audit_keyboard",

    "append_root_pagination",

    "root_admin_back_keyboard",
    "root_admin_home_keyboard",
    "root_admin_profile_keyboard",

    # -----------------------------------------------------
    # REPORTS
    # -----------------------------------------------------

    "ReportUIAction",
    "ReportUICallback",

    "ReportScope",
    "ReportPeriod",

    "ReportBushItem",
    "ReportStoreItem",
    "ReportResultState",
    "ReportStoreResultItem",

    "report_ui_button",
    "normalize_scope",

    "reports_main_keyboard",

    "report_period_keyboard",
    "network_report_period_keyboard",
    "custom_period_cancel_keyboard",

    "report_bush_selector_keyboard",
    "report_store_selector_keyboard",

    "report_result_keyboard",

    "report_store_details_keyboard",
    "report_late_keyboard",
    "report_opening_keyboard",
    "report_closing_keyboard",
    "report_cash_keyboard",

    "store_report_card_keyboard",

    "report_excel_keyboard",
    "report_excel_ready_keyboard",

    "empty_report_keyboard",
    "report_error_keyboard",

    "direct_daily_report_keyboard",

    "append_report_pagination",

    "reports_back_keyboard",
    "reports_home_keyboard",

    # -----------------------------------------------------
    # INVITES
    # -----------------------------------------------------

    "InviteUIAction",
    "InviteUICallback",

    "InviteType",
    "InviteStatus",
    "InviteExpiration",

    "InviteListItem",
    "InviteStoreItem",
    "InviteBushItem",
    "InviteCreateState",

    "invite_ui_button",

    "invites_main_keyboard",

    "invite_store_selector_keyboard",
    "invite_bush_selector_keyboard",

    "store_invite_create_keyboard",
    "bush_invite_create_keyboard",
    "director_invite_create_keyboard",

    "invite_expiration_keyboard",
    "invite_create_cancel_keyboard",

    "created_invite_keyboard",

    "active_invites_keyboard",
    "invite_card_keyboard",

    "revoke_invite_confirmation_keyboard",
    "invite_revoked_keyboard",

    "invite_used_keyboard",
    "invite_expired_keyboard",

    "invite_activation_success_keyboard",
    "invite_activation_error_keyboard",

    "invite_no_access_keyboard",

    "append_invite_pagination",

    "invites_back_keyboard",
]