from __future__ import annotations

from enum import StrEnum


class AuditAction(StrEnum):
    """
    Типи дій для AuditLog.

    Значення синхронізовані з
    app.database.models.enums.AuditAction.
    """

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


__all__ = [
    "AuditAction",
]