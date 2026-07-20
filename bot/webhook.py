import logging

from fastapi import APIRouter, Request, Response
from telegram import Update

from bot.application import application
from db.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """Receive a Telegram Update, deserialise it, and hand it to PTB for dispatch."""
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return Response(status_code=200)


@router.post("/set-webhook")
async def set_webhook() -> dict:
    """
    Register this app's public URL with Telegram as the webhook endpoint.
    Call once after deployment: POST /bot/set-webhook
    Requires WEBHOOK_URL to be set in the environment.
    """
    if not settings.WEBHOOK_URL:
        return {"status": "error", "detail": "WEBHOOK_URL is not set in the environment"}

    webhook_url = f"{settings.WEBHOOK_URL}/bot/webhook"
    await application.bot.set_webhook(
        url=webhook_url,
        allowed_updates=["message"],
    )
    info = await application.bot.get_webhook_info()
    logger.info("Webhook registered: %s (pending=%d)", webhook_url, info.pending_update_count)
    return {
        "status": "ok",
        "webhook_url": webhook_url,
        "pending_updates": info.pending_update_count,
    }
