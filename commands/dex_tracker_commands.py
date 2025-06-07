"""
DexScreener tracker commands for real-time token listings
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import service.dex_tracker_service as dex_tracker_service
import repository.dex_tracker_repo as dex_db
from utils.logger import get_logger
from bot.error_handler import create_error_handler
from datetime import datetime
from utils.formatters import safe_text
from config import DEX_TRACKER_CHAINS, DEX_TRACKER_POLL_INTERVAL

logger = get_logger()

class DexTrackerCommands(commands.Cog):
    """DexScreener tracker commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    # Create command group
    dex_group = app_commands.Group(
        name="dextracker",
        description="Manage DexScreener new listing tracker",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )
    
    @dex_group.command(name="add-channel", description="Add a channel for DexScreener new listings")
    async def addchannel_command(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Add a channel for DexScreener updates"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
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
            success = await dex_db.add_channel(interaction.guild.id, channel.id)
            
            if success:
                # Rebuild cache (tracking will start only if also enabled)
                await dex_tracker_service.rebuild_cache_and_restart_if_needed(self.bot)
                
                # Check if tracking is enabled for this guild
                settings = await dex_db.get_guild_settings(interaction.guild.id)
                is_enabled = settings.get('enabled', False)
                
                embed = discord.Embed(
                    title="Channel Added",
                    description=f"{channel.mention} added for DexScreener updates!",
                    color=0x2ECC71 if is_enabled else 0xE67E22
                )
                
                if not is_enabled:
                    embed.add_field(
                        name="⚠️ Tracking Disabled",
                        value="Use `/dextracker enable` to start receiving updates",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"DexTracker channel {safe_text(channel.name)} (ID: {channel.id}) added by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
            else:
                await interaction.followup.send(f"ℹ️ Channel already configured.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            await interaction.followup.send("❌ Error adding channel.", ephemeral=True)


    @dex_group.command(name="remove-channel", description="Remove a channel from DexScreener tracker")
    @app_commands.describe(channel="Channel to remove (defaults to current channel if none specified)")
    async def removechannel_command(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Remove a channel from DexScreener tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        if not channel:
            channel = interaction.channel
        
        try:
            # Remove channel
            success = await dex_db.remove_channel(interaction.guild.id, channel.id)
            
            if success:
                # Rebuild cache (tracking will stop if no channels left even if enabled)
                await dex_tracker_service.rebuild_cache_and_restart_if_needed(self.bot)
                
                embed = discord.Embed(
                    title="Channel Removed",
                    description=f"{channel.mention} removed from DexScreener updates.",
                    color=0xE67E22
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"DexTracker channel {safe_text(channel.name)} (ID: {channel.id}) removed by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
            else:
                await interaction.followup.send(f"❌ {channel.mention} was not configured.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            await interaction.followup.send("❌ Error removing channel.", ephemeral=True)



    @dex_group.command(name="enable", description="Enable DexScreener tracking")
    async def enable_command(self, interaction: discord.Interaction):
        """Enable DexScreener tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Check if channels exist
            channels = await dex_db.get_channels(interaction.guild.id)
            if not channels:
                await interaction.followup.send(
                    "❌ No channels configured. Add channels first with `/dextracker add-channel`.", 
                    ephemeral=True
                )
                return
            
            # Enable tracking
            success = await dex_db.enable_tracking(interaction.guild.id)
            
            if success:
                # Rebuild cache and start tracking
                await dex_tracker_service.rebuild_cache_and_restart_if_needed(self.bot)
                
                embed = discord.Embed(
                    title="Tracking Enabled",
                    description="✅ DexScreener tracking activated!",
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
                logger.info(f"DexTracker enabled by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
            else:
                await interaction.followup.send("❌ Failed to enable tracking.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error enabling tracking: {e}")
            await interaction.followup.send("❌ Error enabling tracking.", ephemeral=True)


    @dex_group.command(name="disable", description="Disable DexScreener tracking")
    async def disable_command(self, interaction: discord.Interaction):
        """Disable DexScreener tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            success = await dex_db.disable_tracking(interaction.guild.id)
            
            if success:
                # Rebuild cache and stop tracking if no enabled guilds left
                await dex_tracker_service.rebuild_cache_and_restart_if_needed(self.bot)
                
                embed = discord.Embed(
                    title="Tracking Disabled",
                    description="DexScreener tracking deactivated for this server.",
                    color=0xE74C3C
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"DexTracker disabled by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
            else:
                await interaction.followup.send("❌ Failed to disable tracking.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error disabling tracking: {e}")
            await interaction.followup.send("❌ Error disabling tracking.", ephemeral=True)

    @dex_group.command(name="status", description="Show DexScreener tracking status")
    async def status_command(self, interaction: discord.Interaction):
        """Show tracking status"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Get guild settings and channels
            settings = await dex_db.get_guild_settings(interaction.guild.id)
            guild_channels = await dex_db.get_channels(interaction.guild.id)
            
            is_enabled = settings.get('enabled', False)
            has_channels = len(guild_channels) > 0
            
            # Global tracking status
            tracking_status = dex_tracker_service.get_tracking_status()
            is_tracking = tracking_status.get('is_tracking', False)
            
            # This guild's effective status (enabled AND has channels)
            guild_active = is_enabled and has_channels and is_tracking
            
            color = 0x2ECC71 if guild_active else 0xE74C3C
            status_text = "Active" if guild_active else "Inactive"
            
            embed = discord.Embed(
                title=f"DexScreener Status - {interaction.guild.name}",
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
                value=f"📢 {len(guild_channels)}",
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
            logger.debug(f"DexTracker status checked by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
            
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            await interaction.followup.send("❌ Error getting status.", ephemeral=True)
    
    # Add error handlers for all commands
    @addchannel_command.error
    @removechannel_command.error
    @enable_command.error
    @disable_command.error
    @status_command.error
    async def dextracker_command_error(self, interaction, error):
        """Handle errors in DexScreener commands"""
        error_handler = create_error_handler("dextracker_commands")
        await error_handler(self, interaction, error)