import os
import re
import base58
import discord
import aiohttp
import logging
import asyncio
import psutil
from functools import lru_cache
from typing import Set, Dict, List, Optional, Tuple, Any
from datetime import datetime
from dotenv import load_dotenv
from cachetools import TTLCache, cached
from discord.ext import commands
from discord import app_commands

# Enhanced logging configuration with structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Configuration class for better organization and type hints
class Config:
    def __init__(self):
        load_dotenv()
        self.token = os.getenv("DISCORD_BOT_TOKEN")
        if not self.token:
            raise ValueError("DISCORD_BOT_TOKEN not found in environment")
            
        self.target_channels = {
            int(id.strip()) 
            for id in os.getenv("TARGET_CHANNEL_IDS", "").split(",") 
            if id.strip().isdigit()
        }
        self.allowed_users = {
            int(uid.strip()) 
            for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") 
            if uid.strip().isdigit()
        }
        self.base_url = "https://api.dexscreener.com"
        self.twitter_search = "https://x.com/search?q={query}&f=live"
        self.trading_platforms = {
            "Axiom": "https://axiom.trade/meme/{pair}",
            "Photon": "https://photon-sol.tinyastro.io/en/lp/{pair}",
            "Neo BullX": "https://neo.bullx.io/terminal?chainId=1399811149&address={address}"
        }
        
        # Constants
        self.max_error_threshold = 50
        self.max_concurrent_processes = 5
        self.memory_threshold_mb = 300
        self.cleanup_interval = 3600  # 1 hour
        self.metrics_max_entries = 1000

# Improved cache implementation with typing
class TokenCache:
    def __init__(self, ttl: int = 300, maxsize: int = 10_000):
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)
        
    def get(self, key: str) -> Optional[Dict]:
        return self.cache.get(key)
        
    def set(self, key: str, value: Dict) -> None:
        self.cache[key] = value
        
    def clear(self) -> None:
        self.cache.clear()

class MetricsTracker:
    def __init__(self):
        self.processed_count: int = 0
        self.processing_times: List[Tuple[float, float]] = []
        self.last_cleanup: float = datetime.now().timestamp()
        self.error_counts: Dict[str, int] = {}
    
    def record_processing(self, duration: float) -> None:
        self.processed_count += 1
        self.processing_times.append((duration, datetime.now().timestamp()))
    
    def record_error(self, endpoint: str) -> None:
        self.error_counts[endpoint] = self.error_counts.get(endpoint, 0) + 1
    
    def cleanup(self) -> None:
        current_time = datetime.now().timestamp()
        self.processing_times = [
            t for t in self.processing_times[-1000:]
            if current_time - t[1] < 3600
        ]
        self.error_counts.clear()
        self.last_cleanup = current_time

class CryptoBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.typing = False
        intents.presences = False
        intents.integrations = False
        
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        
        self.config = config
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.startup_time = datetime.now()
        self.metrics = MetricsTracker()
        self.token_cache = TokenCache()
        self.processing_semaphore = asyncio.Semaphore(config.max_concurrent_processes)
        
    async def setup_hook(self) -> None:
        self.http_session = await self.setup_http_session()
        self.bg_task = self.loop.create_task(self.cleanup_metrics())
        self.memory_task = self.loop.create_task(self.monitor_memory_usage())
        
        # Register commands
        await self.add_cog(Commands(self))
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} commands")
        except Exception as e:
            logger.error(f"Command sync failed: {e}")
            
    async def setup_http_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=50,
                ttl_dns_cache=300,
                ssl=True
            ),
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "DiscordCryptoBot/1.0"}
        )

    async def cleanup_metrics(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.config.cleanup_interval)
                self.metrics.cleanup()
            except Exception as e:
                logger.error(f"Metrics cleanup error: {e}")

    async def monitor_memory_usage(self) -> None:
        while True:
            try:
                memory = psutil.Process().memory_info().rss / 1024 ** 2
                if memory > self.config.memory_threshold_mb:
                    logger.warning(f"Memory cleanup at {memory:.1f}MB")
                    import gc
                    gc.collect()
                    self.token_cache.clear()
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")

