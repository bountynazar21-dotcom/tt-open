from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.keyboards.callbacks import (
    AuditActionCallback,
    AuditCallback,
    BushAction,
    BushCallback,
    ClusterAction,
    ClusterCallback,
    ClosingAction,
    ClosingCallback,
    GroupAction,
    GroupCallback,
    ImportAction,
    ImportCallback,
    InviteAction,
    InviteCallback,
    MainMenuAction,
    MainMenuCallback,
    OpeningAction,
    OpeningCallback,
    ReportAction,
    ReportCallback,
    SettingsAction,
    SettingsCallback,
    StoreAction,
    StoreCallback,
    UserAction,
    UserCallback,
    UserRoleAction,
    UserRoleCallback,
)
from app.keyboards.common import (
    home_button,
    inline_button,
)


# =========================================================
# ROOT ADMIN CALLBACK
# =========================================================


class RootAdminAction(StrEnum):
    """
    Дії ROOT_ADMIN.
    """

    MENU = "m"

    DASHBOARD = "dash"

    NETWORK = "net"

    STORES = "st"

    BUSHES = "bu"

    CLUSTERS = "ct"

    USERS = "usr"

    PENDING_USERS = "pend"

    OPENING = "op"

    LATE = "late"

    MISSING_OPENING = "mop"

    CLOSING = "cl"

    MISSING_CLOSING = "mcl"

    REPORTS = "rep"

    IMPORT = "im"

    INVITES = "inv"

    SETTINGS = "set"

    GROUPS = "grp"

    AUDIT = "audit"

    SYSTEM = "sys"

    REFRESH = "r"

    BACK = "b"


class RootAdminCallback(
    CallbackData,
    prefix="ra",
):
    """
    ra:<action>:<ref_id>:<page>

    ref_id:
        store_id
        bush_id
        cluster_id
        user_id
        etc.

    0:
        глобальний контекст.
    """

    action: RootAdminAction

    ref_id: int = 0

    page: int = 0


# =========================================================
# STORE STATE
# =========================================================


