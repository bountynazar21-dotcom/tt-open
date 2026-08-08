from __future__ import annotations

import inspect
import logging
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
)

from app.database.models.user import (
    User as DatabaseUser,
)

from app.handlers.bush_admin import (
    normalized_role,
    user_display_name,
)
from app.handlers.common import (
    get_database_user,
    safe_edit,
)
from app.handlers.director import (
    object_id,
    query_all_stores,
    query_network_bushes,
    query_network_users,
    store_code,
    store_name,
)
from app.handlers.opening import (
    call_method,
    first_attr,
    get_service,
    to_bool,
    to_int,
)
from app.handlers.root_admin import (
    load_user,
)
from app.handlers.store import (
    load_store,
    store_title,
)

from app.keyboards import (
    BindingAction,
    BindingCallback,
    MainMenuAction,
    MainMenuCallback,
    UserAction,
    UserCallback,
    inline_button,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="bindings",
)


# =========================================================
# CONSTANTS
# =========================================================


PAGE_SIZE = 10


MANAGER_ROLES = {
    "ROOT_ADMIN",
    "DIRECTOR",
    "BUSH_ADMIN",
}


# =========================================================
# FSM
# =========================================================


class BindingStates(
    StatesGroup
):
    """
    FSM перенесення прив'язок.
    """

    transfer_store = State()

    transfer_bush = State()


# =========================================================
# GENERIC HELPERS
# =========================================================


