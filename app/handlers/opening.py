from __future__ import annotations

import inspect
import logging
from datetime import (
    date,
    datetime,
    time,
)
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

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
    get_access_context,
    get_database_user,
    get_primary_store_id,
    safe_edit,
)
from app.keyboards import (
    OpeningAction,
    OpeningCallback,
    StoreAction,
    StoreCallback,
    home_keyboard,
    inline_button,
)
from app.keyboards.store import (
    opening_already_done_keyboard,
    opening_late_keyboard,
    opening_prepare_keyboard,
    opening_status_keyboard,
    opening_success_keyboard,
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
    name="opening",
)


# =========================================================
# CONSTANTS
# =========================================================


KYIV_TZ = ZoneInfo(
    "Europe/Kyiv"
)


# =========================================================
# FSM
# =========================================================


class OpeningStates(
    StatesGroup
):
    """
    FSM відкриття.
    """

    waiting_manual_time = State()


# =========================================================
# GENERIC HELPERS
# =========================================================


def filter_kwargs(
    method: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Передає методу тільки ті kwargs,
    які підтримує його сигнатура.
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


async def call_method(
    method: Any,
    payload: dict[str, Any],
) -> Any:
    """
    Виклик sync/async методу.
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


def first_attr(
    target: Any,
    *names: str,
    default: Any = None,
) -> Any:
    """
    Повертає перший знайдений атрибут.
    """

    if target is None:
        return default

    if isinstance(
        target,
        dict,
    ):
        for name in names:
            if name in target:
                return target[name]

        return default

    for name in names:
        if hasattr(
            target,
            name,
        ):
            value = getattr(
                target,
                name,
            )

            if value is not None:
                return value

    return default


def to_int(
    value: Any,
    *,
    default: int = 0,
) -> int:
    """
    Нормалізація int.
    """

    if isinstance(
        value,
        bool,
    ):
        return default

    try:
        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def to_bool(
    value: Any,
    *,
    default: bool = False,
) -> bool:
    """
    Нормалізація bool.
    """

    if isinstance(
        value,
        bool,
    ):
        return value

    if value is None:
        return default

    normalized = (
        str(value)
        .strip()
        .lower()
    )

    if normalized in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "active",
        "success",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "n",
        "off",
        "inactive",
        "failed",
    }:
        return False

    return default


# =========================================================
# SERVICES
# =========================================================


def get_service(
    data: dict[str, Any],
    *names: str,
) -> Any | None:
    """
    Дістає сервіс із Services container.
    """

    services = data.get(
        "services"
    )

    if services is None:
        return None

    for name in names:
        try:
            service = getattr(
                services,
                name,
            )

        except Exception:
            continue

        if service is not None:
            return service

    return None


def get_opening_service(
    data: dict[str, Any],
) -> Any | None:
    return get_service(
        data,
        "opening",
        "openings",
    )


def get_store_service(
    data: dict[str, Any],
) -> Any | None:
    return get_service(
        data,
        "stores",
        "store",
    )


# =========================================================
# FLUSH
# =========================================================


async def flush_changes(
    data: dict[str, Any],
) -> None:
    """
    Flush поточної транзакції.
    Commit виконує DatabaseMiddleware.
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


def accessible_store_ids(
    data: dict[str, Any],
) -> set[int]:
    """
    Доступні ТТ поточного користувача.
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
        to_int(item)
        for item in values
        if to_int(item) > 0
    }


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

    return bool(
        getattr(
            context,
            "has_network_access",
            False,
        )
        if context
        else False
    )


def can_access_store(
    *,
    store_id: int,
    data: dict[str, Any],
) -> bool:
    """
    Базова перевірка доступу до ТТ.
    """

    if store_id <= 0:
        return False

    if has_network_access(
        data
    ):
        return True

    stores = accessible_store_ids(
        data
    )

    if store_id in stores:
        return True

    primary_store_id = (
        get_primary_store_id(
            data
        )
    )

    return (
        primary_store_id
        == store_id
    )


# =========================================================
# STORE IDS
# =========================================================


def resolve_store_id(
    *,
    callback_store_id: int,
    data: dict[str, Any],
) -> int | None:
    """
    Визначає ТТ.

    1. callback store_id
    2. primary_store_id
    3. якщо доступна лише одна ТТ
    """

    if callback_store_id > 0:
        return callback_store_id

    primary = get_primary_store_id(
        data
    )

    if primary:
        return primary

    stores = sorted(
        accessible_store_ids(
            data
        )
    )

    if len(stores) == 1:
        return stores[0]

    return None


# =========================================================
# STORE INFO
# =========================================================


async def load_store(
    *,
    store_id: int,
    data: dict[str, Any],
) -> Any | None:
    """
    Отримує Store.
    """

    service = get_store_service(
        data
    )

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
                return await call_method(
                    method,
                    {
                        "store_id": store_id,
                        "id": store_id,
                        "include_inactive": True,
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
        "stores",
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
                    "store_id": store_id,
                    "id": store_id,
                },
            )

        except Exception:
            continue

    return None


def store_title(
    store: Any,
    *,
    store_id: int,
) -> str:
    """
    Людська назва ТТ.
    """

    code = first_attr(
        store,
        "code",
        "store_code",
    )

    name = first_attr(
        store,
        "name",
        "title",
    )

    if code and name:
        return (
            f"{code} · {name}"
        )

    if code:
        return str(
            code
        )

    if name:
        return str(
            name
        )

    return (
        f"ТТ #{store_id}"
    )


# =========================================================
# MULTI STORE SELECT
# =========================================================


async def build_store_choices(
    *,
    store_ids: set[int],
    data: dict[str, Any],
) -> list[
    tuple[int, str]
]:
    """
    Назви ТТ для select keyboard.
    """

    result: list[
        tuple[int, str]
    ] = []

    for store_id in sorted(
        store_ids
    ):
        store = await load_store(
            store_id=store_id,
            data=data,
        )

        result.append(
            (
                store_id,
                store_title(
                    store,
                    store_id=store_id,
                ),
            )
        )

    return result


# =========================================================
# DATETIME
# =========================================================


def now_local(
) -> datetime:
    return datetime.now(
        KYIV_TZ
    )


def format_time(
    value: Any,
) -> str:
    """
    Форматує datetime/time/string.
    """

    if value is None:
        return "—"

    if isinstance(
        value,
        datetime,
    ):
        return value.astimezone(
            KYIV_TZ
        ).strftime(
            "%H:%M"
        )

    if isinstance(
        value,
        time,
    ):
        return value.strftime(
            "%H:%M"
        )

    text = str(
        value
    ).strip()

    if not text:
        return "—"

    return text


# =========================================================
# OPENING RESULT
# =========================================================


def result_success(
    result: Any,
) -> bool:
    """
    Чи успішний check-in.
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
        "registered",
        "is_success",
        default=None,
    )

    if explicit is not None:
        return to_bool(
            explicit,
            default=False,
        )

    return True


