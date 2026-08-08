from __future__ import annotations

from enum import StrEnum

from aiogram.filters.callback_data import (
    CallbackData,
)


# =========================================================
# COMMON ACTIONS
# =========================================================


class CommonAction(StrEnum):
    """
    Загальні дії.
    """

    OPEN = "o"
    VIEW = "v"
    BACK = "b"
    CANCEL = "c"

    CONFIRM = "ok"
    REFRESH = "r"

    CREATE = "new"
    EDIT = "e"

    DELETE = "del"

    ACTIVATE = "on"
    DEACTIVATE = "off"

    NEXT = "n"
    PREVIOUS = "p"

    SELECT = "s"


# =========================================================
# MAIN MENU
# =========================================================


class MainMenuAction(StrEnum):
    """
    Головне меню.
    """

    HOME = "home"

    OPENING = "open"
    CLOSING = "close"

    REPORTS = "rep"

    STORES = "stores"
    USERS = "users"

    BUSHES = "bush"
    CLUSTERS = "cluster"

    SETTINGS = "set"
    ADMIN = "admin"

    PROFILE = "me"

    HELP = "help"


class MainMenuCallback(
    CallbackData,
    prefix="m",
):
    """
    m:<action>
    """

    action: MainMenuAction


# =========================================================
# PAGINATION
# =========================================================


class PaginationCallback(
    CallbackData,
    prefix="pg",
):
    """
    Універсальна пагінація.

    section:
        короткий код розділу.

    page:
        номер сторінки.

    ref:
        додатковий ID.
        0 = відсутній.
    """

    section: str
    page: int
    ref: int = 0


# =========================================================
# OPENING
# =========================================================


class OpeningAction(StrEnum):
    """
    Ранкове відкриття.
    """

    MENU = "m"

    SELECT_STORE = "s"

    PREPARE = "p"
    CONFIRM = "ok"

    STATUS = "st"

    LATE = "late"

    REFRESH = "r"

    MANUAL = "man"

    BACK = "b"


class OpeningCallback(
    CallbackData,
    prefix="op",
):
    """
    op:<action>:<store_id>

    store_id=0:
        ТТ ще не вибрана.
    """

    action: OpeningAction
    store_id: int = 0


# =========================================================
# CLOSING
# =========================================================


class ClosingAction(StrEnum):
    """
    Закриття ТТ.
    """

    MENU = "m"

    SELECT_STORE = "s"

    PREPARE = "p"

    CASH = "cash"

    RECEIPT = "rec"

    CONFIRM = "ok"

    STATUS = "st"

    REFRESH = "r"

    MANUAL = "man"

    BACK = "b"


class ClosingCallback(
    CallbackData,
    prefix="cl",
):
    """
    cl:<action>:<store_id>
    """

    action: ClosingAction
    store_id: int = 0


# =========================================================
# CASH
# =========================================================


class CashAction(StrEnum):
    """
    Каса.
    """

    VIEW = "v"

    ENTER = "in"

    CORRECT = "e"

    CONFIRM = "ok"

    CANCEL = "c"

    REPORT = "rep"

    BACK = "b"


class CashCallback(
    CallbackData,
    prefix="ca",
):
    """
    ca:<action>:<store_id>:<report_id>
    """

    action: CashAction

    store_id: int = 0
    report_id: int = 0


# =========================================================
# STORES
# =========================================================


class StoreAction(StrEnum):
    """
    Управління ТТ.
    """

    LIST = "ls"

    VIEW = "v"

    SEARCH = "q"

    CREATE = "new"

    EDIT = "e"

    BUSH = "bu"

    CLUSTER = "cl"

    ACTIVATE = "on"

    DEACTIVATE = "off"

    USERS = "usr"

    SCHEDULE = "sch"

    REPORT = "rep"

    BACK = "b"


class StoreCallback(
    CallbackData,
    prefix="st",
):
    """
    st:<action>:<store_id>:<page>
    """

    action: StoreAction

    store_id: int = 0
    page: int = 0


# =========================================================
# STORE SELECTION
# =========================================================


class StoreSelectAction(StrEnum):
    """
    Вибір ТТ для іншої операції.
    """

    SELECT = "s"
    PAGE = "p"
    CANCEL = "c"


class StoreSelectCallback(
    CallbackData,
    prefix="ss",
):
    """
    context:
        op
        cl
        usr
        bush
        cluster
        report
        etc.
    """

    action: StoreSelectAction

    context: str

    store_id: int = 0
    page: int = 0


