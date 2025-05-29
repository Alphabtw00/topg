import discord
import asyncio
import re
from datetime import datetime
from utils.logger import get_logger
from discord import AllowedMentions
from handlers.message_processor import process_message_with_timeout
from utils.validators import get_addresses_from_content
from utils.formatters import safe_text

logger = get_logger()

# Cache for webhooks to avoid repeated lookups
webhook_cache = {}

# Pre-computed channel sets for ultra-fast O(1) lookups
_forwarding_channels = None

def init_forwarding_cache():
    """Initialize forwarding channel sets for fast lookup - call once at bot startup"""
    global _forwarding_channels
    from config import (ENABLE_BOT_FORWARDING, ENABLE_USER_FORWARDING, ENABLE_TOKEN_LOCK_ALERTS,
                       BOT_INPUT_CHANNEL_IDS, USER_INPUT_CHANNEL_IDS, TOKEN_LOCK_INPUT_CHANNEL_IDS)
    
    _forwarding_channels = set()
    
    if ENABLE_BOT_FORWARDING:
        _forwarding_channels.update(BOT_INPUT_CHANNEL_IDS)
    if ENABLE_USER_FORWARDING:
        _forwarding_channels.update(USER_INPUT_CHANNEL_IDS)
    if ENABLE_TOKEN_LOCK_ALERTS:
        _forwarding_channels.update(TOKEN_LOCK_INPUT_CHANNEL_IDS)

def should_process_forwarding(channel_id):
    """Ultra-fast check if ANY forwarding is needed for this channel"""
    return _forwarding_channels and channel_id in _forwarding_channels

async def get_webhook_for_channel(channel, bot):
    """Get or create a webhook for the channel, with caching"""
    cache_key = channel.id
    
    if cache_key in webhook_cache:
        try:
            await webhook_cache[cache_key].fetch()  
            return webhook_cache[cache_key]
        except discord.NotFound:
            del webhook_cache[cache_key]
        except Exception:
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
    from config import (ENABLE_BOT_FORWARDING, BOT_INPUT_CHANNEL_IDS, BOT_OUTPUT_CHANNEL_IDS, 
                       BOT_CHANNEL_COLORS, FORWARD_BOT_IDS)
    
    if not ENABLE_BOT_FORWARDING or message.channel.id not in BOT_INPUT_CHANNEL_IDS:
        return
    
    if not BOT_OUTPUT_CHANNEL_IDS:
        return
    
    if FORWARD_BOT_IDS and message.author.id not in FORWARD_BOT_IDS:
        return
    
    source_channel_name = message.channel.name if hasattr(message.channel, 'name') else f"Channel {message.channel.id}"
    embed_color = BOT_CHANNEL_COLORS.get(message.channel.id, 0x3498db)
    
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
        embed = discord.Embed(description=message.content, color=embed_color)
        embed.set_footer(text=f"From #{source_channel_name}")
        
        if hasattr(message.author, 'name') and hasattr(message.author, 'display_avatar'):
            embed.set_author(name=message.author.name, icon_url=message.author.display_avatar.url)
        
        prepared_embeds.append(embed)
    
    files = None
    if message.attachments:
        try:
            files = [await attachment.to_file() for attachment in message.attachments]
        except Exception as e:
            logger.error(f"Failed to download attachments: {e}")
    
    tasks = []
    for channel_id in BOT_OUTPUT_CHANNEL_IDS:
        tasks.append(forward_bot_to_channel(channel_id, bot, prepared_embeds, files.copy() if files else None))
    
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
    from config import (ENABLE_USER_FORWARDING, USER_INPUT_CHANNEL_IDS, USER_OUTPUT_CHANNEL_IDS, 
                       PROCESS_CRYPTO_IN_FORWARDS, FORWARD_USER_IDS)
    
    if not ENABLE_USER_FORWARDING or message.channel.id not in USER_INPUT_CHANNEL_IDS:
        return
    
    if not USER_OUTPUT_CHANNEL_IDS:
        return
    
    if FORWARD_USER_IDS and message.author.id not in FORWARD_USER_IDS:
        return
    
    crypto_detected = False
    content = message.content
    if PROCESS_CRYPTO_IN_FORWARDS and content:
        if '$' in content or re.search(r'[a-zA-Z0-9]{26,}', content): 
            crypto_detected = True

    base_webhook_params = {
        'username': message.author.display_name,
        'avatar_url': message.author.display_avatar.url,
        'wait': True,
        'allowed_mentions': AllowedMentions(everyone=False, users=False, roles=False, replied_user=False),
        'suppress_embeds': False
    }
    
    quoted_content = ""
    reference_files = None
    reference_embeds = None
    
    if message.reference:
        try:
            reference_channel = bot.get_channel(message.reference.channel_id)
            if reference_channel:
                original_msg = await reference_channel.fetch_message(message.reference.message_id)
                is_reply = message.channel.id == message.reference.channel_id
                
                if not is_reply:
                    if original_msg.embeds:
                        reference_embeds = original_msg.embeds
                    
                    if original_msg.attachments:
                        reference_files = [await a.to_file() for a in original_msg.attachments]
                
                if original_msg.content:
                    lines = original_msg.content.split('\n')
                    quoted_content = '\n'.join([f"> {line}" for line in lines]) + '\n'
                    base_webhook_params['suppress_embeds'] = True
                
        except Exception as e:
            logger.warning(f"Could not fetch original message for forwarding: {e}")
    
    if content or quoted_content:
        base_webhook_params['content'] = (quoted_content or '') + (content or '')
    
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
    
    if not base_webhook_params.get('content') and not base_webhook_params.get('embeds') and not base_webhook_params.get('files'):
        logger.info(f"Skipping empty message from {safe_text(message.author.display_name)}")
        return
    
    processing_tasks = []
    forward_tasks = []
    
    for channel_id in USER_OUTPUT_CHANNEL_IDS:
        forward_tasks.append(forward_user_to_channel(
            channel_id, bot, base_webhook_params, 
            PROCESS_CRYPTO_IN_FORWARDS, crypto_detected, processing_tasks
        ))
    
    await asyncio.gather(*forward_tasks, return_exceptions=True)
    
    if processing_tasks:
        await asyncio.gather(*processing_tasks, return_exceptions=True)

