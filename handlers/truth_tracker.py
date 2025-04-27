"""
Optimized Truth Social tracker for Discord
"""
import asyncio
import discord
import time
import traceback
from datetime import datetime
from typing import Dict, Optional, Set, List, Any
from utils.logger import get_logger
import repository.truth_repo as truth_db
from ui.embeds import create_truth_embed
from config import TRUTH_DEFAULT_INTERVAL


logger = get_logger()

# Tracking state
tracking_task = None
is_tracking = False
last_check_time = None
next_check_time = None
proxy_rotator = None

# Cache for tracking data to reduce DB calls
_cached_guild_accounts = {}  # Map guild_id -> accounts list
_cached_guild_accounts_timestamps = {}  # Map guild_id -> timestamp
_cached_guilds = []
_cached_guilds_timestamp = 0
_cached_channels = {}
_cached_channels_timestamp = {}
CACHE_TTL = 60  # 60 seconds cache TTL

# Efficient processed posts tracking with limited memory usage
processed_posts = {}  # guild_id -> set of post_ids
MAX_PROCESSED_CACHE = 500  # Maximum size of processed posts cache per guild

# Background Task Lock
_task_lock = asyncio.Lock()

async def init_proxy_rotator(countries=None, protocol="http"):
    """Initialize proxy rotator if needed"""
    global proxy_rotator
    try:
        if proxy_rotator is None:
            from service.proxy_handler import ProxyRotator
            proxy_rotator = ProxyRotator(
                countries=countries or ["US"],
                protocol=protocol,
                auto_rotate=True,
                max_proxies=20,
                debug=False
            )
            logger.info("Proxy rotator initialized for Truth Social tracking")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize proxy rotator: {e}")
        return False

async def start_tracking(bot):
    """Start the Truth Social tracking loop with auto-restart capability"""
    global tracking_task, is_tracking
    
    # Try to initialize proxy rotator
    await init_proxy_rotator()
    
    async with _task_lock:
        # Check if task is already running
        if tracking_task and not tracking_task.done():
            logger.info("Truth Social tracking already running")
            return True
        
        # Create and start the task
        tracking_task = bot.loop.create_task(tracking_loop(bot))
        is_tracking = True
        logger.info("Truth Social tracking started")
        return True

async def stop_tracking():
    """Stop the Truth Social tracking loop"""
    global tracking_task, is_tracking
    
    async with _task_lock:
        if tracking_task and not tracking_task.done():
            tracking_task.cancel()
            try:
                await tracking_task
            except asyncio.CancelledError:
                pass
            
        is_tracking = False
        logger.info("Truth Social tracking stopped")
        return True

async def get_cached_guild_accounts(guild_id: int) -> List[Dict]:
    """Get cached tracked accounts for a specific guild with automatic refresh when needed"""
    global _cached_guild_accounts, _cached_guild_accounts_timestamps
    
    current_time = time.time()
    if (guild_id not in _cached_guild_accounts_timestamps or 
            current_time - _cached_guild_accounts_timestamps.get(guild_id, 0) > CACHE_TTL):
        _cached_guild_accounts[guild_id] = await truth_db.get_guild_tracked_accounts(guild_id)
        _cached_guild_accounts_timestamps[guild_id] = current_time
    
    return _cached_guild_accounts.get(guild_id, [])

async def get_cached_guilds() -> List[Dict]:
    """Get cached enabled guilds with automatic refresh when needed"""
    global _cached_guilds, _cached_guilds_timestamp
    
    current_time = time.time()
    if current_time - _cached_guilds_timestamp > CACHE_TTL:
        _cached_guilds = await truth_db.get_all_enabled_guilds()
        _cached_guilds_timestamp = current_time
    
    return _cached_guilds

async def get_cached_channels(guild_id: int) -> List[int]:
    """Get cached channels for a guild with automatic refresh when needed"""
    global _cached_channels, _cached_channels_timestamp
    
    current_time = time.time()
    if (guild_id not in _cached_channels_timestamp or 
            current_time - _cached_channels_timestamp.get(guild_id, 0) > CACHE_TTL):
        _cached_channels[guild_id] = await truth_db.get_truth_channels(guild_id)
        _cached_channels_timestamp[guild_id] = current_time
    
    return _cached_channels.get(guild_id, [])

