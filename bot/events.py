"""
Event handlers for the Discord bot
"""
import sys
import asyncio
import discord
from bot.crypto_bot import CryptoBot
from config import TARGET_CHANNEL_IDS, PREFIX_COMMANDS
from handlers.message_processor import process_message_with_timeout
from handlers.forwarding_handler import forward_message
from utils.logger import get_logger

logger = get_logger()
_bot = None

# Semaphore for limiting concurrent message processing
processing_semaphore = asyncio.Semaphore(5)  # Adjust based on config if needed

async def setup_events(bot: CryptoBot):
    """
    Register all event handlers for the bot
    
    Args:
        bot: The Discord bot instance
    """
    global _bot
    _bot = bot

    # Register message handler
    bot.add_listener(on_message, "on_message")
    
    # Register error handlers
    bot.add_listener(on_error, "on_error")
    bot.add_listener(on_disconnect, "on_disconnect")
    bot.add_listener(on_resumed, "on_resumed")
    bot.add_listener(on_socket_response, "on_socket_response")
    
    logger.info("Discord Events Registered")

async def on_message(message: discord.Message):
    """
    Handle incoming messages
    
    Args:
        message: The Discord message
    """
    # Try forwarding the message first
    asyncio.create_task(forward_message(message, _bot))

    # Skip further processing for bot messages
    if message.author.bot:
        return
    
    # Ignore messages from non-targeted channels
    if TARGET_CHANNEL_IDS and message.channel.id not in TARGET_CHANNEL_IDS:
        return
    
    content = message.content
    # Quick check if the message might contain anything we need to process
    if '$' not in content and not any(c.isalnum() for c in content[:min(20, len(content))]):
        return
    
    # # Check for prefix commands
    # first_word = message.content.split()[0] if message.content else ''
    # if first_word in PREFIX_COMMANDS:
    #     # Process prefix commands when needed
    #     return
    
    asyncio.create_task(process_message_with_timeout(message))

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
    _bot.loop.create_task(_bot._monitor_reconnection())

async def on_resumed():
    """Called when the bot reconnects to Discord after disconnection"""
    logger.info("Reconnected to Discord after disconnection")

async def on_socket_response(payload):
    """Monitor socket responses for connection issues"""
    if payload.get('op') == 9:  # Invalid session
        logger.error("Invalid session detected")
    elif payload.get('op') == 7:  # Reconnect
        logger.warning("Discord requested reconnection")