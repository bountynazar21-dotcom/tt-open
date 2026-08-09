from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

from app.database.models.enums import (
    UserRole,
    UserStatus,
)
from app.database.models.user import User
from app.database.session import (
    async_session_factory,
)
from app.repositories import Repositories
from app.services.import_service import (
    ImportApplyResult,
    ImportPreview,
    ImportService,
)


# =========================================================
# ARGUMENTS
# =========================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Імпорт торгових точок "
            "TT-open із XLSX / XLS / CSV."
        )
    )

    parser.add_argument(
        "file",
        type=str,
        help="Шлях до XLSX / XLS / CSV файлу.",
    )

    parser.add_argument(
        "--actor-telegram-id",
        type=int,
        required=True,
        help=(
            "Telegram ID ROOT_ADMIN або DIRECTOR, "
            "від імені якого виконується імпорт."
        ),
    )

    parser.add_argument(
        "--sheet",
        type=str,
        default=None,
        help=(
            "Назва аркуша Excel. "
            "Якщо не вказано — використовується "
            "активний аркуш."
        ),
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Фактично записати зміни в БД. "
            "Без цього параметра виконується "
            "лише preview."
        ),
    )

    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help=(
            "Дозволити імпорт коректних рядків, "
            "навіть якщо у preview є помилки."
        ),
    )

    parser.add_argument(
        "--include-kyiv",
        action="store_true",
        help=(
            "Не виключати Київ. "
            "За замовчуванням Київ ігнорується."
        ),
    )

    parser.add_argument(
        "--reason",
        type=str,
        default="Імпорт торгових точок через CLI",
        help="Причина для audit log.",
    )

    return parser


# =========================================================
# FILE
# =========================================================


def resolve_file(
    raw_path: str,
) -> Path:
    path = Path(
        raw_path
    ).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"Файл не знайдено: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Шлях не є файлом: {path}"
        )

    extension = (
        path.suffix
        .lower()
        .lstrip(".")
    )

    if extension not in {
        "xlsx",
        "xls",
        "csv",
    }:
        raise ValueError(
            "Підтримуються лише "
            "XLSX, XLS та CSV."
        )

    return path


# =========================================================
# ACTOR
# =========================================================


async def load_actor(
    session,
    *,
    telegram_id: int,
) -> User:
    result = await session.execute(
        select(User).where(
            User.telegram_id
            == telegram_id
        )
    )

    actor = (
        result
        .scalars()
        .first()
    )

    if actor is None:
        raise ValueError(
            "Користувача з Telegram ID "
            f"{telegram_id} не знайдено."
        )

    if actor.status != UserStatus.ACTIVE:
        raise PermissionError(
            "Користувач не має статусу ACTIVE."
        )

    if actor.is_blocked:
        raise PermissionError(
            "Користувач заблокований."
        )

    if actor.role not in {
        UserRole.ROOT_ADMIN,
        UserRole.DIRECTOR,
    }:
        raise PermissionError(
            "Імпорт доступний лише "
            "ROOT_ADMIN або DIRECTOR."
        )

    return actor


# =========================================================
# PREVIEW DISPLAY
# =========================================================


def print_preview(
    preview: ImportPreview,
) -> None:
    print()
    print("=" * 60)
    print("PREVIEW ІМПОРТУ")
    print("=" * 60)

    print(
        f"Файл: {preview.file_name}"
    )

    print(
        "Формат: "
        f"{preview.file_format.value}"
    )

    print(
        "Аркуш: "
        f"{preview.sheet_name or '—'}"
    )

    print(
        "Рядок заголовків: "
        f"{preview.header_row_number}"
    )

    print()
    print(
        f"Всього рядків: {preview.total_rows}"
    )
    print(
        f"Створити:       {preview.create_count}"
    )
    print(
        f"Оновити:        {preview.update_count}"
    )
    print(
        f"Без змін:       {preview.unchanged_count}"
    )
    print(
        f"Проігноровано:  {preview.ignored_count}"
    )
    print(
        f"Помилкових:     {preview.invalid_count}"
    )
    print(
        f"До імпорту:     {preview.actionable_count}"
    )

    if preview.issues:
        print()
        print("-" * 60)
        print("ПРОБЛЕМИ")
        print("-" * 60)

        for issue in preview.issues:
            row_text = (
                f"рядок {issue.row_number}"
                if issue.row_number
                else "файл"
            )

            field_text = (
                f", поле {issue.field}"
                if issue.field
                else ""
            )

            print(
                f"[{issue.level.value.upper()}] "
                f"{row_text}"
                f"{field_text}: "
                f"{issue.message}"
            )

    print()
    print("-" * 60)
    print("РЯДКИ")
    print("-" * 60)

    for row in preview.rows:
        store_code = (
            row.code
            or (
                f"SB-{row.store_number}"
                if row.store_number
                is not None
                else "—"
            )
        )

        print(
            f"#{row.row_number:<4} "
            f"{store_code:<12} "
            f"{row.status.value:<10} "
            f"{row.city or '—'}"
        )

    print("=" * 60)


