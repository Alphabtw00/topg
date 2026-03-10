"""
Lightweight handler for detecting and banning users with forbidden username patterns
"""
import discord
from datetime import datetime
from utils.logger import get_logger
from config import (
    BAN_KEYWORDS,
    COMPILED_BAN_REGEXES,
    USERNAME_BAN_LOG_CHANNEL,
    USERNAME_BAN_SERVER_ID,
    BAN_FUNNY_REASONS,
    BAN_GIF_URL
)
from utils.formatters import safe_text
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
    if str(member):
        names_to_check.append(str(member))
    if member.display_name:
        names_to_check.append(member.display_name)
    if member.nick:
        names_to_check.append(member.nick)

    logger.debug(f"Checking name variants for {member.id}: {[safe_text(name) for name in names_to_check]}")

    for name in names_to_check:
        name_lower = name.lower()

        if BAN_KEYWORDS:
            logger.debug(f"Checking {len(BAN_KEYWORDS)} keywords against '{name}'")

        for keyword in BAN_KEYWORDS:
            if keyword.lower() in name_lower:
                return True, f"Username contains banned keyword: {keyword}"

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


async def ban_user(bot, member, reason, delete_days=1):
    """
    Ban a user and log the action.
    Runs all safety checks, DMsthe user, then bans.

    Args:
        bot: Discord bot instance
        member: Discord member to ban
        reason: Reason for the ban
        delete_days: Number of days of messages to delete (default: 1)

    Returns:
        bool: Success or failure
    """
    guild = member.guild

    # Check if target is actually in the server
    if not guild.get_member(member.id):
        logger.warning(f"User {member.id} is not in guild {guild.id}, ban aborted")
        return False

    # Check if trying to ban the guild owner
    if member.id == guild.owner_id:
        logger.error(f"Cannot ban user {member.id} ({str(member)}) - they are the server owner")
        return False

    # Check if trying to ban the bot itself
    if member.id == bot.user.id:
        logger.error(f"Cannot ban self")
        return False

    # Check bot exists in guild and has ban permission
    bot_member = guild.get_member(bot.user.id)
    if not bot_member:
        logger.error(f"Bot not found in guild {guild.id}")
        return False

    if not bot_member.guild_permissions.ban_members:
        logger.error(f"Bot lacks 'ban_members' permission in guild {guild.id}")
        return False

    # Check role hierarchy — bot vs target
    if not guild.me.top_role > member.top_role:
        logger.error(f"Cannot ban user {member.id} ({str(member)}) - their role is higher than or equal to the bot's highest role")
        return False

    try:
        # Collect user info before banning
        user_info = {
            'id': member.id,
            'username': str(member),
            'display_name': member.display_name,
            'nickname': member.nick,
            'created_at': member.created_at.isoformat() if member.created_at else None,
            'joined_at': member.joined_at.isoformat() if member.joined_at else None,
            'avatar_url': str(member.avatar.url) if member.avatar else None
        }

        delete_days = max(0, min(7, delete_days))

        logger.warning(f"Banning user {member.id} | Username: {safe_text(str(member))} | Display Name: {safe_text(member.display_name)} | Reason: {reason} | Delete Messages: {delete_days} days")

        # DM the user before banning (while they still share the server)
        try:
            funny_reason = random.choice(BAN_FUNNY_REASONS) if BAN_FUNNY_REASONS else "Bye bye!"

            dm_embed = discord.Embed(
                title="You've been banned",
                description=funny_reason,
                color=discord.Color.red()
            )

            if BAN_GIF_URL:
                dm_embed.set_image(url=BAN_GIF_URL)

            await member.send(embed=dm_embed)
            logger.debug(f"Successfully sent ban notification DM to {member.id}")
        except Exception as e:
            logger.debug(f"Could not send DM to {member.id}: {e}")

        # Ban
        await guild.ban(member, reason=f"Automatic ban: {reason}", delete_message_days=delete_days)

        # Send to log channel if configured (auto-ban flow)
        if USERNAME_BAN_LOG_CHANNEL:
            user_info['delete_days'] = delete_days
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
    Send a ban log message to the configured channel (used by auto-ban flow)

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
        channel = bot.get_channel(USERNAME_BAN_LOG_CHANNEL)
        if not channel:
            logger.warning(f"Cannot find log channel {USERNAME_BAN_LOG_CHANNEL}")
            return False

        embed = discord.Embed(
            title="Member Banned",
            description=f"@{user_info['username']} ({user_info['display_name']})",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )

        embed.add_field(name="User ID", value=user_info['id'], inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)

        if 'delete_days' in user_info:
            days_text = f"{user_info['delete_days']} day(s)" if user_info['delete_days'] > 0 else "None"
            embed.add_field(name="Message History Deleted", value=days_text, inline=True)

        if user_info.get('avatar_url'):
            embed.set_author(name="Member Banned", icon_url=user_info.get('avatar_url'))
        else:
            embed.set_author(name="Member Banned")

        if user_info.get('avatar_url'):
            embed.set_thumbnail(url=user_info['avatar_url'])

        if BAN_GIF_URL:
            embed.set_image(url=BAN_GIF_URL)

        embed.set_footer(text=f"Account created: {user_info['created_at'].split('T')[0]}")

        await channel.send(embed=embed)
        return True
    except Exception as e:
        logger.error(f"Failed to send ban log: {e}")
        return False