"""
Intraday equity (P&L) snapshot job — runs every 1 minute, but only pulls a
*fresh* price for tickers whose own exchange is currently open (see
market_data.is_ticker_market_open). Bursa Malaysia (.KL tickers) and US
markets trade in non-overlapping windows, so gating everything on US hours
alone meant Malaysian positions never got live intraday snapshots during
Bursa's actual trading session — they'd sit flat until the next once-daily
mark-to-market. Tickers whose market is currently closed reuse their last
cached price instead of a live call, since that price genuinely hasn't
moved.

Pulls a fresh price for every ticker with an open position and writes one
EquitySnapshot row per user (cumulative P&L at that minute), so the
leaderboard chart can show live intraday movement instead of just one point
per day. The daily close-of-market job (simulator.daily_job) remains the
source of truth for each day's final point.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.database import AsyncSessionLocal
from db.models import EquitySnapshot, Position, PositionStatus
from simulator.engine import calculate_equity
from simulator.market_data import get_intraday_price, get_latest_price, is_ticker_market_open

logger = logging.getLogger(__name__)


async def run_intraday_job() -> None:
    async with AsyncSessionLocal() as session:
        open_positions: list[Position] = (
            await session.execute(
                select(Position)
                .where(Position.status == PositionStatus.open)
                .options(selectinload(Position.idea))
            )
        ).scalars().all()

    if not open_positions:
        return

    tickers = {p.idea.ticker for p in open_positions}

    # Nothing to do this minute if every relevant market is currently closed
    # (e.g. the shared weekend, or the gap between Bursa's afternoon close
    # and the next US open) — skip the cycle rather than writing a snapshot
    # that would be identical to the last one across the board.
    open_tickers = {t for t in tickers if is_ticker_market_open(t)}
    if not open_tickers:
        return

    prices: dict[str, Decimal] = {}
    for ticker in tickers:
        try:
            if ticker in open_tickers:
                prices[ticker] = await get_intraday_price(ticker)
            else:
                # This ticker's own market is closed right now, so its price
                # hasn't moved — reuse the last known value instead of an
                # unnecessary live fetch.
                prices[ticker] = await get_latest_price(ticker)
        except Exception:
            logger.warning("intraday_job: could not fetch price for %s — skipping", ticker)

    if not prices:
        return

    # Naive UTC, matching the rest of the codebase's DateTime columns
    # (e.g. Position.entry_time) — the equity_snapshots.ts column is
    # TIMESTAMP WITHOUT TIME ZONE, which asyncpg rejects tz-aware values for.
    now = datetime.utcnow()

    async with AsyncSessionLocal() as session:
        all_positions: list[Position] = (
            await session.execute(
                select(Position).options(selectinload(Position.idea))
            )
        ).scalars().all()

        by_user: dict[int, list[Position]] = defaultdict(list)
        for p in all_positions:
            by_user[p.idea.user_id].append(p)

        for user_id, user_positions in by_user.items():
            total = calculate_equity(user_positions, prices)
            session.add(
                EquitySnapshot(
                    user_id=user_id,
                    ts=now,
                    cumulative_pnl=total,
                    cumulative_equity=total,
                )
            )

        await session.commit()

    logger.info(
        "intraday_job: snapshot written for %d users (%d/%d tickers live)",
        len(by_user), len(open_tickers), len(tickers),
    )
