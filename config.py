"""
Configuration and environment settings
"""
import os
import discord
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Discord Bot Token
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not found in environment")

# Channel and User IDs
TARGET_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("TARGET_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
ALLOWED_USER_IDS = {int(uid.strip()) for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip().isdigit()}

# API Endpoints
BASE_URL = "https://api.dexscreener.com"
TWITTER_SEARCH_URL = "https://x.com/search?q={query}&f=live"

# Trading Platforms
TRADING_PLATFORMS = {
    "Axiom": "https://axiom.trade/meme/{pair}",
    "Photon": "https://photon-sol.tinyastro.io/en/lp/{pair}",
    "Neo BullX": "https://neo.bullx.io/terminal?chainId=1399811149&address={address}",
}

# Regex Patterns
ADDRESS_REGEX_PATTERN = r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"
TICKER_REGEX_PATTERN = r"\$([^\s]{1,10})"
GITHUB_URL_REGEX_PATTERN = r"^https://github\.com/[a-zA-Z0-9-]+/[a-zA-Z0-9._-]+/?$"

# Performance settings
MAX_ERROR_THRESHOLD = 50
MAX_CONCURRENT_PROCESSES = 5

# Timeouts and Limits
HTTP_TIMEOUT = 15  # seconds
CONNECT_TIMEOUT = 5  # seconds
SOCK_READ_TIMEOUT = 10  # seconds
MAX_CONNECTIONS = 50
DNS_CACHE_TTL = 300  # seconds

# Cache settings
GITHUB_ANALYSIS_CACHE_SIZE = 100
GITHUB_ANALYSIS_CACHE_TTL = 3600  # seconds
ADDRESS_CACHE_SIZE = 10_000
ADDRESS_CACHE_TTL = 300  # seconds

# Initialize Discord intents with optimizations
INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.typing = False
INTENTS.presences = False
INTENTS.integrations = False

# Prefix Commands Registry
# To be populated at runtime
PREFIX_COMMANDS = {}