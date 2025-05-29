import discord
import asyncio
import re
from datetime import datetime
from utils.logger import get_logger
from discord import AllowedMentions
from handlers.message_processor import process_message_with_timeout
from utils.validators import get_addresses_from_content
from functools import lru_cache
from utils.formatters import safe_text


logger = get_logger()

# Cache for webhooks to avoid repeated lookups
webhook_cache = {}

@lru_cache(maxsize=128)
def should_forward_bot_message(channel_id, author_id):
    """Fast filtering function for bot messages"""
    from config import BOT_INPUT_CHANNEL_IDS, FORWARD_BOT_IDS
    
    if BOT_INPUT_CHANNEL_IDS and channel_id not in BOT_INPUT_CHANNEL_IDS:
        return False
    if FORWARD_BOT_IDS and author_id not in FORWARD_BOT_IDS:
        return False
    return True

@lru_cache(maxsize=128)
def should_forward_user_message(channel_id, author_id):
    """Fast filtering function for user messages"""
    from config import USER_INPUT_CHANNEL_IDS, FORWARD_USER_IDS
    
    if USER_INPUT_CHANNEL_IDS and channel_id not in USER_INPUT_CHANNEL_IDS:
        return False
    if FORWARD_USER_IDS and author_id not in FORWARD_USER_IDS:
        return False
    return True

@lru_cache(maxsize=128)
def should_monitor_token_lock(channel_id, author_id):
    """Fast filtering function for token lock messages"""
    from config import TOKEN_LOCK_INPUT_CHANNEL_IDS, TOKEN_LOCK_BOT_IDS
    
    if TOKEN_LOCK_INPUT_CHANNEL_IDS and channel_id not in TOKEN_LOCK_INPUT_CHANNEL_IDS:
        return False
    if TOKEN_LOCK_BOT_IDS and author_id not in TOKEN_LOCK_BOT_IDS:
        return False
    return True

async def get_webhook_for_channel(channel, bot):
    """Get or create a webhook for the channel, with caching"""
    cache_key = channel.id
    
    if cache_key in webhook_cache:
        #verify webhook still valid
        try:
            await webhook_cache[cache_key].fetch()  
            return webhook_cache[cache_key]
        except discord.NotFound:
            # Webhook was deleted, remove from cache
            del webhook_cache[cache_key]
        except Exception:
            # Other error, just proceed to get a new webhook
            pass
    
    try:
        webhooks = await channel.webhooks()
        webhook = next((w for w in webhooks if w.user and w.user.id == bot.user.id), None)
        
        if not webhook:
            webhook = await channel.create_webhook(name=f"{bot.user.name} Forwarding")
        
        webhook_cache[cache_key] = webhook
        return webhook
    except Exception as e:
        logger.error(f"Failed to get webhook for channel {channel.id}: {e}")
        return None

async def forward_bot_messages(message, bot):
    """Forward messages from bots to output channels"""
    from config import BOT_OUTPUT_CHANNEL_IDS, BOT_CHANNEL_COLORS
    
    # Quick return for incomplete configuration
    if not BOT_OUTPUT_CHANNEL_IDS:
        return
    
    # Fast filtering using cached function
    if not should_forward_bot_message(message.channel.id, message.author.id):
        return
    
    # Prepare data once before sending to multiple channels
    source_channel_name = message.channel.name if hasattr(message.channel, 'name') else f"Channel {message.channel.id}"
    embed_color = BOT_CHANNEL_COLORS.get(message.channel.id, 0x3498db)
    
    # Prepare embeds ahead of time
    prepared_embeds = []
    if message.embeds:
        for embed in message.embeds:
            new_embed = embed.copy()
            new_embed.color = embed_color
            
            footer_text = f"Called in: #{source_channel_name}"
            if new_embed.footer and new_embed.footer.text:
                footer_text = f"{new_embed.footer.text} | {footer_text}"
            
            new_embed.set_footer(text=footer_text, icon_url=new_embed.footer.icon_url if new_embed.footer else None)
            prepared_embeds.append(new_embed)
    elif message.content:
        embed = discord.Embed(
            description=message.content,
            color=embed_color
        )
        embed.set_footer(text=f"From #{source_channel_name}")
        
        if hasattr(message.author, 'name') and hasattr(message.author, 'display_avatar'):
            embed.set_author(
                name=message.author.name,
                icon_url=message.author.display_avatar.url
            )
        
        prepared_embeds.append(embed)
    
    # Download attachments once if needed
    files = None
    if message.attachments:
        try:
            files = [await attachment.to_file() for attachment in message.attachments]
        except Exception as e:
            logger.error(f"Failed to download attachments: {e}")
    
    # Forward to all output channels concurrently
    tasks = []
    for channel_id in BOT_OUTPUT_CHANNEL_IDS:
        tasks.append(forward_bot_to_channel(
            channel_id, bot, prepared_embeds, 
            files.copy() if files else None
        ))
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def forward_bot_to_channel(channel_id, bot, embeds, files):
    """Helper to forward bot message to a specific channel"""
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            logger.warning(f"Could not find output channel with ID {channel_id}")
            return
        
        if embeds:
            await channel.send(embeds=embeds)
        
        if files:
            await channel.send(files=files)
            
    except Exception as e:
        logger.error(f"Failed to forward bot message to channel {channel_id}: {e}")

