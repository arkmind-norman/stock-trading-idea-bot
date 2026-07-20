from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    """Normalised view of a Telegram message — used by future trade-idea processing."""
    telegram_user_id: str
    username: Optional[str]
    display_name: str
    text: str
    message_id: int
    timestamp: datetime
    chat_id: int


# typing import needed for Optional in dataclass on Py 3.9
from typing import Optional  # noqa: E402


async def log_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler attached to every text message in a group/supergroup.
    Logs sender + text so we can confirm reception before adding trade-idea logic.
    """
    msg = update.message
    if not msg or not msg.text:
        return

    user = msg.from_user
    logger.info(
        "group_message | user_id=%s username=%s name=%r | chat_id=%s | msg_id=%s | ts=%s | text=%r",
        user.id if user else "?",
        f"@{user.username}" if (user and user.username) else "(no username)",
        user.full_name if user else "?",
        msg.chat_id,
        msg.message_id,
        msg.date.isoformat(),
        msg.text,
    )
