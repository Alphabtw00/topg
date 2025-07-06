"""
BitQuery API service using unified API client
"""
from api.client import ApiClient, ApiEndpoint
from config import BITQUERY_QUERY_API_KEY_1
from utils.logger import get_logger
from typing import Dict, Optional, Any
from config import BITQUERY_BASE_URL

logger = get_logger()

class BitQueryService:
    """Service for BitQuery API interactions"""

    def __init__(self, api_client: ApiClient):
        """Initialize with API client"""
        self.client = api_client

    async def execute_query(self, query: str, variables: Dict = None) -> Optional[Dict]:
        """
        Execute a GraphQL query on BitQuery API

        Args:
            query: GraphQL query string
            variables: Query variables (optional)

        Returns:
            dict: Query response data or None on failure
        """
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {BITQUERY_QUERY_API_KEY_1}"
            }
            
            payload = {
                "query": query,
                "variables": variables or {}
            }
            
            response = await self.client.post(
                BITQUERY_BASE_URL, 
                ApiEndpoint.BITQUERY,
                json_data=payload,
                headers=headers,
                timeout=30
            )
            
            if response and "data" in response:
                return response["data"]
            else:
                logger.error(f"BitQuery API returned invalid response: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error executing BitQuery query: {e}")
            return None