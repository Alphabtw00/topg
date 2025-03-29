"""
Event handlers for the Discord bot
"""
import sys
import re
import asyncio
import discord
from bot.crypto_bot import CryptoBot
from handlers.message_processor import process_message_with_timeout
from handlers.forwarding_handler import forward_message
from utils.auto_message_settings import should_process_channel
from utils.logger import get_logger
from config import FORWARD_GUILD_IDS
from datetime import datetime

logger = get_logger()
_bot = None


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

    if not message.guild:
        return

    if message.guild.id in FORWARD_GUILD_IDS:
        asyncio.create_task(forward_message(message, _bot))

    # Skip further processing for bot messages
    if message.author.bot:
        return
    
    if not await should_process_channel(message.guild.id, message.channel.id):
        return
        
    content = message.content
    # Quick check if the message might contain anything we need to process
    if '$' not in content and not re.search(r'[a-zA-Z0-9]{26,}', content):
        return
       
    # # Check for prefix commands
    # first_word = message.content.split()[0] if message.content else ''
    # if first_word in PREFIX_COMMANDS:
    #     # Process prefix commands when needed
    #     return
    
    asyncio.create_task(process_message_with_timeout(message))

async def on_error(event, *args, **kwargs):
    """
    Optimized error handler with better context retention
   
    Args:
        event: The event that raised the exception
        *args: Event arguments
        **kwargs: Event keyword arguments
    """
    error = sys.exc_info()
    
    # More detailed error context for message-related errors
    if event == 'on_message' and args:
        try:
            message = args[0]
            error_context = {
                'guild_id': message.guild.id if message.guild else None,
                'channel_id': message.channel.id if message.channel else None,
                'user_id': message.author.id if message.author else None,
                'message_length': len(message.content) if message.content else 0,
                'error_time': datetime.now().isoformat()
            }
            logger.error(f"Error in {event}: {error} | Context: {error_context}")
        except Exception:
            logger.error(f"Error in {event}: {error}")
    else:
        logger.error(f"Unhandled error in {event}: {error}")
    
    try:
        # Record error using the existing method
        _bot.increment_error_count(f"event_{event}")

    except Exception:
        # Don't let error tracking cause more errors
        pass

async def on_disconnect():
    """Enhanced disconnect handler with intelligent reconnection"""
    logger.warning("Bot disconnected from Discord. Attempting to reconnect...")
    try:
        # Check if still disconnected after a short delay
        await asyncio.sleep(5)
        
        bot = _bot
        if bot and not bot.is_closed():
            logger.info("Bot automatically reconnected")
            return
            
        # If still disconnected, start reconnection monitor
        logger.warning("Bot still disconnected after 5s, starting monitor")
        bot.loop.create_task(bot._monitor_reconnection(), name="reconnection_monitor")
    except Exception as e:
        logger.error(f"Failed to start reconnection monitor: {e}")
    
async def on_resumed():
    """Enhanced handler for reconnection events"""
    logger.info("Reconnected to Discord after disconnection")
    
    # Run health checks after reconnection
    try:
        bot = _bot
        if bot:
            # Check database connection
            from handlers.mysql_handler import fetch_one
            db_result = await fetch_one("SELECT 1")
            
            # Check HTTP client
            http_healthy = bot.http_session and not bot.http_session.closed
            
            # Log reconnection health status
            logger.info(f"Post-reconnection health check: Database={bool(db_result)}, HTTP={http_healthy}")
            
            # Attempt to repair any unhealthy connections
            if not http_healthy and bot.http_session.closed:
                from api.http_client import setup_http_session
                try:
                    bot.http_session = await setup_http_session()
                    logger.info("Successfully recreated HTTP session after reconnection")
                except Exception as e:
                    logger.error(f"Failed to recreate HTTP session: {e}")
    except Exception as e:
        logger.error(f"Error in post-reconnection health check: {e}")

async def on_socket_response(payload):
    """Enhanced socket response handler with better insights"""
    op_code = payload.get('op')
    
    # Only log important operation codes
    if op_code in [7, 9, 10, 11]:  # Reconnect, Invalid Session, Hello, Heartbeat ACK
        op_names = {
            7: "RECONNECT", 
            9: "INVALID_SESSION", 
            10: "HELLO", 
            11: "HEARTBEAT_ACK"
        }
        op_name = op_names.get(op_code, str(op_code))
        
        # Log with appropriate severity
        if op_code == 9:  # Invalid session is critical
            logger.error(f"Discord socket: {op_name} - Session invalidated")
        elif op_code == 7:  # Reconnect is warning
            logger.warning(f"Discord socket: {op_name} - Reconnection requested")
        else:
            logger.debug(f"Discord socket: {op_name}")
            
        # Take action on critical events
        if op_code == 9:  # Invalid session
            try:
                bot = _bot
                if bot:
                    # Force reconnection
                    logger.info("Attempting to force reconnection due to invalid session")
                    bot.loop.create_task(bot.attempt_reconnect())
            except Exception as e:
                logger.error(f"Error handling invalid session: {e}")