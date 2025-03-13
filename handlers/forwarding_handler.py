"""
Message forwarding system that handles different forwarding configurations
"""
import discord
import asyncio
from datetime import datetime
from utils.logger import get_logger
from utils.validators import get_addresses_from_content, get_tickers_from_content
from handlers.message_processor import process_message

logger = get_logger()

async def forward_bot_messages(message, bot):
    """
    Forward messages from specified bots in input channels to output channels
    
    Args:
        message: Discord message
        bot: Bot instance
    """
    from config import BOT_INPUT_CHANNEL_IDS, BOT_OUTPUT_CHANNEL_IDS, FORWARD_BOT_IDS, BOT_CHANNEL_COLORS
    
    # Skip if configuration is incomplete
    if not BOT_OUTPUT_CHANNEL_IDS:
        return
        
    # Check if message is in an input channel (if specified)
    if BOT_INPUT_CHANNEL_IDS and message.channel.id not in BOT_INPUT_CHANNEL_IDS:
        return
        
    # Skip if not from a bot
    if not message.author.bot:
        return
        
    # If FORWARD_BOT_IDS is set, filter by author ID
    if FORWARD_BOT_IDS and message.author.id not in FORWARD_BOT_IDS:
        return
    
    # Get source channel info for footer
    source_channel_name = message.channel.name if hasattr(message.channel, 'name') else f"Channel {message.channel.id}"
    
    # Get color for this channel
    embed_color = BOT_CHANNEL_COLORS.get(message.channel.id, 0x3498db)
    
    # Forward to all output channels
    for channel_id in BOT_OUTPUT_CHANNEL_IDS:
        try:
            channel = bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"Could not find output channel with ID {channel_id}")
                continue
            
            # Handle embeds
            if message.embeds:
                for embed in message.embeds:
                    # Create a copy of the embed
                    new_embed = embed.copy()
                    
                    # Set color based on source channel
                    new_embed.color = embed_color
                    
                    # Update footer with source channel info
                    footer_text = f"Called in: #{source_channel_name}"
                    if new_embed.footer and new_embed.footer.text:
                        footer_text = f"{new_embed.footer.text} | {footer_text}"
                    
                    new_embed.set_footer(text=footer_text, icon_url=new_embed.footer.icon_url if new_embed.footer else None)
                    await channel.send(embed=new_embed)
            else:
                # Create a new embed for text messages for consistent styling
                if message.content:
                    embed = discord.Embed(
                        description=message.content,
                        color=embed_color
                    )
                    embed.set_footer(text=f"From #{source_channel_name}")
                    
                    # Set author info if possible
                    if hasattr(message.author, 'name') and hasattr(message.author, 'display_avatar'):
                        embed.set_author(
                            name=message.author.name,
                            icon_url=message.author.display_avatar.url
                        )
                    
                    await channel.send(embed=embed)
                
                # Send any attachments
                if message.attachments:
                    files = [await attachment.to_file() for attachment in message.attachments]
                    await channel.send(files=files)
            
        except Exception as e:
            logger.error(f"Failed to forward bot message to channel {channel_id}: {e}")

async def forward_user_messages(message, bot):
    """
    Forward messages from specified users to output channels
    
    Args:
        message: Discord message
        bot: Bot instance
    """
    from config import USER_INPUT_CHANNEL_IDS, USER_OUTPUT_CHANNEL_IDS, FORWARD_USER_IDS, PROCESS_CRYPTO_IN_FORWARDS
    
    # Skip if configuration is incomplete
    if not USER_OUTPUT_CHANNEL_IDS:
        return
    
    # Skip if from a bot
    if message.author.bot:
        return
        
    # Check if message is in an input channel (if specified)
    if USER_INPUT_CHANNEL_IDS and message.channel.id not in USER_INPUT_CHANNEL_IDS:
        return
        
    # If FORWARD_USER_IDS is set, filter by author ID
    if FORWARD_USER_IDS and message.author.id not in FORWARD_USER_IDS:
        return
    
    # Get source info for attribution
    source_info = f"#{message.channel.name}" if hasattr(message.channel, 'name') else f"Channel {message.channel.id}"
    if hasattr(message.guild, 'name'):
        source_info = f"{source_info} in {message.guild.name}"
    
    # Forward to all output channels
    for channel_id in USER_OUTPUT_CHANNEL_IDS:
        try:
            channel = bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"Could not find output channel with ID {channel_id}")
                continue
            
            # Create webhook for user-like messages
            webhooks = await channel.webhooks()
            webhook = next((w for w in webhooks if w.user and w.user.id == bot.user.id), None)
            
            if not webhook:
                webhook = await channel.create_webhook(name=f"{bot.user.name} Forwarding")
            
            # Build webhook parameters
            webhook_params = {
                'content': message.content or None,
                'username': message.author.display_name,
                'avatar_url': message.author.display_avatar.url,
                'embeds': message.embeds,
                'wait': True
            }
            
            # Add attachments if present
            if message.attachments:
                webhook_params['files'] = [await a.to_file() for a in message.attachments]
            
            # Send the message
            sent_message = await webhook.send(**webhook_params)
            
            # Process for crypto addresses if requested
            if PROCESS_CRYPTO_IN_FORWARDS and message.content:
                addresses = get_addresses_from_content(message.content)
                tickers = get_tickers_from_content(message.content)
                
                if addresses or tickers:                    
                    try:
                        # Process it through the normal flow
                        await process_message(message, bot, reply_to=sent_message)
                        
                    except Exception as e:
                        logger.error(f"Error processing crypto in forwarded message: {e}")
                        await sent_message.reply("⚠️ Error analyzing crypto content", mention_author=False)
                
        except Exception as e:
            logger.error(f"Failed to forward user message to channel {channel_id}: {e}")

async def process_message(message, bot, reply_to=None):
    """
    Process a message for crypto addresses and tickers
    
    Args:
        message: Original message with content to analyze
        bot: Bot instance
        reply_to: Optional message to update with results, otherwise replies to original
    """
    from handlers.address_handler import process_addresses
    from handlers.ticker_handler import process_tickers
    
    # Extract addresses and tickers
    content = message.content
    addresses = get_addresses_from_content(content)
    tickers = get_tickers_from_content(content)
    
    if not addresses and not tickers:
        return
    
    # Process in parallel
    tasks = []
    target_message = reply_to or message
    
    if addresses:
        tasks.append(process_addresses(target_message, bot.http_session, addresses))
    
    if tickers:
        tasks.append(process_tickers(target_message, bot.http_session, tickers))
    
    # Run tasks
    if tasks:
        start_time = datetime.now().timestamp()
        await asyncio.gather(*tasks)
        
        # Record metrics
        processing_time = datetime.now().timestamp() - start_time
        bot.record_metric(processing_time)
        
async def forward_message(message, bot):
    """
    Main entry point for message forwarding - handles multiple forwarding configurations
    
    Args:
        message: Discord message
        bot: Bot instance
    """
    # First try the user forwarding config
    await forward_user_messages(message, bot)
    
    # Then try the bot forwarding config
    await forward_bot_messages(message, bot)