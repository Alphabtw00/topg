"""
Health monitoring command
"""
import discord
from discord import app_commands
from discord.ext import commands
from bot.error_handler import create_error_handler
from config import ALLOWED_USER_IDS
from ui.embeds import create_health_embed
from utils.logger import get_logger

logger = get_logger()

class Health(commands.Cog):
    """Health check command for bot status monitoring"""
    
    def __init__(self, bot):
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
            embed = create_health_embed(self.bot, interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"Health command used by {interaction.user}")
        except Exception as e:
            logger.error(f"Health command error: {e}")
            
    # Register error handler
    @health_slash.error
    async def health_error(self, interaction, error):
        await create_error_handler("health")(self, interaction, error)