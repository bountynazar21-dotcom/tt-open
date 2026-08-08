from __future__ import annotations

from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)

from app.database.models.user import (
    User as DatabaseUser,
)
from app.keyboards import (
    BushAdminAction,
    BushAdminCallback,
    DirectorAction,
    DirectorCallback,
    LionAction,
    LionCallback,
    MainMenuAction,
    MainMenuCallback,
    OpeningAction,
    OpeningCallback,
    RootAdminAction,
    RootAdminCallback,
    StoreAction,
    StoreCallback,
    home_keyboard,
    inline_button,
)


# =========================================================
# ROUTER
# =========================================================


router = Router(
    name="common",
)


# =========================================================
# ROLE NAMES
# =========================================================


ROLE_LABELS = {
    "ROOT_ADMIN": "👑 ROOT ADMIN",
    "DIRECTOR": "🏢 Директор",
    "BUSH_ADMIN": "🌿 Адміністратор куща",
    "LION": "🦁 Лев",
    "STORE_USER": "🏪 Торгова точка",
}


STATUS_LABELS = {
    "ACTIVE": "✅ Активний",
    "PENDING": "⏳ Очікує підтвердження",
    "BLOCKED": "⛔ Заблокований",
    "INACTIVE": "⚫ Неактивний",
    "REJECTED": "❌ Відхилений",
}


# =========================================================
# USER HELPERS
# =========================================================


def get_database_user(
    data: dict[str, Any],
) -> DatabaseUser | None:
    """
    Отримує DB-користувача,
    якого передав AuthMiddleware.
    """

    for key in (
        "user",
        "current_user",
        "db_user",
        "authenticated_user",
    ):
        value = data.get(
            key
        )

        if isinstance(
            value,
            DatabaseUser,
        ):
            return value

    auth_context = data.get(
        "auth_context"
    )

    if auth_context is not None:
        for key in (
            "user",
            "current_user",
            "db_user",
        ):
            value = getattr(
                auth_context,
                key,
                None,
            )

            if isinstance(
                value,
                DatabaseUser,
            ):
                return value

    return None


def enum_name(
    value: Any,
) -> str:
    """
    Нормалізує enum / string.
    """

    if value is None:
        return ""

    name = getattr(
        value,
        "name",
        None,
    )

    if name:
        return str(
            name
        ).upper()

    raw_value = getattr(
        value,
        "value",
        value,
    )

    return (
        str(raw_value)
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )


def user_role_name(
    user: DatabaseUser,
) -> str:
    """
    Роль користувача.
    """

    return enum_name(
        getattr(
            user,
            "role",
            None,
        )
    )


def user_status_name(
    user: DatabaseUser,
) -> str:
    """
    Статус користувача.
    """

    return enum_name(
        getattr(
            user,
            "status",
            None,
        )
    )


# =========================================================
# ACCESS HELPERS
# =========================================================


def get_access_context(
    data: dict[str, Any],
) -> Any | None:
    """
    AccessMiddleware додає access_context.
    """

    return data.get(
        "access_context"
    ) or data.get(
        "access_scope"
    )


def get_primary_store_id(
    data: dict[str, Any],
) -> int | None:
    """
    Основна ТТ користувача.
    """

    direct_value = data.get(
        "primary_store_id"
    )

    if direct_value:
        try:
            return int(
                direct_value
            )

        except (
            TypeError,
            ValueError,
        ):
            pass

    access_context = (
        get_access_context(
            data
        )
    )

    if access_context is None:
        return None

    value = getattr(
        access_context,
        "primary_store_id",
        None,
    )

    if value:
        try:
            return int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            pass

    store_ids = getattr(
        access_context,
        "store_ids",
        None,
    )

    if store_ids:
        normalized = [
            int(store_id)
            for store_id
            in store_ids
            if store_id
        ]

        if len(
            normalized
        ) == 1:
            return normalized[0]

    return None


