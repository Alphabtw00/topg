"""
Kalshi API service for prediction market data
"""
import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from api.client import ApiClient, ApiEndpoint
from utils.logger import get_logger
from config import KALSHI_BASE_URL

logger = get_logger()

class KalshiService:
    """Service for Kalshi API interactions"""
    
    def __init__(self, api_client: ApiClient):
        """Initialize with API client"""
        self.client = api_client
        self.base_url = KALSHI_BASE_URL
        
    async def get_event_data(self, event_ticker: str) -> Optional[Dict]:
        """
        Get event data with nested markets
        
        Args:
            event_ticker: Event ticker (e.g., KXSNFMENTION-25SEP28)
            
        Returns:
            Event data with markets or None
        """
        try:
            url = f"{self.base_url}/events/{event_ticker}"
            params = {"with_nested_markets": "true"}
            
            data = await self.client.get(url, ApiEndpoint.KALSHI, params=params)
            
            if not data or "event" not in data:
                logger.error(f"Invalid response from Kalshi API for event {event_ticker}")
                return None
            
            return data
            
        except Exception as e:
            logger.error(f"Error fetching event data for {event_ticker}: {e}")
            return None
    
    async def get_market_candlesticks(self, series_ticker: str, market_ticker: str, 
                                     start_ts: int, end_ts: int) -> Optional[List[Dict]]:
        """
        Get candlestick data for a market
        
        Args:
            series_ticker: Series ticker (e.g., KXSNFMENTION)
            market_ticker: Market ticker (e.g., KXSNFMENTION-25SEP28-ICEB)
            start_ts: Start Unix timestamp
            end_ts: End Unix timestamp
            
        Returns:
            List of candlestick data or None
        """
        try:
            url = f"{self.base_url}/series/{series_ticker}/markets/{market_ticker}/candlesticks"
            params = {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "period_interval": 1  # 1 minute intervals
            }
            
            data = await self.client.get(url, ApiEndpoint.KALSHI, params=params)
            
            if not data or "candlesticks" not in data:
                logger.warning(f"No candlestick data for market {market_ticker}")
                return None
            
            return data["candlesticks"]
            
        except Exception as e:
            logger.error(f"Error fetching candlesticks for {market_ticker}: {e}")
            return None
