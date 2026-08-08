from __future__ import annotations

import inspect
import logging
from enum import Enum
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.database.models.user import (
    User as DatabaseUser,
)
from app.handlers.common import (
    get_database_user,
    safe_edit,
)


logger = logging.getLogger(__name__)


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

BUSH_ADMIN_ROLES = {
    "BUSH_ADMIN",
    "DIRECTOR",
    "ROOT_ADMIN",
}


ROLE_LABELS = {
    "ROOT_ADMIN": "Root Admin",
    "DIRECTOR": "Директор",
    "BUSH_ADMIN": "Адмін куща",
    "LION": "Лев",
    "STORE_USER": "Працівник ТТ",
}


# =========================================================
# GENERIC HELPERS
# =========================================================


def first_attr(
    value: Any,
    *names: str,
    default: Any = None,
) -> Any:
    """
    Повертає перший знайдений attribute/key.
    """

    if value is None:
        return default

    if isinstance(value, dict):
        for name in names:
            if name in value:
                result = value[name]

                if result is not None:
                    return result

        return default

    for name in names:
        try:
            result = getattr(
                value,
                name,
                None,
            )
        except Exception:
            continue

        if result is not None:
            return result

    return default


def to_int(
    value: Any,
    default: int = 0,
) -> int:
    """
    Безпечне int().
    """

    if value is None:
        return default

    try:
        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def to_bool(
    value: Any,
    default: bool = False,
) -> bool:
    """
    Безпечна нормалізація bool.
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value != 0

    if isinstance(value, str):
        normalized = (
            value
            .strip()
            .lower()
        )

        if normalized in {
            "1",
            "true",
            "yes",
            "on",
            "active",
            "enabled",
            "approved",
        }:
            return True

        if normalized in {
            "0",
            "false",
            "no",
            "off",
            "inactive",
            "disabled",
            "blocked",
            "rejected",
        }:
            return False

    return bool(value)


def filtered_kwargs(
    target: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Залишає тільки kwargs,
    які підтримує callable/class.
    """

    try:
        signature = inspect.signature(
            target
        )

    except (
        TypeError,
        ValueError,
    ):
        return dict(payload)

    accepts_kwargs = any(
        parameter.kind
        == inspect.Parameter.VAR_KEYWORD
        for parameter
        in signature.parameters.values()
    )

    if accepts_kwargs:
        return dict(payload)

    return {
        key: value
        for key, value in payload.items()
        if key in signature.parameters
    }


# Compatibility alias.
filter_kwargs = filtered_kwargs


def create_model(
    target: Any,
    **payload: Any,
) -> Any:
    """
    Створює dataclass / Pydantic model /
    звичайний class, відфільтровуючи kwargs.

    Цей helper використовують інші handlers.
    """

    if target is None:
        return payload

    if isinstance(target, dict):
        result = dict(target)
        result.update(payload)
        return result

    # Pydantic v2
    model_fields = getattr(
        target,
        "model_fields",
        None,
    )

    if isinstance(model_fields, dict):
        filtered = {
            key: value
            for key, value in payload.items()
            if key in model_fields
        }

        try:
            return target(
                **filtered
            )
        except Exception:
            pass

    # Dataclass / normal class.
    filtered = filtered_kwargs(
        target,
        payload,
    )

    try:
        return target(
            **filtered
        )

    except TypeError:
        # Якщо class приймає всі дані,
        # але inspect не зміг це визначити.
        return target(
            **payload
        )


def build_keyboard(
    factory: Any,
    **payload: Any,
) -> Any:
    """
    Викликає keyboard factory
    тільки з підтримуваними kwargs.
    """

    if factory is None:
        return None

    if not callable(factory):
        return factory

    kwargs = filtered_kwargs(
        factory,
        payload,
    )

    try:
        return factory(
            **kwargs
        )

    except TypeError:
        # Друга спроба — без kwargs.
        return factory()


