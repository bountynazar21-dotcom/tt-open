from __future__ import annotations

import inspect
import logging
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
)

from app.database.models.user import User as DatabaseUser

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
    get_database_user,
    safe_edit,
    user_role_name,
)
from app.handlers.director import (
    object_id,
    object_is_active,
    query_all_stores,
    query_network_bushes,
    query_network_users,
    store_bush_name,
    store_code,
    store_name,
)
from app.handlers.lion import (
    get_bush_title,
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
    is_store_active,
    load_bush,
    load_cluster,
    load_store,
    store_bush_id,
    store_cluster_id,
    store_title,
)

from app.keyboards import (
    AuditActionCallback,
    AuditCallback,
    GroupAction,
    GroupCallback,
    ImportAction,
    ImportCallback,
    RootAdminAction,
    RootAdminCallback,
    SettingsAction,
    SettingsCallback,
    UserAction,
    UserCallback,
)

from app.keyboards.root_admin import (
    RootAdminDashboardState,
    RootBushItem,
    RootClusterItem,
    RootStoreItem,
    RootStoreState,
    RootUserItem,
    root_admin_audit_keyboard,
    root_admin_back_keyboard,
    root_admin_bush_keyboard,
    root_admin_bushes_keyboard,
    root_admin_closing_keyboard,
    root_admin_cluster_keyboard,
    root_admin_clusters_keyboard,
    root_admin_groups_keyboard,
    root_admin_import_keyboard,
    root_admin_import_preview_keyboard,
    root_admin_invites_keyboard,
    root_admin_late_keyboard,
    root_admin_main_keyboard,
    root_admin_missing_closing_keyboard,
    root_admin_missing_opening_keyboard,
    root_admin_network_group_keyboard,
    root_admin_opening_keyboard,
    root_admin_pending_user_keyboard,
    root_admin_pending_users_keyboard,
    root_admin_reports_keyboard,
    root_admin_role_keyboard,
    root_admin_settings_keyboard,
    root_admin_store_keyboard,
    root_admin_stores_keyboard,
    root_admin_system_keyboard,
    root_admin_user_keyboard,
    root_admin_users_keyboard,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="root_admin",
)


# =========================================================
# CONSTANTS
# =========================================================


PAGE_SIZE = 10


ROOT_ROLE_NAMES = {
    "ROOT_ADMIN",
}


PENDING_STATUS_NAMES = {
    "PENDING",
    "NEW",
    "WAITING",
    "WAITING_APPROVAL",
}


BLOCKED_STATUS_NAMES = {
    "BLOCKED",
    "BANNED",
}


ACTIVE_STATUS_NAMES = {
    "ACTIVE",
    "APPROVED",
}


# =========================================================
# FSM
# =========================================================


class RootAdminStates(
    StatesGroup
):
    """
    FSM ROOT ADMIN.
    """

    waiting_import_file = State()

    waiting_timezone = State()


# =========================================================
# ACCESS
# =========================================================


def is_root_admin(
    user: DatabaseUser | None,
) -> bool:
    """
    Перевірка ROOT_ADMIN.
    """

    if user is None:
        return False

    return (
        user_role_name(
            user
        )
        in ROOT_ROLE_NAMES
    )


async def require_root(
    event: Message | CallbackQuery,
    *,
    data: dict[str, Any],
) -> DatabaseUser | None:
    """
    ROOT guard.
    """

    user = get_database_user(
        data
    )

    if is_root_admin(
        user
    ):
        return user

    if isinstance(
        event,
        CallbackQuery,
    ):
        await event.answer(
            "Доступ лише для ROOT ADMIN.",
            show_alert=True,
        )

    else:
        await event.answer(
            "⛔ Цей розділ доступний "
            "лише ROOT ADMIN."
        )

    return None


# =========================================================
# GENERIC HELPERS
# =========================================================


def normalized_status(
    user: Any,
) -> str:
    """
    Статус користувача.
    """

    status = first_attr(
        user,
        "status",
        default=None,
    )

    raw = first_attr(
        status,
        "name",
        "value",
        default=status,
    )

    if raw is None:
        return ""

    return (
        str(raw)
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )


def username_text(
    user: Any,
) -> str | None:
    """
    Telegram username.
    """

    value = first_attr(
        user,
        "username",
        default=None,
    )

    if not value:
        return None

    return (
        "@"
        + str(value).lstrip("@")
    )


def object_name(
    value: Any,
    *,
    default: str,
) -> str:
    """
    name/title fallback.
    """

    name = first_attr(
        value,
        "name",
        "title",
        default=None,
    )

    if name:
        return str(
            name
        )

    return default


def get_repositories(
    data: dict[str, Any],
) -> Any | None:
    return data.get(
        "repositories"
    )


async def flush_changes(
    data: dict[str, Any],
) -> None:
    """
    Flush without forcing commit.
    """

    repositories = get_repositories(
        data
    )

    if repositories is not None:
        method = getattr(
            repositories,
            "flush",
            None,
        )

        if callable(
            method
        ):
            result = method()

            if inspect.isawaitable(
                result
            ):
                await result

            return

    session = (
        data.get("session")
        or data.get("db_session")
    )

    if session is None:
        return

    method = getattr(
        session,
        "flush",
        None,
    )

    if callable(
        method
    ):
        result = method()

        if inspect.isawaitable(
            result
        ):
            await result


# =========================================================
# SETTINGS
# =========================================================


async def get_setting_value(
    *,
    key: str,
    data: dict[str, Any],
    default: Any = None,
) -> Any:
    """
    Читає system setting.
    """

    service = get_service(
        data,
        "settings",
        "setting",
    )

    if service is not None:
        for method_name in (
            "get_value",
            "get",
            "get_setting",
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
                    {
                        "key": key,
                        "name": key,
                        "default": default,
                    },
                )

            except Exception:
                continue

            if result is None:
                continue

            value = first_attr(
                result,
                "value",
                default=result,
            )

            return value

    repositories = get_repositories(
        data
    )

    if repositories is None:
        return default

    repository = (
        getattr(
            repositories,
            "settings",
            None,
        )
        or getattr(
            repositories,
            "system_settings",
            None,
        )
    )

    if repository is None:
        return default

    for method_name in (
        "get_value",
        "get_by_key",
        "get",
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
                {
                    "key": key,
                    "name": key,
                },
            )

        except Exception:
            continue

        if result is None:
            continue

        return first_attr(
            result,
            "value",
            default=result,
        )

    return default


