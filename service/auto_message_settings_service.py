"""
Server settings service for persistent settings storage with caching
"""
from cachetools import TTLCache
from utils.logger import get_logger
import repository.auto_messaging_settings_repo as settings_db
from config import SERVER_SETTINGS_CACHE_SIZE, SERVER_SETTINGS_CACHE_TTL, CHANNEL_SETTINGS_CACHE_SIZE, CHANNEL_SETTINGS_CACHE_TTL

logger = get_logger()

# Cache for server settings to reduce database queries
SERVER_SETTINGS_CACHE = TTLCache(
    maxsize=SERVER_SETTINGS_CACHE_SIZE,
    ttl=SERVER_SETTINGS_CACHE_TTL
)
CHANNEL_SETTINGS_CACHE = TTLCache(
    maxsize=CHANNEL_SETTINGS_CACHE_SIZE,
    ttl=CHANNEL_SETTINGS_CACHE_TTL
)

async def setup_settings_tables():
    """Set up the database tables for settings"""
    return await settings_db.setup_settings_tables()

async def get_server_settings(guild_id):
    """Get settings for a specific guild with caching"""
    cache_key = f"guild_{guild_id}"
    if cache_key in SERVER_SETTINGS_CACHE:
        return SERVER_SETTINGS_CACHE[cache_key]
    
    settings = await settings_db.get_server_settings(guild_id)
    SERVER_SETTINGS_CACHE[cache_key] = settings
    return settings

async def update_server_settings(guild_id, settings_dict):
    """Update settings for a specific guild"""
    result = await settings_db.update_server_settings(guild_id, settings_dict)
    if result:
        cache_key = f"guild_{guild_id}"
        SERVER_SETTINGS_CACHE[cache_key] = settings_dict
        for key in list(CHANNEL_SETTINGS_CACHE.keys()):
            if f"_guild_{guild_id}_" in key:
                CHANNEL_SETTINGS_CACHE.pop(key, None)
    return result

async def enable_server_wide(guild_id):
    """Enable server-wide mode for a guild"""
    result = await settings_db.enable_server_wide(guild_id)
    if result:
        cache_key = f"guild_{guild_id}"
        SERVER_SETTINGS_CACHE.pop(cache_key, None)
    return result

async def disable_server_wide(guild_id):
    """Disable server-wide mode for a guild"""
    result = await settings_db.disable_server_wide(guild_id)
    if result:
        cache_key = f"guild_{guild_id}"
        SERVER_SETTINGS_CACHE.pop(cache_key, None)
    return result

async def add_channel(guild_id, channel_id):
    """Add a channel to the enabled list (for channel-specific mode)"""
    result = await settings_db.add_channel(guild_id, channel_id)
    if result:
        cache_key = f"channel_{channel_id}_guild_{guild_id}"
        CHANNEL_SETTINGS_CACHE[cache_key] = True
    return result

async def remove_channel(guild_id, channel_id):
    """Remove a channel from the enabled list (for channel-specific mode)"""
    result = await settings_db.remove_channel(guild_id, channel_id)
    if result:
        cache_key = f"channel_{channel_id}_guild_{guild_id}"
        CHANNEL_SETTINGS_CACHE[cache_key] = False
    return result

async def exclude_channel(guild_id, channel_id):
    """Add a channel to the exclusion list (for server-wide mode)"""
    result = await settings_db.exclude_channel(guild_id, channel_id)
    if result:
        cache_key = f"channel_{channel_id}_guild_{guild_id}"
        CHANNEL_SETTINGS_CACHE[cache_key] = False
    return result

async def include_channel(guild_id, channel_id):
    """Remove a channel from the exclusion list (for server-wide mode)"""
    result = await settings_db.include_channel(guild_id, channel_id)
    if result:
        cache_key = f"channel_{channel_id}_guild_{guild_id}"
        CHANNEL_SETTINGS_CACHE[cache_key] = True
    return result

async def get_channels_list(guild_id):
    """Get list of enabled channels for a guild (for channel-specific mode)"""
    return await settings_db.get_channels_list(guild_id)

async def get_excluded_channels(guild_id):
    """Get list of excluded channels for a guild (for server-wide mode)"""
    return await settings_db.get_excluded_channels(guild_id)

async def should_process_channel(guild_id, channel_id):
    """Check if a channel should be processed based on settings"""
    cache_key = f"channel_{channel_id}_guild_{guild_id}"
    if cache_key in CHANNEL_SETTINGS_CACHE:
        return CHANNEL_SETTINGS_CACHE[cache_key]
    
    should_process = await settings_db.should_process_channel(guild_id, channel_id)
    CHANNEL_SETTINGS_CACHE[cache_key] = should_process
    return should_process

def clear_settings_cache():
    """Clear all settings caches"""
    SERVER_SETTINGS_CACHE.clear()
    CHANNEL_SETTINGS_CACHE.clear()