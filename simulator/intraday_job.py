"""
Intraday equity (P&L) snapshot job — runs every 1 minute while the US market
is open.

Pulls a fresh price for every ticker with an open position and writes one
EquitySnapshot row per user (cumulative P&L at that minute), so the
leaderboard chart can show live intraday movement instead of just one point
per day. The daily close-of-market job (simulator.daily_job) remains the
source of truth for each day's final point and prunes these intraday rows
once superseded.
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
from simulator.market_data import get_intraday_price, is_market_open

logger = logging.getLogger(__name__)


async def run_intraday_job() -> None:
    if not is_market_open():
        return

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
    prices: dict[str, Decimal] = {}
    for ticker in tickers:
        try:
            prices[ticker] = await get_intraday_price(ticker)
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

    logger.info("intraday_job: snapshot written for %d users", len(by_user))
