"""
About to graduate alert commands for tokens about to graduate
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import service.about_to_graduate_tracker_service as about_to_graduate_alert
import repository.about_to_graduate_repo as about_to_graduate_db
from utils.logger import get_logger
from utils.formatters import safe_text
from bot.error_handler import create_error_handler
from config import ADMIN_USER_IDS

logger = get_logger()

class About_to_GraduateCommands(commands.Cog):
    """About to graduate alert commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    # Create command group
    alert_group = app_commands.Group(
        name="about_to_graduate",
        description="Manage about to graduate alert tracker for tokens about to graduate",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )
    
    @alert_group.command(name="add-channel", description="Add a channel for about to graduate tracking")
    async def addchannel_command(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Add a channel for about to graduate alert updates"""
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not (interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USER_IDS):
            await interaction.followup.send(
                "You need administrator permissions to use this command.",
                ephemeral=True
            )
            return
    
        
        if not channel:
            channel = interaction.channel
        
        try:
            # Check permissions
            bot_member = interaction.guild.get_member(self.bot.user.id)
            channel_perms = channel.permissions_for(bot_member)
            
            if not channel_perms.send_messages or not channel_perms.embed_links:
                await interaction.followup.send(
                    f"❌ I need 'Send Messages' and 'Embed Links' permissions in {channel.mention}.", 
                    ephemeral=True
                )
                return
            
            # Add channel
            success = await about_to_graduate_db.add_channel(interaction.guild.id, channel.id)
            
            if success:
                # Newly added channel
                await about_to_graduate_alert.rebuild_cache_and_restart_if_needed(self.bot)
                
                # Check if tracking is enabled
                settings = await about_to_graduate_db.get_guild_settings(interaction.guild.id)
                is_enabled = settings.get('enabled', False)
                
                embed = discord.Embed(
                    title="Channel Added",
                    description=f"{channel.mention} added for about to graduate alerts!",
                    color=0x2ECC71 if is_enabled else 0xE67E22
                )
                
                if not is_enabled:
                    embed.add_field(
                        name="⚠️ Tracking Disabled",
                        value="Use `/about_to_graduate enable` to start receiving updates",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"About to graduate alert channel {safe_text(channel.name)} (ID: {channel.id}) added by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")

                
            else:
                # Channel already exists
                await interaction.followup.send(f"ℹ️ {channel.mention} is already configured for about to graduate alerts.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error adding about to graduate alert channel: {e}")
            await interaction.followup.send("❌ Error adding channel.", ephemeral=True)


    @alert_group.command(name="remove-channel", description="Remove a channel from about to graduate tracker")
    async def removechannel_command(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Remove a channel from about to graduate alert tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        if not (interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USER_IDS):
            await interaction.followup.send(
                "You need administrator permissions to use this command.",
                ephemeral=True
            )
            return
        
        if not channel:
            channel = interaction.channel
        
        try:
            # Remove channel
            success = await about_to_graduate_db.remove_channel(interaction.guild.id, channel.id)
            
            if success:
                # Channel was removed
                await about_to_graduate_alert.rebuild_cache_and_restart_if_needed(self.bot)
                
                embed = discord.Embed(
                    title="Channel Removed",
                    description=f"{channel.mention} removed from about to graduate alerts.",
                    color=0xE67E22
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"About to graduate alert channel {safe_text(channel.name)} (ID: {channel.id}) removed by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")
                
            else:
                # Channel was not configured
                await interaction.followup.send(f"❌ {channel.mention} was already not configured for about to graduate alerts.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error removing about to graduate alert channel: {e}")
            await interaction.followup.send("❌ Error removing channel.", ephemeral=True)


    @alert_group.command(name="enable", description="Enable about to graduate tracking")
    async def enable_command(self, interaction: discord.Interaction):
        """Enable about to graduate alert tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        if not (interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USER_IDS):
            await interaction.followup.send(
                "You need administrator permissions to use this command.",
                ephemeral=True
            )
            return
        
        try:
            # Check if channels exist
            channels = await about_to_graduate_db.get_channels(interaction.guild.id)
            if not channels:
                await interaction.followup.send(
                    "❌ No channels configured. Add channels first with `/about_to_graduate add-channel`.", 
                    ephemeral=True
                )
                return
            
            # Enable tracking
            success = await about_to_graduate_db.enable_tracking(interaction.guild.id)
            
            if success:
                # Newly enabled
                await about_to_graduate_alert.rebuild_cache_and_restart_if_needed(self.bot)
                
                embed = discord.Embed(
                    title="About to Graduate Alerts Enabled",
                    description="✅ About to graduate alert tracking activated!",
                    color=0x2ECC71
                )
                
                channel_mentions = []
                for channel_id in channels[:5]:
                    ch = interaction.guild.get_channel(channel_id)
                    if ch:
                        channel_mentions.append(ch.mention)
                
                embed.add_field(
                    name="Active Channels",
                    value=" | ".join(channel_mentions) or "None found",
                    inline=False
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"About to graduate alert tracking enabled by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")

            else:
                # Already enabled
                await interaction.followup.send("ℹ️ About to graduate alert tracking is already enabled for this server.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error enabling about to graduate alert tracking: {e}")
            await interaction.followup.send("❌ Error enabling tracking.", ephemeral=True)


    @alert_group.command(name="disable", description="Disable about to graduate tracking")
    async def disable_command(self, interaction: discord.Interaction):
        """Disable about to graduate alert tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        if not (interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USER_IDS):
            await interaction.followup.send(
                "You need administrator permissions to use this command.",
                ephemeral=True
            )
            return
        
        try:
            success = await about_to_graduate_db.disable_tracking(interaction.guild.id)
            
            if success:
                # Newly disabled
                await about_to_graduate_alert.rebuild_cache_and_restart_if_needed(self.bot)
                
                embed = discord.Embed(
                    title="About to Graduate Alerts Disabled",
                    description="About to graduate alert tracking deactivated for this server.",
                    color=0xE74C3C
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"About to graduate alert tracking disabled by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")
                
            else:
                # Already disabled
                await interaction.followup.send("ℹ️ About to graduate alert tracking is already disabled for this server.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error disabling about to graduate alert tracking: {e}")
            await interaction.followup.send("❌ Error disabling tracking.", ephemeral=True)


    @alert_group.command(name="status", description="Show about to graduate tracking status")
    async def status_command(self, interaction: discord.Interaction):
        """Show about to graduate alert tracking status"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        if not (interaction.user.guild_permissions.administrator or interaction.user.id in ADMIN_USER_IDS):
            await interaction.followup.send(
                "You need administrator permissions to use this command.",
                ephemeral=True
            )
            return
        
        try:
            # Get guild settings and channels
            settings = await about_to_graduate_db.get_guild_settings(interaction.guild.id)
            guild_channels = await about_to_graduate_db.get_channels(interaction.guild.id)
            if guild_channels:
                channel_mentions = " ".join(f"<#{channel_id}>" for channel_id in guild_channels)
            else:
                channel_mentions = "None"
            
            is_enabled = settings.get('enabled', False)
            has_channels = len(guild_channels) > 0
            
            # Global tracking status
            tracking_status = about_to_graduate_alert.get_tracking_status()
            is_tracking = tracking_status.get('is_tracking', False)
            
            # This guild's effective status (enabled AND has channels)
            guild_active = is_enabled and has_channels and is_tracking
            
            color = 0x2ECC71 if guild_active else 0xE74C3C
            status_text = "Active" if guild_active else "Inactive"
            
            embed = discord.Embed(
                title=f"About to Graduate Alert Status - {interaction.guild.name}",
                color=color
            )
            
            embed.add_field(
                name="Status",
                value=f"{'🟢' if guild_active else '🔴'} {status_text}",
                inline=True
            )
            
            embed.add_field(
                name="Enabled",
                value=f"{'✅' if is_enabled else '❌'} {is_enabled}",
                inline=True
            )
            
            embed.add_field(
                name="Channels",
                value=channel_mentions,
                inline=True
            )
                        
            # Show reason if inactive
            if not guild_active:
                reasons = []
                if not is_enabled:
                    reasons.append("Not enabled")
                if not has_channels:
                    reasons.append("No channels")
                if not is_tracking:
                    reasons.append("Global tracking stopped")
                
                embed.add_field(
                    name="Inactive Reason",
                    value=" | ".join(reasons),
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"About to graduate alert status checked by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")
            
        except Exception as e:
            logger.error(f"Error getting about to graduate alert status by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id}): {e}")
            await interaction.followup.send("❌ Error getting status.", ephemeral=True)

    # Add error handlers
    @addchannel_command.error
    @removechannel_command.error
    @enable_command.error
    @disable_command.error
    async def about_to_graduate_alert_command_error(self, interaction, error):
        """Handle errors in about to graduate alert commands"""
        error_handler = create_error_handler("about_to_graduate_alert_commands")
        await error_handler(self, interaction, error)