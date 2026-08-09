from __future__ import annotations

from datetime import (
    date,
    datetime,
    time,
)
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any


# =========================================================
# BASIC
# =========================================================


EMPTY_VALUE = "—"


def safe_text(
    value: Any,
    default: str = EMPTY_VALUE,
) -> str:
    """
    Безпечне перетворення значення в текст.
    """

    if value is None:
        return default

    text = str(
        value
    ).strip()

    return (
        text
        if text
        else default
    )


def html_escape(
    value: Any,
    default: str = EMPTY_VALUE,
) -> str:
    """
    Екранує текст для Telegram HTML parse mode.
    """

    return escape(
        safe_text(
            value,
            default,
        )
    )


# =========================================================
# DATE / TIME
# =========================================================


def format_date(
    value: date | datetime | None,
    default: str = EMPTY_VALUE,
) -> str:
    """
    DD.MM.YYYY
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
    default: str = EMPTY_VALUE,
) -> str:
    """
    HH:MM
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
    default: str = EMPTY_VALUE,
) -> str:
    """
    DD.MM.YYYY HH:MM
    """

    if value is None:
        return default

    return value.strftime(
        "%d.%m.%Y %H:%M"
    )


# =========================================================
# MONEY
# =========================================================


def to_decimal(
    value: Any,
    default: Decimal | None = None,
) -> Decimal | None:
    """
    Перетворює значення в Decimal.
    """

    if value is None:
        return default

    if isinstance(
        value,
        Decimal,
    ):
        return value

    try:
        normalized = (
            str(value)
            .strip()
            .replace(" ", "")
            .replace(",", ".")
        )

        return Decimal(
            normalized
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return default


def format_money(
    value: Any,
    *,
    currency: str = "грн",
    default: str = EMPTY_VALUE,
    decimals: int = 2,
) -> str:
    """
    Форматує грошову суму.

    Приклад:
    12500.5 -> 12 500.50 грн
    """

    amount = to_decimal(
        value
    )

    if amount is None:
        return default

    formatted = (
        f"{amount:,.{decimals}f}"
        .replace(",", " ")
    )

    return (
        f"{formatted} {currency}"
        if currency
        else formatted
    )


def format_money_short(
    value: Any,
    *,
    currency: str = "грн",
    default: str = EMPTY_VALUE,
) -> str:
    """
    Без копійок, якщо вони нульові.
    """

    amount = to_decimal(
        value
    )

    if amount is None:
        return default

    if amount == amount.to_integral():
        formatted = (
            f"{int(amount):,}"
            .replace(",", " ")
        )
    else:
        formatted = (
            f"{amount:,.2f}"
            .replace(",", " ")
        )

    return (
        f"{formatted} {currency}"
        if currency
        else formatted
    )


# =========================================================
# NUMBERS
# =========================================================


def format_integer(
    value: Any,
    default: str = EMPTY_VALUE,
) -> str:
    """
    12500 -> 12 500
    """

    try:
        integer = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default

    return (
        f"{integer:,}"
        .replace(",", " ")
    )


def format_float(
    value: Any,
    *,
    decimals: int = 2,
    default: str = EMPTY_VALUE,
) -> str:
    """
    Форматує float.
    """

    try:
        number = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default

    return (
        f"{number:.{decimals}f}"
    )


def format_percent(
    value: Any,
    *,
    decimals: int = 1,
    multiply: bool = False,
    default: str = EMPTY_VALUE,
) -> str:
    """
    Форматує відсоток.

    multiply=True:
    0.25 -> 25%
    """

    try:
        number = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default

    if multiply:
        number *= 100

    return (
        f"{number:.{decimals}f}%"
    )


# =========================================================
# PHONE
# =========================================================


def normalize_phone(
    value: str | None,
) -> str | None:
    """
    Прибирає пробіли, дужки, дефіси.
    """

    if not value:
        return None

    value = value.strip()

    digits = "".join(
        char
        for char in value
        if char.isdigit()
    )

    if not digits:
        return None

    if value.startswith("+"):
        return (
            "+"
            + digits
        )

    return digits


def format_phone(
    value: str | None,
    default: str = EMPTY_VALUE,
) -> str:
    """
    Просте форматування українського номера.
    """

    normalized = normalize_phone(
        value
    )

    if not normalized:
        return default

    digits = normalized.lstrip(
        "+"
    )

    if (
        len(digits) == 12
        and digits.startswith("380")
    ):
        return (
            f"+380 "
            f"{digits[3:5]} "
            f"{digits[5:8]} "
            f"{digits[8:10]} "
            f"{digits[10:12]}"
        )

    return normalized


# =========================================================
# TELEGRAM
# =========================================================


def format_username(
    username: str | None,
    default: str = EMPTY_VALUE,
) -> str:
    """
    username -> @username
    """

    if not username:
        return default

    value = username.strip()

    if not value:
        return default

    return (
        value
        if value.startswith("@")
        else f"@{value}"
    )


def format_telegram_user(
    user: Any,
    default: str = EMPTY_VALUE,
) -> str:
    """
    Формує читабельне ім'я Telegram-користувача.
    """

    if user is None:
        return default

    full_name = getattr(
        user,
        "full_name",
        None,
    )

    username = getattr(
        user,
        "username",
        None,
    )

    telegram_id = getattr(
        user,
        "telegram_id",
        None,
    )

    parts: list[str] = []

    if full_name:
        parts.append(
            str(full_name)
        )

    if username:
        parts.append(
            format_username(
                username
            )
        )

    if telegram_id:
        parts.append(
            f"ID {telegram_id}"
        )

    return (
        " · ".join(parts)
        if parts
        else default
    )


# =========================================================
# STORE
# =========================================================


def format_store_code(
    store_number: Any,
    *,
    prefix: str = "SB",
    default: str = EMPTY_VALUE,
) -> str:
    """
    76 -> SB-76
    """

    try:
        number = int(
            store_number
        )
    except (
        TypeError,
        ValueError,
    ):
        return default

    return (
        f"{prefix}-{number}"
    )


def format_store_title(
    store: Any,
    default: str = EMPTY_VALUE,
) -> str:
    """
    Формує назву ТТ із доступних полів.
    """

    if store is None:
        return default

    code = getattr(
        store,
        "code",
        None,
    )

    store_number = getattr(
        store,
        "store_number",
        None,
    )

    name = getattr(
        store,
        "name",
        None,
    )

    city = getattr(
        store,
        "city",
        None,
    )

    address = getattr(
        store,
        "address",
        None,
    )

    if not code and store_number is not None:
        code = format_store_code(
            store_number,
            default="",
        )

    parts = [
        str(value).strip()
        for value in (
            code,
            name,
            city,
            address,
        )
        if value
        and str(value).strip()
    ]

    return (
        " · ".join(parts)
        if parts
        else default
    )


# =========================================================
# ENUM / STATUS
# =========================================================


def enum_value(
    value: Any,
    default: str = EMPTY_VALUE,
) -> str:
    """
    Працює з Enum і звичайним значенням.
    """

    if value is None:
        return default

    raw = getattr(
        value,
        "value",
        value,
    )

    return safe_text(
        raw,
        default,
    )


def enum_name(
    value: Any,
    default: str = EMPTY_VALUE,
) -> str:
    """
    Повертає enum.name або строкове значення.
    """

    if value is None:
        return default

    raw = getattr(
        value,
        "name",
        value,
    )

    return safe_text(
        raw,
        default,
    )


def humanize_key(
    value: Any,
    default: str = EMPTY_VALUE,
) -> str:
    """
    OPENED_ON_TIME -> Opened on time
    """

    text = enum_value(
        value,
        default="",
    )

    if not text:
        return default

    return (
        text
        .replace("-", " ")
        .replace("_", " ")
        .strip()
        .lower()
        .capitalize()
    )


# =========================================================
# DURATION
# =========================================================


def format_minutes(
    minutes: Any,
    default: str = EMPTY_VALUE,
) -> str:
    """
    1 -> 1 хв
    15 -> 15 хв
    """

    try:
        value = int(
            minutes
        )
    except (
        TypeError,
        ValueError,
    ):
        return default

    return (
        f"{value} хв"
    )


def format_duration_minutes(
    minutes: Any,
    default: str = EMPTY_VALUE,
) -> str:
    """
    125 -> 2 год 5 хв
    """

    try:
        value = int(
            minutes
        )
    except (
        TypeError,
        ValueError,
    ):
        return default

    if value < 0:
        return default

    hours, mins = divmod(
        value,
        60,
    )

    parts: list[str] = []

    if hours:
        parts.append(
            f"{hours} год"
        )

    if mins or not parts:
        parts.append(
            f"{mins} хв"
        )

    return " ".join(
        parts
    )


# =========================================================
# BOOL
# =========================================================


def format_bool(
    value: Any,
    *,
    yes: str = "✅ Так",
    no: str = "❌ Ні",
) -> str:
    return (
        yes
        if bool(value)
        else no
    )


def format_active(
    value: Any,
) -> str:
    return (
        "🟢 Активний"
        if bool(value)
        else "⚫ Неактивний"
    )


# =========================================================
# TEXT
# =========================================================


def truncate(
    value: Any,
    *,
    max_length: int = 100,
    suffix: str = "…",
    default: str = EMPTY_VALUE,
) -> str:
    """
    Обрізає довгий текст.
    """

    text = safe_text(
        value,
        default,
    )

    if text == default:
        return text

    if len(text) <= max_length:
        return text

    if max_length <= len(suffix):
        return suffix[
            :max_length
        ]

    return (
        text[
            :max_length
            - len(suffix)
        ]
        + suffix
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "EMPTY_VALUE",

    "safe_text",
    "html_escape",

    "format_date",
    "format_time",
    "format_datetime",

    "to_decimal",
    "format_money",
    "format_money_short",

    "format_integer",
    "format_float",
    "format_percent",

    "normalize_phone",
    "format_phone",

    "format_username",
    "format_telegram_user",

    "format_store_code",
    "format_store_title",

    "enum_value",
    "enum_name",
    "humanize_key",

    "format_minutes",
    "format_duration_minutes",

    "format_bool",
    "format_active",

    "truncate",
]