"""
Server settings manager for persistent settings storage with exclusion support
"""
import json
from cachetools import TTLCache
from utils.logger import get_logger
from service.mysql_service import execute_query, fetch_one, fetch_all
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

# Table definitions for setup
TABLES = [
    """
    CREATE TABLE IF NOT EXISTS server_settings (
        guild_id BIGINT NOT NULL PRIMARY KEY,
        server_wide BOOLEAN NOT NULL DEFAULT TRUE,
        settings JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS channel_settings (
        channel_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        excluded BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (channel_id),
        INDEX idx_guild (guild_id)
    ) ENGINE=InnoDB
    """
]
# Server-wide settings (default)
DEFAULT_SETTINGS = {
    "server_wide": True,
    "settings": {}
}

async def setup_settings_tables():
    """
    Set up the database tables for settings
    """
    for table_query in TABLES:
        try:
            await execute_query(table_query)
        except Exception as e:
            logger.error(f"Error creating settings table: {e}")
            return False
    
    # Check if we need to add the excluded column to existing installations
    try:
        await execute_query("""
            SELECT 
                COUNT(*) 
            FROM 
                INFORMATION_SCHEMA.COLUMNS 
            WHERE 
                TABLE_NAME = 'channel_settings' AND 
                COLUMN_NAME = 'excluded'
        """)
        
        # If excluded column doesn't exist, add it
        results = await fetch_one("SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'channel_settings' AND COLUMN_NAME = 'excluded'")
        if results and results[0] == 0:
            await execute_query("ALTER TABLE channel_settings ADD COLUMN excluded BOOLEAN NOT NULL DEFAULT FALSE")
            logger.info("Added 'excluded' column to channel_settings table")
    except Exception as e:
        logger.warning(f"Error checking for excluded column: {e}")
    
    return True

async def get_server_settings(guild_id):
    """
    Get settings for a specific guild with caching
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        dict: Guild settings
    """
    # Check cache first
    cache_key = f"guild_{guild_id}"
    if cache_key in SERVER_SETTINGS_CACHE:
        return SERVER_SETTINGS_CACHE[cache_key]
    
    query = "SELECT server_wide, settings FROM server_settings WHERE guild_id = %s"
    params = (guild_id,)
    
    try:
        result = await fetch_one(query, params)
        
        if result:
            settings = {
                "server_wide": bool(result[0]),
                "settings": json.loads(result[1]) if result[1] else {}
            }
            # Cache the result
            SERVER_SETTINGS_CACHE[cache_key] = settings
            return settings
        else:
            # Insert default settings if not found
            await execute_query(
                "INSERT INTO server_settings (guild_id, server_wide, settings) VALUES (%s, %s, %s)", 
                (guild_id, True, json.dumps({}))
            )
            # Cache the default settings
            SERVER_SETTINGS_CACHE[cache_key] = DEFAULT_SETTINGS
            return DEFAULT_SETTINGS
    except Exception as e:
        logger.error(f"Error getting server settings for {guild_id}: {e}")
        return DEFAULT_SETTINGS

async def update_server_settings(guild_id, settings_dict):
    """
    Update settings for a specific guild
    
    Args:
        guild_id: Discord guild ID
        settings_dict: Settings dictionary to update
        
    Returns:
        bool: Success status
    """
    server_wide = settings_dict.get("server_wide", True)
    settings_json = json.dumps(settings_dict.get("settings", {}))
    
    query = """
    INSERT INTO server_settings (guild_id, server_wide, settings) 
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE 
        server_wide = VALUES(server_wide),
        settings = VALUES(settings)
    """
    params = (guild_id, server_wide, settings_json)
    
    try:
        await execute_query(query, params)
        # Update cache
        cache_key = f"guild_{guild_id}"
        SERVER_SETTINGS_CACHE[cache_key] = settings_dict
        # Clear channel cache for this guild to force refresh
        for key in list(CHANNEL_SETTINGS_CACHE.keys()):
            if f"_guild_{guild_id}_" in key:
                CHANNEL_SETTINGS_CACHE.pop(key, None)
        return True
    except Exception as e:
        logger.error(f"Error updating server settings for {guild_id}: {e}")
        return False

