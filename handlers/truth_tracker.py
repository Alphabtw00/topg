# handlers/truth_tracker.py - ULTRA-OPTIMIZED tracking system
import asyncio
import discord
import time
import traceback
from datetime import datetime
from typing import Dict, Optional, Set, List, Any, Tuple
from utils.logger import get_logger
import repository.truth_repo as truth_db
from ui.embeds import create_truth_embed
from config import TRUTH_DEFAULT_INTERVAL, TRUTH_ACCOUNTS

logger = get_logger()

# Tracking state
tracking_task = None
is_tracking = False
last_check_time = None
next_check_time = None
proxy_rotator = None

# Ultra-optimized caching
_account_cache = {}  # account_id -> {handle, display_name}
_account_channels = {}  # account_id -> [(channel_id, guild_id), ...] - direct channel mapping
_last_post_ids = {}  # account_id -> last_post_id (global)

# Background Task Lock
_task_lock = asyncio.Lock()

async def initialize_and_start_truth_tracking(bot):
    """Initialize and start Truth Social tracking"""
    try:
        logger.info("Initializing Truth Social tracking...")
        
        # Initialize Truth Social tables
        await truth_db.setup_truth_tables()
        
        # Initialize proxy rotator
        await init_proxy_rotator()
        
        # Ultra-optimized cache loading
        await build_tracking_cache()
        
        # Get enabled guilds
        enabled_guilds = await truth_db.get_all_enabled_guilds()
        if enabled_guilds:
            logger.info(f"Found {len(enabled_guilds)} guilds with Truth Social tracking enabled")
            await start_tracking(bot)
        else:
            logger.info("No guilds with Truth Social tracking enabled")
            
        logger.info("Truth Social tracking initialization complete")
    except Exception as e:
        logger.error(f"Error initializing Truth Social tracking: {e}")


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


async def build_tracking_cache():
    """Build optimized tracking cache in a single operation"""
    global _account_cache, _account_channels, _last_post_ids
    
    try:
        # 1. Get all tracked accounts
        accounts = await truth_db.get_all_tracked_accounts()
        
        # 2. Get enabled guilds
        enabled_guilds = await truth_db.get_all_enabled_guilds()
        enabled_guild_ids = {g.get('guild_id') for g in enabled_guilds if g.get('guild_id')}
        
        # 3. Initialize new caches
        new_account_cache = {}
        new_account_channels = {}
        new_last_post_ids = {}
        
        # 4. Process each account
        for account in accounts:
            account_id = account.get('account_id')
            if not account_id:
                continue
                
            # Add account to cache
            new_account_cache[account_id] = {
                'handle': account.get('handle', ''),
                'display_name': account.get('display_name', '')
            }
            
            # Get channels for this account (direct mapping)
            channel_mappings = []
            
            # Get guilds tracking this account
            guilds = await truth_db.get_guilds_for_account(account_id)
            enabled_guilds_for_account = [g for g in guilds if g.get('guild_id') in enabled_guild_ids 
                                         and g.get('last_post_id') != "DISABLED"]
            
            # Find max last_post_id
            max_id = "0"
            
            # Process each guild
            for guild in enabled_guilds_for_account:
                guild_id = guild.get('guild_id')
                last_post_id = guild.get('last_post_id')
                
                # Update max last_post_id
                if last_post_id and last_post_id != "DISABLED" and last_post_id > max_id:
                    max_id = last_post_id
                
                # Get channels for this guild
                channel_ids = await truth_db.get_truth_channels(guild_id)
                
                # Add direct channel mappings with guild info
                for channel_id in channel_ids:
                    channel_mappings.append((channel_id, guild_id))
            
            # Only add account if it has channel mappings
            if channel_mappings:
                new_account_channels[account_id] = channel_mappings
                new_last_post_ids[account_id] = max_id
        
        # 5. Update global caches
        _account_cache = new_account_cache
        _account_channels = new_account_channels
        _last_post_ids = new_last_post_ids
        
        logger.info(f"Ultra-optimized cache built: {len(_account_cache)} accounts, "
                  f"{len(_account_channels)} accounts with channels, "
                  f"{sum(len(channels) for channels in _account_channels.values())} total channel mappings")
        
    except Exception as e:
        logger.error(f"Error building tracking cache: {e}")


async def clear_cache_for_guild(guild_id: int):
    """Clear cache for guild changes"""
    await build_tracking_cache()
    logger.debug(f"Tracking cache rebuilt for guild {guild_id}")


async def refresh_all_caches():
    """Compatibility method - use build_tracking_cache for full rebuild"""
    await build_tracking_cache()