def filter_kwargs(
    method: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Залишає тільки kwargs,
    які підтримує callable.
    """

    try:
        signature = inspect.signature(
            method
        )

    except (
        TypeError,
        ValueError,
    ):
        return dict(
            payload
        )

    accepts_kwargs = any(
        parameter.kind
        == inspect.Parameter.VAR_KEYWORD
        for parameter
        in signature.parameters.values()
    )

    if accepts_kwargs:
        return dict(
            payload
        )

    return {
        key: value
        for key, value
        in payload.items()
        if key in signature.parameters
    }


def enum_value(
    value: Any,
) -> str:
    """
    Enum / str -> lowercase.
    """

    if value is None:
        return ""

    raw = first_attr(
        value,
        "value",
        "name",
        default=value,
    )

    return (
        str(raw)
        .strip()
        .lower()
    )


def normalize_scope(
    value: Any,
) -> str:
    """
    store / bush.
    """

    raw = enum_value(
        value
    )

    mapping = {
        "store":
            "store",

        "stores":
            "store",

        "tt":
            "store",

        "bush":
            "bush",

        "bushes":
            "bush",
    }

    return mapping.get(
        raw,
        raw,
    )


def operation_success(
    result: Any,
) -> bool:
    """
    Нормалізація success.
    """

    if isinstance(
        result,
        bool,
    ):
        return result

    if result is None:
        return False

    value = first_attr(
        result,
        "success",
        "changed",
        "created",
        "activated",
        "deactivated",
        "transferred",
        default=None,
    )

    if value is not None:
        return to_bool(
            value,
            default=False,
        )

    return True


def operation_message(
    result: Any,
) -> str | None:
    """
    Message from service.
    """

    value = first_attr(
        result,
        "message",
        "detail",
        "reason",
        "error",
        default=None,
    )

    if value:
        return str(
            value
        )

    return None


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
    Pagination.
    """

    if not items:
        return (
            [],
            0,
            1,
        )

    total_pages = (
        len(items)
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

    return (
        items[
            start:
            start + page_size
        ],
        normalized_page,
        total_pages,
    )


# =========================================================
# ACCESS
# =========================================================


def manager_role(
    user: DatabaseUser | None,
) -> str:
    """
    Поточна роль.
    """

    if user is None:
        return ""

    return normalized_role(
        user
    )


def can_manage_bindings(
    user: DatabaseUser | None,
) -> bool:
    """
    Хто може керувати bindings.
    """

    return (
        manager_role(
            user
        )
        in MANAGER_ROLES
    )


async def require_manager(
    callback: CallbackQuery,
    *,
    data: dict[str, Any],
) -> DatabaseUser | None:
    """
    Manager guard.
    """

    user = get_database_user(
        data
    )

    if can_manage_bindings(
        user
    ):
        return user

    await callback.answer(
        "Немає доступу до керування "
        "прив'язками.",
        show_alert=True,
    )

    return None


# =========================================================
# SERVICE
# =========================================================


def get_binding_service(
    data: dict[str, Any],
) -> Any | None:
    """
    BindingService.
    """

    return get_service(
        data,
        "bindings",
        "binding",
    )


async def flush_changes(
    data: dict[str, Any],
) -> None:
    """
    Flush transaction.
    """

    repositories = data.get(
        "repositories"
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
# BINDING HELPERS
# =========================================================


def binding_id(
    binding: Any,
) -> int:
    """
    Binding ID.
    """

    return to_int(
        first_attr(
            binding,
            "binding_id",
            "id",
            default=0,
        )
    )


def binding_scope(
    binding: Any,
) -> str:
    """
    store / bush.
    """

    return normalize_scope(
        first_attr(
            binding,
            "scope",
            "binding_scope",
            "type",
            default="",
        )
    )


def binding_target_id(
    binding: Any,
) -> int:
    """
    target id.
    """

    scope = binding_scope(
        binding
    )

    if scope == "store":
        return to_int(
            first_attr(
                binding,
                "store_id",
                "target_id",
                default=0,
            )
        )

    if scope == "bush":
        return to_int(
            first_attr(
                binding,
                "bush_id",
                "target_id",
                default=0,
            )
        )

    return to_int(
        first_attr(
            binding,
            "target_id",
            default=0,
        )
    )


def binding_is_primary(
    binding: Any,
) -> bool:
    """
    Primary binding.
    """

    return to_bool(
        first_attr(
            binding,
            "is_primary",
            "primary",
            default=False,
        )
    )


def binding_is_active(
    binding: Any,
) -> bool:
    """
    Active binding.
    """

    return to_bool(
        first_attr(
            binding,
            "is_active",
            "active",
            default=True,
        ),
        default=True,
    )


def extract_bindings(
    result: Any,
) -> list[Any]:
    """
    UserBindingsResult /
    list / wrapper -> bindings.
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

    combined: list[Any] = []

    for field_name in (
        "bindings",
        "items",
        "results",
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
            ),
        ):
            combined.extend(
                value
            )

    for field_name in (
        "store_bindings",
        "stores",
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
            ),
        ):
            combined.extend(
                value
            )

    for field_name in (
        "bush_bindings",
        "bushes",
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
            ),
        ):
            combined.extend(
                value
            )

    # deduplicate
    normalized: dict[
        tuple[str, int, int],
        Any,
    ] = {}

    for item in combined:
        key = (
            binding_scope(
                item
            ),
            binding_target_id(
                item
            ),
            binding_id(
                item
            ),
        )

        normalized[
            key
        ] = item

    return list(
        normalized.values()
    )


# =========================================================
# LOAD USER BINDINGS
# =========================================================


async def get_user_bindings(
    *,
    target_user_id: int,
    actor: DatabaseUser,
    data: dict[str, Any],
) -> list[Any]:
    """
    Отримує bindings користувача.
    """

    service = get_binding_service(
        data
    )

    payload = {
        "user_id":
            target_user_id,

        "target_user_id":
            target_user_id,

        "actor":
            actor,

        "current_user":
            actor,

        "actor_id":
            getattr(
                actor,
                "id",
                None,
            ),

        "include_inactive":
            True,

        "active_only":
            False,
    }

    if service is not None:
        for method_name in (
            "get_user_bindings",
            "list_user_bindings",
            "get_bindings",
            "list_bindings",
            "get_user_access",
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

            bindings = extract_bindings(
                result
            )

            if bindings:
                return bindings

            if result is not None:
                return []

    # -----------------------------------------------------
    # REPOSITORY FALLBACK
    # -----------------------------------------------------

    repositories = data.get(
        "repositories"
    )

    repository = (
        getattr(
            repositories,
            "bindings",
            None,
        )
        if repositories
        else None
    )

    if repository is None:
        return []

    for method_name in (
        "list_by_user",
        "get_by_user",
        "get_user_bindings",
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

        return extract_bindings(
            result
        )

    return []


# =========================================================
# TARGET LABEL
# =========================================================


async def binding_target_label(
    *,
    binding: Any,
    data: dict[str, Any],
) -> str:
    """
    Назва ТТ / куща.
    """

    direct = first_attr(
        binding,
        "target_name",
        "store_name",
        "bush_name",
        "name",
        default=None,
    )

    scope = binding_scope(
        binding
    )

    target_id = binding_target_id(
        binding
    )

    if direct:
        return str(
            direct
        )

    if scope == "store":
        store = await load_store(
            store_id=target_id,
            data=data,
        )

        return store_title(
            store,
            store_id=target_id,
        )

    if scope == "bush":
        bushes = await query_network_bushes(
            data=data
        )

        bush = next(
            (
                item
                for item in bushes
                if object_id(
                    item
                )
                == target_id
            ),
            None,
        )

        if bush is not None:
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
            f"Кущ #{target_id}"
        )

    return (
        f"#{target_id}"
    )


# =========================================================
# MAIN KEYBOARD
# =========================================================


async def bindings_keyboard(
    *,
    target_user_id: int,
    bindings: list[Any],
    data: dict[str, Any],
) -> InlineKeyboardMarkup:
    """
    Клавіатура bindings.
    """

    rows: list[
        list[Any]
    ] = []

    # -----------------------------------------------------
    # EXISTING BINDINGS
    # -----------------------------------------------------

    for binding in bindings:
        if not binding_is_active(
            binding
        ):
            continue

        scope = binding_scope(
            binding
        )

        target_id = binding_target_id(
            binding
        )

        identifier = binding_id(
            binding
        )

        label = await binding_target_label(
            binding=binding,
            data=data,
        )

        if scope == "store":
            icon = "🏪"

        elif scope == "bush":
            icon = "🌿"

        else:
            icon = "🔗"

        primary = (
            " ⭐"
            if binding_is_primary(
                binding
            )
            else ""
        )

        rows.append(
            [
                inline_button(
                    text=(
                        f"{icon} "
                        f"{label}"
                        f"{primary}"
                    ),
                    callback=BindingCallback(
                        action=(
                            BindingAction.VIEW
                        ),
                        user_id=(
                            target_user_id
                        ),
                        target_id=(
                            target_id
                        ),
                        binding_id=(
                            identifier
                        ),
                    ),
                )
            ]
        )

    # -----------------------------------------------------
    # ADD
    # -----------------------------------------------------

    rows.append(
        [
            inline_button(
                text="➕ Додати ТТ",
                callback=BindingCallback(
                    action=(
                        BindingAction.ADD_STORE
                    ),
                    user_id=(
                        target_user_id
                    ),
                    target_id=0,
                    binding_id=0,
                ),
            ),
            inline_button(
                text="➕ Додати кущ",
                callback=BindingCallback(
                    action=(
                        BindingAction.ADD_BUSH
                    ),
                    user_id=(
                        target_user_id
                    ),
                    target_id=0,
                    binding_id=0,
                ),
            ),
        ]
    )

    rows.append(
        [
            inline_button(
                text="🔙 До користувача",
                callback=UserCallback(
                    action=(
                        UserAction.VIEW
                    ),
                    user_id=(
                        target_user_id
                    ),
                    page=0,
                ),
            )
        ]
    )

    rows.append(
        [
            inline_button(
                text="🏠 Головне меню",
                callback=MainMenuCallback(
                    action=(
                        MainMenuAction.HOME
                    )
                ),
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# SHOW BINDINGS
# =========================================================


async def show_bindings(
    callback: CallbackQuery,
    *,
    target_user_id: int,
    actor: DatabaseUser,
    data: dict[str, Any],
) -> None:
    """
    Картка доступів користувача.
    """

    target_user = await load_user(
        user_id=target_user_id,
        data=data,
    )

    if target_user is None:
        await callback.answer(
            "Користувача не знайдено.",
            show_alert=True,
        )

        return

    try:
        bindings = await get_user_bindings(
            target_user_id=(
                target_user_id
            ),
            actor=actor,
            data=data,
        )

    except Exception:
        logger.exception(
            "Failed loading user bindings: %s",
            target_user_id,
        )

        await callback.answer(
            "Не вдалося отримати прив'язки.",
            show_alert=True,
        )

        return

    active_bindings = [
        binding
        for binding in bindings
        if binding_is_active(
            binding
        )
    ]

    store_count = sum(
        1
        for binding in active_bindings
        if binding_scope(
            binding
        )
        == "store"
    )

    bush_count = sum(
        1
        for binding in active_bindings
        if binding_scope(
            binding
        )
        == "bush"
    )

    await safe_edit(
        callback,
        text=(
            "🔐 <b>Прив'язки користувача</b>\n\n"
            f"👤 <b>{escape(user_display_name(target_user))}</b>\n"
            f"🎭 {escape(normalized_role(target_user) or '—')}\n\n"
            f"🏪 ТТ: <b>{store_count}</b>\n"
            f"🌿 Кущів: <b>{bush_count}</b>\n"
            f"🔗 Усього: <b>{len(active_bindings)}</b>"
        ),
        reply_markup=(
            await bindings_keyboard(
                target_user_id=(
                    target_user_id
                ),
                bindings=bindings,
                data=data,
            )
        ),
    )


# =========================================================
# USER -> BINDINGS
# =========================================================


@router.callback_query(
    UserCallback.filter(
        F.action
        == UserAction.BINDINGS
    )
)
async def user_bindings_callback(
    callback: CallbackQuery,
    callback_data: UserCallback,
    **data: Any,
) -> None:
    """
    Вхід із картки user.
    """

    actor = await require_manager(
        callback,
        data=data,
    )

    if actor is None:
        return

    await callback.answer()

    await show_bindings(
        callback,
        target_user_id=(
            callback_data.user_id
        ),
        actor=actor,
        data=data,
    )


# =========================================================
# VIEW BINDINGS
# =========================================================


@router.callback_query(
    BindingCallback.filter(
        F.action
        == BindingAction.VIEW
    )
)
async def binding_view_callback(
    callback: CallbackQuery,
    callback_data: BindingCallback,
    **data: Any,
) -> None:
    """
    VIEW:
      binding_id == 0 -> list
      binding_id > 0  -> binding card
    """

    actor = await require_manager(
        callback,
        data=data,
    )

    if actor is None:
        return

    await callback.answer()

    # -----------------------------------------------------
    # LIST
    # -----------------------------------------------------

    if callback_data.binding_id <= 0:
        await show_bindings(
            callback,
            target_user_id=(
                callback_data.user_id
            ),
            actor=actor,
            data=data,
        )

        return

    # -----------------------------------------------------
    # CARD
    # -----------------------------------------------------

    bindings = await get_user_bindings(
        target_user_id=(
            callback_data.user_id
        ),
        actor=actor,
        data=data,
    )

    binding = next(
        (
            item
            for item in bindings
            if binding_id(
                item
            )
            == callback_data.binding_id
        ),
        None,
    )

    if binding is None:
        await callback.answer(
            "Прив'язку не знайдено.",
            show_alert=True,
        )

        return

    scope = binding_scope(
        binding
    )

    label = await binding_target_label(
        binding=binding,
        data=data,
    )

    primary = binding_is_primary(
        binding
    )

    scope_title = (
        "Торгова точка"
        if scope == "store"
        else "Кущ"
        if scope == "bush"
        else scope
    )

    rows = []

    if not primary:
        rows.append(
            [
                inline_button(
                    text="⭐ Зробити основною",
                    callback=BindingCallback(
                        action=(
                            BindingAction.PRIMARY
                        ),
                        user_id=(
                            callback_data.user_id
                        ),
                        target_id=(
                            callback_data.target_id
                        ),
                        binding_id=(
                            callback_data.binding_id
                        ),
                    ),
                )
            ]
        )

    if scope == "store":
        rows.append(
            [
                inline_button(
                    text="🔄 Передати ТТ",
                    callback=BindingCallback(
                        action=(
                            BindingAction.TRANSFER_STORE
                        ),
                        user_id=(
                            callback_data.user_id
                        ),
                        target_id=(
                            callback_data.target_id
                        ),
                        binding_id=(
                            callback_data.binding_id
                        ),
                    ),
                )
            ]
        )

    elif scope == "bush":
        rows.append(
            [
                inline_button(
                    text="🔄 Передати кущ",
                    callback=BindingCallback(
                        action=(
                            BindingAction.TRANSFER_BUSH
                        ),
                        user_id=(
                            callback_data.user_id
                        ),
                        target_id=(
                            callback_data.target_id
                        ),
                        binding_id=(
                            callback_data.binding_id
                        ),
                    ),
                )
            ]
        )

    rows.append(
        [
            inline_button(
                text="🗑 Видалити прив'язку",
                callback=BindingCallback(
                    action=(
                        BindingAction.REMOVE
                    ),
                    user_id=(
                        callback_data.user_id
                    ),
                    target_id=(
                        callback_data.target_id
                    ),
                    binding_id=(
                        callback_data.binding_id
                    ),
                ),
            )
        ]
    )

    rows.append(
        [
            inline_button(
                text="🔙 До прив'язок",
                callback=BindingCallback(
                    action=(
                        BindingAction.VIEW
                    ),
                    user_id=(
                        callback_data.user_id
                    ),
                    target_id=0,
                    binding_id=0,
                ),
            )
        ]
    )

    await safe_edit(
        callback,
        text=(
            "🔗 <b>Прив'язка</b>\n\n"
            f"Тип: <b>{escape(scope_title)}</b>\n"
            f"Об'єкт: <b>{escape(label)}</b>\n"
            f"Основна: <b>{'так ⭐' if primary else 'ні'}</b>"
        ),
        reply_markup=(
            InlineKeyboardMarkup(
                inline_keyboard=rows
            )
        ),
    )


# =========================================================
# MUTATION CALL
# =========================================================


async def call_binding_operation(
    *,
    method_names: tuple[str, ...],
    payload: dict[str, Any],
    data: dict[str, Any],
) -> Any:
    """
    Виклик BindingService.
    """

    service = get_binding_service(
        data
    )

    if service is None:
        raise RuntimeError(
            "BindingService недоступний."
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
            kwargs = filter_kwargs(
                method,
                payload,
            )

            result = method(
                **kwargs
            )

            if inspect.isawaitable(
                result
            ):
                result = await result

            await flush_changes(
                data
            )

            return result

        except Exception as error:
            last_error = error

            logger.exception(
                "Binding operation failed: %s",
                method_name,
            )

            continue

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        "Потрібний метод BindingService "
        "не знайдено."
    )


# =========================================================
# ADD STORE
# =========================================================


@router.callback_query(
    BindingCallback.filter(
        F.action
        == BindingAction.ADD_STORE
    )
)
async def add_store_binding_callback(
    callback: CallbackQuery,
    callback_data: BindingCallback,
    **data: Any,
) -> None:
    """
    target_id=0 -> selector
    target_id>0 -> add
    """

    actor = await require_manager(
        callback,
        data=data,
    )

    if actor is None:
        return

    await callback.answer()

    # -----------------------------------------------------
    # SELECT STORE
    # -----------------------------------------------------

    if callback_data.target_id <= 0:
        stores = await query_all_stores(
            data=data
        )

        if not stores:
            await callback.answer(
                "Доступних ТТ немає.",
                show_alert=True,
            )

            return

        rows = []

        for store in stores[
            :50
        ]:
            store_id = object_id(
                store
            )

            if store_id <= 0:
                continue

            label = store_code(
                store
            )

            name = store_name(
                store
            )

            if name:
                label += (
                    f" · {name}"
                )

            rows.append(
                [
                    inline_button(
                        text=(
                            "🏪 "
                            + label[
                                :50
                            ]
                        ),
                        callback=BindingCallback(
                            action=(
                                BindingAction.ADD_STORE
                            ),
                            user_id=(
                                callback_data.user_id
                            ),
                            target_id=(
                                store_id
                            ),
                            binding_id=0,
                        ),
                    )
                ]
            )

        rows.append(
            [
                inline_button(
                    text="🔙 До прив'язок",
                    callback=BindingCallback(
                        action=(
                            BindingAction.VIEW
                        ),
                        user_id=(
                            callback_data.user_id
                        ),
                        target_id=0,
                        binding_id=0,
                    ),
                )
            ]
        )

        await safe_edit(
            callback,
            text=(
                "🏪 <b>Додати ТТ</b>\n\n"
                "Оберіть торгову точку:"
            ),
            reply_markup=(
                InlineKeyboardMarkup(
                    inline_keyboard=rows
                )
            ),
        )

        return

    # -----------------------------------------------------
    # CREATE BINDING
    # -----------------------------------------------------

    payload = {
        "user_id":
            callback_data.user_id,

        "target_user_id":
            callback_data.user_id,

        "store_id":
            callback_data.target_id,

        "target_id":
            callback_data.target_id,

        "scope":
            "store",

        "actor":
            actor,

        "current_user":
            actor,

        "actor_id":
            getattr(
                actor,
                "id",
                None,
            ),
    }

    try:
        result = await call_binding_operation(
            method_names=(
                "add_store_binding",
                "bind_store",
                "create_store_binding",
                "add_store",
                "create_binding",
                "add_binding",
            ),
            payload=payload,
            data=data,
        )

    except Exception:
        await callback.answer(
            "Не вдалося додати ТТ.",
            show_alert=True,
        )

        return

    if not operation_success(
        result
    ):
        await callback.answer(
            operation_message(
                result
            )
            or "Не вдалося додати ТТ.",
            show_alert=True,
        )

        return

    await callback.answer(
        "ТТ додано ✅"
    )

    await show_bindings(
        callback,
        target_user_id=(
            callback_data.user_id
        ),
        actor=actor,
        data=data,
    )


# =========================================================
# ADD BUSH
# =========================================================


@router.callback_query(
    BindingCallback.filter(
        F.action
        == BindingAction.ADD_BUSH
    )
)
async def add_bush_binding_callback(
    callback: CallbackQuery,
    callback_data: BindingCallback,
    **data: Any,
) -> None:
    """
    target_id=0 -> selector
    target_id>0 -> add
    """

    actor = await require_manager(
        callback,
        data=data,
    )

    if actor is None:
        return

    await callback.answer()

    # -----------------------------------------------------
    # SELECT BUSH
    # -----------------------------------------------------

    if callback_data.target_id <= 0:
        bushes = await query_network_bushes(
            data=data
        )

        rows = []

        for bush in bushes[
            :50
        ]:
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

            rows.append(
                [
                    inline_button(
                        text=(
                            "🌿 "
                            + str(name)[
                                :50
                            ]
                        ),
                        callback=BindingCallback(
                            action=(
                                BindingAction.ADD_BUSH
                            ),
                            user_id=(
                                callback_data.user_id
                            ),
                            target_id=(
                                bush_id
                            ),
                            binding_id=0,
                        ),
                    )
                ]
            )

        rows.append(
            [
                inline_button(
                    text="🔙 До прив'язок",
                    callback=BindingCallback(
                        action=(
                            BindingAction.VIEW
                        ),
                        user_id=(
                            callback_data.user_id
                        ),
                        target_id=0,
                        binding_id=0,
                    ),
                )
            ]
        )

        await safe_edit(
            callback,
            text=(
                "🌿 <b>Додати кущ</b>\n\n"
                "Оберіть кущ:"
            ),
            reply_markup=(
                InlineKeyboardMarkup(
                    inline_keyboard=rows
                )
            ),
        )

        return

    # -----------------------------------------------------
    # CREATE BINDING
    # -----------------------------------------------------

    payload = {
        "user_id":
            callback_data.user_id,

        "target_user_id":
            callback_data.user_id,

        "bush_id":
            callback_data.target_id,

        "target_id":
            callback_data.target_id,

        "scope":
            "bush",

        "actor":
            actor,

        "current_user":
            actor,

        "actor_id":
            getattr(
                actor,
                "id",
                None,
            ),
    }

    try:
        result = await call_binding_operation(
            method_names=(
                "add_bush_binding",
                "bind_bush",
                "create_bush_binding",
                "add_bush",
                "create_binding",
                "add_binding",
            ),
            payload=payload,
            data=data,
        )

    except Exception:
        await callback.answer(
            "Не вдалося додати кущ.",
            show_alert=True,
        )

        return

    if not operation_success(
        result
    ):
        await callback.answer(
            operation_message(
                result
            )
            or "Не вдалося додати кущ.",
            show_alert=True,
        )

        return

    await callback.answer(
        "Кущ додано ✅"
    )

    await show_bindings(
        callback,
        target_user_id=(
            callback_data.user_id
        ),
        actor=actor,
        data=data,
    )


# =========================================================
# PRIMARY
# =========================================================


@router.callback_query(
    BindingCallback.filter(
        F.action
        == BindingAction.PRIMARY
    )
)
async def set_primary_binding_callback(
    callback: CallbackQuery,
    callback_data: BindingCallback,
    **data: Any,
) -> None:
    """
    Робить binding основним.
    """

    actor = await require_manager(
        callback,
        data=data,
    )

    if actor is None:
        return

    payload = {
        "binding_id":
            callback_data.binding_id,

        "user_id":
            callback_data.user_id,

        "target_user_id":
            callback_data.user_id,

        "target_id":
            callback_data.target_id,

        "actor":
            actor,

        "current_user":
            actor,

        "actor_id":
            getattr(
                actor,
                "id",
                None,
            ),
    }

    try:
        result = await call_binding_operation(
            method_names=(
                "set_primary",
                "make_primary",
                "set_primary_binding",
                "mark_primary",
            ),
            payload=payload,
            data=data,
        )

    except Exception:
        await callback.answer(
            "Не вдалося змінити "
            "основну прив'язку.",
            show_alert=True,
        )

        return

    if not operation_success(
        result
    ):
        await callback.answer(
            operation_message(
                result
            )
            or "Операція не виконана.",
            show_alert=True,
        )

        return

    await callback.answer(
        "Основну прив'язку змінено ⭐"
    )

    await show_bindings(
        callback,
        target_user_id=(
            callback_data.user_id
        ),
        actor=actor,
        data=data,
    )


# =========================================================
# REMOVE
# =========================================================


@router.callback_query(
    BindingCallback.filter(
        F.action
        == BindingAction.REMOVE
    )
)
async def remove_binding_callback(
    callback: CallbackQuery,
    callback_data: BindingCallback,
    **data: Any,
) -> None:
    """
    Видаляє/deactivates binding.
    """

    actor = await require_manager(
        callback,
        data=data,
    )

    if actor is None:
        return

    payload = {
        "binding_id":
            callback_data.binding_id,

        "user_id":
            callback_data.user_id,

        "target_user_id":
            callback_data.user_id,

        "target_id":
            callback_data.target_id,

        "actor":
            actor,

        "current_user":
            actor,

        "actor_id":
            getattr(
                actor,
                "id",
                None,
            ),
    }

    try:
        result = await call_binding_operation(
            method_names=(
                "deactivate_binding",
                "remove_binding",
                "delete_binding",
                "unbind",
                "remove",
            ),
            payload=payload,
            data=data,
        )

    except Exception:
        await callback.answer(
            "Не вдалося видалити "
            "прив'язку.",
            show_alert=True,
        )

        return

    if not operation_success(
        result
    ):
        await callback.answer(
            operation_message(
                result
            )
            or "Операція не виконана.",
            show_alert=True,
        )

        return

    await callback.answer(
        "Прив'язку видалено ✅"
    )

    await show_bindings(
        callback,
        target_user_id=(
            callback_data.user_id
        ),
        actor=actor,
        data=data,
    )


# =========================================================
# TRANSFER USER SELECTOR
# =========================================================


async def show_transfer_users(
    callback: CallbackQuery,
    *,
    source_user_id: int,
    target_id: int,
    binding_id_value: int,
    transfer_type: str,
    data: dict[str, Any],
) -> None:
    """
    Обираємо нового користувача.
    """

    users = await query_network_users(
        data=data
    )

    users = [
        user
        for user in users
        if object_id(
            user
        )
        != source_user_id
    ]

    rows = []

    action = (
        BindingAction.TRANSFER_STORE
        if transfer_type == "store"
        else BindingAction.TRANSFER_BUSH
    )

    for user in users[
        :50
    ]:
        user_id = object_id(
            user
        )

        if user_id <= 0:
            continue

        name = user_display_name(
            user
        )

        role = normalized_role(
            user
        )

        rows.append(
            [
                inline_button(
                    text=(
                        f"👤 {name[:35]} "
                        f"· {role[:12]}"
                    ),
                    callback=BindingCallback(
                        action=action,

                        # Тут user_id вже
                        # destination user.
                        user_id=user_id,

                        target_id=target_id,

                        binding_id=(
                            binding_id_value
                        ),
                    ),
                )
            ]
        )

    rows.append(
        [
            inline_button(
                text="❌ Скасувати",
                callback=BindingCallback(
                    action=BindingAction.VIEW,
                    user_id=source_user_id,
                    target_id=0,
                    binding_id=0,
                ),
            )
        ]
    )

    await safe_edit(
        callback,
        text=(
            "🔄 <b>Передача прив'язки</b>\n\n"
            "Оберіть користувача, "
            "якому потрібно передати "
            + (
                "торгову точку:"
                if transfer_type == "store"
                else "кущ:"
            )
        ),
        reply_markup=(
            InlineKeyboardMarkup(
                inline_keyboard=rows
            )
        ),
    )


# =========================================================
# TRANSFER STORE
# =========================================================


@router.callback_query(
    BindingCallback.filter(
        F.action
        == BindingAction.TRANSFER_STORE
    )
)
async def transfer_store_callback(
    callback: CallbackQuery,
    callback_data: BindingCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Перший клік:
        user_id = source user

    Після вибору destination:
        user_id = destination user
        source user зберігаємо у FSM.
    """

    actor = await require_manager(
        callback,
        data=data,
    )

    if actor is None:
        return

    state_data = await state.get_data()

    transfer_active = (
        state_data.get(
            "binding_transfer_type"
        )
        == "store"
    )

    # -----------------------------------------------------
    # START TRANSFER
    # -----------------------------------------------------

    if not transfer_active:
        await state.set_state(
            BindingStates.transfer_store
        )

        await state.update_data(
            binding_transfer_type="store",

            binding_source_user_id=(
                callback_data.user_id
            ),

            binding_target_id=(
                callback_data.target_id
            ),

            binding_id=(
                callback_data.binding_id
            ),
        )

        await callback.answer()

        await show_transfer_users(
            callback,
            source_user_id=(
                callback_data.user_id
            ),
            target_id=(
                callback_data.target_id
            ),
            binding_id_value=(
                callback_data.binding_id
            ),
            transfer_type="store",
            data=data,
        )

        return

    # -----------------------------------------------------
    # EXECUTE TRANSFER
    # -----------------------------------------------------

    source_user_id = to_int(
        state_data.get(
            "binding_source_user_id"
        )
    )

    store_id = to_int(
        state_data.get(
            "binding_target_id"
        )
    )

    binding_id_value = to_int(
        state_data.get(
            "binding_id"
        )
    )

    destination_user_id = (
        callback_data.user_id
    )

    payload = {
        "source_user_id":
            source_user_id,

        "from_user_id":
            source_user_id,

        "destination_user_id":
            destination_user_id,

        "target_user_id":
            destination_user_id,

        "to_user_id":
            destination_user_id,

        "store_id":
            store_id,

        "target_id":
            store_id,

        "binding_id":
            binding_id_value,

        "actor":
            actor,

        "current_user":
            actor,
    }

    try:
        result = await call_binding_operation(
            method_names=(
                "transfer_store",
                "transfer_store_binding",
                "move_store_binding",
                "reassign_store",
            ),
            payload=payload,
            data=data,
        )

    except Exception:
        logger.exception(
            "Store binding transfer failed"
        )

        await callback.answer(
            "Не вдалося передати ТТ.",
            show_alert=True,
        )

        return

    if not operation_success(
        result
    ):
        await callback.answer(
            operation_message(
                result
            )
            or "Передачу не виконано.",
            show_alert=True,
        )

        return

    await state.clear()

    await callback.answer(
        "ТТ передано ✅"
    )

    await show_bindings(
        callback,
        target_user_id=(
            destination_user_id
        ),
        actor=actor,
        data=data,
    )


# =========================================================
# TRANSFER BUSH
# =========================================================


@router.callback_query(
    BindingCallback.filter(
        F.action
        == BindingAction.TRANSFER_BUSH
    )
)
async def transfer_bush_callback(
    callback: CallbackQuery,
    callback_data: BindingCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Передача bush binding.
    """

    actor = await require_manager(
        callback,
        data=data,
    )

    if actor is None:
        return

    state_data = await state.get_data()

    transfer_active = (
        state_data.get(
            "binding_transfer_type"
        )
        == "bush"
    )

    # -----------------------------------------------------
    # START
    # -----------------------------------------------------

    if not transfer_active:
        await state.set_state(
            BindingStates.transfer_bush
        )

        await state.update_data(
            binding_transfer_type="bush",

            binding_source_user_id=(
                callback_data.user_id
            ),

            binding_target_id=(
                callback_data.target_id
            ),

            binding_id=(
                callback_data.binding_id
            ),
        )

        await callback.answer()

        await show_transfer_users(
            callback,
            source_user_id=(
                callback_data.user_id
            ),
            target_id=(
                callback_data.target_id
            ),
            binding_id_value=(
                callback_data.binding_id
            ),
            transfer_type="bush",
            data=data,
        )

        return

    # -----------------------------------------------------
    # EXECUTE
    # -----------------------------------------------------

    source_user_id = to_int(
        state_data.get(
            "binding_source_user_id"
        )
    )

    bush_id = to_int(
        state_data.get(
            "binding_target_id"
        )
    )

    binding_id_value = to_int(
        state_data.get(
            "binding_id"
        )
    )

    destination_user_id = (
        callback_data.user_id
    )

    payload = {
        "source_user_id":
            source_user_id,

        "from_user_id":
            source_user_id,

        "destination_user_id":
            destination_user_id,

        "target_user_id":
            destination_user_id,

        "to_user_id":
            destination_user_id,

        "bush_id":
            bush_id,

        "target_id":
            bush_id,

        "binding_id":
            binding_id_value,

        "actor":
            actor,

        "current_user":
            actor,
    }

    try:
        result = await call_binding_operation(
            method_names=(
                "transfer_bush",
                "transfer_bush_binding",
                "move_bush_binding",
                "reassign_bush",
            ),
            payload=payload,
            data=data,
        )

    except Exception:
        logger.exception(
            "Bush binding transfer failed"
        )

        await callback.answer(
            "Не вдалося передати кущ.",
            show_alert=True,
        )

        return

    if not operation_success(
        result
    ):
        await callback.answer(
            operation_message(
                result
            )
            or "Передачу не виконано.",
            show_alert=True,
        )

        return

    await state.clear()

    await callback.answer(
        "Кущ передано ✅"
    )

    await show_bindings(
        callback,
        target_user_id=(
            destination_user_id
        ),
        actor=actor,
        data=data,
    )


# =========================================================
# BACK
# =========================================================


@router.callback_query(
    BindingCallback.filter(
        F.action
        == BindingAction.BACK
    )
)
async def bindings_back_callback(
    callback: CallbackQuery,
    callback_data: BindingCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Back.
    """

    actor = await require_manager(
        callback,
        data=data,
    )

    if actor is None:
        return

    await callback.answer()

    await state.clear()

    if callback_data.user_id > 0:
        await show_bindings(
            callback,
            target_user_id=(
                callback_data.user_id
            ),
            actor=actor,
            data=data,
        )

        return

    await safe_edit(
        callback,
        text="🏠 <b>Головне меню</b>",
        reply_markup=(
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        inline_button(
                            text="🏠 Головне меню",
                            callback=MainMenuCallback(
                                action=(
                                    MainMenuAction.HOME
                                )
                            ),
                        )
                    ]
                ]
            )
        ),
    )


# =========================================================
# IMPORTANT
# =========================================================
#
# Тут НЕ додаємо загальний:
#
# @router.callback_query(
#     BindingCallback.filter()
# )
#
# Поки не завершимо всі routers.
#
# Причина:
# BindingCallback може також
# використовуватися user/admin
# клавіатурами, і catch-all може
# перехопити callback до того,
# як його обробить потрібний router.
#
# Фінальний fallback додамо після
# інтеграційного тесту.
# =========================================================


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "router",

    "PAGE_SIZE",
    "MANAGER_ROLES",

    "BindingStates",

    "filter_kwargs",
    "enum_value",
    "normalize_scope",

    "operation_success",
    "operation_message",

    "paginate",

    "manager_role",
    "can_manage_bindings",
    "require_manager",

    "get_binding_service",
    "flush_changes",

    "binding_id",
    "binding_scope",
    "binding_target_id",
    "binding_is_primary",
    "binding_is_active",

    "extract_bindings",

    "get_user_bindings",

    "binding_target_label",

    "bindings_keyboard",
    "show_bindings",

    "call_binding_operation",

    "show_transfer_users",
]
# =========================================================
# ROOT ADMIN COMPATIBILITY HELPERS
# =========================================================


async def load_user(
    user_id: int = 0,
    data: dict | None = None,
    **kwargs,
):
    """
    Завантажує користувача за internal user ID.

    Compatibility helper для bindings.py
    та інших handlers.
    """

    from app.handlers.bush_admin import (
        load_user as _load_user,
    )

    resolved_id = (
        user_id
        or kwargs.get("target_user_id")
        or kwargs.get("id")
        or kwargs.get("object_id")
        or 0
    )

    try:
        resolved_id = int(resolved_id)

    except (
        TypeError,
        ValueError,
    ):
        return None

    if resolved_id <= 0:
        return None

    context = {}

    if isinstance(data, dict):
        context.update(data)

    # Якщо middleware-параметри прийшли
    # безпосередньо через **kwargs.
    for key, value in kwargs.items():
        if key not in {
            "target_user_id",
            "id",
            "object_id",
        }:
            context.setdefault(
                key,
                value,
            )

    return await _load_user(
        user_id=resolved_id,
        data=context,
    )