async def forward_user_to_channel(channel_id, bot, webhook_params, process_crypto, crypto_detected, processing_tasks):
    """Helper to forward user message to a specific channel"""
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            logger.warning(f"Could not find output channel with ID {channel_id}")
            return None
        
        webhook = await get_webhook_for_channel(channel, bot)
        if not webhook:
            return None
        
        params = webhook_params.copy()
        if 'files' in params:
            new_files = []
            for file in params['files']:
                new_file = discord.File(file.fp, filename=file.filename)
                new_files.append(new_file)
            params['files'] = new_files
        
        sent_message = await webhook.send(**params)
        
        if process_crypto and crypto_detected:
            task = process_message_with_timeout(sent_message)
            processing_tasks.append(task)
        
        return sent_message
        
    except Exception as e:
        logger.error(f"Failed to forward user message to channel {channel_id}: {e}")
        return None

async def process_token_lock_message(message, bot):
    """Process token lock messages and notify users across ALL servers who first called those tokens"""
    from config import ENABLE_TOKEN_LOCK_ALERTS, TOKEN_LOCK_INPUT_CHANNEL_IDS, TOKEN_LOCK_BOT_IDS
    
    if not ENABLE_TOKEN_LOCK_ALERTS or message.channel.id not in TOKEN_LOCK_INPUT_CHANNEL_IDS:
        return
    
    if TOKEN_LOCK_BOT_IDS and message.author.id not in TOKEN_LOCK_BOT_IDS:
        return
    
    # Extract token addresses from message content and embeds
    addresses = set()
    
    if message.content:
        addresses.update(get_addresses_from_content(message.content))
    
    for embed in message.embeds:
        if embed.description:
            addresses.update(get_addresses_from_content(embed.description))
        
        for field in embed.fields:
            if field.value:
                addresses.update(get_addresses_from_content(field.value))
            if field.name:
                addresses.update(get_addresses_from_content(field.name))
        
        if embed.footer and embed.footer.text:
            addresses.update(get_addresses_from_content(embed.footer.text))
    
    if not addresses:
        return
    
    # Process each address concurrently for cross-server notifications
    tasks = [notify_token_caller_all_servers(address, message, bot) for address in addresses]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def notify_token_caller_all_servers(address, lock_message, bot):
    """Notify users who first called a token across ALL servers"""
    try:
        from handlers.mysql_handler import fetch_all
        
        # Get ALL first calls for this token across ALL servers
        query = """
        SELECT user_id, channel_id, message_id, guild_id
        FROM token_first_calls 
        WHERE token_address = %s
        """
        
        results = await fetch_all(query, (address,))
        if not results:
            logger.debug(f"No first calls found for token {address} across all servers")
            return
        
        # Create copied embeds once (without views/buttons)
        copied_embeds = []
        for embed in lock_message.embeds:
            new_embed = discord.Embed.from_dict(embed.to_dict())
            copied_embeds.append(new_embed)
        
        # Notify each caller concurrently
        notification_tasks = []
        for result in results:
            user_id, channel_id, message_id, guild_id = result
            if user_id and channel_id:
                notification_tasks.append(
                    send_lock_notification(bot, user_id, channel_id, message_id, copied_embeds, address)
                )
        
        if notification_tasks:
            await asyncio.gather(*notification_tasks, return_exceptions=True)
        
    except Exception as e:
        logger.error(f"Error processing token lock notifications for {address}: {e}")

async def send_lock_notification(bot, user_id, channel_id, message_id, copied_embeds, address):
    """Send individual lock notification"""
    try:
        channel = bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Channel {channel_id} not found for token lock notification")
            return
        
        notification = f"<@{user_id}> Your called token has been locked! 🔒"
        
        # Try to reply to original message if available
        if message_id:
            try:
                original_msg = await channel.fetch_message(int(message_id))
                await original_msg.reply(content=notification, embeds=copied_embeds)
                logger.debug(f"Sent cross-server token lock notification as reply for {address}")
                return
            except Exception as e:
                logger.warning(f"Could not reply to original message: {e}")
        
        # Fallback: Send as new message
        await channel.send(content=notification, embeds=copied_embeds)
        logger.info(f"Sent cross-server token lock notification as new message for {address}")
        
    except Exception as e:
        logger.error(f"Error sending individual lock notification for {address}: {e}")

async def forward_message(message, bot):
    """Ultra-fast forwarding entry point - only creates task if channel needs processing"""
    start_time = datetime.now().timestamp()
    
    # Run all applicable forwarding methods concurrently
    forwarding_tasks = []
    
    # Check each forwarding type and add task if applicable
    forwarding_tasks.append(forward_user_messages(message, bot))
    forwarding_tasks.append(forward_bot_messages(message, bot))
    forwarding_tasks.append(process_token_lock_message(message, bot))
    
    # Execute all applicable tasks
    if forwarding_tasks:
        await asyncio.gather(*forwarding_tasks, return_exceptions=True)
        
    # Record processing metrics
    bot.record_metric(datetime.now().timestamp() - start_time)