async def get_setting_bool(
    *,
    key: str,
    data: dict[str, Any],
    default: bool,
) -> bool:
    """
    Bool setting.
    """

    value = await get_setting_value(
        key=key,
        data=data,
        default=default,
    )

    return to_bool(
        value,
        default=default,
    )


async def set_setting_value(
    *,
    key: str,
    value: Any,
    user: DatabaseUser,
    data: dict[str, Any],
) -> bool:
    """
    Оновлює system setting.
    """

    service = get_service(
        data,
        "settings",
        "setting",
    )

    payload = {
        "key": key,
        "name": key,
        "value": value,
        "actor": user,
        "user": user,
        "actor_id": getattr(
            user,
            "id",
            None,
        ),
    }

    if service is not None:
        for method_name in (
            "set_value",
            "set",
            "update_setting",
            "update",
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
                await call_method(
                    method,
                    payload,
                )

                await flush_changes(
                    data
                )

                return True

            except Exception:
                continue

    repositories = get_repositories(
        data
    )

    repository = (
        getattr(
            repositories,
            "settings",
            None,
        )
        or getattr(
            repositories,
            "system_settings",
            None,
        )
        if repositories
        else None
    )

    if repository is not None:
        for method_name in (
            "set_value",
            "upsert",
            "set",
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
                await call_method(
                    method,
                    payload,
                )

                await flush_changes(
                    data
                )

                return True

            except Exception:
                continue

    return False


# =========================================================
# CLUSTERS
# =========================================================


async def query_clusters(
    *,
    data: dict[str, Any],
) -> list[Any]:
    """
    Всі кластери.
    """

    payload = {
        "active_only": False,
        "include_inactive": True,
    }

    service = get_service(
        data,
        "clusters",
        "cluster",
    )

    if service is not None:
        for method_name in (
            "list_clusters",
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
                return items

    repositories = get_repositories(
        data
    )

    repository = (
        getattr(
            repositories,
            "clusters",
            None,
        )
        if repositories
        else None
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


def cluster_time_text(
    cluster: Any,
) -> str:
    """
    Час кластера.
    """

    value = first_attr(
        cluster,
        "opening_time",
        "start_time",
        "time",
        default=None,
    )

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


async def count_cluster_stores(
    *,
    cluster_id: int,
    stores: list[Any],
) -> int:
    """
    Кількість ТТ у кластері.
    """

    return sum(
        1
        for store in stores
        if store_cluster_id(
            store
        )
        == cluster_id
    )


# =========================================================
# ROOT ITEMS
# =========================================================


async def build_root_store_item(
    *,
    store: Any,
    user: DatabaseUser | None,
    data: dict[str, Any],
    context: str = "general",
) -> RootStoreItem:
    """
    Store -> RootStoreItem.
    """

    store_id = object_id(
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

    active = is_store_active(
        store
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

    if not active:
        state = RootStoreState.INACTIVE

    elif closed:
        state = RootStoreState.CLOSED

    elif context == "closing":
        if closing_started:
            state = (
                RootStoreState
                .CLOSING_IN_PROGRESS
            )

        elif opened:
            state = (
                RootStoreState
                .WAITING_CLOSING
            )

        else:
            state = (
                RootStoreState
                .WAITING_OPENING
            )

    elif opened:
        if late_minutes > 0:
            state = (
                RootStoreState
                .OPENED_LATE
            )

        else:
            state = (
                RootStoreState
                .OPENED_ON_TIME
            )

    else:
        state = (
            RootStoreState
            .WAITING_OPENING
        )

    bush_name = await store_bush_name(
        store=store,
        data=data,
    )

    cluster_id = store_cluster_id(
        store
    )

    cluster = await load_cluster(
        cluster_id=cluster_id,
        data=data,
    )

    cluster_text = (
        cluster_time_text(
            cluster
        )
        if cluster
        else "—"
    )

    return RootStoreItem(
        store_id=store_id,
        code=store_code(
            store
        ),
        name=(
            store_name(
                store
            )
            or ""
        ),
        bush_name=(
            bush_name
            or "—"
        ),
        cluster_text=cluster_text,
        state=state,
        lateness_minutes=(
            late_minutes
        ),
        is_active=active,
    )


async def build_root_store_items(
    *,
    stores: list[Any],
    user: DatabaseUser | None,
    data: dict[str, Any],
    context: str = "general",
) -> list[
    RootStoreItem
]:
    """
    Усі RootStoreItem.
    """

    result: list[
        RootStoreItem
    ] = []

    for store in stores:
        try:
            item = await build_root_store_item(
                store=store,
                user=user,
                data=data,
                context=context,
            )

        except Exception:
            logger.exception(
                "Failed building RootStoreItem: "
                "store_id=%s",
                object_id(
                    store
                ),
            )

            continue

        result.append(
            item
        )

    return result


async def build_root_bush_items(
    *,
    bushes: list[Any],
    stores: list[Any],
    users: list[Any],
) -> list[
    RootBushItem
]:
    """
    Кущі.
    """

    result: list[
        RootBushItem
    ] = []

    for bush in bushes:
        bush_id = object_id(
            bush
        )

        if bush_id <= 0:
            continue

        stores_count = sum(
            1
            for store in stores
            if store_bush_id(
                store
            )
            == bush_id
        )

        users_count = 0

        for user in users:
            direct_bush_id = to_int(
                first_attr(
                    user,
                    "bush_id",
                    default=0,
                )
            )

            if direct_bush_id == bush_id:
                users_count += 1

        result.append(
            RootBushItem(
                bush_id=bush_id,
                name=object_name(
                    bush,
                    default=(
                        f"Кущ #{bush_id}"
                    ),
                ),
                stores_count=stores_count,
                users_count=users_count,
                is_active=(
                    object_is_active(
                        bush
                    )
                ),
            )
        )

    return result


async def build_root_cluster_items(
    *,
    clusters: list[Any],
    stores: list[Any],
) -> list[
    RootClusterItem
]:
    """
    Кластери.
    """

    result: list[
        RootClusterItem
    ] = []

    for cluster in clusters:
        cluster_id = object_id(
            cluster
        )

        if cluster_id <= 0:
            continue

        stores_count = (
            await count_cluster_stores(
                cluster_id=cluster_id,
                stores=stores,
            )
        )

        result.append(
            RootClusterItem(
                cluster_id=cluster_id,
                name=object_name(
                    cluster,
                    default=(
                        f"Кластер #{cluster_id}"
                    ),
                ),
                opening_time=(
                    cluster_time_text(
                        cluster
                    )
                ),
                stores_count=stores_count,
                is_active=(
                    object_is_active(
                        cluster
                    )
                ),
            )
        )

    return result


def build_root_user_item(
    user: Any,
) -> RootUserItem:
    """
    User -> RootUserItem.
    """

    status = normalized_status(
        user
    )

    role = normalized_role(
        user
    )

    username = first_attr(
        user,
        "username",
        default=None,
    )

    return RootUserItem(
        user_id=object_id(
            user
        ),
        display_name=(
            user_display_name(
                user
            )
        ),
        role_text=(
            role_label(
                role
            )
        ),
        username=(
            str(username)
            if username
            else None
        ),
        is_active=(
            status
            in ACTIVE_STATUS_NAMES
        ),
        is_blocked=(
            status
            in BLOCKED_STATUS_NAMES
        ),
        is_pending=(
            status
            in PENDING_STATUS_NAMES
        ),
    )


# =========================================================
# DASHBOARD
# =========================================================


async def build_root_dashboard(
    *,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> tuple[
    RootAdminDashboardState,
    list[Any],
    list[Any],
    list[Any],
    list[Any],
]:
    """
    Повний network dashboard.
    """

    stores = await query_all_stores(
        data=data
    )

    bushes = await query_network_bushes(
        data=data
    )

    clusters = await query_clusters(
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
        await build_root_store_items(
            stores=active_stores,
            user=user,
            data=data,
            context="opening",
        )
    )

    closing_items = (
        await build_root_store_items(
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
            RootStoreState.OPENED_ON_TIME,
            RootStoreState.OPENED_LATE,
        }
    )

    late_count = sum(
        1
        for item in opening_items
        if item.state
        == RootStoreState.OPENED_LATE
    )

    missing_opening_count = sum(
        1
        for item in opening_items
        if item.state
        == RootStoreState.WAITING_OPENING
    )

    closed_count = sum(
        1
        for item in closing_items
        if item.state
        == RootStoreState.CLOSED
    )

    closing_progress_count = sum(
        1
        for item in closing_items
        if item.state
        == RootStoreState.CLOSING_IN_PROGRESS
    )

    closing_phase_started = (
        closed_count > 0
        or closing_progress_count > 0
    )

    if closing_phase_started:
        missing_closing_count = sum(
            1
            for item in closing_items
            if item.state
            == RootStoreState.WAITING_CLOSING
        )

    else:
        missing_closing_count = 0

    pending_users_count = sum(
        1
        for item in users
        if normalized_status(
            item
        )
        in PENDING_STATUS_NAMES
    )

    blocked_users_count = sum(
        1
        for item in users
        if normalized_status(
            item
        )
        in BLOCKED_STATUS_NAMES
    )

    bot_enabled = await get_setting_bool(
        key="bot_enabled",
        data=data,
        default=True,
    )

    maintenance_enabled = (
        await get_setting_bool(
            key="maintenance_enabled",
            data=data,
            default=False,
        )
    )

    state = RootAdminDashboardState(
        total_stores=len(
            stores
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
        clusters_count=len(
            clusters
        ),
        users_count=len(
            users
        ),
        pending_users_count=(
            pending_users_count
        ),
        blocked_users_count=(
            blocked_users_count
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
            closing_progress_count
        ),
        bot_enabled=bot_enabled,
        maintenance_enabled=(
            maintenance_enabled
        ),
    )

    return (
        state,
        stores,
        bushes,
        clusters,
        users,
    )


def build_dashboard_text(
    state: RootAdminDashboardState,
) -> str:
    """
    Dashboard text.
    """

    bot_text = (
        "🟢 працює"
        if state.bot_enabled
        else "🔴 вимкнений"
    )

    maintenance_text = (
        "🟠 увімкнений"
        if state.maintenance_enabled
        else "🟢 вимкнений"
    )

    lines = [
        "👑 <b>ROOT ADMIN</b>",
        "",
        "🌐 <b>Мережа</b>",
        "",
        (
            "🏪 ТТ: "
            f"<b>{state.active_stores}</b> активних"
        ),
        (
            "⚫ Неактивних: "
            f"<b>{state.inactive_stores}</b>"
        ),
        (
            "🌿 Кущів: "
            f"<b>{state.bushes_count}</b>"
        ),
        (
            "⏰ Кластерів: "
            f"<b>{state.clusters_count}</b>"
        ),
        (
            "👥 Користувачів: "
            f"<b>{state.users_count}</b>"
        ),
        (
            "⏳ Pending: "
            f"<b>{state.pending_users_count}</b>"
        ),
        (
            "⛔ Заблокованих: "
            f"<b>{state.blocked_users_count}</b>"
        ),
        "",
        (
            "🌅 Відкрилися: "
            f"<b>{state.opened_count}/"
            f"{state.active_stores}</b>"
        ),
    ]

    if state.late_count > 0:
        lines.append(
            "⚠️ Запізнення: "
            f"<b>{state.late_count}</b>"
        )

    if state.missing_opening_count > 0:
        lines.append(
            "🚨 Не відкрилися: "
            f"<b>{state.missing_opening_count}</b>"
        )

    lines.extend(
        [
            "",
            (
                "🌙 Закрилися: "
                f"<b>{state.closed_count}/"
                f"{state.active_stores}</b>"
            ),
        ]
    )

    if state.closing_in_progress_count > 0:
        lines.append(
            "🔄 Закриття в процесі: "
            f"<b>{state.closing_in_progress_count}</b>"
        )

    if state.missing_closing_count > 0:
        lines.append(
            "🚨 Не закрилися: "
            f"<b>{state.missing_closing_count}</b>"
        )

    lines.extend(
        [
            "",
            "⚙️ <b>Система</b>",
            f"🤖 Бот: <b>{bot_text}</b>",
            (
                "🛠 Maintenance: "
                f"<b>{maintenance_text}</b>"
            ),
        ]
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
    user: DatabaseUser,
    data: dict[str, Any],
) -> None:
    """
    ROOT dashboard callback.
    """

    (
        state,
        stores,
        bushes,
        clusters,
        users,
    ) = await build_root_dashboard(
        user=user,
        data=data,
    )

    await safe_edit(
        callback,
        text=build_dashboard_text(
            state
        ),
        reply_markup=(
            build_keyboard(
                root_admin_main_keyboard,
                state=state,
            )
        ),
    )


async def show_dashboard_message(
    message: Message,
    *,
    user: DatabaseUser,
    data: dict[str, Any],
) -> None:
    """
    ROOT dashboard message.
    """

    (
        state,
        stores,
        bushes,
        clusters,
        users,
    ) = await build_root_dashboard(
        user=user,
        data=data,
    )

    await message.answer(
        build_dashboard_text(
            state
        ),
        reply_markup=(
            build_keyboard(
                root_admin_main_keyboard,
                state=state,
            )
        ),
    )


# =========================================================
# /ADMIN
# =========================================================


@router.message(
    Command(
        "admin",
        "root",
    )
)
async def root_admin_command(
    message: Message,
    **data: Any,
) -> None:
    """
    /admin
    /root
    """

    user = await require_root(
        message,
        data=data,
    )

    if user is None:
        return

    await show_dashboard_message(
        message,
        user=user,
        data=data,
    )


# =========================================================
# DASHBOARD CALLBACK
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action.in_(
            {
                RootAdminAction.MENU,
                RootAdminAction.DASHBOARD,
                RootAdminAction.NETWORK,
                RootAdminAction.REFRESH,
                RootAdminAction.BACK,
            }
        )
    )
)
async def root_dashboard_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    ROOT dashboard.
    """

    await callback.answer()

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await show_dashboard_callback(
        callback,
        user=user,
        data=data,
    )


# =========================================================
# STORES
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.STORES
    )
)
async def root_stores_callback(
    callback: CallbackQuery,
    callback_data: RootAdminCallback,
    **data: Any,
) -> None:
    """
    Список / картка ТТ.
    """

    await callback.answer()

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    # -----------------------------------------------------
    # STORE CARD
    # -----------------------------------------------------

    if callback_data.ref_id > 0:
        store = await load_store(
            store_id=callback_data.ref_id,
            data=data,
        )

        if store is None:
            await callback.answer(
                "ТТ не знайдено.",
                show_alert=True,
            )

            return

        item = await build_root_store_item(
            store=store,
            user=user,
            data=data,
        )

        await safe_edit(
            callback,
            text=(
                "🏪 <b>Торгова точка</b>\n\n"
                f"<b>{escape(store_title(store, store_id=item.store_id))}</b>\n\n"
                f"🌿 Кущ: <b>{escape(item.bush_name)}</b>\n"
                f"⏰ Кластер: <b>{escape(item.cluster_text)}</b>\n"
                f"Статус: <b>{escape(item.state.value)}</b>"
            ),
            reply_markup=(
                build_keyboard(
                    root_admin_store_keyboard,
                    store_id=item.store_id,
                    store=item,
                )
            ),
        )

        return

    # -----------------------------------------------------
    # STORE LIST
    # -----------------------------------------------------

    stores = await query_all_stores(
        data=data
    )

    items = await build_root_store_items(
        stores=stores,
        user=user,
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

    await safe_edit(
        callback,
        text=(
            "🏪 <b>Торгові точки</b>\n\n"
            f"Усього: <b>{len(items)}</b>\n"
            f"Активних: "
            f"<b>{sum(1 for item in items if item.is_active)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                root_admin_stores_keyboard,
                stores=page_items,
                page=page,
                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# BUSHES
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.BUSHES
    )
)
async def root_bushes_callback(
    callback: CallbackQuery,
    callback_data: RootAdminCallback,
    **data: Any,
) -> None:
    """
    Кущі.
    """

    await callback.answer()

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    stores = await query_all_stores(
        data=data
    )

    bushes = await query_network_bushes(
        data=data
    )

    users = await query_network_users(
        data=data
    )

    items = await build_root_bush_items(
        bushes=bushes,
        stores=stores,
        users=users,
    )

    # -----------------------------------------------------
    # BUSH CARD
    # -----------------------------------------------------

    if callback_data.ref_id > 0:
        item = next(
            (
                bush
                for bush in items
                if bush.bush_id
                == callback_data.ref_id
            ),
            None,
        )

        if item is None:
            await callback.answer(
                "Кущ не знайдено.",
                show_alert=True,
            )

            return

        await safe_edit(
            callback,
            text=(
                "🌿 <b>Кущ</b>\n\n"
                f"<b>{escape(item.name)}</b>\n\n"
                f"🏪 ТТ: <b>{item.stores_count}</b>\n"
                f"👥 Користувачів: "
                f"<b>{item.users_count}</b>\n"
                f"Статус: "
                f"<b>{'активний' if item.is_active else 'неактивний'}</b>"
            ),
            reply_markup=(
                build_keyboard(
                    root_admin_bush_keyboard,
                    bush_id=item.bush_id,
                    bush=item,
                )
            ),
        )

        return

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
            "🌿 <b>Кущі мережі</b>\n\n"
            f"Усього: <b>{len(items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                root_admin_bushes_keyboard,
                bushes=page_items,
                page=page,
                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# CLUSTERS
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.CLUSTERS
    )
)
async def root_clusters_callback(
    callback: CallbackQuery,
    callback_data: RootAdminCallback,
    **data: Any,
) -> None:
    """
    Кластери.
    """

    await callback.answer()

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    stores = await query_all_stores(
        data=data
    )

    clusters = await query_clusters(
        data=data
    )

    items = await build_root_cluster_items(
        clusters=clusters,
        stores=stores,
    )

    # -----------------------------------------------------
    # CLUSTER CARD
    # -----------------------------------------------------

    if callback_data.ref_id > 0:
        item = next(
            (
                cluster
                for cluster in items
                if cluster.cluster_id
                == callback_data.ref_id
            ),
            None,
        )

        if item is None:
            await callback.answer(
                "Кластер не знайдено.",
                show_alert=True,
            )

            return

        await safe_edit(
            callback,
            text=(
                "⏰ <b>Кластер</b>\n\n"
                f"<b>{escape(item.name)}</b>\n\n"
                f"🕐 Відкриття: "
                f"<b>{escape(item.opening_time)}</b>\n"
                f"🏪 ТТ: <b>{item.stores_count}</b>\n"
                f"Статус: "
                f"<b>{'активний' if item.is_active else 'неактивний'}</b>"
            ),
            reply_markup=(
                build_keyboard(
                    root_admin_cluster_keyboard,
                    cluster_id=(
                        item.cluster_id
                    ),
                    cluster=item,
                )
            ),
        )

        return

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
            "⏰ <b>Кластери</b>\n\n"
            f"Усього: <b>{len(items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                root_admin_clusters_keyboard,
                clusters=page_items,
                page=page,
                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# USERS
# =========================================================


async def show_users(
    callback: CallbackQuery,
    *,
    page: int,
    pending_only: bool,
    data: dict[str, Any],
) -> None:
    """
    Список users.
    """

    users = await query_network_users(
        data=data
    )

    if pending_only:
        users = [
            user
            for user in users
            if normalized_status(
                user
            )
            in PENDING_STATUS_NAMES
        ]

    items = [
        build_root_user_item(
            user
        )
        for user in users
    ]

    (
        page_items,
        normalized_page,
        total_pages,
    ) = paginate(
        items,
        page=page,
        page_size=PAGE_SIZE,
    )

    if pending_only:
        text = (
            "⏳ <b>Pending користувачі</b>\n\n"
            f"Очікують рішення: "
            f"<b>{len(items)}</b>"
        )

        markup = build_keyboard(
            root_admin_pending_users_keyboard,
            users=page_items,
            page=normalized_page,
            total_pages=total_pages,
        )

    else:
        text = (
            "👥 <b>Користувачі</b>\n\n"
            f"Усього: <b>{len(items)}</b>\n"
            f"Активних: "
            f"<b>{sum(1 for item in items if item.is_active)}</b>\n"
            f"Pending: "
            f"<b>{sum(1 for item in items if item.is_pending)}</b>\n"
            f"Blocked: "
            f"<b>{sum(1 for item in items if item.is_blocked)}</b>"
        )

        markup = build_keyboard(
            root_admin_users_keyboard,
            users=page_items,
            page=normalized_page,
            total_pages=total_pages,
        )

    await safe_edit(
        callback,
        text=text,
        reply_markup=markup,
    )


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.USERS
    )
)
async def root_users_callback(
    callback: CallbackQuery,
    callback_data: RootAdminCallback,
    **data: Any,
) -> None:
    """
    Users.
    """

    await callback.answer()

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await show_users(
        callback,
        page=callback_data.page,
        pending_only=False,
        data=data,
    )


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.PENDING_USERS
    )
)
async def root_pending_users_callback(
    callback: CallbackQuery,
    callback_data: RootAdminCallback,
    **data: Any,
) -> None:
    """
    Pending users.
    """

    await callback.answer()

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await show_users(
        callback,
        page=callback_data.page,
        pending_only=True,
        data=data,
    )


# =========================================================
# LOAD USER
# =========================================================


async def load_user(
    *,
    user_id: int,
    data: dict[str, Any],
) -> Any | None:
    """
    User by internal DB id.
    """

    service = get_service(
        data,
        "users",
        "user",
    )

    payload = {
        "user_id": user_id,
        "id": user_id,
    }

    if service is not None:
        for method_name in (
            "get_user",
            "get_user_or_raise",
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
                result = await call_method(
                    method,
                    payload,
                )

            except Exception:
                continue

            if result is not None:
                return result

    repositories = get_repositories(
        data
    )

    repository = (
        getattr(
            repositories,
            "users",
            None,
        )
        if repositories
        else None
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
            result = await call_method(
                method,
                payload,
            )

        except Exception:
            continue

        if result is not None:
            return result

    return None


# =========================================================
# USER CARD
# =========================================================


async def show_user_card(
    callback: CallbackQuery,
    *,
    target_user: Any,
) -> None:
    """
    User detail.
    """

    item = build_root_user_item(
        target_user
    )

    status = normalized_status(
        target_user
    )

    username = username_text(
        target_user
    )

    phone = (
        first_attr(
            target_user,
            "phone",
            "phone_number",
            default=None,
        )
        or "—"
    )

    telegram_id = first_attr(
        target_user,
        "telegram_id",
        default="—",
    )

    lines = [
        "👤 <b>Користувач</b>",
        "",
        (
            "Ім'я: "
            f"<b>{escape(item.display_name)}</b>"
        ),
        (
            "Роль: "
            f"<b>{escape(item.role_text)}</b>"
        ),
        (
            "Статус: "
            f"<b>{escape(status or '—')}</b>"
        ),
    ]

    if username:
        lines.append(
            "Telegram: "
            f"<b>{escape(username)}</b>"
        )

    lines.extend(
        [
            (
                "Телефон: "
                f"<code>{escape(str(phone))}</code>"
            ),
            (
                "Telegram ID: "
                f"<code>{escape(str(telegram_id))}</code>"
            ),
        ]
    )

    if item.is_pending:
        markup = build_keyboard(
            root_admin_pending_user_keyboard,
            user_id=item.user_id,
            user=item,
        )

    else:
        markup = build_keyboard(
            root_admin_user_keyboard,
            user_id=item.user_id,
            user=item,
        )

    await safe_edit(
        callback,
        text="\n".join(
            lines
        ),
        reply_markup=markup,
    )


# =========================================================
# USER CALLBACK VIEW
# =========================================================


@router.callback_query(
    UserCallback.filter(
        F.action
        == UserAction.VIEW
    )
)
async def root_user_view_callback(
    callback: CallbackQuery,
    callback_data: UserCallback,
    **data: Any,
) -> None:
    """
    User card.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    target = await load_user(
        user_id=callback_data.user_id,
        data=data,
    )

    if target is None:
        await callback.answer(
            "Користувача не знайдено.",
            show_alert=True,
        )

        return

    await show_user_card(
        callback,
        target_user=target,
    )


# =========================================================
# AUTH SERVICE CALL
# =========================================================


async def auth_user_action(
    *,
    action: str,
    target_user_id: int,
    actor: DatabaseUser,
    data: dict[str, Any],
    role: Any = None,
) -> bool:
    """
    Викликає AuthService.
    """

    service = get_service(
        data,
        "auth",
    )

    if service is None:
        return False

    mapping = {
        "approve": (
            "approve_user",
            "approve",
        ),
        "reject": (
            "reject_user",
            "reject",
        ),
        "block": (
            "block_user",
            "block",
        ),
        "unblock": (
            "unblock_user",
            "unblock",
        ),
        "activate": (
            "activate_user",
            "activate",
        ),
        "deactivate": (
            "deactivate_user",
            "deactivate",
        ),
        "role": (
            "change_role",
            "set_role",
            "update_role",
        ),
    }

    methods = mapping.get(
        action,
        (),
    )

    payload = {
        "user_id":
            target_user_id,

        "target_user_id":
            target_user_id,

        "actor":
            actor,

        "user":
            actor,

        "actor_id":
            getattr(
                actor,
                "id",
                None,
            ),

        "role":
            role,

        "new_role":
            role,
    }

    for method_name in methods:
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
            logger.exception(
                "Auth action failed: "
                "%s user_id=%s",
                action,
                target_user_id,
            )

            continue

        explicit = first_attr(
            result,
            "success",
            "changed",
            "approved",
            default=True,
        )

        await flush_changes(
            data
        )

        return to_bool(
            explicit,
            default=True,
        )

    return False


# =========================================================
# APPROVE / REJECT / BLOCK...
# =========================================================


async def execute_user_action(
    callback: CallbackQuery,
    *,
    action: str,
    target_user_id: int,
    data: dict[str, Any],
) -> None:
    """
    Common user mutation.
    """

    actor = await require_root(
        callback,
        data=data,
    )

    if actor is None:
        return

    success = await auth_user_action(
        action=action,
        target_user_id=(
            target_user_id
        ),
        actor=actor,
        data=data,
    )

    if not success:
        await callback.answer(
            "Не вдалося виконати операцію.",
            show_alert=True,
        )

        return

    await callback.answer(
        "Готово ✅"
    )

    target = await load_user(
        user_id=target_user_id,
        data=data,
    )

    if target is not None:
        await show_user_card(
            callback,
            target_user=target,
        )


@router.callback_query(
    UserCallback.filter(
        F.action
        == UserAction.APPROVE
    )
)
async def root_user_approve_callback(
    callback: CallbackQuery,
    callback_data: UserCallback,
    **data: Any,
) -> None:
    await execute_user_action(
        callback,
        action="approve",
        target_user_id=(
            callback_data.user_id
        ),
        data=data,
    )


@router.callback_query(
    UserCallback.filter(
        F.action
        == UserAction.REJECT
    )
)
async def root_user_reject_callback(
    callback: CallbackQuery,
    callback_data: UserCallback,
    **data: Any,
) -> None:
    await execute_user_action(
        callback,
        action="reject",
        target_user_id=(
            callback_data.user_id
        ),
        data=data,
    )


@router.callback_query(
    UserCallback.filter(
        F.action
        == UserAction.BLOCK
    )
)
async def root_user_block_callback(
    callback: CallbackQuery,
    callback_data: UserCallback,
    **data: Any,
) -> None:
    await execute_user_action(
        callback,
        action="block",
        target_user_id=(
            callback_data.user_id
        ),
        data=data,
    )


@router.callback_query(
    UserCallback.filter(
        F.action
        == UserAction.UNBLOCK
    )
)
async def root_user_unblock_callback(
    callback: CallbackQuery,
    callback_data: UserCallback,
    **data: Any,
) -> None:
    await execute_user_action(
        callback,
        action="unblock",
        target_user_id=(
            callback_data.user_id
        ),
        data=data,
    )


@router.callback_query(
    UserCallback.filter(
        F.action
        == UserAction.ACTIVATE
    )
)
async def root_user_activate_callback(
    callback: CallbackQuery,
    callback_data: UserCallback,
    **data: Any,
) -> None:
    await execute_user_action(
        callback,
        action="activate",
        target_user_id=(
            callback_data.user_id
        ),
        data=data,
    )


@router.callback_query(
    UserCallback.filter(
        F.action
        == UserAction.DEACTIVATE
    )
)
async def root_user_deactivate_callback(
    callback: CallbackQuery,
    callback_data: UserCallback,
    **data: Any,
) -> None:
    await execute_user_action(
        callback,
        action="deactivate",
        target_user_id=(
            callback_data.user_id
        ),
        data=data,
    )


# =========================================================
# ROLE MENU
# =========================================================


@router.callback_query(
    UserCallback.filter(
        F.action
        == UserAction.ROLE
    )
)
async def root_user_role_callback(
    callback: CallbackQuery,
    callback_data: UserCallback,
    **data: Any,
) -> None:
    """
    Role selector.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "🎭 <b>Зміна ролі</b>\n\n"
            "Оберіть нову роль:"
        ),
        reply_markup=(
            build_keyboard(
                root_admin_role_keyboard,
                user_id=(
                    callback_data.user_id
                ),
            )
        ),
    )


# =========================================================
# LIVE OPENING
# =========================================================


async def show_opening_list(
    callback: CallbackQuery,
    *,
    mode: str,
    page: int,
    user: DatabaseUser,
    data: dict[str, Any],
) -> None:
    """
    opening / late / missing.
    """

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

    items = await build_root_store_items(
        stores=stores,
        user=user,
        data=data,
        context="opening",
    )

    if mode == "late":
        items = [
            item
            for item in items
            if item.state
            == RootStoreState.OPENED_LATE
        ]

        items.sort(
            key=lambda item:
                item.lateness_minutes,
            reverse=True,
        )

        title = (
            "⚠️ <b>Запізнення по мережі</b>"
        )

        keyboard = (
            root_admin_late_keyboard
        )

    elif mode == "missing":
        items = [
            item
            for item in items
            if item.state
            == RootStoreState.WAITING_OPENING
        ]

        title = (
            "🚨 <b>Не відкрилися</b>"
        )

        keyboard = (
            root_admin_missing_opening_keyboard
        )

    else:
        title = (
            "🌅 <b>Live — відкриття мережі</b>"
        )

        keyboard = (
            root_admin_opening_keyboard
        )

    (
        page_items,
        normalized_page,
        total_pages,
    ) = paginate(
        items,
        page=page,
        page_size=PAGE_SIZE,
    )

    await safe_edit(
        callback,
        text=(
            f"{title}\n\n"
            f"ТТ у списку: "
            f"<b>{len(items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                keyboard,
                stores=page_items,
                page=normalized_page,
                total_pages=total_pages,
            )
        ),
    )


@router.callback_query(
    RootAdminCallback.filter(
        F.action.in_(
            {
                RootAdminAction.OPENING,
                RootAdminAction.LATE,
                RootAdminAction.MISSING_OPENING,
            }
        )
    )
)
async def root_opening_control_callback(
    callback: CallbackQuery,
    callback_data: RootAdminCallback,
    **data: Any,
) -> None:
    """
    Opening control.
    """

    await callback.answer()

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    if callback_data.action == RootAdminAction.LATE:
        mode = "late"

    elif (
        callback_data.action
        == RootAdminAction.MISSING_OPENING
    ):
        mode = "missing"

    else:
        mode = "all"

    await show_opening_list(
        callback,
        mode=mode,
        page=callback_data.page,
        user=user,
        data=data,
    )


# =========================================================
# LIVE CLOSING
# =========================================================


async def show_closing_list(
    callback: CallbackQuery,
    *,
    missing_only: bool,
    page: int,
    user: DatabaseUser,
    data: dict[str, Any],
) -> None:
    """
    closing / missing closing.
    """

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

    if missing_only:
        filtered: list[Any] = []

        for store in stores:
            store_id = object_id(
                store
            )

            opening = await get_opening_status(
                store_id=store_id,
                user=user,
                data=data,
            )

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

            filtered.append(
                store
            )

        stores = filtered

    items = await build_root_store_items(
        stores=stores,
        user=user,
        data=data,
        context="closing",
    )

    (
        page_items,
        normalized_page,
        total_pages,
    ) = paginate(
        items,
        page=page,
        page_size=PAGE_SIZE,
    )

    if missing_only:
        title = (
            "🚨 <b>Не закрилися</b>"
        )

        keyboard = (
            root_admin_missing_closing_keyboard
        )

    else:
        title = (
            "🌙 <b>Live — закриття мережі</b>"
        )

        keyboard = (
            root_admin_closing_keyboard
        )

    await safe_edit(
        callback,
        text=(
            f"{title}\n\n"
            f"ТТ у списку: "
            f"<b>{len(items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                keyboard,
                stores=page_items,
                page=normalized_page,
                total_pages=total_pages,
            )
        ),
    )


@router.callback_query(
    RootAdminCallback.filter(
        F.action.in_(
            {
                RootAdminAction.CLOSING,
                RootAdminAction.MISSING_CLOSING,
            }
        )
    )
)
async def root_closing_control_callback(
    callback: CallbackQuery,
    callback_data: RootAdminCallback,
    **data: Any,
) -> None:
    """
    Closing control.
    """

    await callback.answer()

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await show_closing_list(
        callback,
        missing_only=(
            callback_data.action
            == RootAdminAction.MISSING_CLOSING
        ),
        page=callback_data.page,
        user=user,
        data=data,
    )


# =========================================================
# REPORTS
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.REPORTS
    )
)
async def root_reports_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Reports section.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "📊 <b>Звіти ROOT ADMIN</b>\n\n"
            "Оберіть область або період:"
        ),
        reply_markup=(
            build_keyboard(
                root_admin_reports_keyboard
            )
        ),
    )


# =========================================================
# INVITES
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.INVITES
    )
)
async def root_invites_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Invites.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "🔗 <b>Запрошення</b>\n\n"
            "Створення та керування "
            "invite-посиланнями."
        ),
        reply_markup=(
            build_keyboard(
                root_admin_invites_keyboard
            )
        ),
    )


# =========================================================
# IMPORT
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.IMPORT
    )
)
async def root_import_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Import menu.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "📥 <b>Імпорт торгових точок</b>\n\n"
            "Завантажте Excel-файл "
            "із даними ТТ.\n\n"
            "Перед застосуванням "
            "бот покаже preview."
        ),
        reply_markup=(
            build_keyboard(
                root_admin_import_keyboard
            )
        ),
    )


@router.callback_query(
    ImportCallback.filter(
        F.action
        == ImportAction.UPLOAD
    )
)
async def import_upload_callback(
    callback: CallbackQuery,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Waiting Excel.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    await state.set_state(
        RootAdminStates
        .waiting_import_file
    )

    await safe_edit(
        callback,
        text=(
            "📎 <b>Надішліть файл</b>\n\n"
            "Підтримується Excel.\n\n"
            "Для скасування:\n"
            "<code>/cancel</code>"
        ),
        reply_markup=None,
    )


@router.message(
    RootAdminStates.waiting_import_file
)
async def import_file_message(
    message: Message,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Отримання Excel для import.
    """

    user = await require_root(
        message,
        data=data,
    )

    if user is None:
        await state.clear()
        return

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
            "❌ Імпорт скасовано."
        )

        return

    document = message.document

    if document is None:
        await message.answer(
            "⚠️ Надішліть Excel-файл "
            "як документ."
        )

        return

    filename = (
        document.file_name
        or ""
    ).lower()

    if not filename.endswith(
        (
            ".xlsx",
            ".xls",
        )
    ):
        await message.answer(
            "⚠️ Потрібен файл "
            "<code>.xlsx</code> або "
            "<code>.xls</code>."
        )

        return

    # Зберігаємо Telegram file_id.
    # Сам download/preview виконаємо
    # через ImportService/FileService.
    await state.update_data(
        import_file_id=(
            document.file_id
        ),
        import_filename=(
            document.file_name
        ),
    )

    await state.clear()

    await message.answer(
        "✅ <b>Файл отримано.</b>\n\n"
        f"📄 {escape(document.file_name or 'Excel')}\n\n"
        "Файл готовий до preview.",
        reply_markup=(
            build_keyboard(
                root_admin_import_preview_keyboard,
                token=0,
                filename=(
                    document.file_name
                ),
            )
        ),
    )


# =========================================================
# SETTINGS
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.SETTINGS
    )
)
async def root_settings_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Settings.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    bot_enabled = await get_setting_bool(
        key="bot_enabled",
        data=data,
        default=True,
    )

    maintenance = await get_setting_bool(
        key="maintenance_enabled",
        data=data,
        default=False,
    )

    timezone = await get_setting_value(
        key="timezone",
        data=data,
        default="Europe/Kyiv",
    )

    await safe_edit(
        callback,
        text=(
            "⚙️ <b>Налаштування</b>\n\n"
            f"🤖 Bot enabled: "
            f"<b>{'так' if bot_enabled else 'ні'}</b>\n"
            f"🛠 Maintenance: "
            f"<b>{'так' if maintenance else 'ні'}</b>\n"
            f"🌍 Timezone: "
            f"<code>{escape(str(timezone))}</code>"
        ),
        reply_markup=(
            build_keyboard(
                root_admin_settings_keyboard,
                bot_enabled=bot_enabled,
                maintenance_enabled=(
                    maintenance
                ),
            )
        ),
    )


# =========================================================
# SYSTEM
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.SYSTEM
    )
)
async def root_system_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    System.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    bot_enabled = await get_setting_bool(
        key="bot_enabled",
        data=data,
        default=True,
    )

    maintenance = await get_setting_bool(
        key="maintenance_enabled",
        data=data,
        default=False,
    )

    await safe_edit(
        callback,
        text=(
            "🖥 <b>Система</b>\n\n"
            f"🤖 Бот: "
            f"<b>{'ON' if bot_enabled else 'OFF'}</b>\n"
            f"🛠 Maintenance: "
            f"<b>{'ON' if maintenance else 'OFF'}</b>"
        ),
        reply_markup=(
            build_keyboard(
                root_admin_system_keyboard,
                bot_enabled=bot_enabled,
                maintenance_enabled=(
                    maintenance
                ),
            )
        ),
    )


# =========================================================
# BOT TOGGLE
# =========================================================


@router.callback_query(
    SettingsCallback.filter(
        F.action
        == SettingsAction.BOT
    )
)
async def toggle_bot_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    ON/OFF bot.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    current = await get_setting_bool(
        key="bot_enabled",
        data=data,
        default=True,
    )

    success = await set_setting_value(
        key="bot_enabled",
        value=not current,
        user=user,
        data=data,
    )

    if not success:
        await callback.answer(
            "Не вдалося змінити setting.",
            show_alert=True,
        )

        return

    await callback.answer(
        "Налаштування змінено ✅"
    )

    await root_system_callback(
        callback,
        **data,
    )


# =========================================================
# MAINTENANCE TOGGLE
# =========================================================


@router.callback_query(
    SettingsCallback.filter(
        F.action
        == SettingsAction.MAINTENANCE
    )
)
async def toggle_maintenance_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Maintenance ON/OFF.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    current = await get_setting_bool(
        key="maintenance_enabled",
        data=data,
        default=False,
    )

    success = await set_setting_value(
        key="maintenance_enabled",
        value=not current,
        user=user,
        data=data,
    )

    if not success:
        await callback.answer(
            "Не вдалося змінити setting.",
            show_alert=True,
        )

        return

    await callback.answer(
        "Maintenance змінено ✅"
    )

    bot_enabled = await get_setting_bool(
        key="bot_enabled",
        data=data,
        default=True,
    )

    updated = not current

    await safe_edit(
        callback,
        text=(
            "🖥 <b>Система</b>\n\n"
            f"🤖 Бот: "
            f"<b>{'ON' if bot_enabled else 'OFF'}</b>\n"
            f"🛠 Maintenance: "
            f"<b>{'ON' if updated else 'OFF'}</b>"
        ),
        reply_markup=(
            build_keyboard(
                root_admin_system_keyboard,
                bot_enabled=bot_enabled,
                maintenance_enabled=(
                    updated
                ),
            )
        ),
    )


# =========================================================
# GROUPS
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.GROUPS
    )
)
async def root_groups_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Telegram groups.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "💬 <b>Telegram-групи</b>\n\n"
            "Налаштування груп та topic "
            "для сповіщень."
        ),
        reply_markup=(
            build_keyboard(
                root_admin_groups_keyboard
            )
        ),
    )


