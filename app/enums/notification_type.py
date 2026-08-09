from __future__ import annotations

from enum import StrEnum


class NotificationType(StrEnum):
    """
    Типи Telegram-сповіщень.

    Значення синхронізовані з
    app.database.models.enums.NotificationType.
    """

    # Відкриття
    OPENING_REMINDER = "opening_reminder"
    OPENING_TIME_REACHED = "opening_time_reached"
    OPENING_LATE_REMINDER = "opening_late_reminder"
    OPENING_DEADLINE_MISSED = "opening_deadline_missed"
    OPENING_SUMMARY = "opening_summary"

    # Закриття
    CLOSING_REMINDER = "closing_reminder"
    CLOSING_TIME_REACHED = "closing_time_reached"
    CLOSING_DEADLINE_MISSED = "closing_deadline_missed"
    CLOSING_SUMMARY = "closing_summary"

    # Денна звітність
    BUSH_DAILY_SUMMARY = "bush_daily_summary"
    NETWORK_DAILY_SUMMARY = "network_daily_summary"


__all__ = [
    "NotificationType",
]