def result_already_exists(
    result: Any,
) -> bool:
    """
    Чи check-in уже існував.
    """

    value = first_attr(
        result,
        "already_exists",
        "already_opened",
        "duplicate",
        "was_existing",
        default=False,
    )

    return to_bool(
        value
    )


def result_lateness_minutes(
    result: Any,
) -> int:
    """
    Хвилини запізнення.
    """

    return max(
        0,
        to_int(
            first_attr(
                result,
                "lateness_minutes",
                "late_minutes",
                "delay_minutes",
                "minutes_late",
                default=0,
            )
        ),
    )


def result_checkin_time(
    result: Any,
) -> Any:
    return first_attr(
        result,
        "checked_in_at",
        "checkin_at",
        "opened_at",
        "actual_time",
        "created_at",
    )


def result_expected_time(
    result: Any,
) -> Any:
    return first_attr(
        result,
        "expected_time",
        "scheduled_time",
        "opening_time",
        "cluster_time",
    )


def result_deadline_time(
    result: Any,
) -> Any:
    return first_attr(
        result,
        "deadline_time",
        "control_deadline",
        "deadline",
    )


def result_message(
    result: Any,
) -> str | None:
    return first_attr(
        result,
        "message",
        "detail",
        "reason",
        "error",
    )


# =========================================================
# REGISTER OPENING
# =========================================================


