"""
Message content processing
"""
import asyncio
import discord
from datetime import datetime
from utils.validators import get_addresses_from_content, get_tickers_from_content
from handlers.address_handler import process_addresses
from handlers.ticker_handler import process_tickers
from utils.logger import get_logger

logger = get_logger()

async def process_message(message: discord.Message):
    """
    Process a Discord message for crypto addresses and tickers
    
    Args:
        message: The Discord message to process
    """
    content = message.content
    
    # Quick check to see if we should process this message
    if '$' not in content and not any(c.isalnum() for c in content[:min(20, len(content))]):
        return
    
    # Get bot instance and session
    bot = message.guild.me._state._get_client()
    if not bot or not bot.http_session:
        logger.error("Bot or HTTP session not available")
        return
    
    # Extract addresses and tickers
    addresses = get_addresses_from_content(content)
    tickers = get_tickers_from_content(content)
    
    if not addresses and not tickers:
        return
    
    # Process in parallel
    tasks = []
    
    if addresses:
        tasks.append(process_addresses(message, bot.http_session, addresses))
    
    if tickers:
        tasks.append(process_tickers(message, bot.http_session, tickers))

    
    # Run tasks
    if tasks:
        start_time = datetime.now().timestamp()
        await asyncio.gather(*tasks)
        
        # Record metrics
        processing_time = datetime.now().timestamp() - start_time
        bot.record_metric(processing_time)