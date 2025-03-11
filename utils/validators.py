"""
Validation utilities
"""
import re
import base58
from functools import lru_cache
from cachetools import TTLCache, cached
from config import ADDRESS_REGEX_PATTERN, TICKER_REGEX_PATTERN, GITHUB_URL_REGEX_PATTERN, ADDRESS_CACHE_SIZE, ADDRESS_CACHE_TTL

# Compile regex patterns for efficiency
ADDRESS_REGEX = re.compile(ADDRESS_REGEX_PATTERN)
TICKER_REGEX = re.compile(TICKER_REGEX_PATTERN)
GITHUB_URL_REGEX = re.compile(GITHUB_URL_REGEX_PATTERN)

# Cache for address validation
ADDRESS_CACHE = TTLCache(maxsize=ADDRESS_CACHE_SIZE, ttl=ADDRESS_CACHE_TTL)

@cached(ADDRESS_CACHE)
def validate_solana_address(candidate: str) -> bool:
    """
    Validate if a string is a valid Solana address
    
    Args:
        candidate: String to validate
        
    Returns:
        bool: True if valid Solana address, False otherwise
    """
    try:
        return len(base58.b58decode(candidate)) == 32
    except Exception:
        return False

def get_addresses_from_content(content: str) -> set:
    """
    Extract and validate Solana addresses from a string
    
    Args:
        content: String to analyze
        
    Returns:
        set: Set of valid Solana addresses
    """
    return {addr for addr in ADDRESS_REGEX.findall(content) if validate_solana_address(addr)}

def get_tickers_from_content(content: str) -> list:
    """
    Extract ticker symbols from a string
    
    Args:
        content: String to analyze
        
    Returns:
        list: List of ticker symbols without the $ prefix
    """
    return list(set(TICKER_REGEX.findall(content)))

def validate_github_url(url: str) -> bool:
    """
    Validate if a string is a valid GitHub repository URL
    
    Args:
        url: String to validate
        
    Returns:
        bool: True if valid GitHub URL, False otherwise
    """
    return bool(GITHUB_URL_REGEX.match(url))