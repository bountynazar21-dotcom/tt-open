from __future__ import annotations

import inspect
import logging
from datetime import date
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)

from app.database.models.user import (
    User as DatabaseUser,
)
from app.handlers.closing import (
    build_closing_status_text,
    get_closing_status,
    result_cash_amount,
    result_exists as closing_exists,
    result_is_completed,
    result_receipt_file_id,
    result_report_id,
)
from app.handlers.common import (
    get_access_context,
    get_database_user,
    get_primary_store_id,
    safe_edit,
)
from app.handlers.opening import (
    build_opening_status_text,
    build_store_choices,
    call_method,
    can_access_store,
    first_attr,
    get_service,
    load_store,
    now_local,
    result_lateness_minutes,
    status_exists as opening_exists,
    store_title,
    to_bool,
    to_int,
)
from app.keyboards import (
    ClosingAction,
    ClosingCallback,
    MainMenuAction,
    MainMenuCallback,
    OpeningAction,
    OpeningCallback,
    ReportAction,
    ReportCallback,
    ScheduleAction,
    ScheduleCallback,
    StoreAction,
    StoreCallback,
    home_keyboard,
    inline_button,
)
from app.keyboards.store import (
    StoreDayState,
    StoreMenuState,
    closing_status_keyboard,
    opening_prepare_keyboard,
    opening_status_keyboard,
    select_store_keyboard,
    store_back_keyboard,
    store_info_keyboard,
    store_main_keyboard,
    store_today_report_keyboard,
    store_unavailable_keyboard,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="store",
)


# =========================================================
# CONSTANTS
# =========================================================


STORE_PAGE_SIZE = 12


# =========================================================
# GENERIC HELPERS
# =========================================================


def enum_text(
    value: Any,
) -> str:
    """
    Enum / str -> читабельний текст.
    """

    if value is None:
        return ""

    raw = first_attr(
        value,
        "value",
        "name",
        default=value,
    )

    return str(
        raw
    ).strip()


def is_store_active(
    store: Any,
) -> bool:
    """
    Чи активна ТТ.
    """

    value = first_attr(
        store,
        "is_active",
        "active",
        default=True,
    )

    return to_bool(
        value,
        default=True,
    )


def store_id_from_object(
    store: Any,
) -> int:
    """
    ID магазину.
    """

    return to_int(
        first_attr(
            store,
            "id",
            "store_id",
            default=0,
        )
    )


def store_bush_id(
    store: Any,
) -> int:
    """
    bush_id ТТ.
    """

    return to_int(
        first_attr(
            store,
            "bush_id",
            default=0,
        )
    )


def store_cluster_id(
    store: Any,
) -> int:
    """
    cluster_id ТТ.
    """

    return to_int(
        first_attr(
            store,
            "cluster_id",
            default=0,
        )
    )


# =========================================================
# SERVICES
# =========================================================


def get_schedule_service(
    data: dict[str, Any],
) -> Any | None:
    return get_service(
        data,
        "schedule",
        "schedules",
    )


def get_bush_service(
    data: dict[str, Any],
) -> Any | None:
    return get_service(
        data,
        "bushes",
        "bush",
    )


def get_cluster_service(
    data: dict[str, Any],
) -> Any | None:
    return get_service(
        data,
        "clusters",
        "cluster",
    )


def get_user_service(
    data: dict[str, Any],
) -> Any | None:
    return get_service(
        data,
        "users",
        "user",
    )


# =========================================================
# ACCESS
# =========================================================


def accessible_bush_ids(
    data: dict[str, Any],
) -> set[int]:
    """
    Кущі, доступні користувачу.
    """

    direct = data.get(
        "accessible_bush_ids"
    )

    if direct:
        return {
            to_int(item)
            for item in direct
            if to_int(item) > 0
        }

    context = get_access_context(
        data
    )

    if context is None:
        return set()

    values = getattr(
        context,
        "bush_ids",
        None,
    )

    if not values:
        return set()

    return {
        to_int(item)
        for item in values
        if to_int(item) > 0
    }