async def enable_server_wide(guild_id):
    """
    Enable server-wide mode for a guild
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        bool: Success status
    """
    settings = await get_server_settings(guild_id)
    
    if settings.get("server_wide", False):
        # Already in server-wide mode
        return True
    
    settings["server_wide"] = True
    return await update_server_settings(guild_id, settings)

async def disable_server_wide(guild_id):
    """
    Disable server-wide mode for a guild
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        bool: Success status
    """
    settings = await get_server_settings(guild_id)
    
    if not settings.get("server_wide", True):
        # Already in channel-specific mode
        return True
    
    settings["server_wide"] = False
    return await update_server_settings(guild_id, settings)

async def add_channel(guild_id, channel_id):
    """
    Add a channel to the enabled list (for channel-specific mode)
    
    Args:
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        
    Returns:
        bool: Success status (True if added, False if already present)
    """
    # Check if channel already exists
    query = "SELECT enabled, excluded FROM channel_settings WHERE channel_id = %s"
    params = (channel_id,)
    
    try:
        result = await fetch_one(query, params)
        
        if result:
            # If already enabled and not excluded, nothing to do
            if result[0] and not result[1]:
                return False
                
            # Update existing record - enable and remove exclusion
            update_query = "UPDATE channel_settings SET enabled = TRUE, excluded = FALSE WHERE channel_id = %s"
            await execute_query(update_query, params)
            
            # Update cache
            cache_key = f"channel_{channel_id}_guild_{guild_id}"
            CHANNEL_SETTINGS_CACHE[cache_key] = True
            return True
        else:
            # Insert new record
            insert_query = "INSERT INTO channel_settings (channel_id, guild_id, enabled, excluded) VALUES (%s, %s, TRUE, FALSE)"
            insert_params = (channel_id, guild_id)
            await execute_query(insert_query, insert_params)
            
            # Update cache
            cache_key = f"channel_{channel_id}_guild_{guild_id}"
            CHANNEL_SETTINGS_CACHE[cache_key] = True
            return True
    except Exception as e:
        logger.error(f"Error adding channel {channel_id} for guild {guild_id}: {e}")
        return False

async def remove_channel(guild_id, channel_id):
    """
    Remove a channel from the enabled list (for channel-specific mode)
    
    Args:
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        
    Returns:
        bool: Success status (True if removed, False if not present)
    """
    # Check if channel exists
    query = "SELECT enabled FROM channel_settings WHERE channel_id = %s AND guild_id = %s"
    params = (channel_id, guild_id)
    
    try:
        result = await fetch_one(query, params)
        
        if result:
            if not result[0]:
                # Channel already disabled
                return False
            else:
                # Update existing record to disabled
                update_query = "UPDATE channel_settings SET enabled = FALSE WHERE channel_id = %s"
                update_params = (channel_id,)
                await execute_query(update_query, update_params)
                
                # Update cache
                cache_key = f"channel_{channel_id}_guild_{guild_id}"
                CHANNEL_SETTINGS_CACHE[cache_key] = False
                return True
        else:
            # Not found - nothing to remove
            return False
    except Exception as e:
        logger.error(f"Error removing channel {channel_id} for guild {guild_id}: {e}")
        return False

async def exclude_channel(guild_id, channel_id):
    """
    Add a channel to the exclusion list (for server-wide mode)
    
    Args:
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        
    Returns:
        bool: Success status (True if excluded, False if already excluded)
    """
    # Check if channel already exists
    query = "SELECT excluded FROM channel_settings WHERE channel_id = %s"
    params = (channel_id,)
    
    try:
        result = await fetch_one(query, params)
        
        if result:
            if result[0]:
                # Already excluded
                return False
            else:
                # Update to exclude
                update_query = "UPDATE channel_settings SET excluded = TRUE WHERE channel_id = %s"
                await execute_query(update_query, params)
        else:
            # Insert new excluded record
            insert_query = "INSERT INTO channel_settings (channel_id, guild_id, enabled, excluded) VALUES (%s, %s, FALSE, TRUE)"
            insert_params = (channel_id, guild_id)
            await execute_query(insert_query, insert_params)
        
        # Update cache
        cache_key = f"channel_{channel_id}_guild_{guild_id}"
        CHANNEL_SETTINGS_CACHE[cache_key] = False  # Don't process this channel
        return True
    except Exception as e:
        logger.error(f"Error excluding channel {channel_id} for guild {guild_id}: {e}")
        return False

