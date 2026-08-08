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
    MainMenuAction,
    MainMenuCallback,
    OpeningAction,
    OpeningCallback,
    ReportAction,
    ReportCallback,
    StoreAction,
    StoreCallback,
    pack_checked,
)
from app.keyboards.common import (
    back_button,
    home_button,
    inline_button,
)


# =========================================================
# LION CALLBACKS
# =========================================================


class LionAction(StrEnum):
    """
    Дії меню Лева.
    """

    MENU = "m"

    DASHBOARD = "dash"

    STORES = "st"

    OPENING = "op"

    CLOSING = "cl"

    LATE = "late"

    MISSING_OPENING = "mop"

    MISSING_CLOSING = "mcl"

    REPORTS = "rep"

    REFRESH = "r"

    BACK = "b"


class LionCallback(
    CallbackData,
    prefix="ln",
):
    """
    ln:<action>:<bush_id>:<page>
    """

    action: LionAction

    bush_id: int = 0

    page: int = 0


# =========================================================
# STORE STATUS
# =========================================================


class LionStoreState(StrEnum):
    """
    Поточний стан ТТ для Лева.
    """

    WAITING_OPENING = "waiting_opening"

    OPENED_ON_TIME = "opened_on_time"

    OPENED_LATE = "opened_late"

    WAITING_CLOSING = "waiting_closing"

    CLOSING_IN_PROGRESS = "closing_in_progress"

    CLOSED = "closed"

    INACTIVE = "inactive"


@dataclass(
    slots=True,
    frozen=True,
)
class LionStoreItem:
    """
    ТТ у списку Лева.
    """

    store_id: int

    code: str

    name: str | None

    state: LionStoreState

    lateness_minutes: int = 0

    @property
    def display_name(self) -> str:
        if self.name:
            return (
                f"{self.code} · {self.name}"
            )

        return self.code


@dataclass(
    slots=True,
    frozen=True,
)
class LionDashboardState:
    """
    Цифри для головного меню Лева.
    """

    bush_id: int

    total_stores: int

    opened_count: int

    late_count: int

    missing_opening_count: int

    closed_count: int

    missing_closing_count: int

    closing_in_progress_count: int = 0


# =========================================================
# HELPERS
# =========================================================


def lion_button(
    *,
    text: str,
    action: LionAction,
    bush_id: int = 0,
    page: int = 0,
) -> InlineKeyboardButton:
    """
    Створює кнопку LionCallback.
    """

    return inline_button(
        text=text,
        callback=LionCallback(
            action=action,
            bush_id=bush_id,
            page=page,
        ),
    )


def store_state_icon(
    state: LionStoreState,
) -> str:
    """
    Іконка стану ТТ.
    """

    mapping = {
        LionStoreState.WAITING_OPENING: "⏳",
        LionStoreState.OPENED_ON_TIME: "✅",
        LionStoreState.OPENED_LATE: "⚠️",
        LionStoreState.WAITING_CLOSING: "🌙",
        LionStoreState.CLOSING_IN_PROGRESS: "🔄",
        LionStoreState.CLOSED: "✅",
        LionStoreState.INACTIVE: "⚫",
    }

    return mapping.get(
        state,
        "🏪",
    )


def store_state_text(
    item: LionStoreItem,
) -> str:
    """
    Текст кнопки ТТ.
    """

    icon = store_state_icon(
        item.state
    )

    text = (
        f"{icon} {item.display_name}"
    )

    if (
        item.state
        == LionStoreState.OPENED_LATE
        and item.lateness_minutes > 0
    ):
        text += (
            f" · +{item.lateness_minutes} хв"
        )

    return text


# =========================================================
# MAIN MENU
# =========================================================


