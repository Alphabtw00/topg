# repository/nword_repo.py
"""
Database operations for N-word tracking - Ultra optimized
"""
from typing import Dict, List, Optional, Tuple
from service.mysql_service import execute_query, fetch_one, fetch_all
from utils.logger import get_logger

logger = get_logger()

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS nword_counts (
        user_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        count INT NOT NULL DEFAULT 1,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, guild_id),
        INDEX idx_guild_count (guild_id, count DESC),
        INDEX idx_global_count (count DESC),
        INDEX idx_user (user_id)
    ) ENGINE=InnoDB
    """
]

async def setup_nword_tables() -> bool:
    """Create N-word tracking table"""
    try:
        await execute_query(TABLES[0])
        return True
    except Exception as e:
        logger.error(f"Error creating nword table: {e}")
        return False

async def increment_count(user_id: int, guild_id: int, count: int = 1) -> bool:
    """
    Increment user count - single optimized query with UPSERT
    
    Args:
        user_id: Discord user ID
        guild_id: Discord guild ID
        count: Number to increment by (default 1)
    """
    query = """
    INSERT INTO nword_counts (user_id, guild_id, count)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE count = count + VALUES(count)
    """
    
    try:
        await execute_query(query, (user_id, guild_id, count))
        return True
    except Exception as e:
        logger.error(f"Error incrementing count for user {user_id}: {e}")
        return False

async def get_user_count(user_id: int, guild_id: int) -> int:
    """Get user's count for specific guild"""
    query = "SELECT count FROM nword_counts WHERE user_id = %s AND guild_id = %s"
    
    try:
        result = await fetch_one(query, (user_id, guild_id))
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error fetching count for user {user_id}: {e}")
        return 0

async def get_user_global_count(user_id: int) -> int:
    """Get user's total count across all guilds"""
    query = "SELECT SUM(count) FROM nword_counts WHERE user_id = %s"
    
    try:
        result = await fetch_one(query, (user_id,))
        return result[0] if result and result[0] else 0
    except Exception as e:
        logger.error(f"Error fetching global count for user {user_id}: {e}")
        return 0

async def get_guild_ranking(guild_id: int, limit: int = 10) -> List[Tuple[int, int]]:
    """
    Get top users in a guild
    
    Returns:
        List of (user_id, count) tuples
    """
    query = """
    SELECT user_id, count 
    FROM nword_counts 
    WHERE guild_id = %s 
    ORDER BY count DESC 
    LIMIT %s
    """
    
    try:
        results = await fetch_all(query, (guild_id, limit))
        return [(int(row[0]), int(row[1])) for row in results] if results else []
    except Exception as e:
        logger.error(f"Error fetching guild ranking: {e}")
        return []

async def get_global_ranking(limit: int = 10) -> List[Tuple[int, int]]:
    """
    Get top users globally (sum across all guilds)
    
    Returns:
        List of (user_id, total_count) tuples
    """
    query = """
    SELECT user_id, SUM(count) as total
    FROM nword_counts
    GROUP BY user_id
    ORDER BY total DESC
    LIMIT %s
    """
    
    try:
        results = await fetch_all(query, (limit,))
        return [(int(row[0]), int(row[1])) for row in results] if results else []
    except Exception as e:
        logger.error(f"Error fetching global ranking: {e}")
        return []

async def get_user_guild_rank(user_id: int, guild_id: int) -> Tuple[int, int]:
    """
    Get user's rank in a specific guild
    
    Returns:
        Tuple of (rank, count) - rank is 0 if not found
    """
    query = """
    SELECT rank_num, count FROM (
        SELECT user_id, count,
               ROW_NUMBER() OVER (ORDER BY count DESC) as rank_num
        FROM nword_counts
        WHERE guild_id = %s
    ) ranked
    WHERE user_id = %s
    """
    
    try:
        result = await fetch_one(query, (guild_id, user_id))
        return (int(result[0]), int(result[1])) if result else (0, 0)
    except Exception as e:
        logger.error(f"Error fetching guild rank for user {user_id}: {e}")
        return (0, 0)

async def get_user_global_rank(user_id: int) -> Tuple[int, int]:
    """
    Get user's global rank
    
    Returns:
        Tuple of (rank, total_count) - rank is 0 if not found
    """
    query = """
    SELECT rank_num, total FROM (
        SELECT user_id, SUM(count) as total,
               ROW_NUMBER() OVER (ORDER BY SUM(count) DESC) as rank_num
        FROM nword_counts
        GROUP BY user_id
    ) ranked
    WHERE user_id = %s
    """
    
    try:
        result = await fetch_one(query, (user_id,))
        return (int(result[0]), int(result[1])) if result else (0, 0)
    except Exception as e:
        logger.error(f"Error fetching global rank for user {user_id}: {e}")
        return (0, 0)

async def get_total_count(guild_id: Optional[int] = None) -> int:
    """
    Get total count across all users
    
    Args:
        guild_id: If provided, get count for specific guild. Otherwise global.
    """
    if guild_id:
        query = "SELECT SUM(count) FROM nword_counts WHERE guild_id = %s"
        params = (guild_id,)
    else:
        query = "SELECT SUM(count) FROM nword_counts"
        params = None
    
    try:
        result = await fetch_one(query, params)
        return result[0] if result and result[0] else 0
    except Exception as e:
        logger.error(f"Error fetching total count: {e}")
        return 0