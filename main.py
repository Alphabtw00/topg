"""
TopG Crypto Discord Bot - Entry Point
"""
import logging
import asyncio
from bot.crypto_bot import CryptoBot
from config import TOKEN, INTENTS
from utils.logger import setup_logger
from bot.error_handler import global_exception_handler

# Initialize logger
logger = setup_logger()

async def main():
    """Main entry point for the bot"""
    bot = None
    try:
        logger.info("Starting bot...")
        asyncio.get_running_loop().set_exception_handler(global_exception_handler)
        bot = CryptoBot(command_prefix="!", intents=INTENTS, help_command=None)
        await bot.start(TOKEN)
        if bot.shutdown_in_progress:
            logger.info("Bot shutting down due to initialization failure")
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        exit(1)
    finally:
        if bot:
            await bot.close()
            
if __name__ == "__main__":
    try:
        # Use asyncio.run() in Python 3.7+
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        exit(1)