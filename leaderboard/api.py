from __future__ import annotations

import os
from collections import defaultdict
from decimal import Decimal
from itertools import groupby
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from db.database import AsyncSessionLocal
from db.models import (
    DailyEquity,
    Idea,
    IdeaStatus,
    Position,
    PositionStatus,
    PriceTick,
    User,
)
from simulator.engine import compute_pnl

router = APIRouter()

_STATIC = os.path.join(os.path.dirname(__file__), "static")

_PALETTE = [
    "#a78bfa", "#60a5fa", "#2dd4bf", "#a3e635",
    "#f472b6", "#fbbf24", "#fb923c", "#e879f9",
]


def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    return "".join(p[0].upper() for p in parts[:2]) if parts else "?"


def _color(user_id: int) -> str:
    return _PALETTE[user_id % len(_PALETTE)]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _proxy_photo_url(user: User) -> str | None:
    """Return proxy URL so the Telegram bot token never reaches the browser."""
    return f"/leaderboard/photo/{user.telegram_user_id}" if user.photo_url else None


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/")
async def index() -> FileResponse:
    return FileResponse(os.path.join(_STATIC, "index.html"))


@router.get("/photo/{telegram_user_id}")
async def user_photo(telegram_user_id: str) -> Response:
    """Proxy the Telegram profile photo so the bot token isn't exposed to the browser."""
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == telegram_user_id)
            )
        ).scalar_one_or_none()
    if not user or not user.photo_url:
        raise HTTPException(status_code=404, detail="No photo")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(user.photo_url)
            r.raise_for_status()
        return Response(
            content=r.content,
            media_type=r.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Photo unavailable")


@router.get("/data/leaderboard")
async def leaderboard_data() -> dict[str, Any]:
    """
    Returns:
      {
        "users": [ranked by cumulative P&L, each with equity_curve],
        "feed":  [all ideas across all users, newest first]
      }
    """
    async with AsyncSessionLocal() as session:
        # ── Latest P&L per user ───────────────────────────────────────────────
        latest_sq = (
            select(
                DailyEquity.user_id,
                func.max(DailyEquity.date).label("latest_date"),
            )
            .group_by(DailyEquity.user_id)
            .subquery()
        )
        equity_rows = (
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

        if not equity_rows:
            # No daily job has run yet — still return the idea feed so it's visible
            feed_rows = (
                await session.execute(
                    select(Idea, User)
                    .join(User, Idea.user_id == User.id)
                    .where(Idea.status.in_([IdeaStatus.open, IdeaStatus.closed]))
                    .options(selectinload(Idea.position))
                    .order_by(Idea.submitted_at.desc())
                    .limit(100)
                )
            ).all()
            feed = []
            for idea, user in feed_rows:
                pos = idea.position
                feed.append({
                    "telegram_user_id": user.telegram_user_id,
                    "display_name": user.display_name,
                    "initials": _initials(user.display_name),
                    "color": _color(user.id),
                    "photo_url": _proxy_photo_url(user),
                    "ticker": idea.ticker,
                    "company_name": idea.company_name or idea.ticker,
                    "direction": idea.direction.value if idea.direction else None,
                    "entry_price": float(pos.entry_price) if pos else None,
                    "current_price": None,
                    "pnl_usd": None,
                    "pnl_pct": None,
                    "status": idea.status.value,
                    "raw_text": (idea.raw_text or "")[:120],
                    "submitted_at": idea.submitted_at.isoformat() if idea.submitted_at else None,
                })
            return {"users": [], "feed": feed}

        # ── All equity curves ─────────────────────────────────────────────────
        curve_rows = (
            await session.execute(
                select(DailyEquity)
                .order_by(DailyEquity.user_id, DailyEquity.date.asc())
            )
        ).scalars().all()
        curves_by_user: dict[int, list] = defaultdict(list)
        for r in curve_rows:
            curves_by_user[r.user_id].append(
                {"date": str(r.date), "equity": float(r.cumulative_pnl)}
            )

        # ── Win stats (closed positions) ──────────────────────────────────────
        win_rows = (
            await session.execute(
                select(
                    Idea.user_id,
                    func.count(Position.id).label("total_closed"),
                    func.sum(case((Position.pnl > 0, 1), else_=0)).label("winners"),
                )
                .join(Position, Position.idea_id == Idea.id)
                .where(Position.status == PositionStatus.closed)
                .group_by(Idea.user_id)
            )
        ).all()
        win_by_user: dict[int, tuple[int, int]] = {
            r.user_id: (int(r.total_closed), int(r.winners or 0)) for r in win_rows
        }

        # ── Streaks: consecutive wins from most-recent closed positions ────────
        closed_rows = (
            await session.execute(
                select(Idea.user_id, Position.pnl)
                .join(Position, Position.idea_id == Idea.id)
                .where(Position.status == PositionStatus.closed)
                .order_by(Idea.user_id, Position.exit_time.desc())
            )
        ).all()
        streak_map: dict[int, int] = {}
        for uid, grp in groupby(closed_rows, key=lambda r: r.user_id):
            streak = 0
            for row in grp:
                if row.pnl is not None and row.pnl > 0:
                    streak += 1
                else:
                    break
            streak_map[uid] = streak

        # ── Feed: all valid ideas, newest first ───────────────────────────────
        feed_rows = (
            await session.execute(
                select(Idea, User)
                .join(User, Idea.user_id == User.id)
                .where(Idea.status.in_([IdeaStatus.open, IdeaStatus.closed]))
                .options(selectinload(Idea.position))
                .order_by(Idea.submitted_at.desc())
                .limit(100)
            )
        ).all()

        # ── Cached prices for open tickers ────────────────────────────────────
        open_tickers = {
            idea.ticker
            for idea, _ in feed_rows
            if idea.status == IdeaStatus.open and idea.ticker
        }
        cached_prices: dict[str, Decimal] = {}
        if open_tickers:
            for pt in (
                await session.execute(
                    select(PriceTick)
                    .where(PriceTick.ticker.in_(open_tickers))
                    .order_by(PriceTick.date.desc())
                )
            ).scalars().all():
                if pt.ticker not in cached_prices:
                    cached_prices[pt.ticker] = pt.price

    # ── Build response ─────────────────────────────────────────────────────────
    users = []
    for rank, (user, pnl) in enumerate(equity_rows, 1):
        total, wins = win_by_user.get(user.id, (0, 0))
        users.append({
            "rank": rank,
            "telegram_user_id": user.telegram_user_id,
            "username": user.username,
            "display_name": user.display_name,
            "initials": _initials(user.display_name),
            "color": _color(user.id),
            "photo_url": _proxy_photo_url(user),
            "pnl": float(pnl),
            "win_rate": round(wins / total, 4) if total else 0.0,
            "idea_count": total,
            "streak": streak_map.get(user.id, 0),
            "equity_curve": curves_by_user.get(user.id, []),
        })

    feed = []
    for idea, user in feed_rows:
        pos = idea.position
        entry = float(pos.entry_price) if pos else None
        current = pnl_usd = pnl_pct = None

        if idea.status == IdeaStatus.closed and pos and pos.pnl is not None:
            pnl_usd = float(pos.pnl)
            current = float(pos.exit_price) if pos.exit_price else None
            if entry and pos.exit_price:
                pnl_pct = float(
                    (pos.exit_price - pos.entry_price) / pos.entry_price * 100
                )
        elif idea.status == IdeaStatus.open and pos and idea.ticker in cached_prices:
            cp = cached_prices[idea.ticker]
            current = float(cp)
            pnl_usd = float(
                compute_pnl(idea.direction.value, pos.entry_price, cp, pos.notional)
            )
            if entry:
                pnl_pct = float((cp - pos.entry_price) / pos.entry_price * 100)

        feed.append({
            "telegram_user_id": user.telegram_user_id,
            "display_name": user.display_name,
            "initials": _initials(user.display_name),
            "color": _color(user.id),
            "photo_url": _proxy_photo_url(user),
            "ticker": idea.ticker,
            "company_name": idea.company_name or idea.ticker,
            "direction": idea.direction.value if idea.direction else None,
            "entry_price": entry,
            "current_price": current,
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "status": idea.status.value,
            "raw_text": (idea.raw_text or "")[:120],
            "submitted_at": idea.submitted_at.isoformat() if idea.submitted_at else None,
        })

    return {"users": users, "feed": feed}


@router.get("/data/user/{telegram_user_id}")
async def user_data(telegram_user_id: str) -> dict[str, Any]:
    """Returns one user's full equity curve and idea history."""
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.telegram_user_id == telegram_user_id)
            )
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        curve_rows = (
            await session.execute(
                select(DailyEquity)
                .where(DailyEquity.user_id == user.id)
                .order_by(DailyEquity.date.asc())
            )
        ).scalars().all()

        win_row = (
            await session.execute(
                select(
                    func.count(Position.id).label("total"),
                    func.sum(case((Position.pnl > 0, 1), else_=0)).label("winners"),
                )
                .join(Idea, Idea.id == Position.idea_id)
                .where(
                    Idea.user_id == user.id,
                    Position.status == PositionStatus.closed,
                )
            )
        ).one()
        total = int(win_row.total or 0)
        wins = int(win_row.winners or 0)

        latest_eq = (
            await session.execute(
                select(DailyEquity)
                .where(DailyEquity.user_id == user.id)
                .order_by(DailyEquity.date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        current_pnl = float(latest_eq.cumulative_pnl) if latest_eq else 0.0

        idea_rows = (
            await session.execute(
                select(Idea)
                .where(
                    Idea.user_id == user.id,
                    Idea.status.in_([IdeaStatus.open, IdeaStatus.closed]),
                )
                .options(selectinload(Idea.position))
                .order_by(Idea.submitted_at.desc())
                .limit(50)
            )
        ).scalars().all()

        streak = 0
        for idea in idea_rows:
            if (
                idea.status == IdeaStatus.closed
                and idea.position
                and idea.position.pnl is not None
            ):
                if idea.position.pnl > 0:
                    streak += 1
                else:
                    break

        open_tickers = {
            i.ticker for i in idea_rows if i.status == IdeaStatus.open and i.ticker
        }
        cached_prices: dict[str, Decimal] = {}
        if open_tickers:
            for pt in (
                await session.execute(
                    select(PriceTick)
                    .where(PriceTick.ticker.in_(open_tickers))
                    .order_by(PriceTick.date.desc())
                )
            ).scalars().all():
                if pt.ticker not in cached_prices:
                    cached_prices[pt.ticker] = pt.price

    ideas_out = []
    for idea in idea_rows:
        pos = idea.position
        entry = float(pos.entry_price) if pos else None
        current = pnl_usd = pnl_pct = None

        if idea.status == IdeaStatus.closed and pos and pos.pnl is not None:
            current = float(pos.exit_price) if pos.exit_price else None
            pnl_usd = float(pos.pnl)
            if entry and pos.exit_price:
                pnl_pct = float(
                    (pos.exit_price - pos.entry_price) / pos.entry_price * 100
                )
        elif idea.status == IdeaStatus.open and pos and idea.ticker in cached_prices:
            cp = cached_prices[idea.ticker]
            current = float(cp)
            pnl_usd = float(
                compute_pnl(idea.direction.value, pos.entry_price, cp, pos.notional)
            )
            if entry:
                pnl_pct = float((cp - pos.entry_price) / pos.entry_price * 100)

        ideas_out.append({
            "ticker": idea.ticker,
            "company_name": idea.company_name or idea.ticker,
            "direction": idea.direction.value if idea.direction else None,
            "entry_price": entry,
            "current_price": current,
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "status": idea.status.value,
            "raw_text": (idea.raw_text or "")[:120],
            "submitted_at": idea.submitted_at.date().isoformat() if idea.submitted_at else None,
        })

    return {
        "telegram_user_id": user.telegram_user_id,
        "display_name": user.display_name,
        "username": user.username,
        "initials": _initials(user.display_name),
        "color": _color(user.id),
        "photo_url": _proxy_photo_url(user),
        "pnl": current_pnl,
        "win_rate": round(wins / total, 4) if total else 0.0,
        "streak": streak,
        "idea_count": total,
        "equity_curve": [
            {"date": str(r.date), "equity": float(r.cumulative_pnl)}
            for r in curve_rows
        ],
        "ideas": ideas_out,
    }
