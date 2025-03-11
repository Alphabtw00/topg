"""
Ticker symbol detection and processing
"""
import asyncio
from urllib.parse import quote
from api.dexscreener import search_token
from handlers.address_handler import process_token_entry
from utils.logger import get_logger
from config import MAX_CONCURRENT_PROCESSES

logger = get_logger()

# Semaphore for limiting concurrent processing
processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROCESSES)

async def process_tickers(message, session, tickers):
    """
    Process a list of ticker symbols
    
    Args:
        message: Discord message
        session: HTTP session
        tickers: List of ticker symbols
    """
    tasks = []
    for ticker in tickers:
        tasks.append(process_ticker_with_semaphore(message, session, ticker))
    
    if tasks:
        await asyncio.gather(*tasks)

async def process_ticker_with_semaphore(message, session, ticker):
    """
    Process a single ticker with semaphore for concurrency control
    
    Args:
        message: Discord message
        session: HTTP session
        ticker: Ticker symbol
    """
    async with processing_semaphore:
        await process_ticker(message, session, ticker)

async def process_ticker(message, session, ticker):
    """
    Process a single ticker symbol
    
    Args:
        message: Discord message
        session: HTTP session
        ticker: Ticker symbol
    """
    try:
        # Clean ticker
        ticker = ticker.strip()
        if not ticker:
            return
        
        # Encode ticker for URL
        encoded_ticker = quote(ticker)
        
        # Search for token
        pair = await search_token(session, encoded_ticker)
        if not pair:
            logger.debug(f"No results found for ticker: ${ticker}")
            return
        
        # Get token address
        address = pair["baseToken"]["address"]
        
        # Check if address is already in message content
        if address.lower() in message.content.lower():
            logger.debug(f"Address {address} already in message, skipping ticker ${ticker}")
            return
        
        # Process token entry
        await process_token_entry(message, session, pair, address)
        
    except Exception as e:
        logger.error(f"Ticker processing error ${ticker}: {e}")