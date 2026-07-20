from contextlib import asynccontextmanager

from fastapi import FastAPI

from bot.webhook import router as bot_router
from leaderboard.api import router as leaderboard_router
from db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Stock Trading Idea Bot", lifespan=lifespan)

app.include_router(bot_router, prefix="/bot")
app.include_router(leaderboard_router, prefix="/leaderboard")


@app.get("/health")
async def health():
    return {"status": "ok"}
