from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/")
async def index() -> FileResponse:
    return FileResponse("leaderboard/static/index.html")


@router.get("/data/leaderboard")
async def leaderboard_data() -> list[dict]:
    """
    Returns ranked list of users with their performance stats.

    Shape: [{ "rank": 1, "username": "...", "pnl": 123.45,
              "win_rate": 0.6, "idea_count": 10 }, ...]

    TODO: query latest DailyEquity row per user, compute win_rate from positions.
    """
    raise NotImplementedError


@router.get("/data/user/{telegram_user_id}")
async def user_data(telegram_user_id: str) -> dict:
    """
    Returns a user's equity curve and individual idea history.

    Shape: {
        "username": "...",
        "equity_curve": [{"date": "2025-01-01", "equity": 1023.50}, ...],
        "ideas": [{"ticker": "AAPL", "direction": "long", "entry": 210.0,
                   "exit": 225.0, "pnl": 71.43, "status": "closed"}, ...]
    }

    TODO: query DailyEquity time series + ideas/positions for the user.
    """
    raise NotImplementedError
