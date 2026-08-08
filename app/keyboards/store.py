from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.keyboards.callbacks import (
    CashAction,
    CashCallback,
    ClosingAction,
    ClosingCallback,
    MainMenuAction,
    MainMenuCallback,
    OpeningAction,
    OpeningCallback,
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
# STORE DAY STATE
# =========================================================


class StoreDayState(StrEnum):
    """
    Стан ТТ на сьогодні.
    """

    NOT_OPENED = "not_opened"

    OPENED_ON_TIME = "opened_on_time"

    OPENED_LATE = "opened_late"

    CLOSING_STARTED = "closing_started"

    CLOSED = "closed"


@dataclass(
    slots=True,
    frozen=True,
)
class StoreMenuState:
    """
    Стан ТТ для побудови меню.

    store_id:
        ID ТТ.

    state:
        поточний стан дня.

    opening_lateness_minutes:
        кількість хвилин запізнення.

    has_cash:
        каса вже введена.

    has_receipt:
        чек уже прикріплено.

    closing_report_id:
        ClosingReport ID.
    """

    store_id: int

    state: StoreDayState

    opening_lateness_minutes: int = 0

    has_cash: bool = False

    has_receipt: bool = False

    closing_report_id: int = 0

    @property
    def is_opened(self) -> bool:
        return self.state in {
            StoreDayState.OPENED_ON_TIME,
            StoreDayState.OPENED_LATE,
            StoreDayState.CLOSING_STARTED,
            StoreDayState.CLOSED,
        }

    @property
    def is_closed(self) -> bool:
        return (
            self.state
            == StoreDayState.CLOSED
        )

    @property
    def closing_in_progress(self) -> bool:
        return (
            self.state
            == StoreDayState.CLOSING_STARTED
        )


# =========================================================
# BASIC BUTTONS
# =========================================================


def opening_button(
    *,
    store_id: int,
    text: str = "🌅 Відкрив магазин",
) -> InlineKeyboardButton:
    """
    Почати відкриття ТТ.
    """

    return inline_button(
        text=text,
        callback=OpeningCallback(
            action=OpeningAction.PREPARE,
            store_id=store_id,
        ),
    )


def opening_status_button(
    *,
    store_id: int,
    text: str = "📍 Статус відкриття",
) -> InlineKeyboardButton:
    """
    Статус відкриття.
    """

    return inline_button(
        text=text,
        callback=OpeningCallback(
            action=OpeningAction.STATUS,
            store_id=store_id,
        ),
    )


def closing_button(
    *,
    store_id: int,
    text: str = "🌙 Закрити магазин",
) -> InlineKeyboardButton:
    """
    Почати закриття.
    """

    return inline_button(
        text=text,
        callback=ClosingCallback(
            action=ClosingAction.PREPARE,
            store_id=store_id,
        ),
    )


def closing_status_button(
    *,
    store_id: int,
    text: str = "📋 Статус закриття",
) -> InlineKeyboardButton:
    """
    Статус закриття.
    """

    return inline_button(
        text=text,
        callback=ClosingCallback(
            action=ClosingAction.STATUS,
            store_id=store_id,
        ),
    )


# =========================================================
# STORE MAIN MENU
# =========================================================


def store_main_keyboard(
    *,
    state: StoreMenuState,
) -> InlineKeyboardMarkup:
    """
    Головне меню торгової точки.

    Кнопки змінюються залежно від того,
    що ТТ уже зробила сьогодні.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    # -----------------------------------------------------
    # НЕ ВІДКРИТО
    # -----------------------------------------------------

    if (
        state.state
        == StoreDayState.NOT_OPENED
    ):
        rows.append(
            [
                opening_button(
                    store_id=state.store_id
                )
            ]
        )

        rows.append(
            [
                opening_status_button(
                    store_id=state.store_id
                )
            ]
        )

    # -----------------------------------------------------
    # ВІДКРИТО
    # -----------------------------------------------------

    elif state.state in {
        StoreDayState.OPENED_ON_TIME,
        StoreDayState.OPENED_LATE,
    }:
        rows.append(
            [
                inline_button(
                    text="✅ Магазин відкритий",
                    callback=OpeningCallback(
                        action=OpeningAction.STATUS,
                        store_id=state.store_id,
                    ),
                )
            ]
        )

        rows.append(
            [
                closing_button(
                    store_id=state.store_id
                )
            ]
        )

    # -----------------------------------------------------
    # ЗАКРИТТЯ В ПРОЦЕСІ
    # -----------------------------------------------------

    elif (
        state.state
        == StoreDayState.CLOSING_STARTED
    ):
        rows.append(
            [
                inline_button(
                    text="🌙 Продовжити закриття",
                    callback=ClosingCallback(
                        action=ClosingAction.STATUS,
                        store_id=state.store_id,
                    ),
                )
            ]
        )

    # -----------------------------------------------------
    # ЗАКРИТО
    # -----------------------------------------------------

    elif (
        state.state
        == StoreDayState.CLOSED
    ):
        rows.append(
            [
                inline_button(
                    text="✅ Зміна завершена",
                    callback=ClosingCallback(
                        action=ClosingAction.STATUS,
                        store_id=state.store_id,
                    ),
                )
            ]
        )

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    rows.append(
        [
            inline_button(
                text="📊 Статус за сьогодні",
                callback=StoreCallback(
                    action=StoreAction.REPORT,
                    store_id=state.store_id,
                    page=0,
                ),
            )
        ]
    )

    # -----------------------------------------------------
    # PROFILE
    # -----------------------------------------------------

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
# MULTI STORE USER
# =========================================================


def select_store_keyboard(
    *,
    stores: list[
        tuple[int, str]
    ],
    context: str,
) -> InlineKeyboardMarkup:
    """
    Якщо користувач прив’язаний
    до кількох ТТ.

    stores:
        [
            (31, "SB-31"),
            (42, "SB-42"),
        ]

    context:
        opening
        closing
        status
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    for store_id, title in stores:
        normalized_title = (
            title.strip()
            or f"ТТ #{store_id}"
        )

        if context == "opening":
            callback = OpeningCallback(
                action=OpeningAction.SELECT_STORE,
                store_id=store_id,
            )

        elif context == "closing":
            callback = ClosingCallback(
                action=ClosingAction.SELECT_STORE,
                store_id=store_id,
            )

        else:
            callback = StoreCallback(
                action=StoreAction.VIEW,
                store_id=store_id,
                page=0,
            )

        rows.append(
            [
                inline_button(
                    text=f"🏪 {normalized_title}",
                    callback=callback,
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
# OPENING PREPARE
# =========================================================


def opening_prepare_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Перед фактичним check-in.

    Користувач бачить:

        Підтвердити відкриття?
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="✅ Так, магазин відкритий",
                    callback=OpeningCallback(
                        action=OpeningAction.CONFIRM,
                        store_id=store_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="❌ Скасувати",
                    callback=OpeningCallback(
                        action=OpeningAction.BACK,
                        store_id=store_id,
                    ),
                )
            ],
        ]
    )


# =========================================================
# OPENING SUCCESS
# =========================================================


def opening_success_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Після успішного відкриття.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                opening_status_button(
                    store_id=store_id,
                    text="📍 Переглянути статус",
                )
            ],
            [
                home_button(
                    text="🏠 До меню"
                )
            ],
        ]
    )


