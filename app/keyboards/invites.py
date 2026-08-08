from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.keyboards.callbacks import (
    InviteAction,
    InviteCallback,
    MainMenuAction,
    MainMenuCallback,
)
from app.keyboards.common import (
    home_button,
    inline_button,
)


# =========================================================
# INVITE UI ACTION
# =========================================================


class InviteUIAction(StrEnum):
    """
    Внутрішні дії UI запрошень.
    """

    MENU = "m"

    SELECT_STORE = "st"

    SELECT_BUSH = "bu"

    SELECT_ROLE = "role"

    EXPIRATION = "exp"

    SINGLE_USE = "once"

    MULTI_USE = "multi"

    CREATE = "new"

    VIEW = "v"

    LIST = "ls"

    REFRESH = "r"

    CANCEL = "c"

    BACK = "b"


class InviteUICallback(
    CallbackData,
    prefix="iui",
):
    """
    iui:<action>:<target_id>:<invite_id>:<page>

    target_id:
        store_id / bush_id / 0

    invite_id:
        конкретне запрошення

    page:
        сторінка списку
    """

    action: InviteUIAction

    target_id: int = 0

    invite_id: int = 0

    page: int = 0


# =========================================================
# INVITE TYPE
# =========================================================


class InviteType(StrEnum):
    """
    Тип запрошення.
    """

    STORE = "store"

    BUSH = "bush"

    DIRECTOR = "director"


# =========================================================
# INVITE STATUS
# =========================================================


class InviteStatus(StrEnum):
    """
    Стан invite.
    """

    ACTIVE = "active"

    USED = "used"

    EXPIRED = "expired"

    REVOKED = "revoked"


# =========================================================
# EXPIRATION
# =========================================================


class InviteExpiration(StrEnum):
    """
    Типові строки дії.
    """

    ONE_HOUR = "1h"

    SIX_HOURS = "6h"

    ONE_DAY = "1d"

    THREE_DAYS = "3d"

    SEVEN_DAYS = "7d"

    THIRTY_DAYS = "30d"

    NEVER = "never"


# =========================================================
# LIST ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class InviteListItem:
    """
    Одне запрошення у списку.
    """

    invite_id: int

    invite_type: InviteType

    target_name: str

    status: InviteStatus = (
        InviteStatus.ACTIVE
    )

    is_single_use: bool = True

    expires_text: str | None = None

    uses_count: int = 0

    max_uses: int | None = None

    @property
    def status_icon(self) -> str:
        mapping = {
            InviteStatus.ACTIVE: "🟢",
            InviteStatus.USED: "✅",
            InviteStatus.EXPIRED: "⌛",
            InviteStatus.REVOKED: "⛔",
        }

        return mapping.get(
            self.status,
            "🔗",
        )

    @property
    def type_icon(self) -> str:
        mapping = {
            InviteType.STORE: "🏪",
            InviteType.BUSH: "🌿",
            InviteType.DIRECTOR: "🏢",
        }

        return mapping.get(
            self.invite_type,
            "🔗",
        )

    @property
    def button_text(self) -> str:
        text = (
            f"{self.status_icon} "
            f"{self.type_icon} "
            f"{self.target_name}"
        )

        if self.is_single_use:
            text += " · 1 раз"

        elif self.max_uses is not None:
            text += (
                f" · {self.uses_count}/"
                f"{self.max_uses}"
            )

        elif self.uses_count > 0:
            text += (
                f" · використано "
                f"{self.uses_count}"
            )

        return text


# =========================================================
# STORE ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class InviteStoreItem:
    """
    ТТ при виборі цілі.
    """

    store_id: int

    code: str

    name: str | None = None

    bush_name: str | None = None

    is_active: bool = True

    @property
    def display_name(self) -> str:
        if self.name:
            return (
                f"{self.code} · {self.name}"
            )

        return self.code

    @property
    def button_text(self) -> str:
        icon = (
            "🏪"
            if self.is_active
            else "⚫"
        )

        text = (
            f"{icon} {self.display_name}"
        )

        if self.bush_name:
            text += (
                f" · {self.bush_name}"
            )

        return text


