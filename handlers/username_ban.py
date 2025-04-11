# handlers/username_ban.py
"""
Lightweight handler for detecting and banning users with forbidden username patterns
"""
import discord
from datetime import datetime
from utils.logger import get_logger
from config import (
    BAN_KEYWORDS,
    COMPILED_BAN_REGEXES,  # Note the double underscore in variable name
    USERNAME_BAN_LOG_CHANNEL,
    USERNAME_BAN_SERVER_ID,
    BAN_FUNNY_REASONS,  # New config for funny ban reasons
    BAN_GIF_URL  # New config for ban GIF
)
import random

logger = get_logger()

async def check_username(member):
    """
    Check if a member's username or display name matches any banned patterns
    
    Args:
        member: Discord member to check
        
    Returns:
        tuple: (should_ban, reason) or (False, None) if no match
    """
    logger.debug(f"Starting username check for {member.id} ({str(member)})")
    
    # Check if this is the configured server
    if not USERNAME_BAN_SERVER_ID:
        logger.debug(f"USERNAME_BAN_SERVER_ID not configured, check aborted for {member.id}")
        return False, None
        
    if member.guild.id != USERNAME_BAN_SERVER_ID:
        logger.debug(f"Member {member.id} in guild {member.guild.id}, not ban server {USERNAME_BAN_SERVER_ID}, check aborted")
        return False, None
        
    # Get all name variants to check
    names_to_check = []
    if str(member):  # Username
        names_to_check.append(str(member))
    if member.display_name:  # Display name
        names_to_check.append(member.display_name)
    if member.nick:  # Nickname (if set)
        names_to_check.append(member.nick)
    
    logger.debug(f"Checking name variants for {member.id}: {[sanitize_for_logging(name) for name in names_to_check]}")
    
    # Check each name variant
    for name in names_to_check:
        # Check keyword patterns (case insensitive)
        name_lower = name.lower()
        
        # Log keywords being checked
        if BAN_KEYWORDS:
            logger.debug(f"Checking {len(BAN_KEYWORDS)} keywords against '{name}'")
            
        for keyword in BAN_KEYWORDS:
            if keyword.lower() in name_lower:
                return True, f"Username contains banned keyword: {keyword}"
        
        # Check regex patterns
        if COMPILED_BAN_REGEXES:
            logger.debug(f"Checking {len(COMPILED_BAN_REGEXES)} regex patterns against '{name}'")
            
        for i, regex in enumerate(COMPILED_BAN_REGEXES):
            try:
                if regex.search(name):
                    return True, f"Username matches banned keyword"
            except Exception as e:
                logger.error(f"Error checking regex pattern #{i+1} against '{name}': {e}")
    
    logger.debug(f"All name checks passed for {member.id} ({str(member)})")
    return False, None

