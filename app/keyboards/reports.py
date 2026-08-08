from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.keyboards.callbacks import (
    MainMenuAction,
    MainMenuCallback,
    ReportAction,
    ReportCallback,
    ReportDateAction,
    ReportDateCallback,
)
from app.keyboards.common import (
    home_button,
    inline_button,
)


# =========================================================
# REPORT UI CALLBACK
# =========================================================


class ReportUIAction(StrEnum):
    """
    Внутрішні дії report UI.
    """

    MENU = "m"

    SCOPE = "scope"

    PERIOD = "period"

    VIEW = "view"

    DETAILS = "det"

    LATE = "late"

    OPENING = "op"

    CLOSING = "cl"

    CASH = "cash"

    MISSING = "miss"

    EXPORT = "xls"

    REFRESH = "r"

    BACK = "b"


class ReportUICallback(
    CallbackData,
    prefix="rui",
):
    """
    rui:<action>:<scope>:<ref_id>:<page>

    scope:
        net
        bush
        store

    ref_id:
        0 для мережі
        bush_id
        store_id
    """

    action: ReportUIAction

    scope: str = "net"

    ref_id: int = 0

    page: int = 0


# =========================================================
# REPORT SCOPE
# =========================================================


class ReportScope(StrEnum):
    """
    Область звіту.
    """

    NETWORK = "net"

    BUSH = "bush"

    STORE = "store"


# =========================================================
# REPORT PERIOD
# =========================================================


class ReportPeriod(StrEnum):
    """
    Період звіту.
    """

    TODAY = "today"

    YESTERDAY = "yday"

    WEEK = "week"

    LAST_WEEK = "lweek"

    MONTH = "month"

    LAST_MONTH = "lmonth"

    CUSTOM = "custom"


# =========================================================
# BUSH ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class ReportBushItem:
    """
    Кущ у selector.
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

        if self.stores_count > 0:
            return (
                f"{icon} {self.name} "
                f"· {self.stores_count} ТТ"
            )

        return (
            f"{icon} {self.name}"
        )


# =========================================================
# STORE ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class ReportStoreItem:
    """
    ТТ у selector.
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
# REPORT RESULT STATE
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class ReportResultState:
    """
    Дані для кнопок готового звіту.
    """

    scope: ReportScope

    ref_id: int

    stores_count: int

    opened_count: int

    late_count: int

    missing_opening_count: int

    closed_count: int

    missing_closing_count: int

    cash_entries_count: int = 0

    can_export_excel: bool = True


# =========================================================
# STORE REPORT ITEM
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class ReportStoreResultItem:
    """
    Рядок ТТ у деталізації звіту.
    """

    store_id: int

    code: str

    name: str | None = None

    opened: bool = False

    late_minutes: int = 0

    closed: bool = False

    cash_present: bool = False

    @property
    def display_name(self) -> str:
        if self.name:
            return (
                f"{self.code} · {self.name}"
            )

        return self.code

    @property
    def button_text(self) -> str:
        parts: list[str] = []

        if self.opened:
            if self.late_minutes > 0:
                parts.append(
                    f"⚠️ +{self.late_minutes} хв"
                )

            else:
                parts.append(
                    "✅"
                )

        else:
            parts.append(
                "🚨"
            )

        parts.append(
            self.display_name
        )

        if self.closed:
            parts.append(
                "🌙✅"
            )

        return " ".join(
            parts
        )


# =========================================================
# HELPERS
# =========================================================


def report_ui_button(
    *,
    text: str,
    action: ReportUIAction,
    scope: ReportScope | str = ReportScope.NETWORK,
    ref_id: int = 0,
    page: int = 0,
) -> InlineKeyboardButton:
    """
    Створює ReportUICallback кнопку.
    """

    scope_value = (
        scope.value
        if isinstance(
            scope,
            ReportScope,
        )
        else str(scope)
    )

    return inline_button(
        text=text,
        callback=ReportUICallback(
            action=action,
            scope=scope_value,
            ref_id=ref_id,
            page=page,
        ),
    )