# =========================================================
# BUSH ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class InviteBushItem:
    """
    Кущ при виборі цілі.
    """

    bush_id: int

    name: str

    stores_count: int = 0

    is_active: bool = True

    @property
    def button_text(self) -> str:
        icon = (
            "🌿"
            if self.is_active
            else "⚫"
        )

        text = (
            f"{icon} {self.name}"
        )

        if self.stores_count > 0:
            text += (
                f" · {self.stores_count} ТТ"
            )

        return text


# =========================================================
# CREATE STATE
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class InviteCreateState:
    """
    Стан майстра створення invite.
    """

    invite_type: InviteType

    target_id: int = 0

    target_name: str | None = None

    expiration: InviteExpiration = (
        InviteExpiration.ONE_DAY
    )

    is_single_use: bool = True

    max_uses: int | None = 1


# =========================================================
# UI BUTTON
# =========================================================


def invite_ui_button(
    *,
    text: str,
    action: InviteUIAction,
    target_id: int = 0,
    invite_id: int = 0,
    page: int = 0,
) -> InlineKeyboardButton:
    """
    InviteUICallback button.
    """

    return inline_button(
        text=text,
        callback=InviteUICallback(
            action=action,
            target_id=target_id,
            invite_id=invite_id,
            page=page,
        ),
    )


# =========================================================
# MAIN MENU
# =========================================================


def invites_main_keyboard(
) -> InlineKeyboardMarkup:
    """
    Головне меню запрошень.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🏪 Запрошення для ТТ",
                    callback=InviteCallback(
                        action=InviteAction.STORE,
                        target_id=0,
                        invite_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🌿 Запрошення для куща",
                    callback=InviteCallback(
                        action=InviteAction.BUSH,
                        target_id=0,
                        invite_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🏢 Запрошення директора",
                    callback=InviteCallback(
                        action=InviteAction.DIRECTOR,
                        target_id=0,
                        invite_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="📋 Активні запрошення",
                    callback=InviteCallback(
                        action=InviteAction.LIST,
                        target_id=0,
                        invite_id=0,
                    ),
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# STORE SELECTOR
# =========================================================


def invite_store_selector_keyboard(
    *,
    stores: list[InviteStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Вибір ТТ для invite.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                inline_button(
                    text=store.button_text,
                    callback=InviteCallback(
                        action=InviteAction.STORE,
                        target_id=store.store_id,
                        invite_id=0,
                    ),
                )
            ]
        )

    if not stores:
        rows.append(
            [
                invite_ui_button(
                    text="ℹ️ Доступних ТТ немає",
                    action=InviteUIAction.MENU,
                )
            ]
        )

    append_invite_pagination(
        rows=rows,
        action=InviteUIAction.SELECT_STORE,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            invite_ui_button(
                text="🔄 Оновити",
                action=InviteUIAction.SELECT_STORE,
                page=page,
            )
        ]
    )

    rows.append(
        [
            invite_ui_button(
                text="🔙 До запрошень",
                action=InviteUIAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# BUSH SELECTOR
# =========================================================


def invite_bush_selector_keyboard(
    *,
    bushes: list[InviteBushItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Вибір куща для invite.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for bush in bushes:
        rows.append(
            [
                inline_button(
                    text=bush.button_text,
                    callback=InviteCallback(
                        action=InviteAction.BUSH,
                        target_id=bush.bush_id,
                        invite_id=0,
                    ),
                )
            ]
        )

    if not bushes:
        rows.append(
            [
                invite_ui_button(
                    text="ℹ️ Доступних кущів немає",
                    action=InviteUIAction.MENU,
                )
            ]
        )

    append_invite_pagination(
        rows=rows,
        action=InviteUIAction.SELECT_BUSH,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            invite_ui_button(
                text="🔄 Оновити",
                action=InviteUIAction.SELECT_BUSH,
                page=page,
            )
        ]
    )

    rows.append(
        [
            invite_ui_button(
                text="🔙 До запрошень",
                action=InviteUIAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORE INVITE
# =========================================================


def store_invite_create_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Налаштування invite для ТТ.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                invite_ui_button(
                    text="⏱ Строк дії",
                    action=InviteUIAction.EXPIRATION,
                    target_id=store_id,
                )
            ],
            [
                invite_ui_button(
                    text="1️⃣ Одноразове",
                    action=InviteUIAction.SINGLE_USE,
                    target_id=store_id,
                ),
                invite_ui_button(
                    text="👥 Багаторазове",
                    action=InviteUIAction.MULTI_USE,
                    target_id=store_id,
                ),
            ],
            [
                inline_button(
                    text="✅ Створити посилання",
                    callback=InviteCallback(
                        action=InviteAction.CREATE,
                        target_id=store_id,
                        invite_id=0,
                    ),
                )
            ],
            [
                invite_ui_button(
                    text="🔙 До вибору ТТ",
                    action=InviteUIAction.SELECT_STORE,
                )
            ],
        ]
    )


# =========================================================
# BUSH INVITE
# =========================================================


def bush_invite_create_keyboard(
    *,
    bush_id: int,
) -> InlineKeyboardMarkup:
    """
    Налаштування invite для куща.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                invite_ui_button(
                    text="⏱ Строк дії",
                    action=InviteUIAction.EXPIRATION,
                    target_id=bush_id,
                )
            ],
            [
                invite_ui_button(
                    text="1️⃣ Одноразове",
                    action=InviteUIAction.SINGLE_USE,
                    target_id=bush_id,
                ),
                invite_ui_button(
                    text="👥 Багаторазове",
                    action=InviteUIAction.MULTI_USE,
                    target_id=bush_id,
                ),
            ],
            [
                inline_button(
                    text="✅ Створити посилання",
                    callback=InviteCallback(
                        action=InviteAction.CREATE,
                        target_id=bush_id,
                        invite_id=0,
                    ),
                )
            ],
            [
                invite_ui_button(
                    text="🔙 До вибору куща",
                    action=InviteUIAction.SELECT_BUSH,
                )
            ],
        ]
    )


