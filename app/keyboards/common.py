from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.keyboards.callbacks import (
    ConfirmAction,
    ConfirmCallback,
    MainMenuAction,
    MainMenuCallback,
    PaginationCallback,
    RefreshCallback,
    ensure_callback_size,
    pack_checked,
)


# =========================================================
# TYPES
# =========================================================


CallbackValue = str | CallbackData


# =========================================================
# BUTTON SPEC
# =========================================================


@dataclass(
    slots=True,
    frozen=True,
)
class InlineButtonSpec:
    """
    Універсальний опис inline-кнопки.

    Можна передати:

        callback
    або
        url

    Одночасно використовувати обидва
    не можна.
    """

    text: str

    callback: CallbackValue | None = None

    url: str | None = None

    def __post_init__(
        self,
    ) -> None:
        if not self.text.strip():
            raise ValueError(
                "Текст кнопки не може "
                "бути порожнім."
            )

        if (
            self.callback is None
            and self.url is None
        ):
            raise ValueError(
                "Кнопка повинна містити "
                "callback або url."
            )

        if (
            self.callback is not None
            and self.url is not None
        ):
            raise ValueError(
                "Кнопка не може одночасно "
                "містити callback і url."
            )


# =========================================================
# CALLBACK PACKING
# =========================================================


def resolve_callback(
    value: CallbackValue,
) -> str:
    """
    Перетворює CallbackData або str
    у готовий callback_data.

    Також перевіряє Telegram limit
    64 bytes.
    """

    if isinstance(
        value,
        CallbackData,
    ):
        return pack_checked(
            value
        )

    callback_data = str(
        value
    ).strip()

    if not callback_data:
        raise ValueError(
            "callback_data не може "
            "бути порожнім."
        )

    return ensure_callback_size(
        callback_data
    )


# =========================================================
# CREATE BUTTON
# =========================================================


def inline_button(
    *,
    text: str,
    callback: CallbackValue | None = None,
    url: str | None = None,
) -> InlineKeyboardButton:
    """
    Створює InlineKeyboardButton.

    Приклад:

        inline_button(
            text="🔙 Назад",
            callback=MainMenuCallback(
                action=MainMenuAction.HOME
            ),
        )
    """

    normalized_text = (
        text.strip()
    )

    if not normalized_text:
        raise ValueError(
            "Текст кнопки не може "
            "бути порожнім."
        )

    if (
        callback is None
        and url is None
    ):
        raise ValueError(
            "Потрібно вказати "
            "callback або url."
        )

    if (
        callback is not None
        and url is not None
    ):
        raise ValueError(
            "Не можна одночасно "
            "вказувати callback і url."
        )

    if callback is not None:
        return InlineKeyboardButton(
            text=normalized_text,
            callback_data=(
                resolve_callback(
                    callback
                )
            ),
        )

    normalized_url = str(
        url
    ).strip()

    if not normalized_url:
        raise ValueError(
            "URL не може бути порожнім."
        )

    return InlineKeyboardButton(
        text=normalized_text,
        url=normalized_url,
    )


# =========================================================
# SPEC -> BUTTON
# =========================================================


def button_from_spec(
    spec: InlineButtonSpec,
) -> InlineKeyboardButton:
    """
    Перетворює InlineButtonSpec
    у Telegram кнопку.
    """

    return inline_button(
        text=spec.text,
        callback=spec.callback,
        url=spec.url,
    )


# =========================================================
# GENERIC KEYBOARD
# =========================================================


