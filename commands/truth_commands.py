"""
Commands for managing Truth Social tracking
"""
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional
import repository.truth_repo as truth_db
import handlers.truth_tracker as tracker
from service.proxy_handler import ProxyRotator
from config import VERIFIED_EMOJI, TRUTH_DEFAULT_INTERVAL
from utils.logger import get_logger
from utils.formatters import format_value, format_date
from bot.error_handler import create_error_handler

logger = get_logger()

class TruthCommands(commands.Cog):
    """Truth Social tracking commands"""

    def __init__(self, bot):
        self.bot = bot
        self.proxy_rotator = None
        self.init_proxy_rotator()
    
    def init_proxy_rotator(self):
        """Initialize proxy rotator for commands"""
        try:
            self.proxy_rotator = ProxyRotator(
                countries=["US"],  # Prefer US proxies for Truth Social
                protocol="http",
                auto_rotate=True,
                max_proxies=10,
                debug=False
            )
            logger.info("Proxy rotator initialized for Truth commands")
        except Exception as e:
            logger.error(f"Failed to initialize proxy rotator: {e}")
            self.proxy_rotator = None
    
    async def get_proxy(self, force_new=False):
        """Get a proxy for a command"""
        if not self.proxy_rotator:
            return None
            
        return await self.proxy_rotator.get_proxy_for_request(force_new=force_new)
    
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
            
            # Get proxy for request
            proxy = await self.get_proxy(force_new=True)
            
            # Search for the account using user metadata API
            user_info = await self.bot.services.truthsocial.get_user_info(handle, proxy=proxy)
            
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
                # Just set a placeholder last_post_id value
                # We'll use "0" - this will catch all new posts going forward
                await truth_db.update_last_post(interaction.guild.id, handle, "0")
                
                # Clear cache to ensure the new account is picked up immediately
                await tracker.clear_cache_for_guild(interaction.guild.id)
                
                # Create a rich embed profile-like display
                embed = discord.Embed(
                    title=f"@{handle} Added to Tracking",
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
                
                # Add the user who added it
                embed.add_field(
                    name="Added by",
                    value=f"{interaction.user.mention}",
                    inline=True
                )
                
                # Add proxy info if used
                if proxy:
                    embed.add_field(
                        name="Using Proxy",
                        value="✅ Proxy rotation enabled",
                        inline=True
                    )
                
                # Set the footer with creation date
                embed.set_footer(text=f"Account created: {formatted_date}")
                
                # Send publicly so others can see who added it
                await interaction.followup.send(embed=embed)
                
                # Track command usage
                self.bot.record_command_usage("truth_track")
                logger.info(f"{interaction.user.name} added @{handle} in server '{interaction.guild.name}' for tracking")
            else:
                await interaction.followup.send(f"❌ Failed to add @{handle} to tracking database.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error tracking Truth Social account: {e}")
            await interaction.followup.send(
                f"❌ Couldn't set up tracking for @{handle}. Please try again later.", 
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
            
            # Remove the account
            success = await truth_db.remove_truth_account(interaction.guild.id, handle)
            
            if success:
                # Clear cache to ensure the removed account is not tracked anymore
                await tracker.clear_cache_for_guild(interaction.guild.id)
                
                embed = discord.Embed(
                    title=f"Stopped tracking @{handle}",
                    description=f"No longer tracking posts from this account in this server.",
                    color=0xF44336  # Red
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Track command usage
                self.bot.record_command_usage("truth_untrack")
                logger.info(f"{interaction.user.name} removed @{handle} from tracking in server '{interaction.guild.name}'")
            else:
                await interaction.followup.send(f"❌ Failed to remove tracking for @{handle}.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error untracking Truth Social account: {e}")
            await interaction.followup.send(f"Error untracking @{handle}. Please try again later.", ephemeral=True)
    
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
                # Clear cache to ensure the new channel is used immediately
                await tracker.clear_cache_for_guild(interaction.guild.id)
                
                embed = discord.Embed(
                    title="Channel Added",
                    description=f"{channel.mention} will now receive Truth Social updates!",
                    color=0x2ECC71  # Green
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Track command usage
                self.bot.record_command_usage("truth_addchannel")
                logger.info(f"{interaction.user.name} added channel #{channel.name} in server '{interaction.guild.name}' for Truth Social tracking")
            else:
                await interaction.followup.send(f"❌ Failed to configure {channel.mention}.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error adding Truth Social channel: {e}")
            await interaction.followup.send(f"❌ Error adding {channel.mention} to Truth Social Updates. Please try again later.", ephemeral=True)
    
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
                # Clear cache to ensure the removed channel is not used anymore
                await tracker.clear_cache_for_guild(interaction.guild.id)
                
                embed = discord.Embed(
                    title="Channel Removed",
                    description=f"{channel.mention} will no longer receive Truth Social updates.",
                    color=0xE67E22  # Orange
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Track command usage
                self.bot.record_command_usage("truth_removechannel")
                logger.info(f"{interaction.user.name} removed channel #{channel.name} in server '{interaction.guild.name}' from Truth Social tracking")
            else:
                await interaction.followup.send(f"❌ {channel.mention} was not configured for updates.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error removing Truth Social channel: {e}")
            await interaction.followup.send(f"❌ Error removing {channel.mention} from Truth Social Updates. Please try again later.", ephemeral=True)
    
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
                # Clear cache to ensure the enabled status is picked up immediately
                await tracker.clear_cache_for_guild(interaction.guild.id)
                
                # Ensure the tracking task is running
                await tracker.start_tracking(self.bot)
                
                embed = discord.Embed(
                    title="Tracking Enabled",
                    description="✅ Truth Social tracking has been activated! Posts will now appear in configured channels.",
                    color=0x2ECC71  # Green
                )
                
                # Add proxy info if available
                if tracker.proxy_rotator and tracker.proxy_rotator.enabled:
                    embed.add_field(
                        name="Proxy Support",
                        value="✅ Proxy rotation is enabled to help avoid rate limits",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Track command usage
                self.bot.record_command_usage("truth_enable")
                logger.info(f"{interaction.user.name} enabled Truth Social tracking in server '{interaction.guild.name}'")
            else:
                await interaction.followup.send("❌ Failed to enable tracking.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error enabling Truth Social tracking: {e}")
            await interaction.followup.send(f"❌ Error enabling Truth Social tracking. Please try again later.", ephemeral=True)
    
    @truth_group.command(name="disable", description="Disable Truth Social tracking")
    async def disable_command(self, interaction: discord.Interaction):
        """Disable Truth Social tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Update settings for this specific guild
            settings = {'enabled': False}
            success = await truth_db.update_guild_settings(interaction.guild.id, settings)
            
            if success:
                # Clear cache to ensure the disabled status is picked up immediately
                await tracker.clear_cache_for_guild(interaction.guild.id)
                
                embed = discord.Embed(
                    title="Tracking Disabled",
                    description="Truth Social tracking has been deactivated for this server. No posts will be sent until re-enabled.",
                    color=0xE74C3C  # Red
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Track command usage
                self.bot.record_command_usage("truth_disable")
                logger.info(f"{interaction.user.name} disabled Truth Social tracking in server '{interaction.guild.name}'")
            else:
                await interaction.followup.send("❌ Failed to disable tracking.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error disabling Truth Social tracking: {e}")
            await interaction.followup.send(f"❌ Error disabling Truth Social tracking. Please try again later.", ephemeral=True)
    
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
            check_interval = settings.get('check_interval', TRUTH_DEFAULT_INTERVAL)
            color = 0x2ECC71 if is_tracking else 0xE74C3C
            
            # Emoji for status
            status_emoji = "🟢" if is_tracking else "🔴"
            status_text = "Active" if is_tracking else "Inactive"
            
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
            
            # Check interval
            embed.add_field(
                name=f"⏰ Check Interval",
                value=f"**{check_interval}s**",
                inline=False
            )
            
            # Proxy status
            proxy_enabled = tracking_status.get('proxy_enabled', False) or (self.proxy_rotator is not None and self.proxy_rotator.enabled)
            embed.add_field(
                name=f"🌐 Proxy Rotation",
                value=f"{'✅ Enabled' if proxy_enabled else '❌ Disabled'}",
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
            
            # Track command usage
            self.bot.record_command_usage("truth_status")
            
        except Exception as e:
            logger.error(f"Error getting Truth Social status: {e}")
            await interaction.followup.send(f"❌ Error getting Truth Social status for server", ephemeral=True)
    
    @truth_group.command(name="search", description="Search Truth Social for users, posts, or hashtags")
    @app_commands.describe(
        query="What to search for",
        search_type="Type of search to perform",
        limit="Maximum number of results (default: 10)"
    )
    @app_commands.choices(search_type=[
        app_commands.Choice(name="Accounts", value="accounts"),
        app_commands.Choice(name="Posts", value="statuses"),
        app_commands.Choice(name="Hashtags", value="hashtags"),
        app_commands.Choice(name="Groups", value="groups")
    ])
    async def search_command(self, interaction: discord.Interaction, 
                            query: str, 
                            search_type: str,
                            limit: Optional[int] = 10):
        """Search Truth Social for different types of content"""
        await interaction.response.defer(thinking=True)
        
        if limit > 40:
            limit = 40  # Cap maximum results at 40 to prevent overload
        
        try:
            # Get proxy for request
            proxy = await self.get_proxy(force_new=True)
            
            # Perform search
            results = await self.bot.services.truthsocial.search(
                searchtype=search_type,
                query=query,
                limit=limit,
                proxy=proxy
            )
            
            if not results:
                await interaction.followup.send(f"No results found for '{query}'")
                return
                
            # Extract the correct result type
            items = results.get(search_type, [])
            
            if not items:
                await interaction.followup.send(f"No {search_type} found matching '{query}'")
                return
                
            # Create embed based on search type
            if search_type == "accounts":
                embed = self.create_account_search_embed(query, items)
            elif search_type == "statuses":
                embed = self.create_status_search_embed(query, items)
            elif search_type == "hashtags":
                embed = self.create_hashtag_search_embed(query, items)
            elif search_type == "groups":
                embed = self.create_group_search_embed(query, items)
            else:
                embed = discord.Embed(
                    title=f"Search results for '{query}'",
                    description=f"Found {len(items)} {search_type}",
                    color=0xE12626  # Truth Social red
                )
                
            await interaction.followup.send(embed=embed)
            
            # Track command usage
            self.bot.record_command_usage(f"truth_search_{search_type}")
            
        except Exception as e:
            logger.error(f"Error searching Truth Social: {e}")
            await interaction.followup.send(f"❌ Error searching Truth Social. Please try again later.")
    
    def create_account_search_embed(self, query, accounts):
        """Create an embed for account search results"""
        embed = discord.Embed(
            title=f"Account search results for '{query}'",
            description=f"Found {len(accounts)} accounts",
            color=0xE12626  # Truth Social red
        )
        
        for i, account in enumerate(accounts[:10]):  # Show top 10 accounts
            name = account.get("display_name", "Unknown")
            username = account.get("username", "unknown")
            verified = account.get("verified", False)
            followers = account.get("followers_count", 0)
            
            # Format name with verification badge if applicable
            name_display = f"{name} {VERIFIED_EMOJI if verified else ''}"
            
            embed.add_field(
                name=f"{i+1}. {name_display} (@{username})",
                value=f"[Profile](https://truthsocial.com/@{username}) • {format_value(followers)} followers",
                inline=False
            )
            
        if len(accounts) > 10:
            embed.set_footer(text=f"Showing 10 of {len(accounts)} results")
            
        return embed
    
    def create_status_search_embed(self, query, statuses):
        """Create an embed for status search results"""
        embed = discord.Embed(
            title=f"Post search results for '{query}'",
            description=f"Found {len(statuses)} posts",
            color=0xE12626  # Truth Social red
        )
        
        for i, status in enumerate(statuses[:5]):  # Show top 5 statuses
            content = status.get("content", "")
            
            # Remove HTML tags from content (simple version)
            import re
            clean_content = re.sub(r'<[^>]+>', '', content)
            if len(clean_content) > 200:
                clean_content = clean_content[:197] + "..."
                
            account = status.get("account", {})
            name = account.get("display_name", "Unknown")
            username = account.get("username", "unknown")
            verified = account.get("verified", False)
            
            # Format name with verification badge if applicable
            name_display = f"{name} {VERIFIED_EMOJI if verified else ''}"
            
            embed.add_field(
                name=f"{i+1}. {name_display} (@{username})",
                value=f"{clean_content}\n[View Post](https://truthsocial.com/@{username}/posts/{status.get('id')})",
                inline=False
            )
            
        if len(statuses) > 5:
            embed.set_footer(text=f"Showing 5 of {len(statuses)} results")
            
        return embed
    
    def create_hashtag_search_embed(self, query, hashtags):
        """Create an embed for hashtag search results"""
        embed = discord.Embed(
            title=f"Hashtag search results for '{query}'",
            description=f"Found {len(hashtags)} hashtags",
            color=0xE12626  # Truth Social red
        )
        
        for i, hashtag in enumerate(hashtags[:15]):  # Show top 15 hashtags
            name = hashtag.get("name", "unknown")
            url = f"https://truthsocial.com/tags/{name}"
            count = hashtag.get("history", [{}])[0].get("uses", 0)
            
            embed.add_field(
                name=f"{i+1}. #{name}",
                value=f"[View Tag]({url}) • {format_value(count)} uses",
                inline=True
            )
            
        if len(hashtags) > 15:
            embed.set_footer(text=f"Showing 15 of {len(hashtags)} results")
            
        return embed
    
    def create_group_search_embed(self, query, groups):
        """Create an embed for group search results"""
        embed = discord.Embed(
            title=f"Group search results for '{query}'",
            description=f"Found {len(groups)} groups",
            color=0xE12626  # Truth Social red
        )
        
        for i, group in enumerate(groups[:10]):  # Show top 10 groups
            name = group.get("title", "Unknown")
            group_id = group.get("id", "")
            members = group.get("member_count", 0)
            
            embed.add_field(
                name=f"{i+1}. {name}",
                value=f"[View Group](https://truthsocial.com/groups/{group_id}) • {format_value(members)} members",
                inline=False
            )
            
        if len(groups) > 10:
            embed.set_footer(text=f"Showing 10 of {len(groups)} results")
            
        return embed
    
    # Add error handlers for all commands
    @track_command.error
    @untrack_command.error
    @addchannel_command.error
    @removechannel_command.error
    @enable_command.error
    @disable_command.error
    @status_command.error
    @search_command.error
    async def truth_command_error(self, interaction, error):
        """Handle errors in Truth Social commands"""
        error_handler = create_error_handler("truth_commands")
        await error_handler(self, interaction, error)