async def ban_user(bot, member, reason):
    """
    Ban a user and log the action
    
    Args:
        bot: Discord bot instance
        member: Discord member to ban
        reason: Reason for the ban
        
    Returns:
        bool: Success or failure
    """
    # Check if this is the configured server
    if not USERNAME_BAN_SERVER_ID:
        logger.warning(f"USERNAME_BAN_SERVER_ID not configured, ban aborted for {member.id}")
        return False
        
    if member.guild.id != USERNAME_BAN_SERVER_ID:
        logger.warning(f"Member {member.id} in guild {member.guild.id}, not ban server {USERNAME_BAN_SERVER_ID}, ban aborted")
        return False
        
    guild = member.guild
    
    # Check bot's permissions
    bot_member = guild.get_member(bot.user.id)
    if not bot_member:
        logger.error(f"Bot not found in guild {guild.id}")
        return False
        
    permissions = bot_member.guild_permissions
    if not permissions.ban_members:
        logger.error(f"Bot lacks 'ban_members' permission in guild {guild.id}")
        return False
    
    try:
        # Get user info before banning
        user_info = {
            'id': member.id,
            'username': str(member),
            'display_name': member.display_name,
            'nickname': member.nick,
            'created_at': member.created_at.isoformat() if member.created_at else None,
            'joined_at': member.joined_at.isoformat() if member.joined_at else None,
            'avatar_url': str(member.avatar.url) if member.avatar else None
        }
        
        # Only log once with all necessary info
        safe_display_name = sanitize_for_logging(member.display_name)
        logger.warning(f"Banning user {member.id} | Username: {str(member)} | Display Name: {safe_display_name} | Reason: {reason}")
        
        # Try to send DM to the user before banning
        try:
            # Select a random funny reason
            funny_reason = random.choice(BAN_FUNNY_REASONS) if BAN_FUNNY_REASONS else "Bye bye!"
            
            # Create embed for DM
            dm_embed = discord.Embed(
                title="You've been banned",
                description=funny_reason,
                color=discord.Color.red()
            )
            
            # Add the GIF to the embed
            if BAN_GIF_URL:
                dm_embed.set_image(url=BAN_GIF_URL)
                
            # Send DM with embed
            await member.send(embed=dm_embed)
            logger.debug(f"Successfully sent ban notification DM to {member.id}")
        except Exception as e:
            logger.debug(f"Could not send DM to {member.id}: {e}")
        
        # Ban the user
        ban_reason = f"Automatic ban: {reason}"
        await guild.ban(member, reason=ban_reason, delete_message_days=1)
        
        # Send log message if channel is configured
        if USERNAME_BAN_LOG_CHANNEL:
            log_result = await send_ban_log(bot, guild.id, user_info, reason)
            logger.debug(f"Ban log message sent: {log_result}")
            
        return True
    except discord.Forbidden:
        logger.error(f"Missing permissions to ban {member.id} in {guild.id}")
        return False
    except Exception as e:
        logger.error(f"Failed to ban user {member.id} in {guild.id}: {e}")
        return False

async def send_ban_log(bot, guild_id, user_info, reason):
    """
    Send a ban log message to the configured channel
    
    Args:
        bot: Discord bot instance
        guild_id: ID of the guild
        user_info: User information dictionary
        reason: Reason for the ban
    """
    if not USERNAME_BAN_LOG_CHANNEL:
        logger.warning("USERNAME_BAN_LOG_CHANNEL not configured, cannot send log")
        return False
        
    try:
        logger.debug(f"Attempting to find log channel {USERNAME_BAN_LOG_CHANNEL}")
        channel = bot.get_channel(USERNAME_BAN_LOG_CHANNEL)
        if not channel:
            logger.warning(f"Cannot find log channel {USERNAME_BAN_LOG_CHANNEL}")
            return False
        
        # Create embed with enhanced styling
        embed = discord.Embed(
            title="Member Banned",
            description=f"@{user_info['username']} ({user_info['display_name']})",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        
        
        # Add user info
        embed.add_field(name="User ID", value=user_info['id'], inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        # Set author with user icon
        if user_info.get('avatar_url'):
            embed.set_author(name="Member Banned", icon_url=user_info.get('avatar_url'))
        else:
            embed.set_author(name="Member Banned")
            
        # Set thumbnail to user avatar
        if user_info.get('avatar_url'):
            embed.set_thumbnail(url=user_info['avatar_url'])
        
        # Add GIF at the bottom of the embed
        if BAN_GIF_URL:
            embed.set_image(url=BAN_GIF_URL)
        
        # Add footer
        embed.set_footer(text=f"Account created: {user_info['created_at'].split('T')[0]}")
        
        # Send the embed
        await channel.send(embed=embed)
        return True
    except Exception as e:
        logger.error(f"Failed to send ban log: {e}")
        return False

def sanitize_for_logging(text):
    """
    Make text safe for logging by replacing non-ASCII characters
    """
    if text is None:
        return "None"
    return text.encode('ascii', 'replace').decode('ascii')