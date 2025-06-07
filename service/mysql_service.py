"""
Database handlers for storing token data, user information, and settings
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
    Initialize the database connection pool with optimized settings
    and connection validation
    """
    global pool
    
    # Check if pool already exists
    if pool is not None:
        # Verify pool is healthy before returning
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    await cursor.fetchone()
            logger.info("Database pool is healthy and reused")
            return True
        except Exception as e:
            logger.warning(f"Existing database pool is unhealthy, recreating: {e}")
            try:
                pool.close()
                await pool.wait_closed()
            except Exception:
                pass
        
    try:
        # Filter out MySQL warnings to prevent them from flooding the terminal
        warnings.filterwarnings('ignore', category=Warning)
        
        # Optimized pool settings
        pool = await aiomysql.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
            autocommit=True,
            maxsize=DB_POOL_MAX_SIZE,
            minsize=DB_POOL_MIN_SIZE,
            echo=False,  # Set to True only for debugging
            pool_recycle=3600,  # Recycle connections older than 1 hour
            connect_timeout=10,  # Timeout for establishing connections
            charset='utf8mb4',
            use_unicode=True,
            loop=asyncio.get_event_loop()
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
                            guild_id BIGINT NOT NULL,
                            user_id BIGINT NOT NULL,
                            user_name VARCHAR(255) NOT NULL,
                            initial_fdv DECIMAL(36, 18) NOT NULL,
                            initial_price DECIMAL(65, 30) NOT NULL,
                            channel_id BIGINT NULL,
                            message_id VARCHAR(64) NULL,
                            call_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE KEY unique_token_guild (token_address, guild_id),
                            INDEX idx_user_id (user_id),
                            INDEX idx_guild_id (guild_id),
                            INDEX idx_call_timestamp (call_timestamp)
                        )
                    ''')
                    logger.info("Created token_first_calls table with optimized indexes")
                else:
                    # Check for and add missing columns and indexes
                    try:
                        # Check if guild_id column exists
                        await cursor.execute('''
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_schema = DATABASE() 
                            AND table_name = 'token_first_calls' 
                            AND column_name = 'guild_id'
                        ''')
                        has_guild_column = await cursor.fetchone()
                        
                        if has_guild_column and has_guild_column[0] == 0:
                            # Add guild_id column
                            await cursor.execute('ALTER TABLE token_first_calls ADD COLUMN guild_id BIGINT NOT NULL DEFAULT 0')
                            logger.info("Added guild_id column to token_first_calls")
                            
                            # Add index for guild_id
                            await cursor.execute('ALTER TABLE token_first_calls ADD INDEX idx_guild_id (guild_id)')
                            logger.info("Added guild_id index to token_first_calls")
                            
                            # Add composite unique key
                            await cursor.execute('ALTER TABLE token_first_calls DROP INDEX unique_token')
                            await cursor.execute('ALTER TABLE token_first_calls ADD UNIQUE KEY unique_token_guild (token_address, guild_id)')
                            logger.info("Modified unique key to include guild_id in token_first_calls")
                        
                        # Check if channel_id column exists
                        await cursor.execute('''
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_schema = DATABASE() 
                            AND table_name = 'token_first_calls' 
                            AND column_name = 'channel_id'
                        ''')
                        has_channel_column = await cursor.fetchone()
                        
                        if has_channel_column and has_channel_column[0] == 0:
                            # Add channel_id column
                            await cursor.execute('ALTER TABLE token_first_calls ADD COLUMN channel_id BIGINT NULL')
                            logger.info("Added channel_id column to token_first_calls")
                        
                        # Check if message_id column exists
                        await cursor.execute('''
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_schema = DATABASE() 
                            AND table_name = 'token_first_calls' 
                            AND column_name = 'message_id'
                        ''')
                        has_message_column = await cursor.fetchone()
                        
                        if has_message_column and has_message_column[0] == 0:
                            # Add message_id column
                            await cursor.execute('ALTER TABLE token_first_calls ADD COLUMN message_id VARCHAR(64) NULL')
                            logger.info("Added message_id column to token_first_calls")
                            
                        # Check for user_id index
                        await cursor.execute('''
                            SELECT COUNT(*) 
                            FROM information_schema.statistics 
                            WHERE table_schema = DATABASE() 
                            AND table_name = 'token_first_calls' 
                            AND index_name = 'idx_user_id'
                        ''')
                        has_user_index = await cursor.fetchone()
                        
                        if has_user_index and has_user_index[0] == 0:
                            await cursor.execute('ALTER TABLE token_first_calls ADD INDEX idx_user_id (user_id)')
                            logger.info("Added missing user_id index to token_first_calls")
                            
                        # Update column sizes if needed
                        await cursor.execute('''
                            ALTER TABLE token_first_calls 
                            MODIFY initial_fdv DECIMAL(36, 18) NOT NULL,
                            MODIFY initial_price DECIMAL(65, 30) NOT NULL
                        ''')
                        logger.debug("Updated token_first_calls table schema")
                    except Exception as e:
                        logger.warning(f"Could not update table schema: {e}")
        
        # Log pool stats
        logger.info(f"Database connection pool established: size={DB_POOL_MIN_SIZE}-{DB_POOL_MAX_SIZE}")
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
        pool = None

# Add a more robust execute_query function with retries
async def execute_query(query, params=None, retries=2):
    """
    Execute a SQL query with retry logic
    
    Args:
        query: SQL query string
        params: Query parameters (tuple)
        retries: Number of retries on connection errors
        
    Returns:
        int: Number of affected rows or None on error
    """
    global pool
    if not pool:
        logger.error("Database pool not initialized")
        return None
        
    for attempt in range(retries + 1):
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    return cursor.rowcount
        except (aiomysql.OperationalError, aiomysql.InternalError) as e:
            # Connection or database internal errors - retry
            if attempt < retries:
                logger.warning(f"Database operation error, retrying ({attempt+1}/{retries}): {e}")
                await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                continue
            logger.error(f"Database operation failed after {retries} retries: {e}")
            return None
        except Exception as e:
            logger.error(f"Database error executing query: {e}")
            logger.debug(f"Query: {query}, Params: {params}")
            return None

async def fetch_one(query, params=None):
    """
    Fetch a single row from the database
    
    Args:
        query: SQL query string
        params: Query parameters (tuple)
        
    Returns:
        tuple: Row data or None if not found
    """
    global pool
    if not pool:
        logger.error("Database pool not initialized")
        return None
        
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                return await cursor.fetchone()
    except Exception as e:
        logger.error(f"Database error fetching row: {e}")
        logger.debug(f"Query: {query}, Params: {params}")
        return None

async def fetch_all(query, params=None):
    """
    Fetch all rows from the database
    
    Args:
        query: SQL query string
        params: Query parameters (tuple)
        
    Returns:
        list: List of rows or empty list if none found
    """
    global pool
    if not pool:
        logger.error("Database pool not initialized")
        return []
        
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                return await cursor.fetchall()
    except Exception as e:
        logger.error(f"Database error fetching rows: {e}")
        logger.debug(f"Query: {query}, Params: {params}")
        return []

async def store_first_call(token_address, guild_id, user_id, user_name, initial_fdv, initial_price, channel_id=None, message_id=None):
    """
    Store information about the first call of a token in a specific server
    
    Args:
        token_address: The token contract address
        guild_id: Discord server ID
        user_id: Discord user ID who first called the token
        user_name: Discord username who first called the token
        initial_fdv: Initial fully diluted value
        initial_price: Initial token price
        channel_id: Discord channel ID where token was called (optional)
        message_id: Discord message ID of the call (optional)
        
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
                    (token_address, guild_id, user_id, user_name, initial_fdv, initial_price, channel_id, message_id) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ''',
                    (token_address, guild_id, user_id, user_name, initial_fdv, initial_price, channel_id, message_id)
                )
                
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Database error storing first call: {e}")
        return False

async def get_first_call(token_address, guild_id):
    """
    Get information about the first call of a token in a specific server
    
    Args:
        token_address: The token contract address
        guild_id: Discord server ID
        
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
                    WHERE token_address = %s AND guild_id = %s
                    ''',
                    (token_address, guild_id)
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