def normalize_scope(
    scope: ReportScope | str,
) -> str:
    """
    Нормалізує scope.
    """

    if isinstance(
        scope,
        ReportScope,
    ):
        return scope.value

    value = str(
        scope
    ).strip().lower()

    aliases = {
        "network": "net",
        "net": "net",

        "bush": "bush",

        "store": "store",
        "shop": "store",
    }

    result = aliases.get(
        value
    )

    if result is None:
        raise ValueError(
            f"Невідомий report scope: {scope}"
        )

    return result


# =========================================================
# MAIN REPORTS MENU
# =========================================================


def reports_main_keyboard(
) -> InlineKeyboardMarkup:
    """
    Головне меню звітів.

    Спочатку обираємо область:
        вся мережа
        кущ
        ТТ
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
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
                    text="🌿 По кущу",
                    callback=ReportCallback(
                        action=ReportAction.BUSH,
                        ref_id=0,
                        page=0,
                    ),
                ),
                inline_button(
                    text="🏪 По ТТ",
                    callback=ReportCallback(
                        action=ReportAction.STORE,
                        ref_id=0,
                        page=0,
                    ),
                ),
            ],
            [
                inline_button(
                    text="📥 Excel по мережі",
                    callback=ReportCallback(
                        action=ReportAction.EXCEL,
                        ref_id=0,
                        page=0,
                    ),
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# PERIOD SELECTION
# =========================================================


def report_period_keyboard(
    *,
    scope: ReportScope | str,
    ref_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Вибір періоду після того,
    як scope вже відомий.
    """

    scope_value = normalize_scope(
        scope
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="📅 Сьогодні",
                    callback=ReportDateCallback(
                        action=ReportDateAction.TODAY,
                        scope=scope_value,
                        ref_id=ref_id,
                    ),
                ),
                inline_button(
                    text="↩️ Вчора",
                    callback=ReportDateCallback(
                        action=(
                            ReportDateAction
                            .YESTERDAY
                        ),
                        scope=scope_value,
                        ref_id=ref_id,
                    ),
                ),
            ],
            [
                inline_button(
                    text="📆 Цей тиждень",
                    callback=ReportDateCallback(
                        action=(
                            ReportDateAction
                            .THIS_WEEK
                        ),
                        scope=scope_value,
                        ref_id=ref_id,
                    ),
                ),
                inline_button(
                    text="⬅️ Минулий",
                    callback=ReportDateCallback(
                        action=(
                            ReportDateAction
                            .LAST_WEEK
                        ),
                        scope=scope_value,
                        ref_id=ref_id,
                    ),
                ),
            ],
            [
                inline_button(
                    text="🗓 Цей місяць",
                    callback=ReportDateCallback(
                        action=(
                            ReportDateAction
                            .THIS_MONTH
                        ),
                        scope=scope_value,
                        ref_id=ref_id,
                    ),
                ),
                inline_button(
                    text="⬅️ Минулий",
                    callback=ReportDateCallback(
                        action=(
                            ReportDateAction
                            .LAST_MONTH
                        ),
                        scope=scope_value,
                        ref_id=ref_id,
                    ),
                ),
            ],
            [
                inline_button(
                    text="📍 Свій період",
                    callback=ReportDateCallback(
                        action=(
                            ReportDateAction
                            .CUSTOM
                        ),
                        scope=scope_value,
                        ref_id=ref_id,
                    ),
                )
            ],
            [
                report_ui_button(
                    text="🔙 До звітів",
                    action=ReportUIAction.MENU,
                    scope=scope_value,
                    ref_id=ref_id,
                )
            ],
        ]
    )


# =========================================================
# NETWORK REPORT PERIOD
# =========================================================


