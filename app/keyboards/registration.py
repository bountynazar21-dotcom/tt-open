from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.keyboards.callbacks import (
    MainMenuAction,
    MainMenuCallback,
    pack_checked,
)


# =========================================================
# REGISTRATION CALLBACKS
# =========================================================


class RegistrationAction(StrEnum):
    """
    Дії під час реєстрації.
    """

    START = "start"

    REFRESH = "refresh"

    STATUS = "status"

    HELP = "help"

    RETRY = "retry"

    CANCEL = "cancel"

    HOME = "home"


class RegistrationCallback(
    CallbackData,
    prefix="reg",
):
    """
    reg:<action>
    """

    action: RegistrationAction


# =========================================================
# BUTTON HELPERS
# =========================================================


def registration_button(
    *,
    text: str,
    action: RegistrationAction,
) -> InlineKeyboardButton:
    """
    Створює registration callback кнопку.
    """

    normalized_text = (
        text.strip()
    )

    if not normalized_text:
        raise ValueError(
            "Текст кнопки не може "
            "бути порожнім."
        )

    return InlineKeyboardButton(
        text=normalized_text,
        callback_data=pack_checked(
            RegistrationCallback(
                action=action
            )
        ),
    )


# =========================================================
# START REGISTRATION
# =========================================================


def registration_start_keyboard(
) -> InlineKeyboardMarkup:
    """
    Початок реєстрації.

    Використовується, якщо користувач
    щойно зайшов у бот.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                registration_button(
                    text="📝 Почати реєстрацію",
                    action=(
                        RegistrationAction.START
                    ),
                )
            ],
            [
                registration_button(
                    text="ℹ️ Допомога",
                    action=(
                        RegistrationAction.HELP
                    ),
                )
            ],
        ]
    )


# =========================================================
# PHONE / CONTACT
# =========================================================


def contact_request_keyboard(
    *,
    text: str = "📱 Надіслати мій номер",
) -> ReplyKeyboardMarkup:
    """
    Telegram сам передає номер
    поточного користувача.

    Це безпечніше, ніж просити
    вводити номер вручну.
    """

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=text,
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True,
        input_field_placeholder=(
            "Натисніть кнопку нижче"
        ),
    )


def remove_registration_reply_keyboard(
) -> ReplyKeyboardRemove:
    """
    Прибирає ReplyKeyboard
    після отримання контакту.
    """

    return ReplyKeyboardRemove(
        remove_keyboard=True,
        selective=True,
    )


# =========================================================
# WAITING APPROVAL
# =========================================================


def pending_registration_keyboard(
) -> InlineKeyboardMarkup:
    """
    Користувач уже зареєстрований,
    але ще очікує підтвердження.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                registration_button(
                    text="🔄 Перевірити статус",
                    action=(
                        RegistrationAction.REFRESH
                    ),
                )
            ],
            [
                registration_button(
                    text="ℹ️ Що далі?",
                    action=(
                        RegistrationAction.HELP
                    ),
                )
            ],
        ]
    )


# =========================================================
# STATUS
# =========================================================


def registration_status_keyboard(
    *,
    allow_retry: bool = False,
    show_help: bool = True,
) -> InlineKeyboardMarkup:
    """
    Універсальна клавіатура статусу заявки.
    """

    rows: list[
        list[InlineKeyboardButton]
    ] = [
        [
            registration_button(
                text="🔄 Оновити статус",
                action=(
                    RegistrationAction.REFRESH
                ),
            )
        ]
    ]

    if allow_retry:
        rows.append(
            [
                registration_button(
                    text="🔁 Спробувати ще раз",
                    action=(
                        RegistrationAction.RETRY
                    ),
                )
            ]
        )

    if show_help:
        rows.append(
            [
                registration_button(
                    text="ℹ️ Допомога",
                    action=(
                        RegistrationAction.HELP
                    ),
                )
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# =========================================================
# REJECTED
# =========================================================


def rejected_registration_keyboard(
) -> InlineKeyboardMarkup:
    """
    Якщо заявку відхилили.

    Користувач може повторити
    реєстрацію, якщо це дозволить handler.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                registration_button(
                    text="🔁 Подати заявку повторно",
                    action=(
                        RegistrationAction.RETRY
                    ),
                )
            ],
            [
                registration_button(
                    text="ℹ️ Допомога",
                    action=(
                        RegistrationAction.HELP
                    ),
                )
            ],
        ]
    )


# =========================================================
# BLOCKED
# =========================================================


def blocked_registration_keyboard(
) -> InlineKeyboardMarkup:
    """
    Для заблокованого користувача.

    Тут навмисно немає кнопки
    повторної реєстрації.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                registration_button(
                    text="🔄 Перевірити статус",
                    action=(
                        RegistrationAction.REFRESH
                    ),
                )
            ],
            [
                registration_button(
                    text="ℹ️ Допомога",
                    action=(
                        RegistrationAction.HELP
                    ),
                )
            ],
        ]
    )


