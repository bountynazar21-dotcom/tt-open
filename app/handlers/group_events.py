from __future__ import annotations

import inspect
import logging
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    Message,
)

from app.database.models.user import (
    User as DatabaseUser,
)
from app.handlers.common import (
    get_database_user,
    safe_edit,
    user_role_name,
)
from app.handlers.opening import (
    call_method,
    first_attr,
    get_service,
    to_bool,
    to_int,
)
from app.keyboards import (
    GroupCallback,
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="group_events",
)


# =========================================================
# CONSTANTS
# =========================================================


GROUP_CHAT_TYPES = {
    "group",
    "supergroup",
}


ACTIVE_MEMBER_STATUSES = {
    "member",
    "administrator",
    "creator",
    "restricted",
}


REMOVED_MEMBER_STATUSES = {
    "left",
    "kicked",
}


GROUP_MANAGER_ROLES = {
    "ROOT_ADMIN",
    "DIRECTOR",
    "BUSH_ADMIN",
}


NETWORK_MANAGER_ROLES = {
    "ROOT_ADMIN",
}


TOPIC_TYPES = {
    "opening",
    "closing",
    "alerts",
    "reports",
    "system",
}


TOPIC_LABELS = {
    "opening":
        "🌅 Відкриття",

    "closing":
        "🌙 Закриття",

    "alerts":
        "🚨 Тривоги",

    "reports":
        "📊 Звіти",

    "system":
        "⚙️ Система",
}


# =========================================================
# GENERIC HELPERS
# =========================================================


