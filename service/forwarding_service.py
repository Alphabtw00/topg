import discord
import asyncio
import re
from datetime import datetime
from utils.logger import get_logger
from discord import AllowedMentions
from service.message_service import process_message_with_timeout
from utils.validators import extract_addresses, extract_tickers_and_addresses_single_regex
from utils.formatters import safe_text

logger = get_logger()

# Cache for webhooks to avoid repeated lookups
webhook_cache = {}

# Pre-computed channel sets for ultra-fast O(1) lookups
_forwarding_channels = None
_alert_channels = None
_bot_input_channels = None
_user_input_channels = None

# Alert configuration - easily extensible
ALERT_CONFIGS = {
    1380171118874333288: {  # Token Lock channel
        'type': 'token_lock',
        'notification': 'Your called token\'s supply has been locked! 🔒',
        'footer_text': 'Token Lock Alert'
    },
    1380170835343704085: {  # Dev Burn channel
        'type': 'dev_burn', 
        'notification': 'Your called token dev has burned supply! 🔥',
        'footer_text': 'Dev Burn Alert'
    },
    1379812775869550673: {  # Dex Paid channel
        'type': 'dex_paid',
        'notification': 'DEX PAID for your call! 💰', 
        'footer_text': 'DEX Paid Alert'
    }
}

def init_forwarding_cache():
    """Initialize forwarding channel sets for fast lookup - call once at bot startup"""
    global _forwarding_channels, _alert_channels, _bot_input_channels, _user_input_channels
    from config import (ENABLE_BOT_FORWARDING, ENABLE_USER_FORWARDING, ENABLE_ALERTS,
                       BOT_INPUT_CHANNEL_IDS, BOT_OUTPUT_CHANNEL_IDS, USER_INPUT_CHANNEL_IDS, USER_OUTPUT_CHANNEL_IDS)
    
    _forwarding_channels = set()
    _alert_channels = set()
    _bot_input_channels = set()
    _user_input_channels = set()
    
    if ENABLE_BOT_FORWARDING:
        if not BOT_INPUT_CHANNEL_IDS or not BOT_OUTPUT_CHANNEL_IDS:
            logger.warning("Bot forwarding enabled but missing input or output channel IDs - skipping")
        else:
            _bot_input_channels = set(BOT_INPUT_CHANNEL_IDS)
            _forwarding_channels.update(BOT_INPUT_CHANNEL_IDS)
            logger.info(f"Bot forwarding initialized: {len(BOT_INPUT_CHANNEL_IDS)} input channels")
    
    # User forwarding setup        
    if ENABLE_USER_FORWARDING:
        if not USER_INPUT_CHANNEL_IDS or not USER_OUTPUT_CHANNEL_IDS:
            logger.warning("User forwarding enabled but missing input or output channel IDs - skipping")
        else:
            _user_input_channels = set(USER_INPUT_CHANNEL_IDS)
            _forwarding_channels.update(USER_INPUT_CHANNEL_IDS)
            logger.info(f"User forwarding initialized: {len(USER_INPUT_CHANNEL_IDS)} input channels")
    
    # Alert channels setup
    if ENABLE_ALERTS:
        if not ALERT_CONFIGS:
            logger.warning("Alerts enabled but no alert configurations found - skipping")
        else:
            _alert_channels = set(ALERT_CONFIGS.keys())
            _forwarding_channels.update(_alert_channels)
            logger.info(f"Alerts initialized: {len(ALERT_CONFIGS)} alert channels")
    
    logger.info(f"Total forwarding channels: {len(_forwarding_channels)}")

def should_process_forwarding(channel_id):
    """Ultra-fast check if ANY forwarding is needed for this channel"""
    return _forwarding_channels and channel_id in _forwarding_channels

def get_channel_type(channel_id):
    """Determine what type of forwarding this channel needs"""
    if channel_id in _bot_input_channels:
        return 'bot'
    elif channel_id in _user_input_channels:
        return 'user'
    elif channel_id in _alert_channels:
        return 'alert'
    return None

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
    from config import (BOT_OUTPUT_CHANNEL_IDS, BOT_CHANNEL_COLORS, FORWARD_BOT_IDS)
        
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
            
            original_icon_url = new_embed.footer.icon_url if new_embed.footer else None
            new_embed.set_footer(text=footer_text, icon_url=original_icon_url)
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
    from config import (USER_OUTPUT_CHANNEL_IDS, PROCESS_CRYPTO_IN_FORWARDS, FORWARD_USER_IDS)
    from utils.validators import crypto_quick_check
    
    if FORWARD_USER_IDS and message.author.id not in FORWARD_USER_IDS:
        return
    
    # Quick crypto check first, then extract if needed
    has_crypto = False
    addresses, tickers = [], []
    if PROCESS_CRYPTO_IN_FORWARDS and message.content:
        if crypto_quick_check(message.content):
            addresses, tickers = extract_tickers_and_addresses_single_regex(message.content)
            has_crypto = bool(addresses or tickers)

    base_webhook_params = {
        'username': message.author.display_name,
        'avatar_url': message.author.display_avatar.url,
        'wait': True,
        'allowed_mentions': AllowedMentions(everyone=True, users=True, roles=True, replied_user=False),
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
                
                #is forwarded message
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
    
    if message.content or quoted_content:
        base_webhook_params['content'] = (quoted_content or '') + (message.content or '')
    
    if message.embeds:
        base_webhook_params['embeds'] = message.embeds if not reference_embeds else message.embeds + reference_embeds
    elif reference_embeds:
        base_webhook_params['embeds'] = reference_embeds
    
    message_files = None
    if message.attachments:
        message_files = [await a.to_file() for a in message.attachments]
    
    if message.stickers:
        sticker_urls = [sticker.url for sticker in message.stickers]
        if sticker_urls:
            base_webhook_params['content'] = (base_webhook_params.get('content', '') + '\n' + '\n'.join(sticker_urls)).strip()
        
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
            has_crypto, processing_tasks
        ))
    
    await asyncio.gather(*forward_tasks, return_exceptions=True)
    
    if processing_tasks:
        await asyncio.gather(*processing_tasks, return_exceptions=True)