async def forward_user_messages(message, bot):
    """Forward user messages with optimized handling"""
    from config import USER_OUTPUT_CHANNEL_IDS, PROCESS_CRYPTO_IN_FORWARDS
    
    # Quick return for incomplete configuration
    if not USER_OUTPUT_CHANNEL_IDS:
        return
    
    # Fast filtering using cached function
    if not should_forward_user_message(message.channel.id, message.author.id):
        return
    
    crypto_detected = False
    content = message.content
    if PROCESS_CRYPTO_IN_FORWARDS and content:
        if ('$' in content or
            re.search(r'[a-zA-Z0-9]{26,}', content)): 
            crypto_detected = True


    # Prepare common webhook parameters once
    base_webhook_params = {
        'username': message.author.display_name,
        'avatar_url': message.author.display_avatar.url,
        'wait': True,
        'allowed_mentions': AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
        'suppress_embeds': False
    }
    
    # Get reference content upfront if needed
    quoted_content = ""
    reference_files = None
    reference_embeds = None
    
    if message.reference:
        try:
            reference_channel = bot.get_channel(message.reference.channel_id)
            if reference_channel:
                original_msg = await reference_channel.fetch_message(message.reference.message_id)
                is_reply = message.channel.id == message.reference.channel_id
                
                # Only include embeds/files for forwards, not replies
                if not is_reply:
                    if original_msg.embeds:
                        reference_embeds = original_msg.embeds
                    
                    if original_msg.attachments:
                        reference_files = [await a.to_file() for a in original_msg.attachments]
                
                # Add quoted content for both forwards and replies
                if original_msg.content:
                    lines = original_msg.content.split('\n')
                    quoted_content = '\n'.join([f"> {line}" for line in lines]) + '\n'
                    base_webhook_params['suppress_embeds'] = True
                
        except Exception as e:
            logger.warning(f"Could not fetch original message for forwarding: {e}")
    
    # Prepare content
    if content or quoted_content:
        base_webhook_params['content'] = (quoted_content or '') + (content or '')

    
    # Add message embeds and files
    if message.embeds:
        base_webhook_params['embeds'] = message.embeds if not reference_embeds else message.embeds + reference_embeds
    elif reference_embeds:
        base_webhook_params['embeds'] = reference_embeds
    
    message_files = None
    if message.attachments:
        message_files = [await a.to_file() for a in message.attachments]
    
    if message_files or reference_files:
        combined_files = []
        if message_files:
            combined_files.extend(message_files)
        if reference_files:
            combined_files.extend(reference_files)
        base_webhook_params['files'] = combined_files
    
    # Skip if nothing to send
    if not base_webhook_params.get('content') and not base_webhook_params.get('embeds') and not base_webhook_params.get('files'):
        logger.info(f"Skipping empty message from {safe_text(message.author.display_name)}")
        return
    
    # Forward to all output channels concurrently
    processing_tasks = []
    forward_tasks = []
    
    for channel_id in USER_OUTPUT_CHANNEL_IDS:
        forward_tasks.append(forward_user_to_channel(
            channel_id, bot, base_webhook_params, 
            PROCESS_CRYPTO_IN_FORWARDS, crypto_detected, processing_tasks
        ))
    
    # Wait for all forwards to complete
    await asyncio.gather(*forward_tasks, return_exceptions=True)
    
    # Now execute any crypto processing tasks that were created
    if processing_tasks:
        await asyncio.gather(*processing_tasks, return_exceptions=True)

async def forward_user_to_channel(channel_id, bot, webhook_params, process_crypto, crypto_detected, processing_tasks):
    """Helper to forward user message to a specific channel"""
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            logger.warning(f"Could not find output channel with ID {channel_id}")
            return None
        
        # Get or create webhook
        webhook = await get_webhook_for_channel(channel, bot)
        if not webhook:
            return None
        
        # Deep copy the webhook params to ensure files aren't reused (for more than 1 output channels so dont give error)
        params = webhook_params.copy()
        if 'files' in params:
            # Create new file objects to avoid "file already sent" errors
            new_files = []
            for file in params['files']:
                new_file = discord.File(file.fp, filename=file.filename)
                new_files.append(new_file)
            params['files'] = new_files
        
        # Send the message
        sent_message = await webhook.send(**params)
        
        # Schedule crypto processing if needed (will be executed later)
        if process_crypto and crypto_detected:
            task = process_message_with_timeout(sent_message)
            processing_tasks.append(task)
        
        return sent_message
        
    except Exception as e:
        logger.error(f"Failed to forward user message to channel {channel_id}: {e}")
        return None

