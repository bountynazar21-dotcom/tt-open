from __future__ import annotations

import re
from datetime import (
    date,
    datetime,
    time,
)
from decimal import Decimal
from typing import Any


# =========================================================
# CONSTANTS
# =========================================================


PHONE_MIN_DIGITS = 10
PHONE_MAX_DIGITS = 15

TELEGRAM_USERNAME_MIN_LENGTH = 5
TELEGRAM_USERNAME_MAX_LENGTH = 32

MAX_REASON_LENGTH = 1000

MAX_NAME_LENGTH = 255

MAX_STORE_CODE_LENGTH = 50


# =========================================================
# GENERIC
# =========================================================


def has_value(
    value: Any,
) -> bool:
    """
    Перевіряє, що значення не порожнє.
    """

    if value is None:
        return False

    if isinstance(
        value,
        str,
    ):
        return bool(
            value.strip()
        )

    return True


def is_non_empty_string(
    value: Any,
) -> bool:
    """
    True тільки для непорожнього рядка.
    """

    return (
        isinstance(
            value,
            str,
        )
        and bool(
            value.strip()
        )
    )


def validate_text_length(
    value: str | None,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> bool:
    """
    Перевіряє довжину тексту.
    """

    if value is None:
        return minimum == 0

    text = value.strip()

    if len(text) < minimum:
        return False

    if (
        maximum is not None
        and len(text) > maximum
    ):
        return False

    return True


# =========================================================
# INTEGER
# =========================================================


def is_integer(
    value: Any,
) -> bool:
    """
    Перевіряє, чи можна привести
    значення до int.
    """

    if isinstance(
        value,
        bool,
    ):
        return False

    try:
        int(
            value
        )
        return True

    except (
        TypeError,
        ValueError,
    ):
        return False


def is_positive_integer(
    value: Any,
) -> bool:
    """
    Ціле число > 0.
    """

    if not is_integer(
        value
    ):
        return False

    return int(
        value
    ) > 0


def is_non_negative_integer(
    value: Any,
) -> bool:
    """
    Ціле число >= 0.
    """

    if not is_integer(
        value
    ):
        return False

    return int(
        value
    ) >= 0


# =========================================================
# MONEY
# =========================================================


def normalize_decimal_string(
    value: Any,
) -> str | None:
    """
    Нормалізує введену суму.

    1 500,50 -> 1500.50
    """

    if value is None:
        return None

    text = (
        str(value)
        .strip()
        .replace("\xa0", "")
        .replace(" ", "")
        .replace(",", ".")
    )

    return (
        text
        if text
        else None
    )


def is_money(
    value: Any,
    *,
    allow_negative: bool = False,
) -> bool:
    """
    Перевіряє грошове значення.
    """

    normalized = (
        normalize_decimal_string(
            value
        )
    )

    if normalized is None:
        return False

    try:
        amount = Decimal(
            normalized
        )

    except Exception:
        return False

    if not amount.is_finite():
        return False

    if (
        not allow_negative
        and amount < 0
    ):
        return False

    exponent = (
        amount.as_tuple()
        .exponent
    )

    # Максимум 2 знаки після коми.
    if exponent < -2:
        return False

    return True


def is_cash_amount(
    value: Any,
) -> bool:
    """
    Каса повинна бути >= 0.
    """

    return is_money(
        value,
        allow_negative=False,
    )


# =========================================================
# PHONE
# =========================================================


def phone_digits(
    value: str | None,
) -> str:
    """
    Залишає тільки цифри.
    """

    if not value:
        return ""

    return "".join(
        char
        for char in str(
            value
        )
        if char.isdigit()
    )


def normalize_phone(
    value: str | None,
) -> str | None:
    """
    Нормалізація телефону.

    Українські варіанти:

        0671234567
        380671234567
        +380671234567

    -> +380671234567
    """

    digits = phone_digits(
        value
    )

    if not digits:
        return None

    # 0671234567
    if (
        len(digits) == 10
        and digits.startswith("0")
    ):
        digits = (
            "38"
            + digits
        )

    # 80671234567
    if (
        len(digits) == 11
        and digits.startswith("80")
    ):
        digits = (
            "3"
            + digits
        )

    if not (
        PHONE_MIN_DIGITS
        <= len(digits)
        <= PHONE_MAX_DIGITS
    ):
        return None

    return (
        "+"
        + digits
    )


def is_phone(
    value: str | None,
) -> bool:
    """
    Перевіряє телефон.
    """

    return (
        normalize_phone(
            value
        )
        is not None
    )


def is_ukrainian_phone(
    value: str | None,
) -> bool:
    """
    Перевіряє український номер
    у форматі +380XXXXXXXXX.
    """

    normalized = (
        normalize_phone(
            value
        )
    )

    if normalized is None:
        return False

    return bool(
        re.fullmatch(
            r"\+380\d{9}",
            normalized,
        )
    )


# =========================================================
# TELEGRAM
# =========================================================


def is_telegram_id(
    value: Any,
) -> bool:
    """
    Telegram user/chat ID.
    """

    if isinstance(
        value,
        bool,
    ):
        return False

    try:
        int(
            value
        )
        return True

    except (
        TypeError,
        ValueError,
    ):
        return False


def normalize_username(
    value: str | None,
) -> str | None:
    """
    @username -> username
    """

    if not value:
        return None

    username = (
        str(value)
        .strip()
        .lstrip("@")
    )

    return (
        username
        if username
        else None
    )


def is_telegram_username(
    value: str | None,
) -> bool:
    """
    Telegram username:
    5-32 символи,
    букви, цифри, underscore.
    """

    username = (
        normalize_username(
            value
        )
    )

    if username is None:
        return False

    if not (
        TELEGRAM_USERNAME_MIN_LENGTH
        <= len(username)
        <= TELEGRAM_USERNAME_MAX_LENGTH
    ):
        return False

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9_]+",
            username,
        )
    )


