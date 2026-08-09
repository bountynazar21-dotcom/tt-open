from __future__ import annotations

from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)
from typing import Any


# =========================================================
# CONSTANTS
# =========================================================


ZERO_MONEY = Decimal("0.00")

MONEY_QUANT = Decimal("0.01")

DEFAULT_CURRENCY = "UAH"

DEFAULT_CURRENCY_SYMBOL = "грн"

# 1 хвилина запізнення = 8 грн
LATE_PENALTY_PER_MINUTE = Decimal("8.00")


# =========================================================
# CONVERSION
# =========================================================


def to_decimal(
    value: Any,
    *,
    default: Decimal | None = None,
) -> Decimal | None:
    """
    Безпечно перетворює значення в Decimal.

    Підтримує:
        1500
        1500.50
        "1500"
        "1500,50"
        "1 500,50"
        Decimal(...)
    """

    if value is None:
        return default

    if isinstance(
        value,
        Decimal,
    ):
        return value

    if isinstance(
        value,
        bool,
    ):
        return default

    try:
        normalized = (
            str(value)
            .strip()
            .replace("\xa0", "")
            .replace(" ", "")
            .replace(",", ".")
        )

        if not normalized:
            return default

        return Decimal(
            normalized
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return default


def require_decimal(
    value: Any,
) -> Decimal:
    """
    Перетворює значення в Decimal.

    Якщо значення некоректне —
    кидає ValueError.
    """

    result = to_decimal(
        value
    )

    if result is None:
        raise ValueError(
            "Некоректне грошове значення."
        )

    return result


# =========================================================
# ROUNDING
# =========================================================


def quantize_money(
    value: Any,
) -> Decimal:
    """
    Округлює суму до 2 знаків після коми.
    """

    amount = require_decimal(
        value
    )

    return amount.quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )


def normalize_money(
    value: Any,
    *,
    allow_negative: bool = False,
) -> Decimal:
    """
    Нормалізує грошову суму.

    За замовчуванням від'ємні
    значення заборонені.
    """

    amount = quantize_money(
        value
    )

    if (
        not allow_negative
        and amount < ZERO_MONEY
    ):
        raise ValueError(
            "Сума не може бути від'ємною."
        )

    return amount


# =========================================================
# PARSING USER INPUT
# =========================================================


def parse_money(
    value: str | int | float | Decimal,
    *,
    allow_negative: bool = False,
) -> Decimal:
    """
    Парсить введену користувачем суму.

    Приклади:
        "12500"
        "12 500"
        "12500,50"
        "12 500.50"
    """

    return normalize_money(
        value,
        allow_negative=allow_negative,
    )


def try_parse_money(
    value: Any,
    *,
    allow_negative: bool = False,
) -> Decimal | None:
    """
    Аналог parse_money(), але замість
    помилки повертає None.
    """

    try:
        return parse_money(
            value,
            allow_negative=allow_negative,
        )
    except (
        ValueError,
        InvalidOperation,
    ):
        return None


def is_valid_money(
    value: Any,
    *,
    allow_negative: bool = False,
) -> bool:
    """
    Перевіряє, чи значення є
    коректною грошовою сумою.
    """

    return (
        try_parse_money(
            value,
            allow_negative=allow_negative,
        )
        is not None
    )


# =========================================================
# FORMATTING
# =========================================================


def format_money(
    value: Any,
    *,
    currency: str = DEFAULT_CURRENCY_SYMBOL,
    decimals: int = 2,
    default: str = "—",
) -> str:
    """
    Форматує суму.

    12500.5 -> "12 500.50 грн"
    """

    amount = to_decimal(
        value
    )

    if amount is None:
        return default

    amount = amount.quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )

    formatted = (
        f"{amount:,.{decimals}f}"
        .replace(",", " ")
    )

    if not currency:
        return formatted

    return (
        f"{formatted} {currency}"
    )


def format_money_compact(
    value: Any,
    *,
    currency: str = DEFAULT_CURRENCY_SYMBOL,
    default: str = "—",
) -> str:
    """
    Якщо копійок немає:
        1500 -> 1 500 грн

    Якщо є:
        1500.50 -> 1 500.50 грн
    """

    amount = to_decimal(
        value
    )

    if amount is None:
        return default

    amount = quantize_money(
        amount
    )

    if (
        amount
        == amount.to_integral_value()
    ):
        formatted = (
            f"{int(amount):,}"
            .replace(",", " ")
        )
    else:
        formatted = (
            f"{amount:,.2f}"
            .replace(",", " ")
        )

    if not currency:
        return formatted

    return (
        f"{formatted} {currency}"
    )


