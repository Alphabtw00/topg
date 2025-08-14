"""
DexScreener live tracker service for real-time token listings
Hybrid approach: requires both enabled status AND channels
"""
import asyncio
import time
import discord
from datetime import datetime
from typing import Dict, List, Optional
from utils.logger import get_logger
import repository.dex_tracker_repo as dex_db
from config import (
    DEX_TRACKER_POLL_INTERVAL,
    DEX_TRACKER_CHAINS
)

logger = get_logger()

# Simple tracking state
tracking_task = None
is_tracking = False
last_check_time = None

# Hybrid cache - only enabled guilds with channels
_active_channels = {}  # guild_id -> [channel_ids] - only enabled guilds with channels
_last_token_address = ""

# Task lock
_task_lock = asyncio.Lock()

async def initialize_and_start_dex_tracking(bot):
    """Initialize and start DexScreener tracking if enabled guilds with channels exist"""
    try:
        logger.info("Initializing DexScreener live tracker...")
        
        # Initialize database tables
        await dex_db.setup_dex_tables()
        
        # Build cache and start if needed
        await rebuild_cache_and_restart_if_needed(bot)
        
        logger.info("DexScreener tracking initialization complete")
    except Exception as e:
        logger.error(f"Error initializing DexScreener tracking: {e}")


async def rebuild_cache_and_restart_if_needed(bot):
    """Rebuild cache and start/stop tracking based on enabled guilds with channels"""
    global _active_channels
    
    try:
        # Get enabled guilds with channels (hybrid query)
        new_channels = await dex_db.get_enabled_guild_channels()
        
        # Update cache
        _active_channels = new_channels
        
        # Start or stop based on whether we have enabled guilds with channels
        if _active_channels:
            total_channels = sum(len(channels) for channels in _active_channels.values())
            logger.info(f"Found {len(_active_channels)} enabled guilds with {total_channels} channels")
            await start_tracking(bot)
        else:
            logger.info("No enabled guilds with channels, stopping dex paid tracking")
            await stop_tracking()
            
    except Exception as e:
        logger.error(f"Error rebuilding cache: {e}")


async def start_tracking(bot):
    """Start tracking only if not already running"""
    global tracking_task, is_tracking
    
    async with _task_lock:
        if tracking_task and not tracking_task.done():
            logger.debug("Tracking already running")
            return
        
        tracking_task = bot.loop.create_task(tracking_loop(bot))
        is_tracking = True
        logger.info("DexScreener tracking started")


async def stop_tracking():
    """Stop tracking"""
    global tracking_task, is_tracking
    
    async with _task_lock:
        if tracking_task and not tracking_task.done():
            tracking_task.cancel()
            try:
                await tracking_task
            except asyncio.CancelledError:
                pass
            
        is_tracking = False
        logger.info("DexScreener tracking stopped")


async def tracking_loop(bot):
    """Main tracking loop - ultra optimized"""
    global last_check_time, _last_token_address
    
    try:
        # Initialize last token address
        logger.info("Initializing tracking baseline...")
        initial_data = await bot.services.dexscreener.get_latest_token_profiles()
        if initial_data:
            for token in initial_data:
                chain_id = token.get("chainId", "")
                if not DEX_TRACKER_CHAINS or chain_id in DEX_TRACKER_CHAINS:
                    _last_token_address = token.get("tokenAddress", "")
                    logger.info(f"Tracking baseline: {_last_token_address[:8]}... on {chain_id}")
                    break
        
        while True:
            try:
                start_time = time.time()
                last_check_time = datetime.now()
                
                # Skip if no active channels (enabled guilds with channels)
                if not _active_channels:
                    logger.debug("No active enabled channels, exiting tracking loop")
                    break
                
                # Fetch latest tokens
                latest_tokens = await bot.services.dexscreener.get_latest_token_profiles()
                if not latest_tokens:
                    await asyncio.sleep(DEX_TRACKER_POLL_INTERVAL)
                    continue

                # Find new tokens (stop at last known)
                new_tokens = []
                newest_token = None
                
                for token in latest_tokens:
                    token_addr = token.get("tokenAddress", "")
                    chain_id = token.get("chainId", "")
                    
                    # Skip non-target chains
                    if DEX_TRACKER_CHAINS and chain_id not in DEX_TRACKER_CHAINS:
                        continue
                    
                    # Track newest for next cycle
                    if newest_token is None:
                        newest_token = token
                    
                    # Stop if we hit last known token
                    if token_addr == _last_token_address:
                        break
                    
                    new_tokens.append(token)
                
                # Update reference for next cycle
                if newest_token:
                    _last_token_address = newest_token.get("tokenAddress", "")
                
                # Process new tokens (fire and forget)
                if new_tokens:
                    logger.debug(f"Processing {len(new_tokens)} new tokens")
                    for token in new_tokens:
                        # Create task and don't wait - maximum speed
                        asyncio.create_task(process_token_async(bot, token))
                
                # Sleep for next cycle
                elapsed = time.time() - start_time
                sleep_time = max(0.1, DEX_TRACKER_POLL_INTERVAL - elapsed)
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error in tracking loop: {e}")
                await asyncio.sleep(1)
    
    except asyncio.CancelledError:
        logger.info("Tracking loop cancelled")
    except Exception as e:
        logger.error(f"Fatal tracking error: {e}")
    finally:
        is_tracking = False


