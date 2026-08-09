from __future__ import annotations

import inspect
import logging
from datetime import (
    datetime,
    timedelta,
)
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
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
from app.handlers.bush_admin import (
    build_keyboard,
    create_model,
    unwrap_collection,
)
from app.handlers.common import (
    get_database_user,
    safe_edit,
    user_role_name,
)
from app.handlers.director import (
    object_id,
    query_all_stores,
    query_network_bushes,
    store_code,
    store_name,
)
from app.handlers.opening import (
    call_method,
    first_attr,
    get_service,
    now_local,
    to_bool,
    to_int,
)
from app.handlers.root_admin import (
    is_root_admin,
)
from app.handlers.store import (
    load_store,
    store_title,
)

from app.keyboards import (
    InviteAction,
    InviteCallback,
)
from app.keyboards.invites import (
    InviteCreateState,
    InviteExpiration,
    InviteListItem,
    InviteStatus,
    InviteType,
    InviteUIAction,
    InviteUICallback,
    InviteBushItem,
    InviteStoreItem,
    active_invites_keyboard,
    bush_invite_create_keyboard,
    created_invite_keyboard,
    director_invite_create_keyboard,
    invite_activation_error_keyboard,
    invite_card_keyboard,
    invite_create_cancel_keyboard,
    invite_expiration_keyboard,
    invite_expired_keyboard,
    invite_no_access_keyboard,
    invite_revoked_keyboard,
    invite_store_selector_keyboard,
    invite_bush_selector_keyboard,
    invite_used_keyboard,
    invites_back_keyboard,
    invites_main_keyboard,
    revoke_invite_confirmation_keyboard,
    store_invite_create_keyboard,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="invites",
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


class InviteStates(
    StatesGroup
):
    """
    Стан створення invite.

    Тип invite потрібно тримати у FSM,
    тому що InviteUICallback.CREATE
    не містить invite_type.
    """

    creating = State()


# =========================================================
# GENERIC HELPERS
# =========================================================


def filter_kwargs(
    method: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Передає callable тільки
    підтримувані kwargs.
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
    Enum / str -> lowercase string.
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


def normalize_role(
    user: DatabaseUser | None,
) -> str:
    """
    Нормалізація ролі.
    """

    if user is None:
        return ""

    return (
        user_role_name(
            user
        )
        .strip()
        .upper()
    )


def can_manage_invites(
    user: DatabaseUser | None,
) -> bool:
    """
    Хто може створювати invite.
    """

    return (
        normalize_role(
            user
        )
        in MANAGER_ROLES
    )


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
# SERVICES
# =========================================================


def get_invite_service(
    data: dict[str, Any],
) -> Any | None:
    """
    InviteService.
    """

    return get_service(
        data,
        "invites",
        "invite",
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
# ACCESS
# =========================================================


def access_context(
    data: dict[str, Any],
) -> Any | None:
    """
    Middleware access context.
    """

    return (
        data.get(
            "access_context"
        )
        or data.get(
            "access_scope"
        )
    )


def has_network_access(
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> bool:
    """
    Network-level access.
    """

    if user is None:
        return False

    if is_root_admin(
        user
    ):
        return True

    if (
        normalize_role(
            user
        )
        == "DIRECTOR"
    ):
        return True

    direct = data.get(
        "has_network_access"
    )

    if isinstance(
        direct,
        bool,
    ):
        return direct

    context = access_context(
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

    context = access_context(
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
            to_int(item)
            for item in direct
            if to_int(item) > 0
        }

    context = access_context(
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
        to_int(item)
        for item in values
        if to_int(item) > 0
    }


def can_access_bush(
    *,
    bush_id: int,
    user: DatabaseUser,
    data: dict[str, Any],
) -> bool:
    """
    Bush permission.
    """

    if bush_id <= 0:
        return False

    if has_network_access(
        user,
        data,
    ):
        return True

    return (
        bush_id
        in accessible_bush_ids(
            data
        )
    )


def can_access_store(
    *,
    store: Any,
    store_id: int,
    user: DatabaseUser,
    data: dict[str, Any],
) -> bool:
    """
    Store permission.
    """

    if store_id <= 0:
        return False

    if has_network_access(
        user,
        data,
    ):
        return True

    if (
        store_id
        in accessible_store_ids(
            data
        )
    ):
        return True

    bush_id = to_int(
        first_attr(
            store,
            "bush_id",
            default=0,
        )
    )

    return (
        bush_id > 0
        and bush_id
        in accessible_bush_ids(
            data
        )
    )


# =========================================================
# EXPIRATION
# =========================================================


def expiration_delta(
    expiration: str,
) -> timedelta | None:
    """
    InviteExpiration -> timedelta.
    """

    normalized = (
        expiration
        .strip()
        .lower()
    )

    mapping: dict[
        str,
        timedelta | None,
    ] = {
        "1h":
            timedelta(
                hours=1
            ),

        "6h":
            timedelta(
                hours=6
            ),

        "1d":
            timedelta(
                days=1
            ),

        "3d":
            timedelta(
                days=3
            ),

        "7d":
            timedelta(
                days=7
            ),

        "30d":
            timedelta(
                days=30
            ),

        "never":
            None,
    }

    if normalized not in mapping:
        raise ValueError(
            f"Unknown expiration: "
            f"{expiration}"
        )

    return mapping[
        normalized
    ]


def expiration_title(
    value: str,
) -> str:
    """
    Людський текст.
    """

    mapping = {
        "1h":
            "1 година",

        "6h":
            "6 годин",

        "1d":
            "1 день",

        "3d":
            "3 дні",

        "7d":
            "7 днів",

        "30d":
            "30 днів",

        "never":
            "Без обмеження",
    }

    return mapping.get(
        value,
        value,
    )


# =========================================================
# INVITE TYPE
# =========================================================


def invite_type_value(
    value: Any,
) -> str:
    """
    InviteType -> store/bush/director.
    """

    raw = enum_value(
        value
    )

    if raw in {
        "store",
        "bush",
        "director",
    }:
        return raw

    return raw


def service_scope_for_type(
    invite_type: str,
) -> str:
    """
    Mapping до InviteService scope.
    """

    normalized = (
        invite_type
        .strip()
        .lower()
    )

    if normalized == "store":
        return "store"

    if normalized == "bush":
        return "bush"

    if normalized == "director":
        return "network"

    raise ValueError(
        f"Unknown invite type: "
        f"{invite_type}"
    )


def role_for_type(
    invite_type: str,
) -> str:
    """
    Роль, яку створює invite.

    STORE    -> STORE_USER
    BUSH     -> LION
    DIRECTOR -> DIRECTOR
    """

    mapping = {
        "store":
            "STORE_USER",

        "bush":
            "LION",

        "director":
            "DIRECTOR",
    }

    return mapping[
        invite_type
    ]


# =========================================================
# SELECTOR ITEMS
# =========================================================


async def build_store_items(
    *,
    user: DatabaseUser,
    data: dict[str, Any],
) -> list[
    InviteStoreItem
]:
    """
    Доступні ТТ.
    """

    stores = await query_all_stores(
        data=data
    )

    result: list[
        InviteStoreItem
    ] = []

    for store in stores:
        store_id = object_id(
            store
        )

        if store_id <= 0:
            continue

        if not can_access_store(
            store=store,
            store_id=store_id,
            user=user,
            data=data,
        ):
            continue

        result.append(
            create_model(
                InviteStoreItem,

                store_id=store_id,

                code=store_code(
                    store
                ),

                name=(
                    store_name(
                        store
                    )
                ),
            )
        )

    return result


async def build_bush_items(
    *,
    user: DatabaseUser,
    data: dict[str, Any],
) -> list[
    InviteBushItem
]:
    """
    Доступні кущі.
    """

    bushes = await query_network_bushes(
        data=data
    )

    result: list[
        InviteBushItem
    ] = []

    for bush in bushes:
        bush_id = object_id(
            bush
        )

        if bush_id <= 0:
            continue

        if not can_access_bush(
            bush_id=bush_id,
            user=user,
            data=data,
        ):
            continue

        name = first_attr(
            bush,
            "name",
            "title",
            default=(
                f"Кущ #{bush_id}"
            ),
        )

        result.append(
            create_model(
                InviteBushItem,

                bush_id=bush_id,

                name=str(
                    name
                ),
            )
        )

    return result


# =========================================================
# INVITE RESULT HELPERS
# =========================================================


def invite_object(
    result: Any,
) -> Any:
    """
    Wrapper -> invite.
    """

    return first_attr(
        result,
        "invite",
        "created_invite",
        "record",
        default=result,
    )


def invite_id(
    value: Any,
) -> int:
    """
    Invite ID.
    """

    invite = invite_object(
        value
    )

    return to_int(
        first_attr(
            invite,
            "id",
            "invite_id",
            default=0,
        )
    )


def invite_token(
    value: Any,
) -> str | None:
    """
    Invite token.
    """

    invite = invite_object(
        value
    )

    token = (
        first_attr(
            value,
            "token",
            "invite_token",
            "code",
            default=None,
        )
        or first_attr(
            invite,
            "token",
            "invite_token",
            "code",
            default=None,
        )
    )

    if not token:
        return None

    return str(
        token
    )


def invite_url(
    value: Any,
) -> str | None:
    """
    Якщо service уже створив URL.
    """

    invite = invite_object(
        value
    )

    result = (
        first_attr(
            value,
            "url",
            "invite_url",
            "deep_link",
            "link",
            default=None,
        )
        or first_attr(
            invite,
            "url",
            "invite_url",
            "deep_link",
            "link",
            default=None,
        )
    )

    if not result:
        return None

    return str(
        result
    )


def invite_created_successfully(
    result: Any,
) -> bool:
    """
    Success flag.
    """

    if result is None:
        return False

    if isinstance(
        result,
        bool,
    ):
        return result

    value = first_attr(
        result,
        "success",
        "created",
        "is_success",
        default=None,
    )

    if value is not None:
        return to_bool(
            value
        )

    return (
        invite_object(
            result
        )
        is not None
    )


# =========================================================
# BUILD DEEP LINK
# =========================================================


async def build_deep_link(
    *,
    callback: CallbackQuery,
    result: Any,
) -> str | None:
    """
    Створює:

        https://t.me/BOT?start=invite_TOKEN
    """

    direct_url = invite_url(
        result
    )

    if direct_url:
        return direct_url

    token = invite_token(
        result
    )

    if not token:
        return None

    try:
        me = await callback.bot.get_me()

    except Exception:
        logger.exception(
            "Failed to get bot username"
        )

        return None

    if not me.username:
        return None

    return (
        f"https://t.me/{me.username}"
        f"?start=invite_{token}"
    )


# =========================================================
# CREATE INVITE SERVICE
# =========================================================


async def create_invite(
    *,
    invite_type: str,
    target_id: int,
    expiration: str,
    single_use: bool,
    actor: DatabaseUser,
    data: dict[str, Any],
) -> Any:
    """
    Створення invite через service.
    """

    service = get_invite_service(
        data
    )

    if service is None:
        raise RuntimeError(
            "InviteService недоступний."
        )

    scope = service_scope_for_type(
        invite_type
    )

    role = role_for_type(
        invite_type
    )

    delta = expiration_delta(
        expiration
    )

    expires_at = (
        now_local()
        + delta
        if delta is not None
        else None
    )

    max_uses = (
        1
        if single_use
        else None
    )

    payload = {
        # scope
        "scope":
            scope,

        "invite_scope":
            scope,

        "type":
            invite_type,

        "invite_type":
            invite_type,

        # target
        "target_id":
            target_id,

        "store_id":
            (
                target_id
                if invite_type
                == "store"
                else None
            ),

        "bush_id":
            (
                target_id
                if invite_type
                == "bush"
                else None
            ),

        # role
        "role":
            role,

        "user_role":
            role,

        "target_role":
            role,

        # expiration
        "expires_at":
            expires_at,

        "expiration":
            delta,

        "expires_in":
            delta,

        "expiration_seconds":
            (
                int(
                    delta.total_seconds()
                )
                if delta is not None
                else None
            ),

        # usage
        "single_use":
            single_use,

        "is_single_use":
            single_use,

        "max_uses":
            max_uses,

        # actor
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

        "created_by_id":
            getattr(
                actor,
                "id",
                None,
            ),
    }

    last_error: Exception | None = None

    for method_name in (
        "create_invite",
        "create",
        "generate_invite",
        "issue_invite",
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
                "Invite creation method failed: "
                "%s",
                method_name,
            )

            continue

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        "Метод створення invite "
        "не знайдено."
    )


# =========================================================
# LIST INVITES
# =========================================================


async def list_invites(
    *,
    actor: DatabaseUser,
    data: dict[str, Any],
) -> list[Any]:
    """
    Список доступних invite.
    """

    service = get_invite_service(
        data
    )

    if service is None:
        return []

    payload = {
        "actor":
            actor,

        "user":
            actor,

        "user_id":
            getattr(
                actor,
                "id",
                None,
            ),

        "active_only":
            False,

        "include_expired":
            True,

        "include_revoked":
            True,
    }

    for method_name in (
        "list_invites",
        "get_invites",
        "list",
        "search",
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

        return unwrap_collection(
            result
        )

    return []


# =========================================================
# GET INVITE
# =========================================================


async def get_invite(
    *,
    invite_id_value: int,
    actor: DatabaseUser,
    data: dict[str, Any],
) -> Any | None:
    """
    Invite by id.
    """

    service = get_invite_service(
        data
    )

    if service is None:
        return None

    payload = {
        "invite_id":
            invite_id_value,

        "id":
            invite_id_value,

        "actor":
            actor,

        "user":
            actor,
    }

    for method_name in (
        "get_invite",
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
            return invite_object(
                result
            )

    # fallback list
    invites = await list_invites(
        actor=actor,
        data=data,
    )

    return next(
        (
            invite
            for invite in invites
            if invite_id(
                invite
            )
            == invite_id_value
        ),
        None,
    )


# =========================================================
# STATUS
# =========================================================


def get_invite_status(
    invite: Any,
) -> InviteStatus:
    """
    Визначає status.
    """

    raw = enum_value(
        first_attr(
            invite,
            "status",
            default=None,
        )
    )

    if raw in {
        "revoked",
        "cancelled",
        "canceled",
    }:
        return InviteStatus.REVOKED

    if raw in {
        "used",
        "consumed",
        "activated",
    }:
        return InviteStatus.USED

    if raw == "expired":
        return InviteStatus.EXPIRED

    if raw == "active":
        return InviteStatus.ACTIVE

    revoked_at = first_attr(
        invite,
        "revoked_at",
        default=None,
    )

    if revoked_at is not None:
        return InviteStatus.REVOKED

    used_at = first_attr(
        invite,
        "used_at",
        "activated_at",
        "consumed_at",
        default=None,
    )

    if used_at is not None:
        return InviteStatus.USED

    expires_at = first_attr(
        invite,
        "expires_at",
        default=None,
    )

    if isinstance(
        expires_at,
        datetime,
    ):
        now = now_local()

        try:
            if expires_at <= now:
                return InviteStatus.EXPIRED

        except TypeError:
            # naive datetime fallback
            if (
                expires_at.replace(
                    tzinfo=None
                )
                <= now.replace(
                    tzinfo=None
                )
            ):
                return InviteStatus.EXPIRED

    return InviteStatus.ACTIVE


# =========================================================
# INVITE LIST ITEM
# =========================================================


def build_invite_list_item(
    invite: Any,
) -> InviteListItem:
    """
    Invite -> UI item.
    """

    identifier = invite_id(
        invite
    )

    status = get_invite_status(
        invite
    )

    scope = enum_value(
        first_attr(
            invite,
            "scope",
            "invite_scope",
            default="",
        )
    )

    role = enum_value(
        first_attr(
            invite,
            "role",
            "target_role",
            default="",
        )
    )

    target_id = to_int(
        first_attr(
            invite,
            "target_id",
            "store_id",
            "bush_id",
            default=0,
        )
    )

    label = first_attr(
        invite,
        "target_name",
        "label",
        "title",
        default=None,
    )

    if not label:
        if scope == "store":
            label = (
                f"ТТ #{target_id}"
            )

        elif scope == "bush":
            label = (
                f"Кущ #{target_id}"
            )

        elif role == "director":
            label = "Директор"

        else:
            label = "Запрошення"

    created_at = first_attr(
        invite,
        "created_at",
        default=None,
    )

    expires_at = first_attr(
        invite,
        "expires_at",
        default=None,
    )

    return create_model(
        InviteListItem,

        invite_id=identifier,

        title=str(
            label
        ),

        name=str(
            label
        ),

        status=status,

        scope=scope,

        target_id=target_id,

        created_at=created_at,

        expires_at=expires_at,
    )


# =========================================================
# INVITE CARD TEXT
# =========================================================


def format_datetime(
    value: Any,
) -> str:
    """
    Datetime UI.
    """

    if value is None:
        return "без обмеження"

    if isinstance(
        value,
        datetime,
    ):
        return value.strftime(
            "%d.%m.%Y %H:%M"
        )

    return str(
        value
    )


def build_invite_card_text(
    invite: Any,
) -> str:
    """
    Повна картка invite.
    """

    status = get_invite_status(
        invite
    )

    status_labels = {
        InviteStatus.ACTIVE:
            "🟢 Активне",

        InviteStatus.USED:
            "✅ Використане",

        InviteStatus.EXPIRED:
            "⌛ Прострочене",

        InviteStatus.REVOKED:
            "🚫 Відкликане",
    }

    scope = enum_value(
        first_attr(
            invite,
            "scope",
            "invite_scope",
            default="",
        )
    )

    role = enum_value(
        first_attr(
            invite,
            "role",
            "target_role",
            default="",
        )
    )

    target_id = to_int(
        first_attr(
            invite,
            "target_id",
            "store_id",
            "bush_id",
            default=0,
        )
    )

    created_at = first_attr(
        invite,
        "created_at",
        default=None,
    )

    expires_at = first_attr(
        invite,
        "expires_at",
        default=None,
    )

    used_at = first_attr(
        invite,
        "used_at",
        "activated_at",
        default=None,
    )

    max_uses = first_attr(
        invite,
        "max_uses",
        default=None,
    )

    uses_count = to_int(
        first_attr(
            invite,
            "uses_count",
            "used_count",
            default=0,
        )
    )

    lines = [
        "🔗 <b>Запрошення</b>",
        "",
        (
            "ID: "
            f"<code>{invite_id(invite)}</code>"
        ),
        (
            "Статус: "
            f"<b>{status_labels.get(status, status.value)}</b>"
        ),
    ]

    if scope:
        lines.append(
            "Scope: "
            f"<b>{escape(scope)}</b>"
        )

    if role:
        lines.append(
            "Роль: "
            f"<b>{escape(role.upper())}</b>"
        )

    if target_id > 0:
        lines.append(
            "Target ID: "
            f"<code>{target_id}</code>"
        )

    lines.extend(
        [
            "",
            (
                "Створено: "
                f"<b>{escape(format_datetime(created_at))}</b>"
            ),
            (
                "Діє до: "
                f"<b>{escape(format_datetime(expires_at))}</b>"
            ),
        ]
    )

    if max_uses is not None:
        lines.append(
            "Використань: "
            f"<b>{uses_count}/{max_uses}</b>"
        )

    if used_at is not None:
        lines.append(
            "Використано: "
            f"<b>{escape(format_datetime(used_at))}</b>"
        )

    return "\n".join(
        lines
    )


# =========================================================
# REVOKE
# =========================================================


async def revoke_invite(
    *,
    invite_id_value: int,
    actor: DatabaseUser,
    data: dict[str, Any],
) -> bool:
    """
    Відкликає invite.
    """

    service = get_invite_service(
        data
    )

    if service is None:
        return False

    payload = {
        "invite_id":
            invite_id_value,

        "id":
            invite_id_value,

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
    }

    for method_name in (
        "revoke_invite",
        "revoke",
        "cancel_invite",
        "deactivate_invite",
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
            logger.exception(
                "Invite revoke failed: %s",
                invite_id_value,
            )

            continue

        await flush_changes(
            data
        )

        explicit = first_attr(
            result,
            "success",
            "revoked",
            default=True,
        )

        return to_bool(
            explicit,
            default=True,
        )

    return False


# =========================================================
# SHOW MENU
# =========================================================


async def show_invites_menu(
    callback: CallbackQuery,
    *,
    user: DatabaseUser,
    data: dict[str, Any],
) -> None:
    """
    Main invite menu.
    """

    role = normalize_role(
        user
    )

    can_store = (
        role
        in MANAGER_ROLES
    )

    can_bush = (
        role
        in {
            "ROOT_ADMIN",
            "DIRECTOR",
            "BUSH_ADMIN",
        }
    )

    can_director = (
        role
        == "ROOT_ADMIN"
    )

    await safe_edit(
        callback,
        text=(
            "🔗 <b>Запрошення</b>\n\n"
            "Оберіть тип запрошення:"
        ),
        reply_markup=(
            build_keyboard(
                invites_main_keyboard,

                can_store=can_store,

                can_bush=can_bush,

                can_director=(
                    can_director
                ),
            )
        ),
    )


# =========================================================
# /INVITES
# =========================================================


@router.message(
    Command(
        "invites",
        "invite",
    )
)
async def invites_command(
    message: Message,
    **data: Any,
) -> None:
    """
    /invites
    """

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        await message.answer(
            "⛔ Керування запрошеннями "
            "вам недоступне.",
            reply_markup=(
                invite_no_access_keyboard()
            ),
        )

        return

    await message.answer(
        "🔗 <b>Запрошення</b>\n\n"
        "Відкрийте меню керування:",
        reply_markup=(
            build_keyboard(
                invites_main_keyboard,

                can_store=True,

                can_bush=True,

                can_director=(
                    is_root_admin(
                        user
                    )
                ),
            )
        ),
    )


# =========================================================
# MENU CALLBACK
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.MENU
    )
)
async def invites_menu_callback(
    callback: CallbackQuery,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Invite main menu.
    """

    await callback.answer()

    await state.clear()

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        await safe_edit(
            callback,
            text=(
                "⛔ Керування запрошеннями "
                "вам недоступне."
            ),
            reply_markup=(
                invite_no_access_keyboard()
            ),
        )

        return

    await show_invites_menu(
        callback,
        user=user,
        data=data,
    )


# =========================================================
# STORE INVITE
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.SELECT_STORE
    )
)
async def select_store_callback(
    callback: CallbackQuery,
    callback_data: InviteUICallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Вибір ТТ.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        return

    # -----------------------------------------------------
    # STORE ALREADY SELECTED
    # -----------------------------------------------------

    if callback_data.target_id > 0:
        store = await load_store(
            store_id=(
                callback_data.target_id
            ),
            data=data,
        )

        if store is None:
            await callback.answer(
                "ТТ не знайдено.",
                show_alert=True,
            )

            return

        if not can_access_store(
            store=store,
            store_id=(
                callback_data.target_id
            ),
            user=user,
            data=data,
        ):
            await callback.answer(
                "Немає доступу до цієї ТТ.",
                show_alert=True,
            )

            return

        await state.set_state(
            InviteStates.creating
        )

        await state.update_data(
            invite_type="store",
            invite_target_id=(
                callback_data.target_id
            ),
            invite_expiration="1d",
            invite_single_use=True,
        )

        await safe_edit(
            callback,
            text=(
                "🏪 <b>Invite для ТТ</b>\n\n"
                f"{escape(store_title(store, store_id=callback_data.target_id))}\n\n"
                "Налаштуйте запрошення:"
            ),
            reply_markup=(
                build_keyboard(
                    store_invite_create_keyboard,

                    store_id=(
                        callback_data.target_id
                    ),

                    target_id=(
                        callback_data.target_id
                    ),
                )
            ),
        )

        return

    # -----------------------------------------------------
    # SELECTOR
    # -----------------------------------------------------

    items = await build_store_items(
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
    )

    await safe_edit(
        callback,
        text=(
            "🏪 <b>Оберіть торгову точку</b>"
        ),
        reply_markup=(
            build_keyboard(
                invite_store_selector_keyboard,

                stores=page_items,

                page=page,

                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# BUSH INVITE
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.SELECT_BUSH
    )
)
async def select_bush_callback(
    callback: CallbackQuery,
    callback_data: InviteUICallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Bush invite.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        return

    if callback_data.target_id > 0:
        bush_id = (
            callback_data.target_id
        )

        if not can_access_bush(
            bush_id=bush_id,
            user=user,
            data=data,
        ):
            await callback.answer(
                "Немає доступу до куща.",
                show_alert=True,
            )

            return

        bushes = await query_network_bushes(
            data=data
        )

        bush = next(
            (
                item
                for item in bushes
                if object_id(item)
                == bush_id
            ),
            None,
        )

        name = first_attr(
            bush,
            "name",
            "title",
            default=(
                f"Кущ #{bush_id}"
            ),
        )

        await state.set_state(
            InviteStates.creating
        )

        await state.update_data(
            invite_type="bush",
            invite_target_id=bush_id,
            invite_expiration="1d",
            invite_single_use=True,
        )

        await safe_edit(
            callback,
            text=(
                "🌿 <b>Invite для куща</b>\n\n"
                f"{escape(str(name))}\n\n"
                "Це запрошення створить "
                "доступ рівня Лева.\n\n"
                "Налаштуйте invite:"
            ),
            reply_markup=(
                build_keyboard(
                    bush_invite_create_keyboard,

                    bush_id=bush_id,

                    target_id=bush_id,
                )
            ),
        )

        return

    items = await build_bush_items(
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
    )

    await safe_edit(
        callback,
        text=(
            "🌿 <b>Оберіть кущ</b>"
        ),
        reply_markup=(
            build_keyboard(
                invite_bush_selector_keyboard,

                bushes=page_items,

                page=page,

                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# DIRECTOR INVITE
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.SELECT_ROLE
    )
)
async def director_invite_callback(
    callback: CallbackQuery,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Director invite.
    """

    user = get_database_user(
        data
    )

    if not is_root_admin(
        user
    ):
        await callback.answer(
            "Invite директора може "
            "створити лише ROOT ADMIN.",
            show_alert=True,
        )

        return

    await callback.answer()

    await state.set_state(
        InviteStates.creating
    )

    await state.update_data(
        invite_type="director",
        invite_target_id=0,
        invite_expiration="1d",
        invite_single_use=True,
    )

    await safe_edit(
        callback,
        text=(
            "🏢 <b>Invite директора</b>\n\n"
            "Запрошення дасть "
            "мережевий доступ із роллю "
            "<b>DIRECTOR</b>.\n\n"
            "Налаштуйте invite:"
        ),
        reply_markup=(
            build_keyboard(
                director_invite_create_keyboard
            )
        ),
    )


# =========================================================
# EXPIRATION BUTTON
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.EXPIRATION
    )
)
async def invite_expiration_menu_callback(
    callback: CallbackQuery,
    callback_data: InviteUICallback,
    state: FSMContext,
) -> None:
    """
    Вибір expiration.
    """

    await callback.answer()

    current = await state.get_data()

    target_id = (
        callback_data.target_id
        or to_int(
            current.get(
                "invite_target_id"
            )
        )
    )

    await safe_edit(
        callback,
        text=(
            "⏳ <b>Термін дії invite</b>\n\n"
            "Оберіть, скільки часу "
            "посилання буде активним:"
        ),
        reply_markup=(
            build_keyboard(
                invite_expiration_keyboard,

                target_id=target_id,
            )
        ),
    )


# =========================================================
# RAW EXPIRATION CALLBACK
# =========================================================
#
# keyboards/invites.py використовує:
#
#     iexp:<value>:<target_id>
#
# Це НЕ CallbackData class,
# тому парсимо вручну.
# =========================================================


@router.callback_query(
    F.data.startswith(
        "iexp:"
    )
)
async def raw_invite_expiration_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    iexp:7d:123
    """

    raw = (
        callback.data
        or ""
    )

    parts = raw.split(
        ":"
    )

    if len(parts) < 3:
        await callback.answer(
            "Невірна кнопка.",
            show_alert=True,
        )

        return

    expiration = (
        parts[1]
        .strip()
        .lower()
    )

    target_id = to_int(
        parts[2]
    )

    try:
        expiration_delta(
            expiration
        )

    except ValueError:
        await callback.answer(
            "Невідомий термін.",
            show_alert=True,
        )

        return

    await state.set_state(
        InviteStates.creating
    )

    await state.update_data(
        invite_expiration=expiration,
        invite_target_id=(
            target_id
            or to_int(
                (
                    await state.get_data()
                ).get(
                    "invite_target_id"
                )
            )
        ),
    )

    await callback.answer(
        "Термін змінено ✅"
    )

    state_data = await state.get_data()

    await show_create_summary(
        callback,
        state_data=state_data,
    )


# =========================================================
# SINGLE USE
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.SINGLE_USE
    )
)
async def single_use_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    One-time invite.
    """

    await state.set_state(
        InviteStates.creating
    )

    await state.update_data(
        invite_single_use=True
    )

    await callback.answer(
        "Одноразове ✅"
    )

    await show_create_summary(
        callback,
        state_data=(
            await state.get_data()
        ),
    )


# =========================================================
# MULTI USE
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.MULTI_USE
    )
)
async def multi_use_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """
    Multi-use invite.
    """

    await state.set_state(
        InviteStates.creating
    )

    await state.update_data(
        invite_single_use=False
    )

    await callback.answer(
        "Багаторазове ✅"
    )

    await show_create_summary(
        callback,
        state_data=(
            await state.get_data()
        ),
    )


# =========================================================
# CREATE SUMMARY
# =========================================================


async def show_create_summary(
    callback: CallbackQuery,
    *,
    state_data: dict[str, Any],
) -> None:
    """
    Показує поточні налаштування invite.
    """

    invite_type = str(
        state_data.get(
            "invite_type",
            "store",
        )
    )

    target_id = to_int(
        state_data.get(
            "invite_target_id"
        )
    )

    expiration = str(
        state_data.get(
            "invite_expiration",
            "1d",
        )
    )

    single_use = bool(
        state_data.get(
            "invite_single_use",
            True,
        )
    )

    type_titles = {
        "store":
            "🏪 ТТ",

        "bush":
            "🌿 Кущ",

        "director":
            "🏢 Директор",
    }

    lines = [
        "🔗 <b>Налаштування invite</b>",
        "",
        (
            "Тип: "
            f"<b>{type_titles.get(invite_type, invite_type)}</b>"
        ),
    ]

    if target_id > 0:
        lines.append(
            "Target ID: "
            f"<code>{target_id}</code>"
        )

    lines.extend(
        [
            (
                "⏳ Термін: "
                f"<b>{expiration_title(expiration)}</b>"
            ),
            (
                "🔢 Використання: "
                f"<b>{'одноразове' if single_use else 'багаторазове'}</b>"
            ),
            "",
            "Створити посилання?",
        ]
    )

    if invite_type == "store":
        markup = build_keyboard(
            store_invite_create_keyboard,

            store_id=target_id,

            target_id=target_id,
        )

    elif invite_type == "bush":
        markup = build_keyboard(
            bush_invite_create_keyboard,

            bush_id=target_id,

            target_id=target_id,
        )

    else:
        markup = build_keyboard(
            director_invite_create_keyboard
        )

    await safe_edit(
        callback,
        text="\n".join(
            lines
        ),
        reply_markup=markup,
    )


# =========================================================
# CREATE
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.CREATE
    )
)
async def invite_create_callback(
    callback: CallbackQuery,
    callback_data: InviteUICallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Фактичне створення invite.
    """

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        await callback.answer(
            "Немає доступу.",
            show_alert=True,
        )

        return

    state_data = await state.get_data()

    invite_type = str(
        state_data.get(
            "invite_type",
            ""
        )
    )

    if not invite_type:
        await callback.answer(
            "Тип invite втрачено. "
            "Почніть створення заново.",
            show_alert=True,
        )

        return

    target_id = (
        callback_data.target_id
        or to_int(
            state_data.get(
                "invite_target_id"
            )
        )
    )

    expiration = str(
        state_data.get(
            "invite_expiration",
            "1d",
        )
    )

    single_use = bool(
        state_data.get(
            "invite_single_use",
            True,
        )
    )

    # Director invite only ROOT.
    if (
        invite_type
        == "director"
        and not is_root_admin(
            user
        )
    ):
        await callback.answer(
            "Invite директора може "
            "створити лише ROOT ADMIN.",
            show_alert=True,
        )

        return

    await callback.answer(
        "Створюю invite…"
    )

    try:
        result = await create_invite(
            invite_type=invite_type,
            target_id=target_id,
            expiration=expiration,
            single_use=single_use,
            actor=user,
            data=data,
        )

    except Exception:
        logger.exception(
            "Invite creation failed"
        )

        await safe_edit(
            callback,
            text=(
                "❌ <b>Не вдалося "
                "створити invite.</b>\n\n"
                "Спробуйте ще раз."
            ),
            reply_markup=(
                invite_create_cancel_keyboard()
            ),
        )

        return

    if not invite_created_successfully(
        result
    ):
        await safe_edit(
            callback,
            text=(
                "❌ InviteService "
                "не підтвердив створення."
            ),
            reply_markup=(
                invite_create_cancel_keyboard()
            ),
        )

        return

    link = await build_deep_link(
        callback=callback,
        result=result,
    )

    identifier = invite_id(
        result
    )

    await state.clear()

    lines = [
        "✅ <b>Invite створено!</b>",
        "",
        (
            "Тип: "
            f"<b>{escape(invite_type.upper())}</b>"
        ),
        (
            "Термін: "
            f"<b>{escape(expiration_title(expiration))}</b>"
        ),
        (
            "Використання: "
            f"<b>{'1 раз' if single_use else 'багаторазове'}</b>"
        ),
    ]

    if link:
        lines.extend(
            [
                "",
                "🔗 <b>Посилання:</b>",
                f"<code>{escape(link)}</code>",
            ]
        )

    await safe_edit(
        callback,
        text="\n".join(
            lines
        ),
        reply_markup=(
            build_keyboard(
                created_invite_keyboard,

                invite_id=identifier,

                url=link,

                invite_url=link,

                link=link,
            )
        ),
    )


# =========================================================
# LIST
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.LIST
    )
)
async def invite_list_callback(
    callback: CallbackQuery,
    callback_data: InviteUICallback,
    **data: Any,
) -> None:
    """
    Список invite.
    """

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        return

    await callback.answer()

    invites = await list_invites(
        actor=user,
        data=data,
    )

    items = [
        build_invite_list_item(
            invite
        )
        for invite in invites
    ]

    # Активні першими.
    status_order = {
        InviteStatus.ACTIVE: 0,
        InviteStatus.USED: 1,
        InviteStatus.EXPIRED: 2,
        InviteStatus.REVOKED: 3,
    }

    items.sort(
        key=lambda item: (
            status_order.get(
                first_attr(
                    item,
                    "status",
                    default=(
                        InviteStatus.ACTIVE
                    ),
                ),
                99,
            ),
            -to_int(
                first_attr(
                    item,
                    "invite_id",
                    default=0,
                )
            ),
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

    active_count = sum(
        1
        for item in items
        if first_attr(
            item,
            "status",
        )
        == InviteStatus.ACTIVE
    )

    await safe_edit(
        callback,
        text=(
            "🔗 <b>Запрошення</b>\n\n"
            f"Усього: <b>{len(items)}</b>\n"
            f"Активних: <b>{active_count}</b>"
        ),
        reply_markup=(
            build_keyboard(
                active_invites_keyboard,

                invites=page_items,

                items=page_items,

                page=page,

                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# VIEW
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.VIEW
    )
)
async def invite_view_callback(
    callback: CallbackQuery,
    callback_data: InviteUICallback,
    **data: Any,
) -> None:
    """
    Invite card.
    """

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        return

    await callback.answer()

    invite = await get_invite(
        invite_id_value=(
            callback_data.invite_id
        ),
        actor=user,
        data=data,
    )

    if invite is None:
        await callback.answer(
            "Invite не знайдено.",
            show_alert=True,
        )

        return

    status = get_invite_status(
        invite
    )

    if status == InviteStatus.USED:
        markup = build_keyboard(
            invite_used_keyboard,

            invite_id=(
                callback_data.invite_id
            ),
        )

    elif status == InviteStatus.EXPIRED:
        markup = build_keyboard(
            invite_expired_keyboard,

            invite_id=(
                callback_data.invite_id
            ),
        )

    elif status == InviteStatus.REVOKED:
        markup = build_keyboard(
            invite_revoked_keyboard,

            invite_id=(
                callback_data.invite_id
            ),
        )

    else:
        markup = build_keyboard(
            invite_card_keyboard,

            invite_id=(
                callback_data.invite_id
            ),

            invite=invite,
        )

    await safe_edit(
        callback,
        text=build_invite_card_text(
            invite
        ),
        reply_markup=markup,
    )


# =========================================================
# REVOKE REQUEST
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.CANCEL
    )
)
async def invite_cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Скасування create flow.
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

    await show_invites_menu(
        callback,
        user=user,
        data=data,
    )


# =========================================================
# LEGACY REVOKE
# =========================================================


@router.callback_query(
    InviteCallback.filter(
        F.action
        == InviteAction.REVOKE
    )
)
async def legacy_revoke_request(
    callback: CallbackQuery,
    callback_data: InviteCallback,
    **data: Any,
) -> None:
    """
    Legacy InviteCallback revoke.
    """

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        return

    await callback.answer()

    await safe_edit(
        callback,
        text=(
            "🚫 <b>Відкликати invite?</b>\n\n"
            "Після цього посилання "
            "перестане працювати."
        ),
        reply_markup=(
            build_keyboard(
                revoke_invite_confirmation_keyboard,

                invite_id=(
                    callback_data.invite_id
                ),
            )
        ),
    )


# =========================================================
# REVOKE CONFIRM
# =========================================================
#
# Якщо revoke confirmation keyboard
# використовує InviteUICallback.VIEW/...
# конкретна кнопка буде підключена
# після фінального import-тесту.
#
# Для сумісності також ловимо
# InviteUIAction.CREATE з invite_id
# ТІЛЬКИ коли create FSM не активний
# не будемо — це було б двозначно.
#
# Тому основний revoke шлях лишаємо
# через legacy InviteCallback.REVOKE,
# який уже є у callbacks.py.
# =========================================================


async def execute_revoke(
    callback: CallbackQuery,
    *,
    invite_id_value: int,
    data: dict[str, Any],
) -> None:
    """
    Виконує revoke.
    """

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        return

    success = await revoke_invite(
        invite_id_value=(
            invite_id_value
        ),
        actor=user,
        data=data,
    )

    if not success:
        await callback.answer(
            "Не вдалося відкликати invite.",
            show_alert=True,
        )

        return

    await callback.answer(
        "Invite відкликано ✅"
    )

    await safe_edit(
        callback,
        text=(
            "🚫 <b>Invite відкликано.</b>\n\n"
            "Посилання більше "
            "не може бути використане."
        ),
        reply_markup=(
            build_keyboard(
                invite_revoked_keyboard,

                invite_id=(
                    invite_id_value
                ),
            )
        ),
    )


# =========================================================
# LEGACY CREATE -> NEW INVITE UI
# =========================================================


@router.callback_query(
    InviteCallback.filter(
        F.action == InviteAction.STORE
    )
)
async def legacy_store_invite_callback(
    callback: CallbackQuery,
    callback_data: InviteCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    ????? ?????? STORE ??????????
    ?? ????? Invite UI.
    """

    modern_callback = InviteUICallback(
        action=InviteUIAction.SELECT_STORE,
        target_id=callback_data.target_id,
        invite_id=0,
        page=0,
    )

    await select_store_callback(
        callback,
        modern_callback,
        state,
        **data,
    )


@router.callback_query(
    InviteCallback.filter(
        F.action == InviteAction.BUSH
    )
)
async def legacy_bush_invite_callback(
    callback: CallbackQuery,
    callback_data: InviteCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    ????? ?????? BUSH ??????????
    ?? ????? Invite UI.
    """

    modern_callback = InviteUICallback(
        action=InviteUIAction.SELECT_BUSH,
        target_id=callback_data.target_id,
        invite_id=0,
        page=0,
    )

    await select_bush_callback(
        callback,
        modern_callback,
        state,
        **data,
    )


@router.callback_query(
    InviteCallback.filter(
        F.action == InviteAction.DIRECTOR
    )
)
async def legacy_director_invite_callback(
    callback: CallbackQuery,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    ????? ?????? DIRECTOR ????????????
    ?? ????? Invite UI.
    """

    await director_invite_callback(
        callback,
        state,
        **data,
    )


# =========================================================
# LEGACY MENU
# =========================================================


@router.callback_query(
    InviteCallback.filter(
        F.action
        == InviteAction.MENU
    )
)
async def legacy_invite_menu_callback(
    callback: CallbackQuery,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Compatibility.
    """

    await callback.answer()

    await state.clear()

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        return

    await show_invites_menu(
        callback,
        user=user,
        data=data,
    )


# =========================================================
# LEGACY LIST
# =========================================================


@router.callback_query(
    InviteCallback.filter(
        F.action
        == InviteAction.LIST
    )
)
async def legacy_invite_list_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Legacy list -> new UI.
    """

    user = get_database_user(
        data
    )

    if not can_manage_invites(
        user
    ):
        return

    await callback.answer()

    invites = await list_invites(
        actor=user,
        data=data,
    )

    items = [
        build_invite_list_item(
            invite
        )
        for invite in invites
    ]

    (
        page_items,
        page,
        total_pages,
    ) = paginate(
        items,
        page=0,
    )

    await safe_edit(
        callback,
        text=(
            "🔗 <b>Запрошення</b>\n\n"
            f"Усього: <b>{len(items)}</b>"
        ),
        reply_markup=(
            build_keyboard(
                active_invites_keyboard,

                invites=page_items,

                items=page_items,

                page=page,

                total_pages=total_pages,
            )
        ),
    )


# =========================================================
# BACK
# =========================================================


@router.callback_query(
    InviteUICallback.filter(
        F.action
        == InviteUIAction.BACK
    )
)
async def invite_back_callback(
    callback: CallbackQuery,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Back -> invite menu.
    """

    await callback.answer()

    await state.clear()

    user = get_database_user(
        data
    )

    if user is None:
        return

    await show_invites_menu(
        callback,
        user=user,
        data=data,
    )


# =========================================================
# UNKNOWN NEW UI
# =========================================================


@router.callback_query(
    InviteUICallback.filter()
)
async def unknown_invite_ui_callback(
    callback: CallbackQuery,
) -> None:
    """
    Старий InviteUICallback.
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
    "MANAGER_ROLES",

    "InviteStates",

    "filter_kwargs",
    "enum_value",
    "normalize_role",
    "can_manage_invites",
    "paginate",

    "get_invite_service",
    "flush_changes",

    "access_context",
    "has_network_access",
    "accessible_bush_ids",
    "accessible_store_ids",
    "can_access_bush",
    "can_access_store",

    "expiration_delta",
    "expiration_title",

    "invite_type_value",
    "service_scope_for_type",
    "role_for_type",

    "build_store_items",
    "build_bush_items",

    "invite_object",
    "invite_id",
    "invite_token",
    "invite_url",
    "invite_created_successfully",

    "build_deep_link",

    "create_invite",
    "list_invites",
    "get_invite",

    "get_invite_status",
    "build_invite_list_item",

    "format_datetime",
    "build_invite_card_text",

    "revoke_invite",

    "show_invites_menu",
    "show_create_summary",

    "execute_revoke",
]