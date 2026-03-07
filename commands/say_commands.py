"""
commands/say_command.py

Interactive Say Command - Cog that launches the SayConfigView.
"""
from discord import app_commands
from discord.ext import commands
import discord
from typing import Optional

from bot.error_handler import create_error_handler
from utils.logger import get_logger
from utils.formatters import safe_text
from config import ADMIN_USER_IDS

from ui.views import SayConfigView

logger = get_logger()


class SayCommands(commands.Cog):
    """Interactive say command with progressive UI"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="say", description="Interactive message/embed sender (bot or webhook).")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.cooldown(1, 3)
    async def say(self, interaction: discord.Interaction):
        """Launch the interactive Say flow (no slash options)."""
        # Permission check (extra safety; decorator already restricts but good to keep)
        if not (interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USER_IDS):
            await interaction.response.send_message("❌ You need administrator permissions!", ephemeral=True)
            return

        view = SayConfigView(interaction)
        # initial ephemeral message with view
        await interaction.response.send_message(embed=view.get_config_embed(), view=view, ephemeral=True)

    @say.error
    async def say_error(self, interaction, error):
        await create_error_handler("say")(self, interaction, error)


async def setup(bot):
    await bot.add_cog(SayCommands(bot))
