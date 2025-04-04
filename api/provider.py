"""
Service provider for all API services
"""
from api.client import ApiClient, ApiEndpoint
from api.dexscreener import DexScreenerService
from api.mobula import MobulaService
from api.github_analyzer import GitHubAnalyzer
from api.website_analyzer import WebsiteAnalyzer
from utils.logger import get_logger

logger = get_logger()

class ServiceProvider:
    """Provider for all API services"""
    
    def __init__(self, bot=None):
        """Initialize service provider with bot instance"""
        self.bot = bot
        self.api_client = None
        self.dexscreener = None
        self.mobula = None
        self.github_analyzer = None
        self.website_analyzer = None
    
    async def setup(self):
        """Set up all services"""
        # Initialize API client
        self.api_client = ApiClient(self.bot)
        await self.api_client.setup()
        logger.info("API client initialized")
        
        # Initialize services
        self.dexscreener = DexScreenerService(self.api_client)
        self.mobula = MobulaService(self.api_client)
        self.github_analyzer = GitHubAnalyzer(self.api_client)
        self.website_analyzer = WebsiteAnalyzer(self.api_client)
        logger.info("All API services initialized")
        
        return self
    
    async def close(self):
        """Close all services"""
        if self.api_client:
            await self.api_client.close()
            logger.info("API client closed")