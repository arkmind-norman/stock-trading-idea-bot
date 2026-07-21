import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from bot.application import application
from bot.webhook import router as bot_router
from db.config import settings
from db.database import init_db
from leaderboard.api import router as leaderboard_router
from simulator.daily_job import run_daily_job
from simulator.intraday_job import run_intraday_job

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# Single scheduler instance — must use --workers 1 (set in railway.json).
_scheduler = AsyncIOScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Database ───────────────────────────────────────────────────────────────
    await init_db()

    # ── Daily mark-to-market cron ──────────────────────────────────────────────
    # 4:30 PM America/New_York Mon–Fri — handles DST automatically.
    _scheduler.add_job(
        run_daily_job,
        CronTrigger(hour=16, minute=30, day_of_week="mon-fri", timezone="America/New_York"),
        id="daily_mark_to_market",
        replace_existing=True,
        misfire_grace_time=3600,  # run even if the process was down at trigger time
    )
    # ── Intraday equity snapshots ────────────────────────────────────────────────
    # Every 1 minute while the US market is open; no-op outside market hours.
    _scheduler.add_job(
        run_intraday_job,
        IntervalTrigger(minutes=1),
        id="intraday_equity_snapshot",
        replace_existing=True,
        misfire_grace_time=30,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — daily job fires at 16:30 America/New_York Mon–Fri, "
        "intraday P&L snapshots every 1 minute during market hours"
    )

    # ── Telegram bot ───────────────────────────────────────────────────────────
    await application.initialize()
    await application.start()

    if settings.TELEGRAM_MODE == "polling":
        logger.info("Telegram bot starting in long-polling mode")
        await application.updater.start_polling(allowed_updates=["message"])
        logger.info("Polling started — waiting for group messages")
    elif settings.TELEGRAM_MODE == "webhook" and settings.WEBHOOK_URL:
        webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}/bot/webhook"
        await application.bot.set_webhook(url=webhook_url, allowed_updates=["message"])
        logger.info("Webhook registered: %s", webhook_url)
    else:
        logger.warning(
            "TELEGRAM_MODE=%r but WEBHOOK_URL is not set — bot will not receive updates. "
            "Set WEBHOOK_URL or call POST /bot/set-webhook manually.",
            settings.TELEGRAM_MODE,
        )

    yield

    # ── Graceful shutdown ──────────────────────────────────────────────────────
    _scheduler.shutdown(wait=False)

    if settings.TELEGRAM_MODE == "polling" and application.updater.running:
        await application.updater.stop()
    await application.stop()
    await application.shutdown()
    logger.info("Bot shut down cleanly")


app = FastAPI(title="Stock Trading Idea Bot", lifespan=lifespan)

app.include_router(bot_router, prefix="/bot")
app.include_router(leaderboard_router, prefix="/leaderboard")

# React build output (leaderboard/frontend, built via `npm run build` into
# leaderboard/static/). leaderboard/api.py serves static/index.html directly;
# this just serves the hashed JS/CSS bundle it references.
_LEADERBOARD_ASSETS = os.path.join(os.path.dirname(__file__), "leaderboard", "static", "assets")
app.mount("/leaderboard/assets", StaticFiles(directory=_LEADERBOARD_ASSETS), name="leaderboard-assets")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return RedirectResponse(url="/leaderboard/")
