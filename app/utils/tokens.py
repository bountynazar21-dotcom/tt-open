from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Any


# =========================================================
# CONSTANTS
# =========================================================


DEFAULT_TOKEN_BYTES = 32

DEFAULT_SHORT_TOKEN_BYTES = 12

DEFAULT_HASH_ALGORITHM = "sha256"


# =========================================================
# RANDOM TOKENS
# =========================================================


def generate_token(
    nbytes: int = DEFAULT_TOKEN_BYTES,
) -> str:
    """
    Генерує URL-safe випадковий token.

    Підходить для:
    - invite links
    - temporary access tokens
    - one-time codes
    """

    if nbytes <= 0:
        raise ValueError(
            "nbytes має бути більше 0."
        )

    return secrets.token_urlsafe(
        nbytes
    )


def generate_short_token(
    nbytes: int = DEFAULT_SHORT_TOKEN_BYTES,
) -> str:
    """
    Коротший URL-safe token.
    """

    return generate_token(
        nbytes
    )


def generate_hex_token(
    nbytes: int = DEFAULT_TOKEN_BYTES,
) -> str:
    """
    Генерує hex token.
    """

    if nbytes <= 0:
        raise ValueError(
            "nbytes має бути більше 0."
        )

    return secrets.token_hex(
        nbytes
    )


# =========================================================
# NUMERIC CODE
# =========================================================


def generate_numeric_code(
    length: int = 6,
) -> str:
    """
    Генерує цифровий одноразовий код.

    Наприклад:
        482913
    """

    if length <= 0:
        raise ValueError(
            "length має бути більше 0."
        )

    return "".join(
        str(
            secrets.randbelow(10)
        )
        for _ in range(
            length
        )
    )


# =========================================================
# HASH
# =========================================================


def hash_token(
    token: str,
    *,
    salt: str = "",
    algorithm: str = DEFAULT_HASH_ALGORITHM,
) -> str:
    """
    Створює hash токена.

    Сам token можна не зберігати в БД —
    достатньо зберігати hash.
    """

    normalized_token = (
        str(token)
        .strip()
    )

    if not normalized_token:
        raise ValueError(
            "token не може бути порожнім."
        )

    payload = (
        f"{salt}{normalized_token}"
    ).encode(
        "utf-8"
    )

    try:
        digest = hashlib.new(
            algorithm
        )
    except ValueError as error:
        raise ValueError(
            "Непідтримуваний hash algorithm: "
            f"{algorithm}"
        ) from error

    digest.update(
        payload
    )

    return digest.hexdigest()


def verify_token_hash(
    token: str,
    expected_hash: str,
    *,
    salt: str = "",
    algorithm: str = DEFAULT_HASH_ALGORITHM,
) -> bool:
    """
    Перевіряє token проти збереженого hash.
    """

    if not token or not expected_hash:
        return False

    actual_hash = hash_token(
        token,
        salt=salt,
        algorithm=algorithm,
    )

    return hmac.compare_digest(
        actual_hash,
        str(
            expected_hash
        ),
    )


# =========================================================
# HMAC SIGNATURE
# =========================================================


def sign_value(
    value: str,
    secret_key: str,
    *,
    algorithm: str = DEFAULT_HASH_ALGORITHM,
) -> str:
    """
    Формує HMAC-підпис для рядка.
    """

    if not secret_key:
        raise ValueError(
            "secret_key не може бути порожнім."
        )

    try:
        digestmod = getattr(
            hashlib,
            algorithm,
        )
    except AttributeError as error:
        raise ValueError(
            "Непідтримуваний hash algorithm: "
            f"{algorithm}"
        ) from error

    return hmac.new(
        secret_key.encode(
            "utf-8"
        ),
        str(value).encode(
            "utf-8"
        ),
        digestmod=digestmod,
    ).hexdigest()