async def include_channel(guild_id, channel_id):
    """
    Remove a channel from the exclusion list (for server-wide mode)
    
    Args:
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        
    Returns:
        bool: Success status (True if included, False if not excluded)
    """
    # Check if channel exists in exclusion list
    query = "SELECT excluded FROM channel_settings WHERE channel_id = %s AND guild_id = %s"
    params = (channel_id, guild_id)
    
    try:
        result = await fetch_one(query, params)
        
        if result:
            if not result[0]:
                # Not excluded
                return False
            else:
                # Remove exclusion
                update_query = "UPDATE channel_settings SET excluded = FALSE WHERE channel_id = %s"
                update_params = (channel_id,)
                await execute_query(update_query, update_params)
                
                # Update cache
                cache_key = f"channel_{channel_id}_guild_{guild_id}"
                CHANNEL_SETTINGS_CACHE[cache_key] = True
                return True
        else:
            # Not found - nothing to include
            return False
    except Exception as e:
        logger.error(f"Error including channel {channel_id} for guild {guild_id}: {e}")
        return False

async def get_channels_list(guild_id):
    """
    Get list of enabled channels for a guild (for channel-specific mode)
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        list: List of enabled channel IDs
    """
    query = "SELECT channel_id FROM channel_settings WHERE guild_id = %s AND enabled = TRUE"
    params = (guild_id,)
    
    try:
        results = await fetch_all(query, params)
        return [int(row[0]) for row in results] if results else []
    except Exception as e:
        logger.error(f"Error getting channels list for guild {guild_id}: {e}")
        return []

async def get_excluded_channels(guild_id):
    """
    Get list of excluded channels for a guild (for server-wide mode)
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        list: List of excluded channel IDs
    """
    query = "SELECT channel_id FROM channel_settings WHERE guild_id = %s AND excluded = TRUE"
    params = (guild_id,)
    
    try:
        results = await fetch_all(query, params)
        return [int(row[0]) for row in results] if results else []
    except Exception as e:
        logger.error(f"Error getting excluded channels for guild {guild_id}: {e}")
        return []

async def should_process_channel(guild_id, channel_id):
    """
    Check if a channel should be processed based on settings
    
    Args:
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        
    Returns:
        bool: Whether to process messages in this channel
    """
    # Check cache first
    cache_key = f"channel_{channel_id}_guild_{guild_id}"
    if cache_key in CHANNEL_SETTINGS_CACHE:
        return CHANNEL_SETTINGS_CACHE[cache_key]
    
    try:
        settings = await get_server_settings(guild_id)
        
        # In server-wide mode, we process all channels EXCEPT excluded ones
        if settings.get("server_wide", True):
            # Check for exclusion
            query = "SELECT 1 FROM channel_settings WHERE channel_id = %s AND guild_id = %s AND excluded = TRUE"
            params = (channel_id, guild_id)
            
            result = await fetch_one(query, params)
            
            # If result exists, channel is excluded, so return False
            # If no result, channel is not excluded, so return True
            should_process = not bool(result)
            
            # Cache the result
            CHANNEL_SETTINGS_CACHE[cache_key] = should_process
            return should_process
        
        # In channel-specific mode, we only process explicitly enabled channels
        else:
            query = "SELECT 1 FROM channel_settings WHERE channel_id = %s AND guild_id = %s AND enabled = TRUE"
            params = (channel_id, guild_id)
            
            result = await fetch_one(query, params)
            enabled = bool(result)
            
            # Cache the result
            CHANNEL_SETTINGS_CACHE[cache_key] = enabled
            return enabled
    except Exception as e:
        logger.error(f"Error checking channel processing for {channel_id} in {guild_id}: {e}")
        # Default to processing in case of error
        return True

def clear_settings_cache():
    """Clear all settings caches"""
    SERVER_SETTINGS_CACHE.clear()
    CHANNEL_SETTINGS_CACHE.clear()