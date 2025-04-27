"""
Database operations for Truth Social tracking
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from handlers.mysql_handler import execute_query, fetch_one, fetch_all
from utils.logger import get_logger
from config import TRUTH_DEFAULT_INTERVAL

logger = get_logger()

# Table definitions
TABLES = [
    """
    CREATE TABLE IF NOT EXISTS truth_accounts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        handle VARCHAR(64) NOT NULL,
        account_id VARCHAR(64) NOT NULL,
        display_name VARCHAR(255) NULL,
        last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_post_id VARCHAR(64) NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY unique_guild_handle (guild_id, handle),
        INDEX idx_guild_id (guild_id),
        INDEX idx_handle (handle)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS truth_channels (
        id INT AUTO_INCREMENT PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        channel_id BIGINT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY unique_channel (guild_id, channel_id),
        INDEX idx_guild (guild_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS truth_settings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY unique_guild (guild_id)
    )
    """
]

async def setup_truth_tables() -> bool:
    """Create Truth Social tracking tables if they don't exist"""
    success = True
    
    for table_query in TABLES:
        try:
            await execute_query(table_query)
        except Exception as e:
            logger.error(f"Error creating Truth Social table: {e}")
            success = False
    
    return success

async def add_truth_account(guild_id: int, handle: str, account_id: str, display_name: str = None) -> bool:
    """Add a Truth Social account to tracking for a specific server"""
    query = """
    INSERT INTO truth_accounts 
    (guild_id, handle, account_id, display_name) 
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE 
    account_id = VALUES(account_id),
    display_name = VALUES(display_name),
    last_checked = CURRENT_TIMESTAMP
    """
    
    result = await execute_query(query, (guild_id, handle, account_id, display_name))
    return result is not None

async def get_truth_account(guild_id: int, handle: str) -> Optional[Dict]:
    """Get a Truth Social account by handle for a specific server"""
    query = """
    SELECT id, guild_id, handle, account_id, display_name, 
           last_checked, last_post_id, created_at 
    FROM truth_accounts 
    WHERE guild_id = %s AND handle = %s
    """
    
    result = await fetch_one(query, (guild_id, handle))
    if not result:
        return None
    
    return {
        'id': result[0],
        'guild_id': result[1],
        'handle': result[2],
        'account_id': result[3],
        'display_name': result[4],
        'last_checked': result[5],
        'last_post_id': result[6],
        'created_at': result[7]
    }

async def update_last_post(guild_id: int, handle: str, post_id: str) -> bool:
    """Update the last seen post ID for an account in a specific server"""
    query = """
    UPDATE truth_accounts 
    SET last_post_id = %s, last_checked = CURRENT_TIMESTAMP 
    WHERE guild_id = %s AND handle = %s
    """
    
    result = await execute_query(query, (post_id, guild_id, handle))
    return result is not None

async def get_guild_tracked_accounts(guild_id: int) -> List[Dict]:
    """Get all tracked Truth Social accounts for a specific server"""
    query = """
    SELECT id, guild_id, handle, account_id, display_name, 
           last_checked, last_post_id, created_at 
    FROM truth_accounts
    WHERE guild_id = %s
    """
    
    results = await fetch_all(query, (guild_id,))
    if not results:
        return []
    
    accounts = []
    for row in results:
        accounts.append({
            'id': row[0],
            'guild_id': row[1],
            'handle': row[2],
            'account_id': row[3],
            'display_name': row[4],
            'last_checked': row[5],
            'last_post_id': row[6],
            'created_at': row[7]
        })
    
    return accounts

async def remove_truth_account(guild_id: int, handle: str) -> bool:
    """Remove a Truth Social account from tracking for a specific server"""
    query = """
    DELETE FROM truth_accounts 
    WHERE guild_id = %s AND handle = %s
    """
    
    result = await execute_query(query, (guild_id, handle))
    return result is not None

async def add_truth_channel(guild_id: int, channel_id: int) -> bool:
    """Add a channel for Truth Social tracking"""
    query = """
    INSERT INTO truth_channels 
    (guild_id, channel_id) 
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE
    created_at = created_at
    """
    
    result = await execute_query(query, (guild_id, channel_id))
    return result is not None

async def remove_truth_channel(guild_id: int, channel_id: int) -> bool:
    """Remove a channel from Truth Social tracking"""
    query = "DELETE FROM truth_channels WHERE guild_id = %s AND channel_id = %s"
    
    result = await execute_query(query, (guild_id, channel_id))
    return result is not None

async def get_truth_channels(guild_id: int) -> List[int]:
    """Get channels configured for Truth Social tracking in a server"""
    query = "SELECT channel_id FROM truth_channels WHERE guild_id = %s"
    
    results = await fetch_all(query, (guild_id,))
    if not results:
        return []
    
    return [int(row[0]) for row in results]

async def get_guild_settings(guild_id: int) -> Dict:
    """Get Truth Social tracker settings for a guild"""
    query = """
    SELECT id, guild_id, enabled, created_at, updated_at 
    FROM truth_settings 
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
        INSERT INTO truth_settings 
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
    """Update Truth Social tracker settings for a guild"""
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
    UPDATE truth_settings 
    SET {', '.join(set_clauses)} 
    WHERE guild_id = %s
    """
    
    params.append(guild_id)
    
    result = await execute_query(query, tuple(params))
    if not result:
        # Settings might not exist yet, try to insert
        settings['guild_id'] = guild_id
        
        # If there's an enabled field, use it; otherwise default to False
        enabled = settings.get('enabled', False)
        
        insert_query = """
        INSERT INTO truth_settings 
        (guild_id, enabled) 
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
        enabled = VALUES(enabled)
        """
        
        result = await execute_query(insert_query, (guild_id, enabled))
        return result is not None
    
    return True

async def get_all_enabled_guilds() -> List[Dict]:
    """Get all guilds with Truth Social tracking enabled"""
    query = """
    SELECT id, guild_id, enabled, created_at, updated_at 
    FROM truth_settings 
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