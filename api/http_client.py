"""
HTTP client for API requests
"""
import aiohttp
import asyncio
import logging
from config import (
    HTTP_TIMEOUT, CONNECT_TIMEOUT, SOCK_READ_TIMEOUT,
    MAX_CONNECTIONS, DNS_CACHE_TTL, MAX_ERROR_THRESHOLD
)
from utils.logger import get_logger
from utils.cache import increment_error_count, get_error_count

logger = get_logger()

async def setup_http_session():
    """
    Create and configure an HTTP client session
    
    Returns:
        aiohttp.ClientSession: Configured HTTP session
    """
    # Optimize connection settings for many concurrent requests
    connector = aiohttp.TCPConnector(
        limit=MAX_CONNECTIONS,  # Maximum number of concurrent connections
        ttl_dns_cache=DNS_CACHE_TTL,  # Cache DNS results
        use_dns_cache=True,
        ssl=True         
    )
    
    timeout = aiohttp.ClientTimeout(
        total=HTTP_TIMEOUT,
        connect=CONNECT_TIMEOUT,
        sock_connect=CONNECT_TIMEOUT,
        sock_read=SOCK_READ_TIMEOUT
    )
    
    return aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers={
            "User-Agent": "DiscordCryptoBot/1.0",
            "Accept": "application/json",
            "Connection": "keep-alive"
        }
    )

async def fetch_data(session: aiohttp.ClientSession, url: str, max_retries=2):
    """
    Fetch data from an API endpoint with retry logic
    
    Args:
        session: HTTP session
        url: URL to fetch
        max_retries: Maximum number of retries
        
    Returns:
        dict or None: JSON response or None on failure
    """
    endpoint = url.split('/')[3]
    
    for attempt in range(max_retries + 1):
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    # Track errors by endpoint
                    error_count = increment_error_count(endpoint)
                    
                    if error_count > MAX_ERROR_THRESHOLD:
                        logger.critical(f"Endpoint {endpoint} experiencing high error rate")
                        
                    if response.status == 429:  # Rate limited
                        if attempt < max_retries:
                            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
                            continue
                    
                    logger.warning(f"API returned status {response.status} for URL: {url}")
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {url} (attempt {attempt+1}/{max_retries+1})")
            if attempt < max_retries:
                await asyncio.sleep(0.5)  # Short delay before retry
                continue
        except Exception as e:
            logger.error(f"Fetch error: {e} for URL: {url}")
            return None
    return None

async def fetch_data_post(session: aiohttp.ClientSession, url: str, json_data=None, max_retries=2, timeout=180):
    """
    Post data to an API endpoint with retry logic
    
    Args:
        session: HTTP session
        url: URL to post to
        json_data: JSON data to send
        max_retries: Maximum number of retries
        timeout: Request timeout in seconds
        
    Returns:
        dict or None: JSON response or None on failure
    """
    endpoint = url.split('/')[-1]
    
    for attempt in range(max_retries + 1):
        try:
            async with session.post(url, json=json_data, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    # Track errors by endpoint
                    error_count = increment_error_count(endpoint)
                    
                    if error_count > MAX_ERROR_THRESHOLD:
                        logger.critical(f"Endpoint {endpoint} experiencing high error rate")
                        
                    if response.status == 429:  # Rate limited
                        if attempt < max_retries:
                            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
                            continue
                    
                    logger.warning(f"API returned status {response.status} for URL: {url}")
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout posting to {url} (attempt {attempt+1}/{max_retries+1})")
            if attempt < max_retries:
                await asyncio.sleep(0.5)  # Short delay before retry
                continue
        except Exception as e:
            logger.error(f"Post error: {e} for URL: {url}")
            return None
    return None