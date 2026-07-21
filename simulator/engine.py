from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.config import settings
from db.database import AsyncSessionLocal
from db.models import Idea, IdeaStatus, Position, PositionStatus
from simulator.market_data import get_latest_price

logger = logging.getLogger(__name__)

_NOTIONAL = Decimal(str(settings.POSITION_NOTIONAL))
_MAX_OPEN = settings.MAX_OPEN_POSITIONS_PER_USER


@dataclass
class OpenedPosition:
    position_id: int
    ticker: str
    direction: str
    entry_price: Decimal
    notional: Decimal
    shares: Decimal


def compute_pnl(
    direction: str,
    entry_price: Decimal,
    exit_price: Decimal,
    notional: Decimal,
) -> Decimal:
    """P&L = ±(exit − entry) / entry × notional; sign is flipped for shorts."""
    sign = Decimal("1") if direction == "long" else Decimal("-1")
    return (sign * (exit_price - entry_price) / entry_price * notional).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


async def open_position(idea_id: int) -> OpenedPosition:
    """
    Open a $1 000-notional simulated position for the given idea.

    Enforces the per-user cap of MAX_OPEN_POSITIONS_PER_USER concurrent positions.
    If the cap is already reached the *oldest* open position (by entry_time) is
    closed at the current market price before the new one is opened (FIFO eviction).
    """
    async with AsyncSessionLocal() as session:
        idea = await session.get(Idea, idea_id)
        if idea is None:
            raise ValueError(f"Idea {idea_id} not found")

        user_id = idea.user_id
        ticker = idea.ticker
        direction = idea.direction.value

        # All open positions for this user, oldest first
        open_positions: list[Position] = (
            await session.execute(
                select(Position)
                .join(Idea, Position.idea_id == Idea.id)
                .where(Idea.user_id == user_id, Position.status == PositionStatus.open)
                .options(selectinload(Position.idea))
                .order_by(Position.entry_time.asc())
            )
        ).scalars().all()

        if len(open_positions) >= _MAX_OPEN:
            oldest = open_positions[0]
            evict_price = await get_latest_price(oldest.idea.ticker)
            evict_time = datetime.utcnow()
            oldest.exit_price = evict_price
            oldest.exit_time = evict_time
            oldest.pnl = compute_pnl(
                oldest.idea.direction.value,
                oldest.entry_price,
                evict_price,
                oldest.notional,
            )
            oldest.status = PositionStatus.closed
            oldest.idea.status = IdeaStatus.closed
            logger.info(
                "FIFO evict: closed position %d (%s) pnl=%s for user %d to make room",
                oldest.id, oldest.idea.ticker, oldest.pnl, user_id,
            )

        entry_price = await get_latest_price(ticker)
        shares = (_NOTIONAL / entry_price).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        now = datetime.utcnow()

        new_position = Position(
            idea_id=idea_id,
            entry_price=entry_price,
            entry_time=now,
            notional=_NOTIONAL,
            status=PositionStatus.open,
        )
        session.add(new_position)
        idea.status = IdeaStatus.open
        await session.commit()
        await session.refresh(new_position)
        position_id = new_position.id

    logger.info(
        "Opened %s %s @ %s (notional=$%s, shares=%s) for user %d",
        direction, ticker, entry_price, _NOTIONAL, shares, user_id,
    )

    return OpenedPosition(
        position_id=position_id,
        ticker=ticker,
        direction=direction,
        entry_price=entry_price,
        notional=_NOTIONAL,
        shares=shares,
    )


async def close_position(
    position_id: int,
    exit_price: Decimal,
    exit_time: datetime,
) -> Decimal:
    """
    Mark a position closed and return its realised P&L in USD.

    pnl = (exit − entry) / entry × notional   (sign flipped for shorts)
    """
    async with AsyncSessionLocal() as session:
        position: Position = (
            await session.execute(
                select(Position)
                .where(Position.id == position_id)
                .options(selectinload(Position.idea))
            )
        ).scalar_one()

        pnl = compute_pnl(
            position.idea.direction.value,
            position.entry_price,
            exit_price,
            position.notional,
        )
        position.exit_price = exit_price
        position.exit_time = exit_time
        position.pnl = pnl
        position.status = PositionStatus.closed
        position.idea.status = IdeaStatus.closed
        await session.commit()

    logger.info("Closed position %d pnl=%s", position_id, pnl)
    return pnl
