from __future__ import annotations

from aiogram import Router

from app.handlers.bindings import (
    router as bindings_router,
)
from app.handlers.bush_admin import (
    router as bush_admin_router,
)
from app.handlers.closing import (
    router as closing_router,
)
from app.handlers.common import (
    router as common_router,
)
from app.handlers.director import (
    router as director_router,
)
from app.handlers.errors import (
    global_error_handler,
)
from app.handlers.group_events import (
    router as group_events_router,
)
from app.handlers.invites import (
    router as invites_router,
)
from app.handlers.lion import (
    router as lion_router,
)
from app.handlers.opening import (
    router as opening_router,
)
from app.handlers.registration import (
    router as registration_router,
)
from app.handlers.reports import (
    router as reports_router,
)
from app.handlers.root_admin import (
    router as root_admin_router,
)
from app.handlers.store import (
    router as store_router,
)


# =========================================================
# ROOT HANDLERS ROUTER
# =========================================================


router = Router(
    name="handlers",
)


# =========================================================
# GLOBAL ERROR HANDLER
# =========================================================
#
# Реєструємо error handler саме
# на БАТЬКІВСЬКОМУ router.
#
# Таким чином він ловитиме помилки
# з усіх дочірніх routers.
#
# Окремо errors_router сюди
# не підключаємо, тому що sibling
# router не є батьківським для
# інших handlers.
# =========================================================


router.errors.register(
    global_error_handler
)


# =========================================================
# ROUTER ORDER
# =========================================================
#
# ПОРЯДОК ВАЖЛИВИЙ.
#
# Спочатку:
#   - реєстрація
#   - адмінські специфічні callbacks
#   - reports / invites / bindings
#
# Потім:
#   - role dashboards
#
# Далі:
#   - store
#   - closing
#   - opening
#
# В самому кінці:
#   - group_events
#   - common
#
# common.py має загальні callbacks,
# тому він ОБОВ'ЯЗКОВО останній.
#
# store.py стоїть ПЕРЕД opening.py,
# тому що opening.py має fallback
# для StoreAction.VIEW.
#
# root_admin.py стоїть ПЕРЕД
# group_events.py, тому що обидва
# можуть працювати з GroupCallback.
# =========================================================


router.include_routers(
    # -----------------------------------------------------
    # REGISTRATION
    # -----------------------------------------------------

    registration_router,

    # -----------------------------------------------------
    # ROOT / MANAGEMENT
    # -----------------------------------------------------

    root_admin_router,

    bindings_router,

    invites_router,

    reports_router,

    # -----------------------------------------------------
    # ROLE PANELS
    # -----------------------------------------------------

    director_router,

    bush_admin_router,

    lion_router,

    # -----------------------------------------------------
    # STORE OPERATIONS
    # -----------------------------------------------------

    store_router,

    closing_router,

    opening_router,

    # -----------------------------------------------------
    # TELEGRAM GROUP EVENTS
    # -----------------------------------------------------

    group_events_router,

    # -----------------------------------------------------
    # COMMON MUST BE LAST
    # -----------------------------------------------------

    common_router,
)


# =========================================================
# PUBLIC API
# =========================================================


def get_handlers_router() -> Router:
    """
    Повертає головний router
    усіх Telegram handlers.

    Використання:

        dp.include_router(
            get_handlers_router()
        )
    """

    return router


__all__ = [
    "router",
    "get_handlers_router",
]