# =========================================================
# INACTIVE
# =========================================================


def inactive_registration_keyboard(
) -> InlineKeyboardMarkup:
    """
    Користувач був активним,
    але його обліковий запис вимкнули.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                registration_button(
                    text="🔄 Перевірити доступ",
                    action=(
                        RegistrationAction.REFRESH
                    ),
                )
            ],
            [
                registration_button(
                    text="ℹ️ Допомога",
                    action=(
                        RegistrationAction.HELP
                    ),
                )
            ],
        ]
    )


# =========================================================
# CANCEL
# =========================================================


def registration_cancel_keyboard(
    *,
    text: str = "❌ Скасувати",
) -> InlineKeyboardMarkup:
    """
    Скасування поточного кроку.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                registration_button(
                    text=text,
                    action=(
                        RegistrationAction.CANCEL
                    ),
                )
            ]
        ]
    )


# =========================================================
# RETRY / CANCEL
# =========================================================


def registration_retry_cancel_keyboard(
) -> InlineKeyboardMarkup:
    """
    Повторити або скасувати.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                registration_button(
                    text="🔁 Повторити",
                    action=(
                        RegistrationAction.RETRY
                    ),
                )
            ],
            [
                registration_button(
                    text="❌ Скасувати",
                    action=(
                        RegistrationAction.CANCEL
                    ),
                )
            ],
        ]
    )


# =========================================================
# SUCCESS
# =========================================================


def registration_completed_keyboard(
    *,
    text: str = "🏠 Перейти в меню",
) -> InlineKeyboardMarkup:
    """
    Показуємо після успішної
    активації користувача.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=pack_checked(
                        MainMenuCallback(
                            action=(
                                MainMenuAction.HOME
                            )
                        )
                    ),
                )
            ]
        ]
    )


# =========================================================
# INVITE ACTIVATED
# =========================================================


def invite_activated_keyboard(
) -> InlineKeyboardMarkup:
    """
    Після успішної активації
    invite-link.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Продовжити",
                    callback_data=pack_checked(
                        MainMenuCallback(
                            action=(
                                MainMenuAction.HOME
                            )
                        )
                    ),
                )
            ]
        ]
    )


# =========================================================
# REFRESH ONLY
# =========================================================


def registration_refresh_keyboard(
    *,
    text: str = "🔄 Оновити",
) -> InlineKeyboardMarkup:
    """
    Одна кнопка оновлення.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                registration_button(
                    text=text,
                    action=(
                        RegistrationAction.REFRESH
                    ),
                )
            ]
        ]
    )


# =========================================================
# HELP BACK
# =========================================================


def registration_help_keyboard(
) -> InlineKeyboardMarkup:
    """
    Кнопка повернення з довідки.
    """

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                registration_button(
                    text="🔙 Назад",
                    action=(
                        RegistrationAction.STATUS
                    ),
                )
            ]
        ]
    )


# =========================================================
# PHONE VALIDATION ERROR
# =========================================================


def contact_retry_keyboard(
) -> ReplyKeyboardMarkup:
    """
    Якщо користувач надіслав
    не свій контакт або звичайний текст.
    """

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📱 Надіслати мій номер",
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True,
        input_field_placeholder=(
            "Використайте кнопку для номера"
        ),
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    # CALLBACK
    "RegistrationAction",
    "RegistrationCallback",

    # HELPERS
    "registration_button",

    # START
    "registration_start_keyboard",

    # CONTACT
    "contact_request_keyboard",
    "contact_retry_keyboard",
    "remove_registration_reply_keyboard",

    # STATUS
    "pending_registration_keyboard",
    "registration_status_keyboard",
    "rejected_registration_keyboard",
    "blocked_registration_keyboard",
    "inactive_registration_keyboard",

    # CONTROL
    "registration_cancel_keyboard",
    "registration_retry_cancel_keyboard",
    "registration_refresh_keyboard",
    "registration_help_keyboard",

    # SUCCESS
    "registration_completed_keyboard",
    "invite_activated_keyboard",
]