# =========================================================
# STORE
# =========================================================


def normalize_store_code(
    value: Any,
) -> str | None:
    """
    Нормалізує код магазину.

    Приклади:

        sb-76
        SB 76
        SB_76

    -> SB-76
    """

    if value is None:
        return None

    text = (
        str(value)
        .strip()
        .upper()
    )

    if not text:
        return None

    match = re.fullmatch(
        r"SB[\s_-]*(\d+)",
        text,
    )

    if match:
        return (
            f"SB-{int(match.group(1))}"
        )

    if text.isdigit():
        return (
            f"SB-{int(text)}"
        )

    return text


def is_store_code(
    value: Any,
) -> bool:
    """
    Перевіряє стандартний код SB-N.
    """

    normalized = (
        normalize_store_code(
            value
        )
    )

    if normalized is None:
        return False

    if (
        len(normalized)
        > MAX_STORE_CODE_LENGTH
    ):
        return False

    return bool(
        re.fullmatch(
            r"SB-\d+",
            normalized,
        )
    )


def store_number_from_code(
    value: Any,
) -> int | None:
    """
    SB-76 -> 76
    """

    normalized = (
        normalize_store_code(
            value
        )
    )

    if normalized is None:
        return None

    match = re.fullmatch(
        r"SB-(\d+)",
        normalized,
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


# =========================================================
# CLUSTER
# =========================================================


def is_cluster_hour(
    value: Any,
) -> bool:
    """
    Валідний кластер відкриття:
    0..23.
    """

    if not is_integer(
        value
    ):
        return False

    hour = int(
        value
    )

    return (
        0
        <= hour
        <= 23
    )


def normalize_cluster_hour(
    value: Any,
) -> int | None:
    """
    Підтримує:

        8
        08
        08:00
        8:00
        Кластер 08:00
        CLUSTER_08
    """

    if value is None:
        return None

    if isinstance(
        value,
        int,
    ):
        return (
            value
            if is_cluster_hour(
                value
            )
            else None
        )

    text = (
        str(value)
        .strip()
        .lower()
    )

    matches = re.findall(
        r"(?<!\d)(\d{1,2})(?::00|\.00|$)",
        text,
    )

    for match in matches:
        hour = int(
            match
        )

        if (
            0
            <= hour
            <= 23
        ):
            return hour

    return None


# =========================================================
# DATE
# =========================================================


def is_date(
    value: Any,
) -> bool:
    """
    Перевіряє date.
    """

    return (
        isinstance(
            value,
            date,
        )
        and not isinstance(
            value,
            datetime,
        )
    )


def is_datetime(
    value: Any,
) -> bool:
    """
    Перевіряє datetime.
    """

    return isinstance(
        value,
        datetime,
    )


def is_time(
    value: Any,
) -> bool:
    """
    Перевіряє time.
    """

    return isinstance(
        value,
        time,
    )


def is_date_range_valid(
    date_from: date,
    date_to: date,
) -> bool:
    """
    date_from <= date_to.
    """

    return (
        date_from
        <= date_to
    )


# =========================================================
# TEXT
# =========================================================


def is_name(
    value: str | None,
    *,
    minimum: int = 2,
    maximum: int = MAX_NAME_LENGTH,
) -> bool:
    """
    Перевіряє ім'я / назву.
    """

    return validate_text_length(
        value,
        minimum=minimum,
        maximum=maximum,
    )


def is_reason(
    value: str | None,
    *,
    required: bool = True,
) -> bool:
    """
    Перевіряє причину адміністративної дії.
    """

    minimum = (
        1
        if required
        else 0
    )

    return validate_text_length(
        value,
        minimum=minimum,
        maximum=MAX_REASON_LENGTH,
    )


# =========================================================
# BOOLEAN
# =========================================================


TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "y",
    "так",
    "т",
    "on",
    "active",
    "активний",
}

