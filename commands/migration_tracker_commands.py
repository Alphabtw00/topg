"""
Migration tracker commands for graduated tokens
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import service.migration_tracker_service as migration_tracker_service
import repository.migration_tracker_repo as migration_db
from utils.logger import get_logger
from utils.formatters import safe_text
from bot.error_handler import create_error_handler

logger = get_logger()

class MigrationTrackerCommands(commands.Cog):
    """Migration tracker commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    # Create command group
    migration_group = app_commands.Group(
        name="migration",
        description="Manage token graduation migration tracker",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True
    )
    
    @migration_group.command(name="add-channel", description="Add a channel for migration tracking")
    async def addchannel_command(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Add a channel for migration updates"""
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
            success = await migration_db.add_channel(interaction.guild.id, channel.id)
            
            if success:
                # Rebuild cache
                await migration_tracker_service.rebuild_cache_and_restart_if_needed(self.bot)
                
                # Check if tracking is enabled
                settings = await migration_db.get_guild_settings(interaction.guild.id)
                is_enabled = settings.get('enabled', False)
                
                embed = discord.Embed(
                    title="Channel Added",
                    description=f"{channel.mention} added for migration tracking!",
                    color=0x2ECC71 if is_enabled else 0xE67E22
                )
                
                if not is_enabled:
                    embed.add_field(
                        name="⚠️ Tracking Disabled",
                        value="Use `/migration enable` to start receiving updates",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"Migration channel {safe_text(channel.name)} (ID: {channel.id}) added by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
            else:
                await interaction.followup.send(f"ℹ️ Channel {channel.mention} is already configured for migration tracking.", ephemeral=True)
                logger.info(f"Migration channel {safe_text(channel.name)} (ID: {channel.id}) already configured by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
        except Exception as e:
            logger.error(f"Error adding migration channel {safe_text(channel.name)} by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}: {e}")
            await interaction.followup.send("❌ Error adding channel.", ephemeral=True)


    @migration_group.command(name="remove-channel", description="Remove a channel from migration tracker")
    async def removechannel_command(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Remove a channel from migration tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        if not channel:
            channel = interaction.channel
        
        try:
            # Remove channel
            success = await migration_db.remove_channel(interaction.guild.id, channel.id)
            
            if success:
                # Rebuild cache
                await migration_tracker_service.rebuild_cache_and_restart_if_needed(self.bot)
                
                embed = discord.Embed(
                    title="Channel Removed",
                    description=f"{channel.mention} removed from migration tracking.",
                    color=0xE67E22
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"Migration channel {safe_text(channel.name)} (ID: {channel.id}) removed by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
            else:
                await interaction.followup.send(f"ℹ️ {channel.mention} is already not configured for migration tracking.", ephemeral=True)
                logger.info(f"Migration channel {safe_text(channel.name)} (ID: {channel.id}) not configured for removal by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
        except Exception as e:
            logger.error(f"Error removing migration channel {safe_text(channel.name)} by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}: {e}")
            await interaction.followup.send("❌ Error removing channel.", ephemeral=True)


    @migration_group.command(name="enable", description="Enable migration tracking")
    async def enable_command(self, interaction: discord.Interaction):
        """Enable migration tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Check if channels exist
            channels = await migration_db.get_channels(interaction.guild.id)
            if not channels:
                await interaction.followup.send(
                    "❌ No channels configured. Add channels first with `/migration add-channel`.", 
                    ephemeral=True
                )
                return
            
            # Check if already enabled
            settings = await migration_db.get_guild_settings(interaction.guild.id)
            if settings.get('enabled', False):
                await interaction.followup.send("ℹ️ Migration tracking is already enabled for this server.", ephemeral=True)
                return
            
            # Enable tracking
            success = await migration_db.enable_tracking(interaction.guild.id)
            
            if success:
                # Rebuild cache and start tracking
                await migration_tracker_service.rebuild_cache_and_restart_if_needed(self.bot)
                
                embed = discord.Embed(
                    title="Tracking Enabled",
                    description="✅ Migration tracking activated!",
                    color=0x2ECC71
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"Migration tracking enabled by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
            else:
                await interaction.followup.send("❌ Migration tracking is already enabled for this server.", ephemeral=True)
                logger.error(f"Failed to enable migration tracking by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
        except Exception as e:
            logger.error(f"Error enabling migration tracking by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}: {e}")
            await interaction.followup.send("❌ Error enabling tracking.", ephemeral=True)


    @migration_group.command(name="disable", description="Disable migration tracking")
    async def disable_command(self, interaction: discord.Interaction):
        """Disable migration tracking"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Check if already disabled
            settings = await migration_db.get_guild_settings(interaction.guild.id)
            if not settings.get('enabled', False):
                await interaction.followup.send("ℹ️ Migration tracking is already disabled for this server.", ephemeral=True)
                return
            
            success = await migration_db.disable_tracking(interaction.guild.id)
            
            if success:
                # Rebuild cache
                await migration_tracker_service.rebuild_cache_and_restart_if_needed(self.bot)
                
                embed = discord.Embed(
                    title="Tracking Disabled",
                    description="Migration tracking deactivated for this server.",
                    color=0xE74C3C
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"Migration tracking disabled by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
            else:
                await interaction.followup.send("❌ Migration tracking is already disabled for this server.", ephemeral=True)
                logger.error(f"Failed to disable migration tracking by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
                
        except Exception as e:
            logger.error(f"Error disabling migration tracking by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}: {e}")
            await interaction.followup.send("❌ Error disabling tracking.", ephemeral=True)



    @migration_group.command(name="status", description="Show Migration tracking status")
    async def status_command(self, interaction: discord.Interaction):
        """Show tracking status"""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Get guild settings and channels
            settings = await migration_db.get_guild_settings(interaction.guild.id)
            guild_channels = await migration_db.get_channels(interaction.guild.id)
            if guild_channels:
                channel_mentions = " ".join(f"<#{channel_id}>" for channel_id in guild_channels)
            else:
                channel_mentions = "None"   
            
            is_enabled = settings.get('enabled', False)
            has_channels = len(guild_channels) > 0
            
            # Global tracking status
            tracking_status = migration_tracker_service.get_tracking_status()
            is_tracking = tracking_status.get('is_tracking', False)
            
            # This guild's effective status (enabled AND has channels)
            guild_active = is_enabled and has_channels and is_tracking
            
            color = 0x2ECC71 if guild_active else 0xE74C3C
            status_text = "Active" if guild_active else "Inactive"
            
            embed = discord.Embed(
                title=f"Migration Tracker Status - {interaction.guild.name}",
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
            logger.debug(f"Migration status checked by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}")
            
        except Exception as e:
            logger.error(f"Error getting migration status by {safe_text(str(interaction.user))} in {safe_text(interaction.guild.name)}: {e}")
            await interaction.followup.send("❌ Error getting status.", ephemeral=True)

    # Add error handlers
    @addchannel_command.error
    @removechannel_command.error
    @enable_command.error
    @disable_command.error
    async def migration_command_error(self, interaction, error):
        """Handle errors in migration commands"""
        error_handler = create_error_handler("migration_commands")
        await error_handler(self, interaction, error)