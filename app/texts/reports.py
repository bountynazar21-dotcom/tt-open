from __future__ import annotations


# =========================================================
# REPORTS
# =========================================================


REPORTS_TITLE = (
    "📊 <b>Звіти</b>"
)

REPORTS_MENU = (
    "📊 <b>Звіти</b>\n\n"
    "Оберіть тип звіту:"
)

REPORTS_NO_DATA = (
    "📭 За вибраний період даних немає."
)

REPORTS_BUILDING = (
    "⏳ Формую звіт..."
)

REPORTS_READY = (
    "✅ <b>Звіт сформовано.</b>"
)


# =========================================================
# PERIOD
# =========================================================


SELECT_REPORT_PERIOD = (
    "📅 Оберіть період звіту."
)

SELECT_REPORT_DATE = (
    "📅 Оберіть дату."
)

SELECT_REPORT_DATE_FROM = (
    "📅 Вкажіть початкову дату."
)

SELECT_REPORT_DATE_TO = (
    "📅 Вкажіть кінцеву дату."
)

INVALID_REPORT_PERIOD = (
    "❌ Некоректний період звіту."
)

INVALID_REPORT_DATE_RANGE = (
    "❌ Кінцева дата не може бути "
    "раніше початкової."
)


# =========================================================
# SCOPE
# =========================================================


SELECT_REPORT_SCOPE = (
    "🎯 Оберіть область звіту."
)

SELECT_REPORT_BUSH = (
    "🌿 Оберіть кущ."
)

SELECT_REPORT_STORE = (
    "🏪 Оберіть торгову точку."
)

REPORT_SCOPE_NETWORK = (
    "🏢 Вся мережа"
)

REPORT_SCOPE_BUSH = (
    "🌿 Кущ"
)

REPORT_SCOPE_STORE = (
    "🏪 Торгова точка"
)


# =========================================================
# OPENING REPORT
# =========================================================


OPENING_REPORT_TITLE = (
    "🟢 <b>Звіт по відкриттях</b>"
)

OPENING_REPORT_EMPTY = (
    "📭 За вибраний період "
    "даних про відкриття немає."
)

OPENING_REPORT_ON_TIME = (
    "✅ Вчасно"
)

OPENING_REPORT_LATE = (
    "⚠️ Із запізненням"
)

OPENING_REPORT_MISSED = (
    "🚨 Не підтверджено"
)


# =========================================================
# CLOSING REPORT
# =========================================================


CLOSING_REPORT_TITLE = (
    "🌙 <b>Звіт по закриттях</b>"
)

CLOSING_REPORT_EMPTY = (
    "📭 За вибраний період "
    "даних про закриття немає."
)

CLOSING_REPORT_ON_TIME = (
    "✅ Вчасно"
)

CLOSING_REPORT_LATE = (
    "⚠️ Із запізненням"
)

CLOSING_REPORT_MISSED = (
    "🚨 Не подано"
)


# =========================================================
# CASH REPORT
# =========================================================


CASH_REPORT_TITLE = (
    "💰 <b>Звіт по касі</b>"
)

CASH_REPORT_EMPTY = (
    "📭 За вибраний період "
    "даних по касі немає."
)

NETWORK_CASH_TITLE = (
    "💰 <b>Каса всієї мережі</b>"
)

TOTAL_CASH_LABEL = (
    "💰 Загальна каса:"
)

AVERAGE_CASH_LABEL = (
    "📊 Середня каса:"
)


# =========================================================
# LATENESS
# =========================================================


LATENESS_REPORT_TITLE = (
    "⏰ <b>Звіт по запізненнях</b>"
)

LATENESS_REPORT_EMPTY = (
    "✅ За вибраний період "
    "запізнень не зафіксовано."
)

LATE_MINUTES_LABEL = (
    "⏱ Хвилин запізнення:"
)

PENALTY_LABEL = (
    "💸 Штраф:"
)


# =========================================================
# SUMMARY
# =========================================================


DAILY_SUMMARY_TITLE = (
    "📅 <b>Денний підсумок</b>"
)

WEEKLY_SUMMARY_TITLE = (
    "📆 <b>Тижневий підсумок</b>"
)

MONTHLY_SUMMARY_TITLE = (
    "🗓 <b>Місячний підсумок</b>"
)

BUSH_SUMMARY_TITLE = (
    "🌿 <b>Підсумок по кущу</b>"
)

