from __future__ import annotations

import logging
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    Message,
)

from app.database.models.user import (
    User as DatabaseUser,
)
from app.handlers.bush_admin import (
    build_keyboard,
    create_model,
    enum_member,
    normalized_role,
    role_label,
    unwrap_collection,
    user_display_name,
    user_is_active,
)
from app.handlers.closing import (
    get_closing_status,
    result_exists as closing_exists,
    result_is_completed,
)
from app.handlers.common import (
    get_access_context,
    get_database_user,
    safe_edit,
    user_role_name,
)
from app.handlers.lion import (
    get_bush_title,
    load_lion_stores,
    paginate,
)
from app.handlers.opening import (
    call_method,
    first_attr,
    get_opening_status,
    get_service,
    result_lateness_minutes,
    status_exists as opening_exists,
    to_bool,
    to_int,
)
from app.handlers.store import (
    bush_title,
    is_store_active,
    load_bush,
    store_bush_id,
)
from app.keyboards.director import (
    DirectorAction,
    DirectorBushItem,
    DirectorCallback,
    DirectorDashboardState,
    DirectorStoreItem,
    DirectorStoreState,
    DirectorUserItem,
    director_bushes_keyboard,
    director_closing_keyboard,
    director_invites_keyboard,
    director_late_keyboard,
    director_main_keyboard,
    director_missing_closing_keyboard,
    director_missing_opening_keyboard,
    director_no_bushes_keyboard,
    director_no_stores_keyboard,
    director_opening_keyboard,
    director_reports_keyboard,
    director_stores_keyboard,
    director_users_keyboard,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="director",
)


# =========================================================
# CONSTANTS
# =========================================================


PAGE_SIZE = 10


ALLOWED_ROLES = {
    "DIRECTOR",
    "ROOT_ADMIN",
}


# =========================================================
# ROLE ACCESS
# =========================================================


def can_use_director_panel(
    user: DatabaseUser | None,
) -> bool:
    """
    Панель директора доступна:
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
# ACCESS CONTEXT
# =========================================================


def has_network_access(
    data: dict[str, Any],
) -> bool:
    """
    Чи користувач має глобальний
    доступ до мережі.
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
                item
            )
            for item in direct
            if to_int(
                item
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
            item
        )
        for item in values
        if to_int(
            item
        ) > 0
    }


def accessible_store_ids(
    data: dict[str, Any],
) -> set[int]:
    """
    Прямо прив'язані ТТ.
    """

    direct = data.get(
        "accessible_store_ids"
    )

    if direct:
        return {
            to_int(
                item
            )
            for item in direct
            if to_int(
                item
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
            item
        )
        for item in values
        if to_int(
            item
        ) > 0
    }


# =========================================================
# OBJECT HELPERS
# =========================================================


def object_id(
    value: Any,
) -> int:
    """
    ID будь-якої ORM сутності.
    """

    if isinstance(
        value,
        int,
    ):
        return max(
            0,
            value,
        )

    return max(
        0,
        to_int(
            first_attr(
                value,
                "id",
                "store_id",
                "bush_id",
                "user_id",
                default=0,
            )
        ),
    )


def object_is_active(
    value: Any,
) -> bool:
    """
    Активність ORM сутності.
    """

    direct = first_attr(
        value,
        "is_active",
        "active",
        default=None,
    )

    if direct is not None:
        return to_bool(
            direct,
            default=True,
        )

    return True


# =========================================================
# QUERY BUSHES
# =========================================================