# =========================================================
# DIRECTOR INVITE
# =========================================================


def director_invite_create_keyboard(
) -> InlineKeyboardMarkup:
    """
    Створення invite для директора.

    Такий invite не прив'язаний
    до конкретної ТТ або куща.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                invite_ui_button(
                    text="⏱ Строк дії",
                    action=InviteUIAction.EXPIRATION,
                )
            ],
            [
                invite_ui_button(
                    text="1️⃣ Одноразове",
                    action=InviteUIAction.SINGLE_USE,
                )
            ],
            [
                inline_button(
                    text="✅ Створити посилання",
                    callback=InviteCallback(
                        action=InviteAction.CREATE,
                        target_id=0,
                        invite_id=0,
                    ),
                )
            ],
            [
                invite_ui_button(
                    text="🔙 До запрошень",
                    action=InviteUIAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# EXPIRATION SELECT
# =========================================================


def invite_expiration_keyboard(
    *,
    target_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Вибір строку дії.

    Значення будемо зберігати
    у FSM / handler context.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="1 година",
                    callback=(
                        f"iexp:1h:{target_id}"
                    ),
                ),
                inline_button(
                    text="6 годин",
                    callback=(
                        f"iexp:6h:{target_id}"
                    ),
                ),
            ],
            [
                inline_button(
                    text="24 години",
                    callback=(
                        f"iexp:1d:{target_id}"
                    ),
                ),
                inline_button(
                    text="3 дні",
                    callback=(
                        f"iexp:3d:{target_id}"
                    ),
                ),
            ],
            [
                inline_button(
                    text="7 днів",
                    callback=(
                        f"iexp:7d:{target_id}"
                    ),
                ),
                inline_button(
                    text="30 днів",
                    callback=(
                        f"iexp:30d:{target_id}"
                    ),
                ),
            ],
            [
                inline_button(
                    text="♾ Без строку",
                    callback=(
                        f"iexp:never:{target_id}"
                    ),
                )
            ],
            [
                invite_ui_button(
                    text="🔙 Назад",
                    action=InviteUIAction.BACK,
                    target_id=target_id,
                )
            ],
        ]
    )


# =========================================================
# CREATED INVITE
# =========================================================


def created_invite_keyboard(
    *,
    invite_url: str,
    invite_id: int,
) -> InlineKeyboardMarkup:
    """
    Після успішного створення.

    Telegram-кнопка відкриває
    готовий deep-link бота.
    """

    normalized_url = (
        invite_url.strip()
    )

    if not normalized_url:
        raise ValueError(
            "invite_url не може "
            "бути порожнім."
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🔗 Відкрити запрошення",
                    url=normalized_url,
                )
            ],
            [
                invite_ui_button(
                    text="👁 Деталі",
                    action=InviteUIAction.VIEW,
                    invite_id=invite_id,
                )
            ],
            [
                inline_button(
                    text="⛔ Відкликати",
                    callback=InviteCallback(
                        action=InviteAction.REVOKE,
                        target_id=0,
                        invite_id=invite_id,
                    ),
                )
            ],
            [
                invite_ui_button(
                    text="➕ Створити ще",
                    action=InviteUIAction.MENU,
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# ACTIVE INVITES LIST
# =========================================================


def active_invites_keyboard(
    *,
    invites: list[InviteListItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Список активних / історичних invite.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for invite in invites:
        rows.append(
            [
                invite_ui_button(
                    text=invite.button_text,
                    action=InviteUIAction.VIEW,
                    invite_id=invite.invite_id,
                    page=page,
                )
            ]
        )

    if not invites:
        rows.append(
            [
                invite_ui_button(
                    text="ℹ️ Запрошень немає",
                    action=InviteUIAction.MENU,
                )
            ]
        )

    append_invite_pagination(
        rows=rows,
        action=InviteUIAction.LIST,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            invite_ui_button(
                text="🔄 Оновити",
                action=InviteUIAction.REFRESH,
                page=page,
            )
        ]
    )

    rows.append(
        [
            invite_ui_button(
                text="➕ Створити нове",
                action=InviteUIAction.MENU,
            )
        ]
    )

    rows.append(
        [
            home_button()
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# INVITE CARD
# =========================================================


def invite_card_keyboard(
    *,
    invite_id: int,
    invite_url: str | None = None,
    is_active: bool = True,
) -> InlineKeyboardMarkup:
    """
    Картка конкретного invite.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    if invite_url:
        rows.append(
            [
                inline_button(
                    text="🔗 Відкрити посилання",
                    url=invite_url,
                )
            ]
        )

    if is_active:
        rows.append(
            [
                inline_button(
                    text="⛔ Відкликати",
                    callback=InviteCallback(
                        action=InviteAction.REVOKE,
                        target_id=0,
                        invite_id=invite_id,
                    ),
                )
            ]
        )

    rows.append(
        [
            invite_ui_button(
                text="🔄 Оновити",
                action=InviteUIAction.VIEW,
                invite_id=invite_id,
            )
        ]
    )

    rows.append(
        [
            invite_ui_button(
                text="🔙 До списку",
                action=InviteUIAction.LIST,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# REVOKE CONFIRMATION
# =========================================================


def revoke_invite_confirmation_keyboard(
    *,
    invite_id: int,
) -> InlineKeyboardMarkup:
    """
    Підтвердження відкликання.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="⛔ Так, відкликати",
                    callback=InviteCallback(
                        action=InviteAction.REVOKE,
                        target_id=0,
                        invite_id=invite_id,
                    ),
                )
            ],
            [
                invite_ui_button(
                    text="🔙 Ні, назад",
                    action=InviteUIAction.VIEW,
                    invite_id=invite_id,
                )
            ],
        ]
    )


# =========================================================
# REVOKED
# =========================================================


def invite_revoked_keyboard(
) -> InlineKeyboardMarkup:
    """
    Після відкликання.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                invite_ui_button(
                    text="📋 До списку",
                    action=InviteUIAction.LIST,
                )
            ],
            [
                invite_ui_button(
                    text="➕ Нове запрошення",
                    action=InviteUIAction.MENU,
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# USED
# =========================================================


def invite_used_keyboard(
    *,
    invite_id: int,
) -> InlineKeyboardMarkup:
    """
    Одноразове запрошення
    вже використано.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                invite_ui_button(
                    text="👁 Деталі",
                    action=InviteUIAction.VIEW,
                    invite_id=invite_id,
                )
            ],
            [
                invite_ui_button(
                    text="➕ Створити нове",
                    action=InviteUIAction.MENU,
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# EXPIRED
# =========================================================


def invite_expired_keyboard(
    *,
    invite_id: int,
) -> InlineKeyboardMarkup:
    """
    Прострочене запрошення.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                invite_ui_button(
                    text="👁 Деталі",
                    action=InviteUIAction.VIEW,
                    invite_id=invite_id,
                )
            ],
            [
                invite_ui_button(
                    text="➕ Створити нове",
                    action=InviteUIAction.MENU,
                )
            ],
            [
                invite_ui_button(
                    text="📋 До списку",
                    action=InviteUIAction.LIST,
                )
            ],
        ]
    )


# =========================================================
# ACTIVATION SUCCESS
# =========================================================


def invite_activation_success_keyboard(
) -> InlineKeyboardMarkup:
    """
    Користувач успішно активував invite.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="✅ Продовжити",
                    callback=MainMenuCallback(
                        action=MainMenuAction.HOME
                    ),
                )
            ]
        ]
    )


# =========================================================
# ACTIVATION ERROR
# =========================================================


def invite_activation_error_keyboard(
) -> InlineKeyboardMarkup:
    """
    Invite невалідний /
    прострочений /
    відкликаний.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🏠 Головне меню",
                    callback=MainMenuCallback(
                        action=MainMenuAction.HOME
                    ),
                )
            ],
            [
                inline_button(
                    text="ℹ️ Допомога",
                    callback=MainMenuCallback(
                        action=MainMenuAction.HELP
                    ),
                )
            ],
        ]
    )


