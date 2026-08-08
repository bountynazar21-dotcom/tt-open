from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.keyboards.callbacks import (
    BindingAction,
    BindingCallback,
    BushAction,
    BushCallback,
    ClosingAction,
    ClosingCallback,
    InviteAction,
    InviteCallback,
    MainMenuAction,
    MainMenuCallback,
    OpeningAction,
    OpeningCallback,
    ReportAction,
    ReportCallback,
    ScheduleAction,
    ScheduleCallback,
    StoreAction,
    StoreCallback,
    UserAction,
    UserCallback,
)
from app.keyboards.common import (
    home_button,
    inline_button,
)


# =========================================================
# CALLBACKS
# =========================================================


class BushAdminAction(StrEnum):
    """
    Дії адміністратора куща.
    """

    MENU = "m"

    DASHBOARD = "dash"

    STORES = "st"

    USERS = "usr"

    LIONS = "lion"

    OPENING = "op"

    LATE = "late"

    MISSING_OPENING = "mop"

    CLOSING = "cl"

    MISSING_CLOSING = "mcl"

    SCHEDULES = "sch"

    REPORTS = "rep"

    INVITES = "inv"

    REFRESH = "r"

    BACK = "b"


class BushAdminCallback(
    CallbackData,
    prefix="ba",
):
    """
    ba:<action>:<bush_id>:<page>
    """

    action: BushAdminAction

    bush_id: int = 0

    page: int = 0


# =========================================================
# STORE STATE
# =========================================================


class BushAdminStoreState(StrEnum):
    """
    Стан ТТ.
    """

    WAITING_OPENING = "waiting_opening"

    OPENED_ON_TIME = "opened_on_time"

    OPENED_LATE = "opened_late"

    WAITING_CLOSING = "waiting_closing"

    CLOSING_IN_PROGRESS = (
        "closing_in_progress"
    )

    CLOSED = "closed"

    INACTIVE = "inactive"


# =========================================================
# DASHBOARD STATE
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class BushAdminDashboardState:
    """
    Дані головної панелі куща.
    """

    bush_id: int

    total_stores: int

    active_stores: int

    opened_count: int

    late_count: int

    missing_opening_count: int

    closed_count: int

    missing_closing_count: int

    closing_in_progress_count: int = 0

    users_count: int = 0

    lions_count: int = 0


# =========================================================
# STORE ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class BushAdminStoreItem:
    """
    ТТ у списку адміністратора.
    """

    store_id: int

    code: str

    name: str | None

    state: BushAdminStoreState

    lateness_minutes: int = 0

    cluster_text: str | None = None

    is_active: bool = True

    @property
    def display_name(self) -> str:
        if self.name:
            return (
                f"{self.code} · {self.name}"
            )

        return self.code


# =========================================================
# USER ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class BushAdminUserItem:
    """
    Користувач у кущі.
    """

    user_id: int

    display_name: str

    role_text: str

    username: str | None = None

    is_active: bool = True

    is_blocked: bool = False

    store_count: int = 0

    @property
    def button_text(self) -> str:
        status = (
            "❌"
            if self.is_blocked
            else (
                "✅"
                if self.is_active
                else "⚫"
            )
        )

        username = (
            f" @{self.username.lstrip('@')}"
            if self.username
            else ""
        )

        return (
            f"{status} "
            f"{self.display_name}"
            f"{username}"
        )


# =========================================================
# HELPERS
# =========================================================


def bush_admin_button(
    *,
    text: str,
    action: BushAdminAction,
    bush_id: int,
    page: int = 0,
) -> InlineKeyboardButton:
    """
    BushAdminCallback button.
    """

    return inline_button(
        text=text,
        callback=BushAdminCallback(
            action=action,
            bush_id=bush_id,
            page=page,
        ),
    )