def unwrap_collection(
    result: Any,
) -> list[Any]:
    """
    Нормалізує repository/service result
    у звичайний list.
    """

    if result is None:
        return []

    if isinstance(
        result,
        list,
    ):
        return result

    if isinstance(
        result,
        (
            tuple,
            set,
            frozenset,
        ),
    ):
        return list(result)

    if isinstance(result, dict):
        for key in (
            "items",
            "results",
            "records",
            "data",
            "users",
            "stores",
            "bushes",
            "bindings",
            "rows",
        ):
            value = result.get(key)

            if isinstance(
                value,
                (
                    list,
                    tuple,
                    set,
                    frozenset,
                ),
            ):
                return list(value)

        return []

    for attr_name in (
        "items",
        "results",
        "records",
        "data",
        "users",
        "stores",
        "bushes",
        "bindings",
        "rows",
    ):
        value = getattr(
            result,
            attr_name,
            None,
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
            return list(value)

    # SQLAlchemy ScalarResult etc.
    all_method = getattr(
        result,
        "all",
        None,
    )

    if callable(all_method):
        try:
            value = all_method()

            if isinstance(
                value,
                (
                    list,
                    tuple,
                ),
            ):
                return list(value)

        except Exception:
            pass

    return []


def enum_member(
    enum_class: Any,
    *names: str,
) -> Any:
    """
    Повертає enum member за name/value.

    Використовується іншими handlers,
    щоб не залежати від точного написання enum.
    """

    if enum_class is None:
        return None

    normalized_names = {
        str(name)
        .strip()
        .lower()
        for name in names
        if name is not None
    }

    for name in names:
        member = getattr(
            enum_class,
            str(name),
            None,
        )

        if member is not None:
            return member

    try:
        members = list(
            enum_class
        )
    except Exception:
        return None

    for member in members:
        member_name = (
            str(
                getattr(
                    member,
                    "name",
                    "",
                )
            )
            .strip()
            .lower()
        )

        member_value = (
            str(
                getattr(
                    member,
                    "value",
                    "",
                )
            )
            .strip()
            .lower()
        )

        if (
            member_name
            in normalized_names
            or member_value
            in normalized_names
        ):
            return member

    # Compatibility fallback.
    if members:
        return members[0]

    return None


def object_id(
    value: Any,
) -> int:
    """
    ID будь-якої моделі.
    """

    return to_int(
        first_attr(
            value,
            "id",
            "object_id",
            "user_id",
            "store_id",
            "bush_id",
            "cluster_id",
            default=0,
        )
    )


# =========================================================
# USER HELPERS
# =========================================================


def normalized_role(
    user_or_role: Any,
) -> str:
    """
    User / Enum / str -> ROLE_NAME.
    """

    if user_or_role is None:
        return ""

    role = first_attr(
        user_or_role,
        "role",
        "user_role",
        default=user_or_role,
    )

    if role is None:
        return ""

    if isinstance(role, Enum):
        raw = (
            getattr(
                role,
                "value",
                None,
            )
            or getattr(
                role,
                "name",
                None,
            )
        )
    else:
        raw = first_attr(
            role,
            "value",
            "name",
            default=role,
        )

    if raw is None:
        return ""

    value = (
        str(raw)
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    aliases = {
        "ROOT":
            "ROOT_ADMIN",

        "ADMIN":
            "ROOT_ADMIN",

        "ROOTADMIN":
            "ROOT_ADMIN",

        "BUSHADMIN":
            "BUSH_ADMIN",

        "BUSH_MANAGER":
            "BUSH_ADMIN",

        "LION_ADMIN":
            "LION",

        "STORE":
            "STORE_USER",

        "STOREUSER":
            "STORE_USER",

        "SELLER":
            "STORE_USER",

        "EMPLOYEE":
            "STORE_USER",
    }

    return aliases.get(
        value,
        value,
    )


def role_label(
    user_or_role: Any,
) -> str:
    """
    Людська назва ролі.
    """

    role = normalized_role(
        user_or_role
    )

    return ROLE_LABELS.get(
        role,
        role or "Без ролі",
    )


def user_display_name(
    user: Any,
) -> str:
    """
    Зручне ім'я користувача.
    """

    if user is None:
        return "Користувач"

    direct = first_attr(
        user,
        "full_name",
        "display_name",
        "name",
        default=None,
    )

    if direct:
        return str(direct)

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

    full_name = " ".join(
        str(item).strip()
        for item in (
            first_name,
            last_name,
        )
        if item
    ).strip()

    if full_name:
        return full_name

    username = first_attr(
        user,
        "username",
        default=None,
    )

    if username:
        username = (
            str(username)
            .strip()
            .removeprefix("@")
        )

        return (
            f"@{username}"
            if username
            else "Користувач"
        )

    telegram_id = to_int(
        first_attr(
            user,
            "telegram_id",
            "tg_id",
            default=0,
        )
    )

    if telegram_id:
        return (
            f"Telegram {telegram_id}"
        )

    identifier = object_id(
        user
    )

    if identifier:
        return (
            f"Користувач #{identifier}"
        )

    return "Користувач"


def user_is_active(
    user: Any,
) -> bool:
    """
    Active user status.
    """

    if user is None:
        return False

    explicit = first_attr(
        user,
        "is_active",
        "active",
        "enabled",
        default=None,
    )

    if explicit is not None:
        return to_bool(
            explicit,
            default=True,
        )

    status = first_attr(
        user,
        "status",
        default=None,
    )

    if status is None:
        return True

    status_value = first_attr(
        status,
        "value",
        "name",
        default=status,
    )

    normalized = (
        str(status_value)
        .strip()
        .lower()
    )

    return normalized not in {
        "inactive",
        "disabled",
        "blocked",
        "rejected",
        "deleted",
        "deactivated",
    }


def can_use_bush_admin_panel(
    user: Any,
) -> bool:
    """
    Bush Admin / Director / Root.
    """

    return (
        normalized_role(user)
        in BUSH_ADMIN_ROLES
    )


# =========================================================
# ACCESS HELPERS
# =========================================================


def has_network_access(
    user: Any,
    data: dict[str, Any],
) -> bool:
    """
    Director / Root або network access
    із middleware.
    """

    role = normalized_role(
        user
    )

    if role in {
        "ROOT_ADMIN",
        "DIRECTOR",
    }:
        return True

    direct = data.get(
        "has_network_access"
    )

    if isinstance(
        direct,
        bool,
    ):
        return direct

    context = (
        data.get(
            "access_context"
        )
        or data.get(
            "access_scope"
        )
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
    Bush IDs із AccessMiddleware.
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

    context = (
        data.get(
            "access_context"
        )
        or data.get(
            "access_scope"
        )
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


def accessible_store_ids(
    data: dict[str, Any],
) -> set[int]:
    """
    Store IDs із AccessMiddleware.
    """

    direct = data.get(
        "accessible_store_ids"
    )

    if direct:
        return {
            to_int(item)
            for item in direct
            if to_int(item) > 0
        }

    context = (
        data.get(
            "access_context"
        )
        or data.get(
            "access_scope"
        )
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
        to_int(item)
        for item in values
        if to_int(item) > 0
    }


# =========================================================
# SERVICES / REPOSITORIES
# =========================================================


def get_service(
    data: dict[str, Any],
    *names: str,
) -> Any | None:
    """
    Отримує service із DI data.
    """

    services = data.get(
        "services"
    )

    for name in names:
        direct = data.get(
            f"{name}_service"
        )

        if direct is not None:
            return direct

        direct = data.get(name)

        if (
            direct is not None
            and not isinstance(
                direct,
                (
                    str,
                    int,
                    float,
                    bool,
                    list,
                    tuple,
                    dict,
                    set,
                ),
            )
        ):
            return direct

        if services is None:
            continue

        if isinstance(
            services,
            dict,
        ):
            value = (
                services.get(name)
                or services.get(
                    f"{name}_service"
                )
            )

        else:
            value = (
                getattr(
                    services,
                    name,
                    None,
                )
                or getattr(
                    services,
                    f"{name}_service",
                    None,
                )
            )

        if value is not None:
            return value

    return None


def get_repository(
    data: dict[str, Any],
    *names: str,
) -> Any | None:
    """
    Repository із DI container.
    """

    repositories = data.get(
        "repositories"
    )

    if repositories is None:
        return None

    for name in names:
        if isinstance(
            repositories,
            dict,
        ):
            result = (
                repositories.get(name)
                or repositories.get(
                    f"{name}_repository"
                )
            )

        else:
            result = (
                getattr(
                    repositories,
                    name,
                    None,
                )
                or getattr(
                    repositories,
                    f"{name}_repository",
                    None,
                )
            )

        if result is not None:
            return result

    return None


async def call_method(
    method: Any,
    payload: dict[str, Any],
) -> Any:
    """
    Sync / async method.
    """

    kwargs = filtered_kwargs(
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

    return result


async def query_collection(
    *,
    service: Any | None,
    repository: Any | None,
    method_names: tuple[str, ...],
    payload: dict[str, Any],
) -> list[Any]:
    """
    Generic list query.
    """

    for source in (
        service,
        repository,
    ):
        if source is None:
            continue

        for method_name in method_names:
            method = getattr(
                source,
                method_name,
                None,
            )

            if not callable(method):
                continue

            try:
                result = await call_method(
                    method,
                    payload,
                )

            except Exception:
                logger.debug(
                    "Collection method failed: %s",
                    method_name,
                    exc_info=True,
                )
                continue

            return unwrap_collection(
                result
            )

    return []


# =========================================================
# BUSH QUERY
# =========================================================


async def query_bushes(
    *,
    actor: DatabaseUser | None,
    data: dict[str, Any],
) -> list[Any]:
    """
    Доступні кущі.
    """

    service = get_service(
        data,
        "bush",
        "bushes",
    )

    repository = get_repository(
        data,
        "bush",
        "bushes",
    )

    payload = {
        "actor":
            actor,

        "user":
            actor,

        "active_only":
            False,

        "include_inactive":
            True,
    }

    bushes = await query_collection(
        service=service,
        repository=repository,
        method_names=(
            "list_bushes",
            "get_bushes",
            "list_all",
            "get_all",
            "list",
            "all",
        ),
        payload=payload,
    )

    if (
        actor is None
        or has_network_access(
            actor,
            data,
        )
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
        if object_id(bush)
        in allowed
    ]


# =========================================================
# STORE QUERY
# =========================================================


async def query_stores(
    *,
    actor: DatabaseUser | None,
    data: dict[str, Any],
    bush_id: int = 0,
) -> list[Any]:
    """
    Доступні ТТ.
    """

    service = get_service(
        data,
        "store",
        "stores",
    )

    repository = get_repository(
        data,
        "store",
        "stores",
    )

    payload = {
        "actor":
            actor,

        "user":
            actor,

        "bush_id":
            bush_id
            or None,

        "active_only":
            False,

        "include_inactive":
            True,
    }

    stores = await query_collection(
        service=service,
        repository=repository,
        method_names=(
            "list_stores",
            "get_stores",
            "list_by_bush",
            "get_by_bush",
            "list_all",
            "get_all",
            "list",
            "all",
        ),
        payload=payload,
    )

    if bush_id > 0:
        stores = [
            store
            for store in stores
            if to_int(
                first_attr(
                    store,
                    "bush_id",
                    default=0,
                )
            )
            == bush_id
        ]

    if (
        actor is None
        or has_network_access(
            actor,
            data,
        )
    ):
        return stores

    allowed_stores = accessible_store_ids(
        data
    )

    allowed_bushes = accessible_bush_ids(
        data
    )

    return [
        store
        for store in stores
        if (
            object_id(store)
            in allowed_stores
            or to_int(
                first_attr(
                    store,
                    "bush_id",
                    default=0,
                )
            )
            in allowed_bushes
        )
    ]


# =========================================================
# USER QUERY
# =========================================================


async def query_users(
    *,
    actor: DatabaseUser | None,
    data: dict[str, Any],
    bush_id: int = 0,
) -> list[Any]:
    """
    Користувачі куща / мережі.
    """

    service = get_service(
        data,
        "user",
        "users",
    )

    repository = get_repository(
        data,
        "user",
        "users",
    )

    payload = {
        "actor":
            actor,

        "current_user":
            actor,

        "bush_id":
            bush_id
            or None,

        "active_only":
            False,

        "include_inactive":
            True,
    }

    users = await query_collection(
        service=service,
        repository=repository,
        method_names=(
            "list_users",
            "get_users",
            "list_by_bush",
            "get_by_bush",
            "list_all",
            "get_all",
            "list",
            "all",
        ),
        payload=payload,
    )

    if bush_id <= 0:
        return users

    filtered: list[Any] = []

    for user in users:
        direct_bush_id = to_int(
            first_attr(
                user,
                "bush_id",
                "primary_bush_id",
                default=0,
            )
        )

        if direct_bush_id == bush_id:
            filtered.append(
                user
            )
            continue

        bush_ids = first_attr(
            user,
            "bush_ids",
            default=None,
        )

        if bush_ids:
            normalized = {
                to_int(item)
                for item in bush_ids
            }

            if bush_id in normalized:
                filtered.append(
                    user
                )

    # Якщо service вже сам відфільтрував,
    # але user model не містить bush_id.
    if not filtered and users:
        return users

    return filtered


# =========================================================
# LOAD SINGLE OBJECT
# =========================================================


async def load_object(
    *,
    kind: str,
    identifier: int,
    data: dict[str, Any],
) -> Any | None:
    """
    Bush / Store / User by ID.
    """

    if identifier <= 0:
        return None

    service = get_service(
        data,
        kind,
        f"{kind}s",
    )

    repository = get_repository(
        data,
        kind,
        f"{kind}s",
    )

    payload = {
        "id":
            identifier,

        f"{kind}_id":
            identifier,

        "object_id":
            identifier,
    }

    for source in (
        service,
        repository,
    ):
        if source is None:
            continue

        for method_name in (
            f"get_{kind}",
            "get_by_id",
            "get",
            "find_by_id",
        ):
            method = getattr(
                source,
                method_name,
                None,
            )

            if not callable(method):
                continue

            try:
                result = await call_method(
                    method,
                    payload,
                )
            except Exception:
                continue

            if result is not None:
                return first_attr(
                    result,
                    kind,
                    "record",
                    "item",
                    default=result,
                )

    return None


async def load_bush(
    *,
    bush_id: int,
    data: dict[str, Any],
) -> Any | None:
    return await load_object(
        kind="bush",
        identifier=bush_id,
        data=data,
    )


async def load_store(
    *,
    store_id: int,
    data: dict[str, Any],
) -> Any | None:
    return await load_object(
        kind="store",
        identifier=store_id,
        data=data,
    )


async def load_user(
    *,
    user_id: int,
    data: dict[str, Any],
) -> Any | None:
    return await load_object(
        kind="user",
        identifier=user_id,
        data=data,
    )


# =========================================================
# DISPLAY HELPERS
# =========================================================


def bush_title(
    bush: Any,
    *,
    bush_id: int = 0,
) -> str:
    """
    Bush display name.
    """

    title = first_attr(
        bush,
        "name",
        "title",
        default=None,
    )

    if title:
        return str(title)

    identifier = (
        object_id(bush)
        or bush_id
    )

    return (
        f"Кущ #{identifier}"
        if identifier
        else "Кущ"
    )


def store_title(
    store: Any,
    *,
    store_id: int = 0,
) -> str:
    """
    Store display name.
    """

    code = first_attr(
        store,
        "code",
        "store_code",
        "number",
        default=None,
    )

    name = first_attr(
        store,
        "name",
        "title",
        "address",
        default=None,
    )

    if code and name:
        return (
            f"{code} · {name}"
        )

    if code:
        return str(code)

    if name:
        return str(name)

    identifier = (
        object_id(store)
        or store_id
    )

    return (
        f"ТТ #{identifier}"
        if identifier
        else "Торгова точка"
    )


# =========================================================
# PAGINATION
# =========================================================


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
# CALLBACK COMPATIBILITY
# =========================================================


def _load_callback_classes() -> tuple[
    Any | None,
    Any | None,
]:
    """
    Підтягуємо callback-и без жорсткого import,
    щоб bush_admin.py не падав через різницю enum.
    """

    try:
        import app.keyboards as keyboards
    except Exception:
        return (
            None,
            None,
        )

    callback_class = getattr(
        keyboards,
        "BushAdminCallback",
        None,
    )

    action_class = getattr(
        keyboards,
        "BushAdminAction",
        None,
    )

    if (
        callback_class is not None
        and action_class is not None
    ):
        return (
            callback_class,
            action_class,
        )

    try:
        from app.keyboards import bush_admin as module
    except Exception:
        return (
            callback_class,
            action_class,
        )

    callback_class = (
        callback_class
        or getattr(
            module,
            "BushAdminCallback",
            None,
        )
    )

    action_class = (
        action_class
        or getattr(
            module,
            "BushAdminAction",
            None,
        )
    )

    return (
        callback_class,
        action_class,
    )


BushAdminCallback, BushAdminAction = (
    _load_callback_classes()
)


def _default_required_value(
    field: Any,
) -> Any:
    """
    Default для required CallbackData field.
    """

    annotation = getattr(
        field,
        "annotation",
        None,
    )

    text = str(
        annotation
    ).lower()

    if "bool" in text:
        return False

    if (
        "int" in text
        or "float" in text
    ):
        return 0

    return ""


def make_callback(
    *action_names: str,
    **payload: Any,
) -> str:
    """
    Створює BushAdminCallback.
    Якщо callback class недоступний —
    використовує raw ba:...
    """

    if (
        BushAdminCallback is not None
        and BushAdminAction is not None
    ):
        action = enum_member(
            BushAdminAction,
            *action_names,
        )

        if action is not None:
            values = {
                "action":
                    action,

                **payload,
            }

            model_fields = getattr(
                BushAdminCallback,
                "model_fields",
                None,
            )

            if isinstance(
                model_fields,
                dict,
            ):
                values = {
                    key: value
                    for key, value
                    in values.items()
                    if key
                    in model_fields
                }

                for (
                    field_name,
                    field,
                ) in model_fields.items():
                    if field_name in values:
                        continue

                    is_required = getattr(
                        field,
                        "is_required",
                        None,
                    )

                    try:
                        required = (
                            is_required()
                            if callable(is_required)
                            else False
                        )
                    except Exception:
                        required = False

                    if required:
                        values[
                            field_name
                        ] = (
                            _default_required_value(
                                field
                            )
                        )

            try:
                callback_data = (
                    BushAdminCallback(
                        **values
                    )
                )

                return (
                    callback_data.pack()
                )

            except Exception:
                logger.debug(
                    "Could not build "
                    "BushAdminCallback",
                    exc_info=True,
                )

    action = (
        action_names[0]
        if action_names
        else "menu"
    )

    bush_id = to_int(
        payload.get(
            "bush_id"
        )
    )

    store_id = to_int(
        payload.get(
            "store_id"
        )
    )

    user_id = to_int(
        payload.get(
            "user_id"
        )
    )

    page = to_int(
        payload.get(
            "page"
        )
    )

    return (
        f"ba:{action}:"
        f"{bush_id}:"
        f"{store_id}:"
        f"{user_id}:"
        f"{page}"
    )


# =========================================================
# FALLBACK KEYBOARDS
# =========================================================


def main_keyboard(
    *,
    bush_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Bush Admin dashboard keyboard.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏪 Торгові точки",
                    callback_data=make_callback(
                        "STORES",
                        "STORE_LIST",
                        bush_id=bush_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Користувачі",
                    callback_data=make_callback(
                        "USERS",
                        "USER_LIST",
                        bush_id=bush_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌿 Кущі",
                    callback_data=make_callback(
                        "BUSHES",
                        "BUSH_LIST",
                        bush_id=bush_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Оновити",
                    callback_data=make_callback(
                        "REFRESH",
                        "DASHBOARD",
                        bush_id=bush_id,
                    ),
                )
            ],
        ]
    )


def list_back_keyboard(
    *,
    bush_id: int = 0,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data=make_callback(
                        "DASHBOARD",
                        "MENU",
                        bush_id=bush_id,
                    ),
                )
            ]
        ]
    )


# =========================================================
# DASHBOARD
# =========================================================


async def dashboard_data(
    *,
    actor: DatabaseUser,
    data: dict[str, Any],
    bush_id: int = 0,
) -> dict[str, Any]:
    """
    Дані Bush Admin dashboard.
    """

    bushes = await query_bushes(
        actor=actor,
        data=data,
    )

    if bush_id <= 0:
        if len(bushes) == 1:
            bush_id = object_id(
                bushes[0]
            )

        elif (
            normalized_role(actor)
            == "BUSH_ADMIN"
        ):
            allowed = sorted(
                accessible_bush_ids(
                    data
                )
            )

            if allowed:
                bush_id = allowed[0]

    stores = await query_stores(
        actor=actor,
        data=data,
        bush_id=bush_id,
    )

    users = await query_users(
        actor=actor,
        data=data,
        bush_id=bush_id,
    )

    active_stores = sum(
        1
        for store in stores
        if to_bool(
            first_attr(
                store,
                "is_active",
                "active",
                default=True,
            ),
            default=True,
        )
    )

    active_users = sum(
        1
        for user in users
        if user_is_active(user)
    )

    bush = None

    if bush_id > 0:
        bush = next(
            (
                item
                for item in bushes
                if object_id(item)
                == bush_id
            ),
            None,
        )

        if bush is None:
            bush = await load_bush(
                bush_id=bush_id,
                data=data,
            )

    return {
        "bush_id":
            bush_id,

        "bush":
            bush,

        "bushes":
            bushes,

        "stores":
            stores,

        "users":
            users,

        "active_stores":
            active_stores,

        "active_users":
            active_users,
    }


async def build_bush_admin_dashboard(
    *,
    actor: DatabaseUser,
    data: dict[str, Any],
    bush_id: int = 0,
) -> tuple[
    str,
    InlineKeyboardMarkup,
]:
    """
    Dashboard text + keyboard.
    """

    state = await dashboard_data(
        actor=actor,
        data=data,
        bush_id=bush_id,
    )

    current_bush_id = to_int(
        state[
            "bush_id"
        ]
    )

    bush = state[
        "bush"
    ]

    if current_bush_id:
        scope_title = bush_title(
            bush,
            bush_id=current_bush_id,
        )
    else:
        scope_title = "Доступні кущі"

    text = (
        "🌿 <b>Панель адміністратора куща</b>\n\n"
        f"👤 {escape(user_display_name(actor))}\n"
        f"🎭 {escape(role_label(actor))}\n"
        f"📍 <b>{escape(scope_title)}</b>\n\n"
        f"🏪 ТТ: <b>{len(state['stores'])}</b>\n"
        f"✅ Активних ТТ: "
        f"<b>{state['active_stores']}</b>\n\n"
        f"👥 Користувачів: "
        f"<b>{len(state['users'])}</b>\n"
        f"✅ Активних: "
        f"<b>{state['active_users']}</b>"
    )

    return (
        text,
        main_keyboard(
            bush_id=current_bush_id,
        ),
    )


# =========================================================
# SHOW DASHBOARD
# =========================================================


async def show_dashboard_callback(
    callback: CallbackQuery,
    *,
    actor: DatabaseUser,
    data: dict[str, Any],
    bush_id: int = 0,
) -> None:
    text, markup = (
        await build_bush_admin_dashboard(
            actor=actor,
            data=data,
            bush_id=bush_id,
        )
    )

    await safe_edit(
        callback,
        text=text,
        reply_markup=markup,
    )


# =========================================================
# COMMAND
# =========================================================


@router.message(
    Command(
        "bush_admin",
        "bush",
    )
)
async def bush_admin_command(
    message: Message,
    **data: Any,
) -> None:
    """
    /bush_admin
    """

    actor = get_database_user(
        data
    )

    if not can_use_bush_admin_panel(
        actor
    ):
        await message.answer(
            "⛔ У вас немає доступу "
            "до панелі адміністратора куща."
        )
        return

    text, markup = (
        await build_bush_admin_dashboard(
            actor=actor,
            data=data,
        )
    )

    await message.answer(
        text,
        reply_markup=markup,
    )


# =========================================================
# LIST STORES
# =========================================================


async def show_stores(
    callback: CallbackQuery,
    *,
    actor: DatabaseUser,
    data: dict[str, Any],
    bush_id: int,
    page: int = 0,
) -> None:
    stores = await query_stores(
        actor=actor,
        data=data,
        bush_id=bush_id,
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        stores,
        page=page,
    )

    rows: list[
        list[
            InlineKeyboardButton
        ]
    ] = []

    for store in page_items:
        store_id = object_id(
            store
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        "🏪 "
                        + store_title(
                            store,
                            store_id=store_id,
                        )[:55]
                    ),
                    callback_data=make_callback(
                        "STORE",
                        "VIEW_STORE",
                        bush_id=bush_id,
                        store_id=store_id,
                        page=page,
                    ),
                )
            ]
        )

    if total_pages > 1:
        nav: list[
            InlineKeyboardButton
        ] = []

        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=make_callback(
                        "STORES",
                        "STORE_LIST",
                        bush_id=bush_id,
                        page=page - 1,
                    ),
                )
            )

        nav.append(
            InlineKeyboardButton(
                text=(
                    f"{page + 1}/"
                    f"{total_pages}"
                ),
                callback_data=make_callback(
                    "STORES",
                    "STORE_LIST",
                    bush_id=bush_id,
                    page=page,
                ),
            )
        )

        if (
            page
            < total_pages - 1
        ):
            nav.append(
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=make_callback(
                        "STORES",
                        "STORE_LIST",
                        bush_id=bush_id,
                        page=page + 1,
                    ),
                )
            )

        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data=make_callback(
                    "DASHBOARD",
                    "MENU",
                    bush_id=bush_id,
                ),
            )
        ]
    )

    await safe_edit(
        callback,
        text=(
            "🏪 <b>Торгові точки</b>\n\n"
            f"Усього: <b>{len(stores)}</b>"
        ),
        reply_markup=(
            InlineKeyboardMarkup(
                inline_keyboard=rows
            )
        ),
    )