def build_keyboard(
    rows: Sequence[
        Sequence[
            InlineButtonSpec
            | InlineKeyboardButton
        ]
    ],
) -> InlineKeyboardMarkup:
    """
    Універсальний builder.

    Приклад:

        build_keyboard(
            [
                [
                    InlineButtonSpec(
                        text="✅ Так",
                        callback="yes",
                    ),
                    InlineButtonSpec(
                        text="❌ Ні",
                        callback="no",
                    ),
                ],
            ]
        )
    """

    inline_rows: list[
        list[
            InlineKeyboardButton
        ]
    ] = []

    for row in rows:
        current_row: list[
            InlineKeyboardButton
        ] = []

        for item in row:
            if isinstance(
                item,
                InlineKeyboardButton,
            ):
                current_row.append(
                    item
                )

            else:
                current_row.append(
                    button_from_spec(
                        item
                    )
                )

        if current_row:
            inline_rows.append(
                current_row
            )

    return InlineKeyboardMarkup(
        inline_keyboard=inline_rows
    )


# =========================================================
# EMPTY KEYBOARD
# =========================================================


def empty_keyboard(
) -> InlineKeyboardMarkup:
    """
    Порожня клавіатура.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[]
    )


# =========================================================
# ONE BUTTON
# =========================================================


def single_button_keyboard(
    *,
    text: str,
    callback: CallbackValue,
) -> InlineKeyboardMarkup:
    """
    Клавіатура з однією кнопкою.
    """

    return build_keyboard(
        [
            [
                InlineButtonSpec(
                    text=text,
                    callback=callback,
                )
            ]
        ]
    )


# =========================================================
# HOME
# =========================================================


def home_button(
    *,
    text: str = "🏠 Головне меню",
) -> InlineKeyboardButton:
    """
    Кнопка головного меню.
    """

    return inline_button(
        text=text,
        callback=MainMenuCallback(
            action=MainMenuAction.HOME
        ),
    )


def home_keyboard(
    *,
    text: str = "🏠 Головне меню",
) -> InlineKeyboardMarkup:
    """
    Лише кнопка головного меню.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                home_button(
                    text=text
                )
            ]
        ]
    )


# =========================================================
# BACK
# =========================================================


def back_button(
    callback: CallbackValue,
    *,
    text: str = "🔙 Назад",
) -> InlineKeyboardButton:
    """
    Універсальна кнопка Назад.
    """

    return inline_button(
        text=text,
        callback=callback,
    )


def back_keyboard(
    callback: CallbackValue,
    *,
    text: str = "🔙 Назад",
) -> InlineKeyboardMarkup:
    """
    Клавіатура тільки з Назад.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                back_button(
                    callback,
                    text=text,
                )
            ]
        ]
    )


# =========================================================
# CANCEL
# =========================================================


def cancel_button(
    callback: CallbackValue,
    *,
    text: str = "❌ Скасувати",
) -> InlineKeyboardButton:
    """
    Кнопка скасування.
    """

    return inline_button(
        text=text,
        callback=callback,
    )


def cancel_keyboard(
    callback: CallbackValue,
    *,
    text: str = "❌ Скасувати",
) -> InlineKeyboardMarkup:
    """
    Клавіатура скасування.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                cancel_button(
                    callback,
                    text=text,
                )
            ]
        ]
    )


# =========================================================
# BACK + HOME
# =========================================================


def back_home_keyboard(
    *,
    back_callback: CallbackValue,
    back_text: str = "🔙 Назад",
    home_text: str = "🏠 Меню",
) -> InlineKeyboardMarkup:
    """
    Назад + Головне меню.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                back_button(
                    back_callback,
                    text=back_text,
                ),
                home_button(
                    text=home_text
                ),
            ]
        ]
    )


# =========================================================
# BACK + CANCEL
# =========================================================


def back_cancel_keyboard(
    *,
    back_callback: CallbackValue,
    cancel_callback: CallbackValue,
    back_text: str = "🔙 Назад",
    cancel_text: str = "❌ Скасувати",
) -> InlineKeyboardMarkup:
    """
    Назад + Скасувати.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                back_button(
                    back_callback,
                    text=back_text,
                ),
                cancel_button(
                    cancel_callback,
                    text=cancel_text,
                ),
            ]
        ]
    )


# =========================================================
# REFRESH
# =========================================================