@router.callback_query(
    GroupCallback.filter(
        F.action
        == GroupAction.NETWORK
    )
)
async def network_group_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Network group settings.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "🌐 <b>Група мережі</b>\n\n"
            "Тут налаштовується головна "
            "Telegram-група для системних "
            "сповіщень."
        ),
        reply_markup=(
            build_keyboard(
                root_admin_network_group_keyboard
            )
        ),
    )


# =========================================================
# AUDIT
# =========================================================


@router.callback_query(
    RootAdminCallback.filter(
        F.action
        == RootAdminAction.AUDIT
    )
)
async def root_audit_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Audit menu.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "📜 <b>Audit Log</b>\n\n"
            "Історія системних дій, "
            "коригувань та змін."
        ),
        reply_markup=(
            build_keyboard(
                root_admin_audit_keyboard
            )
        ),
    )


# =========================================================
# AUDIT LIST
# =========================================================


@router.callback_query(
    AuditCallback.filter(
        F.action
        == AuditActionCallback.LIST
    )
)
async def audit_list_callback(
    callback: CallbackQuery,
    callback_data: AuditCallback,
    **data: Any,
) -> None:
    """
    Останні audit events.
    """

    user = await require_root(
        callback,
        data=data,
    )

    if user is None:
        return

    await callback.answer()

    service = get_service(
        data,
        "audit",
    )

    if service is None:
        await callback.answer(
            "AuditService недоступний.",
            show_alert=True,
        )

        return

    result = None

    for method_name in (
        "list_entries",
        "list_audit",
        "search",
        "get_page",
        "list",
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
                {
                    "user": user,
                    "actor": user,
                    "page": (
                        callback_data.page
                    ),
                    "limit": PAGE_SIZE,
                    "page_size": PAGE_SIZE,
                },
            )

            break

        except Exception:
            continue

    entries = unwrap_collection(
        result
    )

    lines = [
        "📜 <b>Audit Log</b>",
        "",
    ]

    if not entries:
        lines.append(
            "Записів немає."
        )

    else:
        for entry in entries[
            :PAGE_SIZE
        ]:
            action = first_attr(
                entry,
                "action",
                "event",
                default="action",
            )

            description = first_attr(
                entry,
                "description",
                "message",
                default="",
            )

            lines.append(
                "• "
                f"<b>{escape(str(action))}</b>"
                + (
                    f" — {escape(str(description))}"
                    if description
                    else ""
                )
            )

    await safe_edit(
        callback,
        text="\n".join(
            lines
        ),
        reply_markup=(
            build_keyboard(
                root_admin_audit_keyboard,
                page=(
                    callback_data.page
                ),
            )
        ),
    )