# =========================================================
# LIST USERS
# =========================================================


async def show_users(
    callback: CallbackQuery,
    *,
    actor: DatabaseUser,
    data: dict[str, Any],
    bush_id: int,
    page: int = 0,
) -> None:
    users = await query_users(
        actor=actor,
        data=data,
        bush_id=bush_id,
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        users,
        page=page,
    )

    rows: list[
        list[
            InlineKeyboardButton
        ]
    ] = []

    for user in page_items:
        user_id = object_id(
            user
        )

        icon = (
            "✅"
            if user_is_active(user)
            else "⛔"
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{icon} "
                        f"{user_display_name(user)[:40]}"
                        f" · "
                        f"{role_label(user)[:14]}"
                    ),
                    callback_data=make_callback(
                        "USER",
                        "VIEW_USER",
                        bush_id=bush_id,
                        user_id=user_id,
                        page=page,
                    ),
                )
            ]
        )

    if total_pages > 1:
        nav: list[
            InlineKeyboardButton
        ] = []

        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=make_callback(
                        "USERS",
                        "USER_LIST",
                        bush_id=bush_id,
                        page=page - 1,
                    ),
                )
            )

        nav.append(
            InlineKeyboardButton(
                text=(
                    f"{page + 1}/"
                    f"{total_pages}"
                ),
                callback_data=make_callback(
                    "USERS",
                    "USER_LIST",
                    bush_id=bush_id,
                    page=page,
                ),
            )
        )

        if (
            page
            < total_pages - 1
        ):
            nav.append(
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=make_callback(
                        "USERS",
                        "USER_LIST",
                        bush_id=bush_id,
                        page=page + 1,
                    ),
                )
            )

        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data=make_callback(
                    "DASHBOARD",
                    "MENU",
                    bush_id=bush_id,
                ),
            )
        ]
    )

    await safe_edit(
        callback,
        text=(
            "👥 <b>Користувачі куща</b>\n\n"
            f"Усього: <b>{len(users)}</b>"
        ),
        reply_markup=(
            InlineKeyboardMarkup(
                inline_keyboard=rows
            )
        ),
    )


