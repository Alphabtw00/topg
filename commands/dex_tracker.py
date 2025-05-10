"""
DexScreener tracker commands for real-time token listings
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import service.dex_tracker as dex_tracker
import repository.dex_tracker_repo as dex_db
from utils.logger import get_logger
from bot.error_handler import create_error_handler
from datetime import datetime
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
    @app_commands.describe(channel="Channel to send DexScreener updates to (defaults to current channel if none specified)")
    async def addchannel_command(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Add a channel for DexScreener updates"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Use current channel if none specified
        if not channel:
            channel = interaction.channel
        
        try:
            # Check channel permissions
            bot_member = interaction.guild.get_member(self.bot.user.id)
            channel_perms = channel.permissions_for(bot_member)
            
            if not channel_perms.send_messages or not channel_perms.embed_links:
                await interaction.followup.send(
                    f"❌ I need 'Send Messages' and 'Embed Links' permissions in {channel.mention}.", 
                    ephemeral=True
                )
                return
            
            # Add channel for this specific guild
            success = await dex_db.add_channel(interaction.guild.id, channel.id)
            
            if success:
                # Enable tracking if not already enabled
                await dex_db.enable_tracking(interaction.guild.id)
                
                # Clear cache to ensure the new channel is used immediately
                await dex_tracker.clear_cache_for_guild(interaction.guild.id)
                await dex_tracker.refresh_all_caches()
                
                # Ensure tracking is started
                await dex_tracker.start_tracking(self.bot)
                
                embed = discord.Embed(
                    title="DexScreener Tracker Enabled",
                    description=f"{channel.mention} will now receive DexScreener new listing updates!",
                    color=0x2ECC71  # Green
                )
                
                # Add chain info
                if DEX_TRACKER_CHAINS:
                    chains_text = ", ".join([chain.upper() for chain in DEX_TRACKER_CHAINS])
                    embed.add_field(
                        name="⛓️ Tracked Chains",
                        value=chains_text,
                        inline=False
                    )
                
                # Add poll interval
                embed.add_field(
                    name="⏱️ Poll Interval",
                    value=f"`{DEX_TRACKER_POLL_INTERVAL}` seconds",
                    inline=True
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Track command usage
                self.bot.record_command_usage("dextracker_add_channel")
                logger.info(f"{interaction.user.name} added channel #{channel.name} in server '{interaction.guild.name}' for DexScreener tracking")
            else:
                await interaction.followup.send(f"ℹ️ Channel {channel.mention} is already configured for DexScreener updates.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error adding DexScreener channel: {e}")
            await interaction.followup.send(f"❌ Error adding {channel.mention} to DexScreener tracker. Please try again later.", ephemeral=True)
    
    @dex_group.command(name="remove-channel", description="Remove a channel from DexScreener tracker")
    @app_commands.describe(channel="Channel to remove (defaults to current channel if none specified)")
    async def removechannel_command(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Remove a channel from DexScreener tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Use current channel if none specified
        if not channel:
            channel = interaction.channel
        
        try:
            # Remove channel for this specific guild
            success = await dex_db.remove_channel(interaction.guild.id, channel.id)
            
            if success:
                # Clear cache to ensure the removed channel is not used anymore
                await dex_tracker.clear_cache_for_guild(interaction.guild.id)
                await dex_tracker.refresh_all_caches()
                
                embed = discord.Embed(
                    title="Channel Removed",
                    description=f"{channel.mention} will no longer receive DexScreener updates.",
                    color=0xE67E22  # Orange
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Track command usage
                self.bot.record_command_usage("dextracker_remove_channel")
                logger.info(f"{interaction.user.name} removed channel #{channel.name} in server '{interaction.guild.name}' from DexScreener tracking")
            else:
                await interaction.followup.send(f"❌ {channel.mention} was not configured for DexScreener updates.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error removing DexScreener channel: {e}")
            await interaction.followup.send(f"❌ Error removing {channel.mention} from DexScreener tracker. Please try again later.", ephemeral=True)
    
    @dex_group.command(name="enable", description="Enable DexScreener tracking")
    async def enable_command(self, interaction: discord.Interaction):
        """Enable DexScreener tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Validate setup for this specific guild
            channels = await dex_db.get_channels(interaction.guild.id)
            
            if not channels:
                await interaction.followup.send(
                    "❌ No channels configured for this server. Add channels first with `/dextracker add-channel`.", 
                    ephemeral=True
                )
                return
            
            # Update settings for this specific guild
            success = await dex_db.enable_tracking(interaction.guild.id)
            
            if success:
                # Clear cache to ensure the enabled status is picked up immediately
                await dex_tracker.clear_cache_for_guild(interaction.guild.id)
                await dex_tracker.refresh_all_caches()
                
                # Ensure the tracking task is running
                await dex_tracker.start_tracking(self.bot)
                
                # Format channel mentions
                channel_mentions = []
                for channel_id in channels:
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        channel_mentions.append(channel.mention)
                
                channels_text = " | ".join(channel_mentions) if channel_mentions else "No channels found"
                
                embed = discord.Embed(
                    title="Tracking Enabled",
                    description="✅ DexScreener tracking has been activated! New paid listings will appear in configured channels.",
                    color=0x2ECC71  # Green
                )
                
                embed.add_field(
                    name="📣 Output Channels",
                    value=channels_text,
                    inline=False
                )
                
                # Add chain info
                if DEX_TRACKER_CHAINS:
                    chains_text = ", ".join([chain.upper() for chain in DEX_TRACKER_CHAINS])
                    embed.add_field(
                        name="⛓️ Tracked Chains",
                        value=chains_text,
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Track command usage
                self.bot.record_command_usage("dextracker_enable")
                logger.info(f"{interaction.user.name} enabled DexScreener tracking in server '{interaction.guild.name}'")
            else:
                await interaction.followup.send("❌ Failed to enable tracking.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error enabling DexScreener tracking: {e}")
            await interaction.followup.send(f"❌ Error enabling DexScreener tracking. Please try again later.", ephemeral=True)
    
    @dex_group.command(name="disable", description="Disable DexScreener tracking")
    async def disable_command(self, interaction: discord.Interaction):
        """Disable DexScreener tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Update settings for this specific guild
            success = await dex_db.disable_tracking(interaction.guild.id)
            
            if success:
                # Clear cache to ensure the disabled status is picked up immediately
                await dex_tracker.clear_cache_for_guild(interaction.guild.id)
                await dex_tracker.refresh_all_caches()
                
                embed = discord.Embed(
                    title="Tracking Disabled",
                    description="DexScreener tracking has been deactivated for this server. No updates will be sent until re-enabled.",
                    color=0xE74C3C  # Red
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Track command usage
                self.bot.record_command_usage("dextracker_disable")
                logger.info(f"{interaction.user.name} disabled DexScreener tracking in server '{interaction.guild.name}'")
            else:
                await interaction.followup.send("❌ Failed to disable tracking.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error disabling DexScreener tracking: {e}")
            await interaction.followup.send(f"❌ Error disabling DexScreener tracking. Please try again later.", ephemeral=True)
    
    @dex_group.command(name="status", description="Show status of DexScreener tracking")
    async def status_command(self, interaction: discord.Interaction):
        """Show status of DexScreener tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Get settings for this specific guild
            settings = await dex_db.get_guild_settings(interaction.guild.id)
            
            # Get channels for this specific guild
            channel_ids = await dex_db.get_channels(interaction.guild.id)
            channels = []
            for channel_id in channel_ids:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    channels.append(channel.mention)
            
            # Get tracking status
            tracking_status = dex_tracker.get_tracking_status()
            is_tracking = tracking_status.get('is_tracking', False) and settings.get('enabled', False)
            
            # Create embed
            color = 0x2ECC71 if is_tracking else 0xE74C3C
            
            # Emoji for status
            status_emoji = "🟢" if is_tracking else "🔴"
            status_text = "Active" if is_tracking else "Inactive"
            
            embed = discord.Embed(
                title=f"DexScreener Tracker for {interaction.guild.name}",
                color=color
            )
            
            # Set thumbnail
            embed.set_thumbnail(url="https://pbs.twimg.com/profile_images/1519780093915611136/xZMsv6j5_400x400.jpg")
            
            # Status fields
            embed.add_field(
                name=f"🔄 Tracker Status",
                value=f"{status_emoji} **{status_text}**",
                inline=False
            )
            
            # Check interval
            embed.add_field(
                name=f"⏰ Check Interval",
                value=f"**{DEX_TRACKER_POLL_INTERVAL}s**",
                inline=False
            )
            
            # Channels section - server-specific
            if channels:
                channels_text = "\n".join([f"📢 {c}" for c in channels[:5]])
                if len(channels) > 5:
                    channels_text += f"\n*...and {len(channels) - 5} more*"
            else:
                channels_text = "*No output channels configured in this server*"
                
            embed.add_field(
                name=f"📣 Output Channels ({len(channels)})",
                value=channels_text,
                inline=False
            )
            
            # Chains section
            if DEX_TRACKER_CHAINS:
                chains_text = ", ".join([chain.upper() for chain in DEX_TRACKER_CHAINS])
                embed.add_field(
                    name="⛓️ Tracked Chains",
                    value=chains_text,
                    inline=False
                )
            
            # Set footer with server icon
            embed.set_footer(
                text=f"DexScreener updates for {interaction.guild.name}",
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None
            )
            
            # Add server banner if available
            if interaction.guild.banner:
                embed.set_image(url=interaction.guild.banner.url)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Track command usage
            self.bot.record_command_usage("dextracker_status")
            logger.debug(f"{interaction.user.name} checked DexScreener status in server '{interaction.guild.name}'")
            
        except Exception as e:
            logger.error(f"Error getting DexScreener status: {e}")
            await interaction.followup.send(f"❌ Error getting DexScreener status for server", ephemeral=True)
    
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