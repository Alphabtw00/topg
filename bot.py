import os
import re
import base58
import discord
import aiohttp
import logging
import asyncio
import sys
import psutil
from functools import lru_cache
from typing import Set
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import quote
from cachetools import TTLCache, cached
from discord.ext import commands
from discord import app_commands

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# # Add file handler for persistent logs
# try:
#     os.makedirs('logs', exist_ok=True)
#     file_handler = logging.FileHandler(f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log')
#     file_handler.setLevel(logging.WARNING)
#     file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
#     logger.addHandler(file_handler)
# except Exception as e:
#     logger.error(f"Failed to setup log file: {e}")

load_dotenv()

# config
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    logger.critical("DISCORD_BOT_TOKEN not found in environment")
    exit(1)
TARGET_CHANNEL_IDS = {int(id.strip()) for id in os.getenv("TARGET_CHANNEL_IDS", "").split(",") if id.strip().isdigit()}
ALLOWED_USER_IDS = {int(uid.strip()) for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip().isdigit()}
BASE_URL = "https://api.dexscreener.com"
TWITTER_SEARCH_URL = "https://x.com/search?q={query}&f=live"
TRADING_PLATFORMS = {
    "Axiom": "https://axiom.trade/meme/{pair}",
    "Photon": "https://photon-sol.tinyastro.io/en/lp/{pair}",
    "Neo BullX": "https://neo.bullx.io/terminal?chainId=1399811149&address={address}",
}
ADDRESS_REGEX = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
TICKER_REGEX = re.compile(r"\$([^\s]{1,10})")
GITHUB_URL_REGEX = re.compile(r"^https://github\.com/[a-zA-Z0-9-]+/[a-zA-Z0-9._-]+/?$")
GITHUB_ANALYSIS_CACHE = TTLCache(maxsize=100, ttl=3600)
ADDRESS_CACHE = TTLCache(maxsize=10_000, ttl=300)
MAX_ERROR_THRESHOLD = 50
error_counts = {}
MAX_CONCURRENT_PROCESSES = 5
processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROCESSES)
PREFIX_COMMANDS = {}


# Initialize bot with optimized intents
intents = discord.Intents.default()
intents.message_content = True
intents.typing = False
# Disable unnecessary intents
intents.presences = False
intents.integrations = False