# =========================================================
# RESULT DISPLAY
# =========================================================


def print_result(
    result: ImportApplyResult,
) -> None:
    print()
    print("=" * 60)
    print("РЕЗУЛЬТАТ ІМПОРТУ")
    print("=" * 60)

    print(
        f"Файл: {result.file_name}"
    )

    print(
        "Рядків у preview: "
        f"{result.total_preview_rows}"
    )

    print(
        f"Спроб запису:    {result.attempted_count}"
    )

    print(
        f"Успішно:         {result.success_count}"
    )

    print(
        f"Помилок:         {result.failed_count}"
    )

    print(
        f"Створено:        {result.created_count}"
    )

    print(
        f"Оновлено:        {result.updated_count}"
    )

    print(
        f"Без змін:        {result.unchanged_count}"
    )

    print(
        f"Проігноровано:   {result.ignored_count}"
    )

    print(
        f"Невалідних:      {result.invalid_count}"
    )

    failed_items = [
        item
        for item in result.items
        if not item.success
    ]

    if failed_items:
        print()
        print("-" * 60)
        print("ПОМИЛКИ ЗАПИСУ")
        print("-" * 60)

        for item in failed_items:
            code = (
                item.code
                or (
                    f"SB-{item.store_number}"
                    if item.store_number
                    is not None
                    else "—"
                )
            )

            print(
                f"Рядок {item.row_number} "
                f"({code}): "
                f"{item.error or 'невідома помилка'}"
            )

    print("=" * 60)


# =========================================================
# IMPORT
# =========================================================


async def run_import(
    *,
    file_path: Path,
    actor_telegram_id: int,
    sheet_name: str | None,
    should_apply: bool,
    allow_partial: bool,
    ignore_kyiv: bool,
    reason: str,
) -> None:
    content = file_path.read_bytes()

    if not content:
        raise ValueError(
            "Файл порожній."
        )

    async with (
        async_session_factory()
        as session
    ):
        repositories = Repositories(
            session
        )

        actor = await load_actor(
            session,
            telegram_id=actor_telegram_id,
        )

        service = ImportService(
            repositories
        )

        # -----------------------------------------
        # PREVIEW
        # -----------------------------------------

        preview = await service.preview_bytes(
            actor=actor,
            content=content,
            file_name=file_path.name,
            sheet_name=sheet_name,
            ignore_kyiv=ignore_kyiv,
        )

        print_preview(
            preview
        )

        # -----------------------------------------
        # PREVIEW ONLY
        # -----------------------------------------

        if not should_apply:
            print()
            print(
                "ℹ️ Це лише preview."
            )

            print(
                "Для фактичного запису "
                "додайте параметр --apply."
            )

            await session.rollback()

            return

        # -----------------------------------------
        # SAFETY
        # -----------------------------------------

        if preview.actionable_count == 0:
            print()
            print(
                "ℹ️ Немає рядків, які потрібно "
                "створити або оновити."
            )

            await session.rollback()

            return

        if (
            preview.invalid_count > 0
            and not allow_partial
        ):
            print()
            print(
                "❌ Імпорт НЕ виконано: "
                "у preview є помилки."
            )

            print(
                "Виправте файл або використайте "
                "--allow-partial."
            )

            await session.rollback()

            return

        # -----------------------------------------
        # APPLY
        # -----------------------------------------

        result = await service.apply_preview(
            actor=actor,
            preview=preview,
            allow_partial=allow_partial,
            reason=reason,
        )

        await session.commit()

        print_result(
            result
        )


# =========================================================
# MAIN
# =========================================================


async def async_main() -> int:
    parser = build_parser()

    args = parser.parse_args()

    try:
        file_path = resolve_file(
            args.file
        )

        await run_import(
            file_path=file_path,
            actor_telegram_id=(
                args.actor_telegram_id
            ),
            sheet_name=args.sheet,
            should_apply=args.apply,
            allow_partial=(
                args.allow_partial
            ),
            ignore_kyiv=(
                not args.include_kyiv
            ),
            reason=(
                args.reason.strip()
                or "Імпорт торгових точок через CLI"
            ),
        )

    except Exception as error:
        print()
        print(
            "❌ ПОМИЛКА ІМПОРТУ"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        return 1

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