async def query_network_bushes(
    *,
    data: dict[str, Any],
) -> list[Any]:
    """
    Отримує всі доступні кущі.
    """

    payload = {
        "active_only": False,
        "include_inactive": True,
    }

    service = get_service(
        data,
        "bushes",
        "bush",
    )

    if service is not None:
        for method_name in (
            "list_bushes",
            "list_all",
            "get_all",
            "list",
            "all",
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

            except Exception:
                continue

            items = unwrap_collection(
                result
            )

            if items:
                return filter_accessible_bushes(
                    items,
                    data=data,
                )

    repositories = data.get(
        "repositories"
    )

    if repositories is None:
        return []

    repository = getattr(
        repositories,
        "bushes",
        None,
    )

    if repository is None:
        return []

    for method_name in (
        "list_all",
        "get_all",
        "list",
        "all",
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
            return filter_accessible_bushes(
                items,
                data=data,
            )

    return []


def filter_accessible_bushes(
    bushes: list[Any],
    *,
    data: dict[str, Any],
) -> list[Any]:
    """
    Фільтрація кущів по access context.
    """

    if has_network_access(
        data
    ):
        return bushes

    allowed = accessible_bush_ids(
        data
    )

    if not allowed:
        return []

    return [
        bush
        for bush in bushes
        if object_id(
            bush
        ) in allowed
    ]


# =========================================================
# NETWORK STORES
# =========================================================


async def query_all_stores(
    *,
    data: dict[str, Any],
) -> list[Any]:
    """
    Отримує всі доступні ТТ.

    Якщо директор має network access —
    пробує отримати всі ТТ напряму.

    Інакше збирає ТТ із доступних кущів.
    """

    stores: list[Any] = []

    # -----------------------------------------------------
    # GLOBAL QUERY
    # -----------------------------------------------------

    if has_network_access(
        data
    ):
        payload = {
            "active_only": False,
            "include_inactive": True,
        }

        service = get_service(
            data,
            "stores",
            "store",
        )

        if service is not None:
            for method_name in (
                "list_stores",
                "list_all",
                "get_all",
                "list",
                "all",
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

                except Exception:
                    continue

                items = unwrap_collection(
                    result
                )

                if items:
                    stores.extend(
                        items
                    )
                    break

        if not stores:
            repositories = data.get(
                "repositories"
            )

            repository = (
                getattr(
                    repositories,
                    "stores",
                    None,
                )
                if repositories
                else None
            )

            if repository is not None:
                for method_name in (
                    "list_all",
                    "get_all",
                    "list",
                    "all",
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
                        stores.extend(
                            items
                        )
                        break

    # -----------------------------------------------------
    # ACCESSIBLE BUSHES
    # -----------------------------------------------------

    if not stores:
        for bush_id in sorted(
            accessible_bush_ids(
                data
            )
        ):
            bush_stores = (
                await load_lion_stores(
                    bush_id=bush_id,
                    data=data,
                )
            )

            stores.extend(
                bush_stores
            )

    # -----------------------------------------------------
    # DIRECT STORE BINDINGS
    # -----------------------------------------------------

    direct_ids = (
        accessible_store_ids(
            data
        )
    )

    for store_id in direct_ids:
        service = get_service(
            data,
            "stores",
            "store",
        )

        store = None

        if service is not None:
            for method_name in (
                "get_store",
                "get_store_or_raise",
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
                    store = await call_method(
                        method,
                        {
                            "store_id":
                                store_id,

                            "id":
                                store_id,

                            "include_inactive":
                                True,
                        },
                    )

                except Exception:
                    continue

                if store is not None:
                    break

        if store is not None:
            stores.append(
                store
            )

    # -----------------------------------------------------
    # DEDUPLICATE
    # -----------------------------------------------------

    normalized: dict[
        int,
        Any,
    ] = {}

    for store in stores:
        store_id = object_id(
            store
        )

        if store_id <= 0:
            continue

        normalized[
            store_id
        ] = store

    return sorted(
        normalized.values(),
        key=lambda item: (
            str(
                first_attr(
                    item,
                    "code",
                    "store_code",
                    default="",
                )
            ),
            object_id(
                item
            ),
        ),
    )


# =========================================================
# NETWORK USERS
# =========================================================


async def query_network_users(
    *,
    data: dict[str, Any],
) -> list[Any]:
    """
    Користувачі мережі.
    """

    payload = {
        "active_only": False,
        "include_inactive": True,
    }

    service = get_service(
        data,
        "users",
        "user",
    )

    if service is not None:
        for method_name in (
            "list_users",
            "list_all",
            "get_all",
            "list",
            "search",
            "all",
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

            except Exception:
                continue

            items = unwrap_collection(
                result
            )

            if items:
                return items

    repositories = data.get(
        "repositories"
    )

    if repositories is None:
        return []

    repository = getattr(
        repositories,
        "users",
        None,
    )

    if repository is None:
        return []

    for method_name in (
        "list_all",
        "get_all",
        "list",
        "all",
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


# =========================================================
# STORE LABELS
# =========================================================


def store_code(
    store: Any,
) -> str:
    """
    Код ТТ.
    """

    store_id = object_id(
        store
    )

    code = first_attr(
        store,
        "code",
        "store_code",
        default=None,
    )

    if code:
        return str(
            code
        )

    return (
        f"ТТ-{store_id}"
    )


def store_name(
    store: Any,
) -> str | None:
    """
    Назва ТТ.
    """

    value = first_attr(
        store,
        "name",
        "title",
        "address",
        default=None,
    )

    if value:
        return str(
            value
        )

    return None


async def store_bush_name(
    *,
    store: Any,
    data: dict[str, Any],
) -> str | None:
    """
    Назва куща ТТ.
    """

    bush_id = store_bush_id(
        store
    )

    if bush_id <= 0:
        return None

    bush = await load_bush(
        bush_id=bush_id,
        data=data,
    )

    if bush is not None:
        value = first_attr(
            bush,
            "name",
            "title",
            default=None,
        )

        if value:
            return str(
                value
            )

    return (
        f"Кущ #{bush_id}"
    )


# =========================================================
# STORE STATE
# =========================================================


async def build_director_store_item(
    *,
    store: Any,
    user: DatabaseUser | None,
    data: dict[str, Any],
    context: str = "general",
) -> DirectorStoreItem:
    """
    Store -> DirectorStoreItem.
    """

    store_id = object_id(
        store
    )

    active = is_store_active(
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

    closing_started = closing_exists(
        closing
    )

    closed = result_is_completed(
        closing
    )

    # -----------------------------------------------------
    # STATE
    # -----------------------------------------------------

    if not active:
        state = enum_member(
            DirectorStoreState,
            "INACTIVE",
        )

    elif closed:
        state = enum_member(
            DirectorStoreState,
            "CLOSED",
        )

    elif context == "closing":
        if closing_started:
            state = enum_member(
                DirectorStoreState,
                "CLOSING_IN_PROGRESS",
                "CLOSING_STARTED",
                "WAITING_CLOSING",
            )

        elif opened:
            state = enum_member(
                DirectorStoreState,
                "WAITING_CLOSING",
                "OPENED_ON_TIME",
            )

        else:
            state = enum_member(
                DirectorStoreState,
                "WAITING_OPENING",
                "NOT_OPENED",
            )

    elif opened:
        if late_minutes > 0:
            state = enum_member(
                DirectorStoreState,
                "OPENED_LATE",
            )

        else:
            state = enum_member(
                DirectorStoreState,
                "OPENED_ON_TIME",
            )

    else:
        state = enum_member(
            DirectorStoreState,
            "WAITING_OPENING",
            "NOT_OPENED",
        )

    bush_name = await store_bush_name(
        store=store,
        data=data,
    )

    return create_model(
        DirectorStoreItem,

        store_id=store_id,

        code=store_code(
            store
        ),

        name=store_name(
            store
        ),

        bush_name=bush_name,

        state=state,

        lateness_minutes=(
            late_minutes
        ),

        is_active=active,
    )


async def build_director_store_items(
    *,
    stores: list[Any],
    user: DatabaseUser | None,
    data: dict[str, Any],
    context: str = "general",
) -> list[
    DirectorStoreItem
]:
    """
    Статуси всіх ТТ.
    """

    result: list[
        DirectorStoreItem
    ] = []

    for store in stores:
        try:
            item = (
                await build_director_store_item(
                    store=store,
                    user=user,
                    data=data,
                    context=context,
                )
            )

        except Exception:
            logger.exception(
                "Failed building DirectorStoreItem "
                "for store_id=%s",
                object_id(
                    store
                ),
            )

            continue

        result.append(
            item
        )

    return result


# =========================================================
# BUSH ITEMS
# =========================================================


async def count_bush_stores(
    *,
    bush_id: int,
    data: dict[str, Any],
) -> int:
    """
    Кількість ТТ у кущі.
    """

    stores = await load_lion_stores(
        bush_id=bush_id,
        data=data,
    )

    return len(
        stores
    )


async def build_director_bush_items(
    *,
    bushes: list[Any],
    data: dict[str, Any],
) -> list[
    DirectorBushItem
]:
    """
    Bush ORM -> DirectorBushItem.
    """

    result: list[
        DirectorBushItem
    ] = []

    for bush in bushes:
        bush_id = object_id(
            bush
        )

        if bush_id <= 0:
            continue

        name = first_attr(
            bush,
            "name",
            "title",
            default=(
                f"Кущ #{bush_id}"
            ),
        )

        stores_count = (
            await count_bush_stores(
                bush_id=bush_id,
                data=data,
            )
        )

        item = create_model(
            DirectorBushItem,

            bush_id=bush_id,

            name=str(
                name
            ),

            stores_count=(
                stores_count
            ),

            is_active=(
                object_is_active(
                    bush
                )
            ),
        )

        result.append(
            item
        )

    return result


# =========================================================
# USER ITEMS
# =========================================================


def build_director_user_item(
    user: Any,
) -> DirectorUserItem:
    """
    User -> DirectorUserItem.
    """

    username = first_attr(
        user,
        "username",
        default=None,
    )

    role_name = normalized_role(
        user
    )

    return create_model(
        DirectorUserItem,

        user_id=object_id(
            user
        ),

        display_name=(
            user_display_name(
                user
            )
        ),

        name=(
            user_display_name(
                user
            )
        ),

        role_text=(
            role_label(
                role_name
            )
        ),

        role=role_name,

        username=(
            str(username)
            if username
            else None
        ),

        is_active=(
            user_is_active(
                user
            )
        ),
    )


# =========================================================
# DASHBOARD
# =========================================================


async def build_director_dashboard(
    *,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> tuple[
    DirectorDashboardState,
    list[Any],
    list[Any],
    list[Any],
]:
    """
    Мережевий dashboard.
    """

    stores = await query_all_stores(
        data=data
    )

    bushes = await query_network_bushes(
        data=data
    )

    users = await query_network_users(
        data=data
    )

    active_stores = [
        store
        for store in stores
        if is_store_active(
            store
        )
    ]

    opening_items = (
        await build_director_store_items(
            stores=active_stores,
            user=user,
            data=data,
            context="opening",
        )
    )

    closing_items = (
        await build_director_store_items(
            stores=active_stores,
            user=user,
            data=data,
            context="closing",
        )
    )

    opened_on_time_state = (
        enum_member(
            DirectorStoreState,
            "OPENED_ON_TIME",
        )
    )

    opened_late_state = (
        enum_member(
            DirectorStoreState,
            "OPENED_LATE",
        )
    )

    waiting_opening_state = (
        enum_member(
            DirectorStoreState,
            "WAITING_OPENING",
            "NOT_OPENED",
        )
    )

    closed_state = (
        enum_member(
            DirectorStoreState,
            "CLOSED",
        )
    )

    closing_progress_state = (
        enum_member(
            DirectorStoreState,
            "CLOSING_IN_PROGRESS",
            "CLOSING_STARTED",
            "WAITING_CLOSING",
        )
    )

    waiting_closing_state = (
        enum_member(
            DirectorStoreState,
            "WAITING_CLOSING",
            "OPENED_ON_TIME",
        )
    )

    opened_count = sum(
        1
        for item in opening_items
        if first_attr(
            item,
            "state",
        )
        in {
            opened_on_time_state,
            opened_late_state,
        }
    )

    late_count = sum(
        1
        for item in opening_items
        if first_attr(
            item,
            "state",
        )
        == opened_late_state
    )

    missing_opening_count = sum(
        1
        for item in opening_items
        if first_attr(
            item,
            "state",
        )
        == waiting_opening_state
    )

    closed_count = sum(
        1
        for item in closing_items
        if first_attr(
            item,
            "state",
        )
        == closed_state
    )

    closing_in_progress_count = sum(
        1
        for item in closing_items
        if first_attr(
            item,
            "state",
        )
        == closing_progress_state
    )

    closing_phase_started = (
        closed_count > 0
        or closing_in_progress_count > 0
    )

    if closing_phase_started:
        missing_closing_count = sum(
            1
            for item in closing_items
            if first_attr(
                item,
                "state",
            )
            == waiting_closing_state
        )

    else:
        missing_closing_count = 0

    active_users_count = sum(
        1
        for item in users
        if user_is_active(
            item
        )
    )

    state = create_model(
        DirectorDashboardState,

        total_stores=len(
            active_stores
        ),

        active_stores=len(
            active_stores
        ),

        inactive_stores=(
            len(stores)
            - len(active_stores)
        ),

        bushes_count=len(
            bushes
        ),

        users_count=len(
            users
        ),

        active_users_count=(
            active_users_count
        ),

        opened_count=(
            opened_count
        ),

        late_count=(
            late_count
        ),

        missing_opening_count=(
            missing_opening_count
        ),

        closed_count=(
            closed_count
        ),

        closing_in_progress_count=(
            closing_in_progress_count
        ),

        missing_closing_count=(
            missing_closing_count
        ),
    )

    return (
        state,
        stores,
        bushes,
        users,
    )


# =========================================================
# DASHBOARD TEXT
# =========================================================


def build_dashboard_text(
    state: DirectorDashboardState,
) -> str:
    """
    Текст головної панелі директора.
    """

    total_stores = to_int(
        first_attr(
            state,
            "total_stores",
            "active_stores",
            default=0,
        )
    )

    bushes_count = to_int(
        first_attr(
            state,
            "bushes_count",
            default=0,
        )
    )

    users_count = to_int(
        first_attr(
            state,
            "users_count",
            default=0,
        )
    )

    opened_count = to_int(
        first_attr(
            state,
            "opened_count",
            default=0,
        )
    )

    late_count = to_int(
        first_attr(
            state,
            "late_count",
            default=0,
        )
    )

    missing_opening = to_int(
        first_attr(
            state,
            "missing_opening_count",
            default=0,
        )
    )

    closed_count = to_int(
        first_attr(
            state,
            "closed_count",
            default=0,
        )
    )

    closing_progress = to_int(
        first_attr(
            state,
            "closing_in_progress_count",
            default=0,
        )
    )

    missing_closing = to_int(
        first_attr(
            state,
            "missing_closing_count",
            default=0,
        )
    )

    lines = [
        "🏢 <b>Панель директора</b>",
        "",
        "🌐 <b>Вся мережа</b>",
        "",
        (
            "🌿 Кущів: "
            f"<b>{bushes_count}</b>"
        ),
        (
            "🏪 Активних ТТ: "
            f"<b>{total_stores}</b>"
        ),
        (
            "👥 Користувачів: "
            f"<b>{users_count}</b>"
        ),
        "",
        (
            "🌅 Відкрилися: "
            f"<b>{opened_count}/{total_stores}</b>"
        ),
    ]

    if late_count > 0:
        lines.append(
            "⚠️ Запізнилися: "
            f"<b>{late_count}</b>"
        )

    if missing_opening > 0:
        lines.append(
            "🚨 Не відкрилися: "
            f"<b>{missing_opening}</b>"
        )

    lines.extend(
        [
            "",
            (
                "🌙 Закрилися: "
                f"<b>{closed_count}/{total_stores}</b>"
            ),
        ]
    )

    if closing_progress > 0:
        lines.append(
            "🔄 Закриття в процесі: "
            f"<b>{closing_progress}</b>"
        )

    if missing_closing > 0:
        lines.append(
            "🚨 Не закрилися: "
            f"<b>{missing_closing}</b>"
        )

    return "\n".join(
        lines
    )


# =========================================================
# SHOW DASHBOARD
# =========================================================


async def show_dashboard_callback(
    callback: CallbackQuery,
    *,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> None:
    """
    Dashboard callback.
    """

    state, stores, bushes, users = (
        await build_director_dashboard(
            user=user,
            data=data,
        )
    )

    await safe_edit(
        callback,
        text=(
            build_dashboard_text(
                state
            )
        ),
        reply_markup=(
            build_keyboard(
                director_main_keyboard,

                state=state,
            )
        ),
    )


async def show_dashboard_message(
    message: Message,
    *,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> None:
    """
    Dashboard command.
    """

    state, stores, bushes, users = (
        await build_director_dashboard(
            user=user,
            data=data,
        )
    )

    await message.answer(
        build_dashboard_text(
            state
        ),
        reply_markup=(
            build_keyboard(
                director_main_keyboard,

                state=state,
            )
        ),
    )


# =========================================================
# /DIRECTOR
# =========================================================


@router.message(
    Command(
        "director",
        "network",
    )
)
async def director_command(
    message: Message,
    **data: Any,
) -> None:
    """
    /director
    /network
    """

    user = get_database_user(
        data
    )

    if not can_use_director_panel(
        user
    ):
        await message.answer(
            "⛔ Панель директора "
            "вам недоступна."
        )

        return

    await show_dashboard_message(
        message,
        user=user,
        data=data,
    )


# =========================================================
# MENU / DASHBOARD / REFRESH
# =========================================================


@router.callback_query(
    DirectorCallback.filter(
        F.action.in_(
            {
                DirectorAction.MENU,
                DirectorAction.DASHBOARD,
                DirectorAction.REFRESH,
            }
        )
    )
)
async def director_dashboard_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Головна панель директора.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    if not can_use_director_panel(
        user
    ):
        await callback.answer(
            "Панель директора недоступна.",
            show_alert=True,
        )

        return

    await show_dashboard_callback(
        callback,
        user=user,
        data=data,
    )


# =========================================================
# BUSHES
# =========================================================


@router.callback_query(
    DirectorCallback.filter(
        F.action
        == DirectorAction.BUSHES
    )
)
async def director_bushes_callback(
    callback: CallbackQuery,
    callback_data: DirectorCallback,
    **data: Any,
) -> None:
    """
    Список кущів.
    """

    await callback.answer()

    bushes = await query_network_bushes(
        data=data
    )

    items = await build_director_bush_items(
        bushes=bushes,
        data=data,
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        items,
        page=callback_data.page,
        page_size=PAGE_SIZE,
    )

    if not items:
        await safe_edit(
            callback,
            text=(
                "🌿 <b>Кущі</b>\n\n"
                "Кущів не знайдено."
            ),
            reply_markup=(
                build_keyboard(
                    director_no_bushes_keyboard
                )
            ),
        )

        return

    await safe_edit(
        callback,
        text=(
            "🌿 <b>Кущі мережі</b>\n\n"
            f"Усього: <b>{len(items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                director_bushes_keyboard,

                bushes=page_items,

                page=page,

                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# STORES
# =========================================================


@router.callback_query(
    DirectorCallback.filter(
        F.action
        == DirectorAction.STORES
    )
)
async def director_stores_callback(
    callback: CallbackQuery,
    callback_data: DirectorCallback,
    **data: Any,
) -> None:
    """
    Усі ТТ.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    stores = await query_all_stores(
        data=data
    )

    items = (
        await build_director_store_items(
            stores=stores,
            user=user,
            data=data,
            context="general",
        )
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        items,
        page=callback_data.page,
        page_size=PAGE_SIZE,
    )

    if not items:
        await safe_edit(
            callback,
            text=(
                "🏪 <b>Торгові точки</b>\n\n"
                "ТТ не знайдено."
            ),
            reply_markup=(
                build_keyboard(
                    director_no_stores_keyboard
                )
            ),
        )

        return

    active_count = sum(
        1
        for store in stores
        if is_store_active(
            store
        )
    )

    await safe_edit(
        callback,
        text=(
            "🏪 <b>Торгові точки мережі</b>\n\n"
            f"Усього: <b>{len(items)}</b>\n"
            f"Активних: <b>{active_count}</b>"
        ),
        reply_markup=(
            build_keyboard(
                director_stores_keyboard,

                stores=page_items,

                page=page,

                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# USERS
# =========================================================


@router.callback_query(
    DirectorCallback.filter(
        F.action
        == DirectorAction.USERS
    )
)
async def director_users_callback(
    callback: CallbackQuery,
    callback_data: DirectorCallback,
    **data: Any,
) -> None:
    """
    Користувачі мережі.
    """

    await callback.answer()

    users = await query_network_users(
        data=data
    )

    items = [
        build_director_user_item(
            user
        )
        for user in users
    ]

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        items,
        page=callback_data.page,
        page_size=PAGE_SIZE,
    )

    active_count = sum(
        1
        for user in users
        if user_is_active(
            user
        )
    )

    await safe_edit(
        callback,
        text=(
            "👥 <b>Користувачі мережі</b>\n\n"
            f"Усього: <b>{len(items)}</b>\n"
            f"Активних: <b>{active_count}</b>"
        ),
        reply_markup=(
            build_keyboard(
                director_users_keyboard,

                users=page_items,

                page=page,

                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# OPENING
# =========================================================


@router.callback_query(
    DirectorCallback.filter(
        F.action
        == DirectorAction.OPENING
    )
)
async def director_opening_callback(
    callback: CallbackQuery,
    callback_data: DirectorCallback,
    **data: Any,
) -> None:
    """
    Live відкриття мережі.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    stores = [
        store
        for store in (
            await query_all_stores(
                data=data
            )
        )
        if is_store_active(
            store
        )
    ]

    items = (
        await build_director_store_items(
            stores=stores,
            user=user,
            data=data,
            context="opening",
        )
    )

    opened_on_time_state = (
        enum_member(
            DirectorStoreState,
            "OPENED_ON_TIME",
        )
    )

    opened_late_state = (
        enum_member(
            DirectorStoreState,
            "OPENED_LATE",
        )
    )

    waiting_state = (
        enum_member(
            DirectorStoreState,
            "WAITING_OPENING",
            "NOT_OPENED",
        )
    )

    opened_count = sum(
        1
        for item in items
        if first_attr(
            item,
            "state",
        )
        in {
            opened_on_time_state,
            opened_late_state,
        }
    )

    late_count = sum(
        1
        for item in items
        if first_attr(
            item,
            "state",
        )
        == opened_late_state
    )

    missing_count = sum(
        1
        for item in items
        if first_attr(
            item,
            "state",
        )
        == waiting_state
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        items,
        page=callback_data.page,
        page_size=PAGE_SIZE,
    )

    await safe_edit(
        callback,
        text=(
            "🌅 <b>Live — відкриття мережі</b>\n\n"
            f"✅ Відкрилися: "
            f"<b>{opened_count}/{len(items)}</b>\n"
            f"⚠️ Запізнилися: "
            f"<b>{late_count}</b>\n"
            f"🚨 Не відкрилися: "
            f"<b>{missing_count}</b>"
        ),
        reply_markup=(
            build_keyboard(
                director_opening_keyboard,

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
    DirectorCallback.filter(
        F.action
        == DirectorAction.LATE
    )
)
async def director_late_callback(
    callback: CallbackQuery,
    callback_data: DirectorCallback,
    **data: Any,
) -> None:
    """
    Усі запізнення мережі.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    stores = [
        store
        for store in (
            await query_all_stores(
                data=data
            )
        )
        if is_store_active(
            store
        )
    ]

    items = (
        await build_director_store_items(
            stores=stores,
            user=user,
            data=data,
            context="opening",
        )
    )

    late_state = enum_member(
        DirectorStoreState,
        "OPENED_LATE",
    )

    late_items = [
        item
        for item in items
        if first_attr(
            item,
            "state",
        )
        == late_state
    ]

    late_items.sort(
        key=lambda item:
            to_int(
                first_attr(
                    item,
                    "lateness_minutes",
                    default=0,
                )
            ),
        reverse=True,
    )

    total_minutes = sum(
        to_int(
            first_attr(
                item,
                "lateness_minutes",
                default=0,
            )
        )
        for item in late_items
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        late_items,
        page=callback_data.page,
        page_size=PAGE_SIZE,
    )

    await safe_edit(
        callback,
        text=(
            "⚠️ <b>Запізнення по мережі</b>\n\n"
            f"ТТ із запізненням: "
            f"<b>{len(late_items)}</b>\n"
            f"Сумарно хвилин: "
            f"<b>{total_minutes}</b>"
        ),
        reply_markup=(
            build_keyboard(
                director_late_keyboard,

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
    DirectorCallback.filter(
        F.action
        == DirectorAction.MISSING_OPENING
    )
)
async def director_missing_opening_callback(
    callback: CallbackQuery,
    callback_data: DirectorCallback,
    **data: Any,
) -> None:
    """
    ТТ без відкриття.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    stores = [
        store
        for store in (
            await query_all_stores(
                data=data
            )
        )
        if is_store_active(
            store
        )
    ]

    items = (
        await build_director_store_items(
            stores=stores,
            user=user,
            data=data,
            context="opening",
        )
    )

    waiting_state = enum_member(
        DirectorStoreState,
        "WAITING_OPENING",
        "NOT_OPENED",
    )

    missing_items = [
        item
        for item in items
        if first_attr(
            item,
            "state",
        )
        == waiting_state
    ]

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        missing_items,
        page=callback_data.page,
        page_size=PAGE_SIZE,
    )

    await safe_edit(
        callback,
        text=(
            "🚨 <b>Не відкрилися</b>\n\n"
            f"ТТ без check-in: "
            f"<b>{len(missing_items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                director_missing_opening_keyboard,

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
    DirectorCallback.filter(
        F.action
        == DirectorAction.CLOSING
    )
)
async def director_closing_callback(
    callback: CallbackQuery,
    callback_data: DirectorCallback,
    **data: Any,
) -> None:
    """
    Live закриття мережі.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    stores = [
        store
        for store in (
            await query_all_stores(
                data=data
            )
        )
        if is_store_active(
            store
        )
    ]

    items = (
        await build_director_store_items(
            stores=stores,
            user=user,
            data=data,
            context="closing",
        )
    )

    closed_state = enum_member(
        DirectorStoreState,
        "CLOSED",
    )

    progress_state = enum_member(
        DirectorStoreState,
        "CLOSING_IN_PROGRESS",
        "CLOSING_STARTED",
        "WAITING_CLOSING",
    )

    waiting_state = enum_member(
        DirectorStoreState,
        "WAITING_CLOSING",
        "OPENED_ON_TIME",
    )

    closed_count = sum(
        1
        for item in items
        if first_attr(
            item,
            "state",
        )
        == closed_state
    )

    progress_count = sum(
        1
        for item in items
        if first_attr(
            item,
            "state",
        )
        == progress_state
    )

    waiting_count = sum(
        1
        for item in items
        if first_attr(
            item,
            "state",
        )
        == waiting_state
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        items,
        page=callback_data.page,
        page_size=PAGE_SIZE,
    )

    await safe_edit(
        callback,
        text=(
            "🌙 <b>Live — закриття мережі</b>\n\n"
            f"✅ Закрилися: "
            f"<b>{closed_count}/{len(items)}</b>\n"
            f"🔄 Закриття в процесі: "
            f"<b>{progress_count}</b>\n"
            f"⏳ Очікують закриття: "
            f"<b>{waiting_count}</b>"
        ),
        reply_markup=(
            build_keyboard(
                director_closing_keyboard,

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
    DirectorCallback.filter(
        F.action
        == DirectorAction.MISSING_CLOSING
    )
)
async def director_missing_closing_callback(
    callback: CallbackQuery,
    callback_data: DirectorCallback,
    **data: Any,
) -> None:
    """
    Відкриті сьогодні ТТ,
    які не завершили закриття.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    stores = [
        store
        for store in (
            await query_all_stores(
                data=data
            )
        )
        if is_store_active(
            store
        )
    ]

    missing_items: list[
        DirectorStoreItem
    ] = []

    for store in stores:
        store_id = object_id(
            store
        )

        opening = await get_opening_status(
            store_id=store_id,
            user=user,
            data=data,
        )

        # Магазин не відкривався —
        # він не належить до списку
        # "не закрився".
        if not opening_exists(
            opening
        ):
            continue

        closing = await get_closing_status(
            store_id=store_id,
            user=user,
            data=data,
        )

        if result_is_completed(
            closing
        ):
            continue

        item = (
            await build_director_store_item(
                store=store,
                user=user,
                data=data,
                context="closing",
            )
        )

        missing_items.append(
            item
        )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        missing_items,
        page=callback_data.page,
        page_size=PAGE_SIZE,
    )

    await safe_edit(
        callback,
        text=(
            "🚨 <b>Не закрилися</b>\n\n"
            f"Незавершених ТТ: "
            f"<b>{len(missing_items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                director_missing_closing_keyboard,

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
    DirectorCallback.filter(
        F.action
        == DirectorAction.REPORTS
    )
)
async def director_reports_callback(
    callback: CallbackQuery,
) -> None:
    """
    Звіти директора.
    """

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "📊 <b>Звіти по мережі</b>\n\n"
            "Оберіть потрібний тип "
            "або період звіту:"
        ),
        reply_markup=(
            build_keyboard(
                director_reports_keyboard
            )
        ),
    )


# =========================================================
# INVITES
# =========================================================


@router.callback_query(
    DirectorCallback.filter(
        F.action
        == DirectorAction.INVITES
    )
)
async def director_invites_callback(
    callback: CallbackQuery,
) -> None:
    """
    Invite директорського рівня.
    """

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "🔗 <b>Запрошення</b>\n\n"
            "Створення та керування "
            "запрошеннями користувачів."
        ),
        reply_markup=(
            build_keyboard(
                director_invites_keyboard
            )
        ),
    )


# =========================================================
# BACK
# =========================================================


@router.callback_query(
    DirectorCallback.filter(
        F.action
        == DirectorAction.BACK
    )
)
async def director_back_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Назад до dashboard.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    await show_dashboard_callback(
        callback,
        user=user,
        data=data,
    )


# =========================================================
# UNKNOWN
# =========================================================


@router.callback_query(
    DirectorCallback.filter()
)
async def unknown_director_callback(
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

    "can_use_director_panel",

    "has_network_access",
    "accessible_bush_ids",
    "accessible_store_ids",

    "object_id",
    "object_is_active",

    "query_network_bushes",
    "filter_accessible_bushes",

    "query_all_stores",
    "query_network_users",

    "store_code",
    "store_name",
    "store_bush_name",

    "build_director_store_item",
    "build_director_store_items",

    "count_bush_stores",
    "build_director_bush_items",

    "build_director_user_item",

    "build_director_dashboard",
    "build_dashboard_text",

    "show_dashboard_callback",
    "show_dashboard_message",
]
# =========================================================
# ROOT ADMIN COMPATIBILITY
# =========================================================

async def load_user(
    user_id: int = 0,
    data: dict | None = None,
    **kwargs,
):
    from app.handlers.bush_admin import load_user as _load_user

    resolved_id = (
        user_id
        or kwargs.get("target_user_id")
        or kwargs.get("id")
        or kwargs.get("object_id")
        or 0
    )

    try:
        resolved_id = int(resolved_id)
    except (TypeError, ValueError):
        return None

    if resolved_id <= 0:
        return None

    context = {}

    if isinstance(data, dict):
        context.update(data)

    for key, value in kwargs.items():
        if key not in {
            "target_user_id",
            "id",
            "object_id",
        }:
            context.setdefault(key, value)

    return await _load_user(
        user_id=resolved_id,
        data=context,
    )


# =========================================================
# ROOT ADMIN CHECK
# =========================================================

def is_root_admin(
    user=None,
    telegram_id=None,
    **kwargs,
) -> bool:
    """
    ????????? ROOT_ADMIN:
    1. ?? ????? ???????????;
    2. ?? Telegram ID ?? settings.
    """

    from app.handlers.bush_admin import normalized_role

    if user is not None:
        try:
            if normalized_role(user) == "ROOT_ADMIN":
                return True
        except Exception:
            pass

    candidate_id = (
        telegram_id
        or kwargs.get("tg_id")
        or kwargs.get("user_id")
    )

    if candidate_id is None and user is not None:
        candidate_id = (
            getattr(user, "telegram_id", None)
            or getattr(user, "tg_id", None)
        )

    if candidate_id is None:
        return False

    try:
        candidate_id = int(candidate_id)
    except (TypeError, ValueError):
        return False

    try:
        from app.config import settings

        checker = getattr(
            settings,
            "is_root_admin",
            None,
        )

        if callable(checker):
            return bool(
                checker(candidate_id)
            )

        root_ids = getattr(
            settings,
            "root_admin_ids",
            [],
        )

        return candidate_id in {
            int(item)
            for item in root_ids
        }

    except Exception:
        return False
