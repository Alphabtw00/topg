"""
Mobula API client for historical price data
"""
import aiohttp
import asyncio
from datetime import datetime
from api.http_client import fetch_data
from utils.logger import get_logger
from config import MOBULA_ATH_URL

logger = get_logger()

async def get_all_time_high(session: aiohttp.ClientSession, address: str, creation_timestamp: int = None,chain_id: str = "solana", max_retries=3):
    """
    Get all-time high price data for a token
    
    Args:
        session: HTTP session
        address: Contact address
        creation_timestamp: Creation timestamp in milliseconds
        
    Returns:
        tuple: (ATH price, ATH timestamp) or (None, None) if not found
    """
    try:
        # Determine appropriate time period based on token age
        # current_time = int(datetime.now().timestamp() * 1000)
        # token_age = current_time - (creation_timestamp or 0)
        
        # # Select period granularity based on token age - optimized for accuracy
        # if token_age < 1 * 60 * 60 * 1000:  #1 hour below
        #     period = "1min"
        # elif token_age < 5 * 60 * 60 * 1000:   #5 hour below
        #     period = "5min"
        # elif token_age < 15 * 60 * 60 * 1000:  # 15 hour below
        #     period = "15min"
        # elif token_age < 3 * 24 * 60 * 60 * 1000:  # 3 days below
        #     period = "1h"
        # elif token_age < 7 * 24 * 60 * 60 * 1000:  # 1 week below
        #     period = "2h"
        # elif token_age < 14 * 24 * 60 * 60 * 1000:  # 2 week below
        #     period = "4h"
        # elif token_age < 70 * 24 * 60 * 60 * 1000:  # 70 days below (10 weeks)
        #     period = "1d"
        # elif token_age < 365 * 24 * 60 * 60 * 1000:  # 1 year below
        #     period = "7d"
        # else:  # Older than 1 year
        #     period = "30d"

        # Always request the maximum number of candles (1000)
        # This ensures we don't miss any potential ATH within the API's limit
        # url = f"https://production-api.mobula.io/api/1/market/history/pair?address={pair_address}&blockchain=solana&period={period}"
        # logger.info(f"Fetching ATH for {address} with period {period} (token age: {token_age/1000/60/60:.2f} hours)")

        # url = MOBULA_ATH_URL.format(contact_address=address, period=period, blockchain=chain_id)

        url = f"https://production-api.mobula.io/api/1/market/history/pair?asset={address}&blockchain=solana&amount=1000000000"
        for retry in range(max_retries + 1):
            data = await fetch_data(session, url)
            
            # Check for valid data
            if data and data.get("data"):
                # Find ATH using max() with key function - more efficient
                valid_candles = [c for c in data["data"] if c.get("high") is not None]
                # logger.info(f"Found {len(valid_candles)} valid candles for ATH calculation")
                if valid_candles:
                    # sorted_candles = sorted(valid_candles, key=lambda x: x["high"], reverse=True)
                    # top_candles = sorted_candles[:3]  # Top 3 highest candles
                    
                    # for i, candle in enumerate(top_candles):
                    #     candle_time = datetime.fromtimestamp(candle["time"]/1000).strftime('%Y-%m-%d %H:%M:%S')
                    #     logger.info(f"Top {i+1} candle: high={candle['high']}, time={candle_time}")
                    
                    # # Get the highest candle
                    ath_candle = max(valid_candles, key=lambda x: x["high"])
                    # ath_time = datetime.fromtimestamp(ath_candle["time"]/1000).strftime('%Y-%m-%d %H:%M:%S')
                    # logger.info(f"ATH identified: price={ath_candle['high']}, time={ath_time}")
                    
                    return ath_candle["high"], ath_candle["time"]
                return None, None
            
            #not retrying on 404
            elif data is None and retry < max_retries:
                # Only retry for potential 5xx errors (data is None)
                await asyncio.sleep(0.2 * (retry + 1))  # Exponential backoff
                continue
            
            # Return None for definitive failures (404) or after all retries
            break
            
        return None, None
       
    except Exception as e:
        logger.error(f"ATH fetch error for {address}: {e}")
        return None, None

def calculate_ath_marketcap(ath_price: float, current_price: float, current_fdv: float):
    # logger.info(f"ATH calculation inputs: ath_price={ath_price}, current_price={current_price}, current_fdv={current_fdv}")
    """
    Calculate ATH market cap based on ATH price and current FDV
    
    Args:
        ath_price: All-time high price
        current_price: Current price
        current_fdv: Current fully diluted valuation
        
    Returns:
        float or None: Calculated ATH market cap or None if input data is invalid
    """
    if not all([ath_price, current_price, current_fdv]):
        return None
    
    try:
        fdv_price_ratio = current_fdv / current_price

        # ath_marketcap = ath_price * fdv_price_ratio
        # logger.info(f"ATH calculation: fdv_price_ratio={fdv_price_ratio}, ath_marketcap={ath_marketcap}")

        return ath_price * fdv_price_ratio
    except (ZeroDivisionError, TypeError, ValueError):
        return None