class RootStoreState(StrEnum):
    """
    Стан ТТ у live-monitor.
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
# DASHBOARD
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class RootAdminDashboardState:
    """
    Основні цифри ROOT dashboard.
    """

    total_stores: int

    active_stores: int

    inactive_stores: int

    bushes_count: int

    clusters_count: int

    users_count: int

    pending_users_count: int

    blocked_users_count: int

    opened_count: int

    late_count: int

    missing_opening_count: int

    closed_count: int

    missing_closing_count: int

    closing_in_progress_count: int = 0

    bot_enabled: bool = True

    maintenance_enabled: bool = False


# =========================================================
# STORE ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class RootStoreItem:
    """
    ТТ для списків ROOT_ADMIN.
    """

    store_id: int

    code: str

    name: str | None

    bush_name: str | None

    cluster_text: str | None

    state: RootStoreState

    lateness_minutes: int = 0

    is_active: bool = True

    @property
    def display_name(self) -> str:
        if self.name:
            return (
                f"{self.code} · {self.name}"
            )

        return self.code


# =========================================================
# BUSH ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class RootBushItem:
    """
    Кущ.
    """

    bush_id: int

    name: str

    stores_count: int = 0

    users_count: int = 0

    is_active: bool = True

    @property
    def button_text(self) -> str:
        icon = (
            "🌿"
            if self.is_active
            else "⚫"
        )

        return (
            f"{icon} {self.name} "
            f"· {self.stores_count} ТТ"
        )


# =========================================================
# CLUSTER ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class RootClusterItem:
    """
    Кластер.
    """

    cluster_id: int

    name: str

    opening_time: str

    stores_count: int = 0

    is_active: bool = True

    @property
    def button_text(self) -> str:
        icon = (
            "⏰"
            if self.is_active
            else "⚫"
        )

        return (
            f"{icon} {self.opening_time} "
            f"· {self.name} "
            f"· {self.stores_count} ТТ"
        )


# =========================================================
# USER ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class RootUserItem:
    """
    Користувач.
    """

    user_id: int

    display_name: str

    role_text: str

    username: str | None = None

    is_active: bool = True

    is_blocked: bool = False

    is_pending: bool = False

    @property
    def button_text(self) -> str:
        if self.is_pending:
            icon = "⏳"

        elif self.is_blocked:
            icon = "⛔"

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
            f"{icon} {self.display_name}"
            f"{username} · {self.role_text}"
        )


# =========================================================
# BUTTON
# =========================================================


def root_admin_button(
    *,
    text: str,
    action: RootAdminAction,
    ref_id: int = 0,
    page: int = 0,
) -> InlineKeyboardButton:
    """
    Створює RootAdminCallback.
    """

    return inline_button(
        text=text,
        callback=RootAdminCallback(
            action=action,
            ref_id=ref_id,
            page=page,
        ),
    )


# =========================================================
# STORE STATUS HELPERS
# =========================================================


def root_store_state_icon(
    state: RootStoreState,
) -> str:
    """
    Іконка стану ТТ.
    """

    mapping = {
        RootStoreState
        .WAITING_OPENING: "⏳",

        RootStoreState
        .OPENED_ON_TIME: "✅",

        RootStoreState
        .OPENED_LATE: "⚠️",

        RootStoreState
        .WAITING_CLOSING: "🌙",

        RootStoreState
        .CLOSING_IN_PROGRESS: "🔄",

        RootStoreState
        .CLOSED: "✅",

        RootStoreState
        .INACTIVE: "⚫",
    }

    return mapping.get(
        state,
        "🏪",
    )


def root_store_button_text(
    store: RootStoreItem,
) -> str:
    """
    Текст ТТ у списках.
    """

    icon = root_store_state_icon(
        store.state
    )

    text = (
        f"{icon} {store.display_name}"
    )

    if (
        store.state
        == RootStoreState.OPENED_LATE
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
# MAIN DASHBOARD
# =========================================================


def root_admin_main_keyboard(
    *,
    state: RootAdminDashboardState,
) -> InlineKeyboardMarkup:
    """
    Головна панель ROOT_ADMIN.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    # -----------------------------------------------------
    # BOT STATE
    # -----------------------------------------------------

    if not state.bot_enabled:
        rows.append(
            [
                root_admin_button(
                    text="🔴 БОТ ВИМКНЕНО",
                    action=(
                        RootAdminAction.SYSTEM
                    ),
                )
            ]
        )

    elif state.maintenance_enabled:
        rows.append(
            [
                root_admin_button(
                    text="🟠 РЕЖИМ ОБСЛУГОВУВАННЯ",
                    action=(
                        RootAdminAction.SYSTEM
                    ),
                )
            ]
        )

    # -----------------------------------------------------
    # OPENING
    # -----------------------------------------------------

    rows.append(
        [
            root_admin_button(
                text=(
                    "🌅 Відкриття "
                    f"{state.opened_count}/"
                    f"{state.active_stores}"
                ),
                action=(
                    RootAdminAction.OPENING
                ),
            )
        ]
    )

    if state.late_count > 0:
        rows.append(
            [
                root_admin_button(
                    text=(
                        "⚠️ Запізнилися: "
                        f"{state.late_count}"
                    ),
                    action=(
                        RootAdminAction.LATE
                    ),
                )
            ]
        )

    if (
        state.missing_opening_count
        > 0
    ):
        rows.append(
            [
                root_admin_button(
                    text=(
                        "🚨 Не відкрилися: "
                        f"{state.missing_opening_count}"
                    ),
                    action=(
                        RootAdminAction
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
            root_admin_button(
                text=(
                    "🌙 Закриття "
                    f"{state.closed_count}/"
                    f"{state.active_stores}"
                ),
                action=(
                    RootAdminAction.CLOSING
                ),
            )
        ]
    )

    if (
        state.missing_closing_count
        > 0
    ):
        rows.append(
            [
                root_admin_button(
                    text=(
                        "🚨 Не закрилися: "
                        f"{state.missing_closing_count}"
                    ),
                    action=(
                        RootAdminAction
                        .MISSING_CLOSING
                    ),
                )
            ]
        )

    # -----------------------------------------------------
    # STRUCTURE
    # -----------------------------------------------------

    rows.append(
        [
            root_admin_button(
                text=(
                    "🏪 ТТ "
                    f"({state.active_stores})"
                ),
                action=(
                    RootAdminAction.STORES
                ),
            ),
            root_admin_button(
                text=(
                    "🌿 Кущі "
                    f"({state.bushes_count})"
                ),
                action=(
                    RootAdminAction.BUSHES
                ),
            ),
        ]
    )

    rows.append(
        [
            root_admin_button(
                text=(
                    "⏰ Кластери "
                    f"({state.clusters_count})"
                ),
                action=(
                    RootAdminAction.CLUSTERS
                ),
            ),
            root_admin_button(
                text=(
                    "👥 Люди "
                    f"({state.users_count})"
                ),
                action=(
                    RootAdminAction.USERS
                ),
            ),
        ]
    )

    # -----------------------------------------------------
    # PENDING USERS
    # -----------------------------------------------------

    if (
        state.pending_users_count
        > 0
    ):
        rows.append(
            [
                root_admin_button(
                    text=(
                        "🕐 Нові заявки: "
                        f"{state.pending_users_count}"
                    ),
                    action=(
                        RootAdminAction
                        .PENDING_USERS
                    ),
                )
            ]
        )

    # -----------------------------------------------------
    # REPORTS / IMPORT
    # -----------------------------------------------------

    rows.append(
        [
            root_admin_button(
                text="📊 Звіти",
                action=(
                    RootAdminAction.REPORTS
                ),
            ),
            root_admin_button(
                text="📥 Імпорт",
                action=(
                    RootAdminAction.IMPORT
                ),
            ),
        ]
    )

    # -----------------------------------------------------
    # MANAGEMENT
    # -----------------------------------------------------

    rows.append(
        [
            root_admin_button(
                text="🔗 Запрошення",
                action=(
                    RootAdminAction.INVITES
                ),
            ),
            root_admin_button(
                text="💬 Telegram",
                action=(
                    RootAdminAction.GROUPS
                ),
            ),
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="⚙️ Налаштування",
                action=(
                    RootAdminAction.SETTINGS
                ),
            ),
            root_admin_button(
                text="🧾 Audit Log",
                action=(
                    RootAdminAction.AUDIT
                ),
            ),
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🛠 Система",
                action=(
                    RootAdminAction.SYSTEM
                ),
            )
        ]
    )

    # -----------------------------------------------------
    # REFRESH
    # -----------------------------------------------------

    rows.append(
        [
            root_admin_button(
                text="🔄 Оновити",
                action=(
                    RootAdminAction.REFRESH
                ),
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORES
# =========================================================


def root_admin_stores_keyboard(
    *,
    stores: list[RootStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Усі ТТ.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                inline_button(
                    text=(
                        root_store_button_text(
                            store
                        )
                    ),
                    callback=StoreCallback(
                        action=StoreAction.VIEW,
                        store_id=store.store_id,
                        page=page,
                    ),
                )
            ]
        )

    append_root_pagination(
        rows=rows,
        action=RootAdminAction.STORES,
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
            ),
            inline_button(
                text="➕ Створити",
                callback=StoreCallback(
                    action=StoreAction.CREATE,
                    store_id=0,
                    page=0,
                ),
            ),
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🔄 Оновити",
                action=RootAdminAction.STORES,
                page=page,
            )
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🔙 До адмінки",
                action=RootAdminAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORE CARD
# =========================================================


def root_admin_store_keyboard(
    *,
    store_id: int,
    is_active: bool,
) -> InlineKeyboardMarkup:
    """
    Повне керування ТТ.
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
                text="📊 Звіти",
                callback=ReportCallback(
                    action=ReportAction.STORE,
                    ref_id=store_id,
                    page=0,
                ),
            )
        ],
        [
            inline_button(
                text="👥 Користувачі",
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
            root_admin_button(
                text="🔙 До ТТ",
                action=RootAdminAction.STORES,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# BUSHES
# =========================================================


def root_admin_bushes_keyboard(
    *,
    bushes: list[RootBushItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Усі кущі.
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

    append_root_pagination(
        rows=rows,
        action=RootAdminAction.BUSHES,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            inline_button(
                text="➕ Створити кущ",
                callback=BushCallback(
                    action=BushAction.CREATE,
                    bush_id=0,
                    page=0,
                ),
            )
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🔄 Оновити",
                action=RootAdminAction.BUSHES,
                page=page,
            )
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🔙 До адмінки",
                action=RootAdminAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# BUSH CARD
# =========================================================


def root_admin_bush_keyboard(
    *,
    bush_id: int,
    is_active: bool,
) -> InlineKeyboardMarkup:
    """
    Повна картка куща.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = [
        [
            inline_button(
                text="🏪 ТТ куща",
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
                text="✏️ Редагувати",
                callback=BushCallback(
                    action=BushAction.EDIT,
                    bush_id=bush_id,
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
                    callback=BushCallback(
                        action=(
                            BushAction.DEACTIVATE
                        ),
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
                    text="✅ Активувати",
                    callback=BushCallback(
                        action=(
                            BushAction.ACTIVATE
                        ),
                        bush_id=bush_id,
                        page=0,
                    ),
                )
            ]
        )

    rows.append(
        [
            root_admin_button(
                text="🔙 До кущів",
                action=RootAdminAction.BUSHES,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# CLUSTERS
# =========================================================


def root_admin_clusters_keyboard(
    *,
    clusters: list[RootClusterItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Кластери відкриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for cluster in clusters:
        rows.append(
            [
                inline_button(
                    text=cluster.button_text,
                    callback=ClusterCallback(
                        action=ClusterAction.VIEW,
                        cluster_id=cluster.cluster_id,
                        page=page,
                    ),
                )
            ]
        )

    append_root_pagination(
        rows=rows,
        action=RootAdminAction.CLUSTERS,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            inline_button(
                text="➕ Створити кластер",
                callback=ClusterCallback(
                    action=ClusterAction.CREATE,
                    cluster_id=0,
                    page=0,
                ),
            )
        ]
    )

    rows.append(
        [
            inline_button(
                text="⚙️ Стандартні 07/08/09/10",
                callback=ClusterCallback(
                    action=ClusterAction.DEFAULTS,
                    cluster_id=0,
                    page=0,
                ),
            )
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🔙 До адмінки",
                action=RootAdminAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# CLUSTER CARD
# =========================================================


def root_admin_cluster_keyboard(
    *,
    cluster_id: int,
    is_active: bool,
) -> InlineKeyboardMarkup:
    """
    Картка кластера.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = [
        [
            inline_button(
                text="🏪 ТТ кластера",
                callback=ClusterCallback(
                    action=ClusterAction.STORES,
                    cluster_id=cluster_id,
                    page=0,
                ),
            )
        ],
        [
            inline_button(
                text="✏️ Редагувати",
                callback=ClusterCallback(
                    action=ClusterAction.EDIT,
                    cluster_id=cluster_id,
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
                    callback=ClusterCallback(
                        action=(
                            ClusterAction.DEACTIVATE
                        ),
                        cluster_id=cluster_id,
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
                    callback=ClusterCallback(
                        action=(
                            ClusterAction.ACTIVATE
                        ),
                        cluster_id=cluster_id,
                        page=0,
                    ),
                )
            ]
        )

    rows.append(
        [
            root_admin_button(
                text="🔙 До кластерів",
                action=RootAdminAction.CLUSTERS,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# USERS
# =========================================================


def root_admin_users_keyboard(
    *,
    users: list[RootUserItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Всі користувачі.
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

    append_root_pagination(
        rows=rows,
        action=RootAdminAction.USERS,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            inline_button(
                text="🕐 Очікують",
                callback=UserCallback(
                    action=UserAction.PENDING,
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
            inline_button(
                text="🔍 Пошук користувача",
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
            root_admin_button(
                text="🔙 До адмінки",
                action=RootAdminAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# PENDING USERS
# =========================================================


def root_admin_pending_users_keyboard(
    *,
    users: list[RootUserItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Нові заявки.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for user in users:
        rows.append(
            [
                inline_button(
                    text=(
                        f"⏳ {user.display_name}"
                    ),
                    callback=UserCallback(
                        action=UserAction.VIEW,
                        user_id=user.user_id,
                        page=page,
                    ),
                )
            ]
        )

    if not users:
        rows.append(
            [
                root_admin_button(
                    text="✅ Нових заявок немає",
                    action=RootAdminAction.USERS,
                )
            ]
        )

    append_root_pagination(
        rows=rows,
        action=(
            RootAdminAction.PENDING_USERS
        ),
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            root_admin_button(
                text="🔄 Оновити",
                action=(
                    RootAdminAction.PENDING_USERS
                ),
                page=page,
            )
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🔙 До користувачів",
                action=RootAdminAction.USERS,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# PENDING USER CARD
# =========================================================


def root_admin_pending_user_keyboard(
    *,
    user_id: int,
) -> InlineKeyboardMarkup:
    """
    Підтвердження нового користувача.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="✅ Підтвердити",
                    callback=UserCallback(
                        action=UserAction.APPROVE,
                        user_id=user_id,
                        page=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🎭 Обрати роль",
                    callback=UserCallback(
                        action=UserAction.ROLE,
                        user_id=user_id,
                        page=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="❌ Відхилити",
                    callback=UserCallback(
                        action=UserAction.REJECT,
                        user_id=user_id,
                        page=0,
                    ),
                )
            ],
            [
                root_admin_button(
                    text="🔙 До заявок",
                    action=(
                        RootAdminAction
                        .PENDING_USERS
                    ),
                )
            ],
        ]
    )


# =========================================================
# USER CARD
# =========================================================


def root_admin_user_keyboard(
    *,
    user_id: int,
    is_active: bool,
    is_blocked: bool,
) -> InlineKeyboardMarkup:
    """
    Повне керування користувачем.
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
                text="🏪 ТТ",
                callback=UserCallback(
                    action=UserAction.STORE,
                    user_id=user_id,
                    page=0,
                ),
            ),
            inline_button(
                text="🌿 Кущі",
                callback=UserCallback(
                    action=UserAction.BUSH,
                    user_id=user_id,
                    page=0,
                ),
            ),
        ],
        [
            inline_button(
                text="🔗 Усі прив’язки",
                callback=UserCallback(
                    action=UserAction.BINDINGS,
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
            root_admin_button(
                text="🔙 До користувачів",
                action=RootAdminAction.USERS,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# USER ROLE SELECTION
# =========================================================


def root_admin_role_keyboard(
    *,
    user_id: int,
) -> InlineKeyboardMarkup:
    """
    Вибір ролі користувача.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="👑 ROOT ADMIN",
                    callback=UserRoleCallback(
                        action=UserRoleAction.ROOT,
                        user_id=user_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="🏢 Директор",
                    callback=UserRoleCallback(
                        action=UserRoleAction.DIRECTOR,
                        user_id=user_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="🌿 Адмін куща",
                    callback=UserRoleCallback(
                        action=(
                            UserRoleAction.BUSH_ADMIN
                        ),
                        user_id=user_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="🦁 Лев",
                    callback=UserRoleCallback(
                        action=UserRoleAction.LION,
                        user_id=user_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="🏪 ТТ",
                    callback=UserRoleCallback(
                        action=(
                            UserRoleAction.STORE_USER
                        ),
                        user_id=user_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="❌ Скасувати",
                    callback=UserRoleCallback(
                        action=UserRoleAction.CANCEL,
                        user_id=user_id,
                    ),
                )
            ],
        ]
    )


# =========================================================
# OPENING
# =========================================================


def root_admin_opening_keyboard(
    *,
    stores: list[RootStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Live відкриття мережі.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                inline_button(
                    text=(
                        root_store_button_text(
                            store
                        )
                    ),
                    callback=OpeningCallback(
                        action=OpeningAction.STATUS,
                        store_id=store.store_id,
                    ),
                )
            ]
        )

    append_root_pagination(
        rows=rows,
        action=RootAdminAction.OPENING,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            root_admin_button(
                text="⚠️ Запізнення",
                action=RootAdminAction.LATE,
            ),
            root_admin_button(
                text="🚨 Не відкрилися",
                action=(
                    RootAdminAction
                    .MISSING_OPENING
                ),
            ),
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🔄 Оновити",
                action=RootAdminAction.OPENING,
                page=page,
            )
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🔙 До адмінки",
                action=RootAdminAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# LATE
# =========================================================


def root_admin_late_keyboard(
    *,
    stores: list[RootStoreItem],
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
                        f"⚠️ {store.display_name}"
                        f" · {minutes} хв"
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
                root_admin_button(
                    text="✅ Запізнень немає",
                    action=RootAdminAction.OPENING,
                )
            ]
        )

    append_root_pagination(
        rows=rows,
        action=RootAdminAction.LATE,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            root_admin_button(
                text="🔙 До відкриття",
                action=RootAdminAction.OPENING,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# MISSING OPENING
# =========================================================


def root_admin_missing_opening_keyboard(
    *,
    stores: list[RootStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    ТТ без check-in.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                inline_button(
                    text=(
                        f"🚨 {store.display_name}"
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
                root_admin_button(
                    text="✅ Усі ТТ відкрилися",
                    action=RootAdminAction.OPENING,
                )
            ]
        )

    append_root_pagination(
        rows=rows,
        action=(
            RootAdminAction.MISSING_OPENING
        ),
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            root_admin_button(
                text="🔙 До відкриття",
                action=RootAdminAction.OPENING,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# CLOSING
# =========================================================


def root_admin_closing_keyboard(
    *,
    stores: list[RootStoreItem],
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
                    text=(
                        root_store_button_text(
                            store
                        )
                    ),
                    callback=ClosingCallback(
                        action=ClosingAction.STATUS,
                        store_id=store.store_id,
                    ),
                )
            ]
        )

    append_root_pagination(
        rows=rows,
        action=RootAdminAction.CLOSING,
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            root_admin_button(
                text="🚨 Не закрилися",
                action=(
                    RootAdminAction
                    .MISSING_CLOSING
                ),
            )
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🔄 Оновити",
                action=RootAdminAction.CLOSING,
                page=page,
            )
        ]
    )

    rows.append(
        [
            root_admin_button(
                text="🔙 До адмінки",
                action=RootAdminAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# MISSING CLOSING
# =========================================================


def root_admin_missing_closing_keyboard(
    *,
    stores: list[RootStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    ТТ без завершеного закриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                inline_button(
                    text=(
                        f"🚨 {store.display_name}"
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
                root_admin_button(
                    text="✅ Усі ТТ закрилися",
                    action=RootAdminAction.CLOSING,
                )
            ]
        )

    append_root_pagination(
        rows=rows,
        action=(
            RootAdminAction.MISSING_CLOSING
        ),
        page=page,
        total_pages=total_pages,
    )

    rows.append(
        [
            root_admin_button(
                text="🔙 До закриття",
                action=RootAdminAction.CLOSING,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# REPORTS
# =========================================================


def root_admin_reports_keyboard(
) -> InlineKeyboardMarkup:
    """
    Усі звіти.
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
                    text="🗓 Інший період",
                    callback=ReportCallback(
                        action=ReportAction.CUSTOM,
                        ref_id=0,
                        page=0,
                    ),
                )
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
                    text="🌿 Кущ",
                    callback=ReportCallback(
                        action=ReportAction.BUSH,
                        ref_id=0,
                        page=0,
                    ),
                ),
                inline_button(
                    text="🏪 ТТ",
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
                root_admin_button(
                    text="🔙 До адмінки",
                    action=RootAdminAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# IMPORT
# =========================================================


def root_admin_import_keyboard(
) -> InlineKeyboardMarkup:
    """
    Імпорт ТТ із Excel/CSV.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="📤 Завантажити файл",
                    callback=ImportCallback(
                        action=ImportAction.UPLOAD,
                        token=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="👁 Попередній перегляд",
                    callback=ImportCallback(
                        action=ImportAction.PREVIEW,
                        token=0,
                    ),
                )
            ],
            [
                root_admin_button(
                    text="🔙 До адмінки",
                    action=RootAdminAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# IMPORT PREVIEW
# =========================================================


def root_admin_import_preview_keyboard(
    *,
    token: int = 0,
    has_errors: bool = False,
) -> InlineKeyboardMarkup:
    """
    Підтвердження імпорту.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    if not has_errors:
        rows.append(
            [
                inline_button(
                    text="✅ Виконати імпорт",
                    callback=ImportCallback(
                        action=ImportAction.APPLY,
                        token=token,
                    ),
                )
            ]
        )

    else:
        rows.append(
            [
                inline_button(
                    text="⚠️ Імпортувати валідні",
                    callback=ImportCallback(
                        action=(
                            ImportAction.APPLY_PARTIAL
                        ),
                        token=token,
                    ),
                )
            ]
        )

    rows.append(
        [
            inline_button(
                text="❌ Скасувати",
                callback=ImportCallback(
                    action=ImportAction.CANCEL,
                    token=token,
                ),
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# INVITES
# =========================================================


def root_admin_invites_keyboard(
) -> InlineKeyboardMarkup:
    """
    Усі типи запрошень.
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
                root_admin_button(
                    text="🔙 До адмінки",
                    action=RootAdminAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# SETTINGS
# =========================================================


def root_admin_settings_keyboard(
    *,
    bot_enabled: bool,
    maintenance_enabled: bool,
) -> InlineKeyboardMarkup:
    """
    Системні налаштування.
    """

    bot_text = (
        "🟢 Бот увімкнений"
        if bot_enabled
        else "🔴 Бот вимкнений"
    )

    maintenance_text = (
        "🟠 Maintenance ON"
        if maintenance_enabled
        else "🟢 Maintenance OFF"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text=bot_text,
                    callback=SettingsCallback(
                        action=SettingsAction.BOT
                    ),
                )
            ],
            [
                inline_button(
                    text=maintenance_text,
                    callback=SettingsCallback(
                        action=(
                            SettingsAction.MAINTENANCE
                        )
                    ),
                )
            ],
            [
                inline_button(
                    text="🌍 Часовий пояс",
                    callback=SettingsCallback(
                        action=SettingsAction.TIMEZONE
                    ),
                )
            ],
            [
                inline_button(
                    text="🌅 Відкриття",
                    callback=SettingsCallback(
                        action=SettingsAction.OPENING
                    ),
                ),
                inline_button(
                    text="🌙 Закриття",
                    callback=SettingsCallback(
                        action=SettingsAction.CLOSING
                    ),
                ),
            ],
            [
                inline_button(
                    text="🔔 Сповіщення",
                    callback=SettingsCallback(
                        action=(
                            SettingsAction
                            .NOTIFICATIONS
                        )
                    ),
                )
            ],
            [
                inline_button(
                    text="📊 Звіти",
                    callback=SettingsCallback(
                        action=SettingsAction.REPORTS
                    ),
                )
            ],
            [
                inline_button(
                    text="💬 Telegram-групи",
                    callback=SettingsCallback(
                        action=SettingsAction.GROUPS
                    ),
                )
            ],
            [
                root_admin_button(
                    text="🔙 До адмінки",
                    action=RootAdminAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# SYSTEM
# =========================================================


def root_admin_system_keyboard(
    *,
    bot_enabled: bool,
    maintenance_enabled: bool,
) -> InlineKeyboardMarkup:
    """
    Технічне керування ботом.
    """

    bot_text = (
        "🔴 Вимкнути бот"
        if bot_enabled
        else "🟢 Увімкнути бот"
    )

    maintenance_text = (
        "🟢 Вимкнути maintenance"
        if maintenance_enabled
        else "🟠 Увімкнути maintenance"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text=bot_text,
                    callback=SettingsCallback(
                        action=SettingsAction.BOT
                    ),
                )
            ],
            [
                inline_button(
                    text=maintenance_text,
                    callback=SettingsCallback(
                        action=(
                            SettingsAction.MAINTENANCE
                        )
                    ),
                )
            ],
            [
                root_admin_button(
                    text="💬 Telegram-групи",
                    action=RootAdminAction.GROUPS,
                )
            ],
            [
                root_admin_button(
                    text="📥 Імпорт ТТ",
                    action=RootAdminAction.IMPORT,
                )
            ],
            [
                root_admin_button(
                    text="🧾 Audit Log",
                    action=RootAdminAction.AUDIT,
                )
            ],
            [
                root_admin_button(
                    text="⚙️ Усі налаштування",
                    action=RootAdminAction.SETTINGS,
                )
            ],
            [
                root_admin_button(
                    text="🔙 До адмінки",
                    action=RootAdminAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# TELEGRAM GROUPS
# =========================================================


def root_admin_groups_keyboard(
) -> InlineKeyboardMarkup:
    """
    Telegram групи / топіки.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🌐 Група мережі",
                    callback=GroupCallback(
                        action=GroupAction.NETWORK,
                        bush_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🌿 Групи кущів",
                    callback=GroupCallback(
                        action=GroupAction.BUSH,
                        bush_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="✅ Перевірити доступ",
                    callback=GroupCallback(
                        action=GroupAction.VERIFY,
                        bush_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="📨 Тестове повідомлення",
                    callback=GroupCallback(
                        action=GroupAction.TEST,
                        bush_id=0,
                    ),
                )
            ],
            [
                root_admin_button(
                    text="🔙 До адмінки",
                    action=RootAdminAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# NETWORK GROUP
# =========================================================


def root_admin_network_group_keyboard(
) -> InlineKeyboardMarkup:
    """
    Налаштування головної Telegram групи.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🔗 Зареєструвати групу",
                    callback=GroupCallback(
                        action=GroupAction.REGISTER,
                        bush_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🌅 Topic відкриття",
                    callback=GroupCallback(
                        action=(
                            GroupAction.OPENING_TOPIC
                        ),
                        bush_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🌙 Topic закриття",
                    callback=GroupCallback(
                        action=(
                            GroupAction.CLOSING_TOPIC
                        ),
                        bush_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🚨 Topic alerts",
                    callback=GroupCallback(
                        action=(
                            GroupAction.ALERTS_TOPIC
                        ),
                        bush_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="📊 Topic summaries",
                    callback=GroupCallback(
                        action=(
                            GroupAction.SUMMARIES_TOPIC
                        ),
                        bush_id=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="✅ Перевірити",
                    callback=GroupCallback(
                        action=GroupAction.VERIFY,
                        bush_id=0,
                    ),
                ),
                inline_button(
                    text="📨 Тест",
                    callback=GroupCallback(
                        action=GroupAction.TEST,
                        bush_id=0,
                    ),
                ),
            ],
            [
                inline_button(
                    text="🗑 Очистити прив’язку",
                    callback=GroupCallback(
                        action=GroupAction.CLEAR,
                        bush_id=0,
                    ),
                )
            ],
            [
                root_admin_button(
                    text="🔙 До Telegram",
                    action=RootAdminAction.GROUPS,
                )
            ],
        ]
    )


# =========================================================
# AUDIT
# =========================================================


def root_admin_audit_keyboard(
) -> InlineKeyboardMarkup:
    """
    AuditLog.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="📋 Останні дії",
                    callback=AuditCallback(
                        action=(
                            AuditActionCallback.LIST
                        ),
                        ref_id=0,
                        page=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="👤 По користувачу",
                    callback=AuditCallback(
                        action=(
                            AuditActionCallback.USER
                        ),
                        ref_id=0,
                        page=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="🏪 По ТТ",
                    callback=AuditCallback(
                        action=(
                            AuditActionCallback.STORE
                        ),
                        ref_id=0,
                        page=0,
                    ),
                ),
                inline_button(
                    text="🌿 По кущу",
                    callback=AuditCallback(
                        action=(
                            AuditActionCallback.BUSH
                        ),
                        ref_id=0,
                        page=0,
                    ),
                ),
            ],
            [
                inline_button(
                    text="📊 Статистика",
                    callback=AuditCallback(
                        action=(
                            AuditActionCallback.STATS
                        ),
                        ref_id=0,
                        page=0,
                    ),
                )
            ],
            [
                inline_button(
                    text="📥 Export Excel",
                    callback=AuditCallback(
                        action=(
                            AuditActionCallback.EXPORT
                        ),
                        ref_id=0,
                        page=0,
                    ),
                )
            ],
            [
                root_admin_button(
                    text="🔙 До адмінки",
                    action=RootAdminAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# PAGINATION
# =========================================================


def append_root_pagination(
    *,
    rows: list[
        list[InlineKeyboardButton]
    ],
    action: RootAdminAction,
    page: int,
    total_pages: int,
    ref_id: int = 0,
) -> None:
    """
    Пагінація ROOT_ADMIN.
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
            root_admin_button(
                text="⬅️",
                action=action,
                ref_id=ref_id,
                page=(
                    normalized_page - 1
                ),
            )
        )

    pagination_row.append(
        root_admin_button(
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
            root_admin_button(
                text="➡️",
                action=action,
                ref_id=ref_id,
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


def root_admin_back_keyboard(
) -> InlineKeyboardMarkup:
    """
    Повернення в ROOT dashboard.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                root_admin_button(
                    text="🔙 Назад",
                    action=RootAdminAction.MENU,
                )
            ]
        ]
    )


# =========================================================
# HOME
# =========================================================


def root_admin_home_keyboard(
) -> InlineKeyboardMarkup:
    """
    Загальне головне меню.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                home_button()
            ]
        ]
    )


# =========================================================
# PROFILE
# =========================================================


def root_admin_profile_keyboard(
) -> InlineKeyboardMarkup:
    """
    Профіль ROOT_ADMIN.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                root_admin_button(
                    text="👑 ROOT адмінка",
                    action=RootAdminAction.MENU,
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
# EXPORTS
# =========================================================


__all__ = [
    # CALLBACK
    "RootAdminAction",
    "RootAdminCallback",

    # STATE
    "RootStoreState",
    "RootAdminDashboardState",
    "RootStoreItem",
    "RootBushItem",
    "RootClusterItem",
    "RootUserItem",

    # HELPERS
    "root_admin_button",
    "root_store_state_icon",
    "root_store_button_text",

    # MAIN
    "root_admin_main_keyboard",

    # STORES
    "root_admin_stores_keyboard",
    "root_admin_store_keyboard",

    # BUSHES
    "root_admin_bushes_keyboard",
    "root_admin_bush_keyboard",

    # CLUSTERS
    "root_admin_clusters_keyboard",
    "root_admin_cluster_keyboard",

    # USERS
    "root_admin_users_keyboard",
    "root_admin_pending_users_keyboard",
    "root_admin_pending_user_keyboard",
    "root_admin_user_keyboard",
    "root_admin_role_keyboard",

    # OPENING
    "root_admin_opening_keyboard",
    "root_admin_late_keyboard",
    "root_admin_missing_opening_keyboard",

    # CLOSING
    "root_admin_closing_keyboard",
    "root_admin_missing_closing_keyboard",

    # REPORTS
    "root_admin_reports_keyboard",

    # IMPORT
    "root_admin_import_keyboard",
    "root_admin_import_preview_keyboard",

    # INVITES
    "root_admin_invites_keyboard",

    # SETTINGS
    "root_admin_settings_keyboard",

    # SYSTEM
    "root_admin_system_keyboard",

    # GROUPS
    "root_admin_groups_keyboard",
    "root_admin_network_group_keyboard",

    # AUDIT
    "root_admin_audit_keyboard",

    # PAGINATION
    "append_root_pagination",

    # NAVIGATION
    "root_admin_back_keyboard",
    "root_admin_home_keyboard",
    "root_admin_profile_keyboard",
]