"""
Database handlers for storing token data and user information
"""
import aiomysql
import asyncio
from utils.logger import get_logger
from decimal import Decimal
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_POOL_MIN_SIZE, DB_POOL_MAX_SIZE

logger = get_logger()

# Connection pool for MySQL
pool = None

async def setup_db_pool():
    """
    Initialize the database connection pool
    """
    global pool
    try:
        pool = await aiomysql.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
            autocommit=True,
            maxsize=DB_POOL_MAX_SIZE,
            minsize=DB_POOL_MIN_SIZE
        )
        
        # Create tables if they don't exist
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(f"SHOW TABLES LIKE 'token_first_calls'")
                result = await cursor.fetchone()
                if not result:
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS token_first_calls (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            token_address VARCHAR(64) NOT NULL,
                            user_id BIGINT NOT NULL,
                            user_name VARCHAR(255) NOT NULL,
                            initial_fdv DECIMAL(20, 8) NOT NULL,
                            initial_price DECIMAL(38, 18) NOT NULL,
                            call_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE KEY unique_token (token_address)
                        )
                    ''')
                    logger.info("Created token_first_calls table")
                
        logger.info("Database connection pool established")
        return True
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return False

async def close_db_pool():
    """
    Close the database connection pool
    """
    global pool
    if pool:
        pool.close()
        await pool.wait_closed()
        logger.info("Database connection pool closed")

async def store_first_call(token_address, user_id, user_name, initial_fdv, initial_price):
    """
    Store information about the first call of a token
    
    Args:
        token_address: The token contract address
        user_id: Discord user ID who first called the token
        user_name: Discord username who first called the token
        initial_fdv: Initial fully diluted value
        initial_price: Initial token price
        
    Returns:
        bool: True if successful, False otherwise
    """
    global pool
    if not pool:
        logger.error("Database pool not initialized")
        return False
        
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    '''
                    INSERT IGNORE INTO token_first_calls 
                    (token_address, user_id, user_name, initial_fdv, initial_price) 
                    VALUES (%s, %s, %s, %s, %s)
                    ''',
                    (token_address.lower(), user_id, user_name, initial_fdv, initial_price)
                )
                
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Database error storing first call: {e}")
        return False

async def get_first_call(token_address):
    """
    Get information about the first call of a token
    
    Args:
        token_address: The token contract address
        
    Returns:
        dict: First call information or None if not found
    """
    global pool
    if not pool:
        logger.error("Database pool not initialized")
        return None
        
    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    '''
                    SELECT * FROM token_first_calls 
                    WHERE token_address = %s
                    ''',
                    (token_address.lower(),)
                )
                
                result = await cursor.fetchone()
                return result
    except Exception as e:
        logger.error(f"Database error retrieving first call: {e}")
        return None