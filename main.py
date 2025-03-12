"""
TopG Crypto Discord Bot - Entry Point
"""
import logging
import asyncio
from bot.crypto_bot import CryptoBot
from config import TOKEN, INTENTS
from utils.logger import setup_logger

# Initialize logger
logger = setup_logger()

async def main():
    """Main entry point for the bot"""
    try:
        logger.info("Starting bot...")
        bot = CryptoBot(command_prefix="!", intents=INTENTS, help_command=None)
        await bot.start(TOKEN)
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        exit(1)
    finally:
        if bot:
            await bot.close()
            # Add explicit database pool cleanup
            from handlers.mysql_handler import close_db_pool
            await close_db_pool()

if __name__ == "__main__":
    try:
        # Use asyncio.run() in Python 3.7+
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        exit(1)