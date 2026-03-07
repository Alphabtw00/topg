"""
Message content processing
"""
import asyncio
import discord
from datetime import datetime
from service.address_service import process_addresses, process_tickers
from utils.logger import get_logger
from utils.formatters import safe_text
from utils.validators import extract_tickers_and_addresses_single_regex
 

logger = get_logger()

async def process_message_with_timeout(message, bot):
    """
    Process a message and extract crypto addresses and tickers with timeout
    
    Args:
        message: Discord message
    """
    try:
        # Start time for performance tracking
        start_time = datetime.now().timestamp()
        
        # Get bot client once
        if not bot or not hasattr(bot, 'services'):
            logger.error("Bot client or services not available")
            return
        
        addresses, tickers = extract_tickers_and_addresses_single_regex(message.content)
    
        if not addresses and not tickers:
            return
    
        timeout = max(15, min(len(addresses) + len(tickers), 30))

        # Process with appropriate timeout
        await asyncio.wait_for(
            asyncio.gather(
                process_addresses(message, addresses, bot),
                process_tickers(message, tickers, bot),
                return_exceptions=True
            ),
            timeout=timeout
        )
        
        # Single metric recording
        bot.record_metric(datetime.now().timestamp() - start_time)
        

    except asyncio.TimeoutError:
        logger.warning(f"Message processing timeout for {message.author} in {safe_text(message.channel)}")

    except Exception as e:
        logger.error(f"Error processing message {message.id}: {str(e)}")