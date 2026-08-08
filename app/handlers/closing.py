from __future__ import annotations

import inspect
import logging
from datetime import datetime
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import (
    State,
    StatesGroup,
)
from aiogram.types import (
    CallbackQuery,
    Message,
)

from app.database.models.user import (
    User as DatabaseUser,
)
from app.handlers.common import (
    get_database_user,
    safe_edit,
)
from app.handlers.opening import (
    KYIV_TZ,
    build_store_choices,
    call_method,
    can_access_store,
    filter_kwargs,
    first_attr,
    flush_changes,
    format_time,
    get_service,
    load_store,
    now_local,
    resolve_store_id,
    store_title,
    to_bool,
    to_int,
)
from app.keyboards import (
    CashAction,
    CashCallback,
    ClosingAction,
    ClosingCallback,
    StoreAction,
    StoreCallback,
    home_keyboard,
)
from app.keyboards.store import (
    cash_confirmation_keyboard,
    cash_input_keyboard,
    closing_already_done_keyboard,
    closing_confirmation_keyboard,
    closing_prepare_keyboard,
    closing_status_keyboard,
    closing_success_keyboard,
    receipt_received_keyboard,
    receipt_request_keyboard,
    select_store_keyboard,
    store_info_keyboard,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="closing",
)


# =========================================================
# CONSTANTS
# =========================================================


MONEY_QUANT = Decimal(
    "0.01"
)

MAX_CASH_AMOUNT = Decimal(
    "10000000.00"
)


# =========================================================
# FSM
# =========================================================


class ClosingStates(
    StatesGroup
):
    """
    FSM процесу закриття.
    """

    waiting_cash = State()

    waiting_cash_confirmation = State()

    waiting_receipt = State()

    waiting_manual_time = State()


# =========================================================
# SERVICES
# =========================================================


def get_closing_service(
    data: dict[str, Any],
) -> Any | None:
    """
    ClosingService.
    """

    return get_service(
        data,
        "closing",
        "closings",
    )


def get_cash_service(
    data: dict[str, Any],
) -> Any | None:
    """
    CashService.
    """

    return get_service(
        data,
        "cash",
    )


def get_file_service(
    data: dict[str, Any],
) -> Any | None:
    """
    FileService.
    """

    return get_service(
        data,
        "files",
        "file",
    )


# =========================================================
# GENERIC RESULT HELPERS
# =========================================================


def result_success(
    result: Any,
) -> bool:
    """
    Чи успішна операція.
    """

    if isinstance(
        result,
        bool,
    ):
        return result

    if result is None:
        return False

    explicit = first_attr(
        result,
        "success",
        "created",
        "updated",
        "completed",
        "is_success",
        default=None,
    )

    if explicit is not None:
        return to_bool(
            explicit,
            default=False,
        )

    return True


def result_message(
    result: Any,
) -> str | None:
    """
    Повідомлення сервісу.
    """

    return first_attr(
        result,
        "message",
        "reason",
        "detail",
        "error",
    )


def result_report(
    result: Any,
) -> Any:
    """
    Витягує ClosingReport із wrapper.
    """

    return first_attr(
        result,
        "report",
        "closing_report",
        "record",
        default=result,
    )


def result_report_id(
    result: Any,
) -> int:
    """
    ID ClosingReport.
    """

    report = result_report(
        result
    )

    value = first_attr(
        result,
        "report_id",
        "closing_report_id",
        default=None,
    )

    if value is None:
        value = first_attr(
            report,
            "id",
            "report_id",
            default=0,
        )

    return max(
        0,
        to_int(
            value
        ),
    )


def result_cash_amount(
    result: Any,
) -> Decimal | None:
    """
    Каса із ClosingReport.
    """

    report = result_report(
        result
    )

    value = first_attr(
        result,
        "cash_amount",
        "cash",
        default=None,
    )

    if value is None:
        value = first_attr(
            report,
            "cash_amount",
            "cash",
            "cash_total",
            default=None,
        )

    if value is None:
        return None

    try:
        return Decimal(
            str(value)
        ).quantize(
            MONEY_QUANT,
            rounding=ROUND_HALF_UP,
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return None


def result_receipt_file_id(
    result: Any,
) -> str | None:
    """
    Telegram file_id чека.
    """

    report = result_report(
        result
    )

    value = first_attr(
        result,
        "receipt_file_id",
        "receipt_telegram_file_id",
        default=None,
    )

    if value is None:
        value = first_attr(
            report,
            "receipt_file_id",
            "receipt_telegram_file_id",
            "receipt_photo_file_id",
            default=None,
        )

    if not value:
        return None

    return str(
        value
    )


def result_closed_at(
    result: Any,
) -> Any:
    """
    Час завершення зміни.
    """

    report = result_report(
        result
    )

    return (
        first_attr(
            result,
            "closed_at",
            "completed_at",
            "finished_at",
            default=None,
        )
        or first_attr(
            report,
            "closed_at",
            "completed_at",
            "finished_at",
            default=None,
        )
    )


def result_started_at(
    result: Any,
) -> Any:
    """
    Час початку закриття.
    """

    report = result_report(
        result
    )

    return (
        first_attr(
            result,
            "started_at",
            "closing_started_at",
            default=None,
        )
        or first_attr(
            report,
            "started_at",
            "closing_started_at",
            "created_at",
            default=None,
        )
    )


def result_is_completed(
    result: Any,
) -> bool:
    """
    Чи завершена зміна.
    """

    if result is None:
        return False

    report = result_report(
        result
    )

    explicit = first_attr(
        result,
        "is_completed",
        "completed",
        "is_closed",
        "closed",
        default=None,
    )

    if explicit is None:
        explicit = first_attr(
            report,
            "is_completed",
            "completed",
            "is_closed",
            "closed",
            default=None,
        )

    if explicit is not None:
        return to_bool(
            explicit
        )

    return (
        result_closed_at(
            result
        )
        is not None
    )


def result_exists(
    result: Any,
) -> bool:
    """
    Чи існує ClosingReport.
    """

    if result is None:
        return False

    report = result_report(
        result
    )

    identifier = first_attr(
        report,
        "id",
        "report_id",
        default=None,
    )

    if identifier is not None:
        return True

    if result_cash_amount(
        result
    ) is not None:
        return True

    if result_receipt_file_id(
        result
    ):
        return True

    if result_started_at(
        result
    ) is not None:
        return True

    if result_closed_at(
        result
    ) is not None:
        return True

    return False


# =========================================================
# MONEY
# =========================================================


def normalize_cash_text(
    value: str,
) -> str:
    """
    Нормалізує:

        12 500
        12,500
        12500,50
        12 500 грн
    """

    normalized = (
        value.strip()
        .lower()
        .replace("грн.", "")
        .replace("грн", "")
        .replace("₴", "")
        .replace("\u00a0", "")
        .replace(" ", "")
    )

    # Українська десяткова кома.
    if (
        "," in normalized
        and "." not in normalized
    ):
        normalized = (
            normalized.replace(
                ",",
                ".",
            )
        )

    # Якщо є і "," і ".",
    # коми трактуємо як розділювачі тисяч.
    elif (
        "," in normalized
        and "." in normalized
    ):
        normalized = (
            normalized.replace(
                ",",
                "",
            )
        )

    return normalized


def parse_cash_amount(
    value: str,
) -> Decimal | None:
    """
    Парсить касу.
    """

    normalized = normalize_cash_text(
        value
    )

    if not normalized:
        return None

    try:
        amount = Decimal(
            normalized
        )

    except InvalidOperation:
        return None

    if amount < 0:
        return None

    if amount > MAX_CASH_AMOUNT:
        return None

    return amount.quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )


def format_money(
    amount: Decimal | None,
) -> str:
    """
    12500 -> 12 500.00 грн
    """

    if amount is None:
        return "—"

    formatted = (
        f"{amount:,.2f}"
        .replace(
            ",",
            " ",
        )
    )

    return (
        f"{formatted} грн"
    )


# =========================================================
# LOAD CLOSING STATUS
# =========================================================


async def get_closing_status(
    *,
    store_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> Any | None:
    """
    ClosingReport за сьогодні.
    """

    service = get_closing_service(
        data
    )

    if service is None:
        return None

    today = now_local().date()

    payload = {
        "store_id": store_id,

        "user": user,
        "actor": user,

        "user_id": (
            getattr(
                user,
                "id",
                None,
            )
            if user is not None
            else None
        ),

        "date": today,
        "work_date": today,
        "target_date": today,
    }

    for method_name in (
        "get_today_status",
        "get_store_today_status",
        "get_today_report",
        "get_closing_status",
        "get_store_closing",
        "get_for_store_date",
        "get_by_store_date",
    ):
        method = getattr(
            service,
            method_name,
            None,
        )

        if not callable(
            method
        ):
            continue

        try:
            return await call_method(
                method,
                payload,
            )

        except (
            TypeError,
            ValueError,
            LookupError,
        ):
            continue

    # -----------------------------------------------------
    # FALLBACK REPOSITORY
    # -----------------------------------------------------

    repositories = data.get(
        "repositories"
    )

    if repositories is None:
        return None

    repository = getattr(
        repositories,
        "closings",
        None,
    )

    if repository is None:
        return None

    for method_name in (
        "get_by_store_date",
        "get_for_store_date",
        "get_store_date",
    ):
        method = getattr(
            repository,
            method_name,
            None,
        )

        if not callable(
            method
        ):
            continue

        try:
            return await call_method(
                method,
                payload,
            )

        except Exception:
            continue

    return None


# =========================================================
# START CLOSING
# =========================================================


async def start_closing(
    *,
    store_id: int,
    user: DatabaseUser,
    data: dict[str, Any],
) -> Any:
    """
    Створює draft ClosingReport,
    якщо його ще немає.
    """

    existing = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    if result_exists(
        existing
    ):
        return existing

    service = get_closing_service(
        data
    )

    if service is None:
        raise RuntimeError(
            "ClosingService недоступний."
        )

    current_time = now_local()

    payload = {
        "store_id": store_id,

        "user": user,
        "actor": user,

        "user_id": getattr(
            user,
            "id",
            None,
        ),

        "actor_id": getattr(
            user,
            "id",
            None,
        ),

        "started_at": current_time,
        "closing_started_at":
            current_time,

        "work_date":
            current_time.date(),

        "date":
            current_time.date(),
    }

    last_error: Exception | None = None

    for method_name in (
        "start_closing",
        "begin_closing",
        "create_draft",
        "get_or_create_today",
        "start",
    ):
        method = getattr(
            service,
            method_name,
            None,
        )

        if not callable(
            method
        ):
            continue

        try:
            result = await call_method(
                method,
                payload,
            )

            await flush_changes(
                data
            )

            return result

        except TypeError as error:
            last_error = error

            continue

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        "У ClosingService не знайдено "
        "метод початку закриття."
    )


# =========================================================
# SET CASH
# =========================================================