# =========================================================
# LIST BUSHES
# =========================================================


async def show_bushes(
    callback: CallbackQuery,
    *,
    actor: DatabaseUser,
    data: dict[str, Any],
    page: int = 0,
) -> None:
    bushes = await query_bushes(
        actor=actor,
        data=data,
    )

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        bushes,
        page=page,
    )

    rows: list[
        list[
            InlineKeyboardButton
        ]
    ] = []

    for bush in page_items:
        bush_id = object_id(
            bush
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        "🌿 "
                        + bush_title(
                            bush,
                            bush_id=bush_id,
                        )[:55]
                    ),
                    callback_data=make_callback(
                        "BUSH",
                        "VIEW_BUSH",
                        bush_id=bush_id,
                        page=page,
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data=make_callback(
                    "DASHBOARD",
                    "MENU",
                ),
            )
        ]
    )

    await safe_edit(
        callback,
        text=(
            "🌿 <b>Доступні кущі</b>\n\n"
            f"Усього: <b>{len(bushes)}</b>"
        ),
        reply_markup=(
            InlineKeyboardMarkup(
                inline_keyboard=rows
            )
        ),
    )


# =========================================================
# STORE CARD
# =========================================================


async def show_store_card(
    callback: CallbackQuery,
    *,
    actor: DatabaseUser,
    data: dict[str, Any],
    bush_id: int,
    store_id: int,
) -> None:
    store = await load_store(
        store_id=store_id,
        data=data,
    )

    if store is None:
        await callback.answer(
            "ТТ не знайдено.",
            show_alert=True,
        )
        return

    active = to_bool(
        first_attr(
            store,
            "is_active",
            "active",
            default=True,
        ),
        default=True,
    )

    cluster = first_attr(
        store,
        "cluster",
        "cluster_name",
        "opening_cluster",
        default=None,
    )

    address = first_attr(
        store,
        "address",
        default=None,
    )

    lines = [
        "🏪 <b>Торгова точка</b>",
        "",
        (
            f"<b>{escape(store_title(store, store_id=store_id))}</b>"
        ),
        (
            "Статус: "
            f"<b>{'✅ активна' if active else '⛔ неактивна'}</b>"
        ),
    ]

    if address:
        lines.append(
            f"📍 {escape(str(address))}"
        )

    if cluster:
        lines.append(
            f"🕐 Кластер: "
            f"<b>{escape(str(cluster))}</b>"
        )

    await safe_edit(
        callback,
        text="\n".join(lines),
        reply_markup=(
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 До ТТ",
                            callback_data=make_callback(
                                "STORES",
                                "STORE_LIST",
                                bush_id=bush_id,
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Панель куща",
                            callback_data=make_callback(
                                "DASHBOARD",
                                "MENU",
                                bush_id=bush_id,
                            ),
                        )
                    ],
                ]
            )
        ),
    )


