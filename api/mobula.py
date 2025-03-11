"""
Mobula API client for historical price data
"""
import aiohttp
from datetime import datetime
from api.http_client import fetch_data
from utils.logger import get_logger

logger = get_logger()

async def get_all_time_high(session: aiohttp.ClientSession, pair_address: str, creation_timestamp: int = None):
    """
    Get all-time high price data for a token
    
    Args:
        session: HTTP session
        pair_address: Pair address
        creation_timestamp: Creation timestamp in milliseconds
        
    Returns:
        tuple: (ATH price, ATH timestamp) or (None, None) if not found
    """
    try:
        # Determine appropriate time period based on token age
        current_time = int(datetime.now().timestamp() * 1000)
        token_age = current_time - (creation_timestamp or 0)
        
        # Select period granularity based on token age - optimized for accuracy
        if token_age < 1 * 60 * 60 * 1000:  
            period = "1min"
        elif token_age < 5 * 60 * 60 * 1000:  
            period = "5min"
        elif token_age < 15 * 60 * 60 * 1000:  # 8 to 24 hours
            period = "15min"
        elif token_age < 3 * 24 * 60 * 60 * 1000:  # 1 day to 3 days
            period = "1h"
        elif token_age < 7 * 24 * 60 * 60 * 1000:  # 3 days to 7 days
            period = "2h"
        elif token_age < 14 * 24 * 60 * 60 * 1000:  # 7 days to 14 days
            period = "4h"
        elif token_age < 70 * 24 * 60 * 60 * 1000:  # 14 days to 1 month (approx. 30 days)
            period = "1d"
        elif token_age < 365 * 24 * 60 * 60 * 1000:  # 1 month to 1 year (approx. 365 days)
            period = "7d"
        else:  # Older than 1 year
            period = "30d"
            
        # Always request the maximum number of candles (1000)
        # This ensures we don't miss any potential ATH within the API's limit
        url = f"https://production-api.mobula.io/api/1/market/history/pair?address={pair_address}&blockchain=solana&period={period}"
        data = await fetch_data(session, url)
        
        if not data or not data.get("data"):
            return None, None
            
        # Find ATH using max() with key function - more efficient than iterating manually
        valid_candles = [c for c in data["data"] if c.get("high") is not None]
        if not valid_candles:
            return None, None
            
        ath_candle = max(valid_candles, key=lambda x: x["high"])
        return ath_candle["high"], ath_candle["time"]
        
    except Exception as e:
        logger.error(f"ATH fetch error for {pair_address}: {e}")
        return None, None

def calculate_ath_marketcap(ath_price: float, current_price: float, current_fdv: float):
    """
    Calculate ATH market cap based on ATH price and current FDV
    
    Args:
        ath_price: All-time high price
        current_price: Current price
        current_fdv: Current fully diluted valuation
        
    Returns:
        float or None: Calculated ATH market cap or None if input data is invalid
    """
    if not ath_price or not current_price or not current_fdv:
        return None
    
    try:
        fdv_price_ratio = current_fdv / current_price
        return ath_price * fdv_price_ratio
    except ZeroDivisionError:
        return None