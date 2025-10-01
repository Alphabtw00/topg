"""
Configuration and environment settings
"""
import os
import re
import discord
from dotenv import load_dotenv
from itertools import count
from utils.formatters import parse_channel_colors

# Load environment variables
load_dotenv()

# ========================================================================================================================================================================================
# Discord Bot Configuration
# ========================================================================================================================================================================================
# Core settings
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not found in environment")
PREFIX_COMMANDS = {}

# Discord intents with optimizations
INTENTS = discord.Intents.all()
INTENTS.message_content = True
INTENTS.typing = False
INTENTS.presences = False
INTENTS.integrations = False

ADMIN_USER_IDS = {int(id.strip()) for id in os.getenv("ADMIN_USER_IDS", "").split(",") if id.strip().isdigit()}

# ========================================================================================================================================================================================
# Message Forwarding Configuration
# ========================================================================================================================================================================================
# Guild settings
FORWARD_GUILD_IDS = {int(id.strip()) for id in os.getenv("FORWARD_GUILD_IDS", "").split(",") if id.strip().isdigit()}
PROCESS_CRYPTO_IN_FORWARDS = os.getenv("PROCESS_CRYPTO_IN_FORWARDS", "True").lower() in ("true", "1", "yes")

# Echo Bot message forwarding
BOT_INPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("BOT_INPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
BOT_OUTPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("BOT_OUTPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
FORWARD_BOT_IDS = {int(id.strip()) for id in os.getenv("FORWARD_BOT_IDS", "").split(",") if id.strip().isdigit()}
BOT_CHANNEL_COLORS = parse_channel_colors(os.getenv("BOT_EMBED_COLOR", "0x3498db"), BOT_INPUT_CHANNEL_IDS)

# User message forwarding
USER_INPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("USER_INPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
USER_OUTPUT_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("USER_OUTPUT_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
FORWARD_USER_IDS = {int(id.strip()) for id in os.getenv("FORWARD_USER_IDS", "").split(",") if id.strip().isdigit()}

ENABLE_BOT_FORWARDING = os.getenv("ENABLE_BOT_FORWARDING", "True").lower() in ("true", "1", "yes")
ENABLE_USER_FORWARDING = os.getenv("ENABLE_USER_FORWARDING", "True").lower() in ("true", "1", "yes")
ENABLE_ALERTS = os.getenv("ENABLE_ALERTS", "True").lower() in ("true", "1", "yes")



# ========================================================================================================================================================================================
# API Keys & External Services
# ========================================================================================================================================================================================
# GitHub API
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise ValueError("GITHUB_TOKEN not found in environment")

# Anthropic API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in environment")

# VirusTotal API
VIRUS_TOTAL_API_KEY = os.getenv("VIRUS_TOTAL_API_KEY")
if not VIRUS_TOTAL_API_KEY:
    raise ValueError("VIRUS_TOTAL_API_KEY not found in environment")

#final stretch
BITQUERY_SUBSCRIPTION_API_KEY_1 = os.getenv("BITQUERY_SUBSCRIPTION_API_KEY_1")
if not BITQUERY_SUBSCRIPTION_API_KEY_1:
    raise ValueError("BITQUERY_SUBSCRIPTION_API_KEY_1 not found in environment")

#migration (pf)
BITQUERY_SUBSCRIPTION_API_KEY_2 = os.getenv("BITQUERY_SUBSCRIPTION_API_KEY_2")
if not BITQUERY_SUBSCRIPTION_API_KEY_2:
    raise ValueError("BITQUERY_SUBSCRIPTION_API_KEY_2 not found in environment")

#migration (bonk,boop,beleive,moonshot,jup,virtual curve)
BITQUERY_SUBSCRIPTION_API_KEY_3 = os.getenv("BITQUERY_SUBSCRIPTION_API_KEY_3")
if not BITQUERY_SUBSCRIPTION_API_KEY_3:
    raise ValueError("BITQUERY_SUBSCRIPTION_API_KEY_3 not found in environment")

BITQUERY_QUERY_API_KEY_1 = os.getenv("BITQUERY_QUERY_API_KEY_1")
if not BITQUERY_QUERY_API_KEY_1:
    raise ValueError("BITQUERY_QUERY_API_KEY_1 not found in environment")

MOBULA_API_KEY = os.getenv("MOBULA_API_KEY")
if not MOBULA_API_KEY:
    raise ValueError("MOBULA_API_KEY not found in environment")
# ========================================================================================================================================================================================
# API Endpoints
# ========================================================================================================================================================================================
DEXSCREENER_BASE_URL = "https://api.dexscreener.com"
TWITTER_SEARCH_URL = "https://x.com/search?q={query}&f=live"
MOBULA_BASE_URL =  "https://explorer-api.mobula.io/api/1/market"
MOBULA_ATH_URL = "https://explorer-api.mobula.io/api/1/market/history/pair?asset={contact_address}&blockchain={blockchain}&period={period}&amount=100000"
MORALIS_BASE_URL = "https://solana-gateway.moralis.io"
BITQUERY_BASE_URL = "https://streaming.bitquery.io/eap"
# ========================================================================================================================================================================================
# Trading Platforms
# ========================================================================================================================================================================================
TRADING_PLATFORMS = {
    "Axiom": "https://axiom.trade/t/{address}",
    "GMGN": "https://gmgn.ai/sol/token/{address}",
    "Photon": "https://photon-sol.tinyastro.io/en/lp/{address}",
    "Neo BullX": "https://neo.bullx.io/terminal?chainId=1399811149&address={address}"
}

# ========================================================================================================================================================================================
# Database Configuration
# ========================================================================================================================================================================================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "crypto_bot")
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))
DB_SSL_CA = os.getenv("DB_SSL_CA")


# ========================================================================================================================================================================================
# Performance & Limits
# ========================================================================================================================================================================================
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

# Website cache
WEBSITE_ANALYSIS_CACHE_SIZE = 100
WEBSITE_ANALYSIS_CACHE_TTL = 3600 * 12  # 12 hours
WHOIS_CACHE_TTL = 3600 * 24 * 7  # 7 days

# Other caches
SERVER_SETTINGS_CACHE_SIZE = 100
SERVER_SETTINGS_CACHE_TTL = 86400  # seconds
CHANNEL_SETTINGS_CACHE_SIZE = 1000
CHANNEL_SETTINGS_CACHE_TTL = 86400  # seconds

# ==============================================
# Regular Expressions
# ==============================================
COMBINED_EXTRACTION_REGEX = re.compile(r'(\$[^\s]{1,10})|(\b[1-9A-HJ-NP-Za-km-z]{32,44}\b)')
ADDRESS_REGEX_PATTERN = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
TICKER_REGEX_PATTERN = r"\$([^\s]{1,10})"
WEBSITE_REGEX_PATTERN = r'^(?:http|https)://'  # http:// or https://
r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain
r'localhost|'  # localhost
r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
r'(?::\d+)?'  # optional port
r'(?:/?|[/?]\S+)$'
GITHUB_REPO_REGEX_PATTERN = r'^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$'

# ==============================================
# Truth Social Configuration
# ==============================================
# Truth Social accounts
TRUTH_ACCOUNTS = []
for index in count(1):
    username = os.getenv(f"TRUTHSOCIAL_USERNAME_{index}")
    password = os.getenv(f"TRUTHSOCIAL_PASSWORD_{index}")
    if not username or not password:
        break
    TRUTH_ACCOUNTS.append({"username": username, "password": password})

# Fallback to standard environment variables if no indexed accounts found
if not TRUTH_ACCOUNTS and os.getenv("TRUTHSOCIAL_USERNAME") and os.getenv("TRUTHSOCIAL_PASSWORD"):
    TRUTH_ACCOUNTS.append({
        "username": os.getenv("TRUTHSOCIAL_USERNAME"),
        "password": os.getenv("TRUTHSOCIAL_PASSWORD")
    })

# Tracking settings
TRUTH_DEFAULT_INTERVAL = 8
TRUTH_MAX_ACCOUNTS_PER_SERVER = 5 
MIN_ACCOUNT_USAGE_INTERVAL = 25.0 #in seconds

# Pink verified emoji to use in truth social embed
VERIFIED_EMOJI = "<:Pink_Verified:1360315088837415135>"

# ==============================================
# Moderation Configuration
# ==============================================
# Server-specific username ban configuration
USERNAME_BAN_SERVER_ID = int(os.getenv('USERNAME_BAN_SERVER_ID', 0)) or None
USERNAME_BAN_LOG_CHANNEL = int(os.getenv('USERNAME_BAN_LOG_CHANNEL', 0)) or None

# Ban keywords - Add some common variations
BAN_KEYWORDS = ["daniworldwide", "dani worldwide", "dani_worldwide", "d@ni w0rldwide"]

# Fallback simpler regex for just detecting "daniworldwide" (case insensitive)
SIMPLE_DANI_REGEX = r"(?i)d\W*a\W*n\W*i\W*w\W*o\W*r\W*l\W*d\W*w\W*i\W*d\W*e"

# Enhanced regex pattern with MORE Cyrillic lookalikes
DANI_WORLDWIDE_REGEX = r"(?i)\b[dⅾᗪｄDᴅdDдДⅆ][^a-zA-Z]*[aａaAäÄ@4ᴀаАaáàäâ][^a-zA-Z]*[nｎnNⁿᴨNηᴎнНńñ][^a-zA-Z]*[iｉiI1!|ιɪɩиИìíîï][^a-zA-Z]*[wｗwWѡѡѠᴡшШщЩŵẃẁẅ][^a-zA-Z]*[oｏoO0öÖøØоОòóôöõ][^a-zA-Z]*[rｒrRᴙʀрРŕŗř][^a-zA-Z]*[lｌlL1|ʟлЛĺļľł][^a-zA-Z]*[dⅾᗪｄDᴅdDдДⅆ][^a-zA-Z]*[wｗwWѡѡѠᴡшШщЩŵẃẁẅ][^a-zA-Z]*[iｉiI1!|ιɪɩиИìíîï][^a-zA-Z]*[dⅾᗪｄDᴅdDдДⅆ][^a-zA-Z]*[eｅeE3ëËεɛеЕэЭèéêë]"

USERNAME_BAN_REGEXES = [
    DANI_WORLDWIDE_REGEX,
    SIMPLE_DANI_REGEX,
    # Add more regex patterns here if needed
]
COMPILED_BAN_REGEXES = [re.compile(pattern) for pattern in USERNAME_BAN_REGEXES]

# Funny ban reasons for embeds
BAN_FUNNY_REASONS = [
    "KYS Nigger"
    # "Nice try, Diddy!"
]

# Ban GIF URL
BAN_GIF_URL = "https://i.imgur.com/sGySZT3.gif" 
FIGHT_BACK_GIF_URL = "https://i.imgur.com/3fJo5ne.gif"


# ==============================================
# DexScreener Tracker Configuration
# ==============================================
# Tracking settings
DEX_TRACKER_POLL_INTERVAL = 2  # seconds - Adjust as needed (1-5 seconds recommended)
DEX_TRACKER_CHAINS = ["solana"]  # List of chain IDs to track

# Cache settings
DEX_TRACKER_CACHE_SIZE = 1000
DEX_TRACKER_CACHE_TTL = 3600 *24