async def register_opening(
    *,
    store_id: int,
    user: DatabaseUser,
    data: dict[str, Any],
    opened_at: datetime | None = None,
    manual: bool = False,
) -> Any:
    """
    Реєстрація відкриття через OpeningService.
    """

    service = get_opening_service(
        data
    )

    if service is None:
        raise RuntimeError(
            "OpeningService недоступний."
        )

    actual_time = (
        opened_at
        or now_local()
    )

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

        "opened_at": actual_time,
        "checked_in_at": actual_time,
        "checkin_at": actual_time,
        "actual_time": actual_time,

        "manual": manual,
        "is_manual": manual,
    }

    method_names = (
        (
            "manual_checkin",
            "correct_opening",
            "set_manual_opening",
            "manual_opening",
        )
        if manual
        else (
            "check_in",
            "checkin",
            "register_opening",
            "confirm_opening",
            "open_store",
            "create_checkin",
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
        "У OpeningService не знайдено "
        "метод реєстрації відкриття."
    )


# =========================================================
# GET TODAY STATUS
# =========================================================


async def get_opening_status(
    *,
    store_id: int,
    user: DatabaseUser | None,
    data: dict[str, Any],
) -> Any | None:
    """
    Поточний статус відкриття ТТ.
    """

    service = get_opening_service(
        data
    )

    if service is None:
        return None

    today = now_local().date()

    payload = {
        "store_id": store_id,

        "user": user,
        "actor": user,

        "user_id": getattr(
            user,
            "id",
            None,
        )
        if user is not None
        else None,

        "date": today,
        "work_date": today,
        "target_date": today,
    }

    for method_name in (
        "get_today_status",
        "get_store_today_status",
        "get_today_checkin",
        "get_opening_status",
        "get_store_opening",
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
            LookupError,
            ValueError,
        ):
            continue

    return None


# =========================================================
# STATUS DETECTION
# =========================================================


def status_exists(
    result: Any,
) -> bool:
    """
    Чи є check-in.
    """

    if result is None:
        return False

    explicit = first_attr(
        result,
        "exists",
        "is_opened",
        "opened",
        "has_checkin",
        default=None,
    )

    if explicit is not None:
        return to_bool(
            explicit
        )

    checkin = first_attr(
        result,
        "checkin",
        "opening",
        "record",
        default=None,
    )

    if checkin is not None:
        return True

    identifier = first_attr(
        result,
        "id",
        "checkin_id",
        "opening_id",
        default=None,
    )

    if identifier is not None:
        return True

    checkin_time = (
        result_checkin_time(
            result
        )
    )

    return (
        checkin_time is not None
    )


# =========================================================
# BUILD STATUS TEXT
# =========================================================


async def build_opening_status_text(
    *,
    store_id: int,
    result: Any,
    data: dict[str, Any],
) -> str:
    """
    Текст статусу відкриття.
    """

    store = await load_store(
        store_id=store_id,
        data=data,
    )

    title = store_title(
        store,
        store_id=store_id,
    )

    if not status_exists(
        result
    ):
        return (
            "🌅 <b>Статус відкриття</b>\n\n"
            f"🏪 <b>{escape(title)}</b>\n\n"
            "⏳ Відкриття за сьогодні "
            "ще не зафіксовано."
        )

    # Якщо service повернув wrapper,
    # пробуємо дістати сам record.
    record = first_attr(
        result,
        "checkin",
        "opening",
        "record",
        default=result,
    )

    late_minutes = (
        result_lateness_minutes(
            result
        )
    )

    if late_minutes <= 0:
        late_minutes = (
            result_lateness_minutes(
                record
            )
        )

    checkin_at = (
        result_checkin_time(
            result
        )
        or result_checkin_time(
            record
        )
    )

    expected = (
        result_expected_time(
            result
        )
        or result_expected_time(
            record
        )
    )

    deadline = (
        result_deadline_time(
            result
        )
        or result_deadline_time(
            record
        )
    )

    lines = [
        "🌅 <b>Статус відкриття</b>",
        "",
        f"🏪 <b>{escape(title)}</b>",
        "",
        (
            "🕐 Фактичне відкриття: "
            f"<b>{escape(format_time(checkin_at))}</b>"
        ),
    ]

    if expected is not None:
        lines.append(
            "📅 Час за графіком: "
            f"<b>{escape(format_time(expected))}</b>"
        )

    if deadline is not None:
        lines.append(
            "⏱ Контрольний час: "
            f"<b>{escape(format_time(deadline))}</b>"
        )

    lines.append(
        ""
    )

    if late_minutes > 0:
        lines.append(
            "⚠️ <b>Запізнення: "
            f"{late_minutes} хв.</b>"
        )

    else:
        lines.append(
            "✅ <b>Відкрито вчасно.</b>"
        )

    return "\n".join(
        lines
    )


# =========================================================
# SHOW STORE SELECT
# =========================================================


async def show_store_selection(
    callback: CallbackQuery,
    *,
    data: dict[str, Any],
) -> None:
    """
    Якщо користувач має кілька ТТ.
    """

    store_ids = accessible_store_ids(
        data
    )

    if not store_ids:
        await safe_edit(
            callback,
            text=(
                "⚠️ До вашого профілю "
                "не прив’язано жодної ТТ."
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
            "зафіксувати відкриття?"
        ),
        reply_markup=(
            select_store_keyboard(
                stores=stores,
                context="opening",
            )
        ),
    )


# =========================================================
# SHOW OPENING MENU
# =========================================================


async def show_opening_menu(
    callback: CallbackQuery,
    *,
    store_id: int,
    user: DatabaseUser,
    data: dict[str, Any],
) -> None:
    """
    Відкриття конкретної ТТ.
    """

    result = await get_opening_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    if status_exists(
        result
    ):
        text = (
            await build_opening_status_text(
                store_id=store_id,
                result=result,
                data=data,
            )
        )

        await safe_edit(
            callback,
            text=text,
            reply_markup=(
                opening_status_keyboard(
                    store_id=store_id,
                    can_close=True,
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
            "🌅 <b>Відкриття магазину</b>\n\n"
            f"🏪 <b>{escape(title)}</b>\n\n"
            "Натисніть кнопку нижче "
            "лише після фактичного "
            "відкриття торгової точки."
        ),
        reply_markup=(
            opening_prepare_keyboard(
                store_id=store_id
            )
        ),
    )


# =========================================================
# MENU
# =========================================================


@router.callback_query(
    OpeningCallback.filter(
        F.action
        == OpeningAction.MENU
    )
)
async def opening_menu_callback(
    callback: CallbackQuery,
    callback_data: OpeningCallback,
    **data: Any,
) -> None:
    """
    Вхід у відкриття.
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

    await show_opening_menu(
        callback,
        store_id=store_id,
        user=user,
        data=data,
    )


# =========================================================
# SELECT STORE
# =========================================================


@router.callback_query(
    OpeningCallback.filter(
        F.action
        == OpeningAction.SELECT_STORE
    )
)
async def opening_select_store_callback(
    callback: CallbackQuery,
    callback_data: OpeningCallback,
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

    await show_opening_menu(
        callback,
        store_id=store_id,
        user=user,
        data=data,
    )


# =========================================================
# PREPARE
# =========================================================


@router.callback_query(
    OpeningCallback.filter(
        F.action
        == OpeningAction.PREPARE
    )
)
async def opening_prepare_callback(
    callback: CallbackQuery,
    callback_data: OpeningCallback,
    **data: Any,
) -> None:
    """
    Підтвердження перед check-in.
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

    existing = await get_opening_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    if status_exists(
        existing
    ):
        text = (
            await build_opening_status_text(
                store_id=store_id,
                result=existing,
                data=data,
            )
        )

        await safe_edit(
            callback,
            text=(
                "ℹ️ <b>Відкриття вже "
                "зафіксовано.</b>\n\n"
                f"{text}"
            ),
            reply_markup=(
                opening_already_done_keyboard(
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
            "🌅 <b>Підтвердження відкриття</b>\n\n"
            f"🏪 {escape(title)}\n\n"
            "Магазин уже фактично відкритий "
            "і готовий до роботи?"
        ),
        reply_markup=(
            opening_prepare_keyboard(
                store_id=store_id
            )
        ),
    )


# =========================================================
# CONFIRM
# =========================================================


@router.callback_query(
    OpeningCallback.filter(
        F.action
        == OpeningAction.CONFIRM
    )
)
async def opening_confirm_callback(
    callback: CallbackQuery,
    callback_data: OpeningCallback,
    **data: Any,
) -> None:
    """
    Фактичний check-in.
    """

    user = get_database_user(
        data
    )

    if user is None:
        await callback.answer(
            "Користувача не знайдено.",
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

    await callback.answer(
        "Фіксую відкриття…"
    )

    # -----------------------------------------------------
    # DUPLICATE CHECK
    # -----------------------------------------------------

    existing = await get_opening_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    if status_exists(
        existing
    ):
        text = (
            await build_opening_status_text(
                store_id=store_id,
                result=existing,
                data=data,
            )
        )

        await safe_edit(
            callback,
            text=(
                "ℹ️ <b>Відкриття вже "
                "було зафіксовано.</b>\n\n"
                f"{text}"
            ),
            reply_markup=(
                opening_already_done_keyboard(
                    store_id=store_id
                )
            ),
        )

        return

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------

    try:
        result = await register_opening(
            store_id=store_id,
            user=user,
            data=data,
        )

    except Exception:
        logger.exception(
            "Opening check-in failed: "
            "store_id=%s user_id=%s",
            store_id,
            getattr(
                user,
                "id",
                None,
            ),
        )

        await safe_edit(
            callback,
            text=(
                "❌ <b>Не вдалося "
                "зафіксувати відкриття.</b>\n\n"
                "Спробуйте ще раз."
            ),
            reply_markup=(
                opening_prepare_keyboard(
                    store_id=store_id
                )
            ),
        )

        return

    # -----------------------------------------------------
    # RESULT
    # -----------------------------------------------------

    if not result_success(
        result
    ):
        reason = result_message(
            result
        )

        await safe_edit(
            callback,
            text=(
                "❌ <b>Відкриття "
                "не зафіксовано.</b>\n\n"
                f"{escape(str(reason or 'Спробуйте ще раз.'))}"
            ),
            reply_markup=(
                opening_prepare_keyboard(
                    store_id=store_id
                )
            ),
        )

        return

    if result_already_exists(
        result
    ):
        current = (
            await get_opening_status(
                store_id=store_id,
                user=user,
                data=data,
            )
        )

        text = (
            await build_opening_status_text(
                store_id=store_id,
                result=current or result,
                data=data,
            )
        )

        await safe_edit(
            callback,
            text=text,
            reply_markup=(
                opening_already_done_keyboard(
                    store_id=store_id
                )
            ),
        )

        return

    late_minutes = (
        result_lateness_minutes(
            result
        )
    )

    # Після запису перечитуємо статус,
    # щоб показати дані вже з БД.
    current = await get_opening_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    status_result = (
        current
        or result
    )

    text = (
        await build_opening_status_text(
            store_id=store_id,
            result=status_result,
            data=data,
        )
    )

    if late_minutes > 0:
        await safe_edit(
            callback,
            text=(
                "⚠️ <b>Магазин відкрито "
                "із запізненням.</b>\n\n"
                f"{text}"
            ),
            reply_markup=(
                opening_late_keyboard(
                    store_id=store_id
                )
            ),
        )

    else:
        await safe_edit(
            callback,
            text=(
                "✅ <b>Відкриття "
                "зафіксовано.</b>\n\n"
                f"{text}"
            ),
            reply_markup=(
                opening_success_keyboard(
                    store_id=store_id
                )
            ),
        )


# =========================================================
# STATUS
# =========================================================


@router.callback_query(
    OpeningCallback.filter(
        F.action.in_(
            {
                OpeningAction.STATUS,
                OpeningAction.REFRESH,
                OpeningAction.LATE,
            }
        )
    )
)
async def opening_status_callback(
    callback: CallbackQuery,
    callback_data: OpeningCallback,
    **data: Any,
) -> None:
    """
    Статус / refresh.
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

    result = await get_opening_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    text = (
        await build_opening_status_text(
            store_id=store_id,
            result=result,
            data=data,
        )
    )

    if status_exists(
        result
    ):
        markup = (
            opening_status_keyboard(
                store_id=store_id,
                can_close=True,
            )
        )

    else:
        markup = (
            opening_prepare_keyboard(
                store_id=store_id
            )
        )

    await safe_edit(
        callback,
        text=text,
        reply_markup=markup,
    )


# =========================================================
# MANUAL CORRECTION
# =========================================================


@router.callback_query(
    OpeningCallback.filter(
        F.action
        == OpeningAction.MANUAL
    )
)
async def opening_manual_callback(
    callback: CallbackQuery,
    callback_data: OpeningCallback,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Адмінське ручне коригування.
    """

    user = get_database_user(
        data
    )

    if user is None:
        return

    # Ручне коригування дозволяємо
    # тільки менеджерам/адмінам.
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
        .replace("-", "_")
        .replace(" ", "_")
    )

    allowed_roles = {
        "ROOT_ADMIN",
        "DIRECTOR",
        "BUSH_ADMIN",
    }

    if role_name not in allowed_roles:
        await callback.answer(
            "Ручне коригування "
            "доступне лише адміністрації.",
            show_alert=True,
        )

        return

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

    await callback.answer()

    await state.set_state(
        OpeningStates
        .waiting_manual_time
    )

    await state.update_data(
        opening_store_id=store_id
    )

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
            "✏️ <b>Ручне коригування "
            "відкриття</b>\n\n"
            f"🏪 {escape(title)}\n\n"
            "Введіть фактичний час "
            "відкриття у форматі:\n\n"
            "<code>08:03</code>\n\n"
            "Для скасування надішліть "
            "<code>/cancel</code>."
        ),
        reply_markup=None,
    )


# =========================================================
# PARSE MANUAL TIME
# =========================================================


def parse_manual_time(
    text: str,
) -> time | None:
    """
    HH:MM
    """

    normalized = (
        text.strip()
    )

    for fmt in (
        "%H:%M",
        "%H.%M",
    ):
        try:
            parsed = datetime.strptime(
                normalized,
                fmt,
            )

            return parsed.time()

        except ValueError:
            continue

    return None


# =========================================================
# MANUAL TIME MESSAGE
# =========================================================


@router.message(
    OpeningStates.waiting_manual_time
)
async def opening_manual_time_handler(
    message: Message,
    state: FSMContext,
    **data: Any,
) -> None:
    """
    Зберігає скоригований час.
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
            "❌ Ручне коригування "
            "скасовано.",
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
            "⚠️ Невірний формат часу.\n\n"
            "Введіть, наприклад:\n"
            "<code>08:03</code>"
        )

        return

    state_data = await state.get_data()

    store_id = to_int(
        state_data.get(
            "opening_store_id"
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

    local_now = now_local()

    corrected_at = datetime.combine(
        local_now.date(),
        parsed_time,
        tzinfo=KYIV_TZ,
    )

    try:
        result = await register_opening(
            store_id=store_id,
            user=user,
            data=data,
            opened_at=corrected_at,
            manual=True,
        )

    except Exception:
        logger.exception(
            "Manual opening correction failed: "
            "store_id=%s",
            store_id,
        )

        await message.answer(
            "❌ Не вдалося виконати "
            "ручне коригування.\n\n"
            "Перевірте час і спробуйте "
            "ще раз."
        )

        return

    await state.clear()

    status = await get_opening_status(
        store_id=store_id,
        user=user,
        data=data,
    )

    result_for_text = (
        status
        or result
    )

    status_text = (
        await build_opening_status_text(
            store_id=store_id,
            result=result_for_text,
            data=data,
        )
    )

    await message.answer(
        "✅ <b>Час відкриття "
        "скориговано.</b>\n\n"
        f"{status_text}",
        reply_markup=(
            opening_status_keyboard(
                store_id=store_id,
                can_close=True,
            )
        ),
    )


# =========================================================
# BACK
# =========================================================


@router.callback_query(
    OpeningCallback.filter(
        F.action
        == OpeningAction.BACK
    )
)
async def opening_back_callback(
    callback: CallbackQuery,
    callback_data: OpeningCallback,
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
# STORE ACTION -> OPENING
# =========================================================


@router.callback_query(
    StoreCallback.filter(
        F.action
        == StoreAction.VIEW
    )
)
async def opening_store_view_fallback(
    callback: CallbackQuery,
    callback_data: StoreCallback,
    **data: Any,
) -> None:
    """
    Базова картка ТТ.

    Пізніше store.py матиме повніший handler.
    Цей fallback корисний, поки store.py
    ще не підключений.
    """

    await callback.answer()

    store_id = (
        callback_data.store_id
    )

    if store_id <= 0:
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
# UNKNOWN CALLBACK
# =========================================================


@router.callback_query(
    OpeningCallback.filter()
)
async def unknown_opening_callback(
    callback: CallbackQuery,
) -> None:
    """
    Старий / невідомий callback.
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

    "KYIV_TZ",

    "OpeningStates",

    "filter_kwargs",
    "call_method",
    "first_attr",
    "to_int",
    "to_bool",

    "get_service",
    "get_opening_service",
    "get_store_service",

    "flush_changes",

    "accessible_store_ids",
    "has_network_access",
    "can_access_store",
    "resolve_store_id",

    "load_store",
    "store_title",
    "build_store_choices",

    "now_local",
    "format_time",

    "result_success",
    "result_already_exists",
    "result_lateness_minutes",
    "result_checkin_time",
    "result_expected_time",
    "result_deadline_time",
    "result_message",

    "register_opening",
    "get_opening_status",
    "status_exists",

    "build_opening_status_text",

    "show_store_selection",
    "show_opening_menu",

    "parse_manual_time",
]