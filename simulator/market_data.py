"""
Market-data provider wrapper.

All callers use get_latest_price() and fetch_daily_closes().
Swapping yfinance for another provider only requires changing this file.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict
from zoneinfo import ZoneInfo

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.database import AsyncSessionLocal
from db.models import PriceTick

_NY_TZ = ZoneInfo("America/New_York")
_KL_TZ = ZoneInfo("Asia/Kuala_Lumpur")


def is_market_open() -> bool:
    """True Mon–Fri 9:30–16:00 America/New_York (US markets). Ignores US market holidays."""
    now = datetime.now(_NY_TZ)
    if now.weekday() >= 5:  # Sat=5, Sun=6
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def is_bursa_open() -> bool:
    """
    True Mon–Fri during Bursa Malaysia's two trading sessions — 9:00–12:30
    and 14:30–17:00 Asia/Kuala_Lumpur — excluding the midday lunch break.
    Ignores Malaysian market holidays.
    """
    now = datetime.now(_KL_TZ)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    morning = 9 * 60 <= minutes < 12 * 60 + 30
    afternoon = 14 * 60 + 30 <= minutes < 17 * 60
    return morning or afternoon


def is_ticker_market_open(ticker: str) -> bool:
    """
    Dispatches to the right exchange's trading hours based on the ticker's
    suffix. Bursa Malaysia (.KL) and US markets trade in non-overlapping
    windows (Malaysia is UTC+8, opposite side of the clock from US Eastern),
    so a single global "is the market open" check would either miss Bursa's
    entire session or misreport it as open during US hours when Bursa is
    actually closed. Everything else defaults to US hours.
    """
    if ticker.upper().endswith(".KL"):
        return is_bursa_open()
    return is_market_open()


_BARE_DIGITS_RE = re.compile(r"^\d{1,6}$")


def _yf_has_data(ticker: str) -> bool:
    """Synchronous yfinance check — intended to run in an executor."""
    try:
        return not yf.Ticker(ticker).history(period="2d").empty
    except Exception:
        return False


def _yf_search(query: str) -> list[dict]:
    """Synchronous yfinance text search — intended to run in an executor."""
    try:
        return yf.Search(query, max_results=8).quotes or []
    except Exception:
        return []


async def resolve_ticker(
    candidate: str,
    company_name: str | None = None,
) -> str | None:
    """
    Try to find a valid yfinance symbol for the given candidate.

    Resolution order:
      1. yfinance Search by company_name — most accurate; avoids the LLM
         hallucinating a plausible-looking but wrong exchange code (e.g. 0138.KL
         instead of 5286.KL for MI Technovation).  Skipped when company_name is None.
      2. candidate as-is — handles exact US tickers (AAPL, TSLA) and cases where
         the LLM already returned the correct suffixed symbol (1155.KL).
      3. candidate + ".KL" — bare 4-digit Bursa codes (e.g. "0272" → "0272.KL").
      4. yfinance Search by candidate — last resort (e.g. "SCGB" → 0225.KL).

    Returns the resolved symbol string, or None if nothing works.
    """
    loop = asyncio.get_event_loop()

    # 1. Company-name search first — ground truth beats the LLM's ticker guess
    if company_name:
        quotes = await loop.run_in_executor(None, _yf_search, company_name)
        for q in quotes:
            sym = q.get("symbol", "")
            if sym and await loop.run_in_executor(None, _yf_has_data, sym):
                return sym

    # 2. Candidate as-is
    if await loop.run_in_executor(None, _yf_has_data, candidate):
        return candidate

    # 3. Bare digit code → try appending .KL (Bursa Malaysia)
    if _BARE_DIGITS_RE.match(candidate):
        kl = candidate + ".KL"
        if await loop.run_in_executor(None, _yf_has_data, kl):
            return kl

    # 4. Search by the raw candidate string
    quotes = await loop.run_in_executor(None, _yf_search, candidate)
    for q in quotes:
        sym = q.get("symbol", "")
        if sym and await loop.run_in_executor(None, _yf_has_data, sym):
            return sym

    return None


async def get_latest_price(ticker: str) -> Decimal:
    """
    Return the most recent available close price for ticker.
    Checks the price_ticks DB cache for today first; falls back to yfinance.
    """
    today = datetime.now(timezone.utc).date()

    async with AsyncSessionLocal() as session:
        cached = await session.get(PriceTick, (ticker, today))
        if cached is not None:
            return cached.price

    hist = yf.Ticker(ticker).history(period="5d")
    if hist.empty:
        raise ValueError(f"yfinance returned no data for {ticker!r}")
    price = Decimal(str(float(hist["Close"].iloc[-1]))).quantize(Decimal("0.0001"))

    async with AsyncSessionLocal() as session:
        stmt = (
            pg_insert(PriceTick)
            .values(ticker=ticker, date=today, price=price)
            .on_conflict_do_nothing()
        )
        await session.execute(stmt)
        await session.commit()

    return price


def _fetch_intraday_price_sync(ticker: str) -> Decimal:
    """Synchronous live-price fetch — intended to run in an executor."""
    last = yf.Ticker(ticker).fast_info.get("last_price")
    if last is None:
        hist = yf.Ticker(ticker).history(period="1d", interval="1m")
        if hist.empty:
            raise ValueError(f"yfinance returned no intraday data for {ticker!r}")
        last = float(hist["Close"].iloc[-1])
    return Decimal(str(last)).quantize(Decimal("0.0001"))


async def get_intraday_price(ticker: str) -> Decimal:
    """
    Fetch ticker's current live price directly from yfinance, bypassing the
    once-per-day PriceTick cache used by get_latest_price(). Used by the
    intraday snapshot job, which needs a fresh read on every tick rather than
    the first price seen that day.

    Refreshes today's price_ticks row as a side effect, so other callers of
    get_latest_price() benefit from the freshest price too.
    """
    loop = asyncio.get_event_loop()
    price = await loop.run_in_executor(None, _fetch_intraday_price_sync, ticker)

    today = datetime.now(timezone.utc).date()
    async with AsyncSessionLocal() as session:
        stmt = (
            pg_insert(PriceTick)
            .values(ticker=ticker, date=today, price=price)
            .on_conflict_do_update(
                index_elements=["ticker", "date"],
                set_={"price": price},
            )
        )
        await session.execute(stmt)
        await session.commit()

    return price


async def fetch_daily_closes(ticker: str, start: date, end: date) -> Dict[date, Decimal]:
    """
    Return {date: close_price} for every trading day in [start, end] inclusive.
    Reads from DB cache and fills any gaps via yfinance, then writes new rows back.
    """
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(PriceTick).where(
                    PriceTick.ticker == ticker,
                    PriceTick.date >= start,
                    PriceTick.date <= end,
                )
            )
        ).scalars().all()
    cached: Dict[date, Decimal] = {r.date: r.price for r in rows}

    # Always re-fetch from yfinance to fill any missing trading days.
    hist = yf.Ticker(ticker).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),  # yfinance end is exclusive
    )
    fetched: Dict[date, Decimal] = {}
    for ts, row in hist.iterrows():
        d = ts.date()
        if d not in cached:
            fetched[d] = Decimal(str(float(row["Close"]))).quantize(Decimal("0.0001"))

    if fetched:
        async with AsyncSessionLocal() as session:
            for d, price in fetched.items():
                stmt = (
                    pg_insert(PriceTick)
                    .values(ticker=ticker, date=d, price=price)
                    .on_conflict_do_update(
                        index_elements=["ticker", "date"],
                        set_={"price": price},
                    )
                )
                await session.execute(stmt)
            await session.commit()
        cached.update(fetched)

    return {d: cached[d] for d in sorted(cached) if start <= d <= end}