# =========================================================
# BUSHES
# =========================================================


class BushAction(StrEnum):
    """
    Управління кущами.
    """

    LIST = "ls"

    VIEW = "v"

    CREATE = "new"

    EDIT = "e"

    STORES = "st"

    USERS = "usr"

    STATS = "stat"

    ACTIVATE = "on"

    DEACTIVATE = "off"

    MOVE_STORE = "mv"

    BACK = "b"


class BushCallback(
    CallbackData,
    prefix="bu",
):
    """
    bu:<action>:<bush_id>:<page>
    """

    action: BushAction

    bush_id: int = 0
    page: int = 0


# =========================================================
# BUSH SELECTION
# =========================================================


class BushSelectAction(StrEnum):
    """
    Вибір куща.
    """

    SELECT = "s"
    PAGE = "p"
    CANCEL = "c"


class BushSelectCallback(
    CallbackData,
    prefix="bs",
):
    """
    context:
        store
        user
        report
        etc.
    """

    action: BushSelectAction

    context: str

    bush_id: int = 0
    page: int = 0


# =========================================================
# CLUSTERS
# =========================================================


class ClusterAction(StrEnum):
    """
    Управління кластерами.
    """

    LIST = "ls"

    VIEW = "v"

    CREATE = "new"

    EDIT = "e"

    STORES = "st"

    ASSIGN = "as"

    ACTIVATE = "on"

    DEACTIVATE = "off"

    DEFAULTS = "def"

    BACK = "b"


class ClusterCallback(
    CallbackData,
    prefix="ct",
):
    """
    ct:<action>:<cluster_id>:<page>
    """

    action: ClusterAction

    cluster_id: int = 0
    page: int = 0


# =========================================================
# CLUSTER SELECTION
# =========================================================


class ClusterSelectAction(StrEnum):
    """
    Вибір кластера.
    """

    SELECT = "s"

    NONE = "none"

    PAGE = "p"

    CANCEL = "c"


class ClusterSelectCallback(
    CallbackData,
    prefix="cs",
):
    """
    context:
        store
        import
        etc.
    """

    action: ClusterSelectAction

    context: str

    cluster_id: int = 0
    page: int = 0


# =========================================================
# USERS
# =========================================================


class UserAction(StrEnum):
    """
    Управління користувачами.
    """

    LIST = "ls"

    VIEW = "v"

    SEARCH = "q"

    PENDING = "pend"

    BLOCKED = "block"

    APPROVE = "ok"

    REJECT = "rej"

    BLOCK = "ban"

    UNBLOCK = "unban"

    ACTIVATE = "on"

    DEACTIVATE = "off"

    ROLE = "role"

    STORE = "st"

    BUSH = "bu"

    BINDINGS = "bind"

    BACK = "b"


class UserCallback(
    CallbackData,
    prefix="u",
):
    """
    u:<action>:<user_id>:<page>
    """

    action: UserAction

    user_id: int = 0
    page: int = 0


# =========================================================
# USER ROLE
# =========================================================


class UserRoleAction(StrEnum):
    """
    Вибір ролі.
    """

    ROOT = "root"

    DIRECTOR = "dir"

    BUSH_ADMIN = "ba"

    LION = "lion"

    STORE_USER = "store"

    CANCEL = "c"


class UserRoleCallback(
    CallbackData,
    prefix="ur",
):
    """
    ur:<action>:<user_id>
    """

    action: UserRoleAction

    user_id: int


# =========================================================
# BINDINGS
# =========================================================


class BindingAction(StrEnum):
    """
    Прив’язки користувачів.
    """

    VIEW = "v"

    ADD_STORE = "ast"

    ADD_BUSH = "abu"

    PRIMARY = "pri"

    REMOVE = "del"

    TRANSFER_STORE = "tst"

    TRANSFER_BUSH = "tbu"

    BACK = "b"


class BindingCallback(
    CallbackData,
    prefix="bd",
):
    """
    target_id:
        store_id або bush_id.

    binding_id:
        ID прив’язки.
    """

    action: BindingAction

    user_id: int

    target_id: int = 0

    binding_id: int = 0


# =========================================================
# REPORTS
# =========================================================


class ReportAction(StrEnum):
    """
    Звіти.
    """

    MENU = "m"

    DAILY = "d"

    WEEKLY = "w"

    MONTHLY = "mon"

    CUSTOM = "custom"

    STORE = "st"

    BUSH = "bu"

    NETWORK = "net"

    EXCEL = "xls"

    REFRESH = "r"

    BACK = "b"


