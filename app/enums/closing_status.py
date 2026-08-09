from __future__ import annotations

from enum import StrEnum


class ClosingStatus(StrEnum):
    """
    Статус закриття торгової точки.

    Значення синхронізовані з
    app.database.models.enums.ClosingStatus.
    """

    NOT_REQUIRED = "not_required"

    WAITING = "waiting"

    SUBMITTED_ON_TIME = "submitted_on_time"

    SUBMITTED_LATE = "submitted_late"

    MISSED_DEADLINE = "missed_deadline"

    MANUALLY_CONFIRMED = "manually_confirmed"

    DAY_OFF = "day_off"

    TEMPORARILY_CLOSED = "temporarily_closed"


__all__ = [
    "ClosingStatus",
]