# =========================================================
# OPENING LATE
# =========================================================


def opening_late_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Якщо магазин відкрився із запізненням.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                opening_status_button(
                    store_id=store_id
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# OPENING ALREADY CONFIRMED
# =========================================================


def opening_already_done_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Якщо користувач повторно
    натиснув відкриття.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                opening_status_button(
                    store_id=store_id
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# OPENING STATUS
# =========================================================


def opening_status_keyboard(
    *,
    store_id: int,
    can_close: bool = True,
) -> InlineKeyboardMarkup:
    """
    Кнопки під статусом відкриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = [
        [
            inline_button(
                text="🔄 Оновити",
                callback=OpeningCallback(
                    action=OpeningAction.REFRESH,
                    store_id=store_id,
                ),
            )
        ]
    ]

    if can_close:
        rows.append(
            [
                closing_button(
                    store_id=store_id
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
# CLOSING START
# =========================================================


def closing_prepare_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Перший крок закриття.

    Після підтвердження handler
    переводить користувача до введення каси.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🌙 Почати закриття",
                    callback=ClosingCallback(
                        action=ClosingAction.CASH,
                        store_id=store_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="❌ Скасувати",
                    callback=ClosingCallback(
                        action=ClosingAction.BACK,
                        store_id=store_id,
                    ),
                )
            ],
        ]
    )


# =========================================================
# CASH INPUT
# =========================================================


def cash_input_keyboard(
    *,
    store_id: int,
    report_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Клавіатура під повідомленням:

        Введіть суму каси.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="❌ Скасувати",
                    callback=CashCallback(
                        action=CashAction.CANCEL,
                        store_id=store_id,
                        report_id=report_id,
                    ),
                )
            ]
        ]
    )


# =========================================================
# CASH CONFIRM
# =========================================================


def cash_confirmation_keyboard(
    *,
    store_id: int,
    report_id: int,
) -> InlineKeyboardMarkup:
    """
    Після введення суми:

        Каса: 12 500 грн.
        Все правильно?
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="✅ Так, правильно",
                    callback=CashCallback(
                        action=CashAction.CONFIRM,
                        store_id=store_id,
                        report_id=report_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="✏️ Ввести іншу суму",
                    callback=CashCallback(
                        action=CashAction.ENTER,
                        store_id=store_id,
                        report_id=report_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="❌ Скасувати",
                    callback=CashCallback(
                        action=CashAction.CANCEL,
                        store_id=store_id,
                        report_id=report_id,
                    ),
                )
            ],
        ]
    )


