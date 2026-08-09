from __future__ import annotations

from enum import StrEnum


class ScheduleExceptionType(StrEnum):
    """
    Тип винятку з робочого графіка ТТ.

    Значення синхронізовані з
    app.database.models.enums.ScheduleExceptionType.
    """

    DAY_OFF = "day_off"

    CUSTOM_SCHEDULE = "custom_schedule"

    TEMPORARILY_CLOSED = "temporarily_closed"

    REPAIR = "repair"

    HOLIDAY = "holiday"

    OPEN_LATER = "open_later"

    CLOSE_EARLIER = "close_earlier"


# Compatibility alias.
ExceptionType = ScheduleExceptionType


__all__ = [
    "ScheduleExceptionType",
    "ExceptionType",
]