async def save_cash_amount(
    *,
    store_id: int,
    report_id: int,
    amount: Decimal,
    user: DatabaseUser,
    data: dict[str, Any],
) -> Any:
    """
    Записує касу.
    """

    cash_service = get_cash_service(
        data
    )

    payload = {
        "store_id": store_id,

        "report_id": report_id,
        "closing_report_id":
            report_id,

        "cash_amount": amount,
        "amount": amount,
        "cash": amount,

        "user": user,
        "actor": user,

        "user_id": getattr(
            user,
            "id",
            None,
        ),

        "actor_id": getattr(
            user,
            "id",
            None,
        ),
    }

    if cash_service is not None:
        for method_name in (
            "set_cash",
            "set_cash_amount",
            "set_closing_cash",
            "save_cash",
            "update_cash",
        ):
            method = getattr(
                cash_service,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            try:
                result = await call_method(
                    method,
                    payload,
                )

                await flush_changes(
                    data
                )

                return result

            except TypeError:
                continue

    # -----------------------------------------------------
    # FALLBACK VIA CLOSING SERVICE
    # -----------------------------------------------------

    closing_service = (
        get_closing_service(
            data
        )
    )

    if closing_service is not None:
        for method_name in (
            "set_cash",
            "set_cash_amount",
            "update_cash",
        ):
            method = getattr(
                closing_service,
                method_name,
                None,
            )

            if not callable(
                method
            ):
                continue

            try:
                result = await call_method(
                    method,
                    payload,
                )

                await flush_changes(
                    data
                )

                return result

            except TypeError:
                continue

    raise RuntimeError(
        "Метод збереження каси "
        "не знайдено."
    )


# =========================================================
# RECEIPT EXTRACTION
# =========================================================


def extract_receipt_file(
    message: Message,
) -> tuple[
    str,
    str | None,
    str,
] | None:
    """
    Повертає:

        file_id
        file_unique_id
        kind
    """

    if message.photo:
        photo = message.photo[-1]

        return (
            photo.file_id,
            photo.file_unique_id,
            "photo",
        )

    document = message.document

    if document is not None:
        mime_type = (
            document.mime_type
            or ""
        ).lower()

        # Дозволяємо image/pdf.
        if (
            mime_type.startswith(
                "image/"
            )
            or mime_type
            == "application/pdf"
        ):
            return (
                document.file_id,
                document.file_unique_id,
                "document",
            )

    return None


# =========================================================
# SAVE RECEIPT
# =========================================================


async def save_receipt(
    *,
    store_id: int,
    report_id: int,
    file_id: str,
    file_unique_id: str | None,
    upload_kind: str,
    user: DatabaseUser,
    data: dict[str, Any],
) -> Any:
    """
    Прив'язує чек до ClosingReport.
    """

    service = get_closing_service(
        data
    )

    if service is None:
        raise RuntimeError(
            "ClosingService недоступний."
        )

    payload = {
        "store_id": store_id,

        "report_id": report_id,
        "closing_report_id":
            report_id,

        "receipt_file_id":
            file_id,

        "file_id":
            file_id,

        "telegram_file_id":
            file_id,

        "receipt_file_unique_id":
            file_unique_id,

        "file_unique_id":
            file_unique_id,

        "upload_kind":
            upload_kind,

        "user": user,
        "actor": user,

        "user_id": getattr(
            user,
            "id",
            None,
        ),

        "actor_id": getattr(
            user,
            "id",
            None,
        ),
    }

    last_error: Exception | None = None

    for method_name in (
        "attach_receipt",
        "set_receipt",
        "save_receipt",
        "update_receipt",
        "add_receipt",
    ):
        method = getattr(
            service,
            method_name,
            None,
        )

        if not callable(
            method
        ):
            continue

        try:
            result = await call_method(
                method,
                payload,
            )

            await flush_changes(
                data
            )

            return result

        except TypeError as error:
            last_error = error

            continue

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        "Метод збереження чека "
        "не знайдено."
    )


# =========================================================
# COMPLETE CLOSING
# =========================================================


async def complete_closing(
    *,
    store_id: int,
    report_id: int,
    user: DatabaseUser,
    data: dict[str, Any],
    closed_at: datetime | None = None,
    manual: bool = False,
) -> Any:
    """
    Завершує зміну.
    """

    service = get_closing_service(
        data
    )

    if service is None:
        raise RuntimeError(
            "ClosingService недоступний."
        )

    actual_time = (
        closed_at
        or now_local()
    )

    payload = {
        "store_id": store_id,

        "report_id": report_id,
        "closing_report_id":
            report_id,

        "user": user,
        "actor": user,

        "user_id": getattr(
            user,
            "id",
            None,
        ),

        "actor_id": getattr(
            user,
            "id",
            None,
        ),

        "closed_at": actual_time,
        "completed_at": actual_time,
        "finished_at": actual_time,

        "manual": manual,
        "is_manual": manual,
    }

    method_names = (
        (
            "manual_close",
            "manual_closing",
            "correct_closing",
            "set_manual_closing",
        )
        if manual
        else (
            "complete_closing",
            "finish_closing",
            "confirm_closing",
            "close_store",
            "complete",
            "finalize",
        )
    )

    last_error: Exception | None = None

    for method_name in method_names:
        method = getattr(
            service,
            method_name,
            None,
        )

        if not callable(
            method
        ):
            continue

        try:
            result = await call_method(
                method,
                payload,
            )

            await flush_changes(
                data
            )

            return result

        except TypeError as error:
            last_error = error

            continue

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        "Метод завершення закриття "
        "не знайдено."
    )


# =========================================================
# STATUS TEXT
# =========================================================


