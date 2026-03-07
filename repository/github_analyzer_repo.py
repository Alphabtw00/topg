"""
Database operations for GitHub analysis cache
"""
from typing import Dict, Optional, Any
from datetime import datetime
from service.mysql_service import execute_query, fetch_one
from utils.logger import get_logger
import json

logger = get_logger()

# Table definition
TABLES = [
    """
    CREATE TABLE IF NOT EXISTS github_analysis_cache (
        cache_key VARCHAR(255) NOT NULL PRIMARY KEY,
        repo_info JSON NOT NULL,
        analysis JSON NOT NULL,
        timestamp BIGINT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_timestamp (timestamp)
    )
    """
]

async def setup_github_tables() -> bool:
    """Create GitHub analysis cache table if it doesn't exist"""
    success = True
    
    for table_query in TABLES:
        try:
            await execute_query(table_query)
        except Exception as e:
            logger.error(f"Error creating GitHub cache table: {e}")
            success = False
    
    return success

async def get_cached_analysis(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached analysis from database"""
    query = """
    SELECT repo_info, analysis, timestamp
    FROM github_analysis_cache
    WHERE cache_key = %s
    """
    
    try:
        result = await fetch_one(query, (cache_key,))
        
        if not result:
            return None
        
        return {
            'repo_info': json.loads(result[0]),
            'analysis': json.loads(result[1]),
            'timestamp': result[2],
            'cached': True
        }
    except Exception as e:
        logger.error(f"Error getting cached analysis for {cache_key}: {e}")
        return None

async def save_analysis(cache_key: str, repo_info: Dict, analysis: Dict, timestamp: float) -> bool:
    """Save analysis to database cache"""
    query = """
    INSERT INTO github_analysis_cache (cache_key, repo_info, analysis, timestamp)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        repo_info = VALUES(repo_info),
        analysis = VALUES(analysis),
        timestamp = VALUES(timestamp)
    """
    
    try:
        repo_info_json = json.dumps(repo_info)
        analysis_json = json.dumps(analysis)
        
        await execute_query(query, (cache_key, repo_info_json, analysis_json, timestamp))
        return True
    except Exception as e:
        logger.error(f"Error saving analysis for {cache_key}: {e}")
        return False

async def clear_analysis(cache_key: str) -> bool:
    """Clear specific analysis from cache"""
    query = "DELETE FROM github_analysis_cache WHERE cache_key = %s"
    
    try:
        result = await execute_query(query, (cache_key,))
        return result is not None
    except Exception as e:
        logger.error(f"Error clearing analysis for {cache_key}: {e}")
        return False