async def tracking_loop(bot):
    """Main tracking loop with ultra-optimized two-stage pipeline"""
    global last_check_time, next_check_time
    
    try:
        # Ensure cache is loaded
        if not _account_cache or not _account_channels:
            await build_tracking_cache()
        
        while True:
            try:
                start_time = time.time()
                
                # Update timing info
                last_check_time = datetime.now()
                
                # Skip if no accounts to track
                if not _account_channels:
                    await asyncio.sleep(TRUTH_DEFAULT_INTERVAL)
                    continue
                
                logger.debug(f"Polling Truth Social for {len(_account_channels)} accounts at {last_check_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # STAGE 1: Ultra-fast concurrent polling
                poll_tasks = []
                for account_id in _account_channels:
                    last_id = _last_post_ids.get(account_id, "0")
                    task = poll_account(bot, account_id, last_id)
                    poll_tasks.append(task)
                
                # Execute all polls with concurrency control
                semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests
                
                async def poll_with_semaphore(task_coro):
                    async with semaphore:
                        return await task_coro
                
                poll_results = await asyncio.gather(*[poll_with_semaphore(task) for task in poll_tasks], 
                                                  return_exceptions=True)
                
                # STAGE 2: Ultra-fast concurrent broadcasting
                send_tasks = []
                for result in poll_results:
                    if isinstance(result, tuple) and len(result) == 3:
                        account_id, new_posts, new_last_id = result
                        
                        if new_posts:
                            # Create broadcast task
                            send_task = broadcast_posts(bot, account_id, new_posts, new_last_id)
                            send_tasks.append(send_task)
                            
                            # Update global last_post_id
                            _last_post_ids[account_id] = new_last_id
                
                # Execute all broadcasts concurrently
                if send_tasks:
                    await asyncio.gather(*send_tasks, return_exceptions=True)
                
                # Calculate precise sleep time
                elapsed = time.time() - start_time
                sleep_time = max(0.01, TRUTH_DEFAULT_INTERVAL - elapsed)
                next_check_time = datetime.now().timestamp() + sleep_time
                
                # Sleep until next check
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                logger.info("Truth Social tracking task cancelled")
                raise
            except Exception as e:
                logger.error(f"Error in Truth Social tracking loop: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(1)  # Short sleep on error
                
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


async def poll_account(bot, account_id, last_post_id):
    """Ultra-optimized polling - gets all new posts since last_post_id"""
    try:
        handle = _account_cache.get(account_id, {}).get('handle', '')
        
        # Skip if no handle
        if not handle:
            return None
        
        # Get proxy for request
        proxy = None
        if proxy_rotator:
            proxy = await proxy_rotator.get_proxy_for_request(force_new=False)
        
        # Get new posts (up to 5) to handle rapid posting
        new_posts = await bot.services.truthsocial.get_latest_posts(
            account_id=account_id,
            last_post_id=last_post_id,
            proxy=proxy
        )
        
        # If no new posts, return None
        if not new_posts:
            return None
        
        # Sort posts by ID (newest first)
        new_posts.sort(key=lambda p: p.get('id', ''), reverse=True)
        
        # Get newest post ID
        newest_post_id = new_posts[0].get('id')
        if not newest_post_id or newest_post_id <= last_post_id:
            return None
        
        # Return all new posts and newest ID
        return (account_id, new_posts, newest_post_id)
        
    except Exception as e:
        logger.error(f"Error polling account {account_id}: {e}")
        return None


async def broadcast_posts(bot, account_id, posts, new_last_id):
    """Ultra-fast broadcasting to all channels with guild tracking"""
    try:
        handle = _account_cache.get(account_id, {}).get('handle', '')
        
        # Get all channels for this account
        channel_mappings = _account_channels.get(account_id, [])
        
        # Group by guild for tracking and efficient updates
        guild_channels = {}
        for channel_id, guild_id in channel_mappings:
            if guild_id not in guild_channels:
                guild_channels[guild_id] = []
            
            # Get channel object
            channel = bot.get_channel(channel_id)
            if channel:
                guild_channels[guild_id].append(channel)
        
        # Track how many posts we've sent
        total_sent = 0
        
        # Process all posts (oldest first to maintain chronology)
        for post in reversed(posts):
            # Create embed once
            embed = create_truth_embed(post)
            image_url = embed.image.url if embed.image else "No image set"
            print(f"Post ID {post.get('id')} image URL: {image_url}")
            
            # Send to all channels concurrently
            channel_tasks = []
            for guild_id, channels in guild_channels.items():
                for channel in channels:
                    task = send_to_channel(channel, embed)
                    channel_tasks.append(task)
            
            # Wait for all sends to complete
            if channel_tasks:
                results = await asyncio.gather(*channel_tasks, return_exceptions=True)
                successful_sends = sum(1 for r in results if r is True)
                if successful_sends > 0:
                    total_sent += 1
        
        # Update last_post_id in database concurrently for all guilds
        update_tasks = []
        for guild_id in guild_channels:
            if guild_channels[guild_id]:  # Only update if we have channels
                task = truth_db.update_last_post(guild_id, account_id, new_last_id)
                update_tasks.append(task)
        
        # Execute all database updates concurrently
        if update_tasks:
            await asyncio.gather(*update_tasks, return_exceptions=True)
        
        # Log stats
        guilds_count = len(guild_channels)
        channels_count = sum(len(channels) for channels in guild_channels.values())
        if total_sent > 0:
            logger.info(f"Broadcast {total_sent} posts from @{handle} to {guilds_count} guilds ({channels_count} channels)")
            
        return total_sent
    
    except Exception as e:
        logger.error(f"Error broadcasting posts for account {account_id}: {e}")
        return 0


async def send_to_channel(channel, embed):
    """Send a message to a channel with error handling"""
    try:
        await channel.send(embed=embed)
        return True
    except Exception as e:
        logger.error(f"Error sending post to channel {channel.id}: {e}")
        return False


def get_tracking_status() -> Dict:
    """Get current tracking status"""
    return {
        'is_tracking': is_tracking,
        'last_check': last_check_time,
        'next_check': next_check_time,
        'account_count': len(_account_cache),
        'active_accounts': len(_account_channels),
        'channel_mappings': sum(len(channels) for channels in _account_channels.values()),
        'proxy_enabled': proxy_rotator is not None and proxy_rotator.enabled
    }