from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.keyboards.callbacks import (
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
# DIRECTOR CALLBACK
# =========================================================


class DirectorAction(StrEnum):
    """
    Дії директора.
    """

    MENU = "m"

    DASHBOARD = "dash"

    BUSHES = "bu"

    STORES = "st"

    USERS = "usr"

    OPENING = "op"

    LATE = "late"

    MISSING_OPENING = "mop"

    CLOSING = "cl"

    MISSING_CLOSING = "mcl"

    REPORTS = "rep"

    INVITES = "inv"

    REFRESH = "r"

    BACK = "b"


class DirectorCallback(
    CallbackData,
    prefix="dr",
):
    """
    dr:<action>:<ref_id>:<page>

    ref_id:
        bush_id / store_id / інший ID.

    0:
        вся мережа.
    """

    action: DirectorAction

    ref_id: int = 0

    page: int = 0


# =========================================================
# NETWORK STORE STATE
# =========================================================


class DirectorStoreState(StrEnum):
    """
    Стан ТТ для директора.
    """

    WAITING_OPENING = "waiting_opening"

    OPENED_ON_TIME = "opened_on_time"

    OPENED_LATE = "opened_late"

    WAITING_CLOSING = "waiting_closing"

    CLOSING_IN_PROGRESS = "closing_in_progress"

    CLOSED = "closed"

    INACTIVE = "inactive"


# =========================================================
# DASHBOARD
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class DirectorDashboardState:
    """
    Загальна статистика мережі.
    """

    total_stores: int

    active_stores: int

    bushes_count: int

    users_count: int

    opened_count: int

    late_count: int

    missing_opening_count: int

    closed_count: int

    missing_closing_count: int

    closing_in_progress_count: int = 0


# =========================================================
# BUSH ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class DirectorBushItem:
    """
    Один кущ у списку директора.
    """

    bush_id: int

    name: str

    total_stores: int

    opened_count: int = 0

    late_count: int = 0

    missing_opening_count: int = 0

    closed_count: int = 0

    missing_closing_count: int = 0

    is_active: bool = True

    @property
    def button_text(self) -> str:
        status = (
            "🌿"
            if self.is_active
            else "⚫"
        )

        return (
            f"{status} {self.name} "
            f"· {self.total_stores} ТТ"
        )


# =========================================================
# STORE ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class DirectorStoreItem:
    """
    ТТ у мережі.
    """

    store_id: int

    code: str

    name: str | None

    bush_name: str | None

    state: DirectorStoreState

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
class DirectorUserItem:
    """
    Користувач для списку директора.
    """

    user_id: int

    display_name: str

    role_text: str

    username: str | None = None

    is_active: bool = True

    is_blocked: bool = False

    @property
    def button_text(self) -> str:
        if self.is_blocked:
            icon = "❌"

        elif self.is_active:
            icon = "✅"

        else:
            icon = "⚫"

        username = (
            f" @{self.username.lstrip('@')}"
            if self.username
            else ""
        )

        return (
            f"{icon} "
            f"{self.display_name}"
            f"{username}"
        )


# =========================================================
# BUTTON
# =========================================================


def director_button(
    *,
    text: str,
    action: DirectorAction,
    ref_id: int = 0,
    page: int = 0,
) -> InlineKeyboardButton:
    """
    DirectorCallback button.
    """

    return inline_button(
        text=text,
        callback=DirectorCallback(
            action=action,
            ref_id=ref_id,
            page=page,
        ),
    )


# =========================================================
# STORE STATE
# =========================================================


def store_state_icon(
    state: DirectorStoreState,
) -> str:
    """
    Іконка статусу ТТ.
    """

    mapping = {
        DirectorStoreState.WAITING_OPENING:
            "⏳",

        DirectorStoreState.OPENED_ON_TIME:
            "✅",

        DirectorStoreState.OPENED_LATE:
            "⚠️",

        DirectorStoreState.WAITING_CLOSING:
            "🌙",

        DirectorStoreState.CLOSING_IN_PROGRESS:
            "🔄",

        DirectorStoreState.CLOSED:
            "✅",

        DirectorStoreState.INACTIVE:
            "⚫",
    }

    return mapping.get(
        state,
        "🏪",
    )


def store_button_text(
    store: DirectorStoreItem,
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
        == DirectorStoreState.OPENED_LATE
        and store.lateness_minutes > 0
    ):
        text += (
            f" · +{store.lateness_minutes} хв"
        )

    if store.bush_name:
        text += (
            f" · {store.bush_name}"
        )

    return text


# =========================================================
# MAIN MENU
# =========================================================


def director_main_keyboard(
    *,
    state: DirectorDashboardState,
) -> InlineKeyboardMarkup:
    """
    Головний dashboard директора.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    # -----------------------------------------------------
    # OPENING
    # -----------------------------------------------------

    rows.append(
        [
            director_button(
                text=(
                    "🌅 Відкриття "
                    f"{state.opened_count}/"
                    f"{state.active_stores}"
                ),
                action=DirectorAction.OPENING,
            )
        ]
    )

    if state.late_count > 0:
        rows.append(
            [
                director_button(
                    text=(
                        "⚠️ Запізнилися: "
                        f"{state.late_count}"
                    ),
                    action=DirectorAction.LATE,
                )
            ]
        )

    if state.missing_opening_count > 0:
        rows.append(
            [
                director_button(
                    text=(
                        "🚨 Не відкрилися: "
                        f"{state.missing_opening_count}"
                    ),
                    action=(
                        DirectorAction
                        .MISSING_OPENING
                    ),
                )
            ]
        )

    # -----------------------------------------------------
    # CLOSING
    # -----------------------------------------------------

    rows.append(
        [
            director_button(
                text=(
                    "🌙 Закриття "
                    f"{state.closed_count}/"
                    f"{state.active_stores}"
                ),
                action=DirectorAction.CLOSING,
            )
        ]
    )

    if state.missing_closing_count > 0:
        rows.append(
            [
                director_button(
                    text=(
                        "🚨 Не закрилися: "
                        f"{state.missing_closing_count}"
                    ),
                    action=(
                        DirectorAction
                        .MISSING_CLOSING
                    ),
                )
            ]
        )

    # -----------------------------------------------------
    # NETWORK
    # -----------------------------------------------------

    rows.append(
        [
            director_button(
                text=(
                    "🌿 Кущі "
                    f"({state.bushes_count})"
                ),
                action=DirectorAction.BUSHES,
            ),
            director_button(
                text=(
                    "🏪 ТТ "
                    f"({state.active_stores})"
                ),
                action=DirectorAction.STORES,
            ),
        ]
    )

    rows.append(
        [
            director_button(
                text=(
                    "👥 Користувачі "
                    f"({state.users_count})"
                ),
                action=DirectorAction.USERS,
            )
        ]
    )

    # -----------------------------------------------------
    # REPORTS
    # -----------------------------------------------------

    rows.append(
        [
            director_button(
                text="📊 Звіти мережі",
                action=DirectorAction.REPORTS,
            ),
            director_button(
                text="🔗 Запрошення",
                action=DirectorAction.INVITES,
            ),
        ]
    )

    # -----------------------------------------------------
    # REFRESH
    # -----------------------------------------------------

    rows.append(
        [
            director_button(
                text="🔄 Оновити",
                action=DirectorAction.REFRESH,
            )
        ]
    )

    rows.append(
        [
            inline_button(
                text="👤 Мій профіль",
                callback=MainMenuCallback(
                    action=MainMenuAction.PROFILE
                ),
            ),
            inline_button(
                text="ℹ️ Допомога",
                callback=MainMenuCallback(
                    action=MainMenuAction.HELP
                ),
            ),
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# BUSHES
# =========================================================


def director_bushes_keyboard(
    *,
    bushes: list[DirectorBushItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Список кущів мережі.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for bush in bushes:
        rows.append(
            [
                inline_button(
                    text=bush.button_text,
                    callback=BushCallback(
                        action=BushAction.VIEW,
                        bush_id=bush.bush_id,
                        page=page,
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        action=DirectorAction.BUSHES,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            director_button(
                text="🔄 Оновити",
                action=DirectorAction.BUSHES,
                page=page,
            )
        ]
    )

    rows.append(
        [
            director_button(
                text="🔙 До меню",
                action=DirectorAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# BUSH CARD
# =========================================================


def director_bush_keyboard(
    *,
    bush_id: int,
    is_active: bool = True,
) -> InlineKeyboardMarkup:
    """
    Картка конкретного куща.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = [
        [
            inline_button(
                text="🏪 Торгові точки",
                callback=BushCallback(
                    action=BushAction.STORES,
                    bush_id=bush_id,
                    page=0,
                ),
            )
        ],
        [
            inline_button(
                text="👥 Користувачі",
                callback=BushCallback(
                    action=BushAction.USERS,
                    bush_id=bush_id,
                    page=0,
                ),
            )
        ],
        [
            inline_button(
                text="📊 Статистика",
                callback=BushCallback(
                    action=BushAction.STATS,
                    bush_id=bush_id,
                    page=0,
                ),
            )
        ],
        [
            inline_button(
                text="📄 Звіт куща",
                callback=ReportCallback(
                    action=ReportAction.BUSH,
                    ref_id=bush_id,
                    page=0,
                ),
            )
        ],
    ]

    if is_active:
        rows.append(
            [
                inline_button(
                    text="⚫ Деактивувати кущ",
                    callback=BushCallback(
                        action=BushAction.DEACTIVATE,
                        bush_id=bush_id,
                        page=0,
                    ),
                )
            ]
        )

    else:
        rows.append(
            [
                inline_button(
                    text="✅ Активувати кущ",
                    callback=BushCallback(
                        action=BushAction.ACTIVATE,
                        bush_id=bush_id,
                        page=0,
                    ),
                )
            ]
        )

    rows.append(
        [
            director_button(
                text="🔙 До кущів",
                action=DirectorAction.BUSHES,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORES
# =========================================================


def director_stores_keyboard(
    *,
    stores: list[DirectorStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Усі ТТ мережі.
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
                        store_id=store.store_id,
                        page=page,
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        action=DirectorAction.STORES,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            inline_button(
                text="🔍 Пошук ТТ",
                callback=StoreCallback(
                    action=StoreAction.SEARCH,
                    store_id=0,
                    page=0,
                ),
            )
        ]
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
            director_button(
                text="🔄 Оновити",
                action=DirectorAction.STORES,
                page=page,
            )
        ]
    )

    rows.append(
        [
            director_button(
                text="🔙 До меню",
                action=DirectorAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORE CARD
# =========================================================


def director_store_keyboard(
    *,
    store_id: int,
    is_active: bool = True,
) -> InlineKeyboardMarkup:
    """
    Картка ТТ для директора.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = [
        [
            inline_button(
                text="🌅 Відкриття",
                callback=OpeningCallback(
                    action=OpeningAction.STATUS,
                    store_id=store_id,
                ),
            ),
            inline_button(
                text="🌙 Закриття",
                callback=ClosingCallback(
                    action=ClosingAction.STATUS,
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
                text="👥 Працівники",
                callback=StoreCallback(
                    action=StoreAction.USERS,
                    store_id=store_id,
                    page=0,
                ),
            ),
            inline_button(
                text="🕐 Графік",
                callback=StoreCallback(
                    action=StoreAction.SCHEDULE,
                    store_id=store_id,
                    page=0,
                ),
            ),
        ],
        [
            inline_button(
                text="🌿 Кущ",
                callback=StoreCallback(
                    action=StoreAction.BUSH,
                    store_id=store_id,
                    page=0,
                ),
            ),
            inline_button(
                text="⏰ Кластер",
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
                    text="⚫ Деактивувати",
                    callback=StoreCallback(
                        action=StoreAction.DEACTIVATE,
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
                    text="✅ Активувати",
                    callback=StoreCallback(
                        action=StoreAction.ACTIVATE,
                        store_id=store_id,
                        page=0,
                    ),
                )
            ]
        )

    rows.append(
        [
            director_button(
                text="🔙 До ТТ",
                action=DirectorAction.STORES,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# OPENING
# =========================================================


def director_opening_keyboard(
    *,
    stores: list[DirectorStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Live відкриття всієї мережі.
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
                        action=OpeningAction.STATUS,
                        store_id=store.store_id,
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        action=DirectorAction.OPENING,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            director_button(
                text="⚠️ Запізнення",
                action=DirectorAction.LATE,
            ),
            director_button(
                text="🚨 Не відкрилися",
                action=(
                    DirectorAction
                    .MISSING_OPENING
                ),
            ),
        ]
    )

    rows.append(
        [
            director_button(
                text="🔄 Оновити",
                action=DirectorAction.OPENING,
                page=page,
            )
        ]
    )

    rows.append(
        [
            director_button(
                text="🔙 До меню",
                action=DirectorAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# LATE
# =========================================================


def director_late_keyboard(
    *,
    stores: list[DirectorStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Усі ТТ із запізненнями.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        minutes = max(
            0,
            store.lateness_minutes,
        )

        bush = (
            f" · {store.bush_name}"
            if store.bush_name
            else ""
        )

        rows.append(
            [
                inline_button(
                    text=(
                        f"⚠️ {store.display_name}"
                        f" · {minutes} хв"
                        f"{bush}"
                    ),
                    callback=OpeningCallback(
                        action=OpeningAction.STATUS,
                        store_id=store.store_id,
                    ),
                )
            ]
        )

    if not stores:
        rows.append(
            [
                director_button(
                    text="✅ Запізнень немає",
                    action=DirectorAction.OPENING,
                )
            ]
        )

    append_pagination(
        rows=rows,
        action=DirectorAction.LATE,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            director_button(
                text="🔄 Оновити",
                action=DirectorAction.LATE,
                page=page,
            )
        ]
    )

    rows.append(
        [
            director_button(
                text="🔙 До відкриття",
                action=DirectorAction.OPENING,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# MISSING OPENING
# =========================================================


def director_missing_opening_keyboard(
    *,
    stores: list[DirectorStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    ТТ, які не відмітили відкриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        bush = (
            f" · {store.bush_name}"
            if store.bush_name
            else ""
        )

        rows.append(
            [
                inline_button(
                    text=(
                        f"🚨 {store.display_name}"
                        f"{bush}"
                    ),
                    callback=OpeningCallback(
                        action=OpeningAction.STATUS,
                        store_id=store.store_id,
                    ),
                )
            ]
        )

    if not stores:
        rows.append(
            [
                director_button(
                    text="✅ Усі ТТ відкрилися",
                    action=DirectorAction.OPENING,
                )
            ]
        )

    append_pagination(
        rows=rows,
        action=(
            DirectorAction.MISSING_OPENING
        ),
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            director_button(
                text="🔄 Оновити",
                action=(
                    DirectorAction.MISSING_OPENING
                ),
                page=page,
            )
        ]
    )

    rows.append(
        [
            director_button(
                text="🔙 До відкриття",
                action=DirectorAction.OPENING,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# CLOSING
# =========================================================


def director_closing_keyboard(
    *,
    stores: list[DirectorStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Live закриття мережі.
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
                        action=ClosingAction.STATUS,
                        store_id=store.store_id,
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        action=DirectorAction.CLOSING,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            director_button(
                text="🚨 Не закрилися",
                action=(
                    DirectorAction
                    .MISSING_CLOSING
                ),
            )
        ]
    )

    rows.append(
        [
            director_button(
                text="🔄 Оновити",
                action=DirectorAction.CLOSING,
                page=page,
            )
        ]
    )

    rows.append(
        [
            director_button(
                text="🔙 До меню",
                action=DirectorAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# MISSING CLOSING
# =========================================================


def director_missing_closing_keyboard(
    *,
    stores: list[DirectorStoreItem],
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
        bush = (
            f" · {store.bush_name}"
            if store.bush_name
            else ""
        )

        rows.append(
            [
                inline_button(
                    text=(
                        f"🚨 {store.display_name}"
                        f"{bush}"
                    ),
                    callback=ClosingCallback(
                        action=ClosingAction.STATUS,
                        store_id=store.store_id,
                    ),
                )
            ]
        )

    if not stores:
        rows.append(
            [
                director_button(
                    text="✅ Усі ТТ закрилися",
                    action=DirectorAction.CLOSING,
                )
            ]
        )

    append_pagination(
        rows=rows,
        action=(
            DirectorAction.MISSING_CLOSING
        ),
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            director_button(
                text="🔄 Оновити",
                action=(
                    DirectorAction.MISSING_CLOSING
                ),
                page=page,
            )
        ]
    )

    rows.append(
        [
            director_button(
                text="🔙 До закриття",
                action=DirectorAction.CLOSING,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# USERS
# =========================================================


def director_users_keyboard(
    *,
    users: list[DirectorUserItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Користувачі мережі.
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
        action=DirectorAction.USERS,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            inline_button(
                text="🕐 Очікують підтвердження",
                callback=UserCallback(
                    action=UserAction.PENDING,
                    user_id=0,
                    page=0,
                ),
            )
        ]
    )

    rows.append(
        [
            inline_button(
                text="🔍 Пошук",
                callback=UserCallback(
                    action=UserAction.SEARCH,
                    user_id=0,
                    page=0,
                ),
            ),
            inline_button(
                text="⛔ Заблоковані",
                callback=UserCallback(
                    action=UserAction.BLOCKED,
                    user_id=0,
                    page=0,
                ),
            ),
        ]
    )

    rows.append(
        [
            director_button(
                text="🔄 Оновити",
                action=DirectorAction.USERS,
                page=page,
            )
        ]
    )

    rows.append(
        [
            director_button(
                text="🔙 До меню",
                action=DirectorAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# USER CARD
# =========================================================


def director_user_keyboard(
    *,
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
                text="🎭 Змінити роль",
                callback=UserCallback(
                    action=UserAction.ROLE,
                    user_id=user_id,
                    page=0,
                ),
            )
        ],
        [
            inline_button(
                text="🏪 Прив’язки ТТ",
                callback=UserCallback(
                    action=UserAction.STORE,
                    user_id=user_id,
                    page=0,
                ),
            ),
            inline_button(
                text="🌿 Прив’язки кущів",
                callback=UserCallback(
                    action=UserAction.BUSH,
                    user_id=user_id,
                    page=0,
                ),
            ),
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
                        action=UserAction.DEACTIVATE,
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
                        action=UserAction.ACTIVATE,
                        user_id=user_id,
                        page=0,
                    ),
                )
            ]
        )

    rows.append(
        [
            director_button(
                text="🔙 До користувачів",
                action=DirectorAction.USERS,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# REPORTS
# =========================================================


def director_reports_keyboard(
) -> InlineKeyboardMarkup:
    """
    Звіти всієї мережі.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="📅 Сьогодні",
                    callback=ReportCallback(
                        action=ReportAction.DAILY,
                        ref_id=0,
                        page=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="📆 Тиждень",
                    callback=ReportCallback(
                        action=ReportAction.WEEKLY,
                        ref_id=0,
                        page=0,
                    ),
                ),
                inline_button(
                    text="🗓 Місяць",
                    callback=ReportCallback(
                        action=ReportAction.MONTHLY,
                        ref_id=0,
                        page=0,
                    ),
                ),
            ],
            [
                inline_button(
                    text="🌐 Вся мережа",
                    callback=ReportCallback(
                        action=ReportAction.NETWORK,
                        ref_id=0,
                        page=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🌿 Обрати кущ",
                    callback=ReportCallback(
                        action=ReportAction.BUSH,
                        ref_id=0,
                        page=0,
                    ),
                ),
                inline_button(
                    text="🏪 Обрати ТТ",
                    callback=ReportCallback(
                        action=ReportAction.STORE,
                        ref_id=0,
                        page=0,
                    ),
                ),
            ],
            [
                inline_button(
                    text="📥 Excel",
                    callback=ReportCallback(
                        action=ReportAction.EXCEL,
                        ref_id=0,
                        page=0,
                    ),
                )
            ],
            [
                director_button(
                    text="🔙 Назад",
                    action=DirectorAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# INVITES
# =========================================================


def director_invites_keyboard(
) -> InlineKeyboardMarkup:
    """
    Запрошення для мережі.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🏪 Для ТТ",
                    callback=InviteCallback(
                        action=InviteAction.STORE,
                        target_id=0,
                        invite_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🌿 Для куща",
                    callback=InviteCallback(
                        action=InviteAction.BUSH,
                        target_id=0,
                        invite_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🏢 Для директора",
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
                director_button(
                    text="🔙 Назад",
                    action=DirectorAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# EMPTY STATES
# =========================================================


def director_no_stores_keyboard(
) -> InlineKeyboardMarkup:
    """
    Якщо ТТ немає.
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
                director_button(
                    text="🔄 Оновити",
                    action=DirectorAction.STORES,
                )
            ],
            [
                director_button(
                    text="🔙 До меню",
                    action=DirectorAction.MENU,
                )
            ],
        ]
    )


def director_no_bushes_keyboard(
) -> InlineKeyboardMarkup:
    """
    Якщо кущів немає.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="➕ Створити кущ",
                    callback=BushCallback(
                        action=BushAction.CREATE,
                        bush_id=0,
                        page=0,
                    ),
                )
            ],
            [
                director_button(
                    text="🔄 Оновити",
                    action=DirectorAction.BUSHES,
                )
            ],
            [
                director_button(
                    text="🔙 До меню",
                    action=DirectorAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# PAGINATION
# =========================================================


def append_pagination(
    *,
    rows: list[
        list[InlineKeyboardButton]
    ],
    action: DirectorAction,
    page: int,
    total_pages: int,
    ref_id: int = 0,
) -> None:
    """
    Пагінація DirectorCallback.
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
            director_button(
                text="⬅️",
                action=action,
                ref_id=ref_id,
                page=normalized_page - 1,
            )
        )

    pagination_row.append(
        director_button(
            text=(
                f"{normalized_page + 1}/"
                f"{total_pages}"
            ),
            action=action,
            ref_id=ref_id,
            page=normalized_page,
        )
    )

    if (
        normalized_page + 1
        < total_pages
    ):
        pagination_row.append(
            director_button(
                text="➡️",
                action=action,
                ref_id=ref_id,
                page=normalized_page + 1,
            )
        )

    rows.append(
        pagination_row
    )


# =========================================================
# BACK
# =========================================================


def director_back_keyboard(
) -> InlineKeyboardMarkup:
    """
    Назад у dashboard.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                director_button(
                    text="🔙 Назад",
                    action=DirectorAction.MENU,
                )
            ]
        ]
    )


# =========================================================
# HOME
# =========================================================


def director_home_keyboard(
) -> InlineKeyboardMarkup:
    """
    Головне меню.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                home_button()
            ]
        ]
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    # CALLBACK
    "DirectorAction",
    "DirectorCallback",

    # STATE
    "DirectorStoreState",
    "DirectorDashboardState",
    "DirectorBushItem",
    "DirectorStoreItem",
    "DirectorUserItem",

    # HELPERS
    "director_button",
    "store_state_icon",
    "store_button_text",

    # MAIN
    "director_main_keyboard",

    # BUSHES
    "director_bushes_keyboard",
    "director_bush_keyboard",
    "director_no_bushes_keyboard",

    # STORES
    "director_stores_keyboard",
    "director_store_keyboard",
    "director_no_stores_keyboard",

    # OPENING
    "director_opening_keyboard",
    "director_late_keyboard",
    "director_missing_opening_keyboard",

    # CLOSING
    "director_closing_keyboard",
    "director_missing_closing_keyboard",

    # USERS
    "director_users_keyboard",
    "director_user_keyboard",

    # REPORTS
    "director_reports_keyboard",

    # INVITES
    "director_invites_keyboard",

    # PAGINATION
    "append_pagination",

    # NAVIGATION
    "director_back_keyboard",
    "director_home_keyboard",
]