def network_access(
    data: dict[str, Any],
) -> bool:
    """
    Доступ до всієї мережі.
    """

    direct = data.get(
        "has_network_access"
    )

    if isinstance(
        direct,
        bool,
    ):
        return direct

    context = get_access_context(
        data
    )

    if context is None:
        return False

    return bool(
        getattr(
            context,
            "has_network_access",
            False,
        )
    )


async def can_view_store(
    *,
    store: Any,
    store_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> bool:
    """
    Перевірка доступу до ТТ.

    Підтримує:
        - глобальний доступ;
        - прямий доступ до ТТ;
        - доступ до куща;
        - AccessService.
    """

    if network_access(
        data
    ):
        return True

    if can_access_store(
        store_id=store_id,
        data=data,
    ):
        return True

    bush_id = store_bush_id(
        store
    )

    if (
        bush_id > 0
        and bush_id
        in accessible_bush_ids(
            data
        )
    ):
        return True

    # -----------------------------------------------------
    # ACCESS SERVICE
    # -----------------------------------------------------

    services = data.get(
        "services"
    )

    if (
        services is not None
        and user is not None
    ):
        try:
            access = services.access

        except Exception:
            access = None

        if access is not None:
            for method_name in (
                "can_view_store",
                "can_manage_store",
                "require_store_view",
            ):
                method = getattr(
                    access,
                    method_name,
                    None,
                )

                if not callable(
                    method
                ):
                    continue

                try:
                    result = method(
                        user=user,
                        store_id=store_id,
                    )

                except TypeError:
                    try:
                        result = method(
                            user,
                            store_id,
                        )

                    except TypeError:
                        continue

                if inspect.isawaitable(
                    result
                ):
                    result = await result

                if isinstance(
                    result,
                    bool,
                ):
                    return result

                # require_* не кинув exception
                if method_name.startswith(
                    "require_"
                ):
                    return True

                allowed = first_attr(
                    result,
                    "allowed",
                    "is_allowed",
                    "success",
                    default=None,
                )

                if allowed is not None:
                    return to_bool(
                        allowed
                    )

    return False


# =========================================================
# BUSH
# =========================================================


async def load_bush(
    *,
    bush_id: int,
    data: dict[str, Any],
) -> Any | None:
    """
    Отримує кущ.
    """

    if bush_id <= 0:
        return None

    service = get_bush_service(
        data
    )

    if service is not None:
        for method_name in (
            "get_bush",
            "get_bush_or_raise",
            "get_by_id",
            "get",
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
                    {
                        "bush_id": bush_id,
                        "id": bush_id,
                        "include_inactive":
                            True,
                    },
                )

            except Exception:
                continue

    repositories = data.get(
        "repositories"
    )

    if repositories is None:
        return None

    repository = getattr(
        repositories,
        "bushes",
        None,
    )

    if repository is None:
        return None

    for method_name in (
        "get_by_id",
        "get",
        "find_by_id",
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
                {
                    "id": bush_id,
                    "bush_id": bush_id,
                },
            )

        except Exception:
            continue

    return None


def bush_title(
    bush: Any,
) -> str:
    """
    Назва куща.
    """

    if bush is None:
        return "—"

    return str(
        first_attr(
            bush,
            "name",
            "title",
            default="—",
        )
    )


# =========================================================
# CLUSTER
# =========================================================


async def load_cluster(
    *,
    cluster_id: int,
    data: dict[str, Any],
) -> Any | None:
    """
    Отримує кластер.
    """

    if cluster_id <= 0:
        return None

    service = get_cluster_service(
        data
    )

    if service is not None:
        for method_name in (
            "get_cluster",
            "get_cluster_or_raise",
            "get_by_id",
            "get",
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
                    {
                        "cluster_id":
                            cluster_id,
                        "id":
                            cluster_id,
                        "include_inactive":
                            True,
                    },
                )

            except Exception:
                continue

    repositories = data.get(
        "repositories"
    )

    if repositories is None:
        return None

    repository = getattr(
        repositories,
        "clusters",
        None,
    )

    if repository is None:
        return None

    for method_name in (
        "get_by_id",
        "get",
        "find_by_id",
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
                {
                    "id": cluster_id,
                    "cluster_id":
                        cluster_id,
                },
            )

        except Exception:
            continue

    return None


def cluster_title(
    cluster: Any,
) -> str:
    """
    Назва + час кластера.
    """

    if cluster is None:
        return "—"

    name = first_attr(
        cluster,
        "name",
        "title",
        default=None,
    )

    opening_time = first_attr(
        cluster,
        "opening_time",
        "start_time",
        "time",
        default=None,
    )

    if (
        hasattr(
            opening_time,
            "strftime",
        )
    ):
        opening_text = (
            opening_time.strftime(
                "%H:%M"
            )
        )

    elif opening_time:
        opening_text = str(
            opening_time
        )

    else:
        opening_text = None

    if (
        opening_text
        and name
    ):
        return (
            f"{opening_text} · {name}"
        )

    if opening_text:
        return opening_text

    if name:
        return str(
            name
        )

    return "—"


# =========================================================
# SCHEDULE
# =========================================================


async def get_store_schedule(
    *,
    store_id: int,
    target_date: date,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> Any | None:
    """
    Ефективний графік ТТ на дату.
    """

    service = get_schedule_service(
        data
    )

    if service is None:
        return None

    payload = {
        "store_id": store_id,

        "date": target_date,
        "target_date": target_date,
        "work_date": target_date,

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
    }

    for method_name in (
        "get_effective_schedule",
        "get_store_schedule_for_date",
        "get_schedule_for_date",
        "resolve_schedule",
        "get_effective_for_date",
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

    return None


def format_schedule_time(
    value: Any,
) -> str:
    """
    time/datetime/string -> HH:MM.
    """

    if value is None:
        return "—"

    if hasattr(
        value,
        "strftime",
    ):
        try:
            return value.strftime(
                "%H:%M"
            )

        except Exception:
            pass

    return str(
        value
    )


def schedule_text(
    schedule: Any,
) -> str:
    """
    Формує короткий опис графіка.
    """

    if schedule is None:
        return "Графік не налаштований"

    is_working = first_attr(
        schedule,
        "is_working",
        "working",
        "is_open",
        default=True,
    )

    if not to_bool(
        is_working,
        default=True,
    ):
        return "Вихідний"

    opening = first_attr(
        schedule,
        "opening_time",
        "open_time",
        "start_time",
        default=None,
    )

    closing = first_attr(
        schedule,
        "closing_time",
        "close_time",
        "end_time",
        default=None,
    )

    if (
        opening is not None
        and closing is not None
    ):
        return (
            f"{format_schedule_time(opening)}"
            "–"
            f"{format_schedule_time(closing)}"
        )

    if opening is not None:
        return (
            "від "
            f"{format_schedule_time(opening)}"
        )

    return "Робочий день"


# =========================================================
# STORE DAY STATE
# =========================================================


async def build_store_menu_state(
    *,
    store_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> StoreMenuState:
    """
    Визначає стан зміни.
    """

    opening = await get_opening_status_safe(
        store_id=store_id,
        user=user,
        data=data,
    )

    closing = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    opened = opening_exists(
        opening
    )

    late_minutes = (
        result_lateness_minutes(
            opening
        )
        if opened
        else 0
    )

    has_closing = closing_exists(
        closing
    )

    closed = result_is_completed(
        closing
    )

    if closed:
        day_state = (
            StoreDayState.CLOSED
        )

    elif has_closing:
        day_state = (
            StoreDayState
            .CLOSING_STARTED
        )

    elif opened and late_minutes > 0:
        day_state = (
            StoreDayState.OPENED_LATE
        )

    elif opened:
        day_state = (
            StoreDayState.OPENED_ON_TIME
        )

    else:
        day_state = (
            StoreDayState.NOT_OPENED
        )

    return StoreMenuState(
        store_id=store_id,
        state=day_state,
        opening_lateness_minutes=(
            late_minutes
        ),
        has_cash=(
            result_cash_amount(
                closing
            )
            is not None
        ),
        has_receipt=bool(
            result_receipt_file_id(
                closing
            )
        ),
        closing_report_id=(
            result_report_id(
                closing
            )
        ),
    )


async def get_opening_status_safe(
    *,
    store_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> Any | None:
    """
    Імпорт локально,
    щоб не створювати зайвих циклів.
    """

    from app.handlers.opening import (
        get_opening_status,
    )

    return await get_opening_status(
        store_id=store_id,
        user=user,
        data=data,
    )


# =========================================================
# STORE CARD TEXT
# =========================================================


async def build_store_card_text(
    *,
    store: Any,
    store_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> str:
    """
    Повна картка ТТ.
    """

    title = store_title(
        store,
        store_id=store_id,
    )

    city = first_attr(
        store,
        "city",
        default=None,
    )

    address = first_attr(
        store,
        "address",
        "street",
        default=None,
    )

    bush_id = store_bush_id(
        store
    )

    cluster_id = store_cluster_id(
        store
    )

    bush = await load_bush(
        bush_id=bush_id,
        data=data,
    )

    cluster = await load_cluster(
        cluster_id=cluster_id,
        data=data,
    )

    schedule = await get_store_schedule(
        store_id=store_id,
        target_date=(
            now_local().date()
        ),
        user=user,
        data=data,
    )

    menu_state = (
        await build_store_menu_state(
            store_id=store_id,
            user=user,
            data=data,
        )
    )

    lines = [
        "🏪 <b>Торгова точка</b>",
        "",
        f"<b>{escape(title)}</b>",
    ]

    if city:
        lines.append(
            f"📍 {escape(str(city))}"
        )

    if address:
        lines.append(
            f"🏠 {escape(str(address))}"
        )

    lines.extend(
        [
            "",
            (
                "🌿 Кущ: "
                f"<b>{escape(bush_title(bush))}</b>"
            ),
            (
                "⏰ Кластер: "
                f"<b>{escape(cluster_title(cluster))}</b>"
            ),
            (
                "🕐 Сьогодні: "
                f"<b>{escape(schedule_text(schedule))}</b>"
            ),
            "",
        ]
    )

    if not is_store_active(
        store
    ):
        lines.append(
            "⚫ <b>ТТ неактивна</b>"
        )

    elif (
        menu_state.state
        == StoreDayState.NOT_OPENED
    ):
        lines.append(
            "⏳ <b>Сьогодні ще не відкрито</b>"
        )

    elif (
        menu_state.state
        == StoreDayState.OPENED_ON_TIME
    ):
        lines.append(
            "✅ <b>Магазин відкритий вчасно</b>"
        )

    elif (
        menu_state.state
        == StoreDayState.OPENED_LATE
    ):
        lines.append(
            "⚠️ <b>Магазин відкритий "
            f"із запізненням "
            f"{menu_state.opening_lateness_minutes} хв.</b>"
        )

    elif (
        menu_state.state
        == StoreDayState.CLOSING_STARTED
    ):
        lines.append(
            "🌙 <b>Закриття в процесі</b>"
        )

    elif (
        menu_state.state
        == StoreDayState.CLOSED
    ):
        lines.append(
            "✅ <b>Зміну завершено</b>"
        )

    return "\n".join(
        lines
    )


# =========================================================
# SHOW STORE
# =========================================================


async def show_store(
    *,
    callback: CallbackQuery,
    store_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> None:
    """
    Показ картки ТТ.
    """

    store = await load_store(
        store_id=store_id,
        data=data,
    )

    if store is None:
        await safe_edit(
            callback,
            text=(
                "❌ <b>Торгову точку "
                "не знайдено.</b>"
            ),
            reply_markup=(
                home_keyboard()
            ),
        )

        return

    allowed = await can_view_store(
        store=store,
        store_id=store_id,
        user=user,
        data=data,
    )

    if not allowed:
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    text = await build_store_card_text(
        store=store,
        store_id=store_id,
        user=user,
        data=data,
    )

    state = await build_store_menu_state(
        store_id=store_id,
        user=user,
        data=data,
    )

    if not is_store_active(
        store
    ):
        markup = (
            store_unavailable_keyboard()
        )

    else:
        markup = store_main_keyboard(
            state=state
        )

    await safe_edit(
        callback,
        text=text,
        reply_markup=markup,
    )


# =========================================================
# STORE SELECT FOR MESSAGE
# =========================================================


async def show_store_selector_message(
    message: Message,
    *,
    data: dict[str, Any],
) -> None:
    """
    Якщо в користувача кілька ТТ.
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
        await message.answer(
            "⚠️ До вашого профілю "
            "не прив'язано жодної ТТ.",
            reply_markup=(
                store_unavailable_keyboard()
            ),
        )

        return

    stores = await build_store_choices(
        store_ids=store_ids,
        data=data,
    )

    await message.answer(
        "🏪 <b>Оберіть торгову точку</b>",
        reply_markup=(
            select_store_keyboard(
                stores=stores,
                context="status",
            )
        ),
    )


# =========================================================
# /STORE /TT
# =========================================================


@router.message(
    Command(
        "store",
        "tt",
    )
)
async def store_command(
    message: Message,
    **data: Any,
) -> None:
    """
    /store
    /tt
    """

    user = get_database_user(
        data
    )

    if user is None:
        await message.answer(
            "⚠️ Користувача не знайдено."
        )

        return

    store_id = get_primary_store_id(
        data
    )

    if store_id is None:
        await show_store_selector_message(
            message,
            data=data,
        )

        return

    store = await load_store(
        store_id=store_id,
        data=data,
    )

    if store is None:
        await message.answer(
            "❌ Торгову точку не знайдено."
        )

        return

    allowed = await can_view_store(
        store=store,
        store_id=store_id,
        user=user,
        data=data,
    )

    if not allowed:
        await message.answer(
            "⛔ Немає доступу до цієї ТТ."
        )

        return

    text = await build_store_card_text(
        store=store,
        store_id=store_id,
        user=user,
        data=data,
    )

    state = await build_store_menu_state(
        store_id=store_id,
        user=user,
        data=data,
    )

    await message.answer(
        text,
        reply_markup=(
            store_main_keyboard(
                state=state
            )
            if is_store_active(store)
            else store_unavailable_keyboard()
        ),
    )


# =========================================================
# STORE VIEW
# =========================================================


@router.callback_query(
    StoreCallback.filter(
        F.action
        == StoreAction.VIEW
    )
)
async def store_view_callback(
    callback: CallbackQuery,
    callback_data: StoreCallback,
    **data: Any,
) -> None:
    """
    Картка ТТ.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    await show_store(
        callback=callback,
        store_id=(
            callback_data.store_id
        ),
        user=user,
        data=data,
    )


# =========================================================
# TODAY REPORT
# =========================================================


@router.callback_query(
    StoreCallback.filter(
        F.action
        == StoreAction.REPORT
    )
)
async def store_today_report_callback(
    callback: CallbackQuery,
    callback_data: StoreCallback,
    **data: Any,
) -> None:
    """
    Статус ТТ за сьогодні.
    """

    await callback.answer()

    store_id = (
        callback_data.store_id
    )

    user = get_database_user(
        data
    )

    store = await load_store(
        store_id=store_id,
        data=data,
    )

    if store is None:
        return

    if not await can_view_store(
        store=store,
        store_id=store_id,
        user=user,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    opening = await get_opening_status_safe(
        store_id=store_id,
        user=user,
        data=data,
    )

    closing = await get_closing_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    title = store_title(
        store,
        store_id=store_id,
    )

    lines = [
        "📊 <b>Статус за сьогодні</b>",
        "",
        f"🏪 <b>{escape(title)}</b>",
        "",
    ]

    # -----------------------------------------------------
    # OPENING
    # -----------------------------------------------------

    if opening_exists(
        opening
    ):
        late = result_lateness_minutes(
            opening
        )

        if late > 0:
            lines.append(
                "🌅 Відкриття: "
                f"<b>⚠️ +{late} хв.</b>"
            )

        else:
            lines.append(
                "🌅 Відкриття: "
                "<b>✅ вчасно</b>"
            )

    else:
        lines.append(
            "🌅 Відкриття: "
            "<b>⏳ немає</b>"
        )

    # -----------------------------------------------------
    # CLOSING
    # -----------------------------------------------------

    if result_is_completed(
        closing
    ):
        lines.append(
            "🌙 Закриття: "
            "<b>✅ завершено</b>"
        )

    elif closing_exists(
        closing
    ):
        lines.append(
            "🌙 Закриття: "
            "<b>🔄 в процесі</b>"
        )

    else:
        lines.append(
            "🌙 Закриття: "
            "<b>—</b>"
        )

    # -----------------------------------------------------
    # CASH
    # -----------------------------------------------------

    cash = result_cash_amount(
        closing
    )

    if cash is not None:
        lines.append(
            "💵 Каса: "
            f"<b>{escape(str(cash))} грн</b>"
        )

    # -----------------------------------------------------
    # RECEIPT
    # -----------------------------------------------------

    if result_receipt_file_id(
        closing
    ):
        lines.append(
            "📷 Чек: <b>✅ додано</b>"
        )

    elif closing_exists(
        closing
    ):
        lines.append(
            "📷 Чек: <b>❌ немає</b>"
        )

    await safe_edit(
        callback,
        text="\n".join(
            lines
        ),
        reply_markup=(
            store_today_report_keyboard(
                store_id=store_id,
                is_opened=(
                    opening_exists(
                        opening
                    )
                ),
                is_closed=(
                    result_is_completed(
                        closing
                    )
                ),
            )
        ),
    )


# =========================================================
# STORE SCHEDULE
# =========================================================


@router.callback_query(
    StoreCallback.filter(
        F.action
        == StoreAction.SCHEDULE
    )
)
async def store_schedule_callback(
    callback: CallbackQuery,
    callback_data: StoreCallback,
    **data: Any,
) -> None:
    """
    Графік ТТ.
    """

    await callback.answer()

    store_id = (
        callback_data.store_id
    )

    user = get_database_user(
        data
    )

    store = await load_store(
        store_id=store_id,
        data=data,
    )

    if store is None:
        return

    if not await can_view_store(
        store=store,
        store_id=store_id,
        user=user,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цієї ТТ.",
            show_alert=True,
        )

        return

    today = now_local().date()

    schedule = await get_store_schedule(
        store_id=store_id,
        target_date=today,
        user=user,
        data=data,
    )

    cluster = await load_cluster(
        cluster_id=(
            store_cluster_id(
                store
            )
        ),
        data=data,
    )

    title = store_title(
        store,
        store_id=store_id,
    )

    lines = [
        "🕐 <b>Графік торгової точки</b>",
        "",
        f"🏪 <b>{escape(title)}</b>",
        "",
        (
            "📅 Сьогодні: "
            f"<b>{escape(schedule_text(schedule))}</b>"
        ),
        (
            "⏰ Кластер: "
            f"<b>{escape(cluster_title(cluster))}</b>"
        ),
    ]

    await safe_edit(
        callback,
        text="\n".join(
            lines
        ),
        reply_markup=(
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        inline_button(
                            text="👁 Детальний графік",
                            callback=ScheduleCallback(
                                action=(
                                    ScheduleAction.VIEW
                                ),
                                store_id=store_id,
                                value=0,
                            ),
                        )
                    ],
                    [
                        inline_button(
                            text="🔙 До ТТ",
                            callback=StoreCallback(
                                action=(
                                    StoreAction.VIEW
                                ),
                                store_id=store_id,
                                page=0,
                            ),
                        )
                    ],
                ]
            )
        ),
    )


# =========================================================
# OPENING STATUS FROM STORE
# =========================================================


@router.callback_query(
    StoreCallback.filter(
        F.action
        == StoreAction.LIST
    )
)
async def store_list_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Список доступних ТТ користувача.

    Для глобальних списків директорів
    окремі handlers дадуть розширений UI.
    """

    await callback.answer()

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
                "🏪 <b>Торгові точки</b>\n\n"
                "Доступних ТТ немає."
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
            "🏪 <b>Оберіть торгову точку</b>"
        ),
        reply_markup=(
            select_store_keyboard(
                stores=stores,
                context="status",
            )
        ),
    )


# =========================================================
# STORE OPENING SHORTCUT
# =========================================================


async def show_opening_details(
    *,
    callback: CallbackQuery,
    store_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> None:
    """
    Допоміжний display opening.
    """

    result = await get_opening_status_safe(
        store_id=store_id,
        user=user,
        data=data,
    )

    if opening_exists(
        result
    ):
        text = await build_opening_status_text(
            store_id=store_id,
            result=result,
            data=data,
        )

        markup = opening_status_keyboard(
            store_id=store_id,
            can_close=True,
        )

    else:
        store = await load_store(
            store_id=store_id,
            data=data,
        )

        text = (
            "🌅 <b>Відкриття</b>\n\n"
            f"🏪 <b>{escape(store_title(store, store_id=store_id))}</b>\n\n"
            "Відкриття за сьогодні "
            "ще не зафіксовано."
        )

        markup = opening_prepare_keyboard(
            store_id=store_id
        )

    await safe_edit(
        callback,
        text=text,
        reply_markup=markup,
    )


# =========================================================
# STORE CLOSING SHORTCUT
# =========================================================


async def show_closing_details(
    *,
    callback: CallbackQuery,
    store_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> None:
    """
    Допоміжний display closing.
    """

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
            store_back_keyboard(
                store_id=store_id
            )
        )

    elif closing_exists(
        result
    ):
        cash = result_cash_amount(
            result
        )

        receipt = result_receipt_file_id(
            result
        )

        markup = closing_status_keyboard(
            store_id=store_id,
            has_cash=(
                cash is not None
            ),
            has_receipt=bool(
                receipt
            ),
            can_confirm=(
                cash is not None
                and bool(receipt)
            ),
        )

    else:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    inline_button(
                        text="🌙 Почати закриття",
                        callback=ClosingCallback(
                            action=(
                                ClosingAction.PREPARE
                            ),
                            store_id=store_id,
                        ),
                    )
                ],
                [
                    inline_button(
                        text="🔙 До ТТ",
                        callback=StoreCallback(
                            action=StoreAction.VIEW,
                            store_id=store_id,
                            page=0,
                        ),
                    )
                ],
            ]
        )

    await safe_edit(
        callback,
        text=text,
        reply_markup=markup,
    )


# =========================================================
# STORE PROFILE SHORTCUT
# =========================================================


@router.callback_query(
    MainMenuCallback.filter(
        F.action
        == MainMenuAction.OPENING
    )
)
async def main_menu_opening_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    MainMenu -> opening.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    store_id = get_primary_store_id(
        data
    )

    if store_id is None:
        await safe_edit(
            callback,
            text=(
                "🏪 Оберіть ТТ через "
                "розділ торгових точок."
            ),
            reply_markup=(
                home_keyboard()
            ),
        )

        return

    await show_opening_details(
        callback=callback,
        store_id=store_id,
        user=user,
        data=data,
    )


# =========================================================
# MAIN MENU CLOSING
# =========================================================


@router.callback_query(
    MainMenuCallback.filter(
        F.action
        == MainMenuAction.CLOSING
    )
)
async def main_menu_closing_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    MainMenu -> closing.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    store_id = get_primary_store_id(
        data
    )

    if store_id is None:
        await safe_edit(
            callback,
            text=(
                "🏪 Основну ТТ "
                "не визначено."
            ),
            reply_markup=(
                home_keyboard()
            ),
        )

        return

    await show_closing_details(
        callback=callback,
        store_id=store_id,
        user=user,
        data=data,
    )


# =========================================================
# NO GENERIC FALLBACK
# =========================================================
#
# Важливо:
#
# Тут НЕ ставимо:
#
#   @router.callback_query(
#       StoreCallback.filter()
#   )
#
# Бо StoreCallback використовується також:
#
#   bush_admin.py
#   director.py
#   root_admin.py
#   bindings.py
#
# І загальний fallback міг би
# перехопити їх callback раніше.
# =========================================================


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "router",

    "STORE_PAGE_SIZE",

    "enum_text",
    "is_store_active",
    "store_id_from_object",
    "store_bush_id",
    "store_cluster_id",

    "get_schedule_service",
    "get_bush_service",
    "get_cluster_service",
    "get_user_service",

    "accessible_bush_ids",
    "network_access",
    "can_view_store",

    "load_bush",
    "bush_title",

    "load_cluster",
    "cluster_title",

    "get_store_schedule",
    "format_schedule_time",
    "schedule_text",

    "get_opening_status_safe",
    "build_store_menu_state",

    "build_store_card_text",
    "show_store",

    "show_store_selector_message",

    "show_opening_details",
    "show_closing_details",
]