async def forward_user_to_channel(channel_id, bot, webhook_params, has_crypto, processing_tasks):
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
        
        # Process crypto if found
        if has_crypto:
            task = process_message_with_timeout(sent_message, bot)
            processing_tasks.append(task)
        
        return sent_message
        
    except Exception as e:
        logger.error(f"Failed to forward user message to channel {channel_id}: {e}")
        return None

async def process_alert_message(message, bot):
    """Optimized alert processing - addresses only"""
    alert_config = ALERT_CONFIGS[message.channel.id]
    addresses = set()
    
    # Process all text content
    text_sources = [message.content] if message.content else []
    
    for embed in message.embeds:
        if embed.description:
            text_sources.append(embed.description)
        for field in embed.fields:
            if field.value:
                text_sources.append(field.value)
            if field.name:
                text_sources.append(field.name)
        if embed.footer and embed.footer.text:
            text_sources.append(embed.footer.text)
    
    # Extract addresses from all sources
    for text in text_sources:
        addresses.update(extract_addresses(text))
    
    if not addresses:
        return
    
    # Create copied embeds once with updated footer
    copied_embeds = []
    for embed in message.embeds:
        new_embed = discord.Embed.from_dict(embed.to_dict())
        # Preserve the original footer icon if it exists
        original_icon_url = embed.footer.icon_url if embed.footer else None
        new_embed.set_footer(text=alert_config['footer_text'], icon_url=original_icon_url)
        copied_embeds.append(new_embed)
    
    # Process each address concurrently for cross-server notifications
    tasks = [notify_token_caller_all_servers(address, copied_embeds, alert_config, bot) for address in addresses]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def notify_token_caller_all_servers(address, copied_embeds, alert_config, bot):
    """Notify users who first called a token across ALL servers"""
    try:
        from service.mysql_service import fetch_all
        
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
        
        # Notify each caller concurrently
        notification_tasks = []
        for result in results:
            user_id, channel_id, message_id, guild_id = result
            if user_id and channel_id:
                notification_tasks.append(
                    send_alert_notification(bot, user_id, channel_id, message_id, copied_embeds, address, alert_config)
                )
        
        if notification_tasks:
            await asyncio.gather(*notification_tasks, return_exceptions=True)
        
    except Exception as e:
        logger.error(f"Error processing {alert_config['type']} notifications for {address}: {e}")

async def send_alert_notification(bot, user_id, channel_id, message_id, copied_embeds, address, alert_config):
    """Send individual alert notification"""
    try:
        channel = bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Channel {channel_id} not found for {alert_config['type']} notification")
            return
        
        notification = f"<@{user_id}> {alert_config['notification']}"
        
        # Try to reply to original message if available
        if message_id:
            try:
                original_msg = await channel.fetch_message(int(message_id))
                await original_msg.reply(content=notification, embeds=copied_embeds)
                logger.debug(f"Sent cross-server {alert_config['type']} notification as reply for {address}")
                return
            except Exception as e:
                logger.warning(f"Could not reply to original message: {e}")
        
        # Fallback: Send as new message
        await channel.send(content=notification, embeds=copied_embeds)
        logger.info(f"Sent cross-server {alert_config['type']} notification as new message for {address}")
        
    except Exception as e:
        logger.error(f"Error sending individual {alert_config['type']} notification for {address}: {e}")

async def forward_message(message, bot):
    """Ultra-fast forwarding entry point - only creates specific task needed"""
    start_time = datetime.now().timestamp()
    
    # Determine channel type once
    channel_type = get_channel_type(message.channel.id)
    
    if not channel_type:
        return
    
    # Create only the specific task needed
    if channel_type == 'bot':
        await forward_bot_messages(message, bot)
    elif channel_type == 'user':
        await forward_user_messages(message, bot)
    elif channel_type == 'alert':
        await process_alert_message(message, bot)
        
    # Record processing metrics
    bot.record_metric(datetime.now().timestamp() - start_time)