def get_primary_bush_id(
    data: dict[str, Any],
) -> int | None:
    """
    Якщо доступний один кущ,
    використовуємо його одразу.
    """

    direct_value = data.get(
        "current_bush_id"
    )

    if direct_value:
        try:
            return int(
                direct_value
            )

        except (
            TypeError,
            ValueError,
        ):
            pass

    access_context = (
        get_access_context(
            data
        )
    )

    if access_context is None:
        return None

    bush_ids = getattr(
        access_context,
        "bush_ids",
        None,
    )

    if not bush_ids:
        return None

    normalized = [
        int(bush_id)
        for bush_id
        in bush_ids
        if bush_id
    ]

    if len(
        normalized
    ) == 1:
        return normalized[0]

    return None


# =========================================================
# HOME TEXT
# =========================================================


def build_home_text(
    user: DatabaseUser,
) -> str:
    """
    Текст головного меню.
    """

    role_name = user_role_name(
        user
    )

    role_text = ROLE_LABELS.get(
        role_name,
        role_name or "Користувач",
    )

    display_name = (
        getattr(
            user,
            "full_name",
            None,
        )
        or getattr(
            user,
            "first_name",
            None,
        )
        or "Користувач"
    )

    return (
        "🏠 <b>Головне меню</b>\n\n"
        f"👤 {escape(str(display_name))}\n"
        f"🎭 {escape(role_text)}\n\n"
        "Оберіть потрібний розділ:"
    )


# =========================================================
# HOME KEYBOARD
# =========================================================


