from datetime import date
from decimal import Decimal


async def get_latest_price(ticker: str) -> Decimal:
    """
    Return the most recent available close price for the ticker.

    Uses the price_ticks cache first; falls back to yfinance if cache is stale.

    TODO:
    - Check price_ticks table for today's date; return cached value if present
    - Otherwise call yfinance: yf.Ticker(ticker).fast_info["lastPrice"]
    - Write result to price_ticks cache
    """
    raise NotImplementedError


async def fetch_daily_closes(ticker: str, start: date, end: date) -> dict[date, Decimal]:
    """
    Return {date: close_price} for the requested range.

    TODO:
    - Pull from price_ticks cache where available
    - Fill gaps using yfinance history download
    - Upsert results into price_ticks
    """
    raise NotImplementedError
