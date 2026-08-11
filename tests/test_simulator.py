"""
Unit tests for the simulator engine and daily job.

All DB and network I/O is replaced with fakes, so no live Postgres or
yfinance calls are made. Tests are grouped into four areas:

  1. compute_pnl          — pure P&L arithmetic
  2. _elapsed_trading_days — business-day counting
  3. _should_close        — exit-condition logic
  4. _calculate_equity    — realised + unrealised equity sum
  5. run_daily_job        — orchestration: correct positions get closed,
                            DailyEquity rows are written
  6. is_ticker_market_open — per-exchange trading hours (US / Bursa / HKEX)
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call, patch

import numpy as np
import pytest

from db.models import PositionStatus
from simulator.daily_job import (
    _calculate_equity,
    _elapsed_trading_days,
    _should_close,
    run_daily_job,
)
from simulator.engine import compute_pnl
from simulator.market_data import is_market_open, is_ticker_market_open


# ── Fake domain objects (duck-typed stand-ins for SQLAlchemy models) ──────────

@dataclass
class _Dir:
    value: str


@dataclass
class _Idea:
    user_id: int
    ticker: str
    direction: _Dir
    target_price: Decimal | None = None
    stop_price: Decimal | None = None
    status: str = "open"


@dataclass
class _Pos:
    id: int
    idea: _Idea
    entry_price: Decimal
    entry_time: datetime
    notional: Decimal
    status: object  # PositionStatus enum value
    pnl: Decimal | None = None
    exit_price: Decimal | None = None
    exit_time: datetime | None = None


def _pos(
    *,
    id: int = 1,
    user_id: int = 1,
    ticker: str = "AAPL",
    direction: str = "long",
    entry_price: str = "100",
    notional: str = "1000",
    status: object = PositionStatus.open,
    pnl: str | None = None,
    target: str | None = None,
    stop: str | None = None,
    days_ago: int = 0,
) -> _Pos:
    """Convenience factory for fake positions."""
    return _Pos(
        id=id,
        idea=_Idea(
            user_id=user_id,
            ticker=ticker,
            direction=_Dir(direction),
            target_price=Decimal(target) if target else None,
            stop_price=Decimal(stop) if stop else None,
        ),
        entry_price=Decimal(entry_price),
        entry_time=datetime.utcnow() - timedelta(days=days_ago),
        notional=Decimal(notional),
        status=status,
        pnl=Decimal(pnl) if pnl is not None else None,
    )


def _make_async_session(positions: list) -> AsyncMock:
    """
    Return an AsyncMock that acts as an async context manager session.
    All execute() calls return a result whose .scalars().all() yields positions.
    """
    result = MagicMock()
    result.scalars.return_value.all.return_value = positions

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ═══════════════════════════════════════════════════════════════════════════════
# 1. compute_pnl
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputePnl:
    def test_long_profit(self):
        # 10% gain: (110-100)/100 * 1000 = $100
        assert compute_pnl("long", Decimal("100"), Decimal("110"), Decimal("1000")) == Decimal("100.0000")

    def test_long_loss(self):
        # 10% loss
        assert compute_pnl("long", Decimal("100"), Decimal("90"), Decimal("1000")) == Decimal("-100.0000")

    def test_short_profit(self):
        # Short: price falls 10% → gain
        assert compute_pnl("short", Decimal("100"), Decimal("90"), Decimal("1000")) == Decimal("100.0000")

    def test_short_loss(self):
        # Short: price rises 10% → loss
        assert compute_pnl("short", Decimal("100"), Decimal("110"), Decimal("1000")) == Decimal("-100.0000")

    def test_flat_position(self):
        assert compute_pnl("long", Decimal("100"), Decimal("100"), Decimal("1000")) == Decimal("0.0000")

    def test_fractional_price(self):
        # 25% gain on $500 = $125
        assert compute_pnl("long", Decimal("200"), Decimal("250"), Decimal("500")) == Decimal("125.0000")

    def test_notional_scales_pnl(self):
        # Same % move, different notionals
        small = compute_pnl("long", Decimal("100"), Decimal("110"), Decimal("500"))
        large = compute_pnl("long", Decimal("100"), Decimal("110"), Decimal("1000"))
        assert large == small * 2

    def test_short_symmetric_with_long(self):
        # A short on a falling price should mirror a long on a rising price by the same %.
        pnl_long = compute_pnl("long", Decimal("100"), Decimal("120"), Decimal("1000"))
        pnl_short = compute_pnl("short", Decimal("100"), Decimal("80"), Decimal("1000"))
        assert pnl_long == pnl_short

    def test_result_is_decimal(self):
        result = compute_pnl("long", Decimal("50"), Decimal("75"), Decimal("1000"))
        assert isinstance(result, Decimal)

    def test_rounding_to_four_places(self):
        # 1/3 gain does not produce infinite decimals
        result = compute_pnl("long", Decimal("3"), Decimal("4"), Decimal("1000"))
        assert result == Decimal("333.3333")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. _elapsed_trading_days
# ═══════════════════════════════════════════════════════════════════════════════

class TestElapsedTradingDays:
    def test_same_day_is_zero(self):
        d = date(2025, 1, 6)  # Monday
        assert _elapsed_trading_days(d, d) == 0

    def test_next_business_day(self):
        # Monday → Tuesday = 1
        assert _elapsed_trading_days(date(2025, 1, 6), date(2025, 1, 7)) == 1

    def test_weekend_not_counted(self):
        # Friday → Monday: only Friday counts (Mon is the exclusive end)
        assert _elapsed_trading_days(date(2025, 1, 10), date(2025, 1, 13)) == 1

    def test_full_week(self):
        # Monday to next Monday = 5 business days
        assert _elapsed_trading_days(date(2025, 1, 6), date(2025, 1, 13)) == 5

    def test_exactly_ninety_days(self):
        start = date(2025, 1, 6)
        end = date.fromisoformat(str(np.busday_offset(str(start), 90)))
        assert _elapsed_trading_days(start, end) == 90

    def test_eighty_nine_days(self):
        start = date(2025, 1, 6)
        end = date.fromisoformat(str(np.busday_offset(str(start), 89)))
        assert _elapsed_trading_days(start, end) == 89


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _should_close
# ═══════════════════════════════════════════════════════════════════════════════

class TestShouldClose:
    # Long — target
    def test_long_target_hit_exactly(self):
        assert _should_close("long", Decimal("120"), Decimal("120"), None, 0, 90) == "target"

    def test_long_target_exceeded(self):
        assert _should_close("long", Decimal("125"), Decimal("120"), None, 0, 90) == "target"

    def test_long_target_not_yet(self):
        assert _should_close("long", Decimal("119"), Decimal("120"), None, 0, 90) is None

    # Long — stop
    def test_long_stop_hit_exactly(self):
        assert _should_close("long", Decimal("90"), None, Decimal("90"), 0, 90) == "stop"

    def test_long_stop_breached(self):
        assert _should_close("long", Decimal("85"), None, Decimal("90"), 0, 90) == "stop"

    def test_long_stop_not_hit(self):
        assert _should_close("long", Decimal("91"), None, Decimal("90"), 0, 90) is None

    # Short — target (price drops to/below)
    def test_short_target_hit(self):
        assert _should_close("short", Decimal("80"), Decimal("85"), None, 0, 90) == "target"

    def test_short_target_not_yet(self):
        assert _should_close("short", Decimal("86"), Decimal("85"), None, 0, 90) is None

    # Short — stop (price rises to/above)
    def test_short_stop_hit(self):
        assert _should_close("short", Decimal("110"), None, Decimal("105"), 0, 90) == "stop"

    def test_short_stop_not_hit(self):
        assert _should_close("short", Decimal("104"), None, Decimal("105"), 0, 90) is None

    # Holding period
    def test_holding_period_expired(self):
        assert _should_close("long", Decimal("100"), None, None, 90, 90) == "holding_period"

    def test_holding_period_not_expired(self):
        assert _should_close("long", Decimal("100"), None, None, 89, 90) is None

    def test_no_exit_conditions_no_close(self):
        assert _should_close("long", Decimal("105"), None, None, 10, 90) is None

    # Priority: target beats holding period
    def test_target_priority_over_holding(self):
        reason = _should_close("long", Decimal("130"), Decimal("120"), None, 95, 90)
        assert reason == "target"

    # Priority: stop beats holding period
    def test_stop_priority_over_holding(self):
        reason = _should_close("long", Decimal("70"), None, Decimal("80"), 95, 90)
        assert reason == "stop"

    # No target/stop provided — only holding period applies
    def test_no_target_no_stop_only_holding(self):
        assert _should_close("short", Decimal("200"), None, None, 90, 90) == "holding_period"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. _calculate_equity
# ═══════════════════════════════════════════════════════════════════════════════

class TestCalculateEquity:
    def test_single_closed_position(self):
        pos = _pos(status=PositionStatus.closed, pnl="150")
        assert _calculate_equity([pos], {}) == Decimal("150.0000")

    def test_single_open_position_profit(self):
        # entry=100, current=110 → +10% on $1 000 = $100
        pos = _pos(entry_price="100", notional="1000")
        result = _calculate_equity([pos], {"AAPL": Decimal("110")})
        assert result == Decimal("100.0000")

    def test_single_open_position_loss(self):
        # entry=100, current=90 → -10% = -$100
        pos = _pos(entry_price="100", notional="1000")
        result = _calculate_equity([pos], {"AAPL": Decimal("90")})
        assert result == Decimal("-100.0000")

    def test_short_open_unrealised(self):
        # short, entry=100, current=80 → +20% = +$200
        pos = _pos(direction="short", entry_price="100", notional="1000")
        result = _calculate_equity([pos], {"AAPL": Decimal("80")})
        assert result == Decimal("200.0000")

    def test_realized_plus_unrealized(self):
        # Closed: +$100 realised
        closed = _pos(id=1, status=PositionStatus.closed, pnl="100")
        # Open: entry=100, current=90 → -$100 unrealised
        open_pos = _pos(id=2, status=PositionStatus.open, entry_price="100", notional="1000")
        result = _calculate_equity([closed, open_pos], {"AAPL": Decimal("90")})
        assert result == Decimal("0.0000")  # +100 − 100 = 0

    def test_two_closed_positions_summed(self):
        p1 = _pos(id=1, status=PositionStatus.closed, pnl="200")
        p2 = _pos(id=2, status=PositionStatus.closed, pnl="-50")
        assert _calculate_equity([p1, p2], {}) == Decimal("150.0000")

    def test_missing_price_skips_open_position(self):
        # Open position for a ticker not in prices → should be silently skipped
        open_pos = _pos(ticker="MISSING")
        closed = _pos(id=2, status=PositionStatus.closed, pnl="75")
        result = _calculate_equity([open_pos, closed], {})
        assert result == Decimal("75.0000")

    def test_empty_positions_returns_zero(self):
        assert _calculate_equity([], {}) == Decimal("0.0000")

    def test_result_rounded_to_four_places(self):
        # 1/3 gain: verify decimal rounding rather than infinite precision
        pos = _pos(entry_price="3", notional="1000")
        result = _calculate_equity([pos], {"AAPL": Decimal("4")})
        assert result == Decimal("333.3333")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. run_daily_job — orchestration (DB + price fetcher mocked)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunDailyJob:
    @pytest.mark.asyncio
    async def test_no_open_positions_returns_early(self):
        """When there are no open positions the job exits without any closes."""
        session = _make_async_session([])
        with patch("simulator.daily_job.AsyncSessionLocal", return_value=session):
            with patch("simulator.daily_job.close_position") as mock_close:
                await run_daily_job()
        mock_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_expired_holding_period_closed(self):
        """A position past 90 trading days (≈130 calendar days) is closed."""
        pos = _pos(id=7, days_ago=130)  # well beyond 90 trading days

        s1 = _make_async_session([pos])   # Step 1: open positions
        s2 = _make_async_session([pos])   # Step 5: all positions for equity

        with patch("simulator.daily_job.AsyncSessionLocal", side_effect=[s1, s2]):
            with patch(
                "simulator.daily_job.get_latest_price",
                new=AsyncMock(return_value=Decimal("110")),
            ):
                with patch(
                    "simulator.daily_job.close_position",
                    new=AsyncMock(return_value=Decimal("100")),
                ) as mock_close:
                    await run_daily_job()

        mock_close.assert_called_once()
        args = mock_close.call_args[0]
        assert args[0] == 7                       # correct position id
        assert args[1] == Decimal("110")          # exit at current market price

    @pytest.mark.asyncio
    async def test_target_hit_closes_long(self):
        """A long position whose current price meets its target is closed."""
        pos = _pos(id=3, direction="long", entry_price="100", target="120", days_ago=5)

        s1 = _make_async_session([pos])
        s2 = _make_async_session([pos])

        with patch("simulator.daily_job.AsyncSessionLocal", side_effect=[s1, s2]):
            with patch(
                "simulator.daily_job.get_latest_price",
                new=AsyncMock(return_value=Decimal("125")),  # above target
            ):
                with patch(
                    "simulator.daily_job.close_position",
                    new=AsyncMock(return_value=Decimal("250")),
                ) as mock_close:
                    await run_daily_job()

        mock_close.assert_called_once()
        assert mock_close.call_args[0][0] == 3

    @pytest.mark.asyncio
    async def test_stop_hit_closes_long(self):
        """A long position whose current price is at or below its stop is closed."""
        pos = _pos(id=4, direction="long", entry_price="100", stop="85", days_ago=5)

        s1 = _make_async_session([pos])
        s2 = _make_async_session([pos])

        with patch("simulator.daily_job.AsyncSessionLocal", side_effect=[s1, s2]):
            with patch(
                "simulator.daily_job.get_latest_price",
                new=AsyncMock(return_value=Decimal("80")),  # below stop
            ):
                with patch(
                    "simulator.daily_job.close_position",
                    new=AsyncMock(return_value=Decimal("-200")),
                ) as mock_close:
                    await run_daily_job()

        mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_target_hit_closes_short(self):
        """A short position whose current price drops to/below its target is closed."""
        pos = _pos(id=5, direction="short", entry_price="100", target="75", days_ago=5)

        s1 = _make_async_session([pos])
        s2 = _make_async_session([pos])

        with patch("simulator.daily_job.AsyncSessionLocal", side_effect=[s1, s2]):
            with patch(
                "simulator.daily_job.get_latest_price",
                new=AsyncMock(return_value=Decimal("70")),  # below short target
            ):
                with patch(
                    "simulator.daily_job.close_position",
                    new=AsyncMock(return_value=Decimal("300")),
                ) as mock_close:
                    await run_daily_job()

        mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_position_within_period_not_closed(self):
        """A position 5 days old with no target/stop is NOT closed."""
        pos = _pos(id=6, days_ago=5)

        s1 = _make_async_session([pos])
        s2 = _make_async_session([pos])

        with patch("simulator.daily_job.AsyncSessionLocal", side_effect=[s1, s2]):
            with patch(
                "simulator.daily_job.get_latest_price",
                new=AsyncMock(return_value=Decimal("105")),
            ):
                with patch(
                    "simulator.daily_job.close_position",
                    new=AsyncMock(),
                ) as mock_close:
                    await run_daily_job()

        mock_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_equity_written_per_user(self):
        """One DailyEquity upsert is executed per user."""
        p1 = _pos(id=1, user_id=1, ticker="AAPL", days_ago=5)
        p2 = _pos(id=2, user_id=2, ticker="TSLA", days_ago=5)

        s1 = _make_async_session([p1, p2])
        s2 = _make_async_session([p1, p2])

        with patch("simulator.daily_job.AsyncSessionLocal", side_effect=[s1, s2]):
            with patch(
                "simulator.daily_job.get_latest_price",
                new=AsyncMock(return_value=Decimal("100")),
            ):
                with patch("simulator.daily_job.close_position", new=AsyncMock()):
                    await run_daily_job()

        # s2 is the equity session — execute should be called once per user, plus
        # one for the positions SELECT and one for the intraday-snapshot prune DELETE
        equity_upsert_calls = s2.execute.call_count - 2
        assert equity_upsert_calls == 2  # one per user


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Exchange trading hours (is_ticker_market_open dispatch)
# ═══════════════════════════════════════════════════════════════════════════════

class _FrozenDatetime(datetime):
    """datetime subclass whose now() returns a fixed instant in the asked-for tz."""

    _instant: datetime = None

    @classmethod
    def now(cls, tz=None):
        return cls._instant.astimezone(tz) if tz else cls._instant.replace(tzinfo=None)


@contextmanager
def _at(utc_iso: str):
    """Freeze simulator.market_data's clock at the given UTC instant."""
    frozen = type("_F", (_FrozenDatetime,), {"_instant": datetime.fromisoformat(utc_iso)})
    with patch("simulator.market_data.datetime", frozen):
        yield


