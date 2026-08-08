from __future__ import annotations

import logging
from html import escape
from typing import Any, Iterable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    Message,
)

from app.database.models.user import (
    User as DatabaseUser,
)
from app.handlers.closing import (
    get_closing_status,
    result_exists as closing_exists,
    result_is_completed,
)
from app.handlers.common import (
    get_access_context,
    get_database_user,
    get_primary_bush_id,
    safe_edit,
    user_role_name,
)
from app.handlers.opening import (
    call_method,
    first_attr,
    get_opening_status,
    get_service,
    load_store,
    result_lateness_minutes,
    status_exists as opening_exists,
    store_title,
    to_bool,
    to_int,
)
from app.handlers.store import (
    is_store_active,
    load_bush,
    store_bush_id,
)
from app.keyboards.lion import (
    LionAction,
    LionCallback,
    LionDashboardState,
    LionStoreItem,
    LionStoreState,
    lion_closing_keyboard,
    lion_late_keyboard,
    lion_main_keyboard,
    lion_missing_closing_keyboard,
    lion_missing_opening_keyboard,
    lion_no_stores_keyboard,
    lion_opening_keyboard,
    lion_reports_keyboard,
    lion_select_bush_keyboard,
    lion_stores_keyboard,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="lion",
)


# =========================================================
# CONSTANTS
# =========================================================


PAGE_SIZE = 10


ALLOWED_ROLES = {
    "LION",
    "BUSH_ADMIN",
    "DIRECTOR",
    "ROOT_ADMIN",
}


# =========================================================
# GENERIC HELPERS
# =========================================================


def unwrap_collection(
    result: Any,
) -> list[Any]:
    """
    Нормалізує різні відповіді repository/service:

        list
        tuple
        set
        result.items
        result.stores
        result.results
        result.data
    """

    if result is None:
        return []

    if isinstance(
        result,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        return list(
            result
        )

    for field_name in (
        "items",
        "stores",
        "results",
        "data",
        "records",
    ):
        value = first_attr(
            result,
            field_name,
            default=None,
        )

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
                frozenset,
            ),
        ):
            return list(
                value
            )

    try:
        if (
            not isinstance(
                result,
                (
                    str,
                    bytes,
                    dict,
                ),
            )
            and isinstance(
                result,
                Iterable,
            )
        ):
            return list(
                result
            )

    except TypeError:
        pass

    return [
        result
    ]


