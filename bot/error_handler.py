"""
Centralized error handling for bot commands
"""
import discord
from discord import app_commands
from utils.logger import get_logger
from utils.cache import increment_error_count

logger = get_logger()

def create_error_handler(command_name):
    """
    Create an error handler for a specific command
    
    Args:
        command_name: Name of the command for logging
        
    Returns:
        function: Error handler function
    """
    async def error_handler(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Command on cooldown. Try again in {error.retry_after:.1f}s",
                ephemeral=True,
                delete_after=5
            )
        else:
            logger.error(f"{command_name} command error: {str(error)}")
            increment_error_count(f"{command_name}_error")
            
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