class TestExchangeHours:
    """
    HKEX (.HK) trades 9:30-12:00 and 13:00-16:00 Asia/Hong_Kong — the opposite
    side of the clock from US Eastern. Before .HK was dispatched to its own
    calendar it fell through to US hours, so HK positions were marked "closed"
    for their entire real session (reusing the day-cached price, which had been
    seeded with the *previous* close during the half-hour when Bursa is already
    open and HKEX is not) and "open" overnight when HKEX was actually shut.
    """

    # HKEX sessions — 01:30-04:00 and 05:00-08:00 UTC
    def test_hk_open_morning_session(self):
        with _at("2026-08-11T02:00:00+00:00"):  # 10:00 HKT Tue
            assert is_ticker_market_open("0700.HK") is True

    def test_hk_open_afternoon_session(self):
        with _at("2026-08-11T06:00:00+00:00"):  # 14:00 HKT Tue
            assert is_ticker_market_open("0700.HK") is True

    def test_hk_closed_during_lunch_break(self):
        with _at("2026-08-11T04:30:00+00:00"):  # 12:30 HKT Tue
            assert is_ticker_market_open("0700.HK") is False

    def test_hk_closed_before_open(self):
        """
        09:00 HKT: Bursa is already open, so the intraday job is running, but
        HKEX is not — this is the window that used to seed the day cache with
        yesterday's close.
        """
        with _at("2026-08-11T01:00:00+00:00"):
            assert is_ticker_market_open("0700.HK") is False

    def test_hk_closed_during_us_session(self):
        """The regression: US hours must no longer mark a .HK ticker open."""
        with _at("2026-08-11T18:00:00+00:00"):  # 14:00 ET Tue / 02:00 HKT Wed
            assert is_market_open() is True
            assert is_ticker_market_open("0700.HK") is False

    def test_hk_closed_on_weekend(self):
        with _at("2026-08-15T02:00:00+00:00"):  # 10:00 HKT Sat
            assert is_ticker_market_open("0700.HK") is False

    def test_hk_suffix_is_case_insensitive(self):
        with _at("2026-08-11T02:00:00+00:00"):
            assert is_ticker_market_open("0700.hk") is True

    # The other two calendars must be unaffected by the new branch
    def test_bursa_still_dispatched_during_hk_hours(self):
        with _at("2026-08-11T02:00:00+00:00"):  # 10:00 MYT/HKT Tue
            assert is_ticker_market_open("1155.KL") is True

    def test_bursa_closed_during_lunch_while_hkex_trades(self):
        """Bursa breaks 12:30-14:30, HKEX 12:00-13:00 — the calendars differ."""
        with _at("2026-08-11T05:30:00+00:00"):  # 13:30 local Tue
            assert is_ticker_market_open("1155.KL") is False
            assert is_ticker_market_open("0700.HK") is True

    def test_us_ticker_still_defaults_to_us_hours(self):
        with _at("2026-08-11T18:00:00+00:00"):  # 14:00 ET Tue
            assert is_ticker_market_open("AAPL") is True
        with _at("2026-08-11T02:00:00+00:00"):  # 22:00 ET Mon
            assert is_ticker_market_open("AAPL") is False
