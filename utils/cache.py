"""
Caching utilities
"""
from cachetools import TTLCache
from config import GITHUB_ANALYSIS_CACHE_SIZE, GITHUB_ANALYSIS_CACHE_TTL

# Cache for GitHub analysis results
GITHUB_ANALYSIS_CACHE = TTLCache(maxsize=GITHUB_ANALYSIS_CACHE_SIZE, ttl=GITHUB_ANALYSIS_CACHE_TTL)

# Error count tracking
error_counts = {}

def clear_error_counts():
    """Clear the error count tracking dictionary"""
    error_counts.clear()

def increment_error_count(error_key):
    """
    Increment the error count for a specific error key
    
    Args:
        error_key: Key to track the error
        
    Returns:
        int: Updated error count
    """
    error_counts[error_key] = error_counts.get(error_key, 0) + 1
    return error_counts[error_key]

def get_error_count(error_key=None):
    """
    Get the error count for a specific key or total
    
    Args:
        error_key: Key to get the count for, or None for total
        
    Returns:
        int: Error count
    """
    if error_key is None:
        return sum(error_counts.values())
    return error_counts.get(error_key, 0)