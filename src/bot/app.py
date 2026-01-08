"""Telegram bot application setup."""

import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.bot.handlers.callbacks import callback_query_handler
from src.bot.handlers.commands import (
    experiments_command,
    help_command,
    inventory_command,
    report_command,
    start_command,
)
from src.bot.handlers.messages import message_handler
from src.config import settings

logger = logging.getLogger(__name__)


def create_bot_application() -> Application:
    """Create and configure the Telegram bot application."""
    # Create application
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("inventory", inventory_command))
    app.add_handler(CommandHandler("experiments", experiments_command))

    # Add callback query handler (for inline buttons)
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # Add message handler (for AI assistant)
    # This should be last to catch all non-command messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Telegram bot application configured")

    return app
