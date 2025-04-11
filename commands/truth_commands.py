import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional
import repository.truth_repo as truth_db
import service.truth_service as truth_service
from config import TRUTH_MIN_INTERVAL, TRUTH_MAX_INTERVAL, TRUTH_DEFAULT_INTERVAL, TRUTH_NIGHT_INTERVAL, VERIFIED_EMOJI
from utils.logger import get_logger
from utils.formatters import format_value, format_date
from handlers import truth_tracker as tracker

logger = get_logger()

class TruthCommands(commands.Cog):
    """Truth Social tracking commands"""

    def __init__(self, bot):
        self.bot = bot
    
    # Create command group
    truth_group = app_commands.Group(
        name="truth", 
        description="Manage Truth Social tracking",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )
    
    @truth_group.command(name="track", description="Track a Truth Social account")
    @app_commands.describe(handle="Truth Social handle to track (with or without @)")
    async def track_command(self, interaction: discord.Interaction, handle: str):
        """Add a Truth Social account to tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Clean handle
        handle = handle.strip().lstrip('@')
        if not handle or len(handle) < 2:
            await interaction.followup.send("Please provide a valid Truth Social handle.", ephemeral=True)
            return
        
        try:
            # Check if already tracking this account in this server
            existing = await truth_db.get_truth_account(interaction.guild.id, handle)
            if existing and existing.get('last_post_id') != "DISABLED":
                await interaction.followup.send(f"Already tracking @{handle} in this server.", ephemeral=True)
                return
            
            # Search for the account using user metadata API
            user_info = await truth_service.get_user_info(handle)
            
            if not user_info:
                await interaction.followup.send(
                    f"Could not find account @{handle} on Truth Social or the API is rate limited. "
                    f"Please check the handle and try again later.", 
                    ephemeral=True
                )
                return
            
            # Extract account info from user metadata
            account_id = user_info.get('id', '')
            display_name = user_info.get('display_name', '')
            followers_count = user_info.get('followers_count', 0)
            following_count = user_info.get('following_count', 0)
            statuses_count = user_info.get('statuses_count', 0)
            verified = user_info.get('verified', False)
            created_at = user_info.get('created_at', '')
            avatar_url = user_info.get('avatar', '')
            header_url = user_info.get('header', '')
            
            # Format the created_at date
            formatted_date = format_date(created_at) if created_at else "Unknown"
            
            if not account_id:
                await interaction.followup.send(
                    f"Couldn't fetch information for @{handle}.",
                    ephemeral=True
                )
                return
            
            # Add to database with guild_id
            success = await truth_db.add_truth_account(interaction.guild.id, handle, account_id, display_name)
            
            if success:
                # Get the latest post to initialize tracking
                latest_post = await truth_service.get_latest_post(handle)
                
                # Update with latest post ID if available, otherwise use a placeholder
                if latest_post and latest_post.get('id'):
                    await truth_db.update_last_post(interaction.guild.id, handle, latest_post['id'])
                else:
                    # If the user has no posts yet, save a placeholder that will allow any post to be tracked
                    await truth_db.update_last_post(interaction.guild.id, handle, "0")
                
                # Create a rich embed profile-like display
                embed = discord.Embed(
                    title=f"Successfully added @{handle} to tracking",
                    url=f"https://truthsocial.com/@{handle}",
                    color=0xE12626  # Truth Social red
                )
                
                # Add the verified emoji if account is verified
                name_with_verification = f"{display_name} {VERIFIED_EMOJI if verified and VERIFIED_EMOJI else '✓' if verified else ''}"
                embed.description = f"**{name_with_verification}**\n\n"
                
                # Add stats in a single line with formatting
                embed.description += f"**{format_value(followers_count)}** Followers  •  **{format_value(following_count)}** Following  •  **{format_value(statuses_count)}** Posts"
                
                # Set the profile picture as thumbnail
                if avatar_url:
                    embed.set_thumbnail(url=avatar_url)
                    
                # Set the banner as image
                if header_url:
                    embed.set_image(url=header_url)
                
                # Set the footer with creation date
                embed.set_footer(text=f"Account created: {formatted_date}")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed to add @{handle} to tracking database.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error tracking Truth Social account: {e}")
            await interaction.followup.send(
                f"❌ Error setting up tracking: {str(e)}\n\n"
                f"Note: If this happens repeatedly, Truth Social may be rate limiting requests.", 
                ephemeral=True
            )
    
    @truth_group.command(name="untrack", description="Stop tracking a Truth Social account")
    @app_commands.describe(handle="Truth Social handle to untrack (with or without @)")
    async def untrack_command(self, interaction: discord.Interaction, handle: str):
        """Remove a Truth Social account from tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Clean handle
        handle = handle.strip().lstrip('@')
        
        try:
            # Get account for this specific guild
            account = await truth_db.get_truth_account(interaction.guild.id, handle)
            
            if not account:
                await interaction.followup.send(f"❌ Not tracking @{handle} in this server.", ephemeral=True)
                return
            
            # Two options: completely remove or just disable
            # Option 1: Remove completely
            success = await truth_db.remove_truth_account(interaction.guild.id, handle)
            
            # Option 2: Just disable by setting special last_post_id
            # success = await truth_db.update_last_post(interaction.guild.id, handle, "DISABLED")
            
            if success:
                embed = discord.Embed(
                    title=f"Stopped tracking @{handle}",
                    description=f"No longer tracking posts from this account in this server.",
                    color=0xF44336  # Red
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed to remove tracking for @{handle}.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error untracking Truth Social account: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    @truth_group.command(name="addchannel", description="Set a channel for Truth Social updates")
    @app_commands.describe(channel="Channel to send Truth Social updates to (defaults to current channel if none specified)")
    async def addchannel_command(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Add a channel for Truth Social updates"""
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
            success = await truth_db.add_truth_channel(interaction.guild.id, channel.id)
            
            if success:
                embed = discord.Embed(
                    title="Channel Added",
                    description=f"{channel.mention} will now receive Truth Social updates!",
                    color=0x2ECC71  # Green
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed to configure {channel.mention}.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error adding Truth Social channel: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    @truth_group.command(name="removechannel", description="Remove a channel from Truth Social updates")
    @app_commands.describe(channel="Channel to remove (defaults to current channel if none specified)")
    async def removechannel_command(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Remove a channel from Truth Social updates"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Use current channel if none specified
        if not channel:
            channel = interaction.channel
        
        try:
            # Remove channel for this specific guild
            success = await truth_db.remove_truth_channel(interaction.guild.id, channel.id)
            
            if success:
                embed = discord.Embed(
                    title="Channel Removed",
                    description=f"{channel.mention} will no longer receive Truth Social updates.",
                    color=0xE67E22  # Orange
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(f"❌ {channel.mention} was not configured for updates.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error removing Truth Social channel: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    @truth_group.command(name="interval", description="Set the check interval for Truth Social updates")
    @app_commands.describe(seconds="Seconds between checks (min 1, max 60)")
    async def interval_command(self, interaction: discord.Interaction, seconds: int):
        """Set the check interval for Truth Social updates"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Validate interval
        if seconds < TRUTH_MIN_INTERVAL:
            await interaction.followup.send(
                f"❌ Check interval must be at least {TRUTH_MIN_INTERVAL} second(s).", 
                ephemeral=True
            )
            return
        
        if seconds > TRUTH_MAX_INTERVAL:
            await interaction.followup.send(
                f"❌ Check interval cannot be greater than {TRUTH_MAX_INTERVAL} seconds.", 
                ephemeral=True
            )
            return
        
        try:
            # Update settings for this specific guild
            settings = {'check_interval': seconds}
            success = await truth_db.update_guild_settings(interaction.guild.id, settings)
            
            if success:
                embed = discord.Embed(
                    title="Interval Updated",
                    description=(
                        f"✅ Truth Social check interval set to **{seconds} seconds** during active hours.\n"
                        f"Night mode will use **{TRUTH_NIGHT_INTERVAL} seconds** automatically."
                    ),
                    color=0x3498DB  # Blue
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to update check interval.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting Truth Social interval: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    @truth_group.command(name="enable", description="Enable Truth Social tracking")
    async def enable_command(self, interaction: discord.Interaction):
        """Enable Truth Social tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Validate setup for this specific guild
            accounts = await truth_db.get_guild_tracked_accounts(interaction.guild.id)
            active_accounts = [a for a in accounts if a.get('last_post_id') != "DISABLED"]
            
            channel_ids = await truth_db.get_truth_channels(interaction.guild.id)
            
            if not active_accounts:
                await interaction.followup.send(
                    "❌ No Truth Social accounts configured for this server. Add accounts first with `/truth track`.", 
                    ephemeral=True
                )
                return
            
            if not channel_ids:
                await interaction.followup.send(
                    "❌ No channels configured for this server. Add channels first with `/truth addchannel`.", 
                    ephemeral=True
                )
                return
            
            # Update settings for this specific guild
            settings = {'enabled': True}
            success = await truth_db.update_guild_settings(interaction.guild.id, settings)
            
            if success:
                embed = discord.Embed(
                    title="Tracking Enabled",
                    description="✅ Truth Social tracking has been activated! Posts will now appear in configured channels.",
                    color=0x2ECC71  # Green
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to enable tracking.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error enabling Truth Social tracking: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    @truth_group.command(name="disable", description="Disable Truth Social tracking")
    async def disable_command(self, interaction: discord.Interaction):
        """Disable Truth Social tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Update settings for this specific guild
            settings = {'enabled': False}
            success = await truth_db.update_guild_settings(interaction.guild.id, settings)
            
            if success:
                embed = discord.Embed(
                    title="Tracking Disabled",
                    description="Truth Social tracking has been deactivated for this server. No posts will be sent until re-enabled.",
                    color=0xE74C3C  # Red
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to disable tracking.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error disabling Truth Social tracking: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
    
    @truth_group.command(name="status", description="Show status of Truth Social tracking")
    async def status_command(self, interaction: discord.Interaction):
        """Show status of Truth Social tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Get settings for this specific guild
            settings = await truth_db.get_guild_settings(interaction.guild.id)
            
            # Get active accounts for this specific guild
            accounts = await truth_db.get_guild_tracked_accounts(interaction.guild.id)
            active_accounts = [a for a in accounts if a.get('last_post_id') != "DISABLED"]
            
            # Get channels for this specific guild
            channel_ids = await truth_db.get_truth_channels(interaction.guild.id)
            channels = []
            for channel_id in channel_ids:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    channels.append(channel.mention)
            
            # Get tracking status
            tracking_status = tracker.get_tracking_status()
            is_tracking = tracking_status.get('is_tracking', False) and settings.get('enabled', False)
            
            # Create embed
            is_active = truth_service.is_active_hours()
            current_interval = settings.get('check_interval', TRUTH_DEFAULT_INTERVAL) if is_active else TRUTH_NIGHT_INTERVAL
            color = 0x2ECC71 if is_tracking else 0xE74C3C
            
            # Emoji for status
            status_emoji = "🟢" if is_tracking else "🔴"
            status_text = "Active" if is_tracking else "Inactive"
            
            # Emoji for time of day
            time_emoji = "☀️" if is_active else "🌙"
            time_state = "Active Hours" if is_active else "Night Mode"
            
            embed = discord.Embed(
                title=f"Truth Social Tracker for {interaction.guild.name}",
                color=color
            )
            
            # Set thumbnail
            embed.set_thumbnail(url="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTGQlZkYBgEbptbNjrWpJjzqEhPfY8ugpIsXA&s")
            
            # Status fields
            embed.add_field(
                name=f"🔄 Tracker Status",
                value=f"{status_emoji} **{status_text}**",
                inline=False
            )
            
            # Interval section with day/night indicator
            embed.add_field(
                name=f"⏰Time Mode: {time_state} {time_emoji}",
                value=(
                    f"**Server Check Interval:** `{settings.get('check_interval', TRUTH_DEFAULT_INTERVAL)}s`\n"
                    f"**Current Check Rate:** `{current_interval}s`\n"
                    f"**Night Mode Interval:** `{TRUTH_NIGHT_INTERVAL}s`"
                ),
                inline=False
            )
            
            # Accounts section - server-specific
            if active_accounts:
                # Format with links
                accounts_text = ""
                for a in active_accounts[:5]:
                    # Get account info to show pfp if available
                    accounts_text += f"👤 [`@{a['handle']}`](https://truthsocial.com/@{a['handle']})\n"
                
                if len(active_accounts) > 5:
                    accounts_text += f"\n*...and {len(active_accounts) - 5} more*"
            else:
                accounts_text = "*No accounts tracked in this server*"
                
            embed.add_field(
                name=f"👥 Tracked Accounts ({len(active_accounts)})",
                value=accounts_text,
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
            
            # Set footer with server icon
            embed.set_footer(
                text=f"Truth Social updates for {interaction.guild.name}",
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None
            )
            
            # Add server banner if available
            if interaction.guild.banner:
                embed.set_image(url=interaction.guild.banner.url)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error getting Truth Social status: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)