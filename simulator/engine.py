from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class OpenedPosition:
    position_id: int
    ticker: str
    direction: str
    entry_price: Decimal
    notional: Decimal
    shares: Decimal


async def open_position(
    idea_id: int,
    ticker: str,
    direction: str,
    target_price: float | None,
    stop_price: float | None,
) -> OpenedPosition:
    """
    Fetch the latest close price, create a Position row, and return the details.

    TODO:
    - Call market_data.get_latest_price(ticker)
    - Compute shares = POSITION_NOTIONAL / entry_price
    - Insert Position record into DB linked to idea_id
    - Update Idea.status → "open"
    """
    raise NotImplementedError


async def close_position(position_id: int, exit_price: Decimal, exit_time: datetime) -> Decimal:
    """
    Mark a position closed and compute final P&L.

    Returns the P&L in USD.

    TODO:
    - Fetch Position + its Idea (for direction)
    - pnl = (exit - entry) / entry * notional  (flip sign for shorts)
    - Update Position.exit_price, exit_time, pnl, status → "closed"
    - Update Idea.status → "closed"
    """
    raise NotImplementedError