def store_state_icon(
    state: BushAdminStoreState,
) -> str:
    """
    Іконка ТТ.
    """

    mapping = {
        BushAdminStoreState
        .WAITING_OPENING: "⏳",

        BushAdminStoreState
        .OPENED_ON_TIME: "✅",

        BushAdminStoreState
        .OPENED_LATE: "⚠️",

        BushAdminStoreState
        .WAITING_CLOSING: "🌙",

        BushAdminStoreState
        .CLOSING_IN_PROGRESS: "🔄",

        BushAdminStoreState
        .CLOSED: "✅",

        BushAdminStoreState
        .INACTIVE: "⚫",
    }

    return mapping.get(
        state,
        "🏪",
    )


def store_button_text(
    store: BushAdminStoreItem,
) -> str:
    """
    Текст кнопки ТТ.
    """

    icon = store_state_icon(
        store.state
    )

    text = (
        f"{icon} {store.display_name}"
    )

    if (
        store.state
        == BushAdminStoreState
        .OPENED_LATE
        and store.lateness_minutes > 0
    ):
        text += (
            f" · +{store.lateness_minutes} хв"
        )

    if store.cluster_text:
        text += (
            f" · {store.cluster_text}"
        )

    return text


# =========================================================
# MAIN DASHBOARD
# =========================================================