async def process_token_async(bot, token_data):
    """Process token completely asynchronously"""
    try:
        token_address = token_data.get("tokenAddress", "")
        chain_id = token_data.get("chainId", "")
        
        if not token_address or not chain_id:
            return
        
        # Get token info
        token_info = await bot.services.dexscreener.get_token_info([token_address], chain_id=chain_id)
        if not token_info or token_address not in token_info:
            return
        
        full_token_info = token_info[token_address]
        symbol = full_token_info.get("baseToken", {}).get("symbol", "UNKNOWN")
        name = full_token_info.get("baseToken", {}).get("name", "Unknown")
        
        # Create embed once
        from ui.embeds import create_dex_tracker_embed
        embed = create_dex_tracker_embed(token_data, full_token_info, token_address, symbol, name)
        if not embed:
            return
        
        # Send to channels and alerts (both async, no waiting)
        asyncio.create_task(send_to_all_channels(bot, embed))
        # asyncio.create_task(send_dex_alerts(bot, token_address, embed, name, symbol))
        
    except Exception as e:
        logger.error(f"Error processing token {token_address}: {e}")


async def send_to_all_channels(bot, embed):
    """Send embed to all active channels (enabled guilds only)"""
    try:
        tasks = []
        for guild_id, channel_ids in _active_channels.items():
            for channel_id in channel_ids:
                channel = bot.get_channel(channel_id)
                if channel:
                    tasks.append(channel.send(embed=embed))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    except Exception as e:
        logger.error(f"Error sending to channels: {e}")


async def send_dex_alerts(bot, token_address, embed, name, symbol):
    """Send DEX alerts to first callers"""
    try:
        from service.mysql_service import fetch_all
        
        # Get all first calls
        first_calls = await fetch_all(
            "SELECT user_id, channel_id, message_id FROM token_first_calls WHERE token_address = %s",
            (token_address,)
        )
        
        if not first_calls:
            return
        
        # Send alerts
        tasks = []
        for user_id, call_channel_id, message_id in first_calls:
            if user_id and call_channel_id:
                tasks.append(send_individual_alert(
                    bot, user_id, call_channel_id, message_id, embed, name, symbol
                ))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    except Exception as e:
        logger.error(f"Error sending DEX alerts for {token_address}: {e}")


async def send_individual_alert(bot, user_id, call_channel_id, message_id, embed, name, symbol):
    """Send individual DEX alert"""
    try:
        call_channel = bot.get_channel(int(call_channel_id))
        if not call_channel:
            return
        
        notification = f"<@{user_id}> DEX paid for {name} (${symbol})!"
        reply_embed = discord.Embed.from_dict(embed.to_dict())
        reply_embed.set_footer(text="DEX Alerts", icon_url=embed.footer.icon_url if embed.footer else None)
        
        if message_id:
            try:
                orig_msg = await call_channel.fetch_message(int(message_id))
                await orig_msg.reply(content=notification, embed=reply_embed)
                return
            except:
                pass
        
        await call_channel.send(content=notification, embed=reply_embed)
        
    except Exception as e:
        logger.error(f"Error sending alert to user {user_id}: {e}")


def get_tracking_status() -> Dict:
    """Get current tracking status"""
    return {
        'is_tracking': is_tracking,
        'last_check': last_check_time,
        'guild_count': len(_active_channels),
        'channel_count': sum(len(channels) for channels in _active_channels.values()),
        'last_token': _last_token_address
    }