def build_role_home_keyboard(
    *,
    user: DatabaseUser,
    data: dict[str, Any],
) -> InlineKeyboardMarkup:
    """
    Формує головне меню
    відповідно до ролі.
    """

    role_name = user_role_name(
        user
    )

    # -----------------------------------------------------
    # ROOT ADMIN
    # -----------------------------------------------------

    if role_name == "ROOT_ADMIN":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    inline_button(
                        text="👑 ROOT адмінка",
                        callback=RootAdminCallback(
                            action=(
                                RootAdminAction.MENU
                            ),
                            ref_id=0,
                            page=0,
                        ),
                    )
                ],
                [
                    inline_button(
                        text="👤 Мій профіль",
                        callback=MainMenuCallback(
                            action=(
                                MainMenuAction.PROFILE
                            )
                        ),
                    ),
                    inline_button(
                        text="ℹ️ Допомога",
                        callback=MainMenuCallback(
                            action=(
                                MainMenuAction.HELP
                            )
                        ),
                    ),
                ],
            ]
        )

    # -----------------------------------------------------
    # DIRECTOR
    # -----------------------------------------------------

    if role_name == "DIRECTOR":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    inline_button(
                        text="🏢 Панель директора",
                        callback=DirectorCallback(
                            action=(
                                DirectorAction.MENU
                            ),
                            ref_id=0,
                            page=0,
                        ),
                    )
                ],
                [
                    inline_button(
                        text="👤 Мій профіль",
                        callback=MainMenuCallback(
                            action=(
                                MainMenuAction.PROFILE
                            )
                        ),
                    ),
                    inline_button(
                        text="ℹ️ Допомога",
                        callback=MainMenuCallback(
                            action=(
                                MainMenuAction.HELP
                            )
                        ),
                    ),
                ],
            ]
        )

    # -----------------------------------------------------
    # BUSH ADMIN
    # -----------------------------------------------------

    if role_name == "BUSH_ADMIN":
        bush_id = (
            get_primary_bush_id(
                data
            )
            or 0
        )

        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    inline_button(
                        text="🌿 Мій кущ",
                        callback=BushAdminCallback(
                            action=(
                                BushAdminAction.MENU
                            ),
                            bush_id=bush_id,
                            page=0,
                        ),
                    )
                ],
                [
                    inline_button(
                        text="👤 Мій профіль",
                        callback=MainMenuCallback(
                            action=(
                                MainMenuAction.PROFILE
                            )
                        ),
                    ),
                    inline_button(
                        text="ℹ️ Допомога",
                        callback=MainMenuCallback(
                            action=(
                                MainMenuAction.HELP
                            )
                        ),
                    ),
                ],
            ]
        )

    # -----------------------------------------------------
    # LION
    # -----------------------------------------------------

    if role_name == "LION":
        bush_id = (
            get_primary_bush_id(
                data
            )
            or 0
        )

        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    inline_button(
                        text="🦁 Панель Лева",
                        callback=LionCallback(
                            action=LionAction.MENU,
                            bush_id=bush_id,
                            page=0,
                        ),
                    )
                ],
                [
                    inline_button(
                        text="👤 Мій профіль",
                        callback=MainMenuCallback(
                            action=(
                                MainMenuAction.PROFILE
                            )
                        ),
                    ),
                    inline_button(
                        text="ℹ️ Допомога",
                        callback=MainMenuCallback(
                            action=(
                                MainMenuAction.HELP
                            )
                        ),
                    ),
                ],
            ]
        )

    # -----------------------------------------------------
    # STORE USER
    # -----------------------------------------------------

    if role_name == "STORE_USER":
        store_id = (
            get_primary_store_id(
                data
            )
            or 0
        )

        rows = []

        if store_id > 0:
            rows.extend(
                [
                    [
                        inline_button(
                            text="🏪 Моя ТТ",
                            callback=StoreCallback(
                                action=(
                                    StoreAction.VIEW
                                ),
                                store_id=store_id,
                                page=0,
                            ),
                        )
                    ],
                    [
                        inline_button(
                            text="🌅 Відкриття",
                            callback=OpeningCallback(
                                action=(
                                    OpeningAction.MENU
                                ),
                                store_id=store_id,
                            ),
                        )
                    ],
                ]
            )

        else:
            rows.append(
                [
                    inline_button(
                        text=(
                            "⚠️ ТТ не прив’язана"
                        ),
                        callback=MainMenuCallback(
                            action=(
                                MainMenuAction.PROFILE
                            )
                        ),
                    )
                ]
            )

        rows.append(
            [
                inline_button(
                    text="👤 Мій профіль",
                    callback=MainMenuCallback(
                        action=(
                            MainMenuAction.PROFILE
                        )
                    ),
                ),
                inline_button(
                    text="ℹ️ Допомога",
                    callback=MainMenuCallback(
                        action=(
                            MainMenuAction.HELP
                        )
                    ),
                ),
            ]
        )

        return InlineKeyboardMarkup(
            inline_keyboard=rows
        )

    # -----------------------------------------------------
    # UNKNOWN
    # -----------------------------------------------------

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="👤 Мій профіль",
                    callback=MainMenuCallback(
                        action=(
                            MainMenuAction.PROFILE
                        )
                    ),
                )
            ],
            [
                inline_button(
                    text="ℹ️ Допомога",
                    callback=MainMenuCallback(
                        action=(
                            MainMenuAction.HELP
                        )
                    ),
                )
            ],
        ]
    )


# =========================================================
# PROFILE
# =========================================================


def build_profile_text(
    user: DatabaseUser,
    data: dict[str, Any],
) -> str:
    """
    Формує картку користувача.
    """

    role_name = user_role_name(
        user
    )

    status_name = user_status_name(
        user
    )

    role_text = ROLE_LABELS.get(
        role_name,
        role_name or "—",
    )

    status_text = STATUS_LABELS.get(
        status_name,
        status_name or "—",
    )

    display_name = (
        getattr(
            user,
            "full_name",
            None,
        )
        or getattr(
            user,
            "first_name",
            None,
        )
        or "—"
    )

    username = getattr(
        user,
        "username",
        None,
    )

    phone = getattr(
        user,
        "phone",
        None,
    ) or getattr(
        user,
        "phone_number",
        None,
    )

    telegram_id = getattr(
        user,
        "telegram_id",
        None,
    )

    primary_store_id = (
        get_primary_store_id(
            data
        )
    )

    primary_bush_id = (
        get_primary_bush_id(
            data
        )
    )

    lines = [
        "👤 <b>Мій профіль</b>",
        "",
        (
            "Ім’я: "
            f"<b>{escape(str(display_name))}</b>"
        ),
        (
            "Роль: "
            f"<b>{escape(role_text)}</b>"
        ),
        (
            "Статус: "
            f"<b>{escape(status_text)}</b>"
        ),
    ]

    if username:
        lines.append(
            "Telegram: "
            f"@{escape(str(username).lstrip('@'))}"
        )

    if phone:
        lines.append(
            "Телефон: "
            f"<code>{escape(str(phone))}</code>"
        )

    if telegram_id:
        lines.append(
            "Telegram ID: "
            f"<code>{telegram_id}</code>"
        )

    if primary_store_id:
        lines.append(
            "Основна ТТ: "
            f"<b>#{primary_store_id}</b>"
        )

    if primary_bush_id:
        lines.append(
            "Кущ: "
            f"<b>#{primary_bush_id}</b>"
        )

    return "\n".join(
        lines
    )