def paginate(
    items: list[Any],
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> tuple[
    list[Any],
    int,
    int,
]:
    """
    Повертає:

        page_items
        normalized_page
        total_pages
    """

    if page_size < 1:
        page_size = PAGE_SIZE

    total_items = len(
        items
    )

    if total_items == 0:
        return (
            [],
            0,
            1,
        )

    total_pages = (
        total_items
        + page_size
        - 1
    ) // page_size

    normalized_page = max(
        0,
        min(
            page,
            total_pages - 1,
        ),
    )

    start = (
        normalized_page
        * page_size
    )

    end = (
        start
        + page_size
    )

    return (
        items[
            start:end
        ],
        normalized_page,
        total_pages,
    )


# =========================================================
# ROLE
# =========================================================


def can_use_lion_panel(
    user: DatabaseUser | None,
) -> bool:
    """
    Панель Лева доступна:

        LION
        BUSH_ADMIN
        DIRECTOR
        ROOT_ADMIN
    """

    if user is None:
        return False

    return (
        user_role_name(
            user
        )
        in ALLOWED_ROLES
    )


# =========================================================
# ACCESS
# =========================================================


def has_network_access(
    data: dict[str, Any],
) -> bool:
    """
    Чи користувач бачить всю мережу.
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


def accessible_bush_ids(
    data: dict[str, Any],
) -> set[int]:
    """
    Доступні кущі.
    """

    direct = data.get(
        "accessible_bush_ids"
    )

    if direct:
        return {
            to_int(
                bush_id
            )
            for bush_id in direct
            if to_int(
                bush_id
            ) > 0
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
        to_int(
            bush_id
        )
        for bush_id in values
        if to_int(
            bush_id
        ) > 0
    }


def accessible_store_ids(
    data: dict[str, Any],
) -> set[int]:
    """
    Доступні ТТ.
    """

    direct = data.get(
        "accessible_store_ids"
    )

    if direct:
        return {
            to_int(
                store_id
            )
            for store_id in direct
            if to_int(
                store_id
            ) > 0
        }

    context = get_access_context(
        data
    )

    if context is None:
        return set()

    values = getattr(
        context,
        "store_ids",
        None,
    )

    if not values:
        return set()

    return {
        to_int(
            store_id
        )
        for store_id in values
        if to_int(
            store_id
        ) > 0
    }


def can_view_bush(
    *,
    bush_id: int,
    data: dict[str, Any],
) -> bool:
    """
    Перевірка доступу до куща.
    """

    if bush_id <= 0:
        return False

    if has_network_access(
        data
    ):
        return True

    return (
        bush_id
        in accessible_bush_ids(
            data
        )
    )


def resolve_bush_id(
    *,
    requested_bush_id: int,
    data: dict[str, Any],
) -> int | None:
    """
    Визначає поточний кущ.

    Пріоритет:

        1. callback bush_id
        2. primary bush
        3. єдиний доступний bush
    """

    if requested_bush_id > 0:
        return requested_bush_id

    primary = get_primary_bush_id(
        data
    )

    if primary:
        return primary

    bushes = sorted(
        accessible_bush_ids(
            data
        )
    )

    if len(
        bushes
    ) == 1:
        return bushes[0]

    return None


# =========================================================
# BUSH TITLE
# =========================================================


async def get_bush_title(
    *,
    bush_id: int,
    data: dict[str, Any],
) -> str:
    """
    Назва куща.
    """

    bush = await load_bush(
        bush_id=bush_id,
        data=data,
    )

    if bush is None:
        return (
            f"Кущ #{bush_id}"
        )

    name = first_attr(
        bush,
        "name",
        "title",
        default=None,
    )

    if name:
        return str(
            name
        )

    return (
        f"Кущ #{bush_id}"
    )


# =========================================================
# SELECT BUSH
# =========================================================


async def build_bush_choices(
    *,
    data: dict[str, Any],
) -> list[
    tuple[int, str]
]:
    """
    Список доступних кущів
    для keyboard.
    """

    result: list[
        tuple[int, str]
    ] = []

    for bush_id in sorted(
        accessible_bush_ids(
            data
        )
    ):
        title = await get_bush_title(
            bush_id=bush_id,
            data=data,
        )

        result.append(
            (
                bush_id,
                title,
            )
        )

    return result


async def show_bush_selection_callback(
    callback: CallbackQuery,
    *,
    data: dict[str, Any],
) -> None:
    """
    Якщо доступно кілька кущів.
    """

    bushes = await build_bush_choices(
        data=data
    )

    if not bushes:
        await safe_edit(
            callback,
            text=(
                "🦁 <b>Панель Лева</b>\n\n"
                "⚠️ До вашого профілю "
                "не прив'язано жодного куща."
            ),
            reply_markup=(
                lion_no_stores_keyboard()
            ),
        )

        return

    await safe_edit(
        callback,
        text=(
            "🦁 <b>Панель Лева</b>\n\n"
            "🌿 Оберіть кущ:"
        ),
        reply_markup=(
            lion_select_bush_keyboard(
                bushes=bushes
            )
        ),
    )


async def show_bush_selection_message(
    message: Message,
    *,
    data: dict[str, Any],
) -> None:
    """
    Те саме через command.
    """

    bushes = await build_bush_choices(
        data=data
    )

    if not bushes:
        await message.answer(
            "🦁 <b>Панель Лева</b>\n\n"
            "⚠️ До вашого профілю "
            "не прив'язано жодного куща.",
            reply_markup=(
                lion_no_stores_keyboard()
            ),
        )

        return

    await message.answer(
        "🦁 <b>Панель Лева</b>\n\n"
        "🌿 Оберіть кущ:",
        reply_markup=(
            lion_select_bush_keyboard(
                bushes=bushes
            )
        ),
    )


# =========================================================
# STORE COLLECTION
# =========================================================


def store_object_id(
    store: Any,
) -> int:
    """
    ID Store.
    """

    if isinstance(
        store,
        int,
    ):
        return (
            store
            if store > 0
            else 0
        )

    return to_int(
        first_attr(
            store,
            "id",
            "store_id",
            default=0,
        )
    )


async def query_bush_stores(
    *,
    bush_id: int,
    data: dict[str, Any],
) -> list[Any]:
    """
    Пробує отримати ТТ куща
    через StoreService / BushService /
    StoreRepository.
    """

    payload = {
        "bush_id":
            bush_id,

        "active_only":
            False,

        "include_inactive":
            True,
    }

    # -----------------------------------------------------
    # STORE SERVICE
    # -----------------------------------------------------

    store_service = get_service(
        data,
        "stores",
        "store",
    )

    if store_service is not None:
        for method_name in (
            "list_by_bush",
            "get_by_bush",
            "get_bush_stores",
            "list_bush_stores",
            "get_stores_by_bush",
        ):
            method = getattr(
                store_service,
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

            except Exception:
                continue

            items = unwrap_collection(
                result
            )

            if items:
                return items

    # -----------------------------------------------------
    # BUSH SERVICE
    # -----------------------------------------------------

    bush_service = get_service(
        data,
        "bushes",
        "bush",
    )

    if bush_service is not None:
        for method_name in (
            "get_bush_stores",
            "get_stores",
            "list_stores",
            "list_bush_stores",
        ):
            method = getattr(
                bush_service,
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

            except Exception:
                continue

            items = unwrap_collection(
                result
            )

            if items:
                return items

    # -----------------------------------------------------
    # REPOSITORY
    # -----------------------------------------------------

    repositories = data.get(
        "repositories"
    )

    if repositories is None:
        return []

    repository = getattr(
        repositories,
        "stores",
        None,
    )

    if repository is None:
        return []

    for method_name in (
        "list_by_bush",
        "get_by_bush",
        "get_bush_stores",
        "list_bush_stores",
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
            result = await call_method(
                method,
                payload,
            )

        except Exception:
            continue

        items = unwrap_collection(
            result
        )

        if items:
            return items

    return []


async def load_lion_stores(
    *,
    bush_id: int,
    data: dict[str, Any],
) -> list[Any]:
    """
    Завантажує ТТ конкретного куща.

    Спочатку використовує прямі
    store bindings користувача.

    Якщо у Лева доступ заданий
    на рівні куща — отримує всі
    ТТ цього куща.
    """

    if bush_id <= 0:
        return []

    direct_store_ids = (
        accessible_store_ids(
            data
        )
    )

    stores: list[Any] = []

    # -----------------------------------------------------
    # DIRECT STORE ACCESS
    # -----------------------------------------------------

    if direct_store_ids:
        for store_id in sorted(
            direct_store_ids
        ):
            store = await load_store(
                store_id=store_id,
                data=data,
            )

            if store is None:
                continue

            item_bush_id = (
                store_bush_id(
                    store
                )
            )

            if (
                item_bush_id > 0
                and item_bush_id
                != bush_id
            ):
                continue

            stores.append(
                store
            )

    # -----------------------------------------------------
    # BUSH ACCESS
    # -----------------------------------------------------

    if (
        can_view_bush(
            bush_id=bush_id,
            data=data,
        )
        or has_network_access(
            data
        )
    ):
        bush_stores = (
            await query_bush_stores(
                bush_id=bush_id,
                data=data,
            )
        )

        stores.extend(
            bush_stores
        )

    # -----------------------------------------------------
    # NORMALIZE / LOAD IDS
    # -----------------------------------------------------

    normalized: dict[
        int,
        Any,
    ] = {}

    for item in stores:
        if isinstance(
            item,
            int,
        ):
            store = await load_store(
                store_id=item,
                data=data,
            )

        else:
            store = item

        if store is None:
            continue

        store_id = store_object_id(
            store
        )

        if store_id <= 0:
            continue

        item_bush_id = (
            store_bush_id(
                store
            )
        )

        if (
            item_bush_id > 0
            and item_bush_id
            != bush_id
        ):
            continue

        normalized[
            store_id
        ] = store

    return sorted(
        normalized.values(),
        key=lambda store: (
            str(
                first_attr(
                    store,
                    "code",
                    "store_code",
                    default="",
                )
            ),
            store_object_id(
                store
            ),
        ),
    )


# =========================================================
# STORE STATE
# =========================================================


async def build_lion_store_item(
    *,
    store: Any,
    user: DatabaseUser | None,
    data: dict[str, Any],
    context: str = "general",
) -> LionStoreItem:
    """
    Створює LionStoreItem
    на основі реального стану ТТ.

    context:
        general
        opening
        closing
    """

    store_id = store_object_id(
        store
    )

    opening = await get_opening_status(
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

    active = is_store_active(
        store
    )

    # -----------------------------------------------------
    # INACTIVE
    # -----------------------------------------------------

    if not active:
        state = (
            LionStoreState.INACTIVE
        )

    # -----------------------------------------------------
    # CLOSING VIEW
    # -----------------------------------------------------

    elif context == "closing":
        if closed:
            state = (
                LionStoreState.CLOSED
            )

        elif has_closing:
            state = (
                LionStoreState
                .CLOSING_IN_PROGRESS
            )

        elif opened:
            state = (
                LionStoreState
                .WAITING_CLOSING
            )

        else:
            state = (
                LionStoreState
                .WAITING_OPENING
            )

    # -----------------------------------------------------
    # OPENING / GENERAL VIEW
    # -----------------------------------------------------

    elif opened:
        if late_minutes > 0:
            state = (
                LionStoreState
                .OPENED_LATE
            )

        else:
            state = (
                LionStoreState
                .OPENED_ON_TIME
            )

    else:
        state = (
            LionStoreState
            .WAITING_OPENING
        )

    code = str(
        first_attr(
            store,
            "code",
            "store_code",
            default=(
                f"ТТ-{store_id}"
            ),
        )
    )

    name = first_attr(
        store,
        "name",
        "title",
        default=None,
    )

    return LionStoreItem(
        store_id=store_id,
        code=code,
        name=(
            str(name)
            if name
            else None
        ),
        state=state,
        lateness_minutes=(
            late_minutes
        ),
    )


async def build_lion_store_items(
    *,
    stores: list[Any],
    user: DatabaseUser | None,
    data: dict[str, Any],
    context: str = "general",
) -> list[
    LionStoreItem
]:
    """
    Статуси всіх ТТ.
    """

    result: list[
        LionStoreItem
    ] = []

    for store in stores:
        try:
            item = (
                await build_lion_store_item(
                    store=store,
                    user=user,
                    data=data,
                    context=context,
                )
            )

        except Exception:
            logger.exception(
                "Failed building Lion store "
                "item for store_id=%s",
                store_object_id(
                    store
                ),
            )

            continue

        result.append(
            item
        )

    return result


# =========================================================
# DASHBOARD
# =========================================================


async def build_lion_dashboard(
    *,
    bush_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> tuple[
    LionDashboardState,
    list[Any],
]:
    """
    Рахує dashboard Лева.
    """

    stores = await load_lion_stores(
        bush_id=bush_id,
        data=data,
    )

    active_stores = [
        store
        for store in stores
        if is_store_active(
            store
        )
    ]

    opening_items = (
        await build_lion_store_items(
            stores=active_stores,
            user=user,
            data=data,
            context="opening",
        )
    )

    closing_items = (
        await build_lion_store_items(
            stores=active_stores,
            user=user,
            data=data,
            context="closing",
        )
    )

    opened_count = sum(
        1
        for item in opening_items
        if item.state
        in {
            LionStoreState
            .OPENED_ON_TIME,

            LionStoreState
            .OPENED_LATE,
        }
    )

    late_count = sum(
        1
        for item in opening_items
        if item.state
        == LionStoreState.OPENED_LATE
    )

    missing_opening_count = sum(
        1
        for item in opening_items
        if item.state
        == LionStoreState
        .WAITING_OPENING
    )

    closed_count = sum(
        1
        for item in closing_items
        if item.state
        == LionStoreState.CLOSED
    )

    closing_in_progress_count = sum(
        1
        for item in closing_items
        if item.state
        == LionStoreState
        .CLOSING_IN_PROGRESS
    )

    # Не показуємо "не закрилися"
    # весь день до початку вечірньої
    # фази закриття.
    closing_phase_started = (
        closed_count > 0
        or closing_in_progress_count > 0
    )

    if closing_phase_started:
        missing_closing_count = sum(
            1
            for item in closing_items
            if item.state
            == LionStoreState
            .WAITING_CLOSING
        )

    else:
        missing_closing_count = 0

    state = LionDashboardState(
        bush_id=bush_id,

        total_stores=len(
            active_stores
        ),

        opened_count=opened_count,

        late_count=late_count,

        missing_opening_count=(
            missing_opening_count
        ),

        closed_count=closed_count,

        missing_closing_count=(
            missing_closing_count
        ),

        closing_in_progress_count=(
            closing_in_progress_count
        ),
    )

    return (
        state,
        stores,
    )


# =========================================================
# DASHBOARD TEXT
# =========================================================


async def build_dashboard_text(
    *,
    state: LionDashboardState,
    data: dict[str, Any],
) -> str:
    """
    Текст dashboard.
    """

    bush_name = await get_bush_title(
        bush_id=state.bush_id,
        data=data,
    )

    lines = [
        "🦁 <b>Панель Лева</b>",
        "",
        (
            "🌿 Кущ: "
            f"<b>{escape(bush_name)}</b>"
        ),
        "",
        (
            "🏪 Активних ТТ: "
            f"<b>{state.total_stores}</b>"
        ),
        "",
        (
            "🌅 Відкрилися: "
            f"<b>{state.opened_count}/"
            f"{state.total_stores}</b>"
        ),
    ]

    if state.late_count > 0:
        lines.append(
            "⚠️ Запізнилися: "
            f"<b>{state.late_count}</b>"
        )

    if (
        state.missing_opening_count
        > 0
    ):
        lines.append(
            "🚨 Ще не відкрилися: "
            f"<b>{state.missing_opening_count}</b>"
        )

    lines.extend(
        [
            "",
            (
                "🌙 Закрилися: "
                f"<b>{state.closed_count}/"
                f"{state.total_stores}</b>"
            ),
        ]
    )

    if (
        state.closing_in_progress_count
        > 0
    ):
        lines.append(
            "🔄 Закриття в процесі: "
            f"<b>{state.closing_in_progress_count}</b>"
        )

    if (
        state.missing_closing_count
        > 0
    ):
        lines.append(
            "🚨 Ще не закрилися: "
            f"<b>{state.missing_closing_count}</b>"
        )

    return "\n".join(
        lines
    )


# =========================================================
# SHOW DASHBOARD
# =========================================================


async def show_lion_dashboard_callback(
    callback: CallbackQuery,
    *,
    bush_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> None:
    """
    Dashboard через callback.
    """

    if not can_view_bush(
        bush_id=bush_id,
        data=data,
    ):
        await callback.answer(
            "Немає доступу до цього куща.",
            show_alert=True,
        )

        return

    state, stores = (
        await build_lion_dashboard(
            bush_id=bush_id,
            user=user,
            data=data,
        )
    )

    if not stores:
        bush_name = await get_bush_title(
            bush_id=bush_id,
            data=data,
        )

        await safe_edit(
            callback,
            text=(
                "🦁 <b>Панель Лева</b>\n\n"
                f"🌿 {escape(bush_name)}\n\n"
                "⚠️ У цьому кущі немає "
                "доступних торгових точок."
            ),
            reply_markup=(
                lion_no_stores_keyboard(
                    bush_id=bush_id
                )
            ),
        )

        return

    text = await build_dashboard_text(
        state=state,
        data=data,
    )

    await safe_edit(
        callback,
        text=text,
        reply_markup=(
            lion_main_keyboard(
                state=state
            )
        ),
    )


async def show_lion_dashboard_message(
    message: Message,
    *,
    bush_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> None:
    """
    Dashboard через /lion.
    """

    if not can_view_bush(
        bush_id=bush_id,
        data=data,
    ):
        await message.answer(
            "⛔ Немає доступу "
            "до цього куща."
        )

        return

    state, stores = (
        await build_lion_dashboard(
            bush_id=bush_id,
            user=user,
            data=data,
        )
    )

    if not stores:
        bush_name = await get_bush_title(
            bush_id=bush_id,
            data=data,
        )

        await message.answer(
            "🦁 <b>Панель Лева</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            "⚠️ У цьому кущі немає "
            "доступних торгових точок.",
            reply_markup=(
                lion_no_stores_keyboard(
                    bush_id=bush_id
                )
            ),
        )

        return

    text = await build_dashboard_text(
        state=state,
        data=data,
    )

    await message.answer(
        text,
        reply_markup=(
            lion_main_keyboard(
                state=state
            )
        ),
    )


# =========================================================
# /LION
# =========================================================


@router.message(
    Command("lion")
)
async def lion_command(
    message: Message,
    **data: Any,
) -> None:
    """
    /lion
    """

    user = get_database_user(
        data
    )

    if not can_use_lion_panel(
        user
    ):
        await message.answer(
            "⛔ Панель Лева "
            "вам недоступна."
        )

        return

    bush_id = resolve_bush_id(
        requested_bush_id=0,
        data=data,
    )

    if bush_id is None:
        await show_bush_selection_message(
            message,
            data=data,
        )

        return

    await show_lion_dashboard_message(
        message,
        bush_id=bush_id,
        user=user,
        data=data,
    )


# =========================================================
# MENU / DASHBOARD / REFRESH
# =========================================================


@router.callback_query(
    LionCallback.filter(
        F.action.in_(
            {
                LionAction.MENU,
                LionAction.DASHBOARD,
                LionAction.REFRESH,
            }
        )
    )
)
async def lion_dashboard_callback(
    callback: CallbackQuery,
    callback_data: LionCallback,
    **data: Any,
) -> None:
    """
    Головна панель.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    if not can_use_lion_panel(
        user
    ):
        await callback.answer(
            "Панель Лева недоступна.",
            show_alert=True,
        )

        return

    bush_id = resolve_bush_id(
        requested_bush_id=(
            callback_data.bush_id
        ),
        data=data,
    )

    if bush_id is None:
        await show_bush_selection_callback(
            callback,
            data=data,
        )

        return

    await show_lion_dashboard_callback(
        callback,
        bush_id=bush_id,
        user=user,
        data=data,
    )


# =========================================================
# STORES
# =========================================================


@router.callback_query(
    LionCallback.filter(
        F.action
        == LionAction.STORES
    )
)
async def lion_stores_callback(
    callback: CallbackQuery,
    callback_data: LionCallback,
    **data: Any,
) -> None:
    """
    Всі ТТ Лева.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    bush_id = resolve_bush_id(
        requested_bush_id=(
            callback_data.bush_id
        ),
        data=data,
    )

    if (
        bush_id is None
        or not can_view_bush(
            bush_id=bush_id,
            data=data,
        )
    ):
        await callback.answer(
            "Немає доступу до куща.",
            show_alert=True,
        )

        return

    stores = await load_lion_stores(
        bush_id=bush_id,
        data=data,
    )

    items = await build_lion_store_items(
        stores=stores,
        user=user,
        data=data,
        context="general",
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        items,
        page=callback_data.page,
    )

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "🏪 <b>Торгові точки</b>\n\n"
            f"🌿 {escape(bush_name)}\n"
            f"Усього: <b>{len(items)}</b>"
        ),
        reply_markup=(
            lion_stores_keyboard(
                bush_id=bush_id,
                stores=page_items,
                page=page,
                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# OPENING
# =========================================================


@router.callback_query(
    LionCallback.filter(
        F.action
        == LionAction.OPENING
    )
)
async def lion_opening_callback(
    callback: CallbackQuery,
    callback_data: LionCallback,
    **data: Any,
) -> None:
    """
    Live відкриття.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    bush_id = resolve_bush_id(
        requested_bush_id=(
            callback_data.bush_id
        ),
        data=data,
    )

    if (
        bush_id is None
        or not can_view_bush(
            bush_id=bush_id,
            data=data,
        )
    ):
        await callback.answer(
            "Немає доступу до куща.",
            show_alert=True,
        )

        return

    stores = await load_lion_stores(
        bush_id=bush_id,
        data=data,
    )

    stores = [
        store
        for store in stores
        if is_store_active(
            store
        )
    ]

    items = await build_lion_store_items(
        stores=stores,
        user=user,
        data=data,
        context="opening",
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        items,
        page=callback_data.page,
    )

    opened_count = sum(
        1
        for item in items
        if item.state
        in {
            LionStoreState.OPENED_ON_TIME,
            LionStoreState.OPENED_LATE,
        }
    )

    late_count = sum(
        1
        for item in items
        if item.state
        == LionStoreState.OPENED_LATE
    )

    missing_count = sum(
        1
        for item in items
        if item.state
        == LionStoreState.WAITING_OPENING
    )

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "🌅 <b>Live — відкриття</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            f"✅ Відкрилися: "
            f"<b>{opened_count}/{len(items)}</b>\n"
            f"⚠️ Із запізненням: "
            f"<b>{late_count}</b>\n"
            f"🚨 Ще не відкрилися: "
            f"<b>{missing_count}</b>"
        ),
        reply_markup=(
            lion_opening_keyboard(
                bush_id=bush_id,
                stores=page_items,
                page=page,
                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# LATE
# =========================================================


@router.callback_query(
    LionCallback.filter(
        F.action
        == LionAction.LATE
    )
)
async def lion_late_callback(
    callback: CallbackQuery,
    callback_data: LionCallback,
    **data: Any,
) -> None:
    """
    Тільки запізнення.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    bush_id = resolve_bush_id(
        requested_bush_id=(
            callback_data.bush_id
        ),
        data=data,
    )

    if (
        bush_id is None
        or not can_view_bush(
            bush_id=bush_id,
            data=data,
        )
    ):
        await callback.answer(
            "Немає доступу до куща.",
            show_alert=True,
        )

        return

    stores = await load_lion_stores(
        bush_id=bush_id,
        data=data,
    )

    items = await build_lion_store_items(
        stores=[
            store
            for store in stores
            if is_store_active(
                store
            )
        ],
        user=user,
        data=data,
        context="opening",
    )

    late_items = [
        item
        for item in items
        if item.state
        == LionStoreState.OPENED_LATE
    ]

    late_items.sort(
        key=lambda item:
            item.lateness_minutes,
        reverse=True,
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        late_items,
        page=callback_data.page,
    )

    total_minutes = sum(
        item.lateness_minutes
        for item in late_items
    )

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "⚠️ <b>Запізнення</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            f"ТТ із запізненням: "
            f"<b>{len(late_items)}</b>\n"
            f"Сумарно хвилин: "
            f"<b>{total_minutes}</b>"
        ),
        reply_markup=(
            lion_late_keyboard(
                bush_id=bush_id,
                stores=page_items,
                page=page,
                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# MISSING OPENING
# =========================================================


@router.callback_query(
    LionCallback.filter(
        F.action
        == LionAction.MISSING_OPENING
    )
)
async def lion_missing_opening_callback(
    callback: CallbackQuery,
    callback_data: LionCallback,
    **data: Any,
) -> None:
    """
    Хто не відкрився.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    bush_id = resolve_bush_id(
        requested_bush_id=(
            callback_data.bush_id
        ),
        data=data,
    )

    if (
        bush_id is None
        or not can_view_bush(
            bush_id=bush_id,
            data=data,
        )
    ):
        await callback.answer(
            "Немає доступу до куща.",
            show_alert=True,
        )

        return

    stores = await load_lion_stores(
        bush_id=bush_id,
        data=data,
    )

    items = await build_lion_store_items(
        stores=[
            store
            for store in stores
            if is_store_active(
                store
            )
        ],
        user=user,
        data=data,
        context="opening",
    )

    missing_items = [
        item
        for item in items
        if item.state
        == LionStoreState.WAITING_OPENING
    ]

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        missing_items,
        page=callback_data.page,
    )

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "🚨 <b>Не відкрилися</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            f"Без check-in: "
            f"<b>{len(missing_items)}</b>"
        ),
        reply_markup=(
            lion_missing_opening_keyboard(
                bush_id=bush_id,
                stores=page_items,
                page=page,
                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# CLOSING
# =========================================================


@router.callback_query(
    LionCallback.filter(
        F.action
        == LionAction.CLOSING
    )
)
async def lion_closing_callback(
    callback: CallbackQuery,
    callback_data: LionCallback,
    **data: Any,
) -> None:
    """
    Live закриття.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    bush_id = resolve_bush_id(
        requested_bush_id=(
            callback_data.bush_id
        ),
        data=data,
    )

    if (
        bush_id is None
        or not can_view_bush(
            bush_id=bush_id,
            data=data,
        )
    ):
        await callback.answer(
            "Немає доступу до куща.",
            show_alert=True,
        )

        return

    stores = await load_lion_stores(
        bush_id=bush_id,
        data=data,
    )

    items = await build_lion_store_items(
        stores=[
            store
            for store in stores
            if is_store_active(
                store
            )
        ],
        user=user,
        data=data,
        context="closing",
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        items,
        page=callback_data.page,
    )

    closed_count = sum(
        1
        for item in items
        if item.state
        == LionStoreState.CLOSED
    )

    progress_count = sum(
        1
        for item in items
        if item.state
        == LionStoreState.CLOSING_IN_PROGRESS
    )

    waiting_count = sum(
        1
        for item in items
        if item.state
        == LionStoreState.WAITING_CLOSING
    )

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "🌙 <b>Live — закриття</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            f"✅ Закрилися: "
            f"<b>{closed_count}/{len(items)}</b>\n"
            f"🔄 Закриваються: "
            f"<b>{progress_count}</b>\n"
            f"⏳ Очікують закриття: "
            f"<b>{waiting_count}</b>"
        ),
        reply_markup=(
            lion_closing_keyboard(
                bush_id=bush_id,
                stores=page_items,
                page=page,
                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# MISSING CLOSING
# =========================================================


@router.callback_query(
    LionCallback.filter(
        F.action
        == LionAction.MISSING_CLOSING
    )
)
async def lion_missing_closing_callback(
    callback: CallbackQuery,
    callback_data: LionCallback,
    **data: Any,
) -> None:
    """
    ТТ без завершеного закриття.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    bush_id = resolve_bush_id(
        requested_bush_id=(
            callback_data.bush_id
        ),
        data=data,
    )

    if (
        bush_id is None
        or not can_view_bush(
            bush_id=bush_id,
            data=data,
        )
    ):
        await callback.answer(
            "Немає доступу до куща.",
            show_alert=True,
        )

        return

    stores = await load_lion_stores(
        bush_id=bush_id,
        data=data,
    )

    items = await build_lion_store_items(
        stores=[
            store
            for store in stores
            if is_store_active(
                store
            )
        ],
        user=user,
        data=data,
        context="closing",
    )

    # У список проблемних закриттів
    # включаємо магазини, які:
    # - відкриті;
    # - ще не почали закриття.
    missing_items = [
        item
        for item in items
        if item.state
        == LionStoreState.WAITING_CLOSING
    ]

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        missing_items,
        page=callback_data.page,
    )

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "🚨 <b>Не закрилися</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            f"Очікують завершення: "
            f"<b>{len(missing_items)}</b>"
        ),
        reply_markup=(
            lion_missing_closing_keyboard(
                bush_id=bush_id,
                stores=page_items,
                page=page,
                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# REPORTS
# =========================================================


@router.callback_query(
    LionCallback.filter(
        F.action
        == LionAction.REPORTS
    )
)
async def lion_reports_callback(
    callback: CallbackQuery,
    callback_data: LionCallback,
    **data: Any,
) -> None:
    """
    Звіти куща.
    """

    await callback.answer()

    bush_id = resolve_bush_id(
        requested_bush_id=(
            callback_data.bush_id
        ),
        data=data,
    )

    if (
        bush_id is None
        or not can_view_bush(
            bush_id=bush_id,
            data=data,
        )
    ):
        await callback.answer(
            "Немає доступу до куща.",
            show_alert=True,
        )

        return

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "📊 <b>Звіти Лева</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            "Оберіть потрібний період:"
        ),
        reply_markup=(
            lion_reports_keyboard(
                bush_id=bush_id
            )
        ),
    )


