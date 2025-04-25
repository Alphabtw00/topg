"""
Helper for proxy rotation using SwiftShadow
"""
import asyncio
import random
from typing import Optional, List, Dict, Any

# Using swiftshadow for proxy rotation
try:
    from swiftshadow.classes import ProxyInterface
    from swiftshadow import QuickProxy
    HAS_SWIFTSHADOW = True
except ImportError:
    HAS_SWIFTSHADOW = False

from utils.logger import get_logger
logger = get_logger()

class ProxyRotator:
    """Helper class to manage proxy rotation"""
    
    def __init__(self, countries: List[str] = None, max_proxies: int = 10, protocol: str = "http", 
                debug: bool = False, auto_rotate: bool = True):
        """Initialize proxy rotator"""
        self.enabled = HAS_SWIFTSHADOW
        self.proxy_interface = None
        self.last_proxy = None
        self.protocol = protocol
        self.countries = countries or []
        self.auto_rotate = auto_rotate
        
        # Initialize if SwiftShadow is available
        if self.enabled:
            try:
                self.proxy_interface = ProxyInterface(
                    countries=self.countries,
                    protocol=self.protocol,
                    maxProxies=max_proxies,
                    autoRotate=self.auto_rotate,
                    debug=debug
                )
                logger.info(f"Proxy rotator initialized with {protocol} protocol")
            except Exception as e:
                logger.error(f"Failed to initialize proxy rotator: {e}")
                self.enabled = False
        else:
            logger.warning("SwiftShadow not installed, proxy rotation disabled")
    
    def get_proxy(self) -> Optional[str]:
        """Get a proxy string in format protocol://ip:port"""
        if not self.enabled or not self.proxy_interface:
            return None
            
        try:
            proxy_obj = self.proxy_interface.get()
            if proxy_obj:
                proxy_str = proxy_obj.as_string()
                self.last_proxy = proxy_str
                return proxy_str
            return None
        except Exception as e:
            logger.error(f"Error getting proxy: {e}")
            return None
    
    def rotate(self) -> Optional[str]:
        """Force rotation to a new proxy"""
        if not self.enabled or not self.proxy_interface:
            return None
            
        try:
            self.proxy_interface.rotate()
            return self.get_proxy()
        except Exception as e:
            logger.error(f"Error rotating proxy: {e}")
            return None
    
    def get_quick_proxy(self) -> Optional[str]:
        """Get a one-off proxy without using the interface"""
        if not self.enabled:
            return None
            
        try:
            proxy = QuickProxy(countries=self.countries, protocol=self.protocol)
            if proxy:
                return proxy.as_string()
            return None
        except Exception as e:
            logger.error(f"Error getting quick proxy: {e}")
            return None
    
    async def get_proxy_for_request(self, force_new: bool = False) -> Optional[str]:
        """Get a proxy for a request, with option to force a new one"""
        if not self.enabled:
            return None
            
        if force_new or self.auto_rotate or not self.last_proxy:
            return self.rotate() if self.proxy_interface else self.get_quick_proxy()
        return self.last_proxy