"""
Mobula API service for historical price data
"""
from datetime import datetime
import asyncio
from api.client import ApiClient, ApiEndpoint
from utils.logger import get_logger
from config import MOBULA_ATH_URL

logger = get_logger()

class MobulaService:
    """Service for Mobula API interactions"""
    
    def __init__(self, api_client: ApiClient):
        """Initialize with API client"""
        self.client = api_client
    
    async def get_all_time_high(self, address: str, creation_timestamp: int = None, 
                               chain_id: str = "solana", max_retries=3):
        """
        Get all-time high price data for a token
        
        Args:
            address: Contact address
            creation_timestamp: Creation timestamp in milliseconds
            chain_id: Blockchain ID
            max_retries: Maximum number of retries
            
        Returns:
            tuple: (ATH price, ATH timestamp) or (None, None) if not found
        """
        try:
            # Determine appropriate time period based on token age
            current_time = int(datetime.now().timestamp() * 1000)
            token_age = current_time - (creation_timestamp or 0)
            
            # Select period granularity based on token age - optimized for accuracy
            if token_age < 30 * 60 * 1000:  #30 mins below
                period = "1s"
            if token_age < 2 * 60 * 60 * 1000:  #1 hour below
                period = "1min"
            elif token_age < 5 * 60 * 60 * 1000:   #5 hour below
                period = "5min"
            elif token_age < 24 * 60 * 60 * 1000:  # 1 day below
                period = "15min"
            elif token_age < 3 * 24 * 60 * 60 * 1000:  # 3 days below
                period = "1h"
            elif token_age < 7 * 24 * 60 * 60 * 1000:  # 1 week below
                period = "2h"
            elif token_age < 30 * 24 * 60 * 60 * 1000:  # 30 days below
                period = "4h"
            else:  # Older than 1 year
                period = "1d"

            url = MOBULA_ATH_URL.format(contact_address=address, period=period, blockchain=chain_id)

            for retry in range(max_retries + 1):
                data = await self.client.get(url, ApiEndpoint.MOBULA)
                
                # Check for valid data
                if data and data.get("data"):
                    # Find ATH using max() with key function - more efficient
                    valid_candles = [c for c in data["data"] if c.get("high") is not None]
                    if valid_candles:
                        # Get the highest candle
                        ath_candle = max(valid_candles, key=lambda x: x["high"])
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
    