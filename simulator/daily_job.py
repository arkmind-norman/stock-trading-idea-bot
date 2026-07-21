"""
Daily cron job — run once after US market close (e.g. 21:00 UTC).

Steps:
1. Load all open positions.
2. Fetch the latest close price for every unique ticker.
3. Evaluate exit conditions per position: target hit, stop hit, 90-day holding period.
4. Close any triggered positions.
5. Compute each user's cumulative P&L (realised + unrealised) and upsert a
   DailyEquity row so the leaderboard charts stay up to date.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Protocol

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from db.config import settings
from db.database import AsyncSessionLocal
from db.models import DailyEquity, EquitySnapshot, Idea, Position, PositionStatus
from simulator.engine import calculate_equity as _calculate_equity
from simulator.engine import close_position
from simulator.market_data import get_latest_price

logger = logging.getLogger(__name__)

_HOLDING_DAYS = settings.DEFAULT_HOLDING_TRADING_DAYS


# ── Pure helpers (tested directly, no DB/network needed) ─────────────────────

def _elapsed_trading_days(entry_date: date, today: date) -> int:
    """
    Count Mon–Fri business days from entry_date up to (not including) today.
    Returns 0 on entry day, 1 on the next trading day, etc.
    Note: ignores US public holidays — acceptable for a 90-day window.
    """
    return int(np.busday_count(str(entry_date), str(today)))


def _should_close(
    direction: str,
    current_price: Decimal,
    target: Decimal | None,
    stop: Decimal | None,
    elapsed: int,
    holding_days: int,
) -> str | None:
    """
    Return the exit reason if the position should be closed today, else None.

    Priority: target > stop > holding_period.
    Long:  target when price rises to/above target; stop when price falls to/below stop.
    Short: target when price falls to/below target; stop when price rises to/above stop.
    """
    if direction == "long":
        if target is not None and current_price >= target:
            return "target"
        if stop is not None and current_price <= stop:
            return "stop"
    else:  # short
        if target is not None and current_price <= target:
            return "target"
        if stop is not None and current_price >= stop:
            return "stop"
    if elapsed >= holding_days:
        return "holding_period"
    return None


class _HasStatus(Protocol):
    status: object
    pnl: Decimal | None

    class idea:
        direction: object
        ticker: str

    entry_price: Decimal
    notional: Decimal


# _calculate_equity is now simulator.engine.calculate_equity, imported above
# under this name so existing callers/tests in this module are unaffected.


# ── Single-user snapshot (called immediately after a new position opens) ───────

async def snapshot_user_equity(user_id: int) -> None:
    """
    Write (or update) a DailyEquity row for one user right now.
    Used to make new positions appear on the leaderboard instantly.
    """
    today = datetime.now(timezone.utc).date()

    async with AsyncSessionLocal() as session:
        positions: list[Position] = (
            await session.execute(
                select(Position)
                .join(Idea, Position.idea_id == Idea.id)
                .where(Idea.user_id == user_id)
                .options(selectinload(Position.idea))
            )
        ).scalars().all()

    if not positions:
        return

    open_tickers = {p.idea.ticker for p in positions if p.status == PositionStatus.open}
    prices: dict[str, object] = {}
    for ticker in open_tickers:
        try:
            prices[ticker] = await get_latest_price(ticker)
        except Exception:
            logger.warning("snapshot_user_equity: no price for %s", ticker)

    total = _calculate_equity(positions, prices)

    async with AsyncSessionLocal() as session:
        stmt = (
            pg_insert(DailyEquity)
            .values(user_id=user_id, date=today, cumulative_pnl=total, cumulative_equity=total)
            .on_conflict_do_update(
                index_elements=["user_id", "date"],
                set_={"cumulative_pnl": total, "cumulative_equity": total},
            )
        )
        await session.execute(stmt)
        await session.commit()

    logger.info("snapshot_user_equity: user %d equity=%s written for %s", user_id, total, today)


# ── Orchestration ─────────────────────────────────────────────────────────────

async def run_daily_job() -> None:
    today = datetime.now(timezone.utc).date()
    now = datetime.utcnow()

    # ── Step 1: load all open positions ──────────────────────────────────────
    async with AsyncSessionLocal() as session:
        open_positions: list[Position] = (
            await session.execute(
                select(Position)
                .where(Position.status == PositionStatus.open)
                .options(selectinload(Position.idea))
            )
        ).scalars().all()

    if not open_positions:
        logger.info("daily_job: no open positions — nothing to do")
        return

    # ── Step 2: fetch prices for every unique ticker ──────────────────────────
    tickers = {p.idea.ticker for p in open_positions}
    prices: dict[str, Decimal] = {}
    for ticker in tickers:
        try:
            prices[ticker] = await get_latest_price(ticker)
        except Exception:
            logger.warning("daily_job: could not fetch price for %s — skipping", ticker)

    # ── Step 3: evaluate exit conditions ─────────────────────────────────────
    to_close: list[tuple[int, Decimal, str]] = []  # (position_id, exit_price, reason)

    for pos in open_positions:
        ticker = pos.idea.ticker
        if ticker not in prices:
            continue

        current = prices[ticker]
        target = (
            Decimal(str(pos.idea.target_price))
            if pos.idea.target_price is not None
            else None
        )
        stop = (
            Decimal(str(pos.idea.stop_price))
            if pos.idea.stop_price is not None
            else None
        )
        elapsed = _elapsed_trading_days(pos.entry_time.date(), today)
        reason = _should_close(
            pos.idea.direction.value, current, target, stop, elapsed, _HOLDING_DAYS
        )
        if reason:
            to_close.append((pos.id, current, reason))

    # ── Step 4: close triggered positions ────────────────────────────────────
    for position_id, exit_price, reason in to_close:
        try:
            await close_position(position_id, exit_price, now)
            logger.info(
                "daily_job: closed position %d reason=%s @ %s",
                position_id, reason, exit_price,
            )
        except Exception:
            logger.exception("daily_job: failed to close position %d", position_id)

    # ── Step 5: compute cumulative equity per user, upsert DailyEquity ───────
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
            total = _calculate_equity(user_positions, prices)
            stmt = (
                pg_insert(DailyEquity)
                .values(
                    user_id=user_id,
                    date=today,
                    cumulative_pnl=total,
                    cumulative_equity=total,
                )
                .on_conflict_do_update(
                    index_elements=["user_id", "date"],
                    set_={"cumulative_pnl": total, "cumulative_equity": total},
                )
            )
            await session.execute(stmt)

        # ── Step 6: prune intraday snapshots superseded by today's DailyEquity ──
        await session.execute(
            delete(EquitySnapshot).where(func.date(EquitySnapshot.ts) < today)
        )

        await session.commit()

    logger.info(
        "daily_job: done — %d closed today, equity updated for %d users",
        len(to_close), len(by_user),
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_daily_job())