def bush_admin_main_keyboard(
    *,
    state: BushAdminDashboardState,
) -> InlineKeyboardMarkup:
    """
    Головне меню адміністратора куща.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    # -----------------------------------------------------
    # OPENING
    # -----------------------------------------------------

    rows.append(
        [
            bush_admin_button(
                text=(
                    "🌅 Відкриття "
                    f"{state.opened_count}/"
                    f"{state.active_stores}"
                ),
                action=(
                    BushAdminAction.OPENING
                ),
                bush_id=state.bush_id,
            )
        ]
    )

    if state.late_count > 0:
        rows.append(
            [
                bush_admin_button(
                    text=(
                        "⚠️ Запізнення: "
                        f"{state.late_count}"
                    ),
                    action=(
                        BushAdminAction.LATE
                    ),
                    bush_id=state.bush_id,
                )
            ]
        )

    if (
        state.missing_opening_count
        > 0
    ):
        rows.append(
            [
                bush_admin_button(
                    text=(
                        "🚨 Не відкрилися: "
                        f"{state.missing_opening_count}"
                    ),
                    action=(
                        BushAdminAction
                        .MISSING_OPENING
                    ),
                    bush_id=state.bush_id,
                )
            ]
        )

    # -----------------------------------------------------
    # CLOSING
    # -----------------------------------------------------

    rows.append(
        [
            bush_admin_button(
                text=(
                    "🌙 Закриття "
                    f"{state.closed_count}/"
                    f"{state.active_stores}"
                ),
                action=(
                    BushAdminAction.CLOSING
                ),
                bush_id=state.bush_id,
            )
        ]
    )

    if (
        state.missing_closing_count
        > 0
    ):
        rows.append(
            [
                bush_admin_button(
                    text=(
                        "🚨 Не закрилися: "
                        f"{state.missing_closing_count}"
                    ),
                    action=(
                        BushAdminAction
                        .MISSING_CLOSING
                    ),
                    bush_id=state.bush_id,
                )
            ]
        )

    # -----------------------------------------------------
    # STORES
    # -----------------------------------------------------

    rows.append(
        [
            bush_admin_button(
                text=(
                    "🏪 Торгові точки "
                    f"({state.active_stores})"
                ),
                action=(
                    BushAdminAction.STORES
                ),
                bush_id=state.bush_id,
            )
        ]
    )

    # -----------------------------------------------------
    # USERS
    # -----------------------------------------------------

    rows.append(
        [
            bush_admin_button(
                text=(
                    "👥 Працівники "
                    f"({state.users_count})"
                ),
                action=(
                    BushAdminAction.USERS
                ),
                bush_id=state.bush_id,
            ),
            bush_admin_button(
                text=(
                    "🦁 Леви "
                    f"({state.lions_count})"
                ),
                action=(
                    BushAdminAction.LIONS
                ),
                bush_id=state.bush_id,
            ),
        ]
    )

    # -----------------------------------------------------
    # SCHEDULES
    # -----------------------------------------------------

    rows.append(
        [
            bush_admin_button(
                text="🕐 Графіки ТТ",
                action=(
                    BushAdminAction.SCHEDULES
                ),
                bush_id=state.bush_id,
            ),
            bush_admin_button(
                text="📊 Звіти",
                action=(
                    BushAdminAction.REPORTS
                ),
                bush_id=state.bush_id,
            ),
        ]
    )

    # -----------------------------------------------------
    # INVITES
    # -----------------------------------------------------

    rows.append(
        [
            bush_admin_button(
                text="🔗 Запрошення",
                action=(
                    BushAdminAction.INVITES
                ),
                bush_id=state.bush_id,
            )
        ]
    )

    # -----------------------------------------------------
    # REFRESH
    # -----------------------------------------------------

    rows.append(
        [
            bush_admin_button(
                text="🔄 Оновити",
                action=(
                    BushAdminAction.REFRESH
                ),
                bush_id=state.bush_id,
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


# =========================================================
# STORES
# =========================================================


def bush_admin_stores_keyboard(
    *,
    bush_id: int,
    stores: list[
        BushAdminStoreItem
    ],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Усі ТТ куща.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                inline_button(
                    text=store_button_text(
                        store
                    ),
                    callback=StoreCallback(
                        action=StoreAction.VIEW,
                        store_id=(
                            store.store_id
                        ),
                        page=page,
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=(
            BushAdminAction.STORES
        ),
    )

    rows.append(
        [
            inline_button(
                text="➕ Додати ТТ",
                callback=StoreCallback(
                    action=StoreAction.CREATE,
                    store_id=0,
                    page=0,
                ),
            )
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔄 Оновити",
                action=(
                    BushAdminAction.STORES
                ),
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔙 Назад",
                action=(
                    BushAdminAction.MENU
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORE CARD
# =========================================================


def bush_admin_store_keyboard(
    *,
    bush_id: int,
    store_id: int,
    is_active: bool = True,
) -> InlineKeyboardMarkup:
    """
    Керування конкретною ТТ.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = [
        [
            inline_button(
                text="🌅 Відкриття",
                callback=OpeningCallback(
                    action=(
                        OpeningAction.STATUS
                    ),
                    store_id=store_id,
                ),
            ),
            inline_button(
                text="🌙 Закриття",
                callback=ClosingCallback(
                    action=(
                        ClosingAction.STATUS
                    ),
                    store_id=store_id,
                ),
            ),
        ],
        [
            inline_button(
                text="📊 Звіт ТТ",
                callback=ReportCallback(
                    action=ReportAction.STORE,
                    ref_id=store_id,
                    page=0,
                ),
            )
        ],
        [
            inline_button(
                text="🕐 Графік",
                callback=ScheduleCallback(
                    action=ScheduleAction.VIEW,
                    store_id=store_id,
                    value=0,
                ),
            ),
            inline_button(
                text="👥 Працівники",
                callback=StoreCallback(
                    action=StoreAction.USERS,
                    store_id=store_id,
                    page=0,
                ),
            ),
        ],
        [
            inline_button(
                text="🌿 Змінити кущ",
                callback=StoreCallback(
                    action=StoreAction.BUSH,
                    store_id=store_id,
                    page=0,
                ),
            ),
            inline_button(
                text="⏰ Змінити кластер",
                callback=StoreCallback(
                    action=StoreAction.CLUSTER,
                    store_id=store_id,
                    page=0,
                ),
            ),
        ],
        [
            inline_button(
                text="✏️ Редагувати",
                callback=StoreCallback(
                    action=StoreAction.EDIT,
                    store_id=store_id,
                    page=0,
                ),
            )
        ],
    ]

    if is_active:
        rows.append(
            [
                inline_button(
                    text="⚫ Деактивувати ТТ",
                    callback=StoreCallback(
                        action=(
                            StoreAction.DEACTIVATE
                        ),
                        store_id=store_id,
                        page=0,
                    ),
                )
            ]
        )

    else:
        rows.append(
            [
                inline_button(
                    text="✅ Активувати ТТ",
                    callback=StoreCallback(
                        action=(
                            StoreAction.ACTIVATE
                        ),
                        store_id=store_id,
                        page=0,
                    ),
                )
            ]
        )

    rows.append(
        [
            bush_admin_button(
                text="🔙 До ТТ",
                action=(
                    BushAdminAction.STORES
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# OPENING MONITOR
# =========================================================


def bush_admin_opening_keyboard(
    *,
    bush_id: int,
    stores: list[
        BushAdminStoreItem
    ],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Моніторинг відкриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                inline_button(
                    text=store_button_text(
                        store
                    ),
                    callback=OpeningCallback(
                        action=(
                            OpeningAction.STATUS
                        ),
                        store_id=(
                            store.store_id
                        ),
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=(
            BushAdminAction.OPENING
        ),
    )

    rows.append(
        [
            bush_admin_button(
                text="⚠️ Запізнення",
                action=(
                    BushAdminAction.LATE
                ),
                bush_id=bush_id,
            ),
            bush_admin_button(
                text="🚨 Не відкрилися",
                action=(
                    BushAdminAction
                    .MISSING_OPENING
                ),
                bush_id=bush_id,
            ),
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔄 Оновити",
                action=(
                    BushAdminAction.OPENING
                ),
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔙 До меню",
                action=(
                    BushAdminAction.MENU
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# LATE
# =========================================================


def bush_admin_late_keyboard(
    *,
    bush_id: int,
    stores: list[
        BushAdminStoreItem
    ],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Тільки запізнення.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        minutes = max(
            0,
            store.lateness_minutes,
        )

        rows.append(
            [
                inline_button(
                    text=(
                        "⚠️ "
                        f"{store.display_name} "
                        f"· {minutes} хв"
                    ),
                    callback=OpeningCallback(
                        action=(
                            OpeningAction.STATUS
                        ),
                        store_id=(
                            store.store_id
                        ),
                    ),
                )
            ]
        )

    if not stores:
        rows.append(
            [
                bush_admin_button(
                    text="✅ Запізнень немає",
                    action=(
                        BushAdminAction.OPENING
                    ),
                    bush_id=bush_id,
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=(
            BushAdminAction.LATE
        ),
    )

    rows.append(
        [
            bush_admin_button(
                text="🔄 Оновити",
                action=(
                    BushAdminAction.LATE
                ),
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔙 До відкриття",
                action=(
                    BushAdminAction.OPENING
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# MISSING OPENING
# =========================================================


def bush_admin_missing_opening_keyboard(
    *,
    bush_id: int,
    stores: list[
        BushAdminStoreItem
    ],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    ТТ без check-in відкриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                inline_button(
                    text=(
                        "🚨 "
                        f"{store.display_name}"
                    ),
                    callback=OpeningCallback(
                        action=(
                            OpeningAction.STATUS
                        ),
                        store_id=(
                            store.store_id
                        ),
                    ),
                )
            ]
        )

    if not stores:
        rows.append(
            [
                bush_admin_button(
                    text="✅ Усі ТТ відкриті",
                    action=(
                        BushAdminAction.OPENING
                    ),
                    bush_id=bush_id,
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=(
            BushAdminAction
            .MISSING_OPENING
        ),
    )

    rows.append(
        [
            bush_admin_button(
                text="🔄 Оновити",
                action=(
                    BushAdminAction
                    .MISSING_OPENING
                ),
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔙 До відкриття",
                action=(
                    BushAdminAction.OPENING
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# OPENING MANUAL CONTROL
# =========================================================


def bush_admin_opening_control_keyboard(
    *,
    bush_id: int,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Детальна картка відкриття ТТ.

    Дозволяє адміну виконати
    ручне коригування.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🔄 Оновити статус",
                    callback=OpeningCallback(
                        action=(
                            OpeningAction.REFRESH
                        ),
                        store_id=store_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="✏️ Ручне коригування",
                    callback=OpeningCallback(
                        action=(
                            OpeningAction.MANUAL
                        ),
                        store_id=store_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="🏪 Картка ТТ",
                    callback=StoreCallback(
                        action=StoreAction.VIEW,
                        store_id=store_id,
                        page=0,
                    ),
                )
            ],
            [
                bush_admin_button(
                    text="🔙 До відкриття",
                    action=(
                        BushAdminAction.OPENING
                    ),
                    bush_id=bush_id,
                )
            ],
        ]
    )


# =========================================================
# CLOSING MONITOR
# =========================================================


def bush_admin_closing_keyboard(
    *,
    bush_id: int,
    stores: list[
        BushAdminStoreItem
    ],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Моніторинг закриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                inline_button(
                    text=store_button_text(
                        store
                    ),
                    callback=ClosingCallback(
                        action=(
                            ClosingAction.STATUS
                        ),
                        store_id=(
                            store.store_id
                        ),
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=(
            BushAdminAction.CLOSING
        ),
    )

    rows.append(
        [
            bush_admin_button(
                text="🚨 Не закрилися",
                action=(
                    BushAdminAction
                    .MISSING_CLOSING
                ),
                bush_id=bush_id,
            )
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔄 Оновити",
                action=(
                    BushAdminAction.CLOSING
                ),
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔙 До меню",
                action=(
                    BushAdminAction.MENU
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# MISSING CLOSING
# =========================================================


def bush_admin_missing_closing_keyboard(
    *,
    bush_id: int,
    stores: list[
        BushAdminStoreItem
    ],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    ТТ, які не завершили закриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                inline_button(
                    text=(
                        "🚨 "
                        f"{store.display_name}"
                    ),
                    callback=ClosingCallback(
                        action=(
                            ClosingAction.STATUS
                        ),
                        store_id=(
                            store.store_id
                        ),
                    ),
                )
            ]
        )

    if not stores:
        rows.append(
            [
                bush_admin_button(
                    text="✅ Усі ТТ закриті",
                    action=(
                        BushAdminAction.CLOSING
                    ),
                    bush_id=bush_id,
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=(
            BushAdminAction
            .MISSING_CLOSING
        ),
    )

    rows.append(
        [
            bush_admin_button(
                text="🔄 Оновити",
                action=(
                    BushAdminAction
                    .MISSING_CLOSING
                ),
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔙 До закриття",
                action=(
                    BushAdminAction.CLOSING
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# CLOSING CONTROL
# =========================================================


def bush_admin_closing_control_keyboard(
    *,
    bush_id: int,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Детальна картка закриття.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🔄 Оновити статус",
                    callback=ClosingCallback(
                        action=(
                            ClosingAction.REFRESH
                        ),
                        store_id=store_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="✏️ Ручне коригування",
                    callback=ClosingCallback(
                        action=(
                            ClosingAction.MANUAL
                        ),
                        store_id=store_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="🏪 Картка ТТ",
                    callback=StoreCallback(
                        action=StoreAction.VIEW,
                        store_id=store_id,
                        page=0,
                    ),
                )
            ],
            [
                bush_admin_button(
                    text="🔙 До закриття",
                    action=(
                        BushAdminAction.CLOSING
                    ),
                    bush_id=bush_id,
                )
            ],
        ]
    )


# =========================================================
# USERS
# =========================================================


def bush_admin_users_keyboard(
    *,
    bush_id: int,
    users: list[
        BushAdminUserItem
    ],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Працівники куща.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for user in users:
        rows.append(
            [
                inline_button(
                    text=user.button_text,
                    callback=UserCallback(
                        action=UserAction.VIEW,
                        user_id=user.user_id,
                        page=page,
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=(
            BushAdminAction.USERS
        ),
    )

    rows.append(
        [
            inline_button(
                text="🔍 Знайти користувача",
                callback=UserCallback(
                    action=UserAction.SEARCH,
                    user_id=0,
                    page=0,
                ),
            )
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔄 Оновити",
                action=(
                    BushAdminAction.USERS
                ),
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            bush_admin_button(
                text="🔙 До меню",
                action=(
                    BushAdminAction.MENU
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# LIONS
# =========================================================


def bush_admin_lions_keyboard(
    *,
    bush_id: int,
    lions: list[
        BushAdminUserItem
    ],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Леви куща.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for lion in lions:
        rows.append(
            [
                inline_button(
                    text=(
                        "🦁 "
                        f"{lion.button_text}"
                    ),
                    callback=UserCallback(
                        action=UserAction.VIEW,
                        user_id=lion.user_id,
                        page=page,
                    ),
                )
            ]
        )

    if not lions:
        rows.append(
            [
                bush_admin_button(
                    text="ℹ️ Левів ще немає",
                    action=(
                        BushAdminAction.MENU
                    ),
                    bush_id=bush_id,
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=(
            BushAdminAction.LIONS
        ),
    )

    rows.append(
        [
            bush_admin_button(
                text="🔙 До меню",
                action=(
                    BushAdminAction.MENU
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# USER CARD
# =========================================================


def bush_admin_user_keyboard(
    *,
    bush_id: int,
    user_id: int,
    is_active: bool = True,
    is_blocked: bool = False,
) -> InlineKeyboardMarkup:
    """
    Керування користувачем.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = [
        [
            inline_button(
                text="🏪 Прив’язки до ТТ",
                callback=BindingCallback(
                    action=BindingAction.VIEW,
                    user_id=user_id,
                    target_id=0,
                    binding_id=0,
                ),
            )
        ],
        [
            inline_button(
                text="➕ Додати ТТ",
                callback=BindingCallback(
                    action=BindingAction.ADD_STORE,
                    user_id=user_id,
                    target_id=0,
                    binding_id=0,
                ),
            )
        ],
        [
            inline_button(
                text="🌿 Прив’язка до куща",
                callback=UserCallback(
                    action=UserAction.BUSH,
                    user_id=user_id,
                    page=0,
                ),
            )
        ],
    ]

    if is_blocked:
        rows.append(
            [
                inline_button(
                    text="✅ Розблокувати",
                    callback=UserCallback(
                        action=UserAction.UNBLOCK,
                        user_id=user_id,
                        page=0,
                    ),
                )
            ]
        )

    else:
        rows.append(
            [
                inline_button(
                    text="⛔ Заблокувати",
                    callback=UserCallback(
                        action=UserAction.BLOCK,
                        user_id=user_id,
                        page=0,
                    ),
                )
            ]
        )

    if is_active:
        rows.append(
            [
                inline_button(
                    text="⚫ Деактивувати",
                    callback=UserCallback(
                        action=(
                            UserAction.DEACTIVATE
                        ),
                        user_id=user_id,
                        page=0,
                    ),
                )
            ]
        )

    else:
        rows.append(
            [
                inline_button(
                    text="✅ Активувати",
                    callback=UserCallback(
                        action=(
                            UserAction.ACTIVATE
                        ),
                        user_id=user_id,
                        page=0,
                    ),
                )
            ]
        )

    rows.append(
        [
            bush_admin_button(
                text="🔙 До працівників",
                action=(
                    BushAdminAction.USERS
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# SCHEDULES
# =========================================================


def bush_admin_schedules_keyboard(
    *,
    bush_id: int,
    stores: list[
        BushAdminStoreItem
    ],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Графіки ТТ.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        cluster = (
            f" · {store.cluster_text}"
            if store.cluster_text
            else ""
        )

        rows.append(
            [
                inline_button(
                    text=(
                        "🕐 "
                        f"{store.display_name}"
                        f"{cluster}"
                    ),
                    callback=ScheduleCallback(
                        action=ScheduleAction.VIEW,
                        store_id=(
                            store.store_id
                        ),
                        value=0,
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=(
            BushAdminAction.SCHEDULES
        ),
    )

    rows.append(
        [
            bush_admin_button(
                text="🔙 До меню",
                action=(
                    BushAdminAction.MENU
                ),
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORE SCHEDULE
# =========================================================


def bush_admin_store_schedule_keyboard(
    *,
    bush_id: int,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Управління графіком ТТ.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="📅 Змінити день тижня",
                    callback=ScheduleCallback(
                        action=(
                            ScheduleAction.WEEKDAY
                        ),
                        store_id=store_id,
                        value=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="📋 Скопіювати графік",
                    callback=ScheduleCallback(
                        action=ScheduleAction.COPY,
                        store_id=store_id,
                        value=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="⭐ Виняток на дату",
                    callback=ScheduleCallback(
                        action=(
                            ScheduleAction.EXCEPTION
                        ),
                        store_id=store_id,
                        value=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="⏰ Змінити кластер",
                    callback=ScheduleCallback(
                        action=(
                            ScheduleAction.CLUSTER
                        ),
                        store_id=store_id,
                        value=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="👁 Preview графіка",
                    callback=ScheduleCallback(
                        action=(
                            ScheduleAction.PREVIEW
                        ),
                        store_id=store_id,
                        value=0,
                    ),
                )
            ],
            [
                bush_admin_button(
                    text="🔙 До графіків",
                    action=(
                        BushAdminAction.SCHEDULES
                    ),
                    bush_id=bush_id,
                )
            ],
        ]
    )


# =========================================================
# REPORTS
# =========================================================


def bush_admin_reports_keyboard(
    *,
    bush_id: int,
) -> InlineKeyboardMarkup:
    """
    Звіти куща.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="📅 За сьогодні",
                    callback=ReportCallback(
                        action=ReportAction.DAILY,
                        ref_id=bush_id,
                        page=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="📆 За тиждень",
                    callback=ReportCallback(
                        action=ReportAction.WEEKLY,
                        ref_id=bush_id,
                        page=0,
                    ),
                ),
                inline_button(
                    text="🗓 За місяць",
                    callback=ReportCallback(
                        action=ReportAction.MONTHLY,
                        ref_id=bush_id,
                        page=0,
                    ),
                ),
            ],
            [
                inline_button(
                    text="🌿 Звіт куща",
                    callback=ReportCallback(
                        action=ReportAction.BUSH,
                        ref_id=bush_id,
                        page=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="📥 Excel",
                    callback=ReportCallback(
                        action=ReportAction.EXCEL,
                        ref_id=bush_id,
                        page=0,
                    ),
                )
            ],
            [
                bush_admin_button(
                    text="🔙 Назад",
                    action=(
                        BushAdminAction.MENU
                    ),
                    bush_id=bush_id,
                )
            ],
        ]
    )


# =========================================================
# INVITES
# =========================================================


def bush_admin_invites_keyboard(
    *,
    bush_id: int,
) -> InlineKeyboardMarkup:
    """
    Запрошення у кущ.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🌿 Створити для куща",
                    callback=InviteCallback(
                        action=InviteAction.BUSH,
                        target_id=bush_id,
                        invite_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🏪 Створити для ТТ",
                    callback=InviteCallback(
                        action=InviteAction.STORE,
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
                        target_id=bush_id,
                        invite_id=0,
                    ),
                )
            ],
            [
                bush_admin_button(
                    text="🔙 Назад",
                    action=(
                        BushAdminAction.MENU
                    ),
                    bush_id=bush_id,
                )
            ],
        ]
    )


# =========================================================
# MOVE STORE
# =========================================================


def bush_admin_move_store_keyboard(
    *,
    bush_id: int,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Перенесення ТТ між кущами.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🌿 Обрати новий кущ",
                    callback=BushCallback(
                        action=(
                            BushAction.MOVE_STORE
                        ),
                        bush_id=bush_id,
                        page=store_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="❌ Скасувати",
                    callback=StoreCallback(
                        action=StoreAction.VIEW,
                        store_id=store_id,
                        page=0,
                    ),
                )
            ],
        ]
    )


# =========================================================
# NO STORES
# =========================================================


def bush_admin_no_stores_keyboard(
    *,
    bush_id: int,
) -> InlineKeyboardMarkup:
    """
    Якщо в кущі немає ТТ.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="➕ Додати ТТ",
                    callback=StoreCallback(
                        action=StoreAction.CREATE,
                        store_id=0,
                        page=0,
                    ),
                )
            ],
            [
                bush_admin_button(
                    text="🔄 Оновити",
                    action=(
                        BushAdminAction.STORES
                    ),
                    bush_id=bush_id,
                )
            ],
            [
                bush_admin_button(
                    text="🔙 Назад",
                    action=(
                        BushAdminAction.MENU
                    ),
                    bush_id=bush_id,
                )
            ],
        ]
    )


# =========================================================
# MULTIPLE BUSHES
# =========================================================


def bush_admin_select_bush_keyboard(
    *,
    bushes: list[
        tuple[int, str]
    ],
) -> InlineKeyboardMarkup:
    """
    Якщо адмін має доступ
    до кількох кущів.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for bush_id, name in bushes:
        rows.append(
            [
                bush_admin_button(
                    text=(
                        f"🌿 {name}"
                    ),
                    action=(
                        BushAdminAction.DASHBOARD
                    ),
                    bush_id=bush_id,
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
# PAGINATION
# =========================================================


def append_pagination(
    *,
    rows: list[
        list[InlineKeyboardButton]
    ],
    bush_id: int,
    page: int,
    total_pages: int,
    action: BushAdminAction,
) -> None:
    """
    Пагінація.
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

    pagination_row: list[
        InlineKeyboardButton
    ] = []

    if normalized_page > 0:
        pagination_row.append(
            bush_admin_button(
                text="⬅️",
                action=action,
                bush_id=bush_id,
                page=(
                    normalized_page - 1
                ),
            )
        )

    pagination_row.append(
        bush_admin_button(
            text=(
                f"{normalized_page + 1}/"
                f"{total_pages}"
            ),
            action=action,
            bush_id=bush_id,
            page=normalized_page,
        )
    )

    if (
        normalized_page + 1
        < total_pages
    ):
        pagination_row.append(
            bush_admin_button(
                text="➡️",
                action=action,
                bush_id=bush_id,
                page=(
                    normalized_page + 1
                ),
            )
        )

    rows.append(
        pagination_row
    )


# =========================================================
# BACK
# =========================================================


def bush_admin_back_keyboard(
    *,
    bush_id: int,
) -> InlineKeyboardMarkup:
    """
    Повернення до dashboard.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                bush_admin_button(
                    text="🔙 Назад",
                    action=(
                        BushAdminAction.MENU
                    ),
                    bush_id=bush_id,
                )
            ]
        ]
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    # CALLBACK
    "BushAdminAction",
    "BushAdminCallback",

    # STATE
    "BushAdminStoreState",
    "BushAdminDashboardState",
    "BushAdminStoreItem",
    "BushAdminUserItem",

    # HELPERS
    "bush_admin_button",
    "store_state_icon",
    "store_button_text",

    # MAIN
    "bush_admin_main_keyboard",

    # STORES
    "bush_admin_stores_keyboard",
    "bush_admin_store_keyboard",
    "bush_admin_no_stores_keyboard",
    "bush_admin_move_store_keyboard",

    # OPENING
    "bush_admin_opening_keyboard",
    "bush_admin_late_keyboard",
    "bush_admin_missing_opening_keyboard",
    "bush_admin_opening_control_keyboard",

    # CLOSING
    "bush_admin_closing_keyboard",
    "bush_admin_missing_closing_keyboard",
    "bush_admin_closing_control_keyboard",

    # USERS
    "bush_admin_users_keyboard",
    "bush_admin_lions_keyboard",
    "bush_admin_user_keyboard",

    # SCHEDULE
    "bush_admin_schedules_keyboard",
    "bush_admin_store_schedule_keyboard",

    # REPORTS
    "bush_admin_reports_keyboard",

    # INVITES
    "bush_admin_invites_keyboard",

    # BUSH
    "bush_admin_select_bush_keyboard",

    # PAGINATION
    "append_pagination",

    # BACK
    "bush_admin_back_keyboard",
]