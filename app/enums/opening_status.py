from __future__ import annotations

from enum import StrEnum


class OpeningStatus(StrEnum):
    """
    Статус відкриття торгової точки.

    Значення синхронізовані з
    app.database.models.enums.OpeningStatus.
    """

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


__all__ = [
    "OpeningStatus",
]