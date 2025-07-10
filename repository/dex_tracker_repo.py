"""
Database operations for DexScreener token tracking
"""
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from service.mysql_service import execute_query, fetch_one, fetch_all
from utils.logger import get_logger

logger = get_logger()

# Table definitions
TABLES = [
    """
    CREATE TABLE IF NOT EXISTS dex_tracker_settings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY unique_guild (guild_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dex_tracker_channels (
        id INT AUTO_INCREMENT PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        channel_id BIGINT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY unique_channel (guild_id, channel_id),
        INDEX idx_guild (guild_id)
    )
    """
]


async def get_enabled_guild_channels() -> Dict[int, List[int]]:
    """Get channels for enabled guilds only - hybrid approach"""
    query = """
    SELECT tc.guild_id, tc.channel_id
    FROM dex_tracker_channels tc
    JOIN dex_tracker_settings ts ON tc.guild_id = ts.guild_id
    WHERE ts.enabled = TRUE
    """
    
    results = await fetch_all(query)
    if not results:
        return {}
    
    channels = {}
    for row in results:
        guild_id = int(row[0])
        channel_id = int(row[1])
        
        if guild_id not in channels:
            channels[guild_id] = []
            
        channels[guild_id].append(channel_id)
    
    return channels




async def setup_dex_tables() -> bool:
    """Create DexScreener tracking tables if they don't exist"""
    success = True
    
    for table_query in TABLES:
        try:
            await execute_query(table_query)
        except Exception as e:
            logger.error(f"Error creating DexScreener table: {e}")
            success = False
    
    return success

async def get_guild_settings(guild_id: int) -> Dict:
    """Get DexScreener tracker settings for a guild"""
    query = """
    SELECT id, guild_id, enabled, created_at, updated_at 
    FROM dex_tracker_settings 
    WHERE guild_id = %s
    """
    
    result = await fetch_one(query, (guild_id,))
    
    if not result:
        # Insert default settings
        default_settings = {
            'guild_id': guild_id,
            'enabled': False
        }
        
        insert_query = """
        INSERT INTO dex_tracker_settings 
        (guild_id, enabled) 
        VALUES (%s, %s)
        """
        
        await execute_query(
            insert_query, 
            (
                guild_id, 
                default_settings['enabled']
            )
        )
        
        return default_settings
    
    return {
        'id': result[0],
        'guild_id': result[1],
        'enabled': bool(result[2]),
        'created_at': result[3],
        'updated_at': result[4]
    }

async def update_guild_settings(guild_id: int, settings: Dict) -> bool:
    """Update DexScreener tracker settings for a guild"""
    valid_fields = ['enabled']
    set_clauses = []
    params = []
    
    for field, value in settings.items():
        if field in valid_fields:
            set_clauses.append(f"{field} = %s")
            params.append(value)
    
    if not set_clauses:
        return False  # Nothing to update
    
    query = f"""
    UPDATE dex_tracker_settings 
    SET {', '.join(set_clauses)} 
    WHERE guild_id = %s
    """
    
    params.append(guild_id)
    
    result = await execute_query(query, tuple(params))
    if not result:
        # Settings might not exist yet, try to insert
        settings['guild_id'] = guild_id
        
        # If there's an enabled field, use it; otherwise default to True
        enabled = settings.get('enabled', True)
        
        insert_query = """
        INSERT INTO dex_tracker_settings 
        (guild_id, enabled) 
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
        enabled = VALUES(enabled)
        """
        
        result = await execute_query(insert_query, (guild_id, enabled))
        return result is not None
    
    return True

async def add_channel(guild_id: int, channel_id: int) -> bool:
    """Add a channel to the DexScreener tracker. Returns True if newly added, False if already exists."""
    # Check if channel already exists
    check_query = "SELECT 1 FROM dex_tracker_channels WHERE guild_id = %s AND channel_id = %s"
    existing = await fetch_one(check_query, (guild_id, channel_id))
    
    if existing:
        return False  # Channel already exists
    
    # Insert new channel
    query = """
    INSERT INTO dex_tracker_channels 
    (guild_id, channel_id) 
    VALUES (%s, %s)
    """
    
    result = await execute_query(query, (guild_id, channel_id))
    return result is not None

async def remove_channel(guild_id: int, channel_id: int) -> bool:
    """Remove a channel from the DexScreener tracker. Returns True if removed, False if not found."""
    # Check if channel exists before removing
    check_query = "SELECT 1 FROM dex_tracker_channels WHERE guild_id = %s AND channel_id = %s"
    existing = await fetch_one(check_query, (guild_id, channel_id))
    
    if not existing:
        return False  # Channel doesn't exist
    
    # Remove the channel
    query = "DELETE FROM dex_tracker_channels WHERE guild_id = %s AND channel_id = %s"
    result = await execute_query(query, (guild_id, channel_id))
    return result is not None

async def get_channels(guild_id: int) -> List[int]:
    """Get channels configured for DexScreener tracking in a guild"""
    query = "SELECT channel_id FROM dex_tracker_channels WHERE guild_id = %s"
    
    results = await fetch_all(query, (guild_id,))
    return [int(row[0]) for row in results] if results else []

async def get_all_guild_channels() -> Dict[int, List[int]]:
    """Get all channels configured for DexScreener tracking across all enabled guilds"""
    query = """
    SELECT tc.guild_id, tc.channel_id
    FROM dex_tracker_channels tc
    JOIN dex_tracker_settings ts ON tc.guild_id = ts.guild_id
    WHERE ts.enabled = TRUE
    """
    
    results = await fetch_all(query)
    if not results:
        return {}
    
    channels = {}
    for row in results:
        guild_id = int(row[0])
        channel_id = int(row[1])
        
        if guild_id not in channels:
            channels[guild_id] = []
            
        channels[guild_id].append(channel_id)
    
    return channels

async def get_all_enabled_guilds() -> List[Dict]:
    """Get all guilds with DexScreener tracking enabled"""
    query = """
    SELECT id, guild_id, enabled, created_at, updated_at 
    FROM dex_tracker_settings 
    WHERE enabled = TRUE
    """
    
    results = await fetch_all(query)
    if not results:
        return []
    
    guilds = []
    for row in results:
        guilds.append({
            'id': row[0],
            'guild_id': row[1],
            'enabled': bool(row[2]),
            'created_at': row[3],
            'updated_at': row[4]
        })
    
    return guilds

async def enable_tracking(guild_id: int) -> bool:
    """Enable DexScreener tracking for a guild. Returns True if newly enabled, False if already enabled."""
    # Check current state
    settings = await get_guild_settings(guild_id)
    if settings.get('enabled', False):
        return False  # Already enabled
    
    # Enable tracking
    return await update_guild_settings(guild_id, {'enabled': True})

async def disable_tracking(guild_id: int) -> bool:
    """Disable DexScreener tracking for a guild. Returns True if newly disabled, False if already disabled."""
    # Check current state
    settings = await get_guild_settings(guild_id)
    if not settings.get('enabled', False):
        return False  # Already disabled
    
    # Disable tracking
    return await update_guild_settings(guild_id, {'enabled': False})