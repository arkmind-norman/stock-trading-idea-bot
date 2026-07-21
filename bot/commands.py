"""
Bot command implementations — pure async functions that query the DB and
return formatted strings.  The PTB handler wrappers live in handlers.py.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from db.database import AsyncSessionLocal
from db.models import (
    DailyEquity,
    Direction,
    Idea,
    IdeaStatus,
    Position,
    PositionStatus,
    PriceTick,
    User,
)
from simulator.engine import compute_pnl


async def leaderboard_command() -> str:
    """
    /leaderboard — ranked list of all users by their latest cumulative P&L.
    Returns an HTML-formatted string ready to send via Telegram.
    """
    async with AsyncSessionLocal() as session:
        # Subquery: most-recent daily_equity date per user
        latest_sq = (
            select(
                DailyEquity.user_id,
                func.max(DailyEquity.date).label("latest_date"),
            )
            .group_by(DailyEquity.user_id)
            .subquery()
        )

        rows = (
            await session.execute(
                select(User, DailyEquity.cumulative_pnl)
                .join(latest_sq, User.id == latest_sq.c.user_id)
                .join(
                    DailyEquity,
                    (DailyEquity.user_id == User.id)
                    & (DailyEquity.date == latest_sq.c.latest_date),
                )
                .order_by(DailyEquity.cumulative_pnl.desc())
            )
        ).all()

        if not rows:
            return (
                "No leaderboard data yet.\n"
                "Post a trade idea to get started — results appear after market close."
            )

        # Win-rate stats: closed positions per user
        win_stats_rows = (
            await session.execute(
                select(
                    Idea.user_id,
                    func.count(Position.id).label("total_closed"),
                    func.sum(
                        case((Position.pnl > 0, 1), else_=0)
                    ).label("winners"),
                )
                .join(Position, Position.idea_id == Idea.id)
                .where(Position.status == PositionStatus.closed)
                .group_by(Idea.user_id)
            )
        ).all()

    win_by_user: dict[int, tuple[int, int]] = {
        r.user_id: (r.total_closed, int(r.winners or 0))
        for r in win_stats_rows
    }

    medals = ["🥇", "🥈", "🥉"]
    lines = ["<b>🏆 Leaderboard</b>\n"]
    for i, (user, pnl) in enumerate(rows, 1):
        badge = medals[i - 1] if i <= 3 else f"{i}."
        name = f"@{user.username}" if user.username else user.display_name
        sign = "+" if pnl >= 0 else ""
        pnl_str = f"{sign}${float(pnl):,.2f}"

        total, wins = win_by_user.get(user.id, (0, 0))
        win_rate = f"{wins / total:.0%}" if total else "—"
        idea_count = total  # closed positions ≈ ideas traded

        lines.append(f"{badge} <b>{name}</b>  {pnl_str}  ({idea_count} ideas, {win_rate} win)")

    return "\n".join(lines)


async def myideas_command(telegram_user_id: str) -> str:
    """
    /myideas — the user's open positions and their last 10 closed ideas.
    Returns an HTML-formatted string ready to send via Telegram.
    """
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == telegram_user_id)
            )
        ).scalar_one_or_none()

        if user is None:
            return "You haven't posted any trade ideas yet. Go ahead and share one!"

        ideas: list[Idea] = (
            await session.execute(
                select(Idea)
                .where(
                    Idea.user_id == user.id,
                    Idea.status.in_([IdeaStatus.open, IdeaStatus.closed]),
                )
                .options(selectinload(Idea.position))
                .order_by(Idea.submitted_at.desc())
                .limit(30)
            )
        ).scalars().all()

        if not ideas:
            return "You haven't posted any trade ideas yet. Go ahead and share one!"

        # Fetch cached prices for open tickers so we can show mark-to-market P&L.
        open_tickers = {
            idea.ticker
            for idea in ideas
            if idea.status == IdeaStatus.open and idea.ticker
        }
        cached_prices: dict[str, Decimal] = {}
        if open_tickers:
            price_rows = (
                await session.execute(
                    select(PriceTick)
                    .where(PriceTick.ticker.in_(open_tickers))
                    .order_by(PriceTick.date.desc())
                )
            ).scalars().all()
            for pt in price_rows:
                if pt.ticker not in cached_prices:
                    cached_prices[pt.ticker] = pt.price

    # ── Format output ─────────────────────────────────────────────────────────
    name = f"@{user.username}" if user.username else user.display_name
    open_lines: list[str] = []
    closed_lines: list[str] = []

    for idea in ideas:
        pos: Position | None = idea.position

        if idea.status == IdeaStatus.open and pos:
            arrow = "📈" if idea.direction == Direction.long else "📉"
            entry = float(pos.entry_price)
            line = f"{arrow} <b>{idea.ticker}</b> {idea.direction.value}  @ ${entry:,.2f}"

            if idea.ticker in cached_prices:
                current = cached_prices[idea.ticker]
                unrealised = compute_pnl(
                    idea.direction.value, pos.entry_price, current, pos.notional
                )
                sign = "+" if unrealised >= 0 else ""
                line += f"  (mtm: {sign}${float(unrealised):,.2f})"

            open_lines.append(line)

        elif idea.status == IdeaStatus.closed and pos and pos.pnl is not None:
            entry = float(pos.entry_price)
            exit_ = float(pos.exit_price) if pos.exit_price else 0.0
            pnl = float(pos.pnl)
            sign = "+" if pnl >= 0 else ""
            emoji = "✅" if pnl >= 0 else "❌"
            closed_lines.append(
                f"{emoji} <b>{idea.ticker}</b> {idea.direction.value}  "
                f"${entry:,.2f} → ${exit_:,.2f}  P&L: {sign}${pnl:,.2f}"
            )

    parts = [f"<b>📊 {name}'s ideas</b>\n"]

    if open_lines:
        parts.append(f"<b>Open ({len(open_lines)})</b>")
        parts.extend(open_lines)
    else:
        parts.append("No open positions.")

    closed_to_show = closed_lines[:10]
    if closed_to_show:
        parts.append(f"\n<b>Recent closed ({len(closed_to_show)})</b>")
        parts.extend(closed_to_show)

    return "\n".join(parts)