# =========================================================
# UNKNOWN ROOT CALLBACK
# =========================================================


@router.callback_query(
    RootAdminCallback.filter()
)
async def unknown_root_callback(
    callback: CallbackQuery,
) -> None:
    """
    Старі RootAdminCallback.
    """

    await callback.answer(
        "Ця кнопка ще не підключена "
        "або вже неактуальна.",
        show_alert=False,
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "router",

    "PAGE_SIZE",

    "ROOT_ROLE_NAMES",
    "PENDING_STATUS_NAMES",
    "BLOCKED_STATUS_NAMES",
    "ACTIVE_STATUS_NAMES",

    "RootAdminStates",

    "is_root_admin",
    "require_root",

    "normalized_status",
    "username_text",
    "object_name",

    "get_repositories",
    "flush_changes",

    "get_setting_value",
    "get_setting_bool",
    "set_setting_value",

    "query_clusters",
    "cluster_time_text",
    "count_cluster_stores",

    "build_root_store_item",
    "build_root_store_items",

    "build_root_bush_items",
    "build_root_cluster_items",
    "build_root_user_item",

    "build_root_dashboard",
    "build_dashboard_text",

    "show_dashboard_callback",
    "show_dashboard_message",

    "show_users",

    "load_user",
    "show_user_card",

    "auth_user_action",
    "execute_user_action",

    "show_opening_list",
    "show_closing_list",
]