# =========================================================
# CREATE CANCEL
# =========================================================


def invite_create_cancel_keyboard(
) -> InlineKeyboardMarkup:
    """
    Скасування майстра створення.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                invite_ui_button(
                    text="❌ Скасувати",
                    action=InviteUIAction.CANCEL,
                )
            ]
        ]
    )


# =========================================================
# NO ACCESS
# =========================================================


def invite_no_access_keyboard(
) -> InlineKeyboardMarkup:
    """
    Якщо користувач не має права
    створювати invite.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                home_button()
            ]
        ]
    )


# =========================================================
# PAGINATION
# =========================================================


def append_invite_pagination(
    *,
    rows: list[
        list[InlineKeyboardButton]
    ],
    action: InviteUIAction,
    page: int,
    total_pages: int,
    target_id: int = 0,
) -> None:
    """
    Пагінація invite UI.
    """

    if total_pages <= 1:
        return

    normalized_page = max(
        0,
        min(
            page,
            total_pages - 1,
        ),
    )

    row: list[
        InlineKeyboardButton
    ] = []

    if normalized_page > 0:
        row.append(
            invite_ui_button(
                text="⬅️",
                action=action,
                target_id=target_id,
                page=normalized_page - 1,
            )
        )

    row.append(
        invite_ui_button(
            text=(
                f"{normalized_page + 1}/"
                f"{total_pages}"
            ),
            action=action,
            target_id=target_id,
            page=normalized_page,
        )
    )

    if (
        normalized_page + 1
        < total_pages
    ):
        row.append(
            invite_ui_button(
                text="➡️",
                action=action,
                target_id=target_id,
                page=normalized_page + 1,
            )
        )

    rows.append(
        row
    )


