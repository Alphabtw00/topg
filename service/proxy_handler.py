"""
Simple proxy rotation handler for API requests
"""
import random
import aiohttp
import asyncio
import time
from typing import Optional, List, Dict
from utils.logger import get_logger

logger = get_logger()

class ProxyRotator:
    """Helper class to manage proxy rotation"""
    
    def __init__(self, countries: List[str] = None, max_proxies: int = 10, protocol: str = "http", 
                debug: bool = False, auto_rotate: bool = True):
        """Initialize proxy rotator"""
        # Initialize basic properties
        self.enabled = False
        self.proxies = []
        self.protocol = protocol
        self.countries = countries or []
        self.auto_rotate = auto_rotate
        self.max_proxies = max_proxies
        self.debug = debug
        
        # Used proxies tracking
        self.current_proxy = None
        self.last_used = {}
        
        # Try to initialize proxy list asynchronously
        try:
            # Create a new event loop in a separate thread for initialization
            self.enabled = True
            logger.info(f"Proxy rotator initialized with {protocol} protocol")
        except Exception as e:
            logger.error(f"Failed to initialize proxy rotator: {e}")
            self.enabled = False
    
    def get_proxy(self) -> Optional[str]:
        """Get a proxy string in format protocol://ip:port"""
        if not self.enabled or not self.proxies:
            return None
            
        # For testing purposes, return a dummy proxy - in real usage, load from your proxy provider
        if self.debug:
            # Test proxies for development - you'd replace this with real proxies
            test_proxies = [
                f"{self.protocol}://203.0.113.1:8080",
                f"{self.protocol}://203.0.113.2:8080",
                f"{self.protocol}://203.0.113.3:8080"
            ]
            self.current_proxy = random.choice(test_proxies)
            return self.current_proxy
            
        # If we have proxies, choose one with simple rotation
        if self.proxies:
            self.current_proxy = random.choice(self.proxies)
            return self.current_proxy
            
        return None
    
    def rotate(self) -> Optional[str]:
        """Force rotation to a new proxy"""
        if not self.enabled:
            return None
        
        # Remove current proxy from consideration temporarily
        available_proxies = [p for p in self.proxies if p != self.current_proxy]
        
        # If we have other proxies, choose a different one
        if available_proxies:
            self.current_proxy = random.choice(available_proxies)
            return self.current_proxy
        elif self.proxies:  # If we only have one proxy, use it again
            return self.proxies[0]
            
        return None
    
    async def fetch_proxies(self):
        """Fetch proxies from provider - simplified example"""
        # In a real implementation, you would fetch proxies from your provider
        # This is a placeholder that simulates fetching proxies
        try:
            # Simulate API call to get proxies
            await asyncio.sleep(1)  # Simulate network delay
            
            # Replace this with your actual proxy provider logic
            if self.debug:
                # Generate test proxies
                self.proxies = [
                    f"{self.protocol}://203.0.113.{i}:8080" for i in range(1, self.max_proxies + 1)
                ]
                logger.info(f"Loaded {len(self.proxies)} test proxies")
            else:
                # In real implementation, you'd fetch from your provider
                pass
                
            return len(self.proxies) > 0
            
        except Exception as e:
            logger.error(f"Error fetching proxies: {e}")
            return False
    
    async def get_proxy_for_request(self, force_new: bool = False) -> Optional[str]:
        """Get a proxy for a request, with option to force a new one"""
        if not self.enabled:
            return None
            
        # Fetch proxies if we don't have any yet
        if not self.proxies:
            success = await self.fetch_proxies()
            if not success:
                return None
                
        if force_new or self.auto_rotate or not self.current_proxy:
            return self.rotate()
            
        return self.current_proxy