async def build_closing_status_text(
    *,
    store_id: int,
    result: Any,
    data: dict[str, Any],
) -> str:
    """
    Текст поточного закриття.
    """

    store = await load_store(
        store_id=store_id,
        data=data,
    )

    title = store_title(
        store,
        store_id=store_id,
    )

    if not result_exists(
        result
    ):
        return (
            "🌙 <b>Статус закриття</b>\n\n"
            f"🏪 <b>{escape(title)}</b>\n\n"
            "Закриття за сьогодні "
            "ще не розпочато."
        )

    amount = result_cash_amount(
        result
    )

    receipt = result_receipt_file_id(
        result
    )

    started_at = result_started_at(
        result
    )

    closed_at = result_closed_at(
        result
    )

    completed = result_is_completed(
        result
    )

    lines = [
        "🌙 <b>Статус закриття</b>",
        "",
        f"🏪 <b>{escape(title)}</b>",
        "",
    ]

    if started_at is not None:
        lines.append(
            "🕐 Початок закриття: "
            f"<b>{escape(format_time(started_at))}</b>"
        )

    if amount is not None:
        lines.append(
            "💵 Каса: "
            f"<b>{escape(format_money(amount))}</b>"
        )

    else:
        lines.append(
            "💵 Каса: <b>не внесена</b>"
        )

    if receipt:
        lines.append(
            "📷 Чек: <b>додано ✅</b>"
        )

    else:
        lines.append(
            "📷 Чек: <b>не додано</b>"
        )

    if completed:
        lines.append(
            ""
        )

        lines.append(
            "✅ <b>Зміну завершено.</b>"
        )

        if closed_at is not None:
            lines.append(
                "🌙 Час закриття: "
                f"<b>{escape(format_time(closed_at))}</b>"
            )

    else:
        lines.append(
            ""
        )

        if (
            amount is not None
            and receipt
        ):
            lines.append(
                "🟢 <b>Все готово "
                "до завершення зміни.</b>"
            )

        else:
            lines.append(
                "⏳ <b>Закриття "
                "ще не завершено.</b>"
            )

    return "\n".join(
        lines
    )


# =========================================================
# SHOW STORE SELECTION
# =========================================================


async def show_store_selection(
    callback: CallbackQuery,
    *,
    data: dict[str, Any],
) -> None:
    """
    Вибір ТТ для закриття.
    """

    store_ids = set(
        data.get(
            "accessible_store_ids"
        )
        or []
    )

    store_ids = {
        to_int(item)
        for item in store_ids
        if to_int(item) > 0
    }

    if not store_ids:
        await safe_edit(
            callback,
            text=(
                "⚠️ До вашого профілю "
                "не прив'язано жодної ТТ."
            ),
            reply_markup=(
                home_keyboard()
            ),
        )

        return

    stores = await build_store_choices(
        store_ids=store_ids,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "🏪 <b>Оберіть торгову точку</b>\n\n"
            "Для якої ТТ потрібно "
            "виконати закриття?"
        ),
        reply_markup=(
            select_store_keyboard(
                stores=stores,
                context="closing",
            )
        ),
    )


# =========================================================
# SHOW CLOSING MENU
# =========================================================


async def show_closing_menu(
    callback: CallbackQuery,
    *,
    store_id: int,
    user: DatabaseUser,
    data: dict[str, Any],
) -> None:
    """
    Меню закриття ТТ.
    """

    result = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    if result_is_completed(
        result
    ):
        text = (
            await build_closing_status_text(
                store_id=store_id,
                result=result,
                data=data,
            )
        )

        await safe_edit(
            callback,
            text=text,
            reply_markup=(
                closing_already_done_keyboard(
                    store_id=store_id
                )
            ),
        )

        return

    if result_exists(
        result
    ):
        text = (
            await build_closing_status_text(
                store_id=store_id,
                result=result,
                data=data,
            )
        )

        amount = result_cash_amount(
            result
        )

        receipt = result_receipt_file_id(
            result
        )

        await safe_edit(
            callback,
            text=text,
            reply_markup=(
                closing_status_keyboard(
                    store_id=store_id,
                    has_cash=(
                        amount is not None
                    ),
                    has_receipt=bool(
                        receipt
                    ),
                    can_confirm=(
                        amount is not None
                        and bool(receipt)
                    ),
                )
            ),
        )

        return

    store = await load_store(
        store_id=store_id,
        data=data,
    )

    title = store_title(
        store,
        store_id=store_id,
    )

    await safe_edit(
        callback,
        text=(
            "🌙 <b>Закриття магазину</b>\n\n"
            f"🏪 <b>{escape(title)}</b>\n\n"
            "Починаємо закриття зміни?"
        ),
        reply_markup=(
            closing_prepare_keyboard(
                store_id=store_id
            )
        ),
    )


# =========================================================
# MENU
# =========================================================


