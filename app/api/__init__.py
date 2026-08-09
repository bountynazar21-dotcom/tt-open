from __future__ import annotations

from fastapi import APIRouter

from app.api.health import (
    router as health_router,
)
from app.api.webhook import (
    router as webhook_router,
)


router = APIRouter()


# =========================================================
# API ROUTERS
# =========================================================


router.include_router(
    health_router
)

router.include_router(
    webhook_router
)


# =========================================================
# PUBLIC API
# =========================================================


def get_api_router() -> APIRouter:
    """
    Повертає головний API router.

    Використання:

        app.include_router(
            get_api_router()
        )
    """

    return router


__all__ = [
    "router",
    "get_api_router",
]