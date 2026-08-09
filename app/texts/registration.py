from __future__ import annotations


# =========================================================
# REGISTRATION
# =========================================================


REGISTRATION_TITLE = (
    "📝 <b>Реєстрація</b>"
)

REGISTRATION_START = (
    "📝 <b>Для початку роботи "
    "потрібно завершити реєстрацію.</b>"
)

REGISTRATION_HELP = (
    "ℹ️ <b>Допомога з реєстрацією</b>\n\n"
    "Для роботи з ботом потрібно "
    "підтвердити свій номер телефону "
    "та отримати відповідний доступ."
)


# =========================================================
# CONTACT
# =========================================================


ASK_CONTACT = (
    "📱 <b>Підтвердьте ваш номер телефону.</b>\n\n"
    "Натисніть кнопку нижче "
    "«Надіслати мій номер».\n\n"
    "Важливо: потрібно надіслати "
    "саме свій Telegram-контакт."
)

CONTACT_ONLY_OWN = (
    "⚠️ Потрібно надіслати "
    "саме свій Telegram-контакт."
)

CONTACT_INVALID = (
    "❌ Не вдалося підтвердити номер телефону."
)

CONTACT_MANUAL_NOT_ALLOWED = (
    "📱 Будь ласка, не вводьте "
    "номер вручну.\n\n"
    "Натисніть кнопку "
    "<b>«Надіслати мій номер»</b>."
)

CONTACT_SAVED = (
    "✅ Номер телефону збережено."
)


# =========================================================
# STATUS
# =========================================================


REGISTRATION_PENDING = (
    "⏳ <b>Заявка ще очікує підтвердження.</b>\n\n"
    "Спробуйте перевірити статус пізніше."
)

REGISTRATION_ACTIVE = (
    "✅ <b>Доступ активовано.</b>\n\n"
    "Можете переходити до головного меню."
)

REGISTRATION_BLOCKED = (
    "⛔ <b>Ваш обліковий запис "
    "заблокований.</b>"
)

REGISTRATION_INACTIVE = (
    "⚫ <b>Ваш доступ неактивний.</b>"
)

REGISTRATION_REJECTED = (
    "❌ <b>Заявку було відхилено.</b>"
)

REGISTRATION_NOT_COMPLETED = (
    "📝 Реєстрацію ще не завершено."
)


# =========================================================
# INVITE
# =========================================================


INVITE_ACTIVATION_SUCCESS = (
    "✅ <b>Запрошення активовано.</b>\n\n"
    "Доступ успішно надано."
)

INVITE_ACTIVATION_ERROR = (
    "❌ <b>Не вдалося активувати "
    "запрошення.</b>\n\n"
    "Посилання могло бути "
    "прострочене, використане "
    "або відкликане."
)

INVITE_INVALID = (
    "❌ Некоректне invite-посилання."
)

INVITE_EXPIRED = (
    "⌛ Термін дії запрошення завершився."
)

INVITE_ALREADY_USED = (
    "⚠️ Це запрошення вже використано."
)

INVITE_REVOKED = (
    "🚫 Це запрошення було відкликано."
)


# =========================================================
# ACCOUNT
# =========================================================


ACCOUNT_CREATE_ERROR = (
    "⚠️ Не вдалося створити "
    "обліковий запис.\n\n"
    "Спробуйте /start ще раз."
)

ACCOUNT_NOT_FOUND = (
    "❌ Обліковий запис не знайдено."
)


# =========================================================
# BUTTON / CALLBACK
# =========================================================


REGISTRATION_REFRESH = (
    "🔄 Перевіряю статус..."
)

REGISTRATION_CANCELLED = (
    "❌ Реєстрацію скасовано."
)

REGISTRATION_CALLBACK_EXPIRED = (
    "⚠️ Ця кнопка вже неактуальна. "
    "Використайте /start."
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "REGISTRATION_TITLE",
    "REGISTRATION_START",
    "REGISTRATION_HELP",

    "ASK_CONTACT",
    "CONTACT_ONLY_OWN",
    "CONTACT_INVALID",
    "CONTACT_MANUAL_NOT_ALLOWED",
    "CONTACT_SAVED",

    "REGISTRATION_PENDING",
    "REGISTRATION_ACTIVE",
    "REGISTRATION_BLOCKED",
    "REGISTRATION_INACTIVE",
    "REGISTRATION_REJECTED",
    "REGISTRATION_NOT_COMPLETED",

    "INVITE_ACTIVATION_SUCCESS",
    "INVITE_ACTIVATION_ERROR",
    "INVITE_INVALID",
    "INVITE_EXPIRED",
    "INVITE_ALREADY_USED",
    "INVITE_REVOKED",

    "ACCOUNT_CREATE_ERROR",
    "ACCOUNT_NOT_FOUND",

    "REGISTRATION_REFRESH",
    "REGISTRATION_CANCELLED",
    "REGISTRATION_CALLBACK_EXPIRED",
]