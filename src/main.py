"""Main application entry point for OZON BI system."""

import asyncio
import logging
import sys

from telegram.ext import Application

from src.bot.app import create_bot_application
from src.config import settings
from src.scheduler.jobs import setup_scheduler

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, settings.log_level.upper()),
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("ozon-bi.log"),
    ],
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """Main application entry point."""
    logger.info("Starting OZON BI System")
    logger.info(f"Timezone: {settings.timezone}")
    logger.info(f"Log level: {settings.log_level}")

    # Create Telegram bot application
    app = create_bot_application()

    # Set up scheduler
    scheduler = setup_scheduler(app)

    try:
        # Initialize application
        await app.initialize()
        logger.info("Telegram bot initialized")

        # Start scheduler
        scheduler.start()
        logger.info("Job scheduler started")

        # Start bot
        await app.start()
        logger.info("Telegram bot started")

        # Start polling
        logger.info("Starting polling...")
        await app.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )

        # Keep running until interrupted
        logger.info("OZON BI System is running. Press Ctrl+C to stop.")

        # Run forever
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutdown signal received")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise

    finally:
        # Cleanup
        logger.info("Shutting down...")

        # Stop scheduler
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler stopped")

        # Stop bot
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("Telegram bot stopped")

        logger.info("OZON BI System stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application failed: {e}", exc_info=True)
        sys.exit(1)
