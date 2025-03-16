"""
DexScreener API client
"""
import aiohttp
from config import BASE_URL
from api.http_client import fetch_data
from utils.logger import get_logger

logger = get_logger()

async def get_token_info(session: aiohttp.ClientSession, addresses: list):
    """
    Get token information for a list of addresses
    
    Args:
        session: HTTP session
        addresses: List of token addresses
        
    Returns:
        dict: Token data mapped by address
    """
    if not addresses:
        return {}
    
    # Process addresses in chunks to avoid URL length limits
    chunks = [addresses[i:i+5] for i in range(0, len(addresses), 5)]
    result = {}
    
    for chunk in chunks:
        url = f"{BASE_URL}/tokens/v1/solana/{','.join(chunk)}"
        tokens_data = await fetch_data(session, url)
        
        if tokens_data:
            # Map each entry by address for easy lookup
            for entry in tokens_data:
                base_token = entry.get("baseToken", {})
                address = base_token.get("address", "").lower()
                if address:
                    result[address] = entry
    
    return result

async def search_token(session: aiohttp.ClientSession, ticker: str):
    """
    Search for a token by ticker symbol
    
    Args:
        session: HTTP session
        ticker: Ticker symbol to search for
        
    Returns:
        dict or None: Token data or None if not found
    """
    url = f"{BASE_URL}/latest/dex/search?q={ticker}"
    search_data = await fetch_data(session, url)
    
    if search_data and search_data.get("pairs"):
        return search_data["pairs"][0]
    
    return None

async def get_order_status(session: aiohttp.ClientSession, token_address: str):
    """
    Get the payment status for a token
    
    Args:
        session: HTTP session
        token_address: Token address
        
    Returns:
        str: Status message
    """
    from utils.formatters import relative_time
    
    try:
        url = f"{BASE_URL}/orders/v1/solana/{token_address}"
        data = await fetch_data(session, url)
        
        if data is None:
            return ""
        
        if not data:  # []
            return "❌ Dex Not Paid"
        
        for order in data:
            if order.get("type") == "tokenProfile":
                status = order.get("status")
                timestamp = order.get("paymentTimestamp")
                time_ago = f" ({relative_time(timestamp, include_ago=True)})" if timestamp else ""
                if status == "approved":
                    return f"✅ Dex Paid{time_ago}"
                elif status == "on-hold":
                    return f"⏳ Dex On Hold{time_ago}"
                elif status == "cancelled":
                    return f"🚫 Dex Cancelled{time_ago}"
                else:
                    # Handle any other status dynamically
                    return f"❕ Dex {status.capitalize()}{time_ago}"
       
        
        return "❌ Dex Not Paid"
    
    except Exception as e:
        logger.error(f"Order status error for {token_address}: {e}")
        return "❗ Dex Error"