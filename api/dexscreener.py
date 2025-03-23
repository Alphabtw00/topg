"""
DexScreener API client - Optimized for single token addressing
"""
import aiohttp
import asyncio
from config import DEXSCREENER_BASE_URL
from api.http_client import fetch_data
from utils.logger import get_logger

logger = get_logger()

# async def get_token_info(session: aiohttp.ClientSession, addresses: list):
#     """
#     Get token information for a list of addresses - Using concurrent approach for speed
    
#     Args:
#         session: HTTP session
#         addresses: List of token addresses
        
#     Returns:
#         dict: Token data mapped by address
#     """
#     if not addresses:
#         return {}
    
#     # Create tasks for all addresses concurrently
#     tasks = [_fetch_single_token(session, address) for address in addresses]
#     results = await asyncio.gather(*tasks, return_exceptions=True)
    
#     # Process results into a single dictionary
#     tokens_map = {}
#     for address, result in zip(addresses, results):
#         if isinstance(result, Exception):
#             logger.error(f"Error fetching token {address}: {result}")
#             continue
            
#         if result:
#             address_lower = address.lower()
#             # Only take the first result (most liquid pair) for each token
#             tokens_map[address_lower] = result[0] if result else None
    
#     return tokens_map

# async def _fetch_single_token(session: aiohttp.ClientSession, address: str):
#     """
#     Fetch data for a single token address - helper for get_token_info
    
#     Args:
#         session: HTTP session
#         address: Token address
        
#     Returns:
#         list: Token pairs data
#     """
#     url = f"{DEXSCREENER_BASE_URL}/token-pairs/v1/solana/{address}"
#     return await fetch_data(session, url)

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
    
    results = {}
    try:
        url = f"{DEXSCREENER_BASE_URL}/tokens/v1/solana/{','.join(addresses)}"
        tokens_data = await fetch_data(session, url)
        
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


async def search_token(session: aiohttp.ClientSession, ticker: str):
    """
    Search for a token by ticker symbol
    
    Args:
        session: HTTP session
        ticker: Ticker symbol to search for
        
    Returns:
        dict or None: Token data or None if not found
    """
    url = f"{DEXSCREENER_BASE_URL}/latest/dex/search?q={ticker}"
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
        url = f"{DEXSCREENER_BASE_URL}/orders/v1/solana/{token_address}"
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