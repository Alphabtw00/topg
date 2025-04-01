# handlers/message_processor.py
"""
Message content processing
"""
import asyncio
import discord
from datetime import datetime
from utils.validators import get_addresses_from_content, get_tickers_from_content
from handlers.address_handler import process_addresses, process_tickers
from utils.logger import get_logger

logger = get_logger()

async def process_message_with_timeout(message):
    """
    Process a message and extract crypto addresses and tickers with timeout
    
    Args:
        message: Discord message
    """
    try:
        # Start time for performance tracking
        start_time = datetime.now().timestamp()
        
        # Get bot client once
        bot = message.guild.me._state._get_client()
        if not bot or not hasattr(bot, 'services'):
            logger.error("Bot client or services not available")
            return
        
        # Extract content
        content = message.content
        
        # Get addresses from content
        addresses = get_addresses_from_content(content)
        
        # Get tickers from content
        tickers = get_tickers_from_content(content)
        
        if not addresses and not tickers:
            return
        
        # Process with appropriate timeout
        try:
            timeout = max(15, min(len(addresses) + len(tickers), 30))
            await asyncio.wait_for(
                asyncio.gather(
                    process_addresses(message, addresses, bot),
                    process_tickers(message, tickers, bot),
                    return_exceptions=True
                ),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Message processing timeout for {message.author} in {message.channel}")
        
        # Record metrics
        processing_time = datetime.now().timestamp() - start_time
        bot.record_metric(processing_time)
        
    except Exception as e:
        logger.error(f"Error processing message {message.id}: {str(e)}")