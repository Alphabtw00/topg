import asyncio
import discord
import traceback
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, List, Tuple
from utils.logger import get_logger
import repository.truth_repo as truth_db
import service.truth_service as truth_service
from ui.embeds import create_truth_embed
from config import TRUTH_MIN_INTERVAL, TRUTH_DEFAULT_INTERVAL, TRUTH_NIGHT_INTERVAL

logger = get_logger()

# Track running task
tracking_task = None
is_tracking = False
last_check_time = None
next_check_time = None

# Cache for tracking data to reduce DB calls
_cached_guild_accounts = {}  # Map guild_id -> accounts list
_cached_guild_accounts_timestamps = {}  # Map guild_id -> timestamp
_cached_guilds = []
_cached_guilds_timestamp = 0
_cached_channels = {}
_cached_channels_timestamp = {}
CACHE_TTL = 60  # 60 seconds cache TTL

# Optimization: Track which posts we've already processed
# Now uses guild_id+post_id as key to prevent cross-server duplicates
processed_posts = {}  # guild_id -> set of post_ids
MAX_PROCESSED_CACHE = 500  # Maximum size of processed posts cache per guild

# Background Task Lock
_task_lock = asyncio.Lock()

async def start_tracking(bot):
    """Start the Truth Social tracking loop"""
    global tracking_task, is_tracking
    
    async with _task_lock:
        if tracking_task and not tracking_task.done():
            logger.info("Truth Social tracking already running")
            return True
        
        # Create and start the task
        tracking_task = asyncio.create_task(tracking_loop(bot))
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

async def tracking_loop(bot):
    """Main tracking loop for Truth Social posts"""
    global last_check_time, next_check_time, processed_posts
    
    try:
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
                
                # Get dynamically optimized interval based on Trump's timezone
                dynamic_interval = truth_service.get_optimized_interval()
                is_active = truth_service.is_active_hours()
                
                logger.info(f"Polling Truth Social at {last_check_time.strftime('%Y-%m-%d %H:%M:%S')} | " 
                           f"Interval: {dynamic_interval}s | Active hours: {is_active}")
                # Process each guild independently
                tasks = []
                for guild_data in guilds:
                    tasks.append(process_guild(bot, guild_data, is_active))
                
                # Wait for all guild processing to complete
                if tasks:
                    await asyncio.gather(*tasks)
                
                # Clean up processed posts cache for each guild if it gets too large
                for guild_id, post_set in processed_posts.items():
                    if len(post_set) > MAX_PROCESSED_CACHE:
                        # Keep only the most recent half
                        processed_posts[guild_id] = set(list(post_set)[-MAX_PROCESSED_CACHE//2:])
                
                # Update next check time - use the dynamic interval
                current_check_interval = dynamic_interval
                next_check_time = datetime.now() + timedelta(seconds=current_check_interval)
                
                # Sleep until next check
                await asyncio.sleep(current_check_interval)
                
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
        logger.error(traceback.format_exc())

async def process_guild(bot, guild_data: Dict, is_active: bool):
    """Process a single guild for Truth Social updates"""
    try:
        guild_id = guild_data.get('guild_id')
        user_interval = guild_data.get('check_interval', TRUTH_DEFAULT_INTERVAL)
        
        # Use the appropriate interval based on time of day
        # When active (daytime), use user-configured interval
        # When inactive (nighttime), use the night interval
        check_interval = user_interval if is_active else TRUTH_NIGHT_INTERVAL
        
        # Ensure it's within bounds
        check_interval = max(TRUTH_MIN_INTERVAL, check_interval)
        
        # Get the guild object
        guild = bot.get_guild(guild_id)
        if not guild:
            return
        
        # Get channels for this guild (from cache when possible)
        channel_ids = await get_cached_channels(guild_id)
        if not channel_ids:
            return
        
        # Get channel objects
        channels = []
        for channel_id in channel_ids:
            channel = guild.get_channel(channel_id)
            if channel:
                channels.append(channel)
        
        if not channels:
            return
        
        # Get accounts for this specific guild
        accounts = await get_cached_guild_accounts(guild_id)
        active_accounts = [a for a in accounts if a.get('last_post_id') != "DISABLED"]
        
        if not active_accounts:
            return
        
        # Initialize guild's processed posts set if not exists
        if guild_id not in processed_posts:
            processed_posts[guild_id] = set()
        
        # Process accounts in parallel for better performance
        account_tasks = []
        for account in active_accounts:
            account_tasks.append(process_account(guild_id, account, channels))
        
        # Wait for all account processing to complete
        if account_tasks:
            await asyncio.gather(*account_tasks)
            
    except Exception as e:
        logger.error(f"Error processing guild {guild_id}: {e}")

async def process_account(guild_id: int, account: Dict, channels: List[discord.TextChannel]):
    """Process a single account for Truth Social updates for a specific guild"""
    global processed_posts
    
    try:
        handle = account.get('handle', '')
        last_post_id = account.get('last_post_id')
        
        if not handle or last_post_id == "DISABLED":
            return
        
        # Get new posts
        new_posts = await truth_service.get_new_posts(handle, last_post_id)
        if not new_posts:
            return
            
        # Sort by ID (newest first)
        new_posts.sort(key=lambda p: p.get('id', ''), reverse=True)
        
        # Keep track of the newest post for updating the database
        newest_post_id = None
        
        # Post updates (oldest first)
        for post in reversed(new_posts):
            if not post or 'id' not in post:
                continue
            
            # Skip already processed posts for this guild
            post_id = post.get('id', '')
            if post_id in processed_posts.get(guild_id, set()):
                continue
            
            # Add to processed set for this guild
            processed_posts.setdefault(guild_id, set()).add(post_id)
            
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
        
        # Update last post ID in the database with newest post (guild-specific)
        if newest_post_id:
            await truth_db.update_last_post(guild_id, handle, newest_post_id)
            logger.info(f"Found {len(new_posts)} new post(s) from @{handle} for guild {guild_id}")
            
    except Exception as e:
        logger.error(f"Error processing account {account.get('handle', 'unknown')} for guild {guild_id}: {e}")

def get_tracking_status() -> Dict:
    """Get current tracking status"""
    return {
        'is_tracking': is_tracking,
        'last_check': last_check_time,
        'next_check': next_check_time,
        'account_count': len(truth_service.TRUTH_ACCOUNTS),
        'dynamic_interval': truth_service.get_optimized_interval()
    }