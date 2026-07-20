from dataclasses import dataclass
from datetime import datetime


@dataclass
class IncomingMessage:
    telegram_user_id: str
    username: str | None
    display_name: str
    text: str
    message_id: int
    timestamp: datetime
    chat_id: int


async def handle_message(msg: IncomingMessage) -> str | None:
    """
    Main entry point for every group message.

    Returns an optional reply string to send back to the chat, or None if
    the message is not a trade idea (most messages will return None).

    TODO:
    1. Pass msg.text to llm.classify_and_extract()
    2. If not a trade idea → return None
    3. If ambiguous → return clarification question
    4. If valid idea → call simulator.engine.open_position() and return confirmation
    """
    raise NotImplementedError
