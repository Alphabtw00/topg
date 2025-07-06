from enum import Enum
import aiohttp
import asyncio
import time
from typing import Dict, Optional, Any
from utils.logger import get_logger

logger = get_logger()

# Configuration constants
MAX_CONNECTIONS = 100
DNS_CACHE_TTL = 300
HTTP_TIMEOUT = 30
CONNECT_TIMEOUT = 10
SOCK_READ_TIMEOUT = 30
MAX_ERROR_THRESHOLD = 10

class ApiEndpoint(Enum):
    """Enum for API endpoints - easily extensible for new services"""
    DEXSCREENER = "dexscreener"
    GITHUB = "github"
    MOBULA = "mobula"
    WEBSITE = "website"
    TRENCHBOT = "trenchbot"
    BITQUERY = "bitquery"

class ApiClient:
    """Unified API client for all external service requests"""
    
    def __init__(self, bot=None):
        """Initialize API client with optional bot reference for metrics"""
        self.session = None
        self.bot = bot
    
    async def setup(self):
        """Set up HTTP session with optimized settings"""
        connector = aiohttp.TCPConnector(
            limit=MAX_CONNECTIONS,
            ttl_dns_cache=DNS_CACHE_TTL,
            use_dns_cache=True,
            ssl=True,
            keepalive_timeout=60.0,
            force_close=False,
            enable_cleanup_closed=True,
            limit_per_host=10
        )
        
        timeout = aiohttp.ClientTimeout(
            total=HTTP_TIMEOUT,
            connect=CONNECT_TIMEOUT,
            sock_connect=CONNECT_TIMEOUT,
            sock_read=SOCK_READ_TIMEOUT
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "User-Agent": "DiscordCryptoBot/1.0",
                "Accept": "application/json",
                "Connection": "keep-alive"
            }
        )
        return self
    
    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
    
    async def get(self, url: str, endpoint: ApiEndpoint, params: Dict = None, 
             headers: Dict = None, max_retries: int = 2, timeout: int = None) -> Optional[Any]:
        """
        Make a GET request with standardized error handling and metrics
        
        Args:
            url: URL to request
            endpoint: ApiEndpoint enum identifying the service
            params: Query parameters
            headers: Custom headers to send with the request
            max_retries: Maximum number of retries on failure
            timeout: Custom timeout in seconds
            
        Returns:
            Response data or None on failure
        """
        return await self._request("GET", url, endpoint, params=params, 
                                headers=headers, max_retries=max_retries, timeout=timeout)
    
    async def post(self, url: str, endpoint: ApiEndpoint, data: Dict = None, 
              json_data: Dict = None, headers: Dict = None, max_retries: int = 2, 
              timeout: int = None) -> Optional[Any]:
        """
        Make a POST request with standardized error handling and metrics
        
        Args:
            url: URL to request
            endpoint: ApiEndpoint enum identifying the service
            data: Form data
            json_data: JSON data
            headers: Custom headers to send with the request
            max_retries: Maximum number of retries on failure
            timeout: Custom timeout in seconds
            
        Returns:
            Response data or None on failure
        """
        return await self._request("POST", url, endpoint, data=data, json_data=json_data,
                                   headers=headers, max_retries=max_retries, timeout=timeout)
    
    async def _request(self, method: str, url: str, endpoint: ApiEndpoint, 
                      params: Dict = None, data: Dict = None, json_data: Dict = None,
                      headers: Dict = None, max_retries: int = 2, timeout: int = None) -> Optional[Any]:
        """
        Make an HTTP request with standardized error handling and metrics
        
        Args:
            method: HTTP method
            url: URL to request
            endpoint: ApiEndpoint enum identifying the service
            params: Query parameters
            data: Form data
            json_data: JSON data
            headers: Custom headers to send with the request
            max_retries: Maximum number of retries on failure
            timeout: Custom timeout in seconds
            
        Returns:
            Response data or None on failure
        """
        endpoint_name = endpoint.value
        request_timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        
        for attempt in range(max_retries + 1):
            start_time = time.time()
            try:
                async with self.session.request(
                    method, url, params=params, data=data, json=json_data,
                    headers=headers, timeout=request_timeout
                ) as response:
                    # Record API latency if bot is available
                    latency = time.time() - start_time
                    if self.bot:
                        self.bot.record_api_latency(endpoint_name, latency)
                    
                    if response.status == 200:
                        if endpoint == ApiEndpoint.WEBSITE:
                            # Return dict with text, headers, etc.
                            return {
                                "text": await response.text(),
                                "headers": dict(response.headers),
                                "status": response.status,
                                "url": str(response.url)
                            }
                        return await response.json()
                    else:
                        # Track errors by endpoint
                        if self.bot:
                            error_count = self.bot.increment_error_count(f"api_{endpoint_name}")
                            
                            if error_count > MAX_ERROR_THRESHOLD:
                                logger.critical(f"Endpoint {endpoint_name} experiencing high error rate")
                        
                        if response.status == 429:  # Rate limited
                            wait_time = 1 * (attempt + 1)
                            retry_after = response.headers.get('Retry-After')
                            if retry_after:
                                try:
                                    wait_time = float(retry_after)
                                except ValueError:
                                    pass
                                    
                            if attempt < max_retries:
                                logger.warning(f"Rate limited for {endpoint_name}, waiting {wait_time}s")
                                await asyncio.sleep(wait_time)
                                continue
                        
                        logger.warning(f"API {endpoint_name} returned status {response.status} for URL: {url}")
                        return None
            except asyncio.TimeoutError:
                logger.warning(f"Timeout for {endpoint_name} - {url} (attempt {attempt+1}/{max_retries+1})")
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    continue
            except Exception as e:
                logger.error(f"{endpoint_name} request error: {e} for URL: {url}")
                return None
        return None