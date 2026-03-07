"""
Health monitoring command
"""
import discord
from discord import app_commands
from discord.ext import commands
from bot.error_handler import create_error_handler
from ui.embeds import create_health_embed
from utils.logger import get_logger
from config import ADMIN_USER_IDS, PRIVATE_COMMAND_GUILD_IDS
from datetime import datetime
from utils.formatters import safe_text


logger = get_logger()

class HealthCommands(commands.Cog):
    """Health check command for bot status monitoring"""
   
    def __init__(self, bot):
        self.bot = bot
   
    @app_commands.command(name="health", description="Show comprehensive bot performance metrics and server status")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10)
    @app_commands.guilds(*[discord.Object(id=g) for g in PRIVATE_COMMAND_GUILD_IDS])
    async def health_slash(self, interaction: discord.Interaction):
        """Enhanced health check command (slash version) - Bot owners only"""
        
        # Check if user is a bot owner
        if interaction.user.id not in ADMIN_USER_IDS:
            await interaction.response.send_message(
                "❌ This command is restricted to bot owners only.",
                ephemeral=True,
                delete_after=5
            )
            return
       
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            embed = await create_health_embed(self.bot, interaction.user)
            await interaction.followup.send(embed=embed, ephemeral=True)        
               
            self.bot.record_command_usage("health")
            logger.info(f"Health command used by bot owner {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) [ID: {interaction.user.id}] in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")
            
        except Exception as e:
            logger.error(f"Health command error: {e}")
            await interaction.followup.send(
                "❌ Error generating health report. Please try again.",
                ephemeral=True
            )
           
    # Register error handler
    @health_slash.error
    async def health_error(self, interaction, error):
        await create_error_handler("health")(self, interaction, error)
