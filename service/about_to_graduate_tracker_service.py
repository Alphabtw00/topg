"""
About to graduate alert service for tokens about to graduate
Real-time WebSocket subscription for tokens reaching 90% bonding curve
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Set
from utils.logger import get_logger
import repository.about_to_graduate_repo as about_to_graduate_db
from gql import Client, gql
from gql.transport.websockets import WebsocketsTransport
from config import BITQUERY_SUBSCRIPTION_API_KEY_2

logger = get_logger()

# Simple tracking state
tracking_task = None
is_tracking = False
last_check_time = None

# Active channels cache - only enabled guilds with channels
_active_channels = {}  # guild_id -> [channel_ids]

# Token cache - 24 hour cache to prevent duplicate notifications
_token_cache = {}  # token_address -> timestamp
CACHE_DURATION = 24 * 60 * 60  # 24 hours in seconds

# Task lock
_task_lock = asyncio.Lock()

about_to_graduate_query = gql("""
subscription TokensReaching90PercentBondingCurve {
  Solana {
    DEXPools(
      where: {
        Pool: {
          Base: {PostAmount: {gt: "206900000", le: "246555000"}}, 
          Dex: {ProgramAddress: {is: "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"}}, 
          Market: {QuoteCurrency: {MintAddress: {is: "11111111111111111111111111111111"}}}
        }, 
        Transaction: {Result: {Success: true}}
      }
      limitBy: {by: Pool_Market_BaseCurrency_MintAddress, count: 1}
      orderBy: {descending: Block_Time}
    ) {
      Pool {
        Market {
          BaseCurrency {
            MintAddress
            Name
            Symbol
            Uri
          }
        }
      }
      Transaction {
        Signer
      }
      Block {
        Time
      }
    }
  }
}
""")

async def initialize_and_start_about_to_graduate_tracking(bot):
    """Initialize and start about to graduate alert tracking if enabled guilds exist"""
    try:
        logger.info("Initializing about to graduate alert tracker...")
        
        # Initialize database tables
        await about_to_graduate_db.setup_about_to_graduate_tables()
        
        # Build cache and start if needed
        await rebuild_cache_and_restart_if_needed(bot)
        
        logger.info("About to graduate alert tracking initialization complete")
    except Exception as e:
        logger.error(f"Error initializing about to graduate alert tracking: {e}")


async def rebuild_cache_and_restart_if_needed(bot):
    """Rebuild cache and start/stop tracking based on enabled guilds with channels"""
    global _active_channels
    
    try:
        # Get enabled guilds with channels
        new_channels = await about_to_graduate_db.get_enabled_guild_channels()
        
        # Update cache
        _active_channels = new_channels
        
        # Clean old cache entries
        _cleanup_cache()
        
        # Start or stop based on whether we have enabled guilds with channels
        if _active_channels:
            total_channels = sum(len(channels) for channels in _active_channels.values())
            logger.info(f"Found {len(_active_channels)} enabled guilds with {total_channels} channels for about to graduate alerts")
            await start_tracking(bot)
        else:
            logger.info("No enabled guilds with channels, stopping about to graduate alert tracking")
            await stop_tracking()
            
    except Exception as e:
        logger.error(f"Error rebuilding about to graduate alert cache: {e}")


def _cleanup_cache():
    """Remove expired entries from token cache"""
    global _token_cache
    
    current_time = time.time()
    expired_keys = [
        token for token, timestamp in _token_cache.items()
        if current_time - timestamp > CACHE_DURATION
    ]
    
    for key in expired_keys:
        del _token_cache[key]
    
    if expired_keys:
        logger.debug(f"Cleaned {len(expired_keys)} expired tokens from cache")


async def start_tracking(bot):
    """Start tracking only if not already running"""
    global tracking_task, is_tracking
    
    async with _task_lock:
        if tracking_task and not tracking_task.done():
            logger.debug("About to graduate alert tracking already running")
            return
        
        tracking_task = bot.loop.create_task(tracking_loop(bot))
        is_tracking = True
        logger.info("About to graduate alert tracking started")


async def stop_tracking():
    """Stop tracking"""
    global tracking_task, is_tracking
    
    async with _task_lock:
        if tracking_task and not tracking_task.done():
            tracking_task.cancel()
            try:
                await tracking_task
            except asyncio.CancelledError:
                pass
            
        is_tracking = False
        logger.info("About to graduate alert tracking stopped")


async def tracking_loop(bot):
    """Main tracking loop - only tracks and delegates processing"""
    global last_check_time
    
    try:
        while True:
            try:
                # Skip if no active channels
                if not _active_channels:
                    logger.debug("No active enabled channels, exiting about to graduate alert tracking loop")
                    break
                
                # Create transport with proper headers
                transport = WebsocketsTransport(
                    url=f"wss://streaming.bitquery.io/eap?token={BITQUERY_SUBSCRIPTION_API_KEY_2}",
                    headers={
                        "Sec-WebSocket-Protocol": "graphql-ws"
                    }
                )
                
                logger.debug("Connecting to Bitquery streaming API for about to graduate alerts...")
                async with Client(
                    transport=transport,
                    fetch_schema_from_transport=False,
                ) as session:
                    
                    async for result in session.subscribe(about_to_graduate_query):
                        try:
                            last_check_time = datetime.now()
                            
                            # Check if we still have active channels
                            if not _active_channels:
                                logger.debug("No active channels, stopping about to graduate alert subscription")
                                break
                            
                            pools = result.get("Solana", {}).get("DEXPools", [])
                            if not pools:
                                continue
                            
                            # Process each pool
                            for pool_data in pools:
                                token_address = extract_token_address(pool_data)
                                if token_address and not is_token_cached(token_address):
                                    # Cache token and process
                                    cache_token(token_address)
                                    asyncio.create_task(process_about_to_graduate_alert(bot, pool_data, token_address))
                            
                        except Exception as e:
                            logger.error(f"Error in about to graduate alert tracking loop: {e}")
                            
            except Exception as e:
                logger.error(f"Bitquery connection error for about to graduate: {e}")
                await asyncio.sleep(5)
                
    except asyncio.CancelledError:
        logger.info("About to graduate alert tracking loop cancelled")
    except Exception as e:
        logger.error(f"Fatal about to graduate alert tracking error: {e}")
    finally:
        is_tracking = False


def extract_token_address(pool_data):
    """Extract token mint address from pool data"""
    try:
        return pool_data["Pool"]["Market"]["BaseCurrency"]["MintAddress"]
    except (KeyError, TypeError):
        return None


def is_token_cached(token_address):
    """Check if token is in cache (within 24 hours)"""
    if token_address not in _token_cache:
        return False
    
    current_time = time.time()
    return current_time - _token_cache[token_address] < CACHE_DURATION


def cache_token(token_address):
    """Add token to cache with current timestamp"""
    _token_cache[token_address] = time.time()


async def process_about_to_graduate_alert(bot, pool_data, token_address):
    """Process about to graduate alert completely asynchronously"""
    try:        
        logger.debug(f"New about to graduate alert: {token_address}")

        final_token_info = None
        # Get token info from DexScreener
        token_info = await bot.services.dexscreener.get_token_info([token_address], chain_id="solana")

        if token_info:
            final_token_info = token_info[token_address]
                     
        # Create embed
        from ui.embeds import create_about_to_graduate_embed
        embed = await create_about_to_graduate_embed(final_token_info, pool_data, token_address)
        if not embed:
            return
        
        # Send to all channels
        asyncio.create_task(send_to_all_channels(bot, embed))
        
    except Exception as e:
        logger.error(f"Error processing about to graduate alert {token_address}: {e}")


async def send_to_all_channels(bot, embed):
    """Send embed to all active channels"""
    try:
        tasks = []
        for guild_id, channel_ids in _active_channels.items():
            for channel_id in channel_ids:
                channel = bot.get_channel(channel_id)
                if channel:
                    tasks.append(channel.send(embed=embed))
                else:
                    logger.warning(f"Channel {channel_id} not found in guild {guild_id}")
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    except Exception as e:
        logger.error(f"Error sending about to graduate alerts to channels: {e}")


def get_tracking_status() -> Dict:
    """Get current tracking status"""
    return {
        'is_tracking': is_tracking,
        'last_check': last_check_time,
        'guild_count': len(_active_channels),
        'channel_count': sum(len(channels) for channels in _active_channels.values()),
        'cached_tokens': len(_token_cache)
    }