async def process_token_lock_message(message, bot):
    """
    Process token lock messages and notify users who first called those tokens
    
    Args:
        message: Discord message from token lock bot
        bot: Bot instance
    """
    # Quick initial check
    if not should_monitor_token_lock(message.channel.id, message.author.id):
        return
    
    # Current guild ID
    guild_id = message.guild.id if message.guild else 0
    if not guild_id:
        return
    
    # Extract token addresses from message content and embeds
    addresses = set()
    
    # Check message content
    if message.content:
        addresses.update(get_addresses_from_content(message.content))
    
    # Check embeds
    for embed in message.embeds:
        # Check embed description
        if embed.description:
            addresses.update(get_addresses_from_content(embed.description))
        
        # Check embed fields
        for field in embed.fields:
            if field.value:
                addresses.update(get_addresses_from_content(field.value))
            if field.name:
                addresses.update(get_addresses_from_content(field.name))
        
        # Check footer text
        if embed.footer and embed.footer.text:
            addresses.update(get_addresses_from_content(embed.footer.text))
    
    # Early return if no addresses found
    if not addresses:
        return
    
    # Process each address concurrently for maximum performance
    if addresses:
        tasks = [notify_token_caller(address, guild_id, message, bot) for address in addresses]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def notify_token_caller(address, guild_id, lock_message, bot):
    """
    Notify a user who first called a token that has been locked
    
    Args:
        address: Token address
        guild_id: Guild ID
        lock_message: Message containing lock info
        bot: Bot instance
    """
    try:
        # Get token info from database using standard fetch_one method
        from handlers.mysql_handler import fetch_one
        
        # Use the generic query mechanism rather than a special-purpose function
        query = """
        SELECT user_id, channel_id, message_id 
        FROM token_first_calls 
        WHERE token_address = %s AND guild_id = %s
        """
        
        result = await fetch_one(query, (address, guild_id))
        if not result:
            logger.debug(f"No first call found for token {address} in guild {guild_id}")
            return
        
        # Extract info from the result tuple
        user_id = result[0]
        channel_id = result[1]
        message_id = result[2]
        
        if not user_id or not channel_id:
            return
        
        # Create notification message
        notification = f"<@{user_id}> Your called token has been locked! 🔒"
        
        # Try to get original channel
        channel = bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Channel {channel_id} not found for token lock notification")
            return
        
        # Create copies of embeds WITHOUT the views/buttons
        copied_embeds = []
        for embed in lock_message.embeds:
            # Create a clean copy without carrying over view components
            new_embed = discord.Embed.from_dict(embed.to_dict())
            copied_embeds.append(new_embed)
        
        # Try to reply to original message if available
        if message_id:
            try:
                original_msg = await channel.fetch_message(int(message_id))
                await original_msg.reply(content=notification, embeds=copied_embeds)
                logger.debug(f"Sent token lock notification as reply to original message for {address}")
                return
            except Exception as e:
                logger.warning(f"Could not reply to original message: {e}")
        else:
            # Fallback: Send as new message
            await channel.send(content=notification, embeds=copied_embeds)
            logger.info(f"Sent token lock notification as new message for {address}")
        
    except Exception as e:
        logger.error(f"Error sending token lock notification for {address}: {e}")

async def forward_message(message, bot):
    """
    Main entry point for message forwarding - handles multiple forwarding configurations concurrently
    
    Args:
        message: Discord message
        bot: Bot instance
    """
    start_time = datetime.now().timestamp()
    
    # Fast pre-filtering for all forwarding types
    should_process = False
    
    # Check if message should be forwarded/processed for any type
    if should_forward_user_message(message.channel.id, message.author.id):
        should_process = True
    elif should_forward_bot_message(message.channel.id, message.author.id):
        should_process = True
    elif should_monitor_token_lock(message.channel.id, message.author.id):
        should_process = True
    
    # Early return if no forwarding needed
    if not should_process:
        return
        
    # Run all applicable forwarding methods concurrently
    forwarding_tasks = []
    
    if should_forward_user_message(message.channel.id, message.author.id):
        forwarding_tasks.append(forward_user_messages(message, bot))
        
    if should_forward_bot_message(message.channel.id, message.author.id):
        forwarding_tasks.append(forward_bot_messages(message, bot))
        
    if should_monitor_token_lock(message.channel.id, message.author.id):
        forwarding_tasks.append(process_token_lock_message(message, bot))
    
    # Execute all applicable tasks
    if forwarding_tasks:
        await asyncio.gather(*forwarding_tasks, return_exceptions=True)
        
    # Record processing metrics
    bot.record_metric(datetime.now().timestamp() - start_time)