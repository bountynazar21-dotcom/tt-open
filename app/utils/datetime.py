from __future__ import annotations

from datetime import (
    date,
    datetime,
    time,
    timedelta,
    timezone,
)
from zoneinfo import ZoneInfo


# =========================================================
# CONSTANTS
# =========================================================


DEFAULT_TIMEZONE = "Europe/Kyiv"

UTC = timezone.utc


# =========================================================
# TIMEZONE
# =========================================================


def get_timezone(
    timezone_name: str = DEFAULT_TIMEZONE,
) -> ZoneInfo:
    """
    Повертає timezone за назвою.

    За замовчуванням використовується
    Europe/Kyiv.
    """

    return ZoneInfo(
        timezone_name
    )


def kyiv_timezone() -> ZoneInfo:
    """
    Timezone України.
    """

    return get_timezone(
        DEFAULT_TIMEZONE
    )


# =========================================================
# NOW
# =========================================================


def now_utc() -> datetime:
    """
    Поточний UTC datetime
    з timezone info.
    """

    return datetime.now(
        UTC
    )


def now_local(
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Поточний локальний datetime.
    """

    return datetime.now(
        get_timezone(
            timezone_name
        )
    )


def today_local(
    timezone_name: str = DEFAULT_TIMEZONE,
) -> date:
    """
    Поточна локальна дата.
    """

    return now_local(
        timezone_name
    ).date()


# =========================================================
# AWARE / NAIVE
# =========================================================


def is_aware(
    value: datetime,
) -> bool:
    """
    Перевіряє, чи datetime має timezone.
    """

    return (
        value.tzinfo is not None
        and value.utcoffset() is not None
    )


def is_naive(
    value: datetime,
) -> bool:
    """
    Перевіряє, чи datetime без timezone.
    """

    return not is_aware(
        value
    )


def ensure_aware(
    value: datetime,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Якщо datetime naive —
    додає локальну timezone.

    Якщо aware — повертає без змін.
    """

    if is_aware(
        value
    ):
        return value

    return value.replace(
        tzinfo=get_timezone(
            timezone_name
        )
    )


def ensure_utc(
    value: datetime,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Перетворює datetime в UTC.
    """

    aware = ensure_aware(
        value,
        timezone_name,
    )

    return aware.astimezone(
        UTC
    )


def ensure_local(
    value: datetime,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Перетворює datetime
    в локальну timezone.
    """

    aware = ensure_aware(
        value,
        timezone_name,
    )

    return aware.astimezone(
        get_timezone(
            timezone_name
        )
    )


# =========================================================
# UTC / LOCAL CONVERSION
# =========================================================


def to_utc(
    value: datetime,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Alias для ensure_utc().
    """

    return ensure_utc(
        value,
        timezone_name,
    )


def to_local(
    value: datetime,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Alias для ensure_local().
    """

    return ensure_local(
        value,
        timezone_name,
    )


# =========================================================
# DATE + TIME
# =========================================================


def combine_date_time(
    value_date: date,
    value_time: time,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Об'єднує date + time
    в timezone-aware datetime.
    """

    result = datetime.combine(
        value_date,
        value_time,
    )

    if result.tzinfo is not None:
        return result

    return result.replace(
        tzinfo=get_timezone(
            timezone_name
        )
    )


def local_datetime(
    value_date: date,
    value_time: time,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Alias для combine_date_time().
    """

    return combine_date_time(
        value_date,
        value_time,
        timezone_name,
    )


# =========================================================
# START / END OF DAY
# =========================================================


def start_of_day(
    value: date | datetime,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Початок дня 00:00:00.
    """

    target_date = (
        value.date()
        if isinstance(
            value,
            datetime,
        )
        else value
    )

    return datetime.combine(
        target_date,
        time.min,
        tzinfo=get_timezone(
            timezone_name
        ),
    )


def end_of_day(
    value: date | datetime,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Кінець дня 23:59:59.999999.
    """

    target_date = (
        value.date()
        if isinstance(
            value,
            datetime,
        )
        else value
    )

    return datetime.combine(
        target_date,
        time.max,
        tzinfo=get_timezone(
            timezone_name
        ),
    )


# =========================================================
# DATE RANGE
# =========================================================


def date_range(
    start_date: date,
    end_date: date,
) -> list[date]:
    """
    Повертає список дат включно
    від start_date до end_date.
    """

    if end_date < start_date:
        return []

    days = (
        end_date
        - start_date
    ).days

    return [
        start_date
        + timedelta(
            days=index
        )
        for index in range(
            days + 1
        )
    ]


# =========================================================
# MINUTES
# =========================================================


def minutes_between(
    start: datetime,
    end: datetime,
) -> int:
    """
    Різниця між datetime
    у повних хвилинах.

    Може бути від'ємною.
    """

    difference = (
        end
        - start
    )

    return int(
        difference.total_seconds()
        // 60
    )


def positive_minutes_between(
    start: datetime,
    end: datetime,
) -> int:
    """
    Різниця в хвилинах,
    але не менше 0.
    """

    return max(
        0,
        minutes_between(
            start,
            end,
        ),
    )


def lateness_minutes(
    scheduled_at: datetime,
    actual_at: datetime,
) -> int:
    """
    Кількість хвилин запізнення.

    Якщо actual_at <= scheduled_at,
    повертає 0.
    """

    if actual_at <= scheduled_at:
        return 0

    seconds = (
        actual_at
        - scheduled_at
    ).total_seconds()

    # Навіть частина хвилини після дедлайну
    # вважається хвилиною запізнення.
    return int(
        (
            seconds
            + 59
        )
        // 60
    )


# =========================================================
# DEADLINES
# =========================================================


def add_minutes(
    value: datetime,
    minutes: int,
) -> datetime:
    """
    Додає хвилини до datetime.
    """

    return (
        value
        + timedelta(
            minutes=minutes
        )
    )


def build_deadline(
    scheduled_at: datetime,
    deadline_minutes: int,
) -> datetime:
    """
    Формує deadline від запланованого часу.
    """

    return add_minutes(
        scheduled_at,
        deadline_minutes,
    )


def is_after_deadline(
    current_time: datetime,
    deadline: datetime,
) -> bool:
    """
    True, якщо current_time
    строго пізніше deadline.
    """

    return (
        current_time
        > deadline
    )


def is_deadline_reached(
    current_time: datetime,
    deadline: datetime,
) -> bool:
    """
    True, якщо deadline уже настав
    або пройшов.
    """

    return (
        current_time
        >= deadline
    )


# =========================================================
# PARSING
# =========================================================


def parse_date(
    value: str,
) -> date:
    """
    Парсить дату.

    Підтримує:
    YYYY-MM-DD
    DD.MM.YYYY
    DD/MM/YYYY
    """

    value = value.strip()

    formats = (
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(
                value,
                fmt,
            ).date()
        except ValueError:
            continue

    raise ValueError(
        f"Некоректна дата: {value}"
    )


def parse_time(
    value: str,
) -> time:
    """
    Парсить час.

    Підтримує:
    HH:MM
    HH:MM:SS
    """

    value = value.strip()

    formats = (
        "%H:%M",
        "%H:%M:%S",
    )

    for fmt in formats:
        try:
            return datetime.strptime(
                value,
                fmt,
            ).time()
        except ValueError:
            continue

    raise ValueError(
        f"Некоректний час: {value}"
    )


def parse_datetime(
    value: str,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Парсить ISO datetime.

    Якщо timezone відсутня —
    додає локальну.
    """

    value = value.strip()

    parsed = datetime.fromisoformat(
        value
    )

    return ensure_aware(
        parsed,
        timezone_name,
    )


# =========================================================
# FORMATTING
# =========================================================


def format_date(
    value: date | datetime | None,
    default: str = "—",
) -> str:
    """
    Формат DD.MM.YYYY.
    """

    if value is None:
        return default

    if isinstance(
        value,
        datetime,
    ):
        value = value.date()

    return value.strftime(
        "%d.%m.%Y"
    )


def format_time(
    value: time | datetime | None,
    default: str = "—",
) -> str:
    """
    Формат HH:MM.
    """

    if value is None:
        return default

    if isinstance(
        value,
        datetime,
    ):
        value = value.time()

    return value.strftime(
        "%H:%M"
    )


def format_datetime(
    value: datetime | None,
    default: str = "—",
) -> str:
    """
    Формат DD.MM.YYYY HH:MM.
    """

    if value is None:
        return default

    return value.strftime(
        "%d.%m.%Y %H:%M"
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "DEFAULT_TIMEZONE",
    "UTC",

    "get_timezone",
    "kyiv_timezone",

    "now_utc",
    "now_local",
    "today_local",

    "is_aware",
    "is_naive",
    "ensure_aware",
    "ensure_utc",
    "ensure_local",

    "to_utc",
    "to_local",

    "combine_date_time",
    "local_datetime",

    "start_of_day",
    "end_of_day",
    "date_range",

    "minutes_between",
    "positive_minutes_between",
    "lateness_minutes",

    "add_minutes",
    "build_deadline",
    "is_after_deadline",
    "is_deadline_reached",

    "parse_date",
    "parse_time",
    "parse_datetime",

    "format_date",
    "format_time",
    "format_datetime",
]