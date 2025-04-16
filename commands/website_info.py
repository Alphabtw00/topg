"""
Website analysis command - Check a crypto project website
"""
import asyncio
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands
from utils.validators import validate_url
from bot.error_handler import create_error_handler
from urllib.parse import urlparse
from utils.logger import get_logger
from ui.views import WebsiteAnalysisView
from ui.embeds import _create_website_embed
import io 

logger = get_logger()

class WebsiteChecker(commands.Cog):
    """Website analysis command for crypto projects"""
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("WebsiteChecker cog initialized")
    
    @app_commands.command(name="website-info", description="Analyze a project website")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 15)  # 15 seconds cooldown
    async def check_website(self, interaction: discord.Interaction, website_url: str):
        """
        Analyze a website for crypto project legitimacy
        
        Args:
            interaction: Discord interaction
            website_url: Website URL to analyze
        """
        # Validate URL format
        if not validate_url(website_url):
            return await interaction.response.send_message(
                "❌ Invalid URL format. Please enter a valid website URL.",
                ephemeral=True
            )
        
        # Defer response to allow time for processing
        await interaction.response.defer(thinking=True)
        
        # Record start time for metrics
        start_time = datetime.now().timestamp()
        
        try:
            # Use the website analyzer from the services provider
            result = await self.bot.services.website_analyzer.analyze_website(website_url)
            
            if not result:
                return await interaction.followup.send(
                    "❌ Failed to analyze website. Please ensure the URL is valid and try again.",
                    ephemeral=True
                )
            
            # Create embed for the result
            embed = _create_website_embed(result, interaction, start_time)
            
            # Create view with interactive buttons
            view = WebsiteAnalysisView(website_url, self.bot)
            
            # Get favicon for the thumbnail if available
            favicon_data = result.get("favicon_data")
            if favicon_data:
                favicon_file = discord.File(
                    io.BytesIO(favicon_data), 
                    filename="favicon.png"
                )
                await interaction.followup.send(embed=embed, view=view, file=favicon_file)
            else:
                await interaction.followup.send(embed=embed, view=view)
            
            # Log usage
            self.bot.record_command_usage("health")
            logger.info(f"Website analysis called by {interaction.user} for {website_url} (cached: {result.get('cached', False)})")
            
        except asyncio.TimeoutError:
            logger.warning(f"Analysis timeout for {website_url}")
            await interaction.followup.send(
                "⌛ Analysis timed out. Website analysis can take time for complex sites. Please try again later.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Website analysis error for {website_url}: {str(e)}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to analyze website. The analysis service may be experiencing issues. Please try again later.",
                ephemeral=True
            )
        
    # Register error handler
    @check_website.error
    async def website_error(self, interaction, error):
        error_handler = create_error_handler("website")
        await error_handler(self, interaction, error)


