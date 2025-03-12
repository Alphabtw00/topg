"""
Event handlers for the Discord bot
"""
import sys
import asyncio
import discord
from bot.crypto_bot import CryptoBot
from config import TARGET_CHANNEL_IDS, PREFIX_COMMANDS, INPUT_CHANNEL_IDS, OUTPUT_CHANNEL_IDS
from handlers.message_processor import process_message
from utils.logger import get_logger

logger = get_logger()
_bot = None

# Semaphore for limiting concurrent message processing
# This is defined at module level for global access
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
    
    logger.info("Event handlers registered")

async def on_message(message: discord.Message):
    """
    Handle incoming messages
    
    Args:
        message: The Discord message
    """
    if INPUT_CHANNEL_IDS and message.channel.id in INPUT_CHANNEL_IDS:
        await forward_message(message, _bot)

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
            # Create a task with timeout
            task = asyncio.create_task(process_message(message))
            await asyncio.wait_for(task, timeout=10.0)  # 10-second timeout
        except asyncio.TimeoutError:
            logger.warning(f"Message processing timed out for message {message.id}")
        except Exception as e:
            logger.error(f"Message processing error: {e}")
            try:
                await message.reply(
                    "Processing timed due to too many inputs or high volume of users."
                    "Only partial results may be displayed.",
                    
                    delete_after=10
                )
            except Exception as e:
                logger.error(f"Failed to send timeout notification: {e}")
            
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

async def on_resumed():
    """Called when the bot reconnects to Discord after disconnection"""
    logger.info("Reconnected to Discord after disconnection")

async def on_socket_response(payload):
    """Monitor socket responses for connection issues"""
    if payload.get('op') == 9:  # Invalid session
        logger.error("Invalid session detected")
    elif payload.get('op') == 7:  # Reconnect
        logger.warning("Discord requested reconnection")

async def forward_message(message: discord.Message, bot: CryptoBot):
    """
    Forward a message from input channels to all output channels
    
    Args:
        message: The Discord message to forward
        bot: The bot instance
    """
    try:
        # Skip forwarding if no output channels are configured
        if not OUTPUT_CHANNEL_IDS:
            return
            
        # Get source channel name
        source_channel_name = message.channel.name if hasattr(message.channel, 'name') else f"Channel {message.channel.id}"
        
        # Forward to all output channels
        for channel_id in OUTPUT_CHANNEL_IDS:
            try:
                channel = bot.get_channel(channel_id)
                if not channel:
                    logger.warning(f"Could not find output channel with ID {channel_id}")
                    continue
                
                # If message has embeds, forward them with modified footer
                if message.embeds:
                    for embed in message.embeds:
                        # Create a copy of the embed
                        new_embed = embed.copy()
                        
                        # Update the footer with source channel info
                        footer_text = f"Called in #{source_channel_name}"
                        if new_embed.footer.text:
                            footer_text = f"{new_embed.footer.text} | {footer_text}"
                        
                        new_embed.set_footer(text=footer_text, icon_url=new_embed.footer.icon_url)
                        await channel.send(embed=new_embed)
                else:
                    # Forward regular text messages
                    await channel.send(content=message.content, files=[await a.to_file() for a in message.attachments])
                
            except Exception as e:
                logger.error(f"Failed to forward message to channel {channel_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error forwarding message: {e}")