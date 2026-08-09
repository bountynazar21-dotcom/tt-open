from __future__ import annotations

import logging

from aiogram.types import Update
from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)

from app.bot import get_bot_and_dispatcher
from app.config import settings


logger = logging.getLogger(__name__)


router = APIRouter(
    tags=["telegram"],
)


# =========================================================
# HELPERS
# =========================================================


def validate_webhook_secret(
    received_secret: str | None,
) -> None:
    """
    Перевіряє Telegram webhook secret.

    Telegram передає його у header:

        X-Telegram-Bot-Api-Secret-Token

    Якщо WEBHOOK_SECRET не заданий,
    перевірка пропускається.
    """

    expected_secret = (
        settings.webhook_secret
    )

    if not expected_secret:
        return

    if not received_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook secret missing.",
        )

    if received_secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret.",
        )


# =========================================================
# TELEGRAM WEBHOOK
# =========================================================


@router.post(
    settings.webhook_path,
    status_code=status.HTTP_200_OK,
)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        default=None,
        alias="X-Telegram-Bot-Api-Secret-Token",
    ),
) -> Response:
    """
    Приймає Telegram Update через webhook
    та передає його у aiogram Dispatcher.
    """

    if not settings.use_webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook mode disabled.",
        )

    validate_webhook_secret(
        x_telegram_bot_api_secret_token
    )

    try:
        payload = await request.json()

    except Exception as error:
        logger.warning(
            "Invalid Telegram webhook JSON | "
            "error=%s",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from error

    try:
        update = Update.model_validate(
            payload
        )

    except Exception as error:
        logger.warning(
            "Invalid Telegram update payload | "
            "error=%s",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram update.",
        ) from error

    bot, dispatcher = (
        get_bot_and_dispatcher()
    )

    try:
        await dispatcher.feed_update(
            bot,
            update,
        )

    except Exception:
        logger.exception(
            "Telegram webhook update processing failed | "
            "update_id=%s",
            update.update_id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update processing failed.",
        )

    return Response(
        status_code=status.HTTP_200_OK,
    )


# =========================================================
# WEBHOOK INFO
# =========================================================


@router.get(
    f"{settings.webhook_path}/status",
)
async def webhook_status() -> dict[str, object]:
    """
    Простий статус webhook-конфігурації.

    Секретні значення тут не повертаються.
    """

    return {
        "enabled":
            settings.use_webhook,

        "path":
            settings.webhook_path,

        "configured_url":
            bool(
                settings.webhook_url
            ),

        "secret_configured":
            bool(
                settings.webhook_secret
            ),
    }


__all__ = [
    "router",
    "telegram_webhook",
    "webhook_status",
    "validate_webhook_secret",
]