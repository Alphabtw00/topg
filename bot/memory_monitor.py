"""
Memory usage monitoring
"""
import asyncio
import psutil
import gc
from utils.logger import get_logger
from utils.cache import GITHUB_ANALYSIS_CACHE
from utils.validators import ADDRESS_CACHE

logger = get_logger()

async def monitor_memory_usage(threshold_mb=300, check_interval=300):
    """
    Monitor and manage memory usage
    
    Args:
        threshold_mb: Memory threshold in MB to trigger cleanup
        check_interval: Check interval in seconds
    """
    logger.info(f"Memory monitor started (threshold: {threshold_mb}MB, interval: {check_interval}s)")
    
    while True:
        memory = psutil.Process().memory_info().rss / 1024 ** 2  # Get memory usage in MB
        
        if memory > threshold_mb:
            logger.warning(f"Memory cleanup triggered at {memory:.1f}MB")
            
            # Clear caches
            pre_cleanup = memory
            ADDRESS_CACHE.clear()
            
            # Suggest garbage collection
            gc.collect()
            
            # Check memory after cleanup
            post_cleanup = psutil.Process().memory_info().rss / 1024 ** 2
            logger.info(f"Memory cleanup: {pre_cleanup:.1f}MB → {post_cleanup:.1f}MB (saved: {pre_cleanup-post_cleanup:.1f}MB)")
        
        await asyncio.sleep(check_interval)  # Check periodically