def lion_main_keyboard(
    *,
    state: LionDashboardState,
) -> InlineKeyboardMarkup:
    """
    Головне меню Лева.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    # -----------------------------------------------------
    # OPENING
    # -----------------------------------------------------

    rows.append(
        [
            lion_button(
                text=(
                    "🌅 Відкриття "
                    f"{state.opened_count}/"
                    f"{state.total_stores}"
                ),
                action=LionAction.OPENING,
                bush_id=state.bush_id,
            )
        ]
    )

    # -----------------------------------------------------
    # PROBLEMS
    # -----------------------------------------------------

    if state.late_count > 0:
        rows.append(
            [
                lion_button(
                    text=(
                        "⚠️ Запізнилися: "
                        f"{state.late_count}"
                    ),
                    action=LionAction.LATE,
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
                lion_button(
                    text=(
                        "🚨 Не відкрилися: "
                        f"{state.missing_opening_count}"
                    ),
                    action=(
                        LionAction
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
            lion_button(
                text=(
                    "🌙 Закриття "
                    f"{state.closed_count}/"
                    f"{state.total_stores}"
                ),
                action=LionAction.CLOSING,
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
                lion_button(
                    text=(
                        "🚨 Не закрилися: "
                        f"{state.missing_closing_count}"
                    ),
                    action=(
                        LionAction
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
            lion_button(
                text="🏪 Усі мої ТТ",
                action=LionAction.STORES,
                bush_id=state.bush_id,
            )
        ]
    )

    # -----------------------------------------------------
    # REPORT
    # -----------------------------------------------------

    rows.append(
        [
            lion_button(
                text="📊 Звіти",
                action=LionAction.REPORTS,
                bush_id=state.bush_id,
            ),
            lion_button(
                text="🔄 Оновити",
                action=LionAction.REFRESH,
                bush_id=state.bush_id,
            ),
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
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORES LIST
# =========================================================


def lion_stores_keyboard(
    *,
    bush_id: int,
    stores: list[LionStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Список усіх ТТ Лева.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for item in stores:
        rows.append(
            [
                inline_button(
                    text=store_state_text(
                        item
                    ),
                    callback=StoreCallback(
                        action=StoreAction.VIEW,
                        store_id=item.store_id,
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
        action=LionAction.STORES,
    )

    rows.append(
        [
            lion_button(
                text="🔄 Оновити",
                action=LionAction.STORES,
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            lion_button(
                text="🔙 Назад",
                action=LionAction.MENU,
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


def lion_opening_keyboard(
    *,
    bush_id: int,
    stores: list[LionStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Моніторинг відкриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for item in stores:
        rows.append(
            [
                inline_button(
                    text=store_state_text(
                        item
                    ),
                    callback=OpeningCallback(
                        action=OpeningAction.STATUS,
                        store_id=item.store_id,
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=LionAction.OPENING,
    )

    rows.append(
        [
            lion_button(
                text="⚠️ Тільки запізнення",
                action=LionAction.LATE,
                bush_id=bush_id,
            ),
            lion_button(
                text="🚨 Не відкрилися",
                action=(
                    LionAction
                    .MISSING_OPENING
                ),
                bush_id=bush_id,
            ),
        ]
    )

    rows.append(
        [
            lion_button(
                text="🔄 Оновити",
                action=LionAction.OPENING,
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            lion_button(
                text="🔙 До меню",
                action=LionAction.MENU,
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# LATE STORES
# =========================================================


def lion_late_keyboard(
    *,
    bush_id: int,
    stores: list[LionStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Тільки ТТ із запізненнями.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for item in stores:
        minutes = max(
            0,
            item.lateness_minutes,
        )

        rows.append(
            [
                inline_button(
                    text=(
                        f"⚠️ {item.display_name}"
                        f" · {minutes} хв"
                    ),
                    callback=OpeningCallback(
                        action=OpeningAction.STATUS,
                        store_id=item.store_id,
                    ),
                )
            ]
        )

    if not stores:
        rows.append(
            [
                lion_button(
                    text="✅ Запізнень немає",
                    action=LionAction.OPENING,
                    bush_id=bush_id,
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=LionAction.LATE,
    )

    rows.append(
        [
            lion_button(
                text="🔄 Оновити",
                action=LionAction.LATE,
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            lion_button(
                text="🔙 До відкриття",
                action=LionAction.OPENING,
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


def lion_missing_opening_keyboard(
    *,
    bush_id: int,
    stores: list[LionStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    ТТ, які ще не підтвердили відкриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for item in stores:
        rows.append(
            [
                inline_button(
                    text=(
                        f"🚨 {item.display_name}"
                    ),
                    callback=OpeningCallback(
                        action=OpeningAction.STATUS,
                        store_id=item.store_id,
                    ),
                )
            ]
        )

    if not stores:
        rows.append(
            [
                lion_button(
                    text="✅ Усі ТТ відкрилися",
                    action=LionAction.OPENING,
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
            LionAction.MISSING_OPENING
        ),
    )

    rows.append(
        [
            lion_button(
                text="🔄 Оновити",
                action=(
                    LionAction.MISSING_OPENING
                ),
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            lion_button(
                text="🔙 До відкриття",
                action=LionAction.OPENING,
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# CLOSING MONITOR
# =========================================================


def lion_closing_keyboard(
    *,
    bush_id: int,
    stores: list[LionStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Моніторинг закриття ТТ.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for item in stores:
        rows.append(
            [
                inline_button(
                    text=store_state_text(
                        item
                    ),
                    callback=ClosingCallback(
                        action=ClosingAction.STATUS,
                        store_id=item.store_id,
                    ),
                )
            ]
        )

    append_pagination(
        rows=rows,
        bush_id=bush_id,
        page=page,
        total_pages=total_pages,
        action=LionAction.CLOSING,
    )

    rows.append(
        [
            lion_button(
                text="🚨 Не закрилися",
                action=(
                    LionAction
                    .MISSING_CLOSING
                ),
                bush_id=bush_id,
            )
        ]
    )

    rows.append(
        [
            lion_button(
                text="🔄 Оновити",
                action=LionAction.CLOSING,
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            lion_button(
                text="🔙 До меню",
                action=LionAction.MENU,
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


def lion_missing_closing_keyboard(
    *,
    bush_id: int,
    stores: list[LionStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    ТТ без завершеного закриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for item in stores:
        rows.append(
            [
                inline_button(
                    text=(
                        f"🚨 {item.display_name}"
                    ),
                    callback=ClosingCallback(
                        action=ClosingAction.STATUS,
                        store_id=item.store_id,
                    ),
                )
            ]
        )

    if not stores:
        rows.append(
            [
                lion_button(
                    text="✅ Усі ТТ закрилися",
                    action=LionAction.CLOSING,
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
            LionAction.MISSING_CLOSING
        ),
    )

    rows.append(
        [
            lion_button(
                text="🔄 Оновити",
                action=(
                    LionAction.MISSING_CLOSING
                ),
                bush_id=bush_id,
                page=page,
            )
        ]
    )

    rows.append(
        [
            lion_button(
                text="🔙 До закриття",
                action=LionAction.CLOSING,
                bush_id=bush_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORE CARD FOR LION
# =========================================================


def lion_store_keyboard(
    *,
    store_id: int,
    bush_id: int,
) -> InlineKeyboardMarkup:
    """
    Картка конкретної ТТ.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
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
                lion_button(
                    text="🔙 До списку ТТ",
                    action=LionAction.STORES,
                    bush_id=bush_id,
                )
            ],
        ]
    )