def refresh_button(
    *,
    section: str,
    ref_id: int = 0,
    text: str = "🔄 Оновити",
) -> InlineKeyboardButton:
    """
    Універсальна кнопка refresh.
    """

    normalized_section = (
        section.strip()
    )

    if not normalized_section:
        raise ValueError(
            "section не може бути "
            "порожнім."
        )

    return inline_button(
        text=text,
        callback=RefreshCallback(
            section=normalized_section,
            ref_id=ref_id,
        ),
    )


def refresh_keyboard(
    *,
    section: str,
    ref_id: int = 0,
    text: str = "🔄 Оновити",
) -> InlineKeyboardMarkup:
    """
    Лише refresh.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                refresh_button(
                    section=section,
                    ref_id=ref_id,
                    text=text,
                )
            ]
        ]
    )


# =========================================================
# REFRESH + BACK
# =========================================================


def refresh_back_keyboard(
    *,
    section: str,
    back_callback: CallbackValue,
    ref_id: int = 0,
    refresh_text: str = "🔄 Оновити",
    back_text: str = "🔙 Назад",
) -> InlineKeyboardMarkup:
    """
    Refresh + Назад.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                refresh_button(
                    section=section,
                    ref_id=ref_id,
                    text=refresh_text,
                )
            ],
            [
                back_button(
                    back_callback,
                    text=back_text,
                )
            ],
        ]
    )


# =========================================================
# CONFIRM CALLBACK
# =========================================================


def confirm_button(
    *,
    context: str,
    entity_id: int = 0,
    extra: int = 0,
    text: str = "✅ Підтвердити",
) -> InlineKeyboardButton:
    """
    YES через ConfirmCallback.
    """

    return inline_button(
        text=text,
        callback=ConfirmCallback(
            action=ConfirmAction.YES,
            context=context,
            entity_id=entity_id,
            extra=extra,
        ),
    )


def decline_button(
    *,
    context: str,
    entity_id: int = 0,
    extra: int = 0,
    text: str = "❌ Ні",
) -> InlineKeyboardButton:
    """
    NO через ConfirmCallback.
    """

    return inline_button(
        text=text,
        callback=ConfirmCallback(
            action=ConfirmAction.NO,
            context=context,
            entity_id=entity_id,
            extra=extra,
        ),
    )


# =========================================================
# YES / NO CONFIRMATION
# =========================================================


def confirmation_keyboard(
    *,
    context: str,
    entity_id: int = 0,
    extra: int = 0,
    confirm_text: str = "✅ Так",
    decline_text: str = "❌ Ні",
) -> InlineKeyboardMarkup:
    """
    Універсальне підтвердження.

    Наприклад:

        Видалити?
        [✅ Так] [❌ Ні]
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                confirm_button(
                    context=context,
                    entity_id=entity_id,
                    extra=extra,
                    text=confirm_text,
                ),
                decline_button(
                    context=context,
                    entity_id=entity_id,
                    extra=extra,
                    text=decline_text,
                ),
            ]
        ]
    )


# =========================================================
# CUSTOM CONFIRM / CANCEL
# =========================================================


def confirm_cancel_keyboard(
    *,
    confirm_callback: CallbackValue,
    cancel_callback: CallbackValue,
    confirm_text: str = "✅ Підтвердити",
    cancel_text: str = "❌ Скасувати",
) -> InlineKeyboardMarkup:
    """
    Підтвердити + Скасувати
    з довільними callback.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                inline_button(
                    text=confirm_text,
                    callback=confirm_callback,
                )
            ],
            [
                cancel_button(
                    cancel_callback,
                    text=cancel_text,
                )
            ],
        ]
    )


# =========================================================
# DELETE CONFIRMATION
# =========================================================