class ReportCallback(
    CallbackData,
    prefix="rp",
):
    """
    ref_id:
        store_id або bush_id.

    page:
        пагінація.
    """

    action: ReportAction

    ref_id: int = 0

    page: int = 0


# =========================================================
# REPORT DATE
# =========================================================


class ReportDateAction(StrEnum):
    """
    Вибір періоду.
    """

    TODAY = "today"

    YESTERDAY = "yday"

    THIS_WEEK = "week"

    LAST_WEEK = "lweek"

    THIS_MONTH = "month"

    LAST_MONTH = "lmonth"

    CUSTOM = "custom"

    CANCEL = "c"


class ReportDateCallback(
    CallbackData,
    prefix="rd",
):
    """
    scope:
        net
        bush
        store

    ref_id:
        store_id / bush_id / 0
    """

    action: ReportDateAction

    scope: str

    ref_id: int = 0


# =========================================================
# SCHEDULE
# =========================================================


class ScheduleAction(StrEnum):
    """
    Графік ТТ.
    """

    VIEW = "v"

    WEEKDAY = "wd"

    COPY = "copy"

    EXCEPTION = "ex"

    DELETE_EXCEPTION = "dex"

    PREVIEW = "pre"

    CLUSTER = "cl"

    BACK = "b"


class ScheduleCallback(
    CallbackData,
    prefix="sc",
):
    """
    value:
        weekday / exception_id / etc.
    """

    action: ScheduleAction

    store_id: int

    value: int = 0


# =========================================================
# IMPORT
# =========================================================


class ImportAction(StrEnum):
    """
    Імпорт ТТ.
    """

    MENU = "m"

    UPLOAD = "up"

    PREVIEW = "pre"

    APPLY = "ok"

    APPLY_PARTIAL = "part"

    CANCEL = "c"

    BACK = "b"


class ImportCallback(
    CallbackData,
    prefix="im",
):
    """
    token:
        короткий ID імпорт-сесії.
        0 = поточна FSM-сесія.
    """

    action: ImportAction

    token: int = 0


# =========================================================
# SETTINGS
# =========================================================


class SettingsAction(StrEnum):
    """
    Налаштування.
    """

    MENU = "m"

    BOT = "bot"

    MAINTENANCE = "maint"

    TIMEZONE = "tz"

    OPENING = "op"

    CLOSING = "cl"

    REPORTS = "rep"

    GROUPS = "grp"

    NOTIFICATIONS = "ntf"

    RESET = "reset"

    BACK = "b"


class SettingsCallback(
    CallbackData,
    prefix="se",
):
    """
    se:<action>
    """

    action: SettingsAction


# =========================================================
# TELEGRAM GROUPS
# =========================================================


class GroupAction(StrEnum):
    """
    Налаштування Telegram-груп.
    """

    MENU = "m"

    NETWORK = "net"

    BUSH = "bu"

    REGISTER = "reg"

    VERIFY = "ver"

    TEST = "test"

    OPENING_TOPIC = "op"

    CLOSING_TOPIC = "cl"

    ALERTS_TOPIC = "al"

    SUMMARIES_TOPIC = "sum"

    CLEAR = "del"

    BACK = "b"


class GroupCallback(
    CallbackData,
    prefix="gr",
):
    """
    bush_id=0:
        network.
    """

    action: GroupAction

    bush_id: int = 0


# =========================================================
# INVITES
# =========================================================


class InviteAction(StrEnum):
    """
    Запрошення.
    """

    MENU = "m"

    STORE = "st"

    BUSH = "bu"

    DIRECTOR = "dir"

    LIST = "ls"

    CREATE = "new"

    REVOKE = "del"

    BACK = "b"


class InviteCallback(
    CallbackData,
    prefix="iv",
):
    """
    target_id:
        store_id або bush_id.

    invite_id:
        ID запрошення.
    """

    action: InviteAction

    target_id: int = 0

    invite_id: int = 0


# =========================================================
# AUDIT
# =========================================================


class AuditActionCallback(StrEnum):
    """
    AuditLog UI.
    """

    LIST = "ls"

    VIEW = "v"

    USER = "usr"

    STORE = "st"

    BUSH = "bu"

    EXPORT = "xls"

    STATS = "stat"

    BACK = "b"