FALSE_VALUES = {
    "0",
    "false",
    "no",
    "n",
    "ні",
    "н",
    "off",
    "inactive",
    "неактивний",
}


def parse_bool(
    value: Any,
) -> bool | None:
    """
    Розпізнає bool зі string/int.
    """

    if isinstance(
        value,
        bool,
    ):
        return value

    if value is None:
        return None

    normalized = (
        str(value)
        .strip()
        .lower()
    )

    if normalized in TRUE_VALUES:
        return True

    if normalized in FALSE_VALUES:
        return False

    return None


def is_boolean_value(
    value: Any,
) -> bool:
    """
    Чи можна розпізнати значення як bool.
    """

    return (
        parse_bool(
            value
        )
        is not None
    )


# =========================================================
# FILES
# =========================================================


def file_extension(
    filename: str | None,
) -> str | None:
    """
    report.xlsx -> xlsx
    """

    if not filename:
        return None

    name = (
        str(filename)
        .strip()
        .lower()
    )

    if (
        not name
        or "." not in name
    ):
        return None

    extension = (
        name.rsplit(
            ".",
            1,
        )[1]
        .strip()
    )

    return (
        extension
        if extension
        else None
    )


def is_allowed_file_extension(
    filename: str | None,
    allowed_extensions: set[str]
    | tuple[str, ...]
    | list[str],
) -> bool:
    """
    Перевіряє extension файлу.
    """

    extension = (
        file_extension(
            filename
        )
    )

    if extension is None:
        return False

    allowed = {
        str(item)
        .lower()
        .lstrip(".")
        .strip()
        for item in allowed_extensions
    }

    return (
        extension
        in allowed
    )


def is_excel_file(
    filename: str | None,
) -> bool:
    """
    XLS/XLSX.
    """

    return is_allowed_file_extension(
        filename,
        {
            "xls",
            "xlsx",
        },
    )


def is_table_file(
    filename: str | None,
) -> bool:
    """
    Формати імпорту таблиць.
    """

    return is_allowed_file_extension(
        filename,
        {
            "xls",
            "xlsx",
            "csv",
        },
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "PHONE_MIN_DIGITS",
    "PHONE_MAX_DIGITS",
    "TELEGRAM_USERNAME_MIN_LENGTH",
    "TELEGRAM_USERNAME_MAX_LENGTH",
    "MAX_REASON_LENGTH",
    "MAX_NAME_LENGTH",
    "MAX_STORE_CODE_LENGTH",

    "has_value",
    "is_non_empty_string",
    "validate_text_length",

    "is_integer",
    "is_positive_integer",
    "is_non_negative_integer",

    "normalize_decimal_string",
    "is_money",
    "is_cash_amount",

    "phone_digits",
    "normalize_phone",
    "is_phone",
    "is_ukrainian_phone",

    "is_telegram_id",
    "normalize_username",
    "is_telegram_username",

    "normalize_store_code",
    "is_store_code",
    "store_number_from_code",

    "is_cluster_hour",
    "normalize_cluster_hour",

    "is_date",
    "is_datetime",
    "is_time",
    "is_date_range_valid",

    "is_name",
    "is_reason",

    "TRUE_VALUES",
    "FALSE_VALUES",
    "parse_bool",
    "is_boolean_value",

    "file_extension",
    "is_allowed_file_extension",
    "is_excel_file",
    "is_table_file",
]