def dangerous_confirmation_keyboard(
    *,
    context: str,
    entity_id: int = 0,
    extra: int = 0,
    confirm_text: str = "🗑 Так, підтверджую",
    decline_text: str = "🔙 Ні, назад",
) -> InlineKeyboardMarkup:
    """
    Підтвердження небезпечної дії.

    Використовуємо для:

        - деактивації;
        - видалення прив’язки;
        - блокування;
        - очищення налаштувань.
    """

    return confirmation_keyboard(
        context=context,
        entity_id=entity_id,
        extra=extra,
        confirm_text=confirm_text,
        decline_text=decline_text,
    )


# =========================================================
# PAGINATION
# =========================================================


def pagination_buttons(
    *,
    section: str,
    page: int,
    total_pages: int,
    ref: int = 0,
    show_counter: bool = True,
) -> list[
    InlineKeyboardButton
]:
    """
    Один рядок пагінації.

    Приклад:

        ◀️ | 2/8 | ▶️
    """

    if page < 0:
        raise ValueError(
            "page не може бути "
            "від’ємним."
        )

    if total_pages < 1:
        total_pages = 1

    if page >= total_pages:
        page = (
            total_pages - 1
        )

    buttons: list[
        InlineKeyboardButton
    ] = []

    # -----------------------------------------------------
    # PREVIOUS
    # -----------------------------------------------------

    if page > 0:
        buttons.append(
            inline_button(
                text="⬅️",
                callback=PaginationCallback(
                    section=section,
                    page=page - 1,
                    ref=ref,
                ),
            )
        )

    # -----------------------------------------------------
    # COUNTER
    # -----------------------------------------------------

    if show_counter:
        buttons.append(
            inline_button(
                text=(
                    f"{page + 1}/{total_pages}"
                ),
                callback=PaginationCallback(
                    section=section,
                    page=page,
                    ref=ref,
                ),
            )
        )

    # -----------------------------------------------------
    # NEXT
    # -----------------------------------------------------

    if (
        page + 1
        < total_pages
    ):
        buttons.append(
            inline_button(
                text="➡️",
                callback=PaginationCallback(
                    section=section,
                    page=page + 1,
                    ref=ref,
                ),
            )
        )

    return buttons