NETWORK_SUMMARY_TITLE = (
    "🏢 <b>Підсумок по мережі</b>"
)


# =========================================================
# COUNTERS
# =========================================================


TOTAL_STORES_LABEL = (
    "🏪 Всього ТТ:"
)

OPENED_ON_TIME_LABEL = (
    "✅ Відкрито вчасно:"
)

OPENED_LATE_LABEL = (
    "⚠️ Відкрито із запізненням:"
)

OPENING_MISSED_LABEL = (
    "🚨 Не підтвердили відкриття:"
)

CLOSED_ON_TIME_LABEL = (
    "✅ Закрито вчасно:"
)

CLOSED_LATE_LABEL = (
    "⚠️ Закрито із запізненням:"
)

CLOSING_MISSED_LABEL = (
    "🚨 Не подали закриття:"
)


# =========================================================
# EXCEL
# =========================================================


EXPORT_REPORT_TITLE = (
    "📥 <b>Експорт звіту</b>"
)

EXPORT_REPORT_CONFIRM = (
    "📊 Сформувати Excel-файл?"
)

EXPORT_GENERATING = (
    "⏳ Генерую Excel-файл..."
)

EXPORT_READY = (
    "✅ Excel-звіт готовий."
)

EXPORT_FAILED = (
    "❌ Не вдалося сформувати Excel-звіт."
)

EXPORT_EMPTY = (
    "📭 Немає даних для експорту."
)


# =========================================================
# ERRORS
# =========================================================


REPORT_NOT_FOUND = (
    "❌ Звіт не знайдено."
)

REPORT_BUILD_ERROR = (
    "❌ Не вдалося сформувати звіт."
)

REPORT_ACCESS_DENIED = (
    "⛔ У вас немає доступу "
    "до цього звіту."
)

REPORT_CANCELLED = (
    "❌ Формування звіту скасовано."
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "REPORTS_TITLE",
    "REPORTS_MENU",
    "REPORTS_NO_DATA",
    "REPORTS_BUILDING",
    "REPORTS_READY",

    "SELECT_REPORT_PERIOD",
    "SELECT_REPORT_DATE",
    "SELECT_REPORT_DATE_FROM",
    "SELECT_REPORT_DATE_TO",
    "INVALID_REPORT_PERIOD",
    "INVALID_REPORT_DATE_RANGE",

    "SELECT_REPORT_SCOPE",
    "SELECT_REPORT_BUSH",
    "SELECT_REPORT_STORE",
    "REPORT_SCOPE_NETWORK",
    "REPORT_SCOPE_BUSH",
    "REPORT_SCOPE_STORE",

    "OPENING_REPORT_TITLE",
    "OPENING_REPORT_EMPTY",
    "OPENING_REPORT_ON_TIME",
    "OPENING_REPORT_LATE",
    "OPENING_REPORT_MISSED",

    "CLOSING_REPORT_TITLE",
    "CLOSING_REPORT_EMPTY",
    "CLOSING_REPORT_ON_TIME",
    "CLOSING_REPORT_LATE",
    "CLOSING_REPORT_MISSED",

    "CASH_REPORT_TITLE",
    "CASH_REPORT_EMPTY",
    "NETWORK_CASH_TITLE",
    "TOTAL_CASH_LABEL",
    "AVERAGE_CASH_LABEL",

    "LATENESS_REPORT_TITLE",
    "LATENESS_REPORT_EMPTY",
    "LATE_MINUTES_LABEL",
    "PENALTY_LABEL",

    "DAILY_SUMMARY_TITLE",
    "WEEKLY_SUMMARY_TITLE",
    "MONTHLY_SUMMARY_TITLE",
    "BUSH_SUMMARY_TITLE",
    "NETWORK_SUMMARY_TITLE",

    "TOTAL_STORES_LABEL",
    "OPENED_ON_TIME_LABEL",
    "OPENED_LATE_LABEL",
    "OPENING_MISSED_LABEL",
    "CLOSED_ON_TIME_LABEL",
    "CLOSED_LATE_LABEL",
    "CLOSING_MISSED_LABEL",

    "EXPORT_REPORT_TITLE",
    "EXPORT_REPORT_CONFIRM",
    "EXPORT_GENERATING",
    "EXPORT_READY",
    "EXPORT_FAILED",
    "EXPORT_EMPTY",

    "REPORT_NOT_FOUND",
    "REPORT_BUILD_ERROR",
    "REPORT_ACCESS_DENIED",
    "REPORT_CANCELLED",
]