# =========================================================
# RECEIPT REQUEST
# =========================================================


def receipt_request_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Під повідомленням:

        Надішліть фото чека.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="🔙 Назад до каси",
                    callback=ClosingCallback(
                        action=ClosingAction.CASH,
                        store_id=store_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="❌ Скасувати закриття",
                    callback=ClosingCallback(
                        action=ClosingAction.BACK,
                        store_id=store_id,
                    ),
                )
            ],
        ]
    )


# =========================================================
# RECEIPT RECEIVED
# =========================================================


def receipt_received_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Фото чека отримане.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="✅ Продовжити",
                    callback=ClosingCallback(
                        action=ClosingAction.STATUS,
                        store_id=store_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="📷 Замінити фото",
                    callback=ClosingCallback(
                        action=ClosingAction.RECEIPT,
                        store_id=store_id,
                    ),
                )
            ],
        ]
    )


# =========================================================
# FINAL CLOSING CONFIRMATION
# =========================================================


def closing_confirmation_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Останній крок перед закриттям.

    Handler до цього моменту вже має:

        cash_amount
        receipt_file_id
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="✅ Підтвердити закриття",
                    callback=ClosingCallback(
                        action=ClosingAction.CONFIRM,
                        store_id=store_id,
                    ),
                )
            ],
            [
                inline_button(
                    text="💵 Змінити касу",
                    callback=ClosingCallback(
                        action=ClosingAction.CASH,
                        store_id=store_id,
                    ),
                ),
            ],
            [
                inline_button(
                    text="📷 Замінити чек",
                    callback=ClosingCallback(
                        action=ClosingAction.RECEIPT,
                        store_id=store_id,
                    ),
                ),
            ],
            [
                inline_button(
                    text="❌ Скасувати",
                    callback=ClosingCallback(
                        action=ClosingAction.BACK,
                        store_id=store_id,
                    ),
                )
            ],
        ]
    )


# =========================================================
# CLOSING STATUS
# =========================================================


