"""
Service provider for all API services
"""
from api.client import ApiClient, ApiEndpoint
from api.dexscreener import DexScreenerService
from api.mobula import MobulaService
from api.github_analyzer import GitHubAnalyzer
from api.website_analyzer import WebsiteAnalyzer
from api.truthsocial import TruthSocialService
from api.trenchbot import TrenchBotService
from api.bitquery import BitQueryService
from api.moralis import MoralisService
from api.kalshi import KalshiService
from utils.logger import get_logger

logger = get_logger()

class ApiServiceProvider:
    """Provider for all API services"""
    
    def __init__(self, bot=None):
        """Initialize service provider with bot instance"""
        self.bot = bot
        self.api_client = None
        self.dexscreener = None
        self.mobula = None
        self.moralis = None
        self.github_analyzer = None
        self.trenchbot = None
        self.website_analyzer = None
        self.truthsocial = None
        self.bitquery = None
        self.kalshi = None

    
    async def setup(self):
        """Set up all services"""
        # Initialize API client
        self.api_client = ApiClient(self.bot)
        await self.api_client.setup()
        logger.info("API client initialized")
        
        # Initialize services
        self.dexscreener = DexScreenerService(self.api_client)
        self.mobula = MobulaService(self.api_client)
        self.moralis = MoralisService(self.api_client)
        self.github_analyzer = GitHubAnalyzer(self.api_client)
        self.website_analyzer = WebsiteAnalyzer(self.api_client)
        self.truthsocial = TruthSocialService(self.api_client)
        self.trenchbot = TrenchBotService(self.api_client)
        self.bitquery = BitQueryService(self.api_client)
        self.kalshi = KalshiService(self.api_client)
        # await self.truthsocial.setup()
        logger.info("All API services initialized")
        
        return self
    
    async def close(self):
        """Close all services"""
        if self.api_client:
            await self.api_client.close()
            logger.info("API client closed")
        
        try:
            from service.truth_tracker_service import stop_tracking
            await stop_tracking()
            logger.info("Truth Social tracking stopped")
        except Exception as e:
            logger.error(f"Error stopping Truth Social tracking: {e}")
        
        return True