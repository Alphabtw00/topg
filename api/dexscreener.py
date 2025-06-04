"""
DexScreener API service using unified API client
"""
from api.client import ApiClient, ApiEndpoint
from config import DEXSCREENER_BASE_URL
from utils.logger import get_logger

logger = get_logger()

class DexScreenerService:
    """Service for DexScreener API interactions"""
    
    def __init__(self, api_client: ApiClient):
        """Initialize with API client"""
        self.client = api_client
    
    async def get_token_info(self, addresses: list, chain_id="solana"):
        """
        Get token information for a list of addresses
        
        Args:
            addresses: List of token addresses
            
        Returns:
            dict: Token data mapped by address
        """
        if not addresses:
            return {}
        
        results = {}
        try:
            url = f"{DEXSCREENER_BASE_URL}/tokens/v1/{chain_id}/{','.join(addresses)}"
            tokens_data = await self.client.get(url, ApiEndpoint.DEXSCREENER)
            
            if tokens_data:
                # Map each entry by address for easy lookup
                for entry in tokens_data:
                    base_token = entry.get("baseToken", {})
                    address = base_token.get("address", "")
                    if address:
                        results[address] = entry
        
        except Exception as e:
            logger.error(f"Error fetching token info: {e}")
        
        return results
    
    async def search_token(self, ticker: str):
        """
        Search for a token by ticker symbol
        
        Args:
            ticker: Ticker symbol to search for
            
        Returns:
            dict or None: Token data or None if not found
        """
        url = f"{DEXSCREENER_BASE_URL}/latest/dex/search?q={ticker}"
        search_data = await self.client.get(url, ApiEndpoint.DEXSCREENER)
        
        if search_data and search_data.get("pairs"):
            return search_data["pairs"][0]
        
        return None
    
    async def get_latest_token_profiles(self):
        """
        Get latest token profiles from DexScreener
        
        Returns:
            list: Latest token profiles or empty list if none found
        """
        try:
            url = f"{DEXSCREENER_BASE_URL}/token-profiles/latest/v1"
            profiles_data = await self.client.get(url, ApiEndpoint.DEXSCREENER)
            
            if not profiles_data:
                logger.warning("No token profiles returned from DexScreener API")
                return []
                
            return profiles_data
        except Exception as e:
            logger.error(f"Error fetching latest token profiles: {e}")
            return []
    
    async def get_order_status(self, token_address: str):
        """
        Get the payment status for a token
    
        Args:
            token_address: Token address
        
        Returns:
            str: Status message
        """
        from utils.formatters import relative_time
    
        try:
            url = f"{DEXSCREENER_BASE_URL}/orders/v1/solana/{token_address}"
            data = await self.client.get(url, ApiEndpoint.DEXSCREENER)
        
            if data is None:
                return ""
        
            if not data:  # []
                return "❌ Dex Not Paid"
        
            # Priority order: approved > processing > on-hold > cancelled
            status_priority = {"approved": 1, "processing": 2, "on-hold": 3, "cancelled": 4}
            best_order = None
            
            for order in data:
                if order.get("type") == "tokenProfile":
                    current_status = order.get("status")
                    if not best_order or status_priority.get(current_status, 99) < status_priority.get(best_order.get("status"), 99):
                        best_order = order
            
            if best_order:
                status = best_order.get("status")
                timestamp = best_order.get("paymentTimestamp")
                time_ago = f" ({relative_time(timestamp, include_ago=True)})" if timestamp else ""
                
                if status == "approved":
                    return f"✅ Dex Paid{time_ago}"
                elif status == "on-hold":
                    return f"⏳ Dex On Hold{time_ago}"
                elif status == "processing":
                    return f"⚡ Dex Processing{time_ago}"
                elif status == "cancelled":
                    return f"🚫 Dex Cancelled{time_ago}"
                else:
                    # Handle any other status dynamically (processing, etc.)
                    return f"❕ Dex {status.capitalize()}{time_ago}"
        
            return "❌ Dex Not Paid"
    
        except Exception as e:
            logger.error(f"Order status error for {token_address}: {e}")
            return "❗ Dex Error"