def network_report_period_keyboard(
) -> InlineKeyboardMarkup:
    """
    Період для всієї мережі.
    """

    return report_period_keyboard(
        scope=ReportScope.NETWORK,
        ref_id=0,
    )


# =========================================================
# BUSH SELECTOR
# =========================================================


def report_bush_selector_keyboard(
    *,
    bushes: list[ReportBushItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Вибір куща для звіту.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for bush in bushes:
        rows.append(
            [
                report_ui_button(
                    text=bush.button_text,
                    action=ReportUIAction.PERIOD,
                    scope=ReportScope.BUSH,
                    ref_id=bush.bush_id,
                )
            ]
        )

    if not bushes:
        rows.append(
            [
                report_ui_button(
                    text="ℹ️ Кущів немає",
                    action=ReportUIAction.MENU,
                )
            ]
        )

    append_report_pagination(
        rows=rows,
        scope=ReportScope.BUSH,
        page=page,
        total_pages=total_pages,
        action=ReportUIAction.SCOPE,
    )

    rows.append(
        [
            report_ui_button(
                text="🔄 Оновити",
                action=ReportUIAction.SCOPE,
                scope=ReportScope.BUSH,
                page=page,
            )
        ]
    )

    rows.append(
        [
            report_ui_button(
                text="🔙 До звітів",
                action=ReportUIAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORE SELECTOR
# =========================================================


def report_store_selector_keyboard(
    *,
    stores: list[ReportStoreItem],
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Вибір ТТ для звіту.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                report_ui_button(
                    text=store.button_text,
                    action=ReportUIAction.PERIOD,
                    scope=ReportScope.STORE,
                    ref_id=store.store_id,
                )
            ]
        )

    if not stores:
        rows.append(
            [
                report_ui_button(
                    text="ℹ️ ТТ не знайдено",
                    action=ReportUIAction.MENU,
                )
            ]
        )

    append_report_pagination(
        rows=rows,
        scope=ReportScope.STORE,
        page=page,
        total_pages=total_pages,
        action=ReportUIAction.SCOPE,
    )

    rows.append(
        [
            report_ui_button(
                text="🔄 Оновити",
                action=ReportUIAction.SCOPE,
                scope=ReportScope.STORE,
                page=page,
            )
        ]
    )

    rows.append(
        [
            report_ui_button(
                text="🔙 До звітів",
                action=ReportUIAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# CUSTOM DATE
# =========================================================


def custom_period_cancel_keyboard(
    *,
    scope: ReportScope | str,
    ref_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Поки FSM очікує дату / період.
    """

    scope_value = normalize_scope(
        scope
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="❌ Скасувати",
                    callback=ReportDateCallback(
                        action=ReportDateAction.CANCEL,
                        scope=scope_value,
                        ref_id=ref_id,
                    ),
                )
            ]
        ]
    )


# =========================================================
# RESULT KEYBOARD
# =========================================================


def report_result_keyboard(
    *,
    state: ReportResultState,
) -> InlineKeyboardMarkup:
    """
    Клавіатура під готовим звітом.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    scope = state.scope

    # -----------------------------------------------------
    # DETAILS
    # -----------------------------------------------------

    rows.append(
        [
            report_ui_button(
                text=(
                    "🏪 Деталізація "
                    f"({state.stores_count})"
                ),
                action=ReportUIAction.DETAILS,
                scope=scope,
                ref_id=state.ref_id,
            )
        ]
    )

    # -----------------------------------------------------
    # OPENING
    # -----------------------------------------------------

    rows.append(
        [
            report_ui_button(
                text=(
                    "🌅 Відкриття "
                    f"{state.opened_count}/"
                    f"{state.stores_count}"
                ),
                action=ReportUIAction.OPENING,
                scope=scope,
                ref_id=state.ref_id,
            )
        ]
    )

    # -----------------------------------------------------
    # LATE
    # -----------------------------------------------------

    if state.late_count > 0:
        rows.append(
            [
                report_ui_button(
                    text=(
                        "⚠️ Запізнення "
                        f"({state.late_count})"
                    ),
                    action=ReportUIAction.LATE,
                    scope=scope,
                    ref_id=state.ref_id,
                )
            ]
        )

    # -----------------------------------------------------
    # MISSING OPENING
    # -----------------------------------------------------

    if (
        state.missing_opening_count
        > 0
    ):
        rows.append(
            [
                report_ui_button(
                    text=(
                        "🚨 Без відкриття "
                        f"({state.missing_opening_count})"
                    ),
                    action=ReportUIAction.MISSING,
                    scope=scope,
                    ref_id=state.ref_id,
                )
            ]
        )

    # -----------------------------------------------------
    # CLOSING
    # -----------------------------------------------------

    rows.append(
        [
            report_ui_button(
                text=(
                    "🌙 Закриття "
                    f"{state.closed_count}/"
                    f"{state.stores_count}"
                ),
                action=ReportUIAction.CLOSING,
                scope=scope,
                ref_id=state.ref_id,
            )
        ]
    )

    # -----------------------------------------------------
    # CASH
    # -----------------------------------------------------

    if (
        state.cash_entries_count
        > 0
    ):
        rows.append(
            [
                report_ui_button(
                    text=(
                        "💵 Каса "
                        f"({state.cash_entries_count})"
                    ),
                    action=ReportUIAction.CASH,
                    scope=scope,
                    ref_id=state.ref_id,
                )
            ]
        )

    # -----------------------------------------------------
    # EXCEL
    # -----------------------------------------------------

    if state.can_export_excel:
        rows.append(
            [
                report_ui_button(
                    text="📥 Завантажити Excel",
                    action=ReportUIAction.EXPORT,
                    scope=scope,
                    ref_id=state.ref_id,
                )
            ]
        )

    # -----------------------------------------------------
    # REFRESH
    # -----------------------------------------------------

    rows.append(
        [
            report_ui_button(
                text="🔄 Оновити",
                action=ReportUIAction.REFRESH,
                scope=scope,
                ref_id=state.ref_id,
            )
        ]
    )

    # -----------------------------------------------------
    # NEW REPORT
    # -----------------------------------------------------

    rows.append(
        [
            report_ui_button(
                text="🔙 Новий звіт",
                action=ReportUIAction.MENU,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORE DETAILS
# =========================================================


def report_store_details_keyboard(
    *,
    stores: list[
        ReportStoreResultItem
    ],
    scope: ReportScope | str,
    ref_id: int = 0,
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Деталізація звіту по ТТ.
    """

    scope_value = normalize_scope(
        scope
    )

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        rows.append(
            [
                report_ui_button(
                    text=store.button_text,
                    action=ReportUIAction.VIEW,
                    scope=ReportScope.STORE,
                    ref_id=store.store_id,
                    page=page,
                )
            ]
        )

    if not stores:
        rows.append(
            [
                report_ui_button(
                    text="ℹ️ Даних немає",
                    action=ReportUIAction.BACK,
                    scope=scope_value,
                    ref_id=ref_id,
                )
            ]
        )

    append_report_pagination(
        rows=rows,
        scope=scope_value,
        ref_id=ref_id,
        page=page,
        total_pages=total_pages,
        action=ReportUIAction.DETAILS,
    )

    rows.append(
        [
            report_ui_button(
                text="🔙 До звіту",
                action=ReportUIAction.BACK,
                scope=scope_value,
                ref_id=ref_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# LATE DETAILS
# =========================================================


def report_late_keyboard(
    *,
    stores: list[
        ReportStoreResultItem
    ],
    scope: ReportScope | str,
    ref_id: int = 0,
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Список запізнень.
    """

    scope_value = normalize_scope(
        scope
    )

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        minutes = max(
            0,
            store.late_minutes,
        )

        rows.append(
            [
                report_ui_button(
                    text=(
                        f"⚠️ {store.display_name}"
                        f" · {minutes} хв"
                    ),
                    action=ReportUIAction.VIEW,
                    scope=ReportScope.STORE,
                    ref_id=store.store_id,
                    page=page,
                )
            ]
        )

    if not stores:
        rows.append(
            [
                report_ui_button(
                    text="✅ Запізнень немає",
                    action=ReportUIAction.BACK,
                    scope=scope_value,
                    ref_id=ref_id,
                )
            ]
        )

    append_report_pagination(
        rows=rows,
        scope=scope_value,
        ref_id=ref_id,
        page=page,
        total_pages=total_pages,
        action=ReportUIAction.LATE,
    )

    rows.append(
        [
            report_ui_button(
                text="🔙 До звіту",
                action=ReportUIAction.BACK,
                scope=scope_value,
                ref_id=ref_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# OPENING DETAILS
# =========================================================


def report_opening_keyboard(
    *,
    stores: list[
        ReportStoreResultItem
    ],
    scope: ReportScope | str,
    ref_id: int = 0,
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Деталізація відкриття.
    """

    scope_value = normalize_scope(
        scope
    )

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        if not store.opened:
            icon = "🚨"

        elif store.late_minutes > 0:
            icon = "⚠️"

        else:
            icon = "✅"

        rows.append(
            [
                report_ui_button(
                    text=(
                        f"{icon} {store.display_name}"
                    ),
                    action=ReportUIAction.VIEW,
                    scope=ReportScope.STORE,
                    ref_id=store.store_id,
                    page=page,
                )
            ]
        )

    append_report_pagination(
        rows=rows,
        scope=scope_value,
        ref_id=ref_id,
        page=page,
        total_pages=total_pages,
        action=ReportUIAction.OPENING,
    )

    rows.append(
        [
            report_ui_button(
                text="🔙 До звіту",
                action=ReportUIAction.BACK,
                scope=scope_value,
                ref_id=ref_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# CLOSING DETAILS
# =========================================================


def report_closing_keyboard(
    *,
    stores: list[
        ReportStoreResultItem
    ],
    scope: ReportScope | str,
    ref_id: int = 0,
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Деталізація закриття.
    """

    scope_value = normalize_scope(
        scope
    )

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        icon = (
            "✅"
            if store.closed
            else "🚨"
        )

        rows.append(
            [
                report_ui_button(
                    text=(
                        f"{icon} {store.display_name}"
                    ),
                    action=ReportUIAction.VIEW,
                    scope=ReportScope.STORE,
                    ref_id=store.store_id,
                    page=page,
                )
            ]
        )

    append_report_pagination(
        rows=rows,
        scope=scope_value,
        ref_id=ref_id,
        page=page,
        total_pages=total_pages,
        action=ReportUIAction.CLOSING,
    )

    rows.append(
        [
            report_ui_button(
                text="🔙 До звіту",
                action=ReportUIAction.BACK,
                scope=scope_value,
                ref_id=ref_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# CASH DETAILS
# =========================================================


def report_cash_keyboard(
    *,
    stores: list[
        ReportStoreResultItem
    ],
    scope: ReportScope | str,
    ref_id: int = 0,
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """
    Деталізація каси.
    """

    scope_value = normalize_scope(
        scope
    )

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store in stores:
        icon = (
            "💵"
            if store.cash_present
            else "❌"
        )

        rows.append(
            [
                report_ui_button(
                    text=(
                        f"{icon} {store.display_name}"
                    ),
                    action=ReportUIAction.VIEW,
                    scope=ReportScope.STORE,
                    ref_id=store.store_id,
                    page=page,
                )
            ]
        )

    append_report_pagination(
        rows=rows,
        scope=scope_value,
        ref_id=ref_id,
        page=page,
        total_pages=total_pages,
        action=ReportUIAction.CASH,
    )

    rows.append(
        [
            report_ui_button(
                text="🔙 До звіту",
                action=ReportUIAction.BACK,
                scope=scope_value,
                ref_id=ref_id,
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# STORE REPORT CARD
# =========================================================


def store_report_card_keyboard(
    *,
    store_id: int,
    parent_scope: ReportScope | str = ReportScope.NETWORK,
    parent_ref_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Детальна картка однієї ТТ
    у звіті.
    """

    parent_scope_value = (
        normalize_scope(
            parent_scope
        )
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                report_ui_button(
                    text="🌅 Відкриття",
                    action=ReportUIAction.OPENING,
                    scope=ReportScope.STORE,
                    ref_id=store_id,
                ),
                report_ui_button(
                    text="🌙 Закриття",
                    action=ReportUIAction.CLOSING,
                    scope=ReportScope.STORE,
                    ref_id=store_id,
                ),
            ],
            [
                report_ui_button(
                    text="💵 Каса",
                    action=ReportUIAction.CASH,
                    scope=ReportScope.STORE,
                    ref_id=store_id,
                )
            ],
            [
                report_ui_button(
                    text="📥 Excel ТТ",
                    action=ReportUIAction.EXPORT,
                    scope=ReportScope.STORE,
                    ref_id=store_id,
                )
            ],
            [
                report_ui_button(
                    text="🔙 Назад",
                    action=ReportUIAction.BACK,
                    scope=parent_scope_value,
                    ref_id=parent_ref_id,
                )
            ],
        ]
    )


# =========================================================
# EXCEL
# =========================================================


def report_excel_keyboard(
    *,
    scope: ReportScope | str,
    ref_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Підтвердження Excel export.
    """

    scope_value = normalize_scope(
        scope
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                report_ui_button(
                    text="📥 Сформувати Excel",
                    action=ReportUIAction.EXPORT,
                    scope=scope_value,
                    ref_id=ref_id,
                )
            ],
            [
                report_ui_button(
                    text="🔙 Назад",
                    action=ReportUIAction.BACK,
                    scope=scope_value,
                    ref_id=ref_id,
                )
            ],
        ]
    )


# =========================================================
# EXCEL READY
# =========================================================


def report_excel_ready_keyboard(
    *,
    scope: ReportScope | str,
    ref_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Після відправлення Excel.
    """

    scope_value = normalize_scope(
        scope
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                report_ui_button(
                    text="🔄 Сформувати ще раз",
                    action=ReportUIAction.EXPORT,
                    scope=scope_value,
                    ref_id=ref_id,
                )
            ],
            [
                report_ui_button(
                    text="📊 До звіту",
                    action=ReportUIAction.BACK,
                    scope=scope_value,
                    ref_id=ref_id,
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# EMPTY REPORT
# =========================================================


def empty_report_keyboard(
    *,
    scope: ReportScope | str,
    ref_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Якщо за вибраний період
    немає даних.
    """

    scope_value = normalize_scope(
        scope
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                report_ui_button(
                    text="📅 Обрати інший період",
                    action=ReportUIAction.PERIOD,
                    scope=scope_value,
                    ref_id=ref_id,
                )
            ],
            [
                report_ui_button(
                    text="🔄 Оновити",
                    action=ReportUIAction.REFRESH,
                    scope=scope_value,
                    ref_id=ref_id,
                )
            ],
            [
                report_ui_button(
                    text="🔙 До звітів",
                    action=ReportUIAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# REPORT ERROR
# =========================================================


def report_error_keyboard(
    *,
    scope: ReportScope | str,
    ref_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Якщо формування звіту
    завершилося помилкою.
    """

    scope_value = normalize_scope(
        scope
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                report_ui_button(
                    text="🔄 Спробувати ще раз",
                    action=ReportUIAction.REFRESH,
                    scope=scope_value,
                    ref_id=ref_id,
                )
            ],
            [
                report_ui_button(
                    text="🔙 До звітів",
                    action=ReportUIAction.MENU,
                )
            ],
        ]
    )


# =========================================================
# DIRECT CALLBACK HELPERS
# =========================================================


def direct_daily_report_keyboard(
    *,
    ref_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Швидкий перехід:
        daily / weekly / monthly.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="📅 День",
                    callback=ReportCallback(
                        action=ReportAction.DAILY,
                        ref_id=ref_id,
                        page=0,
                    ),
                ),
                inline_button(
                    text="📆 Тиждень",
                    callback=ReportCallback(
                        action=ReportAction.WEEKLY,
                        ref_id=ref_id,
                        page=0,
                    ),
                ),
            ],
            [
                inline_button(
                    text="🗓 Місяць",
                    callback=ReportCallback(
                        action=ReportAction.MONTHLY,
                        ref_id=ref_id,
                        page=0,
                    ),
                ),
                inline_button(
                    text="📍 Період",
                    callback=ReportCallback(
                        action=ReportAction.CUSTOM,
                        ref_id=ref_id,
                        page=0,
                    ),
                ),
            ],
        ]
    )


# =========================================================
# PAGINATION
# =========================================================


def append_report_pagination(
    *,
    rows: list[
        list[InlineKeyboardButton]
    ],
    scope: ReportScope | str,
    page: int,
    total_pages: int,
    action: ReportUIAction,
    ref_id: int = 0,
) -> None:
    """
    Пагінація report UI.
    """

    if total_pages <= 1:
        return

    scope_value = normalize_scope(
        scope
    )

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
            report_ui_button(
                text="⬅️",
                action=action,
                scope=scope_value,
                ref_id=ref_id,
                page=normalized_page - 1,
            )
        )

    row.append(
        report_ui_button(
            text=(
                f"{normalized_page + 1}/"
                f"{total_pages}"
            ),
            action=action,
            scope=scope_value,
            ref_id=ref_id,
            page=normalized_page,
        )
    )

    if (
        normalized_page + 1
        < total_pages
    ):
        row.append(
            report_ui_button(
                text="➡️",
                action=action,
                scope=scope_value,
                ref_id=ref_id,
                page=normalized_page + 1,
            )
        )

    rows.append(
        row
    )


# =========================================================
# BACK TO REPORTS
# =========================================================


def reports_back_keyboard(
) -> InlineKeyboardMarkup:
    """
    Повернення в меню звітів.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                report_ui_button(
                    text="🔙 До звітів",
                    action=ReportUIAction.MENU,
                )
            ]
        ]
    )


# =========================================================
# HOME
# =========================================================


def reports_home_keyboard(
) -> InlineKeyboardMarkup:
    """
    Повернення в головне меню.
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
            ]
        ]
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    # CALLBACK
    "ReportUIAction",
    "ReportUICallback",

    # ENUMS
    "ReportScope",
    "ReportPeriod",

    # DATA
    "ReportBushItem",
    "ReportStoreItem",
    "ReportResultState",
    "ReportStoreResultItem",

    # HELPERS
    "report_ui_button",
    "normalize_scope",

    # MAIN
    "reports_main_keyboard",

    # PERIOD
    "report_period_keyboard",
    "network_report_period_keyboard",
    "custom_period_cancel_keyboard",

    # SELECTORS
    "report_bush_selector_keyboard",
    "report_store_selector_keyboard",

    # RESULT
    "report_result_keyboard",

    # DETAILS
    "report_store_details_keyboard",
    "report_late_keyboard",
    "report_opening_keyboard",
    "report_closing_keyboard",
    "report_cash_keyboard",
    "store_report_card_keyboard",

    # EXCEL
    "report_excel_keyboard",
    "report_excel_ready_keyboard",

    # EMPTY / ERROR
    "empty_report_keyboard",
    "report_error_keyboard",

    # DIRECT
    "direct_daily_report_keyboard",

    # PAGINATION
    "append_report_pagination",

    # NAVIGATION
    "reports_back_keyboard",
    "reports_home_keyboard",
]