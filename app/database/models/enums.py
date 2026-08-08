from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    ROOT_ADMIN = "root_admin"
    DIRECTOR = "director"
    BUSH_ADMIN = "bush_admin"
    LION = "lion"
    STORE_USER = "store_user"


class UserStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    INACTIVE = "inactive"


class BindingStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class StoreStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TEMPORARILY_CLOSED = "temporarily_closed"


class OpeningStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    WAITING = "waiting"
    OPENED_EARLY = "opened_early"
    OPENED_ON_TIME = "opened_on_time"
    OPENED_LATE = "opened_late"
    MISSED_CONTROL_DEADLINE = "missed_control_deadline"
    OPENED_AFTER_ALERT = "opened_after_alert"
    MANUALLY_CONFIRMED = "manually_confirmed"
    DAY_OFF = "day_off"
    TEMPORARILY_CLOSED = "temporarily_closed"


class ClosingStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    WAITING = "waiting"
    SUBMITTED_ON_TIME = "submitted_on_time"
    SUBMITTED_LATE = "submitted_late"
    MISSED_DEADLINE = "missed_deadline"
    MANUALLY_CONFIRMED = "manually_confirmed"
    DAY_OFF = "day_off"
    TEMPORARILY_CLOSED = "temporarily_closed"


class InviteType(StrEnum):
    ROLE = "role"
    BUSH = "bush"
    STORE = "store"


class InviteStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    USED_UP = "used_up"


class ScheduleExceptionType(StrEnum):
    DAY_OFF = "day_off"
    CUSTOM_SCHEDULE = "custom_schedule"
    TEMPORARILY_CLOSED = "temporarily_closed"
    REPAIR = "repair"
    HOLIDAY = "holiday"
    OPEN_LATER = "open_later"
    CLOSE_EARLIER = "close_earlier"


class NotificationType(StrEnum):
    OPENING_REMINDER = "opening_reminder"
    OPENING_TIME_REACHED = "opening_time_reached"
    OPENING_LATE_REMINDER = "opening_late_reminder"
    OPENING_DEADLINE_MISSED = "opening_deadline_missed"
    OPENING_SUMMARY = "opening_summary"

    CLOSING_REMINDER = "closing_reminder"
    CLOSING_TIME_REACHED = "closing_time_reached"
    CLOSING_DEADLINE_MISSED = "closing_deadline_missed"
    CLOSING_SUMMARY = "closing_summary"

    BUSH_DAILY_SUMMARY = "bush_daily_summary"
    NETWORK_DAILY_SUMMARY = "network_daily_summary"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    EDITED = "edited"
    SKIPPED = "skipped"


class SummaryType(StrEnum):
    BUSH_OPENING = "bush_opening"
    NETWORK_OPENING = "network_opening"
    BUSH_CLOSING = "bush_closing"
    NETWORK_CLOSING = "network_closing"


class AuditAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DEACTIVATED = "deactivated"
    ACTIVATED = "activated"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    DELETED = "deleted"

    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"

    USER_BOUND_TO_STORE = "user_bound_to_store"
    USER_UNBOUND_FROM_STORE = "user_unbound_from_store"

    USER_BOUND_TO_BUSH = "user_bound_to_bush"
    USER_UNBOUND_FROM_BUSH = "user_unbound_from_bush"

    INVITE_CREATED = "invite_created"
    INVITE_USED = "invite_used"
    INVITE_REVOKED = "invite_revoked"

    OPENING_CONFIRMED = "opening_confirmed"
    OPENING_MODIFIED = "opening_modified"

    CLOSING_CONFIRMED = "closing_confirmed"
    CLOSING_MODIFIED = "closing_modified"

    CASH_AMOUNT_MODIFIED = "cash_amount_modified"
    RECEIPT_REPLACED = "receipt_replaced"

    STORE_MOVED_TO_BUSH = "store_moved_to_bush"
    STORE_CLUSTER_CHANGED = "store_cluster_changed"
    STORE_SCHEDULE_CHANGED = "store_schedule_changed"


class EntityType(StrEnum):
    USER = "user"
    STORE = "store"
    BUSH = "bush"
    CLUSTER = "cluster"
    STORE_SCHEDULE = "store_schedule"
    SCHEDULE_EXCEPTION = "schedule_exception"
    INVITE_LINK = "invite_link"
    OPENING_CHECKIN = "opening_checkin"
    CLOSING_REPORT = "closing_report"
    SYSTEM_SETTING = "system_setting"