# New API client class for better organization of API calls
class DexScreenerAPI:
    def __init__(self, session: aiohttp.ClientSession, base_url: str):
        self.session = session
        self.base_url = base_url
        
    async def fetch_token_data(self, addresses: List[str]) -> Optional[Dict]:
        url = f"{self.base_url}/tokens/v1/solana/{','.join(addresses)}"
        return await self._fetch(url)
        
    async def fetch_order_status(self, token_address: str) -> str:
        url = f"{self.base_url}/orders/v1/solana/{token_address}"
        data = await self._fetch(url)
        
        if data is None:
            return ""
            
        if not data:
            return "❌ Dex Not Paid"
            
        for order in data:
            if order.get("type") == "tokenProfile":
                status = order.get("status")
                if status == "approved":
                    timestamp = order.get("paymentTimestamp")
                    time_ago = f" ({self._format_relative_time(timestamp)})" if timestamp else ""
                    return f"✅ Dex Paid{time_ago}"
                elif status == "on-hold":
                    return "⏳ Dex On Hold"
        return "❌ Dex Not Paid"
        
    async def _fetch(self, url: str, max_retries: int = 2) -> Optional[Dict]:
        endpoint = url.split('/')[3]
        
        for attempt in range(max_retries + 1):
            try:
                async with self.session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                        
                    if response.status == 429 and attempt < max_retries:
                        await asyncio.sleep(1 * (attempt + 1))
                        continue
                        
                    logger.warning(f"API status {response.status}: {url}")
                    return None
                    
            except asyncio.TimeoutError:
                if attempt < max_retries:
                    await asyncio.sleep(0.5)
                    continue
            except Exception as e:
                logger.error(f"API error: {e}")
                return None
                
        return None
        
    @staticmethod
    def _format_relative_time(timestamp: Optional[int]) -> str:
        if not timestamp:
            return "N/A"
            
        try:
            delta = datetime.now() - datetime.fromtimestamp(timestamp / 1000)
            
            if delta.days >= 365:
                return f"{delta.days//365}y"
            if delta.days > 30:
                return f"{delta.days//30}mo"
            if delta.days:
                return f"{delta.days}d"
            if delta.seconds >= 3600:
                return f"{delta.seconds//3600}h"
            if delta.seconds >= 60:
                return f"{delta.seconds//60}m"
            return f"{delta.seconds}s"
        except Exception:
            return "N/A"

