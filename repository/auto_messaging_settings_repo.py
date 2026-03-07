"""
Database operations for auto-message settings
"""
import json
from typing import Dict, List
from service.mysql_service import execute_query, fetch_one, fetch_all
from utils.logger import get_logger

logger = get_logger()

# Table definitions
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

async def setup_settings_tables():
    """Set up the database tables for settings"""
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

async def get_server_settings(guild_id: int) -> Dict:
    """Get settings for a specific guild"""
    query = "SELECT server_wide, settings FROM server_settings WHERE guild_id = %s"
    params = (guild_id,)
    
    try:
        result = await fetch_one(query, params)
        
        if result:
            return {
                "server_wide": bool(result[0]),
                "settings": json.loads(result[1]) if result[1] else {}
            }
        else:
            # Insert default settings if not found
            await execute_query(
                "INSERT INTO server_settings (guild_id, server_wide, settings) VALUES (%s, %s, %s)", 
                (guild_id, True, json.dumps({}))
            )
            return {"server_wide": True, "settings": {}}
    except Exception as e:
        logger.error(f"Error getting server settings for {guild_id}: {e}")
        return {"server_wide": True, "settings": {}}

async def update_server_settings(guild_id: int, settings_dict: Dict) -> bool:
    """Update settings for a specific guild"""
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
        return True
    except Exception as e:
        logger.error(f"Error updating server settings for {guild_id}: {e}")
        return False

async def enable_server_wide(guild_id: int) -> bool:
    """Enable server-wide mode for a guild"""
    settings = await get_server_settings(guild_id)
    
    if settings.get("server_wide", False):
        return True
    
    settings["server_wide"] = True
    return await update_server_settings(guild_id, settings)

async def disable_server_wide(guild_id: int) -> bool:
    """Disable server-wide mode for a guild"""
    settings = await get_server_settings(guild_id)
    
    if not settings.get("server_wide", True):
        return True
    
    settings["server_wide"] = False
    return await update_server_settings(guild_id, settings)

async def add_channel(guild_id: int, channel_id: int) -> bool:
    """Add a channel to the enabled list (for channel-specific mode)"""
    query = "SELECT enabled, excluded FROM channel_settings WHERE channel_id = %s"
    params = (channel_id,)
    
    try:
        result = await fetch_one(query, params)
        
        if result:
            if result[0] and not result[1]:
                return False
                
            update_query = "UPDATE channel_settings SET enabled = TRUE, excluded = FALSE WHERE channel_id = %s"
            await execute_query(update_query, params)
            return True
        else:
            insert_query = "INSERT INTO channel_settings (channel_id, guild_id, enabled, excluded) VALUES (%s, %s, TRUE, FALSE)"
            insert_params = (channel_id, guild_id)
            await execute_query(insert_query, insert_params)
            return True
    except Exception as e:
        logger.error(f"Error adding channel {channel_id} for guild {guild_id}: {e}")
        return False

async def remove_channel(guild_id: int, channel_id: int) -> bool:
    """Remove a channel from the enabled list (for channel-specific mode)"""
    query = "SELECT enabled FROM channel_settings WHERE channel_id = %s AND guild_id = %s"
    params = (channel_id, guild_id)
    
    try:
        result = await fetch_one(query, params)
        
        if result:
            if not result[0]:
                return False
            else:
                update_query = "UPDATE channel_settings SET enabled = FALSE WHERE channel_id = %s"
                update_params = (channel_id,)
                await execute_query(update_query, update_params)
                return True
        else:
            return False
    except Exception as e:
        logger.error(f"Error removing channel {channel_id} for guild {guild_id}: {e}")
        return False

async def exclude_channel(guild_id: int, channel_id: int) -> bool:
    """Add a channel to the exclusion list (for server-wide mode)"""
    query = "SELECT excluded FROM channel_settings WHERE channel_id = %s"
    params = (channel_id,)
    
    try:
        result = await fetch_one(query, params)
        
        if result:
            if result[0]:
                return False
            else:
                update_query = "UPDATE channel_settings SET excluded = TRUE WHERE channel_id = %s"
                await execute_query(update_query, params)
        else:
            insert_query = "INSERT INTO channel_settings (channel_id, guild_id, enabled, excluded) VALUES (%s, %s, FALSE, TRUE)"
            insert_params = (channel_id, guild_id)
            await execute_query(insert_query, insert_params)
        
        return True
    except Exception as e:
        logger.error(f"Error excluding channel {channel_id} for guild {guild_id}: {e}")
        return False

async def include_channel(guild_id: int, channel_id: int) -> bool:
    """Remove a channel from the exclusion list (for server-wide mode)"""
    query = "SELECT excluded FROM channel_settings WHERE channel_id = %s AND guild_id = %s"
    params = (channel_id, guild_id)
    
    try:
        result = await fetch_one(query, params)
        
        if result:
            if not result[0]:
                return False
            else:
                update_query = "UPDATE channel_settings SET excluded = FALSE WHERE channel_id = %s"
                update_params = (channel_id,)
                await execute_query(update_query, update_params)
                return True
        else:
            return False
    except Exception as e:
        logger.error(f"Error including channel {channel_id} for guild {guild_id}: {e}")
        return False

async def get_channels_list(guild_id: int) -> List[int]:
    """Get list of enabled channels for a guild (for channel-specific mode)"""
    query = "SELECT channel_id FROM channel_settings WHERE guild_id = %s AND enabled = TRUE"
    params = (guild_id,)
    
    try:
        results = await fetch_all(query, params)
        return [int(row[0]) for row in results] if results else []
    except Exception as e:
        logger.error(f"Error getting channels list for guild {guild_id}: {e}")
        return []

async def get_excluded_channels(guild_id: int) -> List[int]:
    """Get list of excluded channels for a guild (for server-wide mode)"""
    query = "SELECT channel_id FROM channel_settings WHERE guild_id = %s AND excluded = TRUE"
    params = (guild_id,)
    
    try:
        results = await fetch_all(query, params)
        return [int(row[0]) for row in results] if results else []
    except Exception as e:
        logger.error(f"Error getting excluded channels for guild {guild_id}: {e}")
        return []

async def should_process_channel(guild_id: int, channel_id: int) -> bool:
    """Check if a channel should be processed based on settings"""
    try:
        settings = await get_server_settings(guild_id)
        
        if settings.get("server_wide", True):
            query = "SELECT 1 FROM channel_settings WHERE channel_id = %s AND guild_id = %s AND excluded = TRUE"
            params = (channel_id, guild_id)
            
            result = await fetch_one(query, params)
            return not bool(result)
        else:
            query = "SELECT 1 FROM channel_settings WHERE channel_id = %s AND guild_id = %s AND enabled = TRUE"
            params = (channel_id, guild_id)
            
            result = await fetch_one(query, params)
            return bool(result)
    except Exception as e:
        logger.error(f"Error checking channel processing for {channel_id} in {guild_id}: {e}")
        return True