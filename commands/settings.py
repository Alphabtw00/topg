"""
Server and channel settings management commands with streamlined interface
"""
import discord
from discord import app_commands
from discord.ext import commands
from bot.error_handler import create_error_handler
from utils.logger import get_logger
from utils.auto_message_settings import (
    get_server_settings, 
    enable_server_wide, 
    disable_server_wide,
    add_channel, 
    remove_channel,
    exclude_channel,
    include_channel,
    get_channels_list,
    get_excluded_channels
)

logger = get_logger()

class SettingsCommands(commands.Cog):
    """Server and channel settings management commands"""
    
    __slots__ = ("bot",)
    
    def __init__(self, bot):
        self.bot = bot
    
    settings_group = app_commands.Group(
        name="settings", 
        description="Manage bot settings for your server",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )
    
    @settings_group.command(name="status", description="Show current auto-message channel settings")
    async def settings_status(self, interaction: discord.Interaction):
        """Show current settings status for the server"""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to use this command.",
                ephemeral=True,
                delete_after=5
            )
            return
            
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            settings = await get_server_settings(interaction.guild.id)
            
            # Create an embed to display settings
            embed = discord.Embed(
                title="Bot Settings Status",
                description=f"Settings for {interaction.guild.name}",
                color=discord.Color.blue()
            )
            
            mode = "Server-wide" if settings.get("server_wide", False) else "Channel-specific"
            embed.add_field(name="Mode", value=mode, inline=False)
            
            # For server-wide mode, show excluded channels
            if settings.get("server_wide", False):
                excluded_channels = await get_excluded_channels(interaction.guild.id)
                
                if excluded_channels:
                    channel_mentions = []
                    for channel_id in excluded_channels:
                        channel = interaction.guild.get_channel(channel_id)
                        if channel:
                            channel_mentions.append(f"<#{channel_id}>")
                    
                    if channel_mentions:
                        embed.add_field(
                            name="Excluded Channels", 
                            value="\n".join(channel_mentions), 
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="Excluded Channels", 
                            value="No channels excluded.", 
                            inline=False
                        )
                else:
                    embed.add_field(
                        name="Excluded Channels", 
                        value="No channels excluded.", 
                        inline=False
                    )
            
            # For channel-specific mode, show enabled channels
            else:
                enabled_channels = await get_channels_list(interaction.guild.id)
                
                if enabled_channels:
                    channel_mentions = []
                    for channel_id in enabled_channels:
                        channel = interaction.guild.get_channel(channel_id)
                        if channel:
                            channel_mentions.append(f"<#{channel_id}>")
                    
                    if channel_mentions:
                        embed.add_field(
                            name="Enabled Channels", 
                            value="\n".join(channel_mentions), 
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="Enabled Channels", 
                            value="No channels configured.", 
                            inline=False
                        )
                else:
                    embed.add_field(
                        name="Enabled Channels", 
                        value="No channels configured.", 
                        inline=False
                    )
            
            embed.add_field(
                name="Available Commands",
                value=(
                    "`/settings mode` - Switch between server-wide and channel-specific modes\n"
                    "`/settings add-channel [channel]` - Add a channel to auto-messaging (defaults to current channel)\n"
                    "`/settings remove-channel [channel]` - Remove a channel from auto-messaging (defaults to current channel)"
                ),
                inline=False
            )
            
            embed.set_footer(text="Use these commands to configure where the bot should process messages")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.debug(f"Settings status checked by {interaction.user} in {interaction.guild.name}")
            self.bot.record_command_usage("settings_status")
            
        except Exception as e:
            logger.error(f"Settings status error: {e}")
            await interaction.followup.send(
                "Error retrieving settings. Please try again.",
                ephemeral=True
            )
    
    @settings_group.command(name="mode", description="Switch between server-wide and channel-specific modes")
    @app_commands.describe(
        mode="Select the mode for auto-messaging"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Server-wide (all channels)", value="server_wide"),
        app_commands.Choice(name="Channel-specific (select channels only)", value="channel_specific")
    ])
    async def mode_command(self, interaction: discord.Interaction, mode: str):
        """Switch between server-wide and channel-specific modes"""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to use this command.",
                ephemeral=True,
                delete_after=5
            )
            return
            
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Get current settings
            settings = await get_server_settings(interaction.guild.id)
            current_is_server_wide = settings.get("server_wide", True)
            
            # Check if mode is changing
            if mode == "server_wide" and current_is_server_wide:
                await interaction.followup.send(
                    "Server is already in server-wide mode.",
                    ephemeral=True
                )
                return
            elif mode == "channel_specific" and not current_is_server_wide:
                await interaction.followup.send(
                    "Server is already in channel-specific mode.",
                    ephemeral=True
                )
                return
                
            # Apply mode change
            if mode == "server_wide":
                success = await enable_server_wide(interaction.guild.id)
                if success:
                    await interaction.followup.send(
                        "✅ Server-wide auto-messaging has been enabled. The bot will now respond in all channels except those specifically excluded.",
                        ephemeral=True
                    )
                    logger.info(f"Server-wide enabled by {interaction.user} in {interaction.guild.name}")
                    self.bot.record_command_usage("enable_server_wide")
            else:  # channel_specific
                success = await disable_server_wide(interaction.guild.id)
                if success:
                    await interaction.followup.send(
                        "✅ Channel-specific auto-messaging has been enabled. Use `/settings add-channel` to enable specific channels.",
                        ephemeral=True
                    )
                    logger.info(f"Channel-specific enabled by {interaction.user} in {interaction.guild.name}")
                    self.bot.record_command_usage("disable_server_wide")
                    
        except Exception as e:
            logger.error(f"Mode change error: {e}")
            await interaction.followup.send(
                "Error updating settings. Please try again.",
                ephemeral=True
            )
    
    @settings_group.command(name="add-channel", description="Add a channel to auto-messaging (defaults to current channel)")
    @app_commands.describe(channel="The channel to add to auto-messaging (optional, defaults to current channel)")
    async def add_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        """Smart add channel command that works in both modes and defaults to current channel"""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to use this command.",
                ephemeral=True,
                delete_after=5
            )
            return
            
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # If channel is not specified, use the current channel
            if channel is None:
                channel = interaction.channel
            
            # Check current settings
            settings = await get_server_settings(interaction.guild.id)
            is_server_wide = settings.get("server_wide", True)
            mode_name = "Server-wide" if is_server_wide else "Channel-specific"
            
            if is_server_wide:
                # In server-wide mode, this means "include" (remove from exclusion)
                success = await include_channel(interaction.guild.id, channel.id)
                
                if success:
                    await interaction.followup.send(
                        f"✅ Channel {channel.mention} has been included in auto-messaging. (Mode: {mode_name})",
                        ephemeral=True
                    )
                    logger.info(f"Channel {channel.name} (ID: {channel.id}) included by {interaction.user} in {interaction.guild.name} | Mode: {mode_name}")
                    self.bot.record_command_usage("include_channel")
                else:
                    await interaction.followup.send(
                        f"ℹ️ Channel {channel.mention} is already included in auto-messaging. (Mode: {mode_name})",
                        ephemeral=True
                    )
            else:
                # In channel-specific mode, this means "add to enabled list"
                success = await add_channel(interaction.guild.id, channel.id)
                
                if success:
                    await interaction.followup.send(
                        f"✅ Channel {channel.mention} has been added to auto-messaging. (Mode: {mode_name})",
                        ephemeral=True
                    )
                    logger.info(f"Channel {channel.name} (ID: {channel.id}) added by {interaction.user} in {interaction.guild.name} | Mode: {mode_name}")
                    self.bot.record_command_usage("add_channel")
                else:
                    await interaction.followup.send(
                        f"ℹ️ Channel {channel.mention} is already configured for auto-messaging. (Mode: {mode_name})",
                        ephemeral=True
                    )
                
        except Exception as e:
            logger.error(f"Add channel error: {e}")
            await interaction.followup.send(
                "Error updating channel settings. Please try again.",
                ephemeral=True
            )
    
    @settings_group.command(name="remove-channel", description="Remove a channel from auto-messaging (defaults to current channel)")
    @app_commands.describe(channel="The channel to remove from auto-messaging (optional, defaults to current channel)")
    async def remove_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        """Smart remove channel command that works in both modes and defaults to current channel"""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You need administrator permissions to use this command.",
                ephemeral=True,
                delete_after=5
            )
            return
            
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # If channel is not specified, use the current channel
            if channel is None:
                channel = interaction.channel
                
            # Check current settings
            settings = await get_server_settings(interaction.guild.id)
            is_server_wide = settings.get("server_wide", True)
            mode_name = "Server-wide" if is_server_wide else "Channel-specific"
            
            if is_server_wide:
                # In server-wide mode, this means "exclude"
                success = await exclude_channel(interaction.guild.id, channel.id)
                
                if success:
                    await interaction.followup.send(
                        f"✅ Channel {channel.mention} has been excluded from auto-messaging. (Mode: {mode_name})",
                        ephemeral=True
                    )
                    logger.info(f"Channel {channel.name} (ID: {channel.id}) excluded by {interaction.user} in {interaction.guild.name} | Mode: {mode_name}")
                    self.bot.record_command_usage("exclude_channel")
                else:
                    await interaction.followup.send(
                        f"ℹ️ Channel {channel.mention} is already excluded from auto-messaging. (Mode: {mode_name})",
                        ephemeral=True
                    )
            else:
                # In channel-specific mode, this means "remove from enabled list"
                success = await remove_channel(interaction.guild.id, channel.id)
                
                if success:
                    await interaction.followup.send(
                        f"✅ Channel {channel.mention} has been removed from auto-messaging. (Mode: {mode_name})",
                        ephemeral=True
                    )
                    logger.info(f"Channel {channel.name} (ID: {channel.id}) removed by {interaction.user} in {interaction.guild.name} | Mode: {mode_name}")
                    self.bot.record_command_usage("remove_channel")
                else:
                    await interaction.followup.send(
                        f"ℹ️ Channel {channel.mention} was not configured for auto-messaging. (Mode: {mode_name})",
                        ephemeral=True
                    )                               
        except Exception as e:
            logger.error(f"Remove channel error: {e}")
            await interaction.followup.send(
                "Error updating channel settings. Please try again.",
                ephemeral=True
            )
    
    # Register error handlers
    @settings_status.error
    @mode_command.error
    @add_channel_command.error
    @remove_channel_command.error
    async def settings_error(self, interaction, error):
        error_handler = create_error_handler("settings")
        await error_handler(self, interaction, error)