def verify_signature(
    value: str,
    signature: str,
    secret_key: str,
    *,
    algorithm: str = DEFAULT_HASH_ALGORITHM,
) -> bool:
    """
    Перевіряє HMAC-підпис.
    """

    if (
        not value
        or not signature
        or not secret_key
    ):
        return False

    expected = sign_value(
        value,
        secret_key,
        algorithm=algorithm,
    )

    return hmac.compare_digest(
        expected,
        signature,
    )


# =========================================================
# SIGNED TOKEN
# =========================================================


def create_signed_token(
    payload: str,
    secret_key: str,
) -> str:
    """
    Формує token:

        base64(payload).signature
    """

    encoded_payload = (
        base64.urlsafe_b64encode(
            payload.encode(
                "utf-8"
            )
        )
        .decode(
            "ascii"
        )
        .rstrip("=")
    )

    signature = sign_value(
        encoded_payload,
        secret_key,
    )

    return (
        f"{encoded_payload}."
        f"{signature}"
    )


def decode_signed_token(
    token: str,
    secret_key: str,
) -> str | None:
    """
    Перевіряє підпис і повертає payload.

    Якщо token некоректний —
    повертає None.
    """

    try:
        encoded_payload, signature = (
            token.split(
                ".",
                1,
            )
        )
    except ValueError:
        return None

    if not verify_signature(
        encoded_payload,
        signature,
        secret_key,
    ):
        return None

    try:
        padding = (
            "="
            * (
                -len(
                    encoded_payload
                )
                % 4
            )
        )

        raw = (
            base64.urlsafe_b64decode(
                encoded_payload
                + padding
            )
        )

        return raw.decode(
            "utf-8"
        )

    except (
        ValueError,
        UnicodeDecodeError,
    ):
        return None


# =========================================================
# TOKEN NORMALIZATION
# =========================================================


def normalize_token(
    value: Any,
) -> str | None:
    """
    Нормалізує token із callback / deep link.
    """

    if value is None:
        return None

    token = str(
        value
    ).strip()

    if not token:
        return None

    return token


def strip_token_prefix(
    token: str,
    *prefixes: str,
) -> str:
    """
    Прибирає відомий prefix.

    Приклад:
        invite_abc -> abc
    """

    value = str(
        token
    ).strip()

    lowered = value.lower()

    for prefix in prefixes:
        normalized_prefix = str(
            prefix
        )

        if lowered.startswith(
            normalized_prefix.lower()
        ):
            return value[
                len(
                    normalized_prefix
                ):
            ]

    return value


# =========================================================
# INVITE TOKEN
# =========================================================


def normalize_invite_token(
    value: Any,
) -> str | None:
    """
    Нормалізує invite token.

    Підтримує:
        invite_xxx
        invite-xxx
        inv_xxx
        inv-xxx
        token_xxx
        token-xxx
    """

    token = normalize_token(
        value
    )

    if token is None:
        return None

    result = strip_token_prefix(
        token,
        "invite_",
        "invite-",
        "inv_",
        "inv-",
        "token_",
        "token-",
    )

    result = result.strip()

    return (
        result
        if result
        else None
    )


# =========================================================
# SAFE DISPLAY
# =========================================================


def mask_token(
    token: str | None,
    *,
    visible_start: int = 4,
    visible_end: int = 4,
) -> str:
    """
    Маскує token для логів.

    abcdefghijkl
    -> abcd…ijkl
    """

    if not token:
        return "—"

    value = str(
        token
    )

    minimum_length = (
        visible_start
        + visible_end
    )

    if len(value) <= minimum_length:
        return "***"

    return (
        value[
            :visible_start
        ]
        + "…"
        + value[
            -visible_end:
        ]
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "DEFAULT_TOKEN_BYTES",
    "DEFAULT_SHORT_TOKEN_BYTES",
    "DEFAULT_HASH_ALGORITHM",

    "generate_token",
    "generate_short_token",
    "generate_hex_token",

    "generate_numeric_code",

    "hash_token",
    "verify_token_hash",

    "sign_value",
    "verify_signature",

    "create_signed_token",
    "decode_signed_token",

    "normalize_token",
    "strip_token_prefix",
    "normalize_invite_token",

    "mask_token",
]