# =========================================================
# BACK
# =========================================================


def invites_back_keyboard(
) -> InlineKeyboardMarkup:
    """
    Назад до меню invite.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                invite_ui_button(
                    text="🔙 Назад",
                    action=InviteUIAction.MENU,
                )
            ]
        ]
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    # CALLBACK
    "InviteUIAction",
    "InviteUICallback",

    # ENUMS
    "InviteType",
    "InviteStatus",
    "InviteExpiration",

    # DATA
    "InviteListItem",
    "InviteStoreItem",
    "InviteBushItem",
    "InviteCreateState",

    # HELPER
    "invite_ui_button",

    # MAIN
    "invites_main_keyboard",

    # SELECTORS
    "invite_store_selector_keyboard",
    "invite_bush_selector_keyboard",

    # CREATE
    "store_invite_create_keyboard",
    "bush_invite_create_keyboard",
    "director_invite_create_keyboard",
    "invite_expiration_keyboard",
    "invite_create_cancel_keyboard",

    # CREATED
    "created_invite_keyboard",

    # LIST / CARD
    "active_invites_keyboard",
    "invite_card_keyboard",

    # REVOKE
    "revoke_invite_confirmation_keyboard",
    "invite_revoked_keyboard",

    # STATES
    "invite_used_keyboard",
    "invite_expired_keyboard",

    # ACTIVATION
    "invite_activation_success_keyboard",
    "invite_activation_error_keyboard",

    # ACCESS
    "invite_no_access_keyboard",

    # PAGINATION
    "append_invite_pagination",

    # NAVIGATION
    "invites_back_keyboard",
]