async def clear_cache_for_guild(guild_id: int):
    """Clear cache for a specific guild - useful after settings changes"""
    global _cached_guild_accounts_timestamps, _cached_channels_timestamp
    
    # Clear account cache
    if guild_id in _cached_guild_accounts_timestamps:
        del _cached_guild_accounts_timestamps[guild_id]
        
    # Clear channel cache
    if guild_id in _cached_channels_timestamp:
        del _cached_channels_timestamp[guild_id]
    
    # Force refresh of guild list
    global _cached_guilds_timestamp
    _cached_guilds_timestamp = 0
    
    logger.debug(f"Cache cleared for guild {guild_id}")

async def tracking_loop(bot):
    """Main tracking loop for Truth Social posts with restart capability"""
    global last_check_time, next_check_time, processed_posts
    
    try:
        # On startup, make sure accounts are authenticated
        if bot.services and bot.services.truthsocial:
            await bot.services.truthsocial.setup()
        
        while True:
            try:
                # Update timing info
                last_check_time = datetime.now()
                
                # Get all enabled guilds (from cache when possible)
                guilds = await get_cached_guilds()
                if not guilds:
                    logger.debug("No guilds with Truth Social tracking enabled")
                    await asyncio.sleep(30)
                    continue
                
                logger.info(f"Polling Truth Social for {len(guilds)} guilds at {last_check_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Set a fixed tracking limit per run to prevent API overload
                MAX_ACCOUNTS_PER_RUN = 25
                
                # Process all guilds concurrently for faster updates
                guild_tasks = []
                for guild_data in guilds:
                    task = process_guild(bot, guild_data, max_accounts=MAX_ACCOUNTS_PER_RUN)
                    guild_tasks.append(task)
                
                # Wait for all guild processing to complete
                await asyncio.gather(*guild_tasks, return_exceptions=True)
                
                # Clean up processed posts cache for each guild if it gets too large
                for guild_id, post_set in processed_posts.items():
                    if len(post_set) > MAX_PROCESSED_CACHE:
                        # Keep only the most recent half
                        processed_posts[guild_id] = set(list(post_set)[-MAX_PROCESSED_CACHE//2:])
                
                # Set next check time based on the smallest interval
                # This ensures we check frequently enough for all guilds
                
                next_check_time = datetime.now().timestamp() + TRUTH_DEFAULT_INTERVAL
                
                # Sleep until next check
                await asyncio.sleep(TRUTH_DEFAULT_INTERVAL)
                
            except asyncio.CancelledError:
                logger.info("Truth Social tracking task cancelled")
                raise
            except Exception as e:
                logger.error(f"Error in Truth Social tracking loop: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(10)  # Short sleep on error
                
    except asyncio.CancelledError:
        logger.info("Truth Social tracking loop cancelled")
    except Exception as e:
        logger.error(f"Fatal error in Truth Social tracking: {e}")
        # Try to restart the tracking task if it fails
        bot.loop.create_task(restart_tracking(bot))

async def restart_tracking(bot):
    """Try to restart the tracking task after a delay"""
    await asyncio.sleep(60)  # Wait a minute before trying to restart
    await start_tracking(bot)

async def process_guild(bot, guild_data: Dict, max_accounts: int = 25):
    """Process a single guild for Truth Social updates"""
    try:
        guild_id = guild_data.get('guild_id')
        
        # Get the guild object
        guild = bot.get_guild(guild_id)
        if not guild:
            logger.warning(f"Guild {guild_id} not found")
            return
        
        # Get channels for this guild (from cache when possible)
        channel_ids = await get_cached_channels(guild_id)
        if not channel_ids:
            logger.debug(f"No channels configured for guild {guild_id}")
            return
        
        # Get channel objects
        channels = []
        for channel_id in channel_ids:
            channel = guild.get_channel(channel_id)
            if channel:
                channels.append(channel)
        
        if not channels:
            logger.debug(f"No valid channels found for guild {guild_id}")
            return
        
        # Get accounts for this specific guild
        accounts = await get_cached_guild_accounts(guild_id)
        active_accounts = [a for a in accounts if a.get('last_post_id') != "DISABLED"]
        
        if not active_accounts:
            logger.debug(f"No active accounts to track for guild {guild_id}")
            return
            
        # Process accounts up to the maximum
        if len(active_accounts) > max_accounts:
            logger.info(f"Limiting to {max_accounts} accounts for guild {guild_id}")
            # Sort by last checked time to prioritize accounts that haven't been checked recently
            active_accounts.sort(key=lambda a: a.get('last_checked', datetime.min))
        
        # Process all accounts concurrently for faster updates
        account_tasks = []
        for account in active_accounts[:max_accounts]:
            task = process_account(bot, guild_id, account, channels)
            account_tasks.append(task)
        
        # Wait for all account processing to complete
        if account_tasks:
            await asyncio.gather(*account_tasks, return_exceptions=True)
            
    except Exception as e:
        logger.error(f"Error processing guild {guild_id}: {e}")

async def process_account(bot, guild_id: int, account: Dict, channels: List[discord.TextChannel]):
    """Process a single account for Truth Social updates for a specific guild"""
    global processed_posts, proxy_rotator
    
    try:
        handle = account.get('handle', '')
        last_post_id = account.get('last_post_id')
        
        if not handle or last_post_id == "DISABLED":
            return
        
        # Get proxy for request
        proxy = None
        if proxy_rotator:
            proxy = await proxy_rotator.get_proxy_for_request(force_new=True)
            if proxy:
                logger.debug(f"Using proxy {proxy} for account {handle}")
        
        # Get new posts
        new_posts = await bot.services.truthsocial.get_new_posts(handle, last_post_id, proxy=proxy)
        if not new_posts:
            return
            
        # Sort by ID (newest first)
        new_posts.sort(key=lambda p: p.get('id', ''), reverse=True)
        
        # Initialize guild's processed posts set if not exists
        if guild_id not in processed_posts:
            processed_posts[guild_id] = set()
        
        # Keep track of the newest post for updating the database
        newest_post_id = None
        
        # Process count
        posts_processed = 0
        
        # Special case: if last_post_id is "0" (first run), only post the most recent one
        if last_post_id == "0" and new_posts:
            newest = new_posts[0]
            newest_post_id = newest.get('id', '')
            
            # Skip if already processed
            if newest_post_id in processed_posts[guild_id]:
                return
                
            # Add to processed set
            processed_posts[guild_id].add(newest_post_id)
            
            # Create embed
            embed = create_truth_embed(newest)
            
            # Send to all channels for this guild
            for channel in channels:
                try:
                    await channel.send(embed=embed)
                    logger.debug(f"Sent initial post from @{handle} to channel {channel.id}")
                except Exception as e:
                    logger.error(f"Error sending post to channel {channel.id}: {e}")
                    
            # Update database with newest post ID
            await truth_db.update_last_post(guild_id, handle, newest_post_id)
            logger.info(f"Sent 1 initial post from @{handle} for guild {guild_id}")
            return
            
        # Post updates (oldest first to maintain chronology)
        for post in reversed(new_posts):
            if not post or 'id' not in post:
                continue
            
            # Skip already processed posts for this guild
            post_id = post.get('id', '')
            if post_id in processed_posts[guild_id]:
                continue
            
            # Add to processed set for this guild
            processed_posts[guild_id].add(post_id)
            
            # Create embed
            embed = create_truth_embed(post)
            
            # Send to all channels for this guild
            for channel in channels:
                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    logger.error(f"Error sending post to channel {channel.id}: {e}")
            
            # Update newest post ID
            if newest_post_id is None or post.get('id', '') > newest_post_id:
                newest_post_id = post.get('id', '')
                
            # Increment counter
            posts_processed += 1
        
        # Update last post ID in the database with newest post (guild-specific)
        if newest_post_id:
            await truth_db.update_last_post(guild_id, handle, newest_post_id)
            logger.info(f"Found {posts_processed} new post(s) from @{handle} for guild {guild_id}")
            
    except Exception as e:
        logger.error(f"Error processing account {account.get('handle', 'unknown')} for guild {guild_id}: {e}")
        logger.exception(e)

def get_tracking_status() -> Dict:
    """Get current tracking status"""
    return {
        'is_tracking': is_tracking,
        'last_check': last_check_time,
        'next_check': next_check_time,
        'account_count': sum(len(accounts) for accounts in _cached_guild_accounts.values()),
        'proxy_enabled': proxy_rotator is not None and proxy_rotator.enabled
    }