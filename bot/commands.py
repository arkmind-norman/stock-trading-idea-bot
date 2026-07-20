async def leaderboard_command(chat_id: int) -> str:
    """
    /leaderboard — returns a formatted ranking of all users by cumulative P&L.

    TODO: query daily_equity for the latest date per user, sort, format as text.
    """
    raise NotImplementedError


async def myideas_command(telegram_user_id: str, chat_id: int) -> str:
    """
    /myideas — returns a summary of the calling user's open and closed positions.

    TODO: query ideas + positions for this user, format as text.
    """
    raise NotImplementedError
