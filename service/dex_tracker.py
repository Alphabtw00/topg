"""
DexScreener live tracker service for real-time token listings
"""
import asyncio
import time
import discord
from datetime import datetime
from typing import Dict, List, Set, Optional
from utils.logger import get_logger
import repository.dex_tracker_repo as dex_db
from config import (
    DEX_TRACKER_POLL_INTERVAL,
    DEX_TRACKER_CHAINS
)

logger = get_logger()

# Tracking state
tracking_task = None
is_tracking = False
last_check_time = None
next_check_time = None

# Efficient tracking system
_guild_channels = {}  # guild_id -> [channel_ids]
_last_token_address = ""  # Last token address we processed

# Task lock
_task_lock = asyncio.Lock()

async def initialize_and_start_dex_tracking(bot):
    """Initialize and start DexScreener tracking"""
    try:
        logger.info("Initializing DexScreener live tracker...")
        
        # Initialize database tables
        await dex_db.setup_dex_tables()
        
        # Build tracking cache
        await build_tracking_cache()
        
        # Get enabled guilds
        enabled_guilds = await dex_db.get_all_enabled_guilds()
        if enabled_guilds:
            logger.info(f"Found {len(enabled_guilds)} guilds with DexScreener tracking enabled")
            await start_tracking(bot)
        else:
            logger.info("No guilds with DexScreener tracking enabled")
            
        logger.info("DexScreener tracking initialization complete")
    except Exception as e:
        logger.error(f"Error initializing DexScreener tracking: {e}")


async def build_tracking_cache():
    """Build optimized tracking cache in a single operation"""
    global _guild_channels
    
    try:
        # Get all guild channel mappings
        guild_channels = await dex_db.get_all_guild_channels()
        
        # Update global cache
        _guild_channels = guild_channels
        
        logger.info(f"Built DexScreener tracking cache: {len(_guild_channels)} guilds with channels")
        
    except Exception as e:
        logger.error(f"Error building DexScreener tracking cache: {e}")


async def clear_cache_for_guild(guild_id: int):
    """Clear cache for guild changes"""
    await build_tracking_cache()
    logger.debug(f"DexScreener tracking cache rebuilt for guild {guild_id}")


async def refresh_all_caches():
    """Rebuild all caches"""
    await build_tracking_cache()


async def start_tracking(bot):
    """Start the DexScreener tracking loop with auto-restart capability"""
    global tracking_task, is_tracking
    
    async with _task_lock:
        # Check if task is already running
        if tracking_task and not tracking_task.done():
            logger.info("DexScreener tracking already running")
            return True
        
        # Create and start the task
        tracking_task = bot.loop.create_task(tracking_loop(bot))
        is_tracking = True
        logger.info("DexScreener tracking started")
        return True


async def stop_tracking():
    """Stop the DexScreener tracking loop"""
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
        return True


