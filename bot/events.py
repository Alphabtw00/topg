# bot/events.py
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
from service.auto_message_settings import should_process_channel
from handlers.username_ban import check_username, ban_user  # Correct import path
from utils.logger import get_logger
from config import (
    FORWARD_GUILD_IDS,
    USERNAME_BAN_SERVER_ID
)
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
    
    # Register username ban handlers
    bot.add_listener(on_member_join, "on_member_join")
    bot.add_listener(on_member_update, "on_member_update")
    bot.add_listener(on_user_update, "on_user_update")
    
    # Register error handlers
    bot.add_listener(on_error, "on_error")
    bot.add_listener(on_disconnect, "on_disconnect")
    bot.add_listener(on_resumed, "on_resumed")
    bot.add_listener(on_socket_response, "on_socket_response")
    
    logger.info(f"Discord Events Registered | Username Ban Server ID: {USERNAME_BAN_SERVER_ID}")

async def on_message(message: discord.Message):
    """
    Handle incoming messages
    
    Args:
        message: The Discord message
    """

    if not message.guild:
        return

    # if message.guild.id in FORWARD_GUILD_IDS:
    #     asyncio.create_task(forward_message(message, _bot))

    # Skip further processing for bot messages
    if message.author.bot:
        return
    
    # if await should_send_fudded_reply(message):
    #     from config import FIGHT_BACK_GIF_URL
    #     await message.reply(f"{FIGHT_BACK_GIF_URL}")
    
    if not await should_process_channel(message.guild.id, message.channel.id):
        return
        
    content = message.content
    # Quick check if the message might contain anything we need to process
    if '$' not in content and not re.search(r'[a-zA-Z0-9]{26,}', content):
        return
    
    asyncio.create_task(process_message_with_timeout(message))


async def should_send_fudded_reply(message: discord.Message) -> bool:
    """
    Check if we should reply with the fudded message
    
    Args:
        message: The Discord message
    
    Returns:
        bool: True if we should reply with the fudded message
    """
    # Replace these with the actual user IDs and channel IDs you want to target
    TARGET_USER_IDS = [581470835898974208]  # Add the user IDs you want to target
    TARGET_CHANNEL_IDS = [1330987514059554907]  # Add the channel IDs you want to monitor
    
    return (
        message.author.id in TARGET_USER_IDS and 
        message.channel.id in TARGET_CHANNEL_IDS
    )

async def on_member_join(member):
    """
    Handle new member joins - check usernames against banned patterns
    
    Args:
        member: The Discord member who joined
    """
    logger.debug(f"Member joined: {member.id} ({str(member)}) in guild {member.guild.id}")
    
    # Only check for the specified server
    if not USERNAME_BAN_SERVER_ID:
        logger.debug(f"USERNAME_BAN_SERVER_ID not configured, skipping ban check for {member.id}")
        return
        
    if member.guild.id != USERNAME_BAN_SERVER_ID:
        logger.debug(f"Member {member.id} joined guild {member.guild.id}, not ban server {USERNAME_BAN_SERVER_ID}")
        return
    
    # Check username against patterns
    should_ban, reason = await check_username(member)
    
    if should_ban:
        ban_result = await ban_user(_bot, member, reason)
        logger.debug(f"Ban result for {member.id}: {ban_result}")
    else:
        logger.debug(f"Member {member.id} ({str(member)}) passed username check")

async def on_member_update(before, after):
    """
    Handle member updates for nickname/display name changes
    
    Args:
        before: The member before the update
        after: The member after the update
    """
    # Only check for the specified server
    if not USERNAME_BAN_SERVER_ID:
        return
        
    if after.guild.id != USERNAME_BAN_SERVER_ID:
        return
    
    # Log name changes to debug level
    if before.display_name != after.display_name or before.nick != after.nick:
        logger.debug(f"Name change detected - User: {after.id} ({str(after)}) | Before: {before.display_name} | After: {after.display_name}")

    # ALWAYS check the username when a member update occurs in the ban server
    should_ban, reason = await check_username(after)
    if should_ban:
        ban_result = await ban_user(_bot, after, reason)
        logger.debug(f"Ban result for {after.id}: {ban_result}")

async def on_user_update(before, after):
    """
    Handle global username changes
    
    Args:
        before: The user before the update
        after: The user after the update
    """
    # Only if username changed
    if str(before) == str(after):
        return
    
    # We only need to check in our specific server
    if not USERNAME_BAN_SERVER_ID:
        return
    
    logger.debug(f"User {after.id} changed username from {str(before)} to {str(after)}")
        
    # Get our specific server
    bot = _bot
    if not bot:
        logger.warning("Bot instance not available for user_update check")
        return
        
    # Check if the user is in our server
    guild = bot.get_guild(USERNAME_BAN_SERVER_ID)
    if not guild:
        return
        
    member = guild.get_member(after.id)
    if member:
        should_ban, reason = await check_username(member)
        if should_ban:
            ban_result = await ban_user(bot, member, reason)
            logger.debug(f"Ban result for {after.id}: {ban_result}")
    else:
        logger.debug(f"User {after.id} not found in ban server {USERNAME_BAN_SERVER_ID}")

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
            
            # Check Api client
            api_client_healthy = (hasattr(bot, 'services') and 
                               bot.services and 
                               bot.services.api_client and 
                               not bot.services.api_client.session.closed)
            
            # Log reconnection health status
            logger.info(f"Post-reconnection health check: Database={bool(db_result)}, API Client={api_client_healthy}")
            
            # Attempt to repair any unhealthy connections
            if not api_client_healthy and hasattr(bot, 'services'):
                try:
                    await bot.services.api_client.setup()
                    logger.info("Successfully recreated API client after reconnection")
                except Exception as e:
                    logger.error(f"Failed to recreate API client: {e}")
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