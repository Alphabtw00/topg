"""
Moralis API service for graduated tokens tracking
"""
from api.client import ApiClient, ApiEndpoint
from utils.logger import get_logger
from config import MORALIS_BASE_URL

logger = get_logger()


class MoralisService:
    """Service for Moralis graduated tokens API"""
    
    def __init__(self, client: ApiClient):
        self.client = client
    
    async def get_graduated_tokens(self, limit: int = 100):
        """
        Get latest graduated tokens from Moralis PumpFun
        
        Args:
            limit: Number of tokens to fetch (max 100)
            
        Returns:
            list: Latest graduated tokens or empty list if none found
        """
        try:
            url = f"{MORALIS_BASE_URL}/token/mainnet/exchange/pumpfun/graduated"
            params = {"limit": min(limit, 100)}
            
            response = await self.client.get(url, ApiEndpoint.MORALIS, params=params)
            
            if not response or "result" not in response:
                logger.warning("No graduated tokens returned from Moralis API")
                return []
                
            return response["result"]
            
        except Exception as e:
            logger.error(f"Error fetching graduated tokens: {e}")
            return []