# =========================================================
# USER CARD
# =========================================================


async def show_user_card(
    callback: CallbackQuery,
    *,
    actor: DatabaseUser,
    data: dict[str, Any],
    bush_id: int,
    user_id: int,
) -> None:
    user = await load_user(
        user_id=user_id,
        data=data,
    )

    if user is None:
        await callback.answer(
            "Користувача не знайдено.",
            show_alert=True,
        )
        return

    telegram_id = to_int(
        first_attr(
            user,
            "telegram_id",
            "tg_id",
            default=0,
        )
    )

    username = first_attr(
        user,
        "username",
        default=None,
    )

    lines = [
        "👤 <b>Користувач</b>",
        "",
        (
            f"<b>{escape(user_display_name(user))}</b>"
        ),
        (
            f"🎭 {escape(role_label(user))}"
        ),
        (
            "Статус: "
            f"<b>{'✅ активний' if user_is_active(user) else '⛔ неактивний'}</b>"
        ),
    ]

    if telegram_id:
        lines.append(
            "Telegram ID: "
            f"<code>{telegram_id}</code>"
        )

    if username:
        normalized_username = (
            str(username)
            .removeprefix("@")
        )

        lines.append(
            f"@{escape(normalized_username)}"
        )

    await safe_edit(
        callback,
        text="\n".join(lines),
        reply_markup=(
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 До користувачів",
                            callback_data=make_callback(
                                "USERS",
                                "USER_LIST",
                                bush_id=bush_id,
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Панель куща",
                            callback_data=make_callback(
                                "DASHBOARD",
                                "MENU",
                                bush_id=bush_id,
                            ),
                        )
                    ],
                ]
            )
        ),
    )


