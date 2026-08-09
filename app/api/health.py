from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.database.session import (
    check_database_connection,
)


router = APIRouter(
    prefix="/health",
    tags=["health"],
)


@router.get("")
async def health_check() -> JSONResponse:
    """
    Загальна перевірка стану застосунку.

    Перевіряє:
    - чи запущений FastAPI;
    - чи доступна PostgreSQL.
    """

    checked_at = datetime.now(
        UTC
    )

    database_ok = False
    database_error: str | None = None

    try:
        database_ok = bool(
            await check_database_connection()
        )

    except Exception as error:
        database_ok = False
        database_error = (
            type(error).__name__
        )

    healthy = database_ok

    payload: dict[str, Any] = {
        "status": (
            "healthy"
            if healthy
            else "unhealthy"
        ),
        "app": settings.app_name,
        "environment": settings.app_env,
        "database": (
            "ok"
            if database_ok
            else "error"
        ),
        "checked_at": (
            checked_at.isoformat()
        ),
    }

    if database_error is not None:
        payload[
            "database_error"
        ] = database_error

    return JSONResponse(
        status_code=(
            200
            if healthy
            else 503
        ),
        content=payload,
    )


@router.get(
    "/live"
)
async def liveness_check() -> dict[str, str]:
    """
    Liveness probe.

    Не перевіряє PostgreSQL.
    Показує лише, що сам web process працює.
    """

    return {
        "status": "alive",
        "app": settings.app_name,
    }


@router.get(
    "/ready"
)
async def readiness_check() -> JSONResponse:
    """
    Readiness probe.

    Готовність застосунку до роботи
    визначається доступністю PostgreSQL.
    """

    try:
        database_ok = bool(
            await check_database_connection()
        )

    except Exception:
        database_ok = False

    return JSONResponse(
        status_code=(
            200
            if database_ok
            else 503
        ),
        content={
            "status": (
                "ready"
                if database_ok
                else "not_ready"
            ),
            "database": (
                "ok"
                if database_ok
                else "error"
            ),
        },
    )


__all__ = [
    "router",
]