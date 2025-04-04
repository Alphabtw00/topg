"""
Configuration and environment settings
"""
import os
import re
import discord
from dotenv import load_dotenv
from utils.formatters import parse_channel_colors

# Load environment variables
load_dotenv()

# ==============================================
# Discord Bot Configuration
# ==============================================
# Core settings
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not found in environment")
PREFIX_COMMANDS = {}

# Discord intents with optimizations
INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.typing = False
INTENTS.presences = False
INTENTS.integrations = False

# ==============================================
# Message Forwarding Configuration
# ==============================================
# Guild settings
FORWARD_GUILD_IDS = {int(id.strip()) for id in os.getenv("FORWARD_GUILD_IDS", "").split(",") if id.strip().isdigit()}
PROCESS_CRYPTO_IN_FORWARDS = os.getenv("PROCESS_CRYPTO_IN_FORWARDS", "True").lower() in ("true", "1", "yes")

# Bot message forwarding
BOT_INPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("BOT_INPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
BOT_OUTPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("BOT_OUTPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
FORWARD_BOT_IDS = {int(id.strip()) for id in os.getenv("FORWARD_BOT_IDS", "").split(",") if id.strip().isdigit()}
BOT_CHANNEL_COLORS = parse_channel_colors(os.getenv("BOT_EMBED_COLOR", "0x3498db"), BOT_INPUT_CHANNEL_IDS)

# User message forwarding
USER_INPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("USER_INPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
USER_OUTPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("USER_OUTPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
FORWARD_USER_IDS = {int(id.strip()) for id in os.getenv("FORWARD_USER_IDS", "").split(",") if id.strip().isdigit()}

# ==============================================
# API Keys & External Services
# ==============================================
# GitHub API
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise ValueError("GITHUB_TOKEN not found in environment")

# Anthropic API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in environment")

#VirusTotal ApI
VIRUS_TOTAL_API_KEY = os.getenv("VIRUS_TOTAL_API_KEY")
if not VIRUS_TOTAL_API_KEY:
    raise ValueError("VIRUS_TOTAL_API_KEY not found in environment")

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

# ==============================================
# Database Configuration
# ==============================================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "crypto_bot")
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))

# ==============================================
# Performance & Limits
# ==============================================
# Network settings
HTTP_TIMEOUT = 15  # seconds
CONNECT_TIMEOUT = 5  # seconds
SOCK_READ_TIMEOUT = 10  # seconds
MAX_CONNECTIONS = 50
DNS_CACHE_TTL = 300  # seconds

# Error handling
MAX_ERROR_THRESHOLD = 50
MAX_ITEMS_PER_MESSAGE = 5

# GitHub analyzer settings
GITHUB_MAX_FILES_TO_FETCH = 30

# ==============================================
# Cache Settings
# ==============================================
# GitHub cache
GITHUB_ANALYSIS_CACHE_SIZE = 100
GITHUB_ANALYSIS_CACHE_TTL = 36000  # seconds

WEBSITE_ANALYSIS_CACHE_SIZE = 100
WEBSITE_ANALYSIS_CACHE_TTL = 3600 * 12  # 12 hours
WHOIS_CACHE_TTL = 3600 * 24 * 7  # 7 days

# Other caches
ADDRESS_CACHE_SIZE = 10_000
ADDRESS_CACHE_TTL = 3600  # seconds
SERVER_SETTINGS_CACHE_SIZE = 100
SERVER_SETTINGS_CACHE_TTL = 86400  # seconds
CHANNEL_SETTINGS_CACHE_SIZE = 1000
CHANNEL_SETTINGS_CACHE_TTL = 86400  # seconds

# ==============================================
# Regular Expressions
# ==============================================
ADDRESS_REGEX_PATTERN = r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"
TICKER_REGEX_PATTERN = r"\$([^\s]{1,10})"
WEBSITE_REGEX_PATTERN = r'^(?:http|https)://'  # http:// or https://
r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain
r'localhost|'  # localhost
r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
r'(?::\d+)?'  # optional port
r'(?:/?|[/?]\S+)$'
GITHUB_REPO_REGEX_PATTERN = r'^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$'