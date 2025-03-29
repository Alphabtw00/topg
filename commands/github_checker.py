"""
GitHub repository analysis command
"""
import asyncio
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands
from api.github_analyzer import analyze_github_repo
from ui.embeds import create_github_analysis_embed
from ui.views import GitHubAnalysisView
from utils.validators import validate_github_url
from bot.error_handler import create_error_handler
from utils.logger import get_logger

logger = get_logger()

class GithubChecker(commands.Cog):
    """GitHub repository analysis command"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="github-checker", description="Analyze a GitHub repository for legitimacy")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 15)
    async def check_repo(self, interaction: discord.Interaction, repo_url: str):
        """Analyze a GitHub repository for potential scam indicators in crypto projects"""
        
        # Validate GitHub URL format
        if not validate_github_url(repo_url):
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
        
        try:
            # Get the analysis result from the API
            result = await analyze_github_repo(self.bot.http_session, repo_url)
            
            if not result:
                return await interaction.followup.send(
                    "❌ Failed to analyze repository. Please ensure the URL is valid and try again.",
                    ephemeral=True
                )
            
            # Create embed from result data
            embed = create_github_analysis_embed(
                result['repo_info'],
                result['analysis'],
                start_time,
                interaction
            )
            
            # Create and send view with buttons
            view = GitHubAnalysisView(repo_url)
            
            await interaction.followup.send(embed=embed, view=view)
            
            self.bot.record_command_usage("github-checker")
            logger.info(f"GitHub analysis called by {interaction.user} for {repo_url}")
                
        except asyncio.TimeoutError:
            logger.warning(f"Analysis timeout for {repo_url}")
            await interaction.followup.send(
                "⌛ Analysis timed out (3+ minutes). GitHub repository analysis can take time for larger repositories. Please try again later.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Repo analysis error for {repo_url}: {str(e)}", exc_info=False)
            await interaction.followup.send(
                "❌ Failed to analyze repository. The analysis service may be experiencing issues. Please try again later.",
                ephemeral=True
            )
    
    # Register error handler
    @check_repo.error
    async def github_error(self, interaction, error):
        error_handler = create_error_handler("github-checker")
        await error_handler(self, interaction, error)