# =========================================================
# REPORTS
# =========================================================


def lion_reports_keyboard(
    *,
    bush_id: int,
) -> InlineKeyboardMarkup:
    """
    Звіти доступного куща.
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
                    text="🌿 Звіт по кущу",
                    callback=ReportCallback(
                        action=ReportAction.BUSH,
                        ref_id=bush_id,
                        page=0,
                    ),
                )
            ],
            [
                lion_button(
                    text="🔙 Назад",
                    action=LionAction.MENU,
                    bush_id=bush_id,
                )
            ],
        ]
    )


# =========================================================
# BUSH CARD
# =========================================================


def lion_bush_keyboard(
    *,
    bush_id: int,
) -> InlineKeyboardMarkup:
    """
    Перехід до куща.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
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
                lion_button(
                    text="🌅 Відкриття",
                    action=LionAction.OPENING,
                    bush_id=bush_id,
                ),
                lion_button(
                    text="🌙 Закриття",
                    action=LionAction.CLOSING,
                    bush_id=bush_id,
                ),
            ],
            [
                lion_button(
                    text="📊 Звіти",
                    action=LionAction.REPORTS,
                    bush_id=bush_id,
                )
            ],
            [
                lion_button(
                    text="🔙 Назад",
                    action=LionAction.MENU,
                    bush_id=bush_id,
                )
            ],
        ]
    )


# =========================================================
# MULTIPLE BUSHES
# =========================================================


def lion_select_bush_keyboard(
    *,
    bushes: list[
        tuple[int, str]
    ],
) -> InlineKeyboardMarkup:
    """
    Якщо Лев має доступ
    до кількох кущів.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for bush_id, name in bushes:
        rows.append(
            [
                lion_button(
                    text=(
                        f"🌿 {name}"
                    ),
                    action=LionAction.DASHBOARD,
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
# NO STORES
# =========================================================


def lion_no_stores_keyboard(
    *,
    bush_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Якщо до Лева не прив’язано ТТ.
    """

    rows = [
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

    if bush_id > 0:
        rows.insert(
            0,
            [
                lion_button(
                    text="🔄 Оновити",
                    action=LionAction.REFRESH,
                    bush_id=bush_id,
                )
            ],
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
    action: LionAction,
) -> None:
    """
    Додає пагінацію до списку.
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
            lion_button(
                text="⬅️",
                action=action,
                bush_id=bush_id,
                page=(
                    normalized_page - 1
                ),
            )
        )

    pagination_row.append(
        lion_button(
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
            lion_button(
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


def lion_back_keyboard(
    *,
    bush_id: int,
) -> InlineKeyboardMarkup:
    """
    Повернення до dashboard Лева.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                lion_button(
                    text="🔙 Назад",
                    action=LionAction.MENU,
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
    "LionAction",
    "LionCallback",

    # STATE
    "LionStoreState",
    "LionStoreItem",
    "LionDashboardState",

    # HELPERS
    "lion_button",
    "store_state_icon",
    "store_state_text",

    # MAIN
    "lion_main_keyboard",

    # STORES
    "lion_stores_keyboard",
    "lion_store_keyboard",

    # OPENING
    "lion_opening_keyboard",
    "lion_late_keyboard",
    "lion_missing_opening_keyboard",

    # CLOSING
    "lion_closing_keyboard",
    "lion_missing_closing_keyboard",

    # REPORTS
    "lion_reports_keyboard",

    # BUSH
    "lion_bush_keyboard",
    "lion_select_bush_keyboard",

    # EMPTY
    "lion_no_stores_keyboard",

    # PAGINATION
    "append_pagination",

    # BACK
    "lion_back_keyboard",
]