def profile_keyboard(
) -> InlineKeyboardMarkup:
    """
    Кнопка назад із профілю.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🔄 Оновити",
                    callback=MainMenuCallback(
                        action=(
                            MainMenuAction.PROFILE
                        )
                    ),
                )
            ],
            [
                inline_button(
                    text="🏠 Головне меню",
                    callback=MainMenuCallback(
                        action=(
                            MainMenuAction.HOME
                        )
                    ),
                )
            ],
        ]
    )


# =========================================================
# HELP
# =========================================================


def build_help_text(
    user: DatabaseUser | None,
) -> str:
    """
    Базова довідка.
    """

    role_name = (
        user_role_name(
            user
        )
        if user is not None
        else ""
    )

    lines = [
        "ℹ️ <b>Допомога</b>",
        "",
        "Цей бот використовується для "
        "контролю роботи торгових точок.",
        "",
    ]

    if role_name == "STORE_USER":
        lines.extend(
            [
                "🏪 <b>Для ТТ:</b>",
                "• підтвердити відкриття;",
                "• пройти закриття;",
                "• внести касу;",
                "• додати необхідний звіт.",
            ]
        )

    elif role_name == "LION":
        lines.extend(
            [
                "🦁 <b>Для Лева:</b>",
                "• контролювати свої ТТ;",
                "• бачити відкриття;",
                "• бачити запізнення;",
                "• контролювати закриття.",
            ]
        )

    elif role_name == "BUSH_ADMIN":
        lines.extend(
            [
                "🌿 <b>Для адміністратора куща:</b>",
                "• контролювати ТТ куща;",
                "• керувати користувачами;",
                "• працювати з графіками;",
                "• переглядати звіти.",
            ]
        )

    elif role_name == "DIRECTOR":
        lines.extend(
            [
                "🏢 <b>Для директора:</b>",
                "• контроль усієї мережі;",
                "• кущі та ТТ;",
                "• користувачі;",
                "• звітність.",
            ]
        )

    elif role_name == "ROOT_ADMIN":
        lines.extend(
            [
                "👑 <b>Для ROOT_ADMIN:</b>",
                "• повне керування мережею;",
                "• користувачі та ролі;",
                "• кущі та кластери;",
                "• імпорт;",
                "• системні налаштування;",
                "• Audit Log.",
            ]
        )

    else:
        lines.append(
            "Використайте головне меню "
            "для навігації."
        )

    lines.extend(
        [
            "",
            "Команди:",
            "/menu — головне меню",
            "/help — допомога",
        ]
    )

    return "\n".join(
        lines
    )


def help_keyboard(
) -> InlineKeyboardMarkup:
    """
    Клавіатура довідки.
    """

    return InlineKeyboardMarkup(
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


# =========================================================
# SEND / EDIT HELPERS
# =========================================================


async def safe_edit(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """
    Безпечно редагує callback message.
    """

    if callback.message is None:
        return

    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=reply_markup,
        )

    except TelegramBadRequest as error:
        error_text = str(
            error
        ).lower()

        if (
            "message is not modified"
            in error_text
        ):
            return

        try:
            await callback.message.answer(
                text=text,
                reply_markup=reply_markup,
            )

        except TelegramBadRequest:
            pass


# =========================================================
# SHOW HOME
# =========================================================


async def show_home_message(
    message: Message,
    *,
    user: DatabaseUser,
    data: dict[str, Any],
) -> None:
    """
    Надсилає головне меню.
    """

    await message.answer(
        text=build_home_text(
            user
        ),
        reply_markup=(
            build_role_home_keyboard(
                user=user,
                data=data,
            )
        ),
    )


async def show_home_callback(
    callback: CallbackQuery,
    *,
    user: DatabaseUser,
    data: dict[str, Any],
) -> None:
    """
    Редагує повідомлення
    на головне меню.
    """

    await safe_edit(
        callback,
        text=build_home_text(
            user
        ),
        reply_markup=(
            build_role_home_keyboard(
                user=user,
                data=data,
            )
        ),
    )


# =========================================================
# /MENU
# =========================================================


@router.message(
    Command(
        "menu",
        "home",
    )
)
async def menu_command(
    message: Message,
    **data: Any,
) -> None:
    """
    /menu
    /home
    """

    user = get_database_user(
        data
    )

    if user is None:
        await message.answer(
            "⚠️ Не вдалося визначити "
            "ваш обліковий запис.\n\n"
            "Спробуйте /start."
        )

        return

    await show_home_message(
        message,
        user=user,
        data=data,
    )


# =========================================================
# HOME CALLBACK
# =========================================================


@router.callback_query(
    MainMenuCallback.filter(
        F.action
        == MainMenuAction.HOME
    )
)
async def home_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Головне меню.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    if user is None:
        if callback.message:
            await callback.message.answer(
                "⚠️ Сесія користувача "
                "не знайдена.\n"
                "Використайте /start."
            )

        return

    await show_home_callback(
        callback,
        user=user,
        data=data,
    )


# =========================================================
# PROFILE CALLBACK
# =========================================================


@router.callback_query(
    MainMenuCallback.filter(
        F.action
        == MainMenuAction.PROFILE
    )
)
async def profile_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Профіль.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    if user is None:
        return

    await safe_edit(
        callback,
        text=build_profile_text(
            user,
            data,
        ),
        reply_markup=(
            profile_keyboard()
        ),
    )


# =========================================================
# /HELP
# =========================================================


@router.message(
    Command("help")
)
async def help_command(
    message: Message,
    **data: Any,
) -> None:
    """
    /help
    """

    user = get_database_user(
        data
    )

    await message.answer(
        text=build_help_text(
            user
        ),
        reply_markup=(
            help_keyboard()
        ),
    )


# =========================================================
# HELP CALLBACK
# =========================================================


@router.callback_query(
    MainMenuCallback.filter(
        F.action
        == MainMenuAction.HELP
    )
)
async def help_callback(
    callback: CallbackQuery,
    **data: Any,
) -> None:
    """
    Допомога через кнопку.
    """

    await callback.answer()

    user = get_database_user(
        data
    )

    await safe_edit(
        callback,
        text=build_help_text(
            user
        ),
        reply_markup=(
            help_keyboard()
        ),
    )


# =========================================================
# UNKNOWN MAIN MENU ACTION
# =========================================================


@router.callback_query(
    MainMenuCallback.filter()
)
async def unknown_main_menu_callback(
    callback: CallbackQuery,
) -> None:
    """
    Захист від MainMenuCallback,
    який ще не підключений
    до окремого handler.
    """

    await callback.answer(
        "Розділ відкривається "
        "через відповідне меню.",
        show_alert=False,
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "router",

    "ROLE_LABELS",
    "STATUS_LABELS",

    "get_database_user",
    "enum_name",
    "user_role_name",
    "user_status_name",

    "get_access_context",
    "get_primary_store_id",
    "get_primary_bush_id",

    "build_home_text",
    "build_role_home_keyboard",

    "build_profile_text",
    "profile_keyboard",

    "build_help_text",
    "help_keyboard",

    "safe_edit",
    "show_home_message",
    "show_home_callback",
]