def closing_status_keyboard(
    *,
    store_id: int,
    has_cash: bool,
    has_receipt: bool,
    can_confirm: bool,
) -> InlineKeyboardMarkup:
    """
    Динамічна клавіатура статусу закриття.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    # -----------------------------------------------------
    # CASH
    # -----------------------------------------------------

    if has_cash:
        cash_text = "✅ Каса внесена"
    else:
        cash_text = "💵 Внести касу"

    rows.append(
        [
            inline_button(
                text=cash_text,
                callback=ClosingCallback(
                    action=ClosingAction.CASH,
                    store_id=store_id,
                ),
            )
        ]
    )

    # -----------------------------------------------------
    # RECEIPT
    # -----------------------------------------------------

    if has_receipt:
        receipt_text = "✅ Чек додано"
    else:
        receipt_text = "📷 Додати фото чека"

    rows.append(
        [
            inline_button(
                text=receipt_text,
                callback=ClosingCallback(
                    action=ClosingAction.RECEIPT,
                    store_id=store_id,
                ),
            )
        ]
    )

    # -----------------------------------------------------
    # CONFIRM
    # -----------------------------------------------------

    if can_confirm:
        rows.append(
            [
                inline_button(
                    text="✅ Завершити зміну",
                    callback=ClosingCallback(
                        action=ClosingAction.CONFIRM,
                        store_id=store_id,
                    ),
                )
            ]
        )

    # -----------------------------------------------------
    # REFRESH
    # -----------------------------------------------------

    rows.append(
        [
            inline_button(
                text="🔄 Оновити",
                callback=ClosingCallback(
                    action=ClosingAction.REFRESH,
                    store_id=store_id,
                ),
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
# CLOSING SUCCESS
# =========================================================


def closing_success_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Після повного закриття ТТ.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                closing_status_button(
                    store_id=store_id,
                    text="📋 Переглянути звіт",
                )
            ],
            [
                home_button(
                    text="🏠 Головне меню"
                )
            ],
        ]
    )


# =========================================================
# CLOSED ALREADY
# =========================================================


def closing_already_done_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Якщо повторно натиснули
    закриття після завершення.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                closing_status_button(
                    store_id=store_id
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# TODAY REPORT
# =========================================================


def store_today_report_keyboard(
    *,
    store_id: int,
    is_opened: bool,
    is_closed: bool,
) -> InlineKeyboardMarkup:
    """
    Кнопки під денним статусом ТТ.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = []

    if not is_opened:
        rows.append(
            [
                opening_button(
                    store_id=store_id
                )
            ]
        )

    elif not is_closed:
        rows.append(
            [
                closing_button(
                    store_id=store_id
                )
            ]
        )

    rows.append(
        [
            inline_button(
                text="🔄 Оновити",
                callback=StoreCallback(
                    action=StoreAction.REPORT,
                    store_id=store_id,
                    page=0,
                ),
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
# STORE INFORMATION
# =========================================================


def store_info_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Картка ТТ.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="📊 Сьогодні",
                    callback=StoreCallback(
                        action=StoreAction.REPORT,
                        store_id=store_id,
                        page=0,
                    ),
                )
            ],
            [
                opening_status_button(
                    store_id=store_id
                ),
                closing_status_button(
                    store_id=store_id
                ),
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# STORE NOT AVAILABLE
# =========================================================


def store_unavailable_keyboard(
) -> InlineKeyboardMarkup:
    """
    Якщо прив’язка до ТТ відсутня
    або ТТ неактивна.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text="👤 Мій профіль",
                    callback=MainMenuCallback(
                        action=MainMenuAction.PROFILE
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
# SIMPLE BACK
# =========================================================


def store_back_keyboard(
    *,
    store_id: int,
) -> InlineKeyboardMarkup:
    """
    Назад до картки ТТ.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                back_button(
                    StoreCallback(
                        action=StoreAction.VIEW,
                        store_id=store_id,
                        page=0,
                    )
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    # STATE
    "StoreDayState",
    "StoreMenuState",

    # MAIN
    "store_main_keyboard",

    # STORE SELECT
    "select_store_keyboard",

    # COMMON BUTTONS
    "opening_button",
    "opening_status_button",
    "closing_button",
    "closing_status_button",

    # OPENING
    "opening_prepare_keyboard",
    "opening_success_keyboard",
    "opening_late_keyboard",
    "opening_already_done_keyboard",
    "opening_status_keyboard",

    # CLOSING
    "closing_prepare_keyboard",
    "closing_confirmation_keyboard",
    "closing_status_keyboard",
    "closing_success_keyboard",
    "closing_already_done_keyboard",

    # CASH
    "cash_input_keyboard",
    "cash_confirmation_keyboard",

    # RECEIPT
    "receipt_request_keyboard",
    "receipt_received_keyboard",

    # STATUS
    "store_today_report_keyboard",
    "store_info_keyboard",
    "store_unavailable_keyboard",
    "store_back_keyboard",
]