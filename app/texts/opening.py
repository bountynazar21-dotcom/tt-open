from __future__ import annotations


# =========================================================
# OPENING
# =========================================================


OPENING_TITLE = (
    "🟢 <b>Відкриття торгової точки</b>"
)

OPENING_START = (
    "🟢 <b>Відкриття ТТ</b>\n\n"
    "Підтвердіть, що торгова точка "
    "відкрита та працює."
)

OPENING_ALREADY_CONFIRMED = (
    "✅ Відкриття цієї ТТ за сьогодні "
    "вже підтверджено."
)

OPENING_NOT_AVAILABLE = (
    "⚠️ Зараз підтвердження відкриття "
    "для цієї ТТ недоступне."
)


# =========================================================
# STORE
# =========================================================


SELECT_OPENING_STORE = (
    "🏪 Оберіть торгову точку, "
    "відкриття якої потрібно підтвердити."
)

OPENING_STORE_NOT_FOUND = (
    "❌ Торгову точку не знайдено."
)

OPENING_STORE_INACTIVE = (
    "⚫ Ця торгова точка неактивна."
)

OPENING_STORE_ACCESS_DENIED = (
    "⛔ У вас немає доступу "
    "до цієї торгової точки."
)


# =========================================================
# CONFIRMATION
# =========================================================


OPENING_CONFIRM = (
    "🟢 <b>Підтвердити відкриття ТТ?</b>"
)

OPENING_CONFIRM_TEXT = (
    "Після підтвердження бот зафіксує "
    "поточний час відкриття."
)

OPENING_SUBMITTING = (
    "⏳ Фіксую відкриття..."
)


# =========================================================
# SUCCESS
# =========================================================


OPENING_SUCCESS = (
    "✅ <b>Відкриття підтверджено.</b>"
)

OPENING_SUCCESS_ON_TIME = (
    "✅ <b>ТТ відкрита вчасно.</b>"
)

OPENING_SUCCESS_EARLY = (
    "✅ <b>ТТ відкрита завчасно.</b>"
)

OPENING_SUCCESS_LATE = (
    "⚠️ <b>Відкриття підтверджено "
    "із запізненням.</b>"
)


# =========================================================
# LATE
# =========================================================


OPENING_LATE_TITLE = (
    "⚠️ <b>Запізнення відкриття</b>"
)

OPENING_LATE_TEXT = (
    "ТТ була відкрита після "
    "встановленого часу."
)

OPENING_DEADLINE_MISSED = (
    "🚨 <b>Пропущено дедлайн відкриття.</b>\n\n"
    "ТТ досі не підтвердила роботу."
)

OPENING_AFTER_ALERT = (
    "⚠️ Відкриття підтверджено "
    "після сповіщення про запізнення."
)


# =========================================================
# REMINDERS
# =========================================================


OPENING_REMINDER = (
    "⏰ <b>Нагадування про відкриття</b>\n\n"
    "Незабаром потрібно підтвердити "
    "роботу торгової точки."
)

OPENING_TIME_REACHED = (
    "🟢 <b>Настав час відкриття.</b>\n\n"
    "Підтвердіть, що ТТ працює."
)

OPENING_LATE_REMINDER = (
    "⚠️ <b>Відкриття ще не підтверджено.</b>\n\n"
    "Зробіть check-in якнайшвидше."
)


# =========================================================
# MANUAL EDIT
# =========================================================


OPENING_EDIT_TITLE = (
    "✏️ <b>Коригування відкриття ТТ</b>"
)

ASK_NEW_OPENING_TIME = (
    "🕐 Введіть новий фактичний "
    "час відкриття."
)

ASK_OPENING_STATUS = (
    "📌 Оберіть новий статус відкриття."
)

ASK_OPENING_EDIT_REASON = (
    "📝 Вкажіть причину коригування."
)

OPENING_EDIT_CONFIRM = (
    "⚠️ Підтвердіть зміну "
    "даних відкриття."
)

OPENING_EDIT_SUCCESS = (
    "✅ <b>Дані відкриття оновлено.</b>"
)


# =========================================================
# MANUAL CONFIRM
# =========================================================


MANUAL_OPENING_TITLE = (
    "🛠 <b>Ручне підтвердження відкриття</b>"
)

MANUAL_OPENING_REASON = (
    "📝 Вкажіть причину "
    "ручного підтвердження."
)

MANUAL_OPENING_SUCCESS = (
    "✅ Відкриття підтверджено вручну."
)


# =========================================================
# REPORT
# =========================================================


OPENING_REPORT_TITLE = (
    "📊 <b>Звіт по відкриттях</b>"
)

OPENING_REPORT_EMPTY = (
    "📭 За вибраний період "
    "даних про відкриття немає."
)


# =========================================================
# ERRORS
# =========================================================


OPENING_ERROR = (
    "❌ Не вдалося зберегти "
    "відкриття ТТ.\n\n"
    "Спробуйте ще раз."
)

OPENING_CANCELLED = (
    "❌ Підтвердження відкриття скасовано."
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "OPENING_TITLE",
    "OPENING_START",
    "OPENING_ALREADY_CONFIRMED",
    "OPENING_NOT_AVAILABLE",

    "SELECT_OPENING_STORE",
    "OPENING_STORE_NOT_FOUND",
    "OPENING_STORE_INACTIVE",
    "OPENING_STORE_ACCESS_DENIED",

    "OPENING_CONFIRM",
    "OPENING_CONFIRM_TEXT",
    "OPENING_SUBMITTING",

    "OPENING_SUCCESS",
    "OPENING_SUCCESS_ON_TIME",
    "OPENING_SUCCESS_EARLY",
    "OPENING_SUCCESS_LATE",

    "OPENING_LATE_TITLE",
    "OPENING_LATE_TEXT",
    "OPENING_DEADLINE_MISSED",
    "OPENING_AFTER_ALERT",

    "OPENING_REMINDER",
    "OPENING_TIME_REACHED",
    "OPENING_LATE_REMINDER",

    "OPENING_EDIT_TITLE",
    "ASK_NEW_OPENING_TIME",
    "ASK_OPENING_STATUS",
    "ASK_OPENING_EDIT_REASON",
    "OPENING_EDIT_CONFIRM",
    "OPENING_EDIT_SUCCESS",

    "MANUAL_OPENING_TITLE",
    "MANUAL_OPENING_REASON",
    "MANUAL_OPENING_SUCCESS",

    "OPENING_REPORT_TITLE",
    "OPENING_REPORT_EMPTY",

    "OPENING_ERROR",
    "OPENING_CANCELLED",
]