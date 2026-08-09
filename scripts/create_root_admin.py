from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.database.models.enums import (
    UserRole,
    UserStatus,
)
from app.database.models.user import User
from app.database.session import (
    async_session_factory,
)


# =========================================================
# ARGUMENTS
# =========================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Створює нового ROOT_ADMIN "
            "або підвищує існуючого користувача."
        )
    )

    parser.add_argument(
        "--telegram-id",
        type=int,
        required=True,
        help="Telegram ID користувача.",
    )

    parser.add_argument(
        "--full-name",
        type=str,
        default="Root Admin",
        help=(
            "Ім'я користувача. "
            "Потрібне при створенні нового запису."
        ),
    )

    parser.add_argument(
        "--username",
        type=str,
        default=None,
        help=(
            "Telegram username без @. "
            "Необов'язково."
        ),
    )

    parser.add_argument(
        "--phone",
        type=str,
        default=None,
        help="Номер телефону. Необов'язково.",
    )

    return parser


# =========================================================
# NORMALIZATION
# =========================================================


def normalize_username(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    value = (
        value
        .strip()
        .lstrip("@")
    )

    return (
        value
        if value
        else None
    )


def normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    value = value.strip()

    return (
        value
        if value
        else None
    )


# =========================================================
# CREATE / PROMOTE
# =========================================================


async def create_root_admin(
    *,
    telegram_id: int,
    full_name: str,
    username: str | None = None,
    phone: str | None = None,
) -> User:
    """
    Створює ROOT_ADMIN або підвищує
    існуючого Telegram-користувача.
    """

    if telegram_id <= 0:
        raise ValueError(
            "Telegram ID має бути більше 0."
        )

    full_name = (
        full_name.strip()
        or "Root Admin"
    )

    username = normalize_username(
        username
    )

    phone = normalize_optional_text(
        phone
    )

    async with (
        async_session_factory()
        as session
    ):
        result = await session.execute(
            select(User).where(
                User.telegram_id
                == telegram_id
            )
        )

        user = (
            result
            .scalars()
            .first()
        )

        # -------------------------------------------------
        # EXISTING USER
        # -------------------------------------------------

        if user is not None:
            user.role = (
                UserRole.ROOT_ADMIN
            )

            user.status = (
                UserStatus.ACTIVE
            )

            user.is_blocked = False
            user.blocked_at = None
            user.blocked_reason = None

            if full_name:
                user.full_name = (
                    full_name
                )

            if username is not None:
                user.username = (
                    username
                )

            if phone is not None:
                user.phone = (
                    phone
                )

            await session.commit()
            await session.refresh(
                user
            )

            print(
                "✅ Існуючого користувача "
                "підвищено до ROOT_ADMIN."
            )

            return user

        # -------------------------------------------------
        # NEW USER
        # -------------------------------------------------

        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            phone=phone,
            role=(
                UserRole.ROOT_ADMIN
            ),
            status=(
                UserStatus.ACTIVE
            ),
            is_blocked=False,
        )

        session.add(
            user
        )

        await session.commit()

        await session.refresh(
            user
        )

        print(
            "✅ Нового ROOT_ADMIN створено."
        )

        return user


# =========================================================
# MAIN
# =========================================================


async def async_main() -> int:
    parser = build_parser()

    args = parser.parse_args()

    try:
        user = await create_root_admin(
            telegram_id=(
                args.telegram_id
            ),
            full_name=(
                args.full_name
            ),
            username=(
                args.username
            ),
            phone=(
                args.phone
            ),
        )

    except Exception as error:
        print(
            "❌ Не вдалося створити "
            "ROOT_ADMIN:"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        return 1

    print()
    print(
        "ROOT_ADMIN готовий:"
    )
    print(
        f"  DB ID: {user.id}"
    )
    print(
        "  Telegram ID: "
        f"{user.telegram_id}"
    )
    print(
        f"  Ім'я: {user.full_name}"
    )
    print(
        "  Username: "
        f"@{user.username}"
        if user.username
        else "  Username: —"
    )
    print(
        f"  Role: {user.role.value}"
    )
    print(
        f"  Status: {user.status.value}"
    )
    print(
        f"  Blocked: {user.is_blocked}"
    )

    return 0


def main() -> None:
    exit_code = asyncio.run(
        async_main()
    )

    sys.exit(
        exit_code
    )


if __name__ == "__main__":
    main()