async def tracking_loop(bot):
    """Main tracking loop with ultra-optimized processing"""
    global last_check_time, next_check_time, _last_token_address
    
    try:
        # Ensure cache is loaded
        if not _guild_channels:
            await build_tracking_cache()
        
        # Initialize last token address by fetching once
        logger.info("Fetching initial tokens to establish tracking baseline")
        initial_data = await bot.services.dexscreener.get_latest_token_profiles()
        if initial_data and len(initial_data) > 0:
            # Find the first token that matches our target chains
            for token in initial_data:
                chain_id = token.get("chainId", "")
                if not DEX_TRACKER_CHAINS or chain_id in DEX_TRACKER_CHAINS:
                    _last_token_address = token.get("tokenAddress", "")
                    logger.info(f"Initialized DexScreener tracker with latest token: {_last_token_address} on {chain_id}")
                    break
        else:
            logger.warning("Failed to initialize DexScreener tracker with initial tokens")
        
        while True:
            try:
                start_time = time.time()
                
                # Update timing info
                last_check_time = datetime.now()
                
                # Skip if no channels to send to
                if not _guild_channels:
                    logger.debug("No channels configured, skipping poll cycle")
                    await asyncio.sleep(DEX_TRACKER_POLL_INTERVAL)
                    continue
                
                logger.debug(f"Polling DexScreener at {last_check_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Fetch latest tokens
                latest_tokens = await bot.services.dexscreener.get_latest_token_profiles()
                logger.debug(f"Received {len(latest_tokens) if latest_tokens else 0} tokens from DexScreener API")

                # Early return if no tokens
                if not latest_tokens:
                    logger.warning("No tokens returned from API")
                    await asyncio.sleep(DEX_TRACKER_POLL_INTERVAL)
                    continue

                # Track the newest token we'll see this cycle (first one that matches our chains)
                newest_token = None
                new_tokens = []
                processed_count = 0
                
                # Process tokens until we hit our last known token
                for token in latest_tokens:
                    processed_count += 1
                    
                    token_addr = token.get("tokenAddress", "")
                    chain_id = token.get("chainId", "")
                    
                    # Skip tokens not in our target chains
                    if DEX_TRACKER_CHAINS and chain_id not in DEX_TRACKER_CHAINS:
                        continue
                    
                    # Store the first matching token as our new latest token
                    if newest_token is None:
                        newest_token = token
                        logger.debug(f"New reference token will be: {token_addr} on chain {chain_id}")
                    
                    # If we hit our previously stored token, we've seen everything newer already
                    if token_addr == _last_token_address:
                        logger.debug(f"Found last processed token {token_addr} at position {processed_count}, stopping scan")
                        break
                    
                    # This is a new token we need to process
                    logger.debug(f"New token found: {token_addr} on chain {chain_id}")
                    new_tokens.append(token)
                
                # Update our reference point for the next cycle
                if newest_token:
                    prev_token = _last_token_address
                    _last_token_address = newest_token.get("tokenAddress", "")
                    logger.debug(f"Updated tracking reference from {prev_token} to {_last_token_address}")
                
                # Process new tokens in parallel
                if new_tokens:
                    logger.debug(f"Found {len(new_tokens)} new tokens to process out of {processed_count} scanned")
                    
                    # Process tokens concurrently for maximum throughput
                    process_tasks = []
                    for token in new_tokens:
                        task = process_new_token(bot, token)
                        process_tasks.append(task)
                    
                    # Wait for all processing to complete
                    if process_tasks:
                        await asyncio.gather(*process_tasks, return_exceptions=True)
                else:
                    logger.debug(f"No new tokens found after scanning {processed_count} entries")
                
                # Calculate precise sleep time for consistent polling
                elapsed = time.time() - start_time
                sleep_time = max(0.1, DEX_TRACKER_POLL_INTERVAL - elapsed)
                next_check_time = datetime.now().timestamp() + sleep_time
                logger.debug(f"Poll cycle completed in {elapsed:.2f}s, sleeping for {sleep_time:.2f}s")
                
                # Sleep until next check
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                logger.info("DexScreener tracking task cancelled")
                raise
                
            except Exception as e:
                logger.error(f"Error in DexScreener tracking loop: {e}")
                await asyncio.sleep(1)  # Short sleep on error
    
    except asyncio.CancelledError:
        logger.info("DexScreener tracking loop cancelled")
    except Exception as e:
        logger.error(f"Fatal error in DexScreener tracking: {e}")
        # Try to restart the tracking task if it fails
        bot.loop.create_task(restart_tracking(bot))


async def restart_tracking(bot):
    """Try to restart the tracking task after a delay"""
    logger.info("Attempting to restart DexScreener tracking after failure")
    await asyncio.sleep(10)  # Wait 10 seconds before trying to restart
    await start_tracking(bot)


async def process_new_token(bot, token_data):
    """Process a new token and send to all subscribed channels"""
    try:
        token_address = token_data.get("tokenAddress", "")
        chain_id = token_data.get("chainId", "")
        
        if not token_address or not chain_id:
            return False
        
        # Get detailed token info from DexScreener
        token_info = await bot.services.dexscreener.get_token_info([token_address], chain_id=chain_id)
        if not token_info or token_address not in token_info:
            return False
        
        # Get the full token information
        full_token_info = token_info[token_address]
        symbol = full_token_info.get("baseToken", {}).get("symbol", "UNKNOWN")
        name = full_token_info.get("baseToken", {}).get("name", "Unknown")
        
        # Create embed for the token (only once)
        from ui.embeds import create_dex_tracker_embed
        embed = create_dex_tracker_embed(token_data, full_token_info)
        if not embed:
            return False
        
        # Create non-blocking tasks for both operations
        tasks = []
        
        # Send to all enabled guilds (original tracking)
        if _guild_channels:
            tasks.append(asyncio.create_task(send_all_guild_updates(bot, embed)))
        
        # Send cross-server DEX alerts (decoupled)
        tasks.append(asyncio.create_task(send_cross_server_dex_alerts(bot, token_address, embed, name, symbol)))
        
        # Fire and forget - don't wait for completion
        if tasks:
            asyncio.gather(*tasks, return_exceptions=True)
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing token {token_address}: {e}")
        return False

async def send_all_guild_updates(bot, embed):
    """Send tracking updates to all enabled guilds"""
    guild_tasks = []
    for guild_id, channel_ids in _guild_channels.items():
        guild_tasks.append(send_guild_updates(bot, guild_id, channel_ids, embed))
    
    if guild_tasks:
        await asyncio.gather(*guild_tasks, return_exceptions=True)

async def send_guild_updates(bot, guild_id, channel_ids, embed):
    """Send updates to a specific guild (clean, no first call logic)"""
    channels = [bot.get_channel(cid) for cid in channel_ids]
    valid_channels = [ch for ch in channels if ch is not None]
    
    if not valid_channels:
        return
    
    # Send to all channels concurrently
    tasks = [ch.send(embed=embed) for ch in valid_channels]
    await asyncio.gather(*tasks, return_exceptions=True)

async def send_cross_server_dex_alerts(bot, token_address, embed, name, symbol):
    """Send DEX alerts to all first callers across all servers"""
    try:
        from handlers.mysql_handler import fetch_all
        
        # Get ALL first calls across ALL servers
        first_calls = await fetch_all(
            "SELECT user_id, channel_id, message_id FROM token_first_calls WHERE token_address = %s",
            (token_address,)
        )
        
        if not first_calls:
            return
        
        # Send alerts to all first callers concurrently
        alert_tasks = []
        for call_data in first_calls:
            user_id, call_channel_id, message_id = call_data
            if user_id and call_channel_id:
                alert_tasks.append(send_individual_dex_alert(
                    bot, user_id, call_channel_id, message_id, embed, name, symbol
                ))
        
        if alert_tasks:
            await asyncio.gather(*alert_tasks, return_exceptions=True)
            
    except Exception as e:
        logger.error(f"Error sending cross-server DEX alerts for {token_address}: {e}")

async def send_individual_dex_alert(bot, user_id, call_channel_id, message_id, embed, name, symbol):
    """Send DEX alert to individual caller"""
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
        logger.error(f"Error sending DEX alert to user {user_id}: {e}")
        

def get_tracking_status() -> Dict:
    """Get current tracking status"""
    return {
        'is_tracking': is_tracking,
        'last_check': last_check_time,
        'next_check': next_check_time,
        'guild_count': len(_guild_channels),
        'channel_count': sum(len(channels) for channels in _guild_channels.values()),
        'last_token': _last_token_address
    }