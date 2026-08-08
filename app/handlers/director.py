from __future__ import annotations

import inspect
import logging
from html import escape
from typing import Any, Iterable

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
from app.handlers.lion import (
    build_bush_choices,
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
    is_store_active,
    load_bush,
)
from app.keyboards.bush_admin import (
    BushAdminAction,
    BushAdminCallback,
    BushAdminDashboardState,
    BushAdminStoreItem,
    BushAdminStoreState,
    BushAdminUserItem,
    bush_admin_closing_keyboard,
    bush_admin_invites_keyboard,
    bush_admin_late_keyboard,
    bush_admin_lions_keyboard,
    bush_admin_main_keyboard,
    bush_admin_missing_closing_keyboard,
    bush_admin_missing_opening_keyboard,
    bush_admin_no_stores_keyboard,
    bush_admin_opening_keyboard,
    bush_admin_reports_keyboard,
    bush_admin_schedules_keyboard,
    bush_admin_select_bush_keyboard,
    bush_admin_stores_keyboard,
    bush_admin_users_keyboard,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="bush_admin",
)


# =========================================================
# CONSTANTS
# =========================================================


PAGE_SIZE = 10


ALLOWED_ROLES = {
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
    Приводить різні service/repository
    responses до list.
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
        "users",
        "stores",
        "results",
        "records",
        "data",
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


def filtered_kwargs(
    target: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Залишає тільки kwargs,
    які підтримує target.
    """

    try:
        signature = inspect.signature(
            target
        )

    except (
        TypeError,
        ValueError,
    ):
        return payload

    accepts_kwargs = any(
        parameter.kind
        == inspect.Parameter.VAR_KEYWORD
        for parameter
        in signature.parameters.values()
    )

    if accepts_kwargs:
        return payload

    return {
        key: value
        for key, value
        in payload.items()
        if key in signature.parameters
    }


def create_model(
    target: Any,
    **payload: Any,
) -> Any:
    """
    Безпечне створення dataclass/model.

    Це дає нам трохи захисту,
    якщо в keyboard dataclass
    назви optional полів відрізняються.
    """

    kwargs = filtered_kwargs(
        target,
        payload,
    )

    return target(
        **kwargs
    )


def build_keyboard(
    factory: Any,
    **payload: Any,
) -> InlineKeyboardMarkup:
    """
    Викликає keyboard factory тільки
    з підтримуваними kwargs.
    """

    kwargs = filtered_kwargs(
        factory,
        payload,
    )

    return factory(
        **kwargs
    )


def enum_member(
    enum_class: Any,
    *names: str,
) -> Any:
    """
    Пошук enum member за кількома
    можливими назвами.
    """

    for name in names:
        member = getattr(
            enum_class,
            name,
            None,
        )

        if member is not None:
            return member

    try:
        return next(
            iter(enum_class)
        )

    except Exception as error:
        raise RuntimeError(
            f"Не знайдено member у {enum_class}"
        ) from error


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
                "user_id",
                "store_id",
                default=0,
            )
        ),
    )


# =========================================================
# ROLE ACCESS
# =========================================================


def can_use_bush_admin_panel(
    user: DatabaseUser | None,
) -> bool:
    """
    Доступ до панелі куща.
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
    Глобальний доступ.
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
# BUSH SELECTOR
# =========================================================


async def show_bush_selection_callback(
    callback: CallbackQuery,
    *,
    data: dict[str, Any],
) -> None:
    """
    Вибір куща через callback.
    """

    bushes = await build_bush_choices(
        data=data
    )

    if not bushes:
        await safe_edit(
            callback,
            text=(
                "🌿 <b>Адміністрування куща</b>\n\n"
                "⚠️ Немає доступних кущів."
            ),
            reply_markup=(
                bush_admin_no_stores_keyboard()
            ),
        )

        return

    await safe_edit(
        callback,
        text=(
            "🌿 <b>Адміністрування куща</b>\n\n"
            "Оберіть кущ:"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_select_bush_keyboard,
                bushes=bushes,
            )
        ),
    )


async def show_bush_selection_message(
    message: Message,
    *,
    data: dict[str, Any],
) -> None:
    """
    Вибір куща через command.
    """

    bushes = await build_bush_choices(
        data=data
    )

    if not bushes:
        await message.answer(
            "🌿 <b>Адміністрування куща</b>\n\n"
            "⚠️ Немає доступних кущів.",
            reply_markup=(
                bush_admin_no_stores_keyboard()
            ),
        )

        return

    await message.answer(
        "🌿 <b>Адміністрування куща</b>\n\n"
        "Оберіть кущ:",
        reply_markup=(
            build_keyboard(
                bush_admin_select_bush_keyboard,
                bushes=bushes,
            )
        ),
    )


# =========================================================
# STORES
# =========================================================


async def load_bush_stores(
    *,
    bush_id: int,
    data: dict[str, Any],
) -> list[Any]:
    """
    Всі ТТ куща.

    Використовує вже готову
    robust-логіку з lion handler.
    """

    return await load_lion_stores(
        bush_id=bush_id,
        data=data,
    )


def store_object_id(
    store: Any,
) -> int:
    """
    Store ID.
    """

    if isinstance(
        store,
        int,
    ):
        return max(
            0,
            store,
        )

    return max(
        0,
        to_int(
            first_attr(
                store,
                "id",
                "store_id",
                default=0,
            )
        ),
    )


def store_code(
    store: Any,
) -> str:
    """
    SB-XX.
    """

    store_id = store_object_id(
        store
    )

    value = first_attr(
        store,
        "code",
        "store_code",
        default=None,
    )

    if value:
        return str(
            value
        )

    return (
        f"ТТ-{store_id}"
    )


def store_name(
    store: Any,
) -> str | None:
    """
    Назва / адреса ТТ.
    """

    value = first_attr(
        store,
        "name",
        "title",
        "address",
        default=None,
    )

    if not value:
        return None

    return str(
        value
    )


# =========================================================
# STORE STATE
# =========================================================


async def get_store_runtime_state(
    *,
    store: Any,
    user: DatabaseUser | None,
    data: dict[str, Any],
    context: str = "general",
) -> tuple[
    Any,
    int,
]:
    """
    Повертає:

        BushAdminStoreState
        lateness_minutes
    """

    store_id = store_object_id(
        store
    )

    if not is_store_active(
        store
    ):
        return (
            enum_member(
                BushAdminStoreState,
                "INACTIVE",
            ),
            0,
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

    closing_started = (
        closing_exists(
            closing
        )
    )

    closed = result_is_completed(
        closing
    )

    # -----------------------------------------------------
    # CLOSED
    # -----------------------------------------------------

    if closed:
        return (
            enum_member(
                BushAdminStoreState,
                "CLOSED",
            ),
            late_minutes,
        )

    # -----------------------------------------------------
    # CLOSING
    # -----------------------------------------------------

    if context == "closing":
        if closing_started:
            return (
                enum_member(
                    BushAdminStoreState,
                    "CLOSING_IN_PROGRESS",
                    "CLOSING_STARTED",
                    "WAITING_CLOSING",
                ),
                late_minutes,
            )

        if opened:
            return (
                enum_member(
                    BushAdminStoreState,
                    "WAITING_CLOSING",
                    "OPENED_ON_TIME",
                ),
                late_minutes,
            )

    # -----------------------------------------------------
    # OPENING
    # -----------------------------------------------------

    if opened:
        if late_minutes > 0:
            return (
                enum_member(
                    BushAdminStoreState,
                    "OPENED_LATE",
                ),
                late_minutes,
            )

        return (
            enum_member(
                BushAdminStoreState,
                "OPENED_ON_TIME",
            ),
            0,
        )

    return (
        enum_member(
            BushAdminStoreState,
            "WAITING_OPENING",
            "NOT_OPENED",
        ),
        0,
    )


async def build_store_item(
    *,
    store: Any,
    user: DatabaseUser | None,
    data: dict[str, Any],
    context: str = "general",
) -> BushAdminStoreItem:
    """
    Store -> BushAdminStoreItem.
    """

    store_id = store_object_id(
        store
    )

    state, late_minutes = (
        await get_store_runtime_state(
            store=store,
            user=user,
            data=data,
            context=context,
        )
    )

    return create_model(
        BushAdminStoreItem,

        store_id=store_id,

        code=store_code(
            store
        ),

        name=store_name(
            store
        ),

        state=state,

        lateness_minutes=(
            late_minutes
        ),

        is_active=(
            is_store_active(
                store
            )
        ),
    )


async def build_store_items(
    *,
    stores: list[Any],
    user: DatabaseUser | None,
    data: dict[str, Any],
    context: str = "general",
) -> list[
    BushAdminStoreItem
]:
    """
    Побудова станів усіх ТТ.
    """

    result: list[
        BushAdminStoreItem
    ] = []

    for store in stores:
        try:
            item = await build_store_item(
                store=store,
                user=user,
                data=data,
                context=context,
            )

        except Exception:
            logger.exception(
                "Failed building bush admin "
                "store item: store_id=%s",
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
# USERS
# =========================================================


async def query_bush_users(
    *,
    bush_id: int,
    data: dict[str, Any],
) -> list[Any]:
    """
    Користувачі куща.
    """

    payload = {
        "bush_id": bush_id,

        "include_inactive":
            True,

        "active_only":
            False,
    }

    # -----------------------------------------------------
    # USER SERVICE
    # -----------------------------------------------------

    service = get_service(
        data,
        "users",
        "user",
    )

    if service is not None:
        for method_name in (
            "list_by_bush",
            "get_by_bush",
            "get_bush_users",
            "list_bush_users",
            "search_by_bush",
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

    # -----------------------------------------------------
    # BINDINGS SERVICE
    # -----------------------------------------------------

    bindings_service = get_service(
        data,
        "bindings",
        "binding",
    )

    if bindings_service is not None:
        for method_name in (
            "get_bush_users",
            "list_bush_users",
            "users_for_bush",
        ):
            method = getattr(
                bindings_service,
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
        "users",
        None,
    )

    if repository is None:
        return []

    for method_name in (
        "list_by_bush",
        "get_by_bush",
        "get_bush_users",
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


def normalized_role(
    user: Any,
) -> str:
    """
    Роль користувача.
    """

    role = first_attr(
        user,
        "role",
        default=None,
    )

    if role is None:
        return ""

    raw = first_attr(
        role,
        "name",
        "value",
        default=role,
    )

    return (
        str(raw)
        .strip()
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


def user_display_name(
    user: Any,
) -> str:
    """
    Людське ім'я.
    """

    full_name = first_attr(
        user,
        "full_name",
        "display_name",
        default=None,
    )

    if full_name:
        return str(
            full_name
        )

    first_name = first_attr(
        user,
        "first_name",
        default=None,
    )

    last_name = first_attr(
        user,
        "last_name",
        default=None,
    )

    parts = [
        str(part)
        for part in (
            first_name,
            last_name,
        )
        if part
    ]

    if parts:
        return " ".join(
            parts
        )

    username = first_attr(
        user,
        "username",
        default=None,
    )

    if username:
        return (
            "@"
            + str(username)
            .lstrip("@")
        )

    return (
        f"Користувач #{object_id(user)}"
    )


def role_label(
    role_name: str,
) -> str:
    """
    Назва ролі.
    """

    mapping = {
        "ROOT_ADMIN":
            "👑 Root",

        "DIRECTOR":
            "🏢 Директор",

        "BUSH_ADMIN":
            "🌿 Адмін куща",

        "LION":
            "🦁 Лев",

        "STORE_USER":
            "🏪 ТТ",
    }

    return mapping.get(
        role_name,
        role_name
        or "—",
    )


def user_is_active(
    user: Any,
) -> bool:
    """
    Активність user.
    """

    direct = first_attr(
        user,
        "is_active",
        "active",
        default=None,
    )

    if direct is not None:
        return to_bool(
            direct,
            default=True,
        )

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

    return (
        str(raw)
        .strip()
        .upper()
        in {
            "ACTIVE",
            "APPROVED",
        }
    )


def build_user_item(
    user: Any,
) -> BushAdminUserItem:
    """
    User -> keyboard item.
    """

    role_name = normalized_role(
        user
    )

    username = first_attr(
        user,
        "username",
        default=None,
    )

    return create_model(
        BushAdminUserItem,

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


async def build_dashboard(
    *,
    bush_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> tuple[
    BushAdminDashboardState,
    list[Any],
    list[Any],
]:
    """
    Dashboard куща.
    """

    stores = await load_bush_stores(
        bush_id=bush_id,
        data=data,
    )

    users = await query_bush_users(
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
        await build_store_items(
            stores=active_stores,
            user=user,
            data=data,
            context="opening",
        )
    )

    closing_items = (
        await build_store_items(
            stores=active_stores,
            user=user,
            data=data,
            context="closing",
        )
    )

    opened_on_time_state = (
        enum_member(
            BushAdminStoreState,
            "OPENED_ON_TIME",
        )
    )

    opened_late_state = (
        enum_member(
            BushAdminStoreState,
            "OPENED_LATE",
        )
    )

    waiting_opening_state = (
        enum_member(
            BushAdminStoreState,
            "WAITING_OPENING",
            "NOT_OPENED",
        )
    )

    closed_state = (
        enum_member(
            BushAdminStoreState,
            "CLOSED",
        )
    )

    waiting_closing_state = (
        enum_member(
            BushAdminStoreState,
            "WAITING_CLOSING",
            "OPENED_ON_TIME",
        )
    )

    closing_progress_state = (
        enum_member(
            BushAdminStoreState,
            "CLOSING_IN_PROGRESS",
            "CLOSING_STARTED",
            "WAITING_CLOSING",
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

    lions_count = sum(
        1
        for item in users
        if normalized_role(
            item
        )
        == "LION"
    )

    active_users_count = sum(
        1
        for item in users
        if user_is_active(
            item
        )
    )

    state = create_model(
        BushAdminDashboardState,

        bush_id=bush_id,

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

        users_count=len(
            users
        ),

        active_users_count=(
            active_users_count
        ),

        lions_count=(
            lions_count
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
        users,
    )


# =========================================================
# DASHBOARD TEXT
# =========================================================


async def build_dashboard_text(
    *,
    state: BushAdminDashboardState,
    bush_id: int,
    data: dict[str, Any],
) -> str:
    """
    Текст dashboard.
    """

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    total_stores = to_int(
        first_attr(
            state,
            "total_stores",
            "active_stores",
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

    users_count = to_int(
        first_attr(
            state,
            "users_count",
            default=0,
        )
    )

    lions_count = to_int(
        first_attr(
            state,
            "lions_count",
            default=0,
        )
    )

    lines = [
        "🌿 <b>Панель адміністратора куща</b>",
        "",
        f"📍 Кущ: <b>{escape(bush_name)}</b>",
        "",
        (
            "🏪 Активних ТТ: "
            f"<b>{total_stores}</b>"
        ),
        (
            "👥 Користувачів: "
            f"<b>{users_count}</b>"
        ),
        (
            "🦁 Левів: "
            f"<b>{lions_count}</b>"
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

    state, stores, users = (
        await build_dashboard(
            bush_id=bush_id,
            user=user,
            data=data,
        )
    )

    text = await build_dashboard_text(
        state=state,
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=text,
        reply_markup=(
            build_keyboard(
                bush_admin_main_keyboard,

                state=state,

                bush_id=bush_id,
            )
        ),
    )


async def show_dashboard_message(
    message: Message,
    *,
    bush_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> None:
    """
    Dashboard через /bush.
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

    state, stores, users = (
        await build_dashboard(
            bush_id=bush_id,
            user=user,
            data=data,
        )
    )

    text = await build_dashboard_text(
        state=state,
        bush_id=bush_id,
        data=data,
    )

    await message.answer(
        text,
        reply_markup=(
            build_keyboard(
                bush_admin_main_keyboard,

                state=state,

                bush_id=bush_id,
            )
        ),
    )


# =========================================================
# /BUSH
# =========================================================


@router.message(
    Command(
        "bush",
        "bush_admin",
    )
)
async def bush_admin_command(
    message: Message,
    **data: Any,
) -> None:
    """
    /bush
    """

    user = get_database_user(
        data
    )

    if not can_use_bush_admin_panel(
        user
    ):
        await message.answer(
            "⛔ Панель адміністратора "
            "куща вам недоступна."
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

    await show_dashboard_message(
        message,
        bush_id=bush_id,
        user=user,
        data=data,
    )


# =========================================================
# MENU / DASHBOARD / REFRESH
# =========================================================


@router.callback_query(
    BushAdminCallback.filter(
        F.action.in_(
            {
                BushAdminAction.MENU,
                BushAdminAction.DASHBOARD,
                BushAdminAction.REFRESH,
            }
        )
    )
)
async def bush_admin_dashboard_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
    **data: Any,
) -> None:
    """
    Dashboard.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    if not can_use_bush_admin_panel(
        user
    ):
        await callback.answer(
            "Немає доступу до панелі.",
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

    await show_dashboard_callback(
        callback,
        bush_id=bush_id,
        user=user,
        data=data,
    )


# =========================================================
# STORES
# =========================================================


@router.callback_query(
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.STORES
    )
)
async def bush_admin_stores_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
    **data: Any,
) -> None:
    """
    Усі ТТ куща.
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

    stores = await load_bush_stores(
        bush_id=bush_id,
        data=data,
    )

    items = await build_store_items(
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
        page_size=PAGE_SIZE,
    )

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "🏪 <b>Торгові точки куща</b>\n\n"
            f"🌿 {escape(bush_name)}\n"
            f"Усього: <b>{len(items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_stores_keyboard,

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
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.OPENING
    )
)
async def bush_admin_opening_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
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

    stores = await load_bush_stores(
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

    items = await build_store_items(
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

    opened_on_time_state = (
        enum_member(
            BushAdminStoreState,
            "OPENED_ON_TIME",
        )
    )

    opened_late_state = (
        enum_member(
            BushAdminStoreState,
            "OPENED_LATE",
        )
    )

    waiting_state = (
        enum_member(
            BushAdminStoreState,
            "WAITING_OPENING",
            "NOT_OPENED",
        )
    )

    opened = sum(
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

    late = sum(
        1
        for item in items
        if first_attr(
            item,
            "state",
        )
        == opened_late_state
    )

    missing = sum(
        1
        for item in items
        if first_attr(
            item,
            "state",
        )
        == waiting_state
    )

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "🌅 <b>Live — відкриття куща</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            f"✅ Відкрилися: "
            f"<b>{opened}/{len(items)}</b>\n"
            f"⚠️ Запізнилися: "
            f"<b>{late}</b>\n"
            f"🚨 Не відкрилися: "
            f"<b>{missing}</b>"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_opening_keyboard,

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
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.LATE
    )
)
async def bush_admin_late_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
    **data: Any,
) -> None:
    """
    Запізнення.
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

    stores = await load_bush_stores(
        bush_id=bush_id,
        data=data,
    )

    items = await build_store_items(
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

    opened_late_state = (
        enum_member(
            BushAdminStoreState,
            "OPENED_LATE",
        )
    )

    late_items = [
        item
        for item in items
        if first_attr(
            item,
            "state",
        )
        == opened_late_state
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
    )

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "⚠️ <b>Запізнення куща</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            f"ТТ із запізненням: "
            f"<b>{len(late_items)}</b>\n"
            f"Сумарно: "
            f"<b>{total_minutes} хв.</b>"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_late_keyboard,

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
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.MISSING_OPENING
    )
)
async def bush_admin_missing_opening_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
    **data: Any,
) -> None:
    """
    ТТ без check-in.
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

    stores = await load_bush_stores(
        bush_id=bush_id,
        data=data,
    )

    items = await build_store_items(
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

    waiting_state = (
        enum_member(
            BushAdminStoreState,
            "WAITING_OPENING",
            "NOT_OPENED",
        )
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
            f"ТТ без відкриття: "
            f"<b>{len(missing_items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_missing_opening_keyboard,

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
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.CLOSING
    )
)
async def bush_admin_closing_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
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

    stores = await load_bush_stores(
        bush_id=bush_id,
        data=data,
    )

    items = await build_store_items(
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

    closed_state = (
        enum_member(
            BushAdminStoreState,
            "CLOSED",
        )
    )

    progress_state = (
        enum_member(
            BushAdminStoreState,
            "CLOSING_IN_PROGRESS",
            "CLOSING_STARTED",
            "WAITING_CLOSING",
        )
    )

    waiting_state = (
        enum_member(
            BushAdminStoreState,
            "WAITING_CLOSING",
            "OPENED_ON_TIME",
        )
    )

    closed = sum(
        1
        for item in items
        if first_attr(
            item,
            "state",
        )
        == closed_state
    )

    progress = sum(
        1
        for item in items
        if first_attr(
            item,
            "state",
        )
        == progress_state
    )

    waiting = sum(
        1
        for item in items
        if (
            first_attr(
                item,
                "state",
            )
            == waiting_state
            and first_attr(
                item,
                "state",
            )
            != closed_state
        )
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
            "🌙 <b>Live — закриття куща</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            f"✅ Закрилися: "
            f"<b>{closed}/{len(items)}</b>\n"
            f"🔄 В процесі: "
            f"<b>{progress}</b>\n"
            f"⏳ Очікують: "
            f"<b>{waiting}</b>"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_closing_keyboard,

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
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.MISSING_CLOSING
    )
)
async def bush_admin_missing_closing_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
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

    stores = await load_bush_stores(
        bush_id=bush_id,
        data=data,
    )

    missing_items: list[
        BushAdminStoreItem
    ] = []

    for store in stores:
        if not is_store_active(
            store
        ):
            continue

        store_id = store_object_id(
            store
        )

        opening = await get_opening_status(
            store_id=store_id,
            user=user,
            data=data,
        )

        # Якщо ТТ сьогодні взагалі
        # не відкривалася — не рахуємо
        # її як "не закрилася".
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

        item = await build_store_item(
            store=store,
            user=user,
            data=data,
            context="closing",
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
            f"Незавершених ТТ: "
            f"<b>{len(missing_items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_missing_closing_keyboard,

                bush_id=bush_id,

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
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.USERS
    )
)
async def bush_admin_users_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
    **data: Any,
) -> None:
    """
    Всі користувачі куща.
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

    users = await query_bush_users(
        bush_id=bush_id,
        data=data,
    )

    items = [
        build_user_item(
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
    )

    bush_name = await get_bush_title(
        bush_id=bush_id,
        data=data,
    )

    await safe_edit(
        callback,
        text=(
            "👥 <b>Користувачі куща</b>\n\n"
            f"🌿 {escape(bush_name)}\n"
            f"Усього: <b>{len(items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_users_keyboard,

                bush_id=bush_id,

                users=page_items,

                page=page,

                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# LIONS
# =========================================================


@router.callback_query(
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.LIONS
    )
)
async def bush_admin_lions_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
    **data: Any,
) -> None:
    """
    Леви конкретного куща.
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

    users = await query_bush_users(
        bush_id=bush_id,
        data=data,
    )

    lions = [
        user
        for user in users
        if normalized_role(
            user
        )
        == "LION"
    ]

    items = [
        build_user_item(
            user
        )
        for user in lions
    ]

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
            "🦁 <b>Леви куща</b>\n\n"
            f"🌿 {escape(bush_name)}\n"
            f"Усього: <b>{len(items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_lions_keyboard,

                bush_id=bush_id,

                users=page_items,

                lions=page_items,

                page=page,

                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# SCHEDULES
# =========================================================


@router.callback_query(
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.SCHEDULES
    )
)
async def bush_admin_schedules_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
    **data: Any,
) -> None:
    """
    Графіки ТТ куща.
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

    stores = await load_bush_stores(
        bush_id=bush_id,
        data=data,
    )

    items = await build_store_items(
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
            "🕐 <b>Графіки ТТ</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            "Оберіть торгову точку:"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_schedules_keyboard,

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
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.REPORTS
    )
)
async def bush_admin_reports_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
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
            "📊 <b>Звіти куща</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            "Оберіть потрібний період:"
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_reports_keyboard,
                bush_id=bush_id,
            )
        ),
    )


# =========================================================
# INVITES
# =========================================================


@router.callback_query(
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.INVITES
    )
)
async def bush_admin_invites_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
    **data: Any,
) -> None:
    """
    Invite для працівників куща.
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
            "🔗 <b>Запрошення</b>\n\n"
            f"🌿 {escape(bush_name)}\n\n"
            "Тут можна створити "
            "посилання для нового "
            "користувача куща."
        ),
        reply_markup=(
            build_keyboard(
                bush_admin_invites_keyboard,
                bush_id=bush_id,
            )
        ),
    )


# =========================================================
# BACK
# =========================================================


@router.callback_query(
    BushAdminCallback.filter(
        F.action
        == BushAdminAction.BACK
    )
)
async def bush_admin_back_callback(
    callback: CallbackQuery,
    callback_data: BushAdminCallback,
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

    await show_dashboard_callback(
        callback,
        bush_id=bush_id,
        user=user,
        data=data,
    )


# =========================================================
# UNKNOWN
# =========================================================


@router.callback_query(
    BushAdminCallback.filter()
)
async def unknown_bush_admin_callback(
    callback: CallbackQuery,
) -> None:
    """
    Захист від старих callback.
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
    "filtered_kwargs",
    "create_model",
    "build_keyboard",
    "enum_member",
    "object_id",

    "can_use_bush_admin_panel",

    "has_network_access",
    "accessible_bush_ids",
    "can_view_bush",
    "resolve_bush_id",

    "show_bush_selection_callback",
    "show_bush_selection_message",

    "load_bush_stores",

    "store_object_id",
    "store_code",
    "store_name",

    "get_store_runtime_state",
    "build_store_item",
    "build_store_items",

    "query_bush_users",

    "normalized_role",
    "user_display_name",
    "role_label",
    "user_is_active",
    "build_user_item",

    "build_dashboard",
    "build_dashboard_text",

    "show_dashboard_callback",
    "show_dashboard_message",
] 

# =========================================================
# DIRECTOR COMPATIBILITY HELPERS
# =========================================================


def object_id(
    value: Any,
) -> int:
    """
    Повертає internal ID будь-якої моделі.
    """

    if value is None:
        return 0

    if isinstance(value, dict):
        for key in (
            "id",
            "object_id",
            "store_id",
            "bush_id",
            "user_id",
        ):
            raw = value.get(key)

            if raw is not None:
                try:
                    return int(raw)
                except (
                    TypeError,
                    ValueError,
                ):
                    pass

        return 0

    for attr_name in (
        "id",
        "object_id",
        "store_id",
        "bush_id",
        "user_id",
    ):
        raw = getattr(
            value,
            attr_name,
            None,
        )

        if raw is None:
            continue

        try:
            return int(raw)

        except (
            TypeError,
            ValueError,
        ):
            continue

    return 0


def object_is_active(
    value: Any,
) -> bool:
    """
    Чи активний об'єкт.
    """

    if value is None:
        return False

    if isinstance(value, dict):
        raw = value.get(
            "is_active",
            value.get(
                "active",
                True,
            ),
        )

    else:
        raw = getattr(
            value,
            "is_active",
            getattr(
                value,
                "active",
                True,
            ),
        )

    if isinstance(
        raw,
        str,
    ):
        normalized = (
            raw.strip().lower()
        )

        if normalized in {
            "0",
            "false",
            "no",
            "inactive",
            "disabled",
            "deleted",
        }:
            return False

        if normalized in {
            "1",
            "true",
            "yes",
            "active",
            "enabled",
        }:
            return True

    return bool(raw)


def store_code(
    store: Any,
) -> str:
    """
    Код ТТ.
    """

    if store is None:
        return "—"

    if isinstance(
        store,
        dict,
    ):
        value = (
            store.get("code")
            or store.get("store_code")
            or store.get("number")
        )

    else:
        value = (
            getattr(
                store,
                "code",
                None,
            )
            or getattr(
                store,
                "store_code",
                None,
            )
            or getattr(
                store,
                "number",
                None,
            )
        )

    if value:
        return str(value)

    identifier = object_id(
        store
    )

    return (
        f"ТТ-{identifier}"
        if identifier
        else "—"
    )


def store_name(
    store: Any,
) -> str:
    """
    Назва / адреса ТТ.
    """

    if store is None:
        return "Торгова точка"

    if isinstance(
        store,
        dict,
    ):
        value = (
            store.get("name")
            or store.get("title")
            or store.get("address")
        )

    else:
        value = (
            getattr(
                store,
                "name",
                None,
            )
            or getattr(
                store,
                "title",
                None,
            )
            or getattr(
                store,
                "address",
                None,
            )
        )

    if value:
        return str(value)

    return store_code(
        store
    )


def store_bush_name(
    store: Any,
) -> str:
    """
    Назва куща ТТ.
    """

    if store is None:
        return "—"

    if isinstance(
        store,
        dict,
    ):
        direct = (
            store.get("bush_name")
            or store.get("group_name")
        )

        bush = store.get(
            "bush"
        )

    else:
        direct = (
            getattr(
                store,
                "bush_name",
                None,
            )
            or getattr(
                store,
                "group_name",
                None,
            )
        )

        bush = getattr(
            store,
            "bush",
            None,
        )

    if direct:
        return str(direct)

    if bush is not None:
        if isinstance(
            bush,
            dict,
        ):
            value = (
                bush.get("name")
                or bush.get("title")
            )

        else:
            value = (
                getattr(
                    bush,
                    "name",
                    None,
                )
                or getattr(
                    bush,
                    "title",
                    None,
                )
            )

        if value:
            return str(value)

    bush_id = 0

    if isinstance(
        store,
        dict,
    ):
        bush_id = store.get(
            "bush_id",
            0,
        )

    else:
        bush_id = getattr(
            store,
            "bush_id",
            0,
        )

    try:
        bush_id = int(
            bush_id or 0
        )

    except (
        TypeError,
        ValueError,
    ):
        bush_id = 0

    return (
        f"Кущ #{bush_id}"
        if bush_id
        else "—"
    )


async def query_all_stores(
    *,
    data: dict[str, Any],
    actor: DatabaseUser | None = None,
    user: DatabaseUser | None = None,
    **_: Any,
) -> list[Any]:
    """
    Всі доступні ТТ мережі.

    Compatibility wrapper для:
        invites.py
        bindings.py
        reports.py
        root_admin.py
    """

    from app.handlers.bush_admin import (
        query_stores,
    )
    from app.handlers.common import (
        get_database_user,
    )

    current_user = (
        actor
        or user
        or get_database_user(
            data
        )
    )

    return await query_stores(
        actor=current_user,
        data=data,
        bush_id=0,
    )


async def query_network_bushes(
    *,
    data: dict[str, Any],
    actor: DatabaseUser | None = None,
    user: DatabaseUser | None = None,
    **_: Any,
) -> list[Any]:
    """
    Всі доступні кущі.
    """

    from app.handlers.bush_admin import (
        query_bushes,
    )
    from app.handlers.common import (
        get_database_user,
    )

    current_user = (
        actor
        or user
        or get_database_user(
            data
        )
    )

    return await query_bushes(
        actor=current_user,
        data=data,
    )


async def query_network_users(
    *,
    data: dict[str, Any],
    actor: DatabaseUser | None = None,
    user: DatabaseUser | None = None,
    **_: Any,
) -> list[Any]:
    """
    Всі доступні користувачі мережі.
    """

    from app.handlers.bush_admin import (
        query_users,
    )
    from app.handlers.common import (
        get_database_user,
    )

    current_user = (
        actor
        or user
        or get_database_user(
            data
        )
    )

    return await query_users(
        actor=current_user,
        data=data,
        bush_id=0,
    )