#classes
class CryptoBot(commands.Bot):
    __slots__ = ("http_session", "startup_time", "processed_count", "metrics", "bg_task", "memory_task")
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_session = None
        self.startup_time = datetime.now()
        self.metrics = {
            'processed_count': 0,
            'processing_times': [],
            'last_cleanup': datetime.now().timestamp()
        }
        
    async def cleanup_metrics(self):
        """Efficient metrics cleanup using batch operations"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run hourly
                current_time = datetime.now().timestamp()
                # Batch cleanup in one operation
                self.metrics['processing_times'] = [
                    t for t in self.metrics['processing_times'][-1000:]  # Keep last 1000 entries max
                    if current_time - t[1] < 3600  # Only from last hour
                ]
                error_counts.clear()
                self.metrics['last_cleanup'] = current_time
            except Exception as e:
                logger.error(f"Metrics cleanup error: {e}")
    
    async def setup_hook(self):
        # This runs before on_ready
        self.http_session = await setup_http_session()
        self.bg_task = self.loop.create_task(self.cleanup_metrics())
        self.memory_task = self.loop.create_task(monitor_memory_usage())
        await self.add_cog(Commands(self)) #register commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
        logger.info("HTTP session initialized")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

        # Fetch channel info concurrently
        if TARGET_CHANNEL_IDS:
            async def get_channel_info(ch_id):
                channel = self.get_channel(ch_id)
                if channel is None:
                    try:
                        channel = await self.fetch_channel(ch_id)
                    except Exception as e:
                        logger.error(f"Could not fetch channel with ID {ch_id}: {e}")
                        return None
                guild_name = channel.guild.name if channel.guild else "DMs"
                return f"{channel.name} (Server: {guild_name})"

            channel_infos = await asyncio.gather(
                *[get_channel_info(ch_id) for ch_id in TARGET_CHANNEL_IDS]
            )
            channel_infos = [info for info in channel_infos if info]
            logger.info(f"Bot will respond in channels: {', '.join(channel_infos)}")
        else:
            logger.info("Bot will respond in all channels.")

        # Fetch admin user info concurrently
        if ALLOWED_USER_IDS:
            async def get_user_info(user_id):
                try:
                    user = self.get_user(int(user_id))
                    if user is None:
                        user = await self.fetch_user(int(user_id))
                    return f"{user.name}#{user.discriminator} (ID: {user.id})"
                except Exception as e:
                    logger.error(f"Could not fetch user with ID {user_id}: {e}")
                    return None

            user_infos = await asyncio.gather(
                *[get_user_info(user_id) for user_id in ALLOWED_USER_IDS]
            )
            user_infos = [info for info in user_infos if info]
            logger.info(f"Allowed admin users: {', '.join(user_infos)}")

    async def close(self):
        logger.info("Bot is shutting down...")
        if self.http_session:
            await self.http_session.close()
        await super().close()
       
bot = CryptoBot(command_prefix="!", intents=intents, help_command=None, reconnect=True)



#views
class CopyAddressView(discord.ui.View):
    __slots__ = ("address",)
    def __init__(self, address: str):
        super().__init__(timeout=None)
        self.address = address

    @discord.ui.button(label="📋", style=discord.ButtonStyle.grey, custom_id="copy_address", row=0)
    async def copy_address(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_message(self.address, ephemeral=True)
        await asyncio.sleep(30)
        await interaction.delete_original_response()

class GitHubAnalysisView(discord.ui.View):
    __slots__ = ("repo_url",)
    def __init__(self, repo_url: str):
        super().__init__(timeout=None)
        self.repo_url = repo_url
        self.add_item(discord.ui.Button(label="View Repository", url=repo_url))
        self.add_item(discord.ui.Button(
            label="Reanalyze", 
            style=discord.ButtonStyle.gray, 
            custom_id="reanalyze_repo"
        ))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "reanalyze_repo":
            # Clear this repo from cache to force reanalysis
            GITHUB_ANALYSIS_CACHE.pop(self.repo_url, None)
            await interaction.response.send_message("Repository will be reanalyzed on next check.", ephemeral=True)
        return True



#commands
class Commands(commands.Cog):
    def __init__(self, bot: CryptoBot):
        self.bot = bot
    
    @app_commands.command(name="health", description="Show bot performance metrics")
    @app_commands.checks.cooldown(1, 5)
    async def health_slash(self, interaction: discord.Interaction):
        """Health check command (slash version)"""
        if interaction.user.id not in ALLOWED_USER_IDS:
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True,
                delete_after=5
            )
            return

        try:
            embed = await self.health_logic(interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Health command error: {e}")

    async def health_logic(self, user: discord.User) -> discord.Embed:
        """Centralized logic for health command with user-specific features"""
        current_time = datetime.now().timestamp()
        recent_times = [
            t[0] for t in self.bot.metrics['processing_times'] 
            if current_time - t[1] < 3600
        ]
        avg_req_time = sum(recent_times) / len(recent_times) if recent_times else 0

        embed = discord.Embed(
            title="🤖 Bot Health Monitor",
            color=0x6BA1FF,
            timestamp=datetime.now()
        )

        # Performance Metrics
        embed.add_field(
            name="🚀 Performance",
            value=(
                f"Uptime: **`{str(datetime.now() - self.bot.startup_time).split('.')[0]}`**\n"
                f"Latency: **`{self.bot.latency * 1000:.1f}ms`**\n"
                f"Memory: **`{psutil.Process().memory_info().rss / 1024 ** 2:.1f}MB`**\n"
                f"Response: **`{avg_req_time:.2f}s`**"
            ),
            inline=True
        )

        # Activity Metrics
        embed.add_field(
            name="📈 Activity",
            value=(
                f"Processed: **`{self.bot.metrics['processed_count']:,}`**\n"
                f"Errors: **`{sum(error_counts.values()):,}`**\n"
                f"Last Cleanup: **`{relative_time(self.bot.metrics['last_cleanup'] * 1000, include_ago=True)}`**"
            ),
            inline=True
        )

        # System Health
        cpu_usage = psutil.cpu_percent()
        mem_usage = psutil.virtual_memory().percent
        embed.add_field(
            name="🖥️ System Health",
            value=(
                f"CPU: **`{cpu_usage}%`** {self._progress_bar(cpu_usage)}\n"
                f"RAM: **`{mem_usage}%`** {self._progress_bar(mem_usage)}\n"
                f"Tasks: **`{len(asyncio.all_tasks())}`**"
            ),
            inline=False
        )

        embed.set_footer(
            text=f"Requested by {user.display_name}",
            icon_url=user.display_avatar.url
        )

        return embed
    
    def _progress_bar(self, percentage: float) -> str:
        """Create a color-coded progress bar"""
        bars = 10
        filled = int(round(percentage / 100 * bars))
        color = (
            "🟢" if percentage < 50 else
            "🟡" if percentage < 75 else
            "🔴"
        )
        return f"{color} {'█' * filled}{'░' * (bars - filled)}"
    




    @app_commands.command(name="github-checker", description="Analyze a GitHub repository for legitimacy")
    @app_commands.checks.cooldown(1, 15)
    async def check_repo(self, interaction: discord.Interaction, repo_url: str):
        """Analyze a GitHub repository for potential scam indicators in crypto projects"""
        
        # Validate GitHub URL format
        if not GITHUB_URL_REGEX.match(repo_url):
            return await interaction.response.send_message(
                "❌ Invalid GitHub repository URL. Format should be: https://github.com/username/repository", 
                ephemeral=True,
                delete_after=5
            )
        
        # Remove trailing slash if present for consistency
        repo_url = repo_url.rstrip("/")
        
        await interaction.response.defer(thinking=True)
        
        # Record start time for metrics
        start_time = datetime.now().timestamp()
        
        # Check cache first - efficient memory usage
        if repo_url in GITHUB_ANALYSIS_CACHE:
            logger.info(f"Serving cached analysis for {repo_url}")
            cached_data = GITHUB_ANALYSIS_CACHE[repo_url]
            
            # Create embed from cached data
            embed = self._create_embed(
                cached_data['repo_info'],
                cached_data['analysis'],
                start_time,
                interaction
            )
            
            return await interaction.followup.send(
                embed=embed, 
                view=GitHubAnalysisView(repo_url)
            )
        
        try:
            # Make the API request
            async with self.bot.http_session.post(
                "http://localhost:3000/api/analyze",
                json={"repoUrl": repo_url},
                timeout=180  # Increased timeout for large repos
            ) as response:
                if response.status != 200:
                    logger.error(f"API error: Status {response.status} for {repo_url}")
                    return await interaction.followup.send(
                        f"⚠️ Analysis service returned error code {response.status}. This could be due to service overload or an invalid repository.",
                        ephemeral=True
                    )
                
                data = await response.json()
                
                if not data.get("success"):
                    error_msg = data.get('error', 'Unknown error')
                    logger.error(f"API reported failure for {repo_url}: {error_msg}")
                    return await interaction.followup.send(
                        f"⚠️ Analysis failed: {error_msg}",
                        ephemeral=True
                    )
                
                # Extract core data
                result = data["result"]
                
                # Extract repository info and analysis
                repo_info = self._extract_repo_info(result)
                analysis = result["analysis"]
                
                # Cache the repository info and analysis (not the embed)
                GITHUB_ANALYSIS_CACHE[repo_url] = {
                    'repo_info': repo_info,
                    'analysis': analysis,
                    'timestamp': datetime.now()
                }
                
                # Create the embed
                embed = self._create_embed(repo_info, analysis, start_time, interaction)
                
                # Update metrics
                self.bot.metrics['processed_count'] += 1
                self.bot.metrics['processing_times'].append((datetime.now().timestamp() - start_time, datetime.now().timestamp()))
                
                # Create and send view with buttons
                view = GitHubAnalysisView(repo_url)
                await interaction.followup.send(embed=embed, view=view)
                    
        except asyncio.TimeoutError:
            logger.error(f"Analysis timeout for {repo_url}")
            await interaction.followup.send(
                "⌛ Analysis timed out (3+ minutes). GitHub repository analysis can take time for larger repositories. Please try again later.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Repo analysis error for {repo_url}: {str(e)}")
            error_counts[str(e)] = error_counts.get(str(e), 0) + 1
            await interaction.followup.send(
                "❌ Failed to analyze repository. Please ensure the URL is valid and try again. If the problem persists, the analysis service may be experiencing issues.",
                ephemeral=True
            )

    def _extract_repo_info(self, result):
        """Extract repository info from API result, handling both cached and non-cached responses"""
        repo_info = {}
        
        if "repoDetails" in result:
            # First-time API response with full details
            repo_details = result["repoDetails"]
            
            repo_info["name"] = repo_details.get("name", "Unknown")

            owner = repo_details.get("owner", {})
            repo_info["owner"] = owner.get("login", "Unknown")
            repo_info["owner_avatar"] = owner.get("avatar_url", "https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png")
            
            # Repository stats
            repo_info["stars"] = repo_details.get("stargazers_count", 0)
            repo_info["forks"] = repo_details.get("forks_count", 0)
            repo_info["watchers"] = repo_details.get("watchers_count", 0)
            repo_info["open_issues"] = repo_details.get("open_issues_count", 0)
            repo_info["language"] = repo_details.get("language", "Unknown")
            repo_info["size"] = repo_details.get("size", 0)
            
            # Dates
            repo_info["created_at"] = repo_details.get("created_at", "Unknown")
            repo_info["updated_at"] = repo_details.get("updated_at", "Unknown")
            
            # License
            license_info = repo_details.get("license", {})
            repo_info["license"] = license_info.get("name", "No license") if license_info else "No license"
        
        else:
            # Cached API response with limited details - extract what we can
            repo_info["name"] = result.get("repoName", "Unknown")
            repo_info["owner"] = result.get("owner", "Unknown")
            repo_info["stars"] = result.get("stars", 0)
            repo_info["forks"] = result.get("forks", 0)
            repo_info["language"] = result.get("language", "Unknown")
            
            # Set defaults for missing fields
            repo_info["owner_avatar"] = "https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png"
            repo_info["watchers"] = 0
            repo_info["open_issues"] = 0
            repo_info["size"] = 0
            repo_info["created_at"] = "Unknown"
            repo_info["updated_at"] = "Unknown"
            repo_info["license"] = "Unknown"
        
        return repo_info

    def _create_embed(self, repo_info, analysis, start_time, interaction):
        """Create a consistent embed from repository info and analysis"""
        # Core metrics - most important data
        legitimacy_score = analysis.get("finalLegitimacyScore", 0)
        trust_score = analysis.get("trustScore", 0)
        detailed_scores = analysis.get("detailedScores", {})
        code_review = analysis.get("codeReview", {})
        ai_analysis = code_review.get("aiAnalysis", {})
        
        # Determine verdict and color - clear visual indicator
        if legitimacy_score >= 75:
            embed_color = 0x00FF00  # Green
            verdict = "LIKELY LEGITIMATE"
            verdict_emoji = "✅"
        elif legitimacy_score >= 50:
            embed_color = 0xFFD700  # Gold
            verdict = "EXERCISE CAUTION"
            verdict_emoji = "⚠️"
        else:
            embed_color = 0xFF0000  # Red
            verdict = "HIGH RISK"
            verdict_emoji = "🚨"
        
        # Format repository name
        repo_name = repo_info["name"]
        owner = repo_info["owner"]
        
        # Create main embed
        embed = discord.Embed(
            title=f"GitHub Analysis: {owner}/{repo_name}",                   
            url=f"https://github.com/{owner}/{repo_name}",
            color=embed_color,
            timestamp=datetime.now()
        )
        
        # GitHub logo
        embed.set_author(
            name="GitHub Repository Analyzer", 
            icon_url="https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png"
        )

        # Owner avatar
        embed.set_thumbnail(url=repo_info["owner_avatar"])
        
        # Top summary section with verdict
        embed.description = (
            f"## {verdict_emoji} VERDICT: {verdict} {verdict_emoji}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{analysis.get('summary', 'No summary available')}"
        )
                    
        # --- SCORE SECTION (MOST IMPORTANT) ---
        # Format scores as progress bars for visual clarity
        code_quality = detailed_scores.get("codeQuality", 0)
        project_structure = detailed_scores.get("projectStructure", 0)
        implementation = detailed_scores.get("implementation", 0)
        documentation = detailed_scores.get("documentation", 0)
        ai_score = ai_analysis.get("score", 0)
        overall_score = (code_quality + project_structure + implementation + documentation) / 4
        
        # Overall assessment
        embed.add_field(
            name="🛡️ Overall Assessment",
            value=(
                f"**Legitimacy Score:** {self._score_bar(legitimacy_score)} `{legitimacy_score}%`\n"
                f"**Trust Score:** {self._score_bar(trust_score)} `{trust_score}%`\n"
                f"**AI Implementation:** {self._score_bar(ai_score)} `{ai_score}%`\n"
                f"**Average Score:** {self._score_bar(overall_score)} `{overall_score:.0f}%`\n"
            ),
            inline=False
        )
        
        # Detailed scores
        embed.add_field(
            name="📚 Technical Quality",
            value=(
                f"**Code Quality:** {self._score_bar(code_quality*4)} `{code_quality}/25`\n"
                f"**Project Structure:** {self._score_bar(project_structure*4)} `{project_structure}/25`\n"
                f"**Implementation:** {self._score_bar(implementation*4)} `{implementation}/25`\n"
                f"**Documentation:** {self._score_bar(documentation*4)} `{documentation}/25`"
            ),
            inline=False
        )


        # Investment assessment 
        ranking = code_review.get("investmentRanking", {})
        rating = ranking.get("rating", "N/A")
        confidence = ranking.get("confidence", 0)
        
        rating_emoji = {
            "Strong Buy": "🟢", 
            "Buy": "🟢",
            "High": "🟢",
            "Medium": "🟡",
            "Hold": "🟡", 
            "Sell": "🔴",
            "Strong Sell": "🔴",
            "Low": "🔴"
        }.get(rating, "⚪")
        
        embed.add_field(
            name="💰 Investment Rating",
            value=(
                f"**Rating:** {rating_emoji} `{rating}`\n"
                f"**Confidence:** {self._score_bar(confidence)} `{confidence}%`\n"
            ),
            inline=False
        )
        

        # Enhanced repo info with more details
        created_date = format_date(repo_info.get("created_at"))
        updated_date = format_date(repo_info.get("updated_at"))
        size = format_size(repo_info.get("size"))

        # Group basic repository details under "General Info"
        general_info = "\n".join([
            f"**Primary Language:** `{repo_info.get('language')}`",
            f"**License:** `{repo_info.get('license')}`",
            f"**Size:** `{size}`",
            f"**Created:** `{created_date}`",
            f"**Updated:** `{updated_date}`",
        ])

        # Group engagement metrics under "Community Stats"
        community_stats = "\n".join([
            f"**Owner:** [{repo_info.get('owner')}](https://github.com/{repo_info.get('owner', 'Unknown')})",
            f"**Stars:** `{repo_info.get('stars'):,}`",
            f"**Forks:** `{repo_info.get('forks'):,}`",
            f"**Watchers:** `{repo_info.get('watchers'):,}`",
            f"**Open Issues:** `{repo_info.get('open_issues'):,}`",
        ])

        # Add two inline fields to the embed with the new headings
        embed.add_field(
            name="📁 Repo Info",
            value=general_info,
            inline=True
        )
        embed.add_field(
            name="⭐ Community Stats",
            value=community_stats,
            inline=True
        )
                
        # Red flags
        red_flags = code_review.get("redFlags", [])
        if red_flags:
            flags_formatted = "\n".join(f"📉 {flag}" for flag in red_flags[:3])
            embed.add_field(
                name="🚩 Security Concerns",
                value=flags_formatted if flags_formatted else "No significant issues detected",
                inline=False
            )
        
        # Key insights
        reasoning = ranking.get("reasoning", [])
        if reasoning:
            insights_text = "\n".join(f"✔ {item}" for item in reasoning[:3])
            
            if insights_text:
                embed.add_field(
                    name="⚡ Key Insights",
                    value=insights_text,
                    inline=False
                )

        # AI implementation 
        if ai_analysis.get("hasAI", False):
            ai_components = ai_analysis.get("components", [])
            if ai_components:
                ai_features = [
                    comp for comp in ai_components 
                    if not comp.startswith("Areas for improvement:") and "improvement" not in comp.lower() and not comp.startswith("-")
                ]
                
                if ai_features:
                    ai_text = "\n".join(f"🔹 {feature}" for feature in ai_features[:3])
                    
                    embed.add_field(
                        name="🤖 AI Implementation",
                        value=ai_text,
                        inline=False
                    )
        
        # Overall assessment
        if code_review.get("overallAssessment"):
            assessment = code_review.get("overallAssessment")
            
            # Split into paragraphs and get just the first one for brevity
            paragraphs = assessment.split("\n\n")
            first_paragraph = paragraphs[0]
            
            embed.add_field(
                name="👨‍💻 Expert Opinion",
                value=f"> {first_paragraph}",
                inline=False
            )
        
        # Footer
        embed.set_footer(
            text=f"Requested by {interaction.user.display_name} • ⌛Analysis Time: {(datetime.now().timestamp() - start_time):.1f}s", 
            icon_url=interaction.user.display_avatar.url
        )
        
        return embed
    
    def _score_bar(self, percentage: float) -> str:
        """Create a visual score bar for better readability"""
        if percentage <= 0:
            return "⬜⬜⬜⬜⬜"
        
        # Calculate filled and empty blocks
        filled = min(5, max(0, round(percentage / 20)))
        
        # Determine color based on score
        if percentage >= 80:
            filled_char = "🟩"
        elif percentage >= 60:
            filled_char = "🟨"
        elif percentage >= 40:
            filled_char = "🟧"
        else:
            filled_char = "🟥"
        
        # Create bar with appropriate coloring
        return filled_char * filled + "⬜" * (5 - filled)
    
    def create_error_handler(command_name):
        async def error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
            if isinstance(error, app_commands.CommandOnCooldown):
                await interaction.response.send_message(
                    f"Command on cooldown. Try again in {error.retry_after:.1f}s",
                    ephemeral=True,
                    delete_after=5
                )
            else:
                logger.error(f"{command_name} command error: {str(error)}")
                try:
                    await interaction.response.send_message(
                        "An error occurred while processing this command.",
                        ephemeral=True,
                        delete_after=5
                    )
                except:
                    # If response was already sent, use followup
                    await interaction.followup.send(
                        "An error occurred while processing this command.",
                        ephemeral=True
                    )
        return error_handler

    check_repo.error(create_error_handler("github-checker"))
    health_slash.error(create_error_handler("health"))






#optimization helper
async def setup_http_session():
    # Optimize connection settings for many concurrent requests
    connector = aiohttp.TCPConnector(
        limit=50,         # Maximum number of concurrent connections
        ttl_dns_cache=300,  # Cache DNS results for 5 minutes
        use_dns_cache=True,
        ssl=True         
    )
    timeout = aiohttp.ClientTimeout(
        total=15,
        connect=5,
        sock_connect=5,
        sock_read=10
    )
    
    return aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers={
            "User-Agent": "DiscordCryptoBot/1.0",
            "Accept": "application/json",
            "Connection": "keep-alive"
        }
    )

async def monitor_memory_usage(threshold_mb=300): #increase threshold if needed more storage, rn the main storage is caching verifying solana adresses
    while True:
        memory = psutil.Process().memory_info().rss / 1024 ** 2  # Get memory usage in MB
        if memory > threshold_mb:
            logger.warning(f"Memory cleanup triggered at {memory:.1f}MB")
            # Force garbage collection
            import gc
            gc.collect()
            # Clear caches
            ADDRESS_CACHE.clear()
        await asyncio.sleep(300)  # Check every 5 minutes
        
        
        
        




#response helper
def format_size(size_kb):
    """Convert size in KB to a human-readable format (KB, MB, or GB)."""
    try:
        size = float(size_kb)
    except (ValueError, TypeError):
        return "Unknown"
    if size < 1024:
        return f"{size:.0f} KB"
    elif size < 1024 * 1024:
        size_mb = size / 1024
        return f"{size_mb:.2f} MB"
    else:
        size_gb = size / (1024 * 1024)
        return f"{size_gb:.2f} GB"

def format_date(date_str):
    """Return a formatted date string or 'Unknown' if not available."""
    if not date_str or date_str == "Unknown":
        return "Unknown"
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except Exception:
        return date_str

def get_color_from_change(change: float) -> int:
    if change > 0:
        return 0x00FF00  #green
    elif change < 0:
        return 0xFF0000  #red
    else:
        return 0x0000FF  # Blue

def format_value(value) -> str:
    if value is None:
        return "N/A"
        
    value = float(value)
    abs_value = abs(value)
    
    if abs_value >= 1e9:
        return f"{value / 1e9:.1f}".rstrip("0").rstrip(".") + "B"
    if abs_value >= 1e6:
       return f"{value / 1e6:.1f}".rstrip("0").rstrip(".") + "M"
    if abs_value >= 1e3:
        return f"{value / 1e3:.1f}".rstrip("0").rstrip(".") + "K"
    if abs_value < 1:
        # Handle small values efficiently
        return f"{value:.6f}".rstrip('0').rstrip('.')
    
    # Format normal values efficiently
    if abs_value == int(abs_value):
        return str(int(value))
    return f"{value:.2f}".rstrip('0').rstrip('.')

def relative_time(timestamp, include_ago=False) -> str:
    try:
        delta = datetime.now() - datetime.fromtimestamp(timestamp / 1000)
        
        if delta.seconds <= 5 and delta.days == 0:
            return "Just now"
            
        # Format the time unit
        if delta.days >= 365:
            time_str = f"{delta.days//365}y"
        elif delta.days > 30:
            time_str = f"{delta.days//30}mo"
        elif delta.days:
            time_str = f"{delta.days}d"
        elif delta.seconds >= 3600:
            time_str = f"{delta.seconds//3600}h"
        elif delta.seconds >= 60:
            time_str = f"{delta.seconds//60}m"
        else:
            time_str = f"{delta.seconds}s"
        
        return f"{time_str} ago" if include_ago else time_str
    except Exception:
        return "N/A"

@cached(ADDRESS_CACHE)
def validate_solana_address(candidate: str) -> bool:
    try:
        return len(base58.b58decode(candidate)) == 32
    except Exception:
        return False

def calculate_ath_marketcap(ath_price: float, current_price: float, current_fdv: float) -> float:
    """Calculate ATH market cap based on ATH price and current FDV"""
    if not ath_price or not current_price or not current_fdv:
        return None
    
    try:
        fdv_price_ratio = current_fdv / current_price
        return ath_price * fdv_price_ratio
    except ZeroDivisionError:
        return None

def get_addresses_from_content(content: str) -> Set[str]:
    return {addr for addr in ADDRESS_REGEX.findall(content) if validate_solana_address(addr)}

def get_tickers_from_content(content: str) -> Set[str]:
    return list(set(TICKER_REGEX.findall(content)))

def create_header_message(entry: dict) -> str:
    try:
        base = entry["baseToken"]
        quote = entry.get("quoteToken", {})
        market_cap = format_value(entry.get("marketCap", 0)).replace("$", "")
        chain = entry.get("chainId", "N/A").upper()
        dex = entry.get("dexId", "N/A").title()
        symbol_pair = f"${base['symbol']}/{quote.get('symbol', '')}" if quote else base["symbol"]
        chain_dex = f"({chain} @ {dex})" if chain != "N/A" and dex != "N/A" else ""
        return f"✨ [**{base['name']}**]({entry.get('url', '#')}) **[${market_cap}]** - **{symbol_pair}** **{chain_dex}**"
    except Exception as e:
        logger.error(f"Header error: {e}")
        return "Token Information"

def create_embed(entry: dict, address: str, order_status: str) -> discord.Embed:
    try:
        # Extract core data once to avoid repeated dictionary lookups
        change = float(entry.get("priceChange", {}).get("m5", 0))
        embed = discord.Embed(color=get_color_from_change(change))
        
        # Extract data once to avoid repeated lookups
        current_price = float(entry.get("priceUsd", 0))
        current_fdv = float(entry.get("fdv", 0))
        liquidity = float(entry.get("liquidity", {}).get("usd", 0))
        volume_5m = entry.get("volume", {}).get("m5", 0)
        txns = entry.get("txns", {}).get("m5", {})
        buys = txns.get("buys", 0)
        sells = txns.get("sells", 0)
        pair_created_at = entry.get("pairCreatedAt")
        
        # Prices section
        embed.add_field(name="💰 FDV", value=f"**`${format_value(current_fdv)}`**", inline=True)
        embed.add_field(name="💵 USD Price", value=f"**`${format_value(current_price)}`**", inline=True)
        embed.add_field(name="💧 Liquidity", value=f"**`${format_value(liquidity)}`**", inline=True)
        
        # ATH placeholder - will be updated asynchronously
        embed.add_field(name="🏆 ATH", value="**`Fetching...`**", inline=True)
        
        # Changes section
        emoji = "📉" if change < 0 else "📈"
        embed.add_field(name="📊 5m Volume", value=f"**`${format_value(volume_5m)}`**", inline=True)
        embed.add_field(name=f"{emoji} 5m Change", value=f"**`{format_value(change)}%`**", inline=True)
        # embed.add_field(name="\u200b", value="\u200b", inline=True)
        
        # Transactions
        embed.add_field(
            name="🔄 5m Transactions",
            value=f"🟢 **`{format_value(buys)}`** | 🔴 **`{format_value(sells)}`**",
            inline=False,
        )
        
        # Links section - efficiently build the links
        info = entry.get("info", {})
        links = []
        
        # Websites
        websites = info.get("websites", [])
        if websites:
            links.append("**Websites:** " + " ".join(f"[{site.get('label') or 'Website'}]({site['url']})" for site in websites))
        
        # Socials
        socials = info.get("socials", [])
        if socials:
            links.append("**Socials:** " + " ".join(f"[{soc.get('type', 'Social').title()}]({soc['url']})" for soc in socials))
        
        # Chart
        links.append(f"**Chart:** [DEX]({entry.get('url', '#')})")
        
        if links:
            embed.add_field(name="🔗 Links", value="\n".join(links), inline=False)
        
        # Twitter search
        base_token = entry.get('baseToken', {})
        symbol = base_token.get('symbol', '')
        embed.add_field(
            name="👀 Twitter Search",
            value=f"[CA]({TWITTER_SEARCH_URL.format(query=address)})       [TICKER]({TWITTER_SEARCH_URL.format(query=quote(f'${symbol}'))})",
            inline=False
        )
        
        # Contract address
        embed.add_field(name="🔑 Contact Address", value=f"**`{address}`**", inline=False)
        
        # Trading platforms
        platforms = [f"[{name}]({url.format(pair=entry.get('pairAddress', address), address=address)})" 
                     for name, url in TRADING_PLATFORMS.items()]
        embed.add_field(name="💱 Trade On", value=" | ".join(platforms), inline=False)
        
        # Banner
        banner = info.get("header")
        if banner:
            embed.set_image(url=banner)
        
        # Footer
        footer_parts = []
        if pair_created_at:
            footer_parts.append(f"Created {relative_time(pair_created_at, include_ago=True)}")
        
        # Order status
        footer_parts.append(order_status)
        
        # Active boosts
        boosts = entry.get("boosts", {})
        active_boosts = boosts.get("active")
        if active_boosts:
            footer_parts.append(f"🚀 {active_boosts} Boosts")
            
        embed.set_footer(text=" • ".join(footer_parts))
        
        # Thumbnail
        img = info.get("imageUrl")
        if img:
            embed.set_thumbnail(url=img)
            
        return embed
    except Exception as e:
        logger.error(f"Embed error: {e}")
        return None






#api logic
async def fetch_data(session: aiohttp.ClientSession, url: str, max_retries=2):
    endpoint = url.split('/')[3]
    for attempt in range(max_retries + 1):
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_counts[endpoint] = error_counts.get(endpoint, 0) + 1
                    if error_counts[endpoint] > MAX_ERROR_THRESHOLD:
                        logger.critical(f"Endpoint {endpoint} experiencing high error rate")
                        
                    if response.status == 429:  # Rate limited
                        if attempt < max_retries:
                            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
                            continue
                    
                    logger.warning(f"API returned status {response.status} for URL: {url}")
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {url} (attempt {attempt+1}/{max_retries+1})")
            if attempt < max_retries:
                await asyncio.sleep(0.5)  # Short delay before retry
                continue
        except Exception as e:
            logger.error(f"Fetch error: {e} for URL: {url}")
            return None
    return None

async def get_all_time_high(session: aiohttp.ClientSession, pair_address: str, creation_timestamp: int = None) -> tuple:
    try:
        # Determine appropriate time period based on token age
        current_time = int(datetime.now().timestamp() * 1000)
        token_age = current_time - (creation_timestamp or 0)
        
        # Select period granularity based on token age - optimized for accuracy
        # For new tokens (1-3 hours), use 1min granularity to get precise ATH
        if token_age < 1 * 60 * 60 * 1000:  
            period = "1min"
        elif token_age < 5 * 60 * 60 * 1000:  
            period = "5min"
        elif token_age < 15 * 60 * 60 * 1000:  # 8 to 24 hours
            period = "15min"
        elif token_age < 3 * 24 * 60 * 60 * 1000:  # 1 day to 3 days
            period = "1h"
        elif token_age < 7 * 24 * 60 * 60 * 1000:  # 3 days to 7 days
            period = "2h"
        elif token_age < 14 * 24 * 60 * 60 * 1000:  # 7 days to 14 days
            period = "4h"
        elif token_age < 70 * 24 * 60 * 60 * 1000:  # 14 days to 1 month (approx. 30 days)
            period = "1d"
        elif token_age < 365 * 24 * 60 * 60 * 1000:  # 1 month to 1 year (approx. 365 days)
            period = "7d"
        else:  # Older than 1 year
            period = "30d"
            
        # Always request the maximum number of candles (1000)
        # This ensures we don't miss any potential ATH within the API's limit
        url = f"https://production-api.mobula.io/api/1/market/history/pair?address={pair_address}&blockchain=solana&period={period}"
        data = await fetch_data(session, url)
        
        if not data or not data.get("data"):
            return None, None
            
        # Find ATH using max() with key function - more efficient than iterating manually
        valid_candles = [c for c in data["data"] if c.get("high") is not None]
        if not valid_candles:
            return None, None
            
        ath_candle = max(valid_candles, key=lambda x: x["high"])
        return ath_candle["high"], ath_candle["time"]
        
    except Exception as e:
        logger.error(f"ATH fetch error for {pair_address}: {e}")
        return None, None

async def get_order_status(session: aiohttp.ClientSession, token_address: str) -> str:
    try:
        url = f"{BASE_URL}/orders/v1/solana/{token_address}"
        data = await fetch_data(session, url)
        
        if data is None:
            return ""
        
        if not data:  # []
            return "❌ Dex Not Paid"
        for order in data:
            if order.get("type") == "tokenProfile":
                status = order.get("status")
                if status == "approved":
                    timestamp = order.get("paymentTimestamp")
                    time_ago = f" ({relative_time(timestamp, include_ago=True)})" if timestamp else ""
                    return f"✅ Dex Paid{time_ago}"
                elif status == "on-hold":
                    return "⏳ Dex On Hold"
        return "❌ Dex Not Paid"
    
    except Exception as e:
        logger.error(f"Order status error for {token_address}: {e}")
        return "❗ Dex Error"


#api helper
async def process_entry(message: discord.Message, session: aiohttp.ClientSession, entry: dict, address: str):    
    start_time = datetime.now().timestamp()
    try:
        # Start all API calls concurrently
        order_status_task = asyncio.create_task(get_order_status(session, address))
        
        # Initial embed with "Fetching..." for ATH
        initial_embed = create_embed(entry, address, "Fetching...")
        if not initial_embed:
            return
            
        # Send initial response
        response = await message.reply(
            content=create_header_message(entry),
            embed=initial_embed,
            view=CopyAddressView(address),
            mention_author=True
        )
        
        # Get core data for later use
        pair_address = entry.get("pairAddress")
        creation_timestamp = entry.get("pairCreatedAt")
        current_price = float(entry.get("priceUsd", 0))
        current_fdv = float(entry.get("fdv", 0))
        
        # Start ATH fetch in parallel with order status
        ath_task = None
        if pair_address:
            ath_task = asyncio.create_task(get_all_time_high(session, pair_address, creation_timestamp))
        
        # Wait for order status to complete
        order_status = await order_status_task
        
        # Update embed with order status first
        embed_dict = initial_embed.to_dict()
        
        # Update footer with order status
        footer_text = embed_dict.get("footer", {}).get("text", "")
        footer_parts = footer_text.split(" • ")
        for i, part in enumerate(footer_parts):
            if "Dex" in part or "Fetching" in part:
                footer_parts[i] = order_status
                break
        else:
            footer_parts.append(order_status)
        
        embed_dict["footer"] = {"text": " • ".join(footer_parts)}
        
        # If we have ATH task running, wait for it and update
        if ath_task:
            # Await ATH result
            ath_price, ath_timestamp = await ath_task
            
            if ath_price:
                # Calculate ATH market cap
                ath_mcap = calculate_ath_marketcap(ath_price, current_price, current_fdv)
                
                # Format time ago
                time_delta = datetime.now().timestamp() * 1000 - ath_timestamp
                time_display = relative_time(ath_timestamp, include_ago=True)
                
                # Update the ATH field
                for field in embed_dict["fields"]:
                    if field["name"] == "🏆 ATH":
                        field["value"] = f"**`${format_value(ath_mcap)}` [{time_display}]**"
                        break
            else:
                # Update with N/A if ATH data couldn't be fetched
                for field in embed_dict["fields"]:
                    if field["name"] == "🏆 ATH":
                        field["value"] = "**`N/A`**"
                        break
        
        await response.edit(embed=discord.Embed.from_dict(embed_dict))
         
        bot.metrics['processed_count'] += 1
        bot.metrics['processing_times'].append(
            (datetime.now().timestamp() - start_time, start_time)
        )       
    except Exception as e:
        logger.error(f"Processing error: {e}")
        logger.error(f"Error details: {str(e)}")

async def process_ticker(message: discord.Message, session: aiohttp.ClientSession, ticker: str):
    try:
        search_data = await fetch_data(session, f"{BASE_URL}/latest/dex/search?q={ticker}")
        if not search_data or not search_data.get("pairs"):
            return
        
        pair = search_data["pairs"][0]
        address = pair["baseToken"]["address"] 
        if address in message.content: #robust error down, use better one instead of string matching from message input
            return
        await process_entry(message, session, pair, address)
    except Exception as e:
        logger.error(f"Ticker error ${ticker}: {e}")




#bot events
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or (TARGET_CHANNEL_IDS and message.channel.id not in TARGET_CHANNEL_IDS):
        return
    
    first_word = message.content.split()[0] if message.content else ''
    if first_word in PREFIX_COMMANDS:
        #turn on when needed prefix commands
        # await bot.process_commands(message)
        return
    
    content = message.content
    # Quick check to see if we should process this message
    if '$' not in content and not any(c.isalnum() for c in content[:min(20, len(content))]):
        return
        
    # Extract addresses and tickers
    addresses = get_addresses_from_content(content)
    tickers = get_tickers_from_content(content)
    
    
    if not addresses and not tickers:
        return

    session = bot.http_session
    if not session:
        return

    async def process_with_semaphore(coro):
        async with processing_semaphore:
            return await coro

    tasks = []

    if addresses:
        # Process addresses in chunks to avoid URL length limits
        for chunk in [list(addresses)[i:i+5] for i in range(0, len(addresses), 5)]:
            tokens_data = await fetch_data(session, f"{BASE_URL}/tokens/v1/solana/{','.join(chunk)}")
            if tokens_data:
                addr_map = {e["baseToken"]["address"].lower(): e for e in tokens_data}
                tasks.extend(
                    process_with_semaphore(process_entry(message, session, addr_map[addr.lower()], addr))
                    for addr in chunk if addr.lower() in addr_map
                )

    if tickers:
        tasks.extend(
            process_with_semaphore(process_ticker(message, session, ticker)) 
            for ticker in tickers
        )

    if tasks:
        await asyncio.gather(*tasks)

@bot.event
async def on_error(event, *args, **kwargs):
    if event == 'on_message':
        logger.error(f"Error in {event}: {sys.exc_info()}")
    else:
        logger.error(f"Unhandled error in {event}: {sys.exc_info()}")
        
@bot.event
async def on_disconnect():
    logger.warning("Bot disconnected from Discord. Attempting to reconnect...")       

if __name__ == "__main__":
    try:
        logger.info("Starting bot...")
        bot.run(TOKEN, log_handler=None, reconnect=True)  # Disable Discord.py's own logging handler
    except Exception as e:
        logger.critical(f"Failed to start bot: {e}")
        exit(1)