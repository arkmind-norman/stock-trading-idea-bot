"""
Market-data provider wrapper.

All callers use get_latest_price() and fetch_daily_closes().
Swapping yfinance for another provider only requires changing this file.
"""
from __future__ import annotations

import asyncio
import logging
import math
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

logger = logging.getLogger(__name__)

_NY_TZ = ZoneInfo("America/New_York")
_KL_TZ = ZoneInfo("Asia/Kuala_Lumpur")
_HK_TZ = ZoneInfo("Asia/Hong_Kong")


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


def is_hkex_open() -> bool:
    """
    True Mon–Fri during HKEX's two trading sessions — 9:30–12:00 and
    13:00–16:00 Asia/Hong_Kong — excluding the midday lunch break.
    Ignores Hong Kong market holidays.

    Mirrors marketStatusHK() in leaderboard/frontend/src/lib/format.js. Hong
    Kong shares Malaysia's UTC+8 offset but not its session schedule, so this
    can't reuse is_bursa_open().
    """
    now = datetime.now(_HK_TZ)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    morning = 9 * 60 + 30 <= minutes < 12 * 60
    afternoon = 13 * 60 <= minutes < 16 * 60
    return morning or afternoon


def is_ticker_market_open(ticker: str) -> bool:
    """
    Dispatches to the right exchange's trading hours based on the ticker's
    suffix. Bursa Malaysia (.KL), HKEX (.HK) and US markets trade in
    non-overlapping windows (Malaysia and Hong Kong are UTC+8, opposite side
    of the clock from US Eastern), so a single global "is the market open"
    check would either miss the Asian sessions entirely or misreport them as
    open during US hours when they are actually closed. Everything else
    defaults to US hours.
    """
    suffix = ticker.upper()
    if suffix.endswith(".KL"):
        return is_bursa_open()
    if suffix.endswith(".HK"):
        return is_hkex_open()
    return is_market_open()


_BARE_DIGITS_RE = re.compile(r"^\d{1,6}$")


# ── Negative cache for dead symbols ────────────────────────────────────────────
# A delisted or mistyped ticker fails identically on every call, and both price
# jobs swallow the exception and try again on the next tick — so one bad symbol
# costs a full yfinance round-trip every minute, forever (1,440/day). Back off
# exponentially per ticker instead, and let a single success clear the entry.
_FAILURE_GRACE = 2  # fail this many times before backing off at all
_FAILURE_BASE_COOLDOWN = timedelta(minutes=5)
_FAILURE_MAX_COOLDOWN = timedelta(hours=6)

# ticker -> (consecutive_failures, do-not-retry-before)
_failures: dict[str, tuple[int, datetime]] = {}


def _raise_if_known_bad(ticker: str) -> None:
    """Short-circuit a ticker that is in its cooldown window, without a network call."""
    entry = _failures.get(ticker)
    if entry is None:
        return
    count, retry_after = entry
    if datetime.now(timezone.utc) < retry_after:
        raise ValueError(
            f"{ticker!r} failed {count}x in a row; skipping until "
            f"{retry_after.isoformat(timespec='seconds')}"
        )


def _record_failure(ticker: str) -> None:
    count = _failures.get(ticker, (0, None))[0] + 1
    if count <= _FAILURE_GRACE:
        cooldown = timedelta(0)
    else:
        cooldown = min(
            _FAILURE_BASE_COOLDOWN * (2 ** (count - _FAILURE_GRACE - 1)),
            _FAILURE_MAX_COOLDOWN,
        )
    _failures[ticker] = (count, datetime.now(timezone.utc) + cooldown)
    if cooldown:
        logger.warning(
            "market_data: %s failed %d consecutive fetches — backing off %s",
            ticker, count, cooldown,
        )


def _clear_failure(ticker: str) -> None:
    _failures.pop(ticker, None)


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


def _fetch_latest_price_sync(ticker: str) -> Decimal:
    """Synchronous close-price fetch — intended to run in an executor."""
    hist = yf.Ticker(ticker).history(period="5d")
    if hist.empty:
        raise ValueError(f"yfinance returned no data for {ticker!r}")
    close = float(hist["Close"].iloc[-1])
    if math.isnan(close):
        raise ValueError(f"yfinance returned a NaN close price for {ticker!r}")
    return Decimal(str(close)).quantize(Decimal("0.0001"))


async def get_latest_price(ticker: str) -> Decimal:
    """
    Return the most recent available close price for ticker.
    Checks the price_ticks DB cache for today first; falls back to yfinance.
    """
    today = datetime.now(timezone.utc).date()

    async with AsyncSessionLocal() as session:
        cached = await session.get(PriceTick, (ticker, today))
        if cached is not None and not cached.price.is_nan():
            return cached.price

    _raise_if_known_bad(ticker)

    # yfinance is synchronous; calling it directly here blocks the single
    # event loop that also serves the web app and the bot, so every request
    # in flight stalls for the duration of the HTTP round-trip.
    loop = asyncio.get_event_loop()
    try:
        price = await loop.run_in_executor(None, _fetch_latest_price_sync, ticker)
    except Exception:
        _record_failure(ticker)
        raise
    _clear_failure(ticker)

    async with AsyncSessionLocal() as session:
        stmt = (
            pg_insert(PriceTick)
            .values(ticker=ticker, date=today, price=price)
            # do_update, not do_nothing: a row cached as NaN is rejected by the
            # read above, so do_nothing would leave it poisoned forever and
            # send every later call back out to yfinance.
            .on_conflict_do_update(
                index_elements=["ticker", "date"],
                set_={"price": price},
            )
        )
        await session.execute(stmt)
        await session.commit()

    return price


def _fetch_intraday_price_sync(ticker: str) -> Decimal:
    """Synchronous live-price fetch — intended to run in an executor."""
    tk = yf.Ticker(ticker)
    # fast_info has no last_price for HKEX symbols (it returns None for every
    # .HK ticker), so that path always falls through to the 1-minute bars.
    last = tk.fast_info.get("last_price")
    if last is None or math.isnan(last):
        hist = tk.history(period="1d", interval="1m")
        if hist.empty:
            raise ValueError(f"yfinance returned no intraday data for {ticker!r}")
        last = float(hist["Close"].iloc[-1])
    if math.isnan(last):
        raise ValueError(f"yfinance returned a NaN intraday price for {ticker!r}")
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
    _raise_if_known_bad(ticker)

    loop = asyncio.get_event_loop()
    try:
        price = await loop.run_in_executor(None, _fetch_intraday_price_sync, ticker)
    except Exception:
        _record_failure(ticker)
        raise
    _clear_failure(ticker)

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


def _fetch_daily_closes_sync(ticker: str, start: date, end: date):
    """Synchronous date-range history fetch — intended to run in an executor."""
    return yf.Ticker(ticker).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),  # yfinance end is exclusive
    )


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
    # Runs in an executor for the same reason as get_latest_price() — a bare
    # yf call here would block the event loop for the whole round-trip.
    loop = asyncio.get_event_loop()
    hist = await loop.run_in_executor(
        None,
        _fetch_daily_closes_sync,
        ticker,
        start,
        end,
    )
    fetched: Dict[date, Decimal] = {}
    for ts, row in hist.iterrows():
        d = ts.date()
        close = float(row["Close"])
        if d not in cached and not math.isnan(close):
            fetched[d] = Decimal(str(close)).quantize(Decimal("0.0001"))

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
