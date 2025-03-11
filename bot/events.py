"""
Event handlers for the Discord bot
"""
import sys
import asyncio
import discord
from bot.crypto_bot import CryptoBot
from config import TARGET_CHANNEL_IDS, PREFIX_COMMANDS
from handlers.message_processor import process_message
from utils.logger import get_logger

logger = get_logger()

# Semaphore for limiting concurrent message processing
# This is defined at module level for global access
processing_semaphore = asyncio.Semaphore(5)  # Adjust based on config if needed

async def setup_events(bot: CryptoBot):
    """
    Register all event handlers for the bot
    
    Args:
        bot: The Discord bot instance
    """
    # Register message handler
    bot.add_listener(on_message, "on_message")
    
    # Register error handlers
    bot.add_listener(on_error, "on_error")
    bot.add_listener(on_disconnect, "on_disconnect")
    
    logger.info("Event handlers registered")

async def on_message(message: discord.Message):
    """
    Handle incoming messages
    
    Args:
        message: The Discord message
    """
    # Ignore bot messages and messages from non-targeted channels
    if message.author.bot or (TARGET_CHANNEL_IDS and message.channel.id not in TARGET_CHANNEL_IDS):
        return
    
    # Check for prefix commands
    first_word = message.content.split()[0] if message.content else ''
    if first_word in PREFIX_COMMANDS:
        # Process prefix commands when needed
        # await bot.process_commands(message)
        return
    
    # Process the message for crypto addresses and tickers
    async with processing_semaphore:
        try:
            await process_message(message)
        except Exception as e:
            logger.error(f"Message processing error: {e}")

async def on_error(event, *args, **kwargs):
    """
    Handle Discord events that raise exceptions
    
    Args:
        event: The event that raised the exception
        *args: Event arguments
        **kwargs: Event keyword arguments
    """
    if event == 'on_message':
        logger.error(f"Error in {event}: {sys.exc_info()}")
    else:
        logger.error(f"Unhandled error in {event}: {sys.exc_info()}")

async def on_disconnect():
    """Handle bot disconnection events"""
    logger.warning("Bot disconnected from Discord. Attempting to reconnect...")