# =========================================================
# BACK
# =========================================================


@router.callback_query(
    LionCallback.filter(
        F.action
        == LionAction.BACK
    )
)
async def lion_back_callback(
    callback: CallbackQuery,
    callback_data: LionCallback,
    **data: Any,
) -> None:
    """
    Повернення до dashboard.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    bush_id = resolve_bush_id(
        requested_bush_id=(
            callback_data.bush_id
        ),
        data=data,
    )

    if bush_id is None:
        await show_bush_selection_callback(
            callback,
            data=data,
        )

        return

    await show_lion_dashboard_callback(
        callback,
        bush_id=bush_id,
        user=user,
        data=data,
    )


# =========================================================
# UNKNOWN
# =========================================================


@router.callback_query(
    LionCallback.filter()
)
async def unknown_lion_callback(
    callback: CallbackQuery,
) -> None:
    """
    Старі / невідомі callback.
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

    "PAGE_SIZE",
    "ALLOWED_ROLES",

    "unwrap_collection",
    "paginate",

    "can_use_lion_panel",

    "has_network_access",
    "accessible_bush_ids",
    "accessible_store_ids",
    "can_view_bush",
    "resolve_bush_id",

    "get_bush_title",
    "build_bush_choices",

    "show_bush_selection_callback",
    "show_bush_selection_message",

    "store_object_id",
    "query_bush_stores",
    "load_lion_stores",

    "build_lion_store_item",
    "build_lion_store_items",

    "build_lion_dashboard",
    "build_dashboard_text",

    "show_lion_dashboard_callback",
    "show_lion_dashboard_message",
]