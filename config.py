"""
Configuration and environment settings
"""
import os
import discord
from dotenv import load_dotenv
from utils.formatters import parse_channel_colors
# Load environment variables
load_dotenv()

# Discord Bot Token
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not found in environment")

# Auto message allowed channels
TARGET_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("TARGET_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}

# Admin users
ADMIN_USER_IDS = {int(uid.strip()) for uid in os.getenv("ADMIN_USER_IDS", "").split(",") if uid.strip().isdigit()}

#echo bot forwarding
BOT_INPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("BOT_INPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
BOT_OUTPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("BOT_OUTPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
FORWARD_BOT_IDS = {int(id.strip()) for id in os.getenv("FORWARD_BOT_IDS", "").split(",") if id.strip().isdigit()}
BOT_CHANNEL_COLORS = parse_channel_colors(os.getenv("BOT_EMBED_COLOR", "0x3498db"), BOT_INPUT_CHANNEL_IDS)
#dani messages forwarding
USER_INPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("USER_INPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
USER_OUTPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("USER_OUTPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
FORWARD_USER_IDS = {int(id.strip()) for id in os.getenv("FORWARD_USER_IDS", "").split(",") if id.strip().isdigit()}
PROCESS_CRYPTO_IN_FORWARDS = os.getenv("PROCESS_CRYPTO_IN_FORWARDS", "True").lower() in ("true", "1", "yes")


# API Endpoints
DEXSCREENER_BASE_URL = "https://api.dexscreener.com"
TWITTER_SEARCH_URL = "https://x.com/search?q={query}&f=live"
MOBULA_ATH_URL = "https://production-api.mobula.io/api/1/market/history/pair?asset={contact_address}&blockchain={blockchain}&period={period}"

# Trading Platforms
TRADING_PLATFORMS = {
    "Axiom": "https://axiom.trade/meme/{pair}",
    "Photon": "https://photon-sol.tinyastro.io/en/lp/{pair}",
    "Neo BullX": "https://neo.bullx.io/terminal?chainId=1399811149&address={address}",
}

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "crypto_bot")
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))

# Regex Patterns
ADDRESS_REGEX_PATTERN = r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"
TICKER_REGEX_PATTERN = r"\$([^\s]{1,10})"
GITHUB_URL_REGEX_PATTERN = r"^https://github\.com/[a-zA-Z0-9-]+/[a-zA-Z0-9._-]+/?$"

# Performance settings
MAX_ERROR_THRESHOLD = 50

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
PREFIX_COMMANDS = {}