def main():
    try:
        config = Config()
        bot = CryptoBot(config)
        logger.info("Starting bot...")
        bot.run(config.token, log_handler=None)
    except Exception as e:
        logger.critical(f"Bot startup failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()


# Utility classes for formatting and data handling
class Formatter:
    @staticmethod
    def get_color_from_change(change: float) -> int:
        if change > 0:
            return 0x00FF00  # Green
        elif change < 0:
            return 0xFF0000  # Red
        return 0x0000FF  # Blue

    @staticmethod
    def format_value(value: Optional[float]) -> str:
        if value is None:
            return "N/A"
            
        abs_value = abs(float(value))
        
        if abs_value >= 1e9:
            return f"{value/1e9:.1f}B".rstrip("0").rstrip(".")
        if abs_value >= 1e6:
            return f"{value/1e6:.1f}M".rstrip("0").rstrip(".")
        if abs_value >= 1e3:
            return f"{value/1e3:.1f}K".rstrip("0").rstrip(".")
        if abs_value < 1:
            return f"{value:.6f}".rstrip("0").rstrip(".")
            
        return str(int(value)) if abs_value == int(abs_value) else f"{value:.2f}".rstrip("0").rstrip(".")

class TokenAnalyzer:
    def __init__(self, config: Config):
        self.config = config
        self.address_regex = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
        self.ticker_regex = re.compile(r"\$([^\s]{1,10})")

    @cached(TTLCache(maxsize=10_000, ttl=300))
    def validate_solana_address(self, candidate: str) -> bool:
        try:
            return len(base58.b58decode(candidate)) == 32
        except Exception:
            return False

    def get_addresses_from_content(self, content: str) -> Set[str]:
        return {addr for addr in self.address_regex.findall(content) 
                if self.validate_solana_address(addr)}

    def get_tickers_from_content(self, content: str) -> List[str]:
        return list(set(self.ticker_regex.findall(content)))

    def calculate_ath_marketcap(self, 
                              ath_price: float, 
                              current_price: float, 
                              current_fdv: float) -> Optional[float]:
        if not all([ath_price, current_price, current_fdv]):
            return None
        
        try:
            fdv_price_ratio = current_fdv / current_price
            return ath_price * fdv_price_ratio
        except ZeroDivisionError:
            return None

class EmbedBuilder:
    def __init__(self, formatter: Formatter):
        self.formatter = formatter

    def create_header_message(self, entry: Dict[str, Any]) -> str:
        try:
            base = entry["baseToken"]
            quote = entry.get("quoteToken", {})
            market_cap = self.formatter.format_value(entry.get("marketCap", 0)).replace("$", "")
            chain = entry.get("chainId", "N/A").upper()
            dex = entry.get("dexId", "N/A").title()
            
            symbol_pair = f"${base['symbol']}/{quote.get('symbol', '')}" if quote else base["symbol"]
            chain_dex = f"({chain} @ {dex})" if chain != "N/A" and dex != "N/A" else ""
            
            return f"✨ [**{base['name']}**]({entry.get('url', '#')}) **[${market_cap}]** - **{symbol_pair}** **{chain_dex}**"
        except Exception as e:
            logger.error(f"Header creation error: {e}")
            return "Token Information"

    def create_embed(self, 
                    entry: Dict[str, Any], 
                    address: str, 
                    order_status: str) -> Optional[discord.Embed]:
        try:
            # Extract core data
            change = float(entry.get("priceChange", {}).get("m5", 0))
            embed = discord.Embed(color=self.formatter.get_color_from_change(change))
            
            # Core metrics
            metrics = {
                "current_price": float(entry.get("priceUsd", 0)),
                "current_fdv": float(entry.get("fdv", 0)),
                "liquidity": float(entry.get("liquidity", {}).get("usd", 0)),
                "volume_5m": entry.get("volume", {}).get("m5", 0),
                "txns": entry.get("txns", {}).get("m5", {}),
            }
            
            # Add main fields
            self._add_price_fields(embed, metrics)
            self._add_volume_fields(embed, metrics, change)
            self._add_transaction_fields(embed, metrics)
            self._add_links_fields(embed, entry, address)
            self._add_trading_platforms(embed, entry, address)
            
            # Add images and footer
            self._add_media_and_footer(embed, entry, order_status)
            
            return embed
            
        except Exception as e:
            logger.error(f"Embed creation error: {e}")
            return None

    def _add_price_fields(self, embed: discord.Embed, metrics: Dict[str, Any]) -> None:
        embed.add_field(
            name="💰 FDV", 
            value=f"**`${self.formatter.format_value(metrics['current_fdv'])}`**", 
            inline=True
        )
        embed.add_field(
            name="💵 USD Price", 
            value=f"**`${self.formatter.format_value(metrics['current_price'])}`**", 
            inline=True
        )
        embed.add_field(
            name="💧 Liquidity", 
            value=f"**`${self.formatter.format_value(metrics['liquidity'])}`**", 
            inline=True
        )
        embed.add_field(
            name="🏆 ATH", 
            value="**`Fetching...`**", 
            inline=True
        )

    def _add_volume_fields(self, 
                          embed: discord.Embed, 
                          metrics: Dict[str, Any], 
                          change: float) -> None:
        emoji = "📉" if change < 0 else "📈"
        embed.add_field(
            name="📊 5m Volume", 
            value=f"**`${self.formatter.format_value(metrics['volume_5m'])}`**", 
            inline=True
        )
        embed.add_field(
            name=f"{emoji} 5m Change", 
            value=f"**`{self.formatter.format_value(change)}%`**", 
            inline=True
        )

    def _add_transaction_fields(self, embed: discord.Embed, metrics: Dict[str, Any]) -> None:
        txns = metrics['txns']
        buys = txns.get("buys", 0)
        sells = txns.get("sells", 0)
        
        embed.add_field(
            name="🔄 5m Transactions",
            value=f"🟢 **`{self.formatter.format_value(buys)}`** | 🔴 **`{self.formatter.format_value(sells)}`**",
            inline=False
        )

    def _add_links_fields(self, 
                         embed: discord.Embed, 
                         entry: Dict[str, Any], 
                         address: str) -> None:
        info = entry.get("info", {})
        
        # Websites
        websites = info.get("websites", [])
        if websites:
            website_links = " ".join(
                f"[{site.get('label') or 'Website'}]({site['url']})" 
                for site in websites
            )
            embed.add_field(
                name="🔗 Links",
                value=f"**Websites:** {website_links}",
                inline=False
            )
        
        # Socials
        socials = info.get("socials", [])
        if socials:
            social_links = " ".join(
                f"[{soc.get('type', 'Social').title()}]({soc['url']})" 
                for soc in socials
            )
            embed.add_field(
                name="📱 Socials",
                value=social_links,
                inline=False
            )

        # Add contract address
        embed.add_field(
            name="🔑 Contract Address",
            value=f"**`{address}`**",
            inline=False
        )

    def _add_trading_platforms(self, 
                             embed: discord.Embed, 
                             entry: Dict[str, Any], 
                             address: str) -> None:
        platforms = [
            f"[{name}]({url.format(pair=entry.get('pairAddress', address), address=address)})"
            for name, url in self.config.trading_platforms.items()
        ]
        embed.add_field(
            name="💱 Trade On",
            value=" | ".join(platforms),
            inline=False
        )

    def _add_media_and_footer(self, 
                             embed: discord.Embed, 
                             entry: Dict[str, Any], 
                             order_status: str) -> None:
        info = entry.get("info", {})
        
        # Add banner if available
        banner = info.get("header")
        if banner:
            embed.set_image(url=banner)
            
        # Add thumbnail if available
        img = info.get("imageUrl")
        if img:
            embed.set_thumbnail(url=img)
            
        # Set footer
        footer_parts = []
        
        pair_created_at = entry.get("pairCreatedAt")
        if pair_created_at:
            footer_parts.append(f"Created {DexScreenerAPI._format_relative_time(pair_created_at)} ago")
            
        footer_parts.append(order_status)
        
        boosts = entry.get("boosts", {})
        active_boosts = boosts.get("active")
        if active_boosts:
            footer_parts.append(f"🚀 {active_boosts} Boosts")
            
        embed.set_footer(text=" • ".join(footer_parts))

class MessageProcessor:
    def __init__(self, 
                 bot: CryptoBot, 
                 token_analyzer: TokenAnalyzer,
                 embed_builder: EmbedBuilder,
                 api_client: DexScreenerAPI):
        self.bot = bot
        self.token_analyzer = token_analyzer
        self.embed_builder = embed_builder
        self.api_client = api_client

    async def process_message(self, message: discord.Message) -> None:
        # Quick validation
        if not self._should_process_message(message):
            return

        content = message.content
        addresses = self.token_analyzer.get_addresses_from_content(content)
        tickers = self.token_analyzer.get_tickers_from_content(content)

        if not addresses and not tickers:
            return

        async def process_with_semaphore(coro):
            async with self.bot.processing_semaphore:
                return await coro

        tasks = []

        # Process addresses
        if addresses:
            for chunk in [list(addresses)[i:i+5] for i in range(0, len(addresses), 5)]:
                tokens_data = await self.api_client.fetch_token_data(chunk)
                if tokens_data:
                    addr_map = {
                        e["baseToken"]["address"].lower(): e 
                        for e in tokens_data
                    }
                    tasks.extend(
                        process_with_semaphore(
                            self._process_entry(message, addr_map[addr.lower()], addr)
                        )
                        for addr in chunk if addr.lower() in addr_map
                    )

        # Process tickers
        if tickers:
            tasks.extend(
                process_with_semaphore(self._process_ticker(message, ticker))
                for ticker in tickers
            )

        if tasks:
            await asyncio.gather(*tasks)

    def _should_process_message(self, message: discord.Message) -> bool:
        if message.author.bot:
            return False
            
        if self.bot.config.target_channels and message.channel.id not in self.bot.config.target_channels:
            return False
            
        content = message.content
        if not content:
            return False
            
        first_word = content.split()[0]
        if first_word in self.bot.prefix_commands:
            return False
            
        if '$' not in content and not any(c.isalnum() for c in content[:min(20, len(content))]):
            return False
            
        return True

    async def _process_entry(self, 
                           message: discord.Message, 
                           entry: Dict[str, Any], 
                           address: str) -> None:
        start_time = datetime.now().timestamp()
        
        try:
            # Get order status
            order_status = await self.api_client.fetch_order_status(address)
            
            # Create and send initial embed
            embed = self.embed_builder.create_embed(entry, address, order_status)
            if not embed:
                return
                
            response = await message.reply(
                content=self.embed_builder.create_header_message(entry),
                embed=embed,
                view=CopyAddressView(address),
                mention_author=True
            )
            
            # Update processing metrics
            self.bot.metrics.record_processing(datetime.now().timestamp() - start_time)
            
        except Exception as e:
            logger.error(f"Entry processing error: {e}")

    async def _process_ticker(self, 
                            message: discord.Message, 
                            ticker: str) -> None:
        try:
            search_data = await self.api_client.fetch_token_data([ticker])
            if not search_data or not search_data.get("pairs"):
                return
                
            pair = search_data["pairs"][0]
            address = pair["baseToken"]["address"]
            
            if address in message.content:
                return
                
            await self._process_entry(message, pair, address)
            
        except Exception as e:
            logger.error(f"Ticker processing error ${ticker}: {e}")

class Commands(commands.Cog):
    def __init__(self, bot: CryptoBot):
        self.bot = bot

    @app_commands.command(name="health", description="Show bot performance metrics")
    @app_commands.checks.cooldown(1, 5)
    async def health_slash(self, interaction: discord.Interaction) -> None:
        if interaction.user.id not in self.bot.config.allowed_users:
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True,
                delete_after=5
            )
            return

        try:
            embed = await self._create_health_embed(interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Health command error: {e}")
            await interaction.response.send_message(
                "An error occurred while processing your request.",
                ephemeral=True
            )

    async def _create_health_embed(self, user: discord.User) -> discord.Embed:
        embed = discord.Embed(
            title="Bot Health Status",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Calculate uptime
        uptime = datetime.now() - self.bot.startup_time
        days, remainder = divmod(int(uptime.total_seconds()), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Memory usage
        memory = psutil.Process().memory_info().rss / 1024 ** 2
        
        # Processing metrics
        recent_times = [
            t[0] for t in self.bot.metrics.processing_times 
            if datetime.now().timestamp() - t[1] < 3600
        ]
        
        avg_processing = sum(recent_times) / len(recent_times) if recent_times else 0
        
        # Add fields
        embed.add_field(
            name="Uptime",
            value=f"{days}d {hours}h {minutes}m {seconds}s",
            inline=True
        )
        embed.add_field(
            name="Memory Usage",
            value=f"{memory:.1f} MB",
            inline=True
        )
        embed.add_field(
            name="Tokens Processed",
            value=str(self.bot.metrics.processed_count),
            inline=True
        )
        embed.add_field(
            name="Avg Processing Time",
            value=f"{avg_processing:.2f}s",
            inline=True
        )
        embed.add_field(
            name="Server Count",
            value=str(len(self.bot.guilds)),
            inline=True
        )
        
        # Add error counts if any
        if self.bot.metrics.error_counts:
            error_text = "\n".join(
                f"{endpoint}: {count}" 
                for endpoint, count in self.bot.metrics.error_counts.items()
            )
            embed.add_field(
                name="API Errors",
                value=f"```{error_text}```",
                inline=False
            )
            
        embed.set_footer(text=f"Requested by {user.name}")
        return embed

    @app_commands.command(name="ping", description="Check bot latency")
    async def ping_slash(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"Pong! Bot latency: {latency}ms",
            ephemeral=True
        )

# UI Components
class CopyAddressView(discord.ui.View):
    def __init__(self, address: str):
        super().__init__(timeout=None)
        self.address = address
        
    @discord.ui.button(label="Copy Address", style=discord.ButtonStyle.secondary)
    async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"```{self.address}```",
            ephemeral=True,
            delete_after=60
        )

# Main application setup
def setup_bot():
    # Load configuration
    config = Config()
    
    # Initialize bot
    bot = CryptoBot(config)
    
    # Define prefix commands (empty for now but can be expanded)
    bot.prefix_commands = set()
    
    # Create formatter and token analyzer
    formatter = Formatter()
    token_analyzer = TokenAnalyzer(config)
    
    @bot.event
    async def on_ready():
        logger.info(f"Bot is ready! Logged in as {bot.user.name}")
        logger.info(f"Monitoring {len(config.target_channels)} channels")
        
        # Initialize session if not already created
        if not bot.http_session:
            bot.http_session = await bot.setup_http_session()
            
        # Set bot status
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for SOL tokens"
            )
        )
    
    @bot.event
    async def on_message(message: discord.Message):
        # Process commands first
        await bot.process_commands(message)
        
        # Skip processing if session not available
        if not bot.http_session:
            return
            
        # Initialize components if they aren't created yet
        if not hasattr(bot, "message_processor"):
            api_client = DexScreenerAPI(bot.http_session, config.base_url)
            embed_builder = EmbedBuilder(formatter)
            bot.message_processor = MessageProcessor(
                bot, token_analyzer, embed_builder, api_client
            )
            
        # Process the message
        await bot.message_processor.process_message(message)
    
    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"Command on cooldown. Try again in {error.retry_after:.1f}s.",
                delete_after=5
            )
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(
                "You don't have permission to use this command.",
                delete_after=5
            )
        else:
            logger.error(f"Command error: {error}")
    
    return bot

def main():
    try:
        # Set up and run the bot
        bot = setup_bot()
        logger.info("Starting CryptoBot...")
        bot.run(bot.config.token, log_handler=None)
    except Exception as e:
        logger.critical(f"Bot startup failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()