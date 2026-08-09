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

router.errors.register(
    global_error_handler
)


# =========================================================
# ROUTER ORDER
# =========================================================
#
# Порядок важливий:
#
# 1. registration
# 2. management / admin
# 3. invites / bindings / reports
# 4. role dashboards
# 5. store operations
# 6. group events
# 7. common fallback
#
# common_router завжди останній.
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


def get_handlers_router() -> Router:
    """
    Повертає головний router
    усіх Telegram handlers.
    """

    return router


__all__ = [
    "router",
    "get_handlers_router",
]