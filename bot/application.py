from telegram.ext import Application, MessageHandler, filters

from bot.handlers import log_group_message
from db.config import settings


def build_application() -> Application:
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Catch all plain-text messages in groups and supergroups.
    # Requires Group Privacy to be DISABLED in @BotFather so the bot
    # receives messages that aren't directed at it with a / command.
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.GROUPS,
            log_group_message,
        )
    )

    return app


# Module-level singleton.
# Application.builder().build() is cheap — no network call yet.
# The actual connection to Telegram happens in application.initialize()
# which is called from the FastAPI lifespan on startup.
application = build_application()
