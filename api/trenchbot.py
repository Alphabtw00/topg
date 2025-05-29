# api/trenchbot.py
"""
TrenchBot API service for bundle analysis
"""
from api.client import ApiClient, ApiEndpoint
from utils.logger import get_logger

logger = get_logger()

class TrenchBotService:
    """Service for TrenchBot API interactions"""
    
    def __init__(self, api_client: ApiClient):
        """Initialize with API client"""
        self.client = api_client
    
    async def get_bundle_analysis(self, contract_address: str):
        """
        Get bundle analysis for a token contract address
        
        Args:
            contract_address: Token contract address
            
        Returns:
            dict: Bundle analysis data or None if failed
        """
        try:
            url = f"https://trench.bot/api/bundle/bundle_full/{contract_address}"
            bundle_data = await self.client.get(
                url=url,
                endpoint=ApiEndpoint.TRENCHBOT,  # Using website endpoint for flexibility
                timeout=10  # Short timeout to keep command fast
            )
            
            if not bundle_data:
                logger.warning(f"No bundle data returned for {contract_address}")
                return None
              
            return bundle_data
            
        except Exception as e:
            logger.error(f"Error fetching bundle analysis for {contract_address}: {e}")
            return None