def enum_text(
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


def role_name(
    user: DatabaseUser | None,
) -> str:
    """
    Поточна роль.
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


def is_group_chat(
    value: Any,
) -> bool:
    """
    group / supergroup.
    """

    chat = first_attr(
        value,
        "chat",
        default=value,
    )

    chat_type = enum_text(
        first_attr(
            chat,
            "type",
            default="",
        )
    )

    return (
        chat_type
        in GROUP_CHAT_TYPES
    )


def command_argument(
    message: Message,
) -> str | None:
    """
    /group_bush 12
                ^^
    """

    text = (
        message.text
        or ""
    ).strip()

    if not text:
        return None

    parts = text.split(
        maxsplit=1
    )

    if len(parts) < 2:
        return None

    value = parts[1].strip()

    return (
        value
        if value
        else None
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

    explicit = first_attr(
        result,
        "success",
        "created",
        "updated",
        "registered",
        "changed",
        default=None,
    )

    if explicit is not None:
        return to_bool(
            explicit,
            default=False,
        )

    return True


def operation_message(
    result: Any,
) -> str | None:
    """
    Message від GroupService.
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


def filter_kwargs(
    method: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Передає тільки підтримувані kwargs.
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
        if key
        in signature.parameters
    }


async def invoke(
    method: Any,
    payload: dict[str, Any],
) -> Any:
    """
    Sync / async callable.
    """

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

    return result


# =========================================================
# SERVICES
# =========================================================


def get_group_service(
    data: dict[str, Any],
) -> Any | None:
    """
    GroupService.
    """

    return get_service(
        data,
        "groups",
        "group",
    )


async def flush_changes(
    data: dict[str, Any],
) -> None:
    """
    Flush поточної транзакції.
    """

    repositories = data.get(
        "repositories"
    )

    if repositories is not None:
        flush = getattr(
            repositories,
            "flush",
            None,
        )

        if callable(
            flush
        ):
            result = flush()

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

    flush = getattr(
        session,
        "flush",
        None,
    )

    if callable(
        flush
    ):
        result = flush()

        if inspect.isawaitable(
            result
        ):
            await result


# =========================================================
# ACCESS
# =========================================================


def accessible_bush_ids(
    data: dict[str, Any],
) -> set[int]:
    """
    Кущі з AccessMiddleware.
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


def has_network_access(
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> bool:
    """
    Network access.
    """

    if user is None:
        return False

    if role_name(
        user
    ) == "ROOT_ADMIN":
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


def can_manage_groups(
    user: DatabaseUser | None,
) -> bool:
    """
    ROOT / Director / Bush Admin.
    """

    return (
        role_name(
            user
        )
        in GROUP_MANAGER_ROLES
    )


def can_register_network_group(
    user: DatabaseUser | None,
) -> bool:
    """
    Головну network group
    задає ROOT ADMIN.
    """

    return (
        role_name(
            user
        )
        in NETWORK_MANAGER_ROLES
    )


def can_register_bush_group(
    *,
    user: DatabaseUser | None,
    bush_id: int,
    data: dict[str, Any],
) -> bool:
    """
    Доступ до bush group.
    """

    if user is None:
        return False

    role = role_name(
        user
    )

    if role == "ROOT_ADMIN":
        return True

    if role == "DIRECTOR":
        return (
            has_network_access(
                user,
                data,
            )
            or bush_id
            in accessible_bush_ids(
                data
            )
        )

    if role == "BUSH_ADMIN":
        return (
            bush_id
            in accessible_bush_ids(
                data
            )
        )

    return False


# =========================================================
# GROUP RESULT HELPERS
# =========================================================


def group_object(
    result: Any,
) -> Any:
    """
    Wrapper -> group.
    """

    return first_attr(
        result,
        "group",
        "telegram_group",
        "record",
        default=result,
    )


def group_id(
    result: Any,
) -> int:
    """
    Internal DB group ID.
    """

    group = group_object(
        result
    )

    return to_int(
        first_attr(
            group,
            "id",
            "group_id",
            default=0,
        )
    )


def group_chat_id(
    result: Any,
) -> int:
    """
    Telegram chat_id.
    """

    group = group_object(
        result
    )

    return to_int(
        first_attr(
            group,
            "chat_id",
            "telegram_chat_id",
            default=0,
        )
    )


def group_scope(
    result: Any,
) -> str:
    """
    network / bush / unassigned.
    """

    group = group_object(
        result
    )

    return enum_text(
        first_attr(
            group,
            "scope",
            "group_scope",
            "type",
            default="",
        )
    )


def group_bush_id(
    result: Any,
) -> int:
    """
    bush_id.
    """

    group = group_object(
        result
    )

    return to_int(
        first_attr(
            group,
            "bush_id",
            default=0,
        )
    )


# =========================================================
# GET GROUP BY CHAT
# =========================================================


async def get_group_by_chat_id(
    *,
    chat_id: int,
    data: dict[str, Any],
) -> Any | None:
    """
    Registered group by Telegram chat_id.
    """

    service = get_group_service(
        data
    )

    if service is None:
        return None

    payload = {
        "chat_id":
            chat_id,

        "telegram_chat_id":
            chat_id,
    }

    for method_name in (
        "get_by_chat_id",
        "get_group_by_chat_id",
        "get_chat_group",
        "find_by_chat_id",
        "get_group",
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
            result = await invoke(
                method,
                payload,
            )

        except Exception:
            continue

        if result is not None:
            return group_object(
                result
            )

    return None


# =========================================================
# REGISTER GROUP
# =========================================================


async def register_group(
    *,
    chat_id: int,
    title: str | None,
    username: str | None,
    is_forum: bool,
    scope: str,
    bush_id: int,
    actor: DatabaseUser | None,
    data: dict[str, Any],
) -> Any:
    """
    Register / update Telegram group.
    """

    service = get_group_service(
        data
    )

    if service is None:
        raise RuntimeError(
            "GroupService недоступний."
        )

    payload = {
        # telegram
        "chat_id":
            chat_id,

        "telegram_chat_id":
            chat_id,

        "title":
            title,

        "name":
            title,

        "username":
            username,

        "is_forum":
            is_forum,

        # scope
        "scope":
            scope,

        "group_scope":
            scope,

        "type":
            scope,

        "bush_id":
            (
                bush_id
                if bush_id > 0
                else None
            ),

        # actor
        "actor":
            actor,

        "user":
            actor,

        "actor_id":
            (
                getattr(
                    actor,
                    "id",
                    None,
                )
                if actor is not None
                else None
            ),

        # status
        "is_active":
            True,

        "active":
            True,
    }

    if scope == "network":
        methods = (
            "register_network_group",
            "set_network_group",
            "bind_network_group",
            "register_group",
            "upsert_group",
            "ensure_group",
        )

    elif scope == "bush":
        methods = (
            "register_bush_group",
            "set_bush_group",
            "bind_bush_group",
            "register_group",
            "upsert_group",
            "ensure_group",
        )

    else:
        methods = (
            "register_group",
            "upsert_group",
            "ensure_group",
            "save_group",
            "connect_group",
        )

    last_error: Exception | None = None

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
            result = await invoke(
                method,
                payload,
            )

            await flush_changes(
                data
            )

            return result

        except Exception as error:
            last_error = error

            logger.exception(
                "Group registration failed: "
                "method=%s chat_id=%s",
                method_name,
                chat_id,
            )

            continue

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        "Метод реєстрації групи "
        "у GroupService не знайдено."
    )


# =========================================================
# DEACTIVATE GROUP
# =========================================================


async def deactivate_group(
    *,
    chat_id: int,
    data: dict[str, Any],
) -> bool:
    """
    Бота видалили з групи.
    """

    service = get_group_service(
        data
    )

    if service is None:
        return False

    payload = {
        "chat_id":
            chat_id,

        "telegram_chat_id":
            chat_id,

        "is_active":
            False,

        "active":
            False,
    }

    for method_name in (
        "deactivate_group",
        "mark_removed",
        "unregister_group",
        "disconnect_group",
        "deactivate_by_chat_id",
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
            result = await invoke(
                method,
                payload,
            )

        except Exception:
            logger.exception(
                "Failed deactivating group "
                "chat_id=%s",
                chat_id,
            )

            continue

        await flush_changes(
            data
        )

        return operation_success(
            result
        )

    return False


# =========================================================
# TOPICS
# =========================================================


async def set_group_topic(
    *,
    chat_id: int,
    topic_type: str,
    message_thread_id: int,
    actor: DatabaseUser,
    data: dict[str, Any],
) -> Any:
    """
    Зберігає topic групи.

    topic_type:
        opening
        closing
        alerts
        reports
        system
    """

    normalized = (
        topic_type
        .strip()
        .lower()
    )

    if normalized not in TOPIC_TYPES:
        raise ValueError(
            f"Unknown topic type: "
            f"{topic_type}"
        )

    service = get_group_service(
        data
    )

    if service is None:
        raise RuntimeError(
            "GroupService недоступний."
        )

    payload = {
        "chat_id":
            chat_id,

        "telegram_chat_id":
            chat_id,

        "topic_type":
            normalized,

        "type":
            normalized,

        "topic":
            normalized,

        "message_thread_id":
            message_thread_id,

        "thread_id":
            message_thread_id,

        "topic_id":
            message_thread_id,

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

    last_error: Exception | None = None

    for method_name in (
        "set_topic",
        "register_topic",
        "save_topic",
        "set_group_topic",
        "update_topic",
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
            result = await invoke(
                method,
                payload,
            )

            await flush_changes(
                data
            )

            return result

        except Exception as error:
            last_error = error

            logger.exception(
                "Failed saving group topic: "
                "chat_id=%s topic=%s",
                chat_id,
                normalized,
            )

            continue

    if last_error is not None:
        raise last_error

    raise RuntimeError(
        "Метод збереження topic "
        "не знайдено."
    )


# =========================================================
# BOT PERMISSIONS
# =========================================================


async def get_bot_permissions(
    message: Message,
) -> dict[str, Any]:
    """
    Перевіряє статус бота у групі.
    """

    result = {
        "status":
            "unknown",

        "is_admin":
            False,

        "can_manage_topics":
            False,

        "can_delete_messages":
            False,

        "can_invite_users":
            False,
    }

    try:
        bot = await message.bot.get_me()

        member = (
            await message.bot.get_chat_member(
                chat_id=(
                    message.chat.id
                ),
                user_id=(
                    bot.id
                ),
            )
        )

    except Exception:
        logger.exception(
            "Failed checking bot permissions: "
            "chat_id=%s",
            message.chat.id,
        )

        return result

    status = enum_text(
        getattr(
            member,
            "status",
            None,
        )
    )

    result[
        "status"
    ] = status

    result[
        "is_admin"
    ] = (
        status
        in {
            "administrator",
            "creator",
        }
    )

    for attr in (
        "can_manage_topics",
        "can_delete_messages",
        "can_invite_users",
    ):
        result[
            attr
        ] = bool(
            getattr(
                member,
                attr,
                False,
            )
        )

    return result


# =========================================================
# GROUP STATUS TEXT
# =========================================================


async def build_group_status_text(
    message: Message,
    *,
    data: dict[str, Any],
) -> str:
    """
    Поточний статус групи.
    """

    registered = await get_group_by_chat_id(
        chat_id=(
            message.chat.id
        ),
        data=data,
    )

    permissions = await get_bot_permissions(
        message
    )

    lines = [
        "💬 <b>Статус Telegram-групи</b>",
        "",
        (
            "Назва: "
            f"<b>{escape(message.chat.title or '—')}</b>"
        ),
        (
            "Chat ID: "
            f"<code>{message.chat.id}</code>"
        ),
        (
            "Forum Topics: "
            f"<b>{'так' if bool(message.chat.is_forum) else 'ні'}</b>"
        ),
        "",
        (
            "🤖 Статус бота: "
            f"<b>{escape(permissions['status'])}</b>"
        ),
        (
            "🛡 Адміністратор: "
            f"<b>{'так' if permissions['is_admin'] else 'ні'}</b>"
        ),
    ]

    if bool(
        message.chat.is_forum
    ):
        lines.append(
            "🧵 Manage Topics: "
            f"<b>{'так' if permissions['can_manage_topics'] else 'ні'}</b>"
        )

    lines.append(
        ""
    )

    if registered is None:
        lines.extend(
            [
                "⚠️ <b>Група ще не прив'язана "
                "до системи.</b>",
                "",
                "Для головної групи:",
                "<code>/group_network</code>",
                "",
                "Для куща:",
                "<code>/group_bush ID_КУЩА</code>",
            ]
        )

        return "\n".join(
            lines
        )

    scope = group_scope(
        registered
    )

    bush_id = group_bush_id(
        registered
    )

    lines.append(
        "✅ <b>Група зареєстрована.</b>"
    )

    if scope == "network":
        lines.append(
            "🌐 Тип: <b>головна група мережі</b>"
        )

    elif scope == "bush":
        lines.append(
            "🌿 Тип: <b>група куща</b>"
        )

        if bush_id > 0:
            lines.append(
                "Bush ID: "
                f"<code>{bush_id}</code>"
            )

    else:
        lines.append(
            "Тип: "
            f"<b>{escape(scope or 'не визначено')}</b>"
        )

    return "\n".join(
        lines
    )


# =========================================================
# MY_CHAT_MEMBER
# =========================================================


@router.my_chat_member()
async def bot_membership_changed(
    update: ChatMemberUpdated,
    **data: Any,
) -> None:
    """
    Telegram викликає цей event,
    коли статус САМОГО бота в чаті
    змінюється.

    Тут відстежуємо:
        - додали бота;
        - зробили адміном;
        - видалили;
        - заблокували.
    """

    if not is_group_chat(
        update
    ):
        return

    old_status = enum_text(
        update.old_chat_member.status
    )

    new_status = enum_text(
        update.new_chat_member.status
    )

    chat_id = update.chat.id

    logger.info(
        "Bot membership changed: "
        "chat_id=%s old=%s new=%s",
        chat_id,
        old_status,
        new_status,
    )

    # -----------------------------------------------------
    # BOT ADDED / RESTORED
    # -----------------------------------------------------

    became_active = (
        new_status
        in ACTIVE_MEMBER_STATUSES
        and old_status
        not in ACTIVE_MEMBER_STATUSES
    )

    if became_active:
        actor = get_database_user(
            data
        )

        try:
            # Спочатку просто запам'ятовуємо
            # сам факт підключення групи.
            await register_group(
                chat_id=chat_id,
                title=update.chat.title,
                username=update.chat.username,
                is_forum=bool(
                    update.chat.is_forum
                ),
                scope="unassigned",
                bush_id=0,
                actor=actor,
                data=data,
            )

        except Exception:
            # Відсутність generic registration
            # не повинна валити event.
            logger.exception(
                "Could not auto-register "
                "unassigned group: %s",
                chat_id,
            )

        try:
            await update.bot.send_message(
                chat_id=chat_id,
                text=(
                    "✅ <b>Бота підключено до групи.</b>\n\n"
                    f"Chat ID: <code>{chat_id}</code>\n\n"
                    "Тепер адміністратор може "
                    "прив'язати її до системи:\n\n"
                    "🌐 головна група — "
                    "<code>/group_network</code>\n"
                    "🌿 група куща — "
                    "<code>/group_bush ID_КУЩА</code>\n\n"
                    "Перевірка:\n"
                    "<code>/group_status</code>"
                ),
            )

        except Exception:
            logger.exception(
                "Failed sending group welcome: "
                "%s",
                chat_id,
            )

        return

    # -----------------------------------------------------
    # ADMIN STATUS CHANGED
    # -----------------------------------------------------

    if (
        new_status
        in ACTIVE_MEMBER_STATUSES
        and old_status
        in ACTIVE_MEMBER_STATUSES
        and new_status
        != old_status
    ):
        try:
            await register_group(
                chat_id=chat_id,
                title=update.chat.title,
                username=update.chat.username,
                is_forum=bool(
                    update.chat.is_forum
                ),
                scope=(
                    group_scope(
                        await get_group_by_chat_id(
                            chat_id=chat_id,
                            data=data,
                        )
                    )
                    or "unassigned"
                ),
                bush_id=(
                    group_bush_id(
                        await get_group_by_chat_id(
                            chat_id=chat_id,
                            data=data,
                        )
                    )
                ),
                actor=(
                    get_database_user(
                        data
                    )
                ),
                data=data,
            )

        except Exception:
            logger.exception(
                "Failed updating group metadata: "
                "%s",
                chat_id,
            )

        return

    # -----------------------------------------------------
    # BOT REMOVED
    # -----------------------------------------------------

    became_removed = (
        new_status
        in REMOVED_MEMBER_STATUSES
    )

    if became_removed:
        try:
            await deactivate_group(
                chat_id=chat_id,
                data=data,
            )

        except Exception:
            logger.exception(
                "Failed deactivating removed group: "
                "%s",
                chat_id,
            )


# =========================================================
# /GROUP_STATUS
# =========================================================


@router.message(
    Command(
        "group_status",
        "chat_id",
    ),
    F.chat.type.in_(
        {
            "group",
            "supergroup",
        }
    ),
)
async def group_status_command(
    message: Message,
    **data: Any,
) -> None:
    """
    Інформація про групу.
    """

    await message.answer(
        await build_group_status_text(
            message,
            data=data,
        )
    )


# =========================================================
# /GROUP_NETWORK
# =========================================================


@router.message(
    Command(
        "group_network"
    ),
    F.chat.type.in_(
        {
            "group",
            "supergroup",
        }
    ),
)
async def register_network_group_command(
    message: Message,
    **data: Any,
) -> None:
    """
    Реєструє поточну групу як
    головну network group.
    """

    user = get_database_user(
        data
    )

    if not can_register_network_group(
        user
    ):
        await message.answer(
            "⛔ Головну групу мережі "
            "може призначити лише "
            "ROOT ADMIN."
        )

        return

    try:
        result = await register_group(
            chat_id=message.chat.id,
            title=message.chat.title,
            username=message.chat.username,
            is_forum=bool(
                message.chat.is_forum
            ),
            scope="network",
            bush_id=0,
            actor=user,
            data=data,
        )

    except Exception:
        logger.exception(
            "Network group registration failed: "
            "%s",
            message.chat.id,
        )

        await message.answer(
            "❌ Не вдалося зареєструвати "
            "головну групу."
        )

        return

    if not operation_success(
        result
    ):
        await message.answer(
            "❌ "
            + escape(
                operation_message(
                    result
                )
                or "Групу не зареєстровано."
            )
        )

        return

    await message.answer(
        "✅ <b>Готово!</b>\n\n"
        "Ця Telegram-група тепер "
        "зареєстрована як "
        "<b>головна група мережі</b>.\n\n"
        f"Chat ID: <code>{message.chat.id}</code>"
    )


# =========================================================
# /GROUP_BUSH
# =========================================================


@router.message(
    Command(
        "group_bush"
    ),
    F.chat.type.in_(
        {
            "group",
            "supergroup",
        }
    ),
)
async def register_bush_group_command(
    message: Message,
    **data: Any,
) -> None:
    """
    /group_bush 12
    """

    user = get_database_user(
        data
    )

    if not can_manage_groups(
        user
    ):
        await message.answer(
            "⛔ Немає доступу до "
            "керування групами."
        )

        return

    argument = command_argument(
        message
    )

    bush_id = to_int(
        argument
    )

    if bush_id <= 0:
        await message.answer(
            "🌿 Вкажіть ID куща.\n\n"
            "Наприклад:\n"
            "<code>/group_bush 12</code>"
        )

        return

    if not can_register_bush_group(
        user=user,
        bush_id=bush_id,
        data=data,
    ):
        await message.answer(
            "⛔ У вас немає доступу "
            "до цього куща."
        )

        return

    try:
        result = await register_group(
            chat_id=message.chat.id,
            title=message.chat.title,
            username=message.chat.username,
            is_forum=bool(
                message.chat.is_forum
            ),
            scope="bush",
            bush_id=bush_id,
            actor=user,
            data=data,
        )

    except Exception:
        logger.exception(
            "Bush group registration failed: "
            "chat=%s bush=%s",
            message.chat.id,
            bush_id,
        )

        await message.answer(
            "❌ Не вдалося прив'язати "
            "групу до куща."
        )

        return

    if not operation_success(
        result
    ):
        await message.answer(
            "❌ "
            + escape(
                operation_message(
                    result
                )
                or "Операція не виконана."
            )
        )

        return

    await message.answer(
        "✅ <b>Групу куща підключено!</b>\n\n"
        f"🌿 Bush ID: <code>{bush_id}</code>\n"
        f"💬 Chat ID: <code>{message.chat.id}</code>\n\n"
        "Тепер сюди можна направляти "
        "сповіщення цього куща."
    )


# =========================================================
# TOPIC REGISTRATION COMMON
# =========================================================


async def register_current_topic(
    message: Message,
    *,
    topic_type: str,
    data: dict[str, Any],
) -> None:
    """
    Реєстрація поточного Telegram Topic.
    """

    user = get_database_user(
        data
    )

    if not can_manage_groups(
        user
    ):
        await message.answer(
            "⛔ Немає доступу до "
            "керування topics."
        )

        return

    registered = await get_group_by_chat_id(
        chat_id=message.chat.id,
        data=data,
    )

    if registered is None:
        await message.answer(
            "⚠️ Спочатку прив'яжіть "
            "цю групу до системи:\n\n"
            "<code>/group_network</code>\n"
            "або\n"
            "<code>/group_bush ID</code>"
        )

        return

    # -----------------------------------------------------
    # FORUM
    # -----------------------------------------------------

    if bool(
        message.chat.is_forum
    ):
        thread_id = to_int(
            message.message_thread_id
        )

        if thread_id <= 0:
            await message.answer(
                "⚠️ Цю команду потрібно "
                "надіслати <b>всередині "
                "потрібного Topic</b>."
            )

            return

    # -----------------------------------------------------
    # REGULAR GROUP
    # -----------------------------------------------------

    else:
        # 0 = основний чат без topic.
        thread_id = 0

    try:
        result = await set_group_topic(
            chat_id=message.chat.id,
            topic_type=topic_type,
            message_thread_id=thread_id,
            actor=user,
            data=data,
        )

    except Exception:
        logger.exception(
            "Topic registration failed: "
            "chat=%s thread=%s type=%s",
            message.chat.id,
            thread_id,
            topic_type,
        )

        await message.answer(
            "❌ Не вдалося зберегти Topic."
        )

        return

    if not operation_success(
        result
    ):
        await message.answer(
            "❌ "
            + escape(
                operation_message(
                    result
                )
                or "Topic не збережено."
            )
        )

        return

    label = TOPIC_LABELS.get(
        topic_type,
        topic_type,
    )

    await message.answer(
        "✅ <b>Topic підключено.</b>\n\n"
        f"Тип: <b>{escape(label)}</b>\n"
        f"Thread ID: <code>{thread_id}</code>"
    )


# =========================================================
# /TOPIC_OPENING
# =========================================================


@router.message(
    Command(
        "topic_opening"
    ),
    F.chat.type.in_(
        {
            "group",
            "supergroup",
        }
    ),
)
async def topic_opening_command(
    message: Message,
    **data: Any,
) -> None:
    await register_current_topic(
        message,
        topic_type="opening",
        data=data,
    )


# =========================================================
# /TOPIC_CLOSING
# =========================================================


@router.message(
    Command(
        "topic_closing"
    ),
    F.chat.type.in_(
        {
            "group",
            "supergroup",
        }
    ),
)
async def topic_closing_command(
    message: Message,
    **data: Any,
) -> None:
    await register_current_topic(
        message,
        topic_type="closing",
        data=data,
    )


# =========================================================
# /TOPIC_ALERTS
# =========================================================


@router.message(
    Command(
        "topic_alerts"
    ),
    F.chat.type.in_(
        {
            "group",
            "supergroup",
        }
    ),
)
async def topic_alerts_command(
    message: Message,
    **data: Any,
) -> None:
    await register_current_topic(
        message,
        topic_type="alerts",
        data=data,
    )


# =========================================================
# /TOPIC_REPORTS
# =========================================================


@router.message(
    Command(
        "topic_reports"
    ),
    F.chat.type.in_(
        {
            "group",
            "supergroup",
        }
    ),
)
async def topic_reports_command(
    message: Message,
    **data: Any,
) -> None:
    await register_current_topic(
        message,
        topic_type="reports",
        data=data,
    )


# =========================================================
# /TOPIC_SYSTEM
# =========================================================


@router.message(
    Command(
        "topic_system"
    ),
    F.chat.type.in_(
        {
            "group",
            "supergroup",
        }
    ),
)
async def topic_system_command(
    message: Message,
    **data: Any,
) -> None:
    await register_current_topic(
        message,
        topic_type="system",
        data=data,
    )


# =========================================================
# /GROUP_HELP
# =========================================================


@router.message(
    Command(
        "group_help"
    ),
    F.chat.type.in_(
        {
            "group",
            "supergroup",
        }
    ),
)
async def group_help_command(
    message: Message,
) -> None:
    """
    Шпаргалка адміністратора.
    """

    await message.answer(
        "⚙️ <b>Налаштування робочої групи</b>\n\n"
        "Перевірити групу:\n"
        "<code>/group_status</code>\n\n"
        "Головна група мережі:\n"
        "<code>/group_network</code>\n\n"
        "Група конкретного куща:\n"
        "<code>/group_bush 12</code>\n\n"
        "Якщо група використовує Topics, "
        "виконайте потрібну команду "
        "безпосередньо всередині Topic:\n\n"
        "🌅 <code>/topic_opening</code>\n"
        "🌙 <code>/topic_closing</code>\n"
        "🚨 <code>/topic_alerts</code>\n"
        "📊 <code>/topic_reports</code>\n"
        "⚙️ <code>/topic_system</code>"
    )


# =========================================================
# PRIVATE COMMAND PROTECTION
# =========================================================


@router.message(
    Command(
        "group_network",
        "group_bush",
        "group_status",
        "group_help",
        "topic_opening",
        "topic_closing",
        "topic_alerts",
        "topic_reports",
        "topic_system",
    )
)
async def group_command_outside_group(
    message: Message,
) -> None:
    """
    Якщо команду запустили в приваті.
    """

    if is_group_chat(
        message
    ):
        return

    await message.answer(
        "💬 Цю команду потрібно "
        "виконувати безпосередньо "
        "у робочій Telegram-групі."
    )


# =========================================================
# GROUP CALLBACK
# =========================================================


@router.callback_query(
    GroupCallback.filter()
)
async def group_callback_handler(
    callback: CallbackQuery,
    callback_data: GroupCallback,
    **data: Any,
) -> None:
    """
    У callbacks.py можуть бути різні
    GroupAction.

    Щоб файл не був жорстко прив'язаний
    до конкретного набору enum members,
    dispatch робимо через action.value.
    """

    action = enum_text(
        first_attr(
            callback_data,
            "action",
            default="",
        )
    )

    bush_id = to_int(
        first_attr(
            callback_data,
            "bush_id",
            "ref_id",
            default=0,
        )
    )

    # -----------------------------------------------------
    # NETWORK
    # -----------------------------------------------------

    if action in {
        "network",
        "network_group",
    }:
        await callback.answer()

        await safe_edit(
            callback,
            text=(
                "🌐 <b>Головна Telegram-група</b>\n\n"
                "1. Додайте бота в потрібну групу.\n"
                "2. Відкрийте цю групу.\n"
                "3. Виконайте команду:\n\n"
                "<code>/group_network</code>\n\n"
                "Перевірити підключення:\n"
                "<code>/group_status</code>"
            ),
            reply_markup=None,
        )

        return

    # -----------------------------------------------------
    # BUSH
    # -----------------------------------------------------

    if action in {
        "bush",
        "bush_group",
    }:
        await callback.answer()

        bush_hint = (
            f" {bush_id}"
            if bush_id > 0
            else " ID_КУЩА"
        )

        await safe_edit(
            callback,
            text=(
                "🌿 <b>Telegram-група куща</b>\n\n"
                "Додайте бота в потрібну групу "
                "та виконайте там:\n\n"
                f"<code>/group_bush{bush_hint}</code>\n\n"
                "Після цього можна налаштувати "
                "Topics командами "
                "<code>/topic_...</code>."
            ),
            reply_markup=None,
        )

        return

    # -----------------------------------------------------
    # TOPICS
    # -----------------------------------------------------

    if action in {
        "topics",
        "topic",
    }:
        await callback.answer()

        await safe_edit(
            callback,
            text=(
                "🧵 <b>Telegram Topics</b>\n\n"
                "Виконайте потрібну команду "
                "безпосередньо всередині Topic:\n\n"
                "🌅 <code>/topic_opening</code>\n"
                "🌙 <code>/topic_closing</code>\n"
                "🚨 <code>/topic_alerts</code>\n"
                "📊 <code>/topic_reports</code>\n"
                "⚙️ <code>/topic_system</code>"
            ),
            reply_markup=None,
        )

        return

    # -----------------------------------------------------
    # STATUS / REFRESH
    # -----------------------------------------------------

    if action in {
        "status",
        "refresh",
    }:
        await callback.answer(
            "Перевірку статусу виконайте "
            "командою /group_status "
            "у самій групі.",
            show_alert=True,
        )

        return

    # -----------------------------------------------------
    # FALLBACK
    # -----------------------------------------------------

    await callback.answer(
        "Налаштування групи виконується "
        "безпосередньо у Telegram-групі.",
        show_alert=False,
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "router",

    "GROUP_CHAT_TYPES",
    "ACTIVE_MEMBER_STATUSES",
    "REMOVED_MEMBER_STATUSES",

    "GROUP_MANAGER_ROLES",
    "NETWORK_MANAGER_ROLES",

    "TOPIC_TYPES",
    "TOPIC_LABELS",

    "enum_text",
    "role_name",
    "is_group_chat",
    "command_argument",

    "operation_success",
    "operation_message",

    "filter_kwargs",
    "invoke",

    "get_group_service",
    "flush_changes",

    "accessible_bush_ids",
    "has_network_access",

    "can_manage_groups",
    "can_register_network_group",
    "can_register_bush_group",

    "group_object",
    "group_id",
    "group_chat_id",
    "group_scope",
    "group_bush_id",

    "get_group_by_chat_id",

    "register_group",
    "deactivate_group",

    "set_group_topic",

    "get_bot_permissions",
    "build_group_status_text",

    "register_current_topic",
]