def pagination_keyboard(
    *,
    section: str,
    page: int,
    total_pages: int,
    ref: int = 0,
    back_callback: CallbackValue | None = None,
    show_counter: bool = True,
) -> InlineKeyboardMarkup:
    """
    Повна клавіатура пагінації.
    """

    rows: list[
        list[
            InlineKeyboardButton
        ]
    ] = []

    page_buttons = pagination_buttons(
        section=section,
        page=page,
        total_pages=total_pages,
        ref=ref,
        show_counter=show_counter,
    )

    if page_buttons:
        rows.append(
            page_buttons
        )

    if back_callback is not None:
        rows.append(
            [
                back_button(
                    back_callback
                )
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# ITEMS + PAGINATION
# =========================================================


def paginated_items_keyboard(
    *,
    items: Sequence[
        InlineButtonSpec
    ],
    section: str,
    page: int,
    total_pages: int,
    ref: int = 0,
    columns: int = 1,
    back_callback: CallbackValue | None = None,
) -> InlineKeyboardMarkup:
    """
    Будує список кнопок
    + пагінацію.

    Наприклад список ТТ:

        [SB-1]
        [SB-2]
        [SB-3]
        [⬅️  1/5  ➡️]
        [🔙 Назад]
    """

    if columns < 1:
        raise ValueError(
            "columns повинен бути "
            "не меншим за 1."
        )

    rows: list[
        list[
            InlineKeyboardButton
        ]
    ] = []

    current_row: list[
        InlineKeyboardButton
    ] = []

    for item in items:
        current_row.append(
            button_from_spec(
                item
            )
        )

        if (
            len(current_row)
            >= columns
        ):
            rows.append(
                current_row
            )

            current_row = []

    if current_row:
        rows.append(
            current_row
        )

    pagination_row = (
        pagination_buttons(
            section=section,
            page=page,
            total_pages=total_pages,
            ref=ref,
        )
    )

    if pagination_row:
        rows.append(
            pagination_row
        )

    if back_callback is not None:
        rows.append(
            [
                back_button(
                    back_callback
                )
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# URL BUTTON
# =========================================================


def url_keyboard(
    *,
    text: str,
    url: str,
    back_callback: CallbackValue | None = None,
) -> InlineKeyboardMarkup:
    """
    URL-кнопка.

    Наприклад:
        відкрити Telegram group
        або deep-link.
    """

    rows: list[
        list[
            InlineKeyboardButton
        ]
    ] = [
        [
            inline_button(
                text=text,
                url=url,
            )
        ]
    ]

    if back_callback is not None:
        rows.append(
            [
                back_button(
                    back_callback
                )
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# TWO ACTIONS
# =========================================================


def two_actions_keyboard(
    *,
    first_text: str,
    first_callback: CallbackValue,
    second_text: str,
    second_callback: CallbackValue,
    same_row: bool = True,
) -> InlineKeyboardMarkup:
    """
    Дві універсальні кнопки.
    """

    first = inline_button(
        text=first_text,
        callback=first_callback,
    )

    second = inline_button(
        text=second_text,
        callback=second_callback,
    )

    if same_row:
        rows = [
            [
                first,
                second,
            ]
        ]

    else:
        rows = [
            [
                first
            ],
            [
                second
            ],
        ]

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# ACTIONS + BACK
# =========================================================


def actions_back_keyboard(
    *,
    actions: Iterable[
        InlineButtonSpec
    ],
    back_callback: CallbackValue,
    columns: int = 1,
) -> InlineKeyboardMarkup:
    """
    Набір дій + Назад.
    """

    if columns < 1:
        raise ValueError(
            "columns повинен бути "
            "не меншим за 1."
        )

    rows: list[
        list[
            InlineKeyboardButton
        ]
    ] = []

    current: list[
        InlineKeyboardButton
    ] = []

    for action in actions:
        current.append(
            button_from_spec(
                action
            )
        )

        if len(
            current
        ) >= columns:
            rows.append(
                current
            )

            current = []

    if current:
        rows.append(
            current
        )

    rows.append(
        [
            back_button(
                back_callback
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# REFRESH + HOME
# =========================================================


def refresh_home_keyboard(
    *,
    section: str,
    ref_id: int = 0,
) -> InlineKeyboardMarkup:
    """
    Оновити + головне меню.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                refresh_button(
                    section=section,
                    ref_id=ref_id,
                )
            ],
            [
                home_button()
            ],
        ]
    )


# =========================================================
# CANCEL TO HOME
# =========================================================


def cancel_to_home_keyboard(
) -> InlineKeyboardMarkup:
    """
    Скасувати → головне меню.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                home_button(
                    text=(
                        "❌ Скасувати "
                        "та повернутися"
                    )
                )
            ]
        ]
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    # TYPES
    "CallbackValue",

    # SPECS
    "InlineButtonSpec",

    # CALLBACK
    "resolve_callback",

    # BUTTON
    "inline_button",
    "button_from_spec",

    # BUILD
    "build_keyboard",
    "empty_keyboard",
    "single_button_keyboard",

    # HOME
    "home_button",
    "home_keyboard",

    # BACK
    "back_button",
    "back_keyboard",

    # CANCEL
    "cancel_button",
    "cancel_keyboard",

    # COMBINED
    "back_home_keyboard",
    "back_cancel_keyboard",

    # REFRESH
    "refresh_button",
    "refresh_keyboard",
    "refresh_back_keyboard",
    "refresh_home_keyboard",

    # CONFIRMATION
    "confirm_button",
    "decline_button",
    "confirmation_keyboard",
    "confirm_cancel_keyboard",
    "dangerous_confirmation_keyboard",

    # PAGINATION
    "pagination_buttons",
    "pagination_keyboard",
    "paginated_items_keyboard",

    # URL
    "url_keyboard",

    # OTHER
    "two_actions_keyboard",
    "actions_back_keyboard",
    "cancel_to_home_keyboard",
]