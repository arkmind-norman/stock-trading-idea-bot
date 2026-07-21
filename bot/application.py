from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.handlers import handle_leaderboard, handle_myideas, log_group_message
from db.config import settings


def build_application() -> Application:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Receive all plain-text messages in groups so we can detect trade ideas.
    # Requires Group Privacy to be DISABLED in @BotFather.
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND,
            log_group_message,
        )
    )

    # /leaderboard — ranked P&L table for all participants
    app.add_handler(CommandHandler("leaderboard", handle_leaderboard))

    # /myideas — the caller's open and recently-closed positions
    app.add_handler(CommandHandler("myideas", handle_myideas))

    return app


# Module-level singleton — no network call until application.initialize().
application = build_application()