# =========================================================
# CASH
# =========================================================


def normalize_cash_amount(
    value: Any,
) -> Decimal:
    """
    Нормалізація каси.

    Каса не може бути від'ємною.
    """

    return normalize_money(
        value,
        allow_negative=False,
    )


def cash_difference(
    actual: Any,
    expected: Any,
) -> Decimal:
    """
    actual - expected

    Додатне значення = надлишок.
    Від'ємне = недостача.
    """

    actual_amount = (
        quantize_money(
            actual
        )
    )

    expected_amount = (
        quantize_money(
            expected
        )
    )

    return quantize_money(
        actual_amount
        - expected_amount
    )


# =========================================================
# SUM
# =========================================================


def sum_money(
    values: list[Any]
    | tuple[Any, ...],
    *,
    ignore_invalid: bool = True,
) -> Decimal:
    """
    Безпечна сума грошових значень.
    """

    result = ZERO_MONEY

    for value in values:
        amount = to_decimal(
            value
        )

        if amount is None:
            if ignore_invalid:
                continue

            raise ValueError(
                "Знайдено некоректну суму."
            )

        result += amount

    return quantize_money(
        result
    )


# =========================================================
# PENALTIES
# =========================================================


def calculate_late_penalty(
    late_minutes: int,
    *,
    rate_per_minute: Any = LATE_PENALTY_PER_MINUTE,
) -> Decimal:
    """
    Рахує штраф за запізнення.

    За замовчуванням:
        1 хв = 8 грн

    Приклад:
        7 хв -> 56 грн
    """

    try:
        minutes = int(
            late_minutes
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            "Некоректна кількість хвилин."
        ) from error

    if minutes <= 0:
        return ZERO_MONEY

    rate = normalize_money(
        rate_per_minute
    )

    return quantize_money(
        Decimal(
            minutes
        )
        * rate
    )


def calculate_penalty(
    late_minutes: int,
    *,
    rate_per_minute: Any = LATE_PENALTY_PER_MINUTE,
) -> Decimal:
    """
    Alias для calculate_late_penalty().
    """

    return calculate_late_penalty(
        late_minutes,
        rate_per_minute=rate_per_minute,
    )


# =========================================================
# COMPARISON
# =========================================================


def money_equal(
    first: Any,
    second: Any,
) -> bool:
    """
    Порівнює дві суми
    після округлення до копійок.
    """

    try:
        return (
            quantize_money(
                first
            )
            == quantize_money(
                second
            )
        )
    except ValueError:
        return False


def is_zero_money(
    value: Any,
) -> bool:
    """
    Перевіряє, чи сума = 0.00.
    """

    try:
        return (
            quantize_money(
                value
            )
            == ZERO_MONEY
        )
    except ValueError:
        return False


# =========================================================
# DATABASE HELPERS
# =========================================================


def money_to_string(
    value: Any,
) -> str:
    """
    Стабільне представлення Decimal
    для audit/json/text.

    1500 -> "1500.00"
    """

    return format(
        quantize_money(
            value
        ),
        ".2f",
    )


def money_to_float(
    value: Any,
) -> float:
    """
    Decimal -> float.

    Використовувати лише там,
    де Decimal не підтримується.
    """

    return float(
        quantize_money(
            value
        )
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "ZERO_MONEY",
    "MONEY_QUANT",
    "DEFAULT_CURRENCY",
    "DEFAULT_CURRENCY_SYMBOL",
    "LATE_PENALTY_PER_MINUTE",

    "to_decimal",
    "require_decimal",

    "quantize_money",
    "normalize_money",

    "parse_money",
    "try_parse_money",
    "is_valid_money",

    "format_money",
    "format_money_compact",

    "normalize_cash_amount",
    "cash_difference",

    "sum_money",

    "calculate_late_penalty",
    "calculate_penalty",

    "money_equal",
    "is_zero_money",

    "money_to_string",
    "money_to_float",
]