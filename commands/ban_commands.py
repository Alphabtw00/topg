"""
User ban command with consistent messaging
"""
import discord
from discord import app_commands
from discord.ext import commands
from bot.error_handler import create_error_handler
from service.username_ban_service import ban_user
from utils.logger import get_logger
from utils.formatters import safe_text
from datetime import datetime
from config import ADMIN_USER_IDS, BAN_GIF_URL
import asyncio

logger = get_logger()

class BanCommands(commands.Cog):
    """Ban command that uses the same system as auto-banning"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ban", description="Ban a user in this server with funny/nsfw reply")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.cooldown(1, 5)
    @app_commands.describe(
        user="The user to ban",
        reason="Reason for the ban (optional)(Defauls to a funny reason)",
        delete_days="Number of days of messages to delete (optional, default: 1)"
    )
    @app_commands.choices(delete_days=[
        app_commands.Choice(name="None", value=0),
        app_commands.Choice(name="1 day", value=1),
        app_commands.Choice(name="2 days", value=2),
        app_commands.Choice(name="3 days", value=3),
        app_commands.Choice(name="4 days", value=4),
        app_commands.Choice(name="5 days", value=5),
        app_commands.Choice(name="6 days", value=6),
        app_commands.Choice(name="7 days", value=7)
    ])
    async def ban_slash(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "Manual ban triggered by moderator",
        delete_days: int = 1
    ):
        # Check caller has permission
        if not (interaction.user.guild_permissions.ban_members or interaction.user.id in ADMIN_USER_IDS):
            await interaction.response.send_message(
                "You need ban members permission to use this command.",
                ephemeral=True
            )
            return

        # Prevent self-ban
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot ban yourself!",
                ephemeral=True
            )
            return

        # Check caller's role vs target's role
        if not interaction.user.top_role > user.top_role:
            await interaction.response.send_message(
                "You cannot ban someone with a higher or equal role to yours.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            formatted_reason = f"{reason} (Banned by {interaction.user})"
            ban_result = await ban_user(self.bot, user, formatted_reason, delete_days=delete_days)

            if ban_result:
                info_embed = discord.Embed(
                    title="User Banned",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                info_embed.add_field(name="Display Name", value=user.display_name, inline=True)
                info_embed.add_field(name="Username", value=str(user), inline=True)
                info_embed.add_field(name="User ID", value=user.id, inline=True)
                info_embed.add_field(name="Banned by", value=interaction.user.mention, inline=True)
                info_embed.add_field(name="Banned user", value=user.mention, inline=True)
                info_embed.add_field(name="Reason", value=reason, inline=False)
                days_text = f"{delete_days} day(s)" if delete_days > 0 else "None"
                info_embed.add_field(name="Messages Deleted", value=days_text, inline=True)
                if user.avatar:
                    info_embed.set_thumbnail(url=user.avatar.url)
                if BAN_GIF_URL:
                    info_embed.set_image(url=BAN_GIF_URL)

                await interaction.followup.send(embed=info_embed, ephemeral=True)

                self.bot.record_command_usage("ban")
                logger.info(f"Ban command used by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) | Target: {safe_text(user.display_name)} ({safe_text(user.name)}) [ID: {user.id}] in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")

            else:
                await interaction.followup.send(
                    f"Failed to ban **{user}**.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Ban command error: {e}")
            await interaction.followup.send(
                "An error occurred while trying to ban the user. Please check the logs.",
                ephemeral=True
            )

    @ban_slash.error
    async def ban_error(self, interaction, error):
        await create_error_handler("ban")(self, interaction, error)