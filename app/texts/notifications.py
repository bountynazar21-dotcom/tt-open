from __future__ import annotations


# =========================================================
# OPENING NOTIFICATIONS
# =========================================================


OPENING_REMINDER = (
    "⏰ <b>Нагадування про відкриття ТТ</b>\n\n"
    "До початку роботи залишилось небагато часу."
)

OPENING_TIME_REACHED = (
    "🟢 <b>Час відкриття настав.</b>\n\n"
    "Підтвердіть, що торгова точка працює."
)

OPENING_LATE_REMINDER = (
    "⚠️ <b>ТТ ще не підтвердила відкриття.</b>\n\n"
    "Будь ласка, зробіть check-in якнайшвидше."
)

OPENING_DEADLINE_MISSED = (
    "🚨 <b>Пропущено дедлайн відкриття.</b>\n\n"
    "Торгова точка досі не підтвердила роботу."
)

OPENING_CONFIRMED_NOTIFICATION = (
    "✅ <b>Відкриття підтверджено.</b>"
)

OPENING_LATE_NOTIFICATION = (
    "⚠️ <b>Відкриття підтверджено із запізненням.</b>"
)


# =========================================================
# CLOSING NOTIFICATIONS
# =========================================================


CLOSING_REMINDER = (
    "🌙 <b>Нагадування про закриття ТТ</b>\n\n"
    "Потрібно подати вечірній звіт."
)

CLOSING_TIME_REACHED = (
    "🌙 <b>Настав час закриття.</b>\n\n"
    "Надішліть касу та чек."
)

CLOSING_LATE_REMINDER = (
    "⚠️ <b>Звіт про закриття ще не подано.</b>\n\n"
    "Будь ласка, завершіть закриття ТТ."
)

CLOSING_DEADLINE_MISSED = (
    "🚨 <b>Пропущено дедлайн закриття.</b>\n\n"
    "Вечірній звіт досі не подано."
)

CLOSING_CONFIRMED_NOTIFICATION = (
    "✅ <b>Закриття ТТ підтверджено.</b>"
)


# =========================================================
# ADMIN / LION ALERTS
# =========================================================


STORE_OPENING_LATE_ALERT = (
    "🚨 <b>Запізнення відкриття ТТ</b>"
)

STORE_OPENING_MISSED_ALERT = (
    "🚨 <b>ТТ не підтвердила відкриття</b>"
)

STORE_CLOSING_MISSED_ALERT = (
    "🚨 <b>ТТ не подала звіт про закриття</b>"
)

STORE_CASH_REPORT_ALERT = (
    "💰 <b>Отримано вечірній звіт ТТ</b>"
)


# =========================================================
# SUMMARY
# =========================================================


OPENING_SUMMARY_TITLE = (
    "📊 <b>Підсумок відкриття ТТ</b>"
)

CLOSING_SUMMARY_TITLE = (
    "📊 <b>Підсумок закриття ТТ</b>"
)

BUSH_DAILY_SUMMARY_TITLE = (
    "🌿 <b>Підсумок по кущу</b>"
)

NETWORK_DAILY_SUMMARY_TITLE = (
    "🏢 <b>Підсумок по мережі</b>"
)

NETWORK_CASH_SUMMARY_TITLE = (
    "💰 <b>Каса мережі</b>"
)


# =========================================================
# INVITES
# =========================================================


INVITE_CREATED_NOTIFICATION = (
    "🔗 <b>Створено нове запрошення.</b>"
)

INVITE_ACTIVATED_NOTIFICATION = (
    "✅ <b>Запрошення активовано.</b>"
)

INVITE_REVOKED_NOTIFICATION = (
    "🚫 <b>Запрошення відкликано.</b>"
)

INVITE_EXPIRED_NOTIFICATION = (
    "⌛ <b>Термін дії запрошення завершився.</b>"
)


# =========================================================
# USER ACCESS
# =========================================================


USER_ACCESS_GRANTED = (
    "✅ <b>Вам надано доступ до бота.</b>"
)

USER_ACCESS_REVOKED = (
    "⚫ <b>Ваш доступ до бота деактивовано.</b>"
)

USER_BLOCKED_NOTIFICATION = (
    "⛔ <b>Ваш обліковий запис заблоковано.</b>"
)

USER_ROLE_CHANGED = (
    "🔄 <b>Вашу роль у системі змінено.</b>"
)

USER_STORE_BINDING_CHANGED = (
    "🏪 <b>Змінено вашу прив'язку до торгової точки.</b>"
)

USER_BUSH_BINDING_CHANGED = (
    "🌿 <b>Змінено вашу прив'язку до куща.</b>"
)


# =========================================================
# SCHEDULE
# =========================================================


SCHEDULE_CHANGED_NOTIFICATION = (
    "📅 <b>Графік роботи ТТ змінено.</b>"
)

STORE_CLUSTER_CHANGED_NOTIFICATION = (
    "🕐 <b>Кластер відкриття ТТ змінено.</b>"
)

SCHEDULE_EXCEPTION_NOTIFICATION = (
    "📅 <b>Для ТТ встановлено виняток графіка.</b>"
)


# =========================================================
# SYSTEM
# =========================================================


SYSTEM_NOTIFICATION = (
    "ℹ️ <b>Системне повідомлення</b>"
)

SYSTEM_WARNING = (
    "⚠️ <b>Системне попередження</b>"
)

SYSTEM_ERROR_NOTIFICATION = (
    "❌ <b>Системна помилка</b>"
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "OPENING_REMINDER",
    "OPENING_TIME_REACHED",
    "OPENING_LATE_REMINDER",
    "OPENING_DEADLINE_MISSED",
    "OPENING_CONFIRMED_NOTIFICATION",
    "OPENING_LATE_NOTIFICATION",

    "CLOSING_REMINDER",
    "CLOSING_TIME_REACHED",
    "CLOSING_LATE_REMINDER",
    "CLOSING_DEADLINE_MISSED",
    "CLOSING_CONFIRMED_NOTIFICATION",

    "STORE_OPENING_LATE_ALERT",
    "STORE_OPENING_MISSED_ALERT",
    "STORE_CLOSING_MISSED_ALERT",
    "STORE_CASH_REPORT_ALERT",

    "OPENING_SUMMARY_TITLE",
    "CLOSING_SUMMARY_TITLE",
    "BUSH_DAILY_SUMMARY_TITLE",
    "NETWORK_DAILY_SUMMARY_TITLE",
    "NETWORK_CASH_SUMMARY_TITLE",

    "INVITE_CREATED_NOTIFICATION",
    "INVITE_ACTIVATED_NOTIFICATION",
    "INVITE_REVOKED_NOTIFICATION",
    "INVITE_EXPIRED_NOTIFICATION",

    "USER_ACCESS_GRANTED",
    "USER_ACCESS_REVOKED",
    "USER_BLOCKED_NOTIFICATION",
    "USER_ROLE_CHANGED",
    "USER_STORE_BINDING_CHANGED",
    "USER_BUSH_BINDING_CHANGED",

    "SCHEDULE_CHANGED_NOTIFICATION",
    "STORE_CLUSTER_CHANGED_NOTIFICATION",
    "SCHEDULE_EXCEPTION_NOTIFICATION",

    "SYSTEM_NOTIFICATION",
    "SYSTEM_WARNING",
    "SYSTEM_ERROR_NOTIFICATION",
]