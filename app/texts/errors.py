from __future__ import annotations


# =========================================================
# GENERIC
# =========================================================


UNKNOWN_ERROR = (
    "❌ Сталася невідома помилка.\n\n"
    "Спробуйте ще раз."
)

INTERNAL_ERROR = (
    "❌ Сталася внутрішня помилка сервісу.\n\n"
    "Спробуйте повторити дію пізніше."
)

TEMPORARY_ERROR = (
    "⚠️ Тимчасова помилка.\n\n"
    "Спробуйте ще раз через кілька секунд."
)

OPERATION_FAILED = (
    "❌ Не вдалося виконати операцію."
)


# =========================================================
# DATABASE
# =========================================================


DATABASE_ERROR = (
    "❌ Помилка роботи з базою даних."
)

DATABASE_CONNECTION_ERROR = (
    "❌ Не вдалося підключитися до бази даних."
)

DATABASE_SAVE_ERROR = (
    "❌ Не вдалося зберегти зміни."
)

DATABASE_NOT_FOUND = (
    "❌ Запис у базі даних не знайдено."
)


# =========================================================
# ACCESS
# =========================================================


ACCESS_DENIED = (
    "⛔ У вас немає доступу до цієї дії."
)

ROLE_ACCESS_DENIED = (
    "⛔ Ваша роль не має доступу до цього розділу."
)

STORE_ACCESS_DENIED = (
    "⛔ У вас немає доступу до цієї торгової точки."
)

BUSH_ACCESS_DENIED = (
    "⛔ У вас немає доступу до цього куща."
)

ADMIN_ACCESS_DENIED = (
    "⛔ Ця дія доступна лише адміністраторам."
)

ROOT_ADMIN_ACCESS_DENIED = (
    "⛔ Ця дія доступна лише ROOT_ADMIN."
)


# =========================================================
# USER
# =========================================================


USER_NOT_FOUND = (
    "❌ Користувача не знайдено."
)

USER_INACTIVE = (
    "⚫ Обліковий запис користувача неактивний."
)

USER_BLOCKED = (
    "⛔ Обліковий запис користувача заблокований."
)

USER_NOT_REGISTERED = (
    "📝 Користувач ще не завершив реєстрацію."
)

USER_ALREADY_EXISTS = (
    "⚠️ Такий користувач уже існує."
)


# =========================================================
# STORE
# =========================================================


STORE_NOT_FOUND = (
    "❌ Торгову точку не знайдено."
)

STORE_INACTIVE = (
    "⚫ Торгова точка неактивна."
)

STORE_ALREADY_EXISTS = (
    "⚠️ Така торгова точка вже існує."
)

STORE_HAS_NO_CLUSTER = (
    "⚠️ Для цієї ТТ не призначено кластер."
)

STORE_HAS_NO_SCHEDULE = (
    "⚠️ Для цієї ТТ не налаштовано графік."
)


# =========================================================
# BUSH
# =========================================================


BUSH_NOT_FOUND = (
    "❌ Кущ не знайдено."
)

BUSH_INACTIVE = (
    "⚫ Кущ неактивний."
)

BUSH_ALREADY_EXISTS = (
    "⚠️ Такий кущ уже існує."
)


# =========================================================
# CLUSTER
# =========================================================


CLUSTER_NOT_FOUND = (
    "❌ Кластер не знайдено."
)

CLUSTER_INACTIVE = (
    "⚫ Кластер неактивний."
)


# =========================================================
# INVITE
# =========================================================


INVITE_NOT_FOUND = (
    "❌ Запрошення не знайдено."
)

INVITE_INVALID = (
    "❌ Некоректне запрошення."
)

INVITE_EXPIRED = (
    "⌛ Термін дії цього запрошення завершився."
)

INVITE_REVOKED = (
    "🚫 Це запрошення було відкликано."
)

INVITE_ALREADY_USED = (
    "⚠️ Це запрошення вже використано."
)

INVITE_USAGE_LIMIT_REACHED = (
    "⚠️ Ліміт використань цього запрошення вичерпано."
)

INVITE_ACTIVATION_FAILED = (
    "❌ Не вдалося активувати запрошення."
)


# =========================================================
# OPENING
# =========================================================


OPENING_NOT_AVAILABLE = (
    "⚠️ Підтвердження відкриття зараз недоступне."
)

OPENING_ALREADY_CONFIRMED = (
    "⚠️ Відкриття цієї ТТ уже підтверджено."
)

OPENING_SAVE_ERROR = (
    "❌ Не вдалося зберегти відкриття ТТ."
)

OPENING_RECORD_NOT_FOUND = (
    "❌ Запис про відкриття не знайдено."
)


# =========================================================
# CLOSING
# =========================================================


CLOSING_NOT_AVAILABLE = (
    "⚠️ Подання звіту про закриття зараз недоступне."
)

CLOSING_ALREADY_CONFIRMED = (
    "⚠️ Звіт про закриття вже подано."
)

CLOSING_SAVE_ERROR = (
    "❌ Не вдалося зберегти звіт про закриття."
)

CLOSING_RECORD_NOT_FOUND = (
    "❌ Запис про закриття не знайдено."
)


# =========================================================
# REPORTS
# =========================================================


