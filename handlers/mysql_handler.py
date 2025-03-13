"""
Database handlers for storing token data and user information
"""
import aiomysql
import asyncio
import warnings
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
        # Filter out MySQL warnings to prevent them from flooding the terminal
        warnings.filterwarnings('ignore', category=Warning)
        
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
        
        # Create tables if they don't exist or update schema if needed
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Check if table exists
                await cursor.execute(f"SHOW TABLES LIKE 'token_first_calls'")
                result = await cursor.fetchone()
                
                if not result:
                    # Create table with proper column sizes
                    await cursor.execute('''
                        CREATE TABLE IF NOT EXISTS token_first_calls (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            token_address VARCHAR(64) NOT NULL,
                            user_id BIGINT NOT NULL,
                            user_name VARCHAR(255) NOT NULL,
                            initial_fdv DECIMAL(36, 18) NOT NULL,
                            initial_price DECIMAL(65, 30) NOT NULL,
                            call_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE KEY unique_token (token_address)
                        )
                    ''')
                    logger.info("Created token_first_calls table")
                else:
                    # Alter table to increase column size for existing table
                    try:
                        await cursor.execute('''
                            ALTER TABLE token_first_calls 
                            MODIFY initial_fdv DECIMAL(36, 18) NOT NULL,
                            MODIFY initial_price DECIMAL(65, 30) NOT NULL
                        ''')
                        logger.info("Updated token_first_calls table schema")
                    except Exception as e:
                        logger.warning(f"Could not update table schema: {e}")
                
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
    
    # Ensure values are properly formatted to avoid truncation
    try:
        # Convert to string first to handle scientific notation
        if isinstance(initial_price, float):
            initial_price = str(initial_price)
        if isinstance(initial_fdv, float):
            initial_fdv = str(initial_fdv)
            
        # Convert to Decimal for precise storage
        initial_price = Decimal(initial_price)
        initial_fdv = Decimal(initial_fdv)
        
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
    
async def get_db_pool_stats():
    """
    Get database connection pool statistics
    
    Returns:
        dict: Pool statistics with size, free connections, and used connections
    """
    global pool
    
    if not pool:
        return None
        
    try:
        size = pool.size
        free = pool.freesize
        
        return {
            'size': size,
            'free': free,
            'used': size - free
        }
    except Exception as e:
        logger.error(f"Error getting pool stats: {e}")
        return None