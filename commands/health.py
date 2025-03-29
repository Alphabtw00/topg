"""
Health monitoring command
"""
import discord
from discord import app_commands
from discord.ext import commands
from bot.error_handler import create_error_handler
from ui.embeds import create_health_embed
from utils.logger import get_logger
from datetime import datetime


logger = get_logger()

class Health(commands.Cog):
    """Health check command for bot status monitoring"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="health", description="Show bot performance metrics")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.cooldown(1, 5)
    async def health_slash(self, interaction: discord.Interaction):
        """Health check command (slash version)"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to use this command.",
                ephemeral=True,
                delete_after=5
            )
            return
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            embed = await create_health_embed(self.bot, interaction.user)
            await interaction.followup.send(embed=embed, ephemeral=True)        
               
            self.bot.record_command_usage("health")
            logger.info(f"Health command used by {interaction.user}")
        except Exception as e:
            logger.error(f"Health command error: {e}")
            await interaction.followup.send(
                "Error generating health report. Please try again.",
                ephemeral=True
            )
            
    # Register error handler
    @health_slash.error
    async def health_error(self, interaction, error):
        await create_error_handler("health")(self, interaction, error)