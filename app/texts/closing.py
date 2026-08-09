from __future__ import annotations


# =========================================================
# CLOSING
# =========================================================


CLOSING_TITLE = (
    "🌙 <b>Закриття торгової точки</b>"
)

CLOSING_START = (
    "🌙 <b>Закриття ТТ</b>\n\n"
    "Для завершення робочого дня "
    "потрібно подати вечірній звіт."
)

CLOSING_ALREADY_SUBMITTED = (
    "✅ Звіт про закриття за сьогодні "
    "вже подано."
)

CLOSING_NOT_AVAILABLE = (
    "⚠️ Зараз закриття для цієї ТТ "
    "недоступне."
)


# =========================================================
# STORE
# =========================================================


SELECT_CLOSING_STORE = (
    "🏪 Оберіть торгову точку, "
    "яку потрібно закрити."
)

CLOSING_STORE_NOT_FOUND = (
    "❌ Торгову точку не знайдено."
)

CLOSING_STORE_INACTIVE = (
    "⚠️ Ця торгова точка неактивна."
)


# =========================================================
# CASH
# =========================================================


ASK_CASH_AMOUNT = (
    "💰 <b>Вкажіть суму каси.</b>\n\n"
    "Введіть суму цифрами.\n"
    "Наприклад: <code>15420.50</code>"
)

INVALID_CASH_AMOUNT = (
    "❌ Некоректна сума каси.\n\n"
    "Введіть лише число.\n"
    "Наприклад: <code>15420.50</code>"
)

CASH_AMOUNT_TOO_LOW = (
    "❌ Сума каси не може бути від'ємною."
)

CASH_AMOUNT_SAVED = (
    "✅ Суму каси збережено."
)


# =========================================================
# RECEIPT
# =========================================================


ASK_RECEIPT = (
    "🧾 <b>Надішліть фото чека / "
    "вечірнього звіту.</b>"
)

INVALID_RECEIPT = (
    "❌ Не вдалося розпізнати файл.\n\n"
    "Надішліть фото або документ "
    "із чеком."
)

RECEIPT_SAVED = (
    "✅ Чек отримано."
)


# =========================================================
# CONFIRM
# =========================================================


CLOSING_CONFIRM = (
    "📋 <b>Перевірте дані перед відправкою.</b>"
)

CLOSING_CONFIRM_QUESTION = (
    "Все правильно?"
)

CLOSING_SUBMITTING = (
    "⏳ Зберігаю звіт про закриття..."
)


# =========================================================
# SUCCESS
# =========================================================


CLOSING_SUCCESS = (
    "✅ <b>ТТ успішно закрито.</b>\n\n"
    "Вечірній звіт збережено."
)

CLOSING_SUCCESS_LATE = (
    "✅ <b>Звіт про закриття прийнято.</b>\n\n"
    "⚠️ Звіт подано після встановленого дедлайну."
)


# =========================================================
# DEADLINE
# =========================================================


CLOSING_REMINDER = (
    "🌙 Нагадування: настав час "
    "подати звіт про закриття ТТ."
)

CLOSING_DEADLINE_SOON = (
    "⏰ <b>Нагадування про закриття.</b>\n\n"
    "До дедлайну залишилось небагато часу."
)

CLOSING_DEADLINE_MISSED = (
    "🚨 <b>Пропущено дедлайн закриття.</b>\n\n"
    "Звіт по ТТ досі не подано."
)


# =========================================================
# EDIT
# =========================================================


CLOSING_EDIT_TITLE = (
    "✏️ <b>Коригування звіту про закриття</b>"
)

ASK_NEW_CASH_AMOUNT = (
    "💰 Введіть нову суму каси."
)

ASK_NEW_RECEIPT = (
    "🧾 Надішліть новий чек."
)

ASK_CLOSING_EDIT_REASON = (
    "📝 Вкажіть причину коригування."
)

CLOSING_EDIT_CONFIRM = (
    "⚠️ Підтвердіть зміну звіту."
)

CLOSING_EDIT_SUCCESS = (
    "✅ <b>Звіт про закриття оновлено.</b>"
)


# =========================================================
# MANUAL
# =========================================================


MANUAL_CLOSING_TITLE = (
    "🛠 <b>Ручне підтвердження закриття</b>"
)

MANUAL_CLOSING_REASON = (
    "📝 Вкажіть причину ручного підтвердження."
)

MANUAL_CLOSING_SUCCESS = (
    "✅ Закриття підтверджено вручну."
)


# =========================================================
# GROUP DELIVERY
# =========================================================


CLOSING_SENT_TO_GROUP = (
    "✅ Звіт відправлено в групу."
)

CLOSING_GROUP_SEND_FAILED = (
    "⚠️ Звіт збережено, але не вдалося "
    "відправити його в Telegram-групу."
)

CLOSING_RESEND_SUCCESS = (
    "✅ Звіт повторно відправлено в групу."
)


# =========================================================
# ERRORS
# =========================================================


CLOSING_ERROR = (
    "❌ Не вдалося зберегти звіт про закриття.\n\n"
    "Спробуйте ще раз."
)

CLOSING_CANCELLED = (
    "❌ Закриття скасовано."
)

CLOSING_ACCESS_DENIED = (
    "⛔ У вас немає доступу до закриття цієї ТТ."
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "CLOSING_TITLE",
    "CLOSING_START",
    "CLOSING_ALREADY_SUBMITTED",
    "CLOSING_NOT_AVAILABLE",

    "SELECT_CLOSING_STORE",
    "CLOSING_STORE_NOT_FOUND",
    "CLOSING_STORE_INACTIVE",

    "ASK_CASH_AMOUNT",
    "INVALID_CASH_AMOUNT",
    "CASH_AMOUNT_TOO_LOW",
    "CASH_AMOUNT_SAVED",

    "ASK_RECEIPT",
    "INVALID_RECEIPT",
    "RECEIPT_SAVED",

    "CLOSING_CONFIRM",
    "CLOSING_CONFIRM_QUESTION",
    "CLOSING_SUBMITTING",

    "CLOSING_SUCCESS",
    "CLOSING_SUCCESS_LATE",

    "CLOSING_REMINDER",
    "CLOSING_DEADLINE_SOON",
    "CLOSING_DEADLINE_MISSED",

    "CLOSING_EDIT_TITLE",
    "ASK_NEW_CASH_AMOUNT",
    "ASK_NEW_RECEIPT",
    "ASK_CLOSING_EDIT_REASON",
    "CLOSING_EDIT_CONFIRM",
    "CLOSING_EDIT_SUCCESS",

    "MANUAL_CLOSING_TITLE",
    "MANUAL_CLOSING_REASON",
    "MANUAL_CLOSING_SUCCESS",

    "CLOSING_SENT_TO_GROUP",
    "CLOSING_GROUP_SEND_FAILED",
    "CLOSING_RESEND_SUCCESS",

    "CLOSING_ERROR",
    "CLOSING_CANCELLED",
    "CLOSING_ACCESS_DENIED",
]