import pytz
import re
import time
import random
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from utils.logger import get_logger
from truthbrush.api import Api  # Direct import from the library
from config import (
    TRUTH_ACCOUNTS, TRUMP_TIMEZONE, TRUMP_ACTIVE_START_HOUR,
    TRUMP_ACTIVE_END_HOUR, TRUTH_DEFAULT_INTERVAL, TRUTH_NIGHT_INTERVAL,
    DEFAULT_AVATAR
)

logger = get_logger()

# Track current account index for rotation
current_account_index = 0
account_apis = {}  # Cache for API instances

# Caching for frequent checks
_cached_active_hours = False
_cached_active_hours_timestamp = 0
_cached_interval = TRUTH_DEFAULT_INTERVAL
_cached_interval_timestamp = 0
CACHE_TTL = 60  # 60 seconds cache TTL

# Account rate limiting protection
account_last_used = {}
MIN_ACCOUNT_USAGE_INTERVAL = 2  # Minimum seconds between using the same account

def get_next_account_api() -> Api:
    """Get the next account API instance with rotation"""
    global current_account_index, account_last_used
    
    if not TRUTH_ACCOUNTS:
        raise ValueError("No Truth Social accounts configured")
    
    # Try to find an account that hasn't been used recently
    current_time = time.time()
    best_account_idx = current_account_index
    best_wait_time = float('inf')
    
    # Look through all accounts to find the one with the shortest wait time
    for i in range(len(TRUTH_ACCOUNTS)):
        idx = (current_account_index + i) % len(TRUTH_ACCOUNTS)
        account = TRUTH_ACCOUNTS[idx]
        account_key = f"{account['username']}:{account['password']}"
        
        last_used = account_last_used.get(account_key, 0)
        wait_time = last_used + MIN_ACCOUNT_USAGE_INTERVAL - current_time
        
        if wait_time <= 0:
            # This account is ready to use now
            best_account_idx = idx
            break
        
        if wait_time < best_wait_time:
            best_wait_time = wait_time
            best_account_idx = idx
    
    # If we need to wait, do a small sleep
    if best_wait_time > 0:
        time.sleep(min(best_wait_time, 0.5))  # Cap wait time to 0.5s max
    
    # Update the current index for next time
    current_account_index = (best_account_idx + 1) % len(TRUTH_ACCOUNTS)
    
    # Get the selected account
    account = TRUTH_ACCOUNTS[best_account_idx]
    account_key = f"{account['username']}:{account['password']}"
    
    # Update last used time
    account_last_used[account_key] = time.time()
    
    # Check if we already have an API instance for this account
    if account_key not in account_apis:
        # Create new API instance
        account_apis[account_key] = Api(
            username=account['username'],
            password=account['password']
        )
    
    return account_apis[account_key]

def get_optimized_interval() -> int:
    """Get optimized interval based on Trump's timezone and active hours"""
    global _cached_interval, _cached_interval_timestamp
    
    # Use cached value if recent enough
    current_time = time.time()
    if current_time - _cached_interval_timestamp < CACHE_TTL:
        return _cached_interval
    
    # Get current time in Trump's timezone
    tz = pytz.timezone(TRUMP_TIMEZONE)
    now = datetime.now(tz)
    current_hour = now.hour
    
    # Add small random jitter to prevent synchronization
    jitter = random.uniform(0, 1)
    
    # Check if within active hours
    if TRUMP_ACTIVE_START_HOUR <= current_hour < TRUMP_ACTIVE_END_HOUR:
        interval = TRUTH_DEFAULT_INTERVAL + jitter
    else:
        interval = TRUTH_NIGHT_INTERVAL + jitter
    
    # Update cache
    _cached_interval = int(interval)
    _cached_interval_timestamp = current_time
    
    return _cached_interval

def is_active_hours() -> bool:
    """Check if current time is within Trump's active hours"""
    global _cached_active_hours, _cached_active_hours_timestamp
    
    # Use cached value if recent enough
    current_time = time.time()
    if current_time - _cached_active_hours_timestamp < CACHE_TTL:
        return _cached_active_hours
    
    # Get current time in Trump's timezone
    tz = pytz.timezone(TRUMP_TIMEZONE)
    now = datetime.now(tz)
    current_hour = now.hour
    
    # Update cache
    _cached_active_hours = TRUMP_ACTIVE_START_HOUR <= current_hour < TRUMP_ACTIVE_END_HOUR
    _cached_active_hours_timestamp = current_time
    
    return _cached_active_hours

async def get_user_info(handle: str) -> Optional[Dict]:
    """Get user information for a Truth Social account using API directly"""
    try:
        api = get_next_account_api()
        
        # Get user metadata
        user_info = api.lookup(user_handle=handle)
        if user_info:
            return user_info
        return None
    except Exception as e:
        logger.error(f"Error getting user info for {handle}: {e}")
        return None

async def get_latest_post(handle: str) -> Optional[Dict]:
    """Get the most recent post for a Truth Social account using API directly"""
    try:
        api = get_next_account_api()
        
        # Get posts
        posts = list(api.pull_statuses(username=handle, replies=False))
        # Take just the first post (most recent) if any exist
        if posts:
            return posts[0]
        return None
    except Exception as e:
        logger.error(f"Error getting latest post from {handle}: {e}")
        return None

async def get_new_posts(handle: str, last_post_id: Optional[str] = None) -> List[Dict]:
    """Get new posts since the last checked post ID using API directly"""
    try:
        api = get_next_account_api()
        
        if not last_post_id or last_post_id == "DISABLED":
            # If no last post ID, just return the latest post
            posts = list(api.pull_statuses(username=handle, replies=False))
            # Return just the first post (most recent)
            return posts[:1] if posts else []
        
        # Use since_id parameter to only get newer posts
        posts = list(api.pull_statuses(
            username=handle,
            replies=False,
            since_id=last_post_id
        ))
        
        return posts
    except Exception as e:
        logger.error(f"Error getting new posts from {handle}: {e}")
        return []

def extract_text_content(post: Dict) -> str:
    """Extract clean text content from a Truth Social post"""
    if not post or 'content' not in post:
        return ""
    
    # Get the content and strip HTML tags
    content = post.get('content', '')
    content = re.sub(r'<[^>]+>', '', content)
    
    return content.strip()

def get_post_url(handle: str, post_id: str) -> str:
    """Generate a URL to a Truth Social post"""
    handle = handle.strip().lstrip('@')
    return f"https://truthsocial.com/@{handle}/posts/{post_id}"

def get_profile_info(post: Dict) -> Tuple[str, str, str]:
    """Extract profile information from a post"""
    account = post.get('account', {})
    handle = account.get('username', '')
    name = account.get('display_name', handle)
    avatar = account.get('avatar', '') or DEFAULT_AVATAR 
    
    return handle, name, avatar