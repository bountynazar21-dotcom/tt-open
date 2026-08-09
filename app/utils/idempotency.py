from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


# =========================================================
# NORMALIZATION
# =========================================================


def normalize_idempotency_value(
    value: Any,
) -> Any:
    """
    Перетворює значення у стабільний формат,
    придатний для формування idempotency key.
    """

    if value is None:
        return None

    if isinstance(
        value,
        Enum,
    ):
        return normalize_idempotency_value(
            value.value
        )

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    if isinstance(
        value,
        Decimal,
    ):
        return str(value)

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): (
                normalize_idempotency_value(
                    item
                )
            )
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(
                    pair[0]
                ),
            )
        }

    if isinstance(
        value,
        Sequence,
    ) and not isinstance(
        value,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        return [
            normalize_idempotency_value(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    raw_id = getattr(
        value,
        "id",
        None,
    )

    if raw_id is not None:
        return {
            "type": (
                value.__class__.__name__
            ),
            "id": raw_id,
        }

    return str(
        value
    )


# =========================================================
# SERIALIZATION
# =========================================================


def stable_json(
    value: Any,
) -> str:
    """
    Стабільна JSON-серіалізація.

    Однакові дані завжди дають
    однаковий результат незалежно
    від порядку ключів dict.
    """

    normalized = (
        normalize_idempotency_value(
            value
        )
    )

    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    )


# =========================================================
# HASH
# =========================================================


def make_hash(
    value: Any,
    *,
    algorithm: str = "sha256",
) -> str:
    """
    Формує стабільний hash.
    """

    payload = stable_json(
        value
    ).encode(
        "utf-8"
    )

    try:
        hasher = hashlib.new(
            algorithm
        )
    except ValueError as error:
        raise ValueError(
            "Непідтримуваний hash algorithm: "
            f"{algorithm}"
        ) from error

    hasher.update(
        payload
    )

    return hasher.hexdigest()


# =========================================================
# IDEMPOTENCY KEY
# =========================================================


def build_idempotency_key(
    namespace: str,
    *parts: Any,
    prefix: str | None = None,
    length: int = 32,
) -> str:
    """
    Створює короткий стабільний ключ.

    Приклад:

        build_idempotency_key(
            "opening",
            store_id,
            business_date,
        )
    """

    normalized_namespace = (
        str(namespace)
        .strip()
        .lower()
    )

    if not normalized_namespace:
        raise ValueError(
            "namespace не може бути порожнім."
        )

    digest = make_hash(
        {
            "namespace": (
                normalized_namespace
            ),
            "parts": parts,
        }
    )

    if length <= 0:
        raise ValueError(
            "length має бути більше 0."
        )

    digest = digest[
        :length
    ]

    if prefix:
        normalized_prefix = (
            str(prefix)
            .strip()
        )

        if normalized_prefix:
            return (
                f"{normalized_prefix}:"
                f"{digest}"
            )

    return (
        f"{normalized_namespace}:"
        f"{digest}"
    )


# =========================================================
# TELEGRAM UPDATE
# =========================================================


def telegram_update_key(
    update_id: int,
) -> str:
    """
    Idempotency key для Telegram update.
    """

    return build_idempotency_key(
        "telegram_update",
        int(update_id),
    )


def telegram_message_key(
    *,
    chat_id: int,
    message_id: int,
) -> str:
    """
    Idempotency key для Telegram message.
    """

    return build_idempotency_key(
        "telegram_message",
        int(chat_id),
        int(message_id),
    )


# =========================================================
# OPENING
# =========================================================


def opening_key(
    *,
    store_id: int,
    business_date: date,
) -> str:
    """
    Один opening-запис на ТТ + дату.
    """

    return build_idempotency_key(
        "opening",
        int(store_id),
        business_date,
    )


# =========================================================
# CLOSING
# =========================================================


def closing_key(
    *,
    store_id: int,
    business_date: date,
) -> str:
    """
    Один closing-запис на ТТ + дату.
    """

    return build_idempotency_key(
        "closing",
        int(store_id),
        business_date,
    )


# =========================================================
# NOTIFICATIONS
# =========================================================


def notification_key(
    *,
    notification_type: Any,
    store_id: int | None = None,
    business_date: date | None = None,
    user_id: int | None = None,
    extra: Any = None,
) -> str:
    """
    Стабільний ключ для notification,
    щоб scheduler не надсилав дублікати.
    """

    return build_idempotency_key(
        "notification",
        {
            "type": (
                notification_type
            ),
            "store_id": (
                store_id
            ),
            "business_date": (
                business_date
            ),
            "user_id": (
                user_id
            ),
            "extra": extra,
        },
    )


# =========================================================
# REPORTS
# =========================================================


def report_key(
    *,
    report_type: Any,
    date_from: date,
    date_to: date,
    scope: Any = None,
    scope_id: int | None = None,
) -> str:
    """
    Ключ для генерації звіту.
    """

    return build_idempotency_key(
        "report",
        {
            "report_type": (
                report_type
            ),
            "date_from": (
                date_from
            ),
            "date_to": (
                date_to
            ),
            "scope": scope,
            "scope_id": (
                scope_id
            ),
        },
    )


# =========================================================
# GENERIC ENTITY
# =========================================================


def entity_action_key(
    *,
    entity_type: str,
    entity_id: Any,
    action: str,
    version: Any = None,
) -> str:
    """
    Універсальний ключ для критичних
    адміністративних дій.
    """

    return build_idempotency_key(
        "entity_action",
        {
            "entity_type": (
                entity_type
            ),
            "entity_id": (
                entity_id
            ),
            "action": action,
            "version": version,
        },
    )


# =========================================================
# COMPARE
# =========================================================


def same_idempotency_payload(
    first: Any,
    second: Any,
) -> bool:
    """
    Перевіряє, чи два payload
    логічно однакові.
    """

    return (
        stable_json(
            first
        )
        == stable_json(
            second
        )
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "normalize_idempotency_value",
    "stable_json",
    "make_hash",

    "build_idempotency_key",

    "telegram_update_key",
    "telegram_message_key",

    "opening_key",
    "closing_key",

    "notification_key",
    "report_key",
    "entity_action_key",

    "same_idempotency_payload",
]