# =========================================================
# CALLBACK DISPATCH
# =========================================================


def callback_action(
    callback_data: Any,
) -> str:
    action = first_attr(
        callback_data,
        "action",
        default="",
    )

    action = first_attr(
        action,
        "value",
        "name",
        default=action,
    )

    return (
        str(action)
        .strip()
        .lower()
    )


async def dispatch_bush_admin_callback(
    callback: CallbackQuery,
    callback_data: Any,
    **data: Any,
) -> None:
    """
    Один dispatcher для різних версій
    BushAdminAction.
    """

    actor = get_database_user(
        data
    )

    if not can_use_bush_admin_panel(
        actor
    ):
        await callback.answer(
            "Немає доступу.",
            show_alert=True,
        )
        return

    action = callback_action(
        callback_data
    )

    bush_id = to_int(
        first_attr(
            callback_data,
            "bush_id",
            "target_id",
            default=0,
        )
    )

    store_id = to_int(
        first_attr(
            callback_data,
            "store_id",
            default=0,
        )
    )

    user_id = to_int(
        first_attr(
            callback_data,
            "user_id",
            default=0,
        )
    )

    page = to_int(
        first_attr(
            callback_data,
            "page",
            default=0,
        )
    )

    await callback.answer()

    if action in {
        "menu",
        "dashboard",
        "refresh",
        "home",
        "back",
    }:
        await show_dashboard_callback(
            callback,
            actor=actor,
            data=data,
            bush_id=bush_id,
        )
        return

    if action in {
        "bushes",
        "bush_list",
        "select_bush",
    }:
        await show_bushes(
            callback,
            actor=actor,
            data=data,
            page=page,
        )
        return

    if action in {
        "bush",
        "view_bush",
    }:
        await show_dashboard_callback(
            callback,
            actor=actor,
            data=data,
            bush_id=bush_id,
        )
        return

    if action in {
        "stores",
        "store_list",
    }:
        await show_stores(
            callback,
            actor=actor,
            data=data,
            bush_id=bush_id,
            page=page,
        )
        return

    if action in {
        "store",
        "view_store",
    }:
        await show_store_card(
            callback,
            actor=actor,
            data=data,
            bush_id=bush_id,
            store_id=store_id,
        )
        return

    if action in {
        "users",
        "user_list",
    }:
        await show_users(
            callback,
            actor=actor,
            data=data,
            bush_id=bush_id,
            page=page,
        )
        return

    if action in {
        "user",
        "view_user",
    }:
        await show_user_card(
            callback,
            actor=actor,
            data=data,
            bush_id=bush_id,
            user_id=user_id,
        )
        return

    await callback.answer(
        "Розділ ще не підключений.",
        show_alert=False,
    )


