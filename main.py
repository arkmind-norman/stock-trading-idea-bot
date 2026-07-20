import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bot.application import application
from bot.webhook import router as bot_router
from db.config import settings
from db.database import init_db
from leaderboard.api import router as leaderboard_router

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    await application.initialize()
    await application.start()

    if settings.TELEGRAM_MODE == "polling":
        logger.info("Telegram bot starting in long-polling mode")
        await application.updater.start_polling(allowed_updates=["message"])
        logger.info("Polling started — waiting for group messages")
    else:
        logger.info("Telegram bot in webhook mode — POST /bot/set-webhook to register")

    yield

    # ── Graceful shutdown ──────────────────────────────────────────────────────
    if settings.TELEGRAM_MODE == "polling" and application.updater.running:
        await application.updater.stop()
    await application.stop()
    await application.shutdown()
    logger.info("Bot shut down cleanly")


app = FastAPI(title="Stock Trading Idea Bot", lifespan=lifespan)

app.include_router(bot_router, prefix="/bot")
app.include_router(leaderboard_router, prefix="/leaderboard")


@app.get("/health")
async def health():
    return {"status": "ok"}