class AuditCallback(
    CallbackData,
    prefix="au",
):
    """
    ref_id:
        entity/user/store/bush ID.
    """

    action: AuditActionCallback

    ref_id: int = 0

    page: int = 0


# =========================================================
# ADMIN MENU
# =========================================================


class AdminAction(StrEnum):
    """
    Центральна адмінка.
    """

    MENU = "m"

    USERS = "usr"

    STORES = "st"

    BUSHES = "bu"

    CLUSTERS = "ct"

    REPORTS = "rep"

    IMPORT = "im"

    SETTINGS = "set"

    INVITES = "iv"

    AUDIT = "au"

    GROUPS = "gr"

    BACK = "b"


class AdminCallback(
    CallbackData,
    prefix="ad",
):
    """
    ad:<action>
    """

    action: AdminAction


# =========================================================
# CONFIRMATION
# =========================================================


class ConfirmAction(StrEnum):
    """
    Універсальне підтвердження.
    """

    YES = "y"
    NO = "n"


class ConfirmCallback(
    CallbackData,
    prefix="cf",
):
    """
    context:
        короткий тип операції.

    entity_id:
        ID об’єкта.

    extra:
        додатковий ID/параметр.
    """

    action: ConfirmAction

    context: str

    entity_id: int = 0

    extra: int = 0


# =========================================================
# REFRESH
# =========================================================


class RefreshCallback(
    CallbackData,
    prefix="rf",
):
    """
    Універсальний refresh.

    section:
        opening
        closing
        report
        users
        etc.

    ref_id:
        ID сутності.
    """

    section: str

    ref_id: int = 0


# =========================================================
# HELPERS
# =========================================================


def callback_length(
    callback_data: str,
) -> int:
    """
    Повертає довжину callback_data
    у байтах UTF-8.

    Telegram дозволяє максимум 64 bytes.
    """

    return len(
        callback_data.encode(
            "utf-8"
        )
    )


def ensure_callback_size(
    callback_data: str,
    *,
    max_bytes: int = 64,
) -> str:
    """
    Перевіряє Telegram callback_data limit.
    """

    size = callback_length(
        callback_data
    )

    if size > max_bytes:
        raise ValueError(
            "callback_data перевищує "
            f"Telegram limit: "
            f"{size}/{max_bytes} bytes."
        )

    return callback_data


def pack_checked(
    callback: CallbackData,
) -> str:
    """
    Пакує CallbackData
    і перевіряє 64-byte limit.

    Приклад:

        data = pack_checked(
            StoreCallback(
                action=StoreAction.VIEW,
                store_id=31,
            )
        )
    """

    packed = callback.pack()

    return ensure_callback_size(
        packed
    )


__all__ = [
    # COMMON
    "CommonAction",

    # MAIN MENU
    "MainMenuAction",
    "MainMenuCallback",

    # PAGINATION
    "PaginationCallback",

    # OPENING
    "OpeningAction",
    "OpeningCallback",

    # CLOSING
    "ClosingAction",
    "ClosingCallback",

    # CASH
    "CashAction",
    "CashCallback",

    # STORES
    "StoreAction",
    "StoreCallback",
    "StoreSelectAction",
    "StoreSelectCallback",

    # BUSHES
    "BushAction",
    "BushCallback",
    "BushSelectAction",
    "BushSelectCallback",

    # CLUSTERS
    "ClusterAction",
    "ClusterCallback",
    "ClusterSelectAction",
    "ClusterSelectCallback",

    # USERS
    "UserAction",
    "UserCallback",
    "UserRoleAction",
    "UserRoleCallback",

    # BINDINGS
    "BindingAction",
    "BindingCallback",

    # REPORTS
    "ReportAction",
    "ReportCallback",
    "ReportDateAction",
    "ReportDateCallback",

    # SCHEDULE
    "ScheduleAction",
    "ScheduleCallback",

    # IMPORT
    "ImportAction",
    "ImportCallback",

    # SETTINGS
    "SettingsAction",
    "SettingsCallback",

    # GROUPS
    "GroupAction",
    "GroupCallback",

    # INVITES
    "InviteAction",
    "InviteCallback",

    # AUDIT
    "AuditActionCallback",
    "AuditCallback",

    # ADMIN
    "AdminAction",
    "AdminCallback",

    # CONFIRM
    "ConfirmAction",
    "ConfirmCallback",

    # REFRESH
    "RefreshCallback",

    # HELPERS
    "callback_length",
    "ensure_callback_size",
    "pack_checked",
]