@router.callback_query(
    ClosingCallback.filter(
        F.action
        == ClosingAction.MENU
    )
)
async def closing_menu_callback(
    callback: CallbackQuery,
    callback_data: ClosingCallback,
    **data: Any,
) -> None:
    """
    Вхід у закриття.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    if user is None:
        return

    store_id = resolve_store_id(
        callback_store_id=(
            callback_data.store_id
        ),
        data=data,
    )

    if store_id is None:
        await show_store_selection(
            callback,
            data=data,
        )

        return

    if not can_access_store(
        store_id=store_id,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    await show_closing_menu(
        callback,
        store_id=store_id,
        user=user,
        data=data,
    )


# =========================================================
# SELECT STORE
# =========================================================


@router.callback_query(
    ClosingCallback.filter(
        F.action
        == ClosingAction.SELECT_STORE
    )
)
async def closing_select_store_callback(
    callback: CallbackQuery,
    callback_data: ClosingCallback,
    **data: Any,
) -> None:
    """
    Вибір ТТ.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    if user is None:
        return

    store_id = (
        callback_data.store_id
    )

    if not can_access_store(
        store_id=store_id,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    await show_closing_menu(
        callback,
        store_id=store_id,
        user=user,
        data=data,
    )


# =========================================================
# PREPARE
# =========================================================


@router.callback_query(
    ClosingCallback.filter(
        F.action
        == ClosingAction.PREPARE
    )
)
async def closing_prepare_callback(
    callback: CallbackQuery,
    callback_data: ClosingCallback,
    **data: Any,
) -> None:
    """
    Підтвердження початку закриття.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    if user is None:
        return

    store_id = resolve_store_id(
        callback_store_id=(
            callback_data.store_id
        ),
        data=data,
    )

    if store_id is None:
        await show_store_selection(
            callback,
            data=data,
        )

        return

    if not can_access_store(
        store_id=store_id,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    existing = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    if result_is_completed(
        existing
    ):
        text = (
            await build_closing_status_text(
                store_id=store_id,
                result=existing,
                data=data,
            )
        )

        await safe_edit(
            callback,
            text=text,
            reply_markup=(
                closing_already_done_keyboard(
                    store_id=store_id
                )
            ),
        )

        return

    store = await load_store(
        store_id=store_id,
        data=data,
    )

    title = store_title(
        store,
        store_id=store_id,
    )

    await safe_edit(
        callback,
        text=(
            "🌙 <b>Початок закриття</b>\n\n"
            f"🏪 <b>{escape(title)}</b>\n\n"
            "Після початку потрібно буде:\n"
            "1. Внести суму каси.\n"
            "2. Додати фото чека.\n"
            "3. Підтвердити завершення."
        ),
        reply_markup=(
            closing_prepare_keyboard(
                store_id=store_id
            )
        ),
    )


# =========================================================
# CASH STEP
# =========================================================


@router.callback_query(
    ClosingCallback.filter(
        F.action
        == ClosingAction.CASH
    )
)
async def closing_cash_callback(
    callback: CallbackQuery,
    callback_data: ClosingCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Початок / повторне введення каси.
    """

    user = get_database_user(
        data
    )

    if user is None:
        return

    store_id = (
        callback_data.store_id
    )

    if not can_access_store(
        store_id=store_id,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    await callback.answer()

    try:
        result = await start_closing(
            store_id=store_id,
            user=user,
            data=data,
        )

    except Exception:
        logger.exception(
            "Failed to start closing: "
            "store_id=%s",
            store_id,
        )

        await callback.answer(
            "Не вдалося почати закриття.",
            show_alert=True,
        )

        return

    report_id = result_report_id(
        result
    )

    await state.set_state(
        ClosingStates.waiting_cash
    )

    await state.update_data(
        closing_store_id=store_id,
        closing_report_id=report_id,
    )

    await safe_edit(
        callback,
        text=(
            "💵 <b>Каса на кінець зміни</b>\n\n"
            "Введіть фактичну суму каси.\n\n"
            "Наприклад:\n"
            "<code>12500</code>\n"
            "або\n"
            "<code>12500,50</code>"
        ),
        reply_markup=(
            cash_input_keyboard(
                store_id=store_id,
                report_id=report_id,
            )
        ),
    )


# =========================================================
# CASH ENTER CALLBACK
# =========================================================


@router.callback_query(
    CashCallback.filter(
        F.action
        == CashAction.ENTER
    )
)
async def cash_enter_callback(
    callback: CallbackQuery,
    callback_data: CashCallback,
    state: FSMContext,
) -> None:
    """
    Повторне введення каси.
    """

    await callback.answer()

    await state.set_state(
        ClosingStates.waiting_cash
    )

    await state.update_data(
        closing_store_id=(
            callback_data.store_id
        ),
        closing_report_id=(
            callback_data.report_id
        ),
    )

    await safe_edit(
        callback,
        text=(
            "💵 <b>Введіть нову суму каси</b>\n\n"
            "Наприклад:\n"
            "<code>12500,50</code>"
        ),
        reply_markup=(
            cash_input_keyboard(
                store_id=(
                    callback_data.store_id
                ),
                report_id=(
                    callback_data.report_id
                ),
            )
        ),
    )


# =========================================================
# RECEIVE CASH
# =========================================================


@router.message(
    ClosingStates.waiting_cash
)
async def closing_cash_message(
    message: Message,
    state: FSMContext,
) -> None:
    """
    Отримує суму каси.
    """

    text = (
        message.text
        or ""
    ).strip()

    if text.lower() in {
        "/cancel",
        "cancel",
        "скасувати",
    }:
        await state.clear()

        await message.answer(
            "❌ Введення каси скасовано.",
            reply_markup=(
                home_keyboard()
            ),
        )

        return

    amount = parse_cash_amount(
        text
    )

    if amount is None:
        await message.answer(
            "⚠️ <b>Не вдалося розпізнати суму.</b>\n\n"
            "Введіть лише число.\n\n"
            "Наприклад:\n"
            "<code>12500</code>\n"
            "або\n"
            "<code>12500,50</code>"
        )

        return

    state_data = await state.get_data()

    store_id = to_int(
        state_data.get(
            "closing_store_id"
        )
    )

    report_id = to_int(
        state_data.get(
            "closing_report_id"
        )
    )

    if store_id <= 0:
        await state.clear()

        await message.answer(
            "⚠️ Не вдалося визначити ТТ."
        )

        return

    await state.update_data(
        pending_cash_amount=str(
            amount
        )
    )

    await state.set_state(
        ClosingStates
        .waiting_cash_confirmation
    )

    await message.answer(
        "💵 <b>Перевірте суму</b>\n\n"
        f"Каса: <b>{escape(format_money(amount))}</b>\n\n"
        "Все правильно?",
        reply_markup=(
            cash_confirmation_keyboard(
                store_id=store_id,
                report_id=report_id,
            )
        ),
    )


# =========================================================
# CASH CONFIRM
# =========================================================


@router.callback_query(
    CashCallback.filter(
        F.action
        == CashAction.CONFIRM
    )
)
async def cash_confirm_callback(
    callback: CallbackQuery,
    callback_data: CashCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Фактичне збереження каси.
    """

    user = get_database_user(
        data
    )

    if user is None:
        return

    state_data = await state.get_data()

    raw_amount = state_data.get(
        "pending_cash_amount"
    )

    try:
        amount = Decimal(
            str(raw_amount)
        ).quantize(
            MONEY_QUANT,
            rounding=ROUND_HALF_UP,
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        await callback.answer(
            "Сума каси втрачена. "
            "Введіть її ще раз.",
            show_alert=True,
        )

        await state.set_state(
            ClosingStates.waiting_cash
        )

        return

    store_id = (
        callback_data.store_id
    )

    report_id = (
        callback_data.report_id
    )

    await callback.answer(
        "Зберігаю касу…"
    )

    try:
        result = await save_cash_amount(
            store_id=store_id,
            report_id=report_id,
            amount=amount,
            user=user,
            data=data,
        )

    except Exception:
        logger.exception(
            "Cash save failed: "
            "store_id=%s report_id=%s",
            store_id,
            report_id,
        )

        await callback.answer(
            "Не вдалося зберегти касу.",
            show_alert=True,
        )

        return

    if not result_success(
        result
    ):
        await callback.answer(
            result_message(
                result
            )
            or "Не вдалося зберегти касу.",
            show_alert=True,
        )

        return

    await state.update_data(
        pending_cash_amount=None,
        closing_store_id=store_id,
        closing_report_id=report_id,
    )

    await state.set_state(
        ClosingStates.waiting_receipt
    )

    await safe_edit(
        callback,
        text=(
            "✅ <b>Касу збережено.</b>\n\n"
            f"💵 {escape(format_money(amount))}\n\n"
            "📷 Тепер надішліть "
            "<b>фото чека закриття</b>."
        ),
        reply_markup=(
            receipt_request_keyboard(
                store_id=store_id
            )
        ),
    )


# =========================================================
# CASH CANCEL
# =========================================================


@router.callback_query(
    CashCallback.filter(
        F.action
        == CashAction.CANCEL
    )
)
async def cash_cancel_callback(
    callback: CallbackQuery,
    callback_data: CashCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Скасування введення каси.
    """

    await callback.answer(
        "Скасовано."
    )

    await state.clear()

    user = get_database_user(
        data
    )

    if user is None:
        return

    await show_closing_menu(
        callback,
        store_id=(
            callback_data.store_id
        ),
        user=user,
        data=data,
    )


# =========================================================
# RECEIPT REQUEST CALLBACK
# =========================================================


@router.callback_query(
    ClosingCallback.filter(
        F.action
        == ClosingAction.RECEIPT
    )
)
async def closing_receipt_callback(
    callback: CallbackQuery,
    callback_data: ClosingCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Очікування фото чека.
    """

    user = get_database_user(
        data
    )

    if user is None:
        return

    store_id = (
        callback_data.store_id
    )

    if not can_access_store(
        store_id=store_id,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    await callback.answer()

    result = await start_closing(
        store_id=store_id,
        user=user,
        data=data,
    )

    report_id = result_report_id(
        result
    )

    await state.set_state(
        ClosingStates.waiting_receipt
    )

    await state.update_data(
        closing_store_id=store_id,
        closing_report_id=report_id,
    )

    await safe_edit(
        callback,
        text=(
            "📷 <b>Фото чека</b>\n\n"
            "Надішліть фото чека "
            "закриття торгової точки.\n\n"
            "Можна надіслати фото "
            "або файл-зображення."
        ),
        reply_markup=(
            receipt_request_keyboard(
                store_id=store_id
            )
        ),
    )


# =========================================================
# RECEIVE RECEIPT
# =========================================================


@router.message(
    ClosingStates.waiting_receipt
)
async def closing_receipt_message(
    message: Message,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Отримує фото/документ чека.
    """

    if (
        message.text
        and message.text.strip().lower()
        in {
            "/cancel",
            "cancel",
            "скасувати",
        }
    ):
        await state.clear()

        await message.answer(
            "❌ Додавання чека скасовано.",
            reply_markup=(
                home_keyboard()
            ),
        )

        return

    receipt = extract_receipt_file(
        message
    )

    if receipt is None:
        await message.answer(
            "⚠️ Потрібно надіслати "
            "<b>фото чека</b>.\n\n"
            "Текстове повідомлення "
            "не підходить."
        )

        return

    file_id, file_unique_id, upload_kind = (
        receipt
    )

    state_data = await state.get_data()

    store_id = to_int(
        state_data.get(
            "closing_store_id"
        )
    )

    report_id = to_int(
        state_data.get(
            "closing_report_id"
        )
    )

    if store_id <= 0:
        await state.clear()

        await message.answer(
            "⚠️ Не вдалося визначити ТТ."
        )

        return

    user = get_database_user(
        data
    )

    if user is None:
        await state.clear()

        return

    try:
        result = await save_receipt(
            store_id=store_id,
            report_id=report_id,
            file_id=file_id,
            file_unique_id=(
                file_unique_id
            ),
            upload_kind=upload_kind,
            user=user,
            data=data,
        )

    except Exception:
        logger.exception(
            "Receipt save failed: "
            "store_id=%s report_id=%s",
            store_id,
            report_id,
        )

        await message.answer(
            "❌ Не вдалося зберегти чек.\n\n"
            "Спробуйте надіслати фото ще раз."
        )

        return

    if not result_success(
        result
    ):
        await message.answer(
            "❌ "
            + escape(
                str(
                    result_message(
                        result
                    )
                    or "Не вдалося зберегти чек."
                )
            )
        )

        return

    await state.clear()

    current = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    amount = result_cash_amount(
        current
    )

    receipt_file = result_receipt_file_id(
        current
    )

    await message.answer(
        "✅ <b>Чек отримано.</b>",
        reply_markup=(
            receipt_received_keyboard(
                store_id=store_id
            )
        ),
    )

    text = await build_closing_status_text(
        store_id=store_id,
        result=current,
        data=data,
    )

    await message.answer(
        text,
        reply_markup=(
            closing_status_keyboard(
                store_id=store_id,
                has_cash=(
                    amount is not None
                ),
                has_receipt=bool(
                    receipt_file
                ),
                can_confirm=(
                    amount is not None
                    and bool(
                        receipt_file
                    )
                ),
            )
        ),
    )


# =========================================================
# STATUS / REFRESH
# =========================================================


@router.callback_query(
    ClosingCallback.filter(
        F.action.in_(
            {
                ClosingAction.STATUS,
                ClosingAction.REFRESH,
            }
        )
    )
)
async def closing_status_callback(
    callback: CallbackQuery,
    callback_data: ClosingCallback,
    **data: Any,
) -> None:
    """
    Поточний статус закриття.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    store_id = (
        callback_data.store_id
    )

    if store_id <= 0:
        return

    if not can_access_store(
        store_id=store_id,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    result = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    text = await build_closing_status_text(
        store_id=store_id,
        result=result,
        data=data,
    )

    if result_is_completed(
        result
    ):
        markup = (
            closing_already_done_keyboard(
                store_id=store_id
            )
        )

    elif result_exists(
        result
    ):
        amount = result_cash_amount(
            result
        )

        receipt = result_receipt_file_id(
            result
        )

        markup = closing_status_keyboard(
            store_id=store_id,
            has_cash=(
                amount is not None
            ),
            has_receipt=bool(
                receipt
            ),
            can_confirm=(
                amount is not None
                and bool(receipt)
            ),
        )

    else:
        markup = (
            closing_prepare_keyboard(
                store_id=store_id
            )
        )

    await safe_edit(
        callback,
        text=text,
        reply_markup=markup,
    )


# =========================================================
# FINAL CONFIRM
# =========================================================


@router.callback_query(
    ClosingCallback.filter(
        F.action
        == ClosingAction.CONFIRM
    )
)
async def closing_confirm_callback(
    callback: CallbackQuery,
    callback_data: ClosingCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Фінальне завершення зміни.
    """

    user = get_database_user(
        data
    )

    if user is None:
        return

    store_id = (
        callback_data.store_id
    )

    if not can_access_store(
        store_id=store_id,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    current = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    if result_is_completed(
        current
    ):
        await callback.answer(
            "Зміну вже завершено."
        )

        await show_closing_menu(
            callback,
            store_id=store_id,
            user=user,
            data=data,
        )

        return

    amount = result_cash_amount(
        current
    )

    receipt = result_receipt_file_id(
        current
    )

    if amount is None:
        await callback.answer(
            "Спочатку внесіть касу.",
            show_alert=True,
        )

        return

    if not receipt:
        await callback.answer(
            "Спочатку додайте фото чека.",
            show_alert=True,
        )

        return

    report_id = result_report_id(
        current
    )

    await callback.answer(
        "Завершую зміну…"
    )

    try:
        result = await complete_closing(
            store_id=store_id,
            report_id=report_id,
            user=user,
            data=data,
        )

    except Exception:
        logger.exception(
            "Closing completion failed: "
            "store_id=%s report_id=%s",
            store_id,
            report_id,
        )

        await callback.answer(
            "Не вдалося завершити зміну.",
            show_alert=True,
        )

        return

    if not result_success(
        result
    ):
        await callback.answer(
            result_message(
                result
            )
            or "Не вдалося завершити зміну.",
            show_alert=True,
        )

        return

    await state.clear()

    current = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    text = await build_closing_status_text(
        store_id=store_id,
        result=(
            current
            or result
        ),
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "✅ <b>Зміну успішно "
            "завершено.</b>\n\n"
            f"{text}"
        ),
        reply_markup=(
            closing_success_keyboard(
                store_id=store_id
            )
        ),
    )


# =========================================================
# MANUAL CLOSING
# =========================================================


@router.callback_query(
    ClosingCallback.filter(
        F.action
        == ClosingAction.MANUAL
    )
)
async def closing_manual_callback(
    callback: CallbackQuery,
    callback_data: ClosingCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Ручне коригування часу
    закриття адміністрацією.
    """

    user = get_database_user(
        data
    )

    if user is None:
        return

    role = first_attr(
        user,
        "role",
    )

    role_name = (
        str(
            first_attr(
                role,
                "name",
                "value",
                default=role,
            )
        )
        .upper()
        .replace(
            "-",
            "_",
        )
        .replace(
            " ",
            "_",
        )
    )

    if role_name not in {
        "ROOT_ADMIN",
        "DIRECTOR",
        "BUSH_ADMIN",
    }:
        await callback.answer(
            "Ручне коригування "
            "доступне лише адміністрації.",
            show_alert=True,
        )

        return

    store_id = (
        callback_data.store_id
    )

    if not can_access_store(
        store_id=store_id,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    current = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    report_id = result_report_id(
        current
    )

    await state.set_state(
        ClosingStates
        .waiting_manual_time
    )

    await state.update_data(
        closing_store_id=store_id,
        closing_report_id=report_id,
    )

    store = await load_store(
        store_id=store_id,
        data=data,
    )

    title = store_title(
        store,
        store_id=store_id,
    )

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "✏️ <b>Ручне коригування "
            "закриття</b>\n\n"
            f"🏪 {escape(title)}\n\n"
            "Введіть фактичний час "
            "закриття:\n\n"
            "<code>21:03</code>\n\n"
            "Для скасування:\n"
            "<code>/cancel</code>"
        ),
        reply_markup=None,
    )


# =========================================================
# PARSE MANUAL TIME
# =========================================================


def parse_manual_time(
    value: str,
):
    """
    HH:MM / HH.MM
    """

    normalized = (
        value.strip()
    )

    for fmt in (
        "%H:%M",
        "%H.%M",
    ):
        try:
            return datetime.strptime(
                normalized,
                fmt,
            ).time()

        except ValueError:
            continue

    return None


# =========================================================
# RECEIVE MANUAL TIME
# =========================================================


@router.message(
    ClosingStates.waiting_manual_time
)
async def closing_manual_time_handler(
    message: Message,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Ручний час закриття.
    """

    text = (
        message.text
        or ""
    ).strip()

    if text.lower() in {
        "/cancel",
        "cancel",
        "скасувати",
    }:
        await state.clear()

        await message.answer(
            "❌ Коригування скасовано.",
            reply_markup=(
                home_keyboard()
            ),
        )

        return

    parsed_time = parse_manual_time(
        text
    )

    if parsed_time is None:
        await message.answer(
            "⚠️ Невірний формат.\n\n"
            "Приклад:\n"
            "<code>21:03</code>"
        )

        return

    state_data = await state.get_data()

    store_id = to_int(
        state_data.get(
            "closing_store_id"
        )
    )

    report_id = to_int(
        state_data.get(
            "closing_report_id"
        )
    )

    user = get_database_user(
        data
    )

    if (
        store_id <= 0
        or user is None
    ):
        await state.clear()

        return

    current_local = now_local()

    corrected_at = datetime.combine(
        current_local.date(),
        parsed_time,
        tzinfo=KYIV_TZ,
    )

    try:
        result = await complete_closing(
            store_id=store_id,
            report_id=report_id,
            user=user,
            data=data,
            closed_at=corrected_at,
            manual=True,
        )

    except Exception:
        logger.exception(
            "Manual closing correction "
            "failed: store_id=%s",
            store_id,
        )

        await message.answer(
            "❌ Не вдалося виконати "
            "коригування."
        )

        return

    await state.clear()

    current = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    text = await build_closing_status_text(
        store_id=store_id,
        result=(
            current
            or result
        ),
        data=data,
    )

    await message.answer(
        "✅ <b>Час закриття "
        "скориговано.</b>\n\n"
        f"{text}",
        reply_markup=(
            closing_status_keyboard(
                store_id=store_id,
                has_cash=(
                    result_cash_amount(
                        current
                    )
                    is not None
                ),
                has_receipt=bool(
                    result_receipt_file_id(
                        current
                    )
                ),
                can_confirm=False,
            )
        ),
    )


# =========================================================
# BACK
# =========================================================


@router.callback_query(
    ClosingCallback.filter(
        F.action
        == ClosingAction.BACK
    )
)
async def closing_back_callback(
    callback: CallbackQuery,
    callback_data: ClosingCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Назад до картки ТТ.
    """

    await callback.answer()

    await state.clear()

    store_id = (
        callback_data.store_id
    )

    if store_id <= 0:
        await safe_edit(
            callback,
            text="🏠 Головне меню",
            reply_markup=(
                home_keyboard()
            ),
        )

        return

    store = await load_store(
        store_id=store_id,
        data=data,
    )

    title = store_title(
        store,
        store_id=store_id,
    )

    await safe_edit(
        callback,
        text=(
            "🏪 <b>Торгова точка</b>\n\n"
            f"{escape(title)}"
        ),
        reply_markup=(
            store_info_keyboard(
                store_id=store_id
            )
        ),
    )


# =========================================================
# UNKNOWN CASH CALLBACK
# =========================================================


@router.callback_query(
    CashCallback.filter()
)
async def unknown_cash_callback(
    callback: CallbackQuery,
) -> None:
    """
    Старий CashCallback.
    """

    await callback.answer(
        "Ця кнопка вже неактуальна.",
        show_alert=False,
    )


# =========================================================
# UNKNOWN CLOSING CALLBACK
# =========================================================


@router.callback_query(
    ClosingCallback.filter()
)
async def unknown_closing_callback(
    callback: CallbackQuery,
) -> None:
    """
    Старий ClosingCallback.
    """

    await callback.answer(
        "Ця кнопка вже неактуальна.",
        show_alert=False,
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "router",

    "ClosingStates",

    "MONEY_QUANT",
    "MAX_CASH_AMOUNT",

    "get_closing_service",
    "get_cash_service",
    "get_file_service",

    "result_success",
    "result_message",
    "result_report",
    "result_report_id",
    "result_cash_amount",
    "result_receipt_file_id",
    "result_closed_at",
    "result_started_at",
    "result_is_completed",
    "result_exists",

    "normalize_cash_text",
    "parse_cash_amount",
    "format_money",

    "get_closing_status",
    "start_closing",

    "save_cash_amount",

    "extract_receipt_file",
    "save_receipt",

    "complete_closing",

    "build_closing_status_text",

    "show_store_selection",
    "show_closing_menu",

    "parse_manual_time",
]