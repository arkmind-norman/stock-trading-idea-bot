from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from bot.commands import leaderboard_command, myideas_command
from bot.llm import classify_and_extract
from db.database import AsyncSessionLocal
from db.models import Direction, Idea, IdeaStatus, User
from simulator.daily_job import snapshot_user_equity
from simulator.engine import open_position
from simulator.market_data import resolve_ticker

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.50


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_or_create_user(
    session,
    telegram_user_id: str,
    username: Optional[str],
    display_name: str,
) -> User:
    user = (
        await session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
    ).scalar_one_or_none()

    if user is None:
        user = User(
            telegram_user_id=telegram_user_id,
            username=username,
            display_name=display_name,
        )
        session.add(user)
    else:
        user.username = username
        user.display_name = display_name

    return user


# ── Group message handler — the core pipeline ─────────────────────────────────

async def log_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return

    tg_user = msg.from_user
    if not tg_user or tg_user.is_bot:
        return

    text = msg.text

    logger.info(
        "group_message | user=%s | chat=%s | msg=%s | text=%r",
        tg_user.id, msg.chat_id, msg.message_id, text,
    )

    # ── Step 1: typing indicator while LLM runs ───────────────────────────────
    await context.bot.send_chat_action(chat_id=msg.chat_id, action="typing")

    # ── Step 2: LLM classify + extract ───────────────────────────────────────
    try:
        trade_idea = await classify_and_extract(text)
    except Exception:
        logger.exception("LLM call failed for msg %s", msg.message_id)
        return

    if trade_idea is None:
        return  # banter — do nothing

    logger.info(
        "trade_idea detected | ticker=%s dir=%s conf=%.2f target=%s stop=%s",
        trade_idea.ticker, trade_idea.direction, trade_idea.confidence,
        trade_idea.target_price, trade_idea.stop_price,
    )

    if trade_idea.confidence < _CONFIDENCE_THRESHOLD:
        await msg.reply_text(
            f"Did you mean to suggest a {trade_idea.direction} trade on "
            f"{trade_idea.ticker}? Reply with a clearer message and I'll track it!"
        )
        return

    # ── Step 3: Resolve ticker (US → Bursa Malaysia fallback via live search) ──
    resolved = await resolve_ticker(trade_idea.ticker, company_name=trade_idea.company_name)
    if resolved is None:
        await msg.reply_text(
            f"Couldn't find a price feed for <b>{trade_idea.ticker}</b> on any exchange. "
            f"Try using the official ticker symbol (e.g. AAPL, 0272.KL).",
            parse_mode="HTML",
        )
        return
    if resolved != trade_idea.ticker:
        logger.info(
            "ticker resolved: %s → %s (original msg=%r)",
            trade_idea.ticker, resolved, text,
        )
        trade_idea.ticker = resolved

    # ── Step 4: Instant acknowledgement — sends before price fetch ────────────
    arrow = "📈" if trade_idea.direction == "long" else "📉"
    mention = f"@{tg_user.username}" if tg_user.username else tg_user.full_name or str(tg_user.id)
    ack = await msg.reply_text(
        f"{arrow} <b>{trade_idea.ticker}</b> {trade_idea.direction.upper()} locked in for {mention} — fetching price...",
        parse_mode="HTML",
    )

    # ── Step 5: Persist user + idea ───────────────────────────────────────────
    submitted_at = msg.date.replace(tzinfo=None)
    display_name = tg_user.full_name or str(tg_user.id)

    async with AsyncSessionLocal() as session:
        db_user = await _get_or_create_user(
            session,
            telegram_user_id=str(tg_user.id),
            username=tg_user.username,
            display_name=display_name,
        )
        if db_user.first_idea_at is None:
            db_user.first_idea_at = submitted_at

        # Fetch profile photo on first encounter (best-effort)
        if db_user.photo_url is None:
            try:
                photos = await context.bot.get_user_profile_photos(tg_user.id, limit=1)
                if photos.total_count > 0:
                    pfile = await context.bot.get_file(photos.photos[0][-1].file_id)
                    url = pfile.file_path
                    if not url.startswith("http"):
                        url = f"https://api.telegram.org/file/bot{context.bot.token}/{url}"
                    db_user.photo_url = url
            except Exception:
                logger.warning("Could not fetch profile photo for user %s", tg_user.id)

        await session.flush()

        idea = Idea(
            user_id=db_user.id,
            raw_text=text,
            ticker=trade_idea.ticker,
            company_name=trade_idea.company_name,
            direction=Direction(trade_idea.direction),
            target_price=trade_idea.target_price,
            stop_price=trade_idea.stop_price,
            submitted_at=submitted_at,
            status=IdeaStatus.pending,
        )
        session.add(idea)
        await session.commit()
        idea_id = idea.id
        db_user_id = db_user.id

    # ── Step 6: Open the simulated position ───────────────────────────────────
    try:
        opened = await open_position(idea_id)
    except Exception:
        logger.exception("open_position failed for idea %d", idea_id)
        await _mark_idea_rejected(idea_id)
        await ack.edit_text(
            f"⚠️ Spotted a <b>{trade_idea.direction.upper()}</b> on <b>{trade_idea.ticker}</b> "
            f"but couldn't fetch the market price right now. Try again later!",
            parse_mode="HTML",
        )
        return

    try:
        await snapshot_user_equity(db_user_id)
    except Exception:
        logger.warning("snapshot_user_equity failed for user %d — leaderboard will update at EOD", db_user_id)

    # ── Step 7: Edit ack with full trade confirmation ─────────────────────────
    lines = [
        f"{arrow} Opened simulated <b>{opened.direction.upper()}</b> on "
        f"<b>{opened.ticker}</b> @ <b>${float(opened.entry_price):,.2f}</b> for {mention}.",
        f"Notional: $1,000 · {float(opened.shares):.4f} shares",
    ]
    extras = []
    if trade_idea.target_price:
        extras.append(f"Target ${trade_idea.target_price:,.2f}")
    if trade_idea.stop_price:
        extras.append(f"Stop ${trade_idea.stop_price:,.2f}")
    if extras:
        lines.append(" · ".join(extras))

    await ack.edit_text("\n".join(lines), parse_mode="HTML")


async def _mark_idea_rejected(idea_id: int) -> None:
    async with AsyncSessionLocal() as session:
        idea = await session.get(Idea, idea_id)
        if idea:
            idea.status = IdeaStatus.rejected
            await session.commit()


# ── Command handlers ──────────────────────────────────────────────────────────

async def handle_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply = await leaderboard_command()
    await update.message.reply_text(reply, parse_mode="HTML")


async def handle_myideas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.message.from_user
    if not tg_user:
        return
    reply = await myideas_command(str(tg_user.id))
    await update.message.reply_text(reply, parse_mode="HTML")