REPORT_NOT_FOUND = (
    "📭 За вибраний період даних немає."
)

REPORT_BUILD_ERROR = (
    "❌ Не вдалося сформувати звіт."
)

REPORT_EXPORT_ERROR = (
    "❌ Не вдалося створити файл звіту."
)

REPORT_SEND_ERROR = (
    "❌ Не вдалося відправити звіт."
)


# =========================================================
# INPUT
# =========================================================


INVALID_INPUT = (
    "❌ Некоректні дані."
)

INVALID_NUMBER = (
    "❌ Введіть коректне число."
)

INVALID_INTEGER = (
    "❌ Введіть ціле число."
)

INVALID_DATE = (
    "❌ Некоректна дата."
)

INVALID_TIME = (
    "❌ Некоректний час."
)

INVALID_DATETIME = (
    "❌ Некоректна дата або час."
)

INVALID_PHONE = (
    "❌ Некоректний номер телефону."
)

INVALID_FILE = (
    "❌ Некоректний файл."
)

INVALID_IMAGE = (
    "❌ Надішліть коректне зображення."
)


# =========================================================
# TELEGRAM
# =========================================================


TELEGRAM_SEND_ERROR = (
    "❌ Не вдалося відправити повідомлення в Telegram."
)

TELEGRAM_EDIT_ERROR = (
    "❌ Не вдалося оновити повідомлення."
)

TELEGRAM_MESSAGE_NOT_FOUND = (
    "⚠️ Повідомлення більше недоступне."
)

CALLBACK_EXPIRED = (
    "⚠️ Ця кнопка вже неактуальна.\n\n"
    "Оновіть меню."
)


# =========================================================
# FILES / IMPORT
# =========================================================


FILE_TOO_LARGE = (
    "❌ Файл занадто великий."
)

FILE_FORMAT_NOT_SUPPORTED = (
    "❌ Формат файлу не підтримується."
)

IMPORT_ERROR = (
    "❌ Сталася помилка під час імпорту."
)

IMPORT_VALIDATION_ERROR = (
    "❌ У файлі знайдено помилки."
)


# =========================================================
# SCHEDULER
# =========================================================


SCHEDULER_ERROR = (
    "❌ Помилка фонового планувальника."
)

JOB_EXECUTION_ERROR = (
    "❌ Не вдалося виконати фонове завдання."
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "UNKNOWN_ERROR",
    "INTERNAL_ERROR",
    "TEMPORARY_ERROR",
    "OPERATION_FAILED",

    "DATABASE_ERROR",
    "DATABASE_CONNECTION_ERROR",
    "DATABASE_SAVE_ERROR",
    "DATABASE_NOT_FOUND",

    "ACCESS_DENIED",
    "ROLE_ACCESS_DENIED",
    "STORE_ACCESS_DENIED",
    "BUSH_ACCESS_DENIED",
    "ADMIN_ACCESS_DENIED",
    "ROOT_ADMIN_ACCESS_DENIED",

    "USER_NOT_FOUND",
    "USER_INACTIVE",
    "USER_BLOCKED",
    "USER_NOT_REGISTERED",
    "USER_ALREADY_EXISTS",

    "STORE_NOT_FOUND",
    "STORE_INACTIVE",
    "STORE_ALREADY_EXISTS",
    "STORE_HAS_NO_CLUSTER",
    "STORE_HAS_NO_SCHEDULE",

    "BUSH_NOT_FOUND",
    "BUSH_INACTIVE",
    "BUSH_ALREADY_EXISTS",

    "CLUSTER_NOT_FOUND",
    "CLUSTER_INACTIVE",

    "INVITE_NOT_FOUND",
    "INVITE_INVALID",
    "INVITE_EXPIRED",
    "INVITE_REVOKED",
    "INVITE_ALREADY_USED",
    "INVITE_USAGE_LIMIT_REACHED",
    "INVITE_ACTIVATION_FAILED",

    "OPENING_NOT_AVAILABLE",
    "OPENING_ALREADY_CONFIRMED",
    "OPENING_SAVE_ERROR",
    "OPENING_RECORD_NOT_FOUND",

    "CLOSING_NOT_AVAILABLE",
    "CLOSING_ALREADY_CONFIRMED",
    "CLOSING_SAVE_ERROR",
    "CLOSING_RECORD_NOT_FOUND",

    "REPORT_NOT_FOUND",
    "REPORT_BUILD_ERROR",
    "REPORT_EXPORT_ERROR",
    "REPORT_SEND_ERROR",

    "INVALID_INPUT",
    "INVALID_NUMBER",
    "INVALID_INTEGER",
    "INVALID_DATE",
    "INVALID_TIME",
    "INVALID_DATETIME",
    "INVALID_PHONE",
    "INVALID_FILE",
    "INVALID_IMAGE",

    "TELEGRAM_SEND_ERROR",
    "TELEGRAM_EDIT_ERROR",
    "TELEGRAM_MESSAGE_NOT_FOUND",
    "CALLBACK_EXPIRED",

    "FILE_TOO_LARGE",
    "FILE_FORMAT_NOT_SUPPORTED",
    "IMPORT_ERROR",
    "IMPORT_VALIDATION_ERROR",

    "SCHEDULER_ERROR",
    "JOB_EXECUTION_ERROR",
]