# =========================================================
# REGISTER REAL CALLBACK CLASS
# =========================================================


if BushAdminCallback is not None:
    try:
        router.callback_query.register(
            dispatch_bush_admin_callback,
            BushAdminCallback.filter(),
        )

    except Exception:
        logger.exception(
            "Could not register "
            "BushAdminCallback handler"
        )


# =========================================================
# RAW CALLBACK FALLBACK
# =========================================================


@router.callback_query(
    F.data.startswith("ba:")
)
async def raw_bush_admin_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Fallback:
        ba:action:bush_id:store_id:user_id:page
    """

    raw = (
        callback.data
        or ""
    )

    parts = raw.split(":")

    if len(parts) < 2:
        await callback.answer()
        return

    action = (
        parts[1]
        if len(parts) > 1
        else "dashboard"
    )

    bush_id = to_int(
        parts[2]
        if len(parts) > 2
        else 0
    )

    store_id = to_int(
        parts[3]
        if len(parts) > 3
        else 0
    )

    user_id = to_int(
        parts[4]
        if len(parts) > 4
        else 0
    )

    page = to_int(
        parts[5]
        if len(parts) > 5
        else 0
    )

    class RawCallbackData:
        pass

    callback_data = (
        RawCallbackData()
    )

    callback_data.action = action
    callback_data.bush_id = bush_id
    callback_data.store_id = store_id
    callback_data.user_id = user_id
    callback_data.page = page

    await dispatch_bush_admin_callback(
        callback,
        callback_data,
        **data,
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "router",

    "PAGE_SIZE",
    "BUSH_ADMIN_ROLES",
    "ROLE_LABELS",

    "first_attr",
    "to_int",
    "to_bool",

    "filtered_kwargs",
    "filter_kwargs",

    "create_model",
    "build_keyboard",
    "unwrap_collection",
    "enum_member",
    "object_id",

    "normalized_role",
    "role_label",
    "user_display_name",
    "user_is_active",

    "can_use_bush_admin_panel",

    "has_network_access",
    "accessible_bush_ids",
    "accessible_store_ids",

    "get_service",
    "get_repository",
    "call_method",
    "query_collection",

    "query_bushes",
    "query_stores",
    "query_users",

    "load_object",
    "load_bush",
    "load_store",
    "load_user",

    "bush_title",
    "store_title",

    "paginate",

    "BushAdminCallback",
    "BushAdminAction",

    "make_callback",
    "main_keyboard",
    "list_back_keyboard",

    "dashboard_data",
    "build_bush_admin_dashboard",
    "show_dashboard_callback",

    "show_stores",
    "show_users",
    "show_bushes",

    "show_store_card",
    "show_user_card",

    "callback_action",
    "dispatch_bush_admin_callback",
]