"""
Migration tracker service for graduated tokens
Real-time WebSocket subscription for token graduations
"""
import asyncio
import time
import json
from datetime import datetime
from typing import Dict, List, Optional
from utils.logger import get_logger
import repository.migration_tracker_repo as migration_db
from gql import Client, gql
from gql.transport.websockets import WebsocketsTransport
from config import BITQUERY_SUBSCRIPTION_API_KEY_2, BITQUERY_SUBSCRIPTION_API_KEY_3
from ui.embeds import create_migration_tracker_embed

logger = get_logger()

# Simple tracking state
tracking_task = None
is_tracking = False
last_check_time = None
log_websocket = None
method_websocket = None

# Active channels cache - only enabled guilds with channels
_active_channels = {}  # guild_id -> [channel_ids]

# Task lock
_task_lock = asyncio.Lock()

info_query = """
query GetTokenInfo($contractAddress: String!) {
    Solana {
    DEXTradeByTokens(
        where: {Trade: {Currency: {MintAddress: {is: $contractAddress}}}, Transaction: {Result: {Success: true}}}
        orderBy: {descending: Block_Time}
        limit: {count: 1}
    ) {
        Trade {
        Currency {
            Name
            Symbol
            MintAddress
            Uri
        }
        PriceInUSD
        Account {
            Owner
        }
        }
    }
    TokenSupplyUpdates(
        where: {TokenSupplyUpdate: {Currency: {MintAddress: {is: $contractAddress}}}}
        orderBy: {descending: Block_Time}
        limit: {count: 1}
    ) {
        TokenSupplyUpdate {
        PostBalance
        PreBalance
        }
    }
    }
}
"""
        
# Query 1: Log-based migrations (Pump.fun)
log_based_query = gql("""
subscription LogBasedMigrations {
  Solana {
    Instructions(
      where: {
        Transaction: {Result: {Success: true}},
        Instruction: {
          Program: {
            Address: {
              in: [
                "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
              ]
            }
          },
          Logs: {
            includes: {includes: "Migrate"},
            excludes: {includes: "already migrated"}
          }
        }
      }
      orderBy: {descending: Block_Time}
    ) {
      Block {Time}
      Transaction {Signature, Signer}
      Instruction {
        Program {
          Address
          Method
          Name
        }
        Accounts {
          Address
          IsWritable
          Token {Mint, Owner, ProgramId}
        }
        Logs
      }
    }
  }
}
""")

# Query 2: Method-based migrations (Boop, Meteora, Bonk, Moonshot)
method_based_query = gql("""
subscription MethodBasedMigrations {
  Solana {
    Instructions(
      where: {
        Transaction: {Result: {Success: true}}, 
        Instruction: {
          Program: {
            Address: {
              in: [
                "boop8hVGQGqehUK2iVEMEnMrL5RbjywRzHKBmBE7ry4",
                "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN",
                "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",
                "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG"
              ]
            }, 
            Method: {
              in: [
                "graduate",
                "migrate_meteora_damm",
                "migration_damm_v2", 
                "migrate_to_amm",
                "migrate_to_cpswap",
                "migrateFunds"
              ]
            }
          }, 
          Logs: {excludes: {includes: "already migrated"}}
        }
      }
      orderBy: {descending: Block_Time}
    ) {
      Block {Time}
      Transaction {Signature, Signer}
      Instruction {
        Program {
          Address
          Method
          Name
        }
        Accounts {
          Address
          IsWritable
          Token {Mint, Owner, ProgramId}
        }
        Logs
      }
    }
  }
}
""")

async def initialize_and_start_migration_tracking(bot):
    """Initialize and start migration tracking if enabled guilds with channels exist"""
    try:
        logger.info("Initializing migration tracker...")
        
        # Initialize database tables
        await migration_db.setup_migration_tables()
        
        # Build cache and start if needed
        await rebuild_cache_and_restart_if_needed(bot)
        
        logger.info("Migration tracking initialization complete")
    except Exception as e:
        logger.error(f"Error initializing migration tracking: {e}")


async def rebuild_cache_and_restart_if_needed(bot):
    """Rebuild cache and start/stop tracking based on enabled guilds with channels"""
    global _active_channels
    
    try:
        # Get enabled guilds with channels
        new_channels = await migration_db.get_enabled_guild_channels()
        
        # Update cache
        _active_channels = new_channels
        
        # Start or stop based on whether we have enabled guilds with channels
        if _active_channels:
            total_channels = sum(len(channels) for channels in _active_channels.values())
            logger.info(f"Found {len(_active_channels)} enabled guilds with {total_channels} channels")
            await start_tracking(bot)
        else:
            logger.info("No enabled guilds with channels, stopping migration tracking")
            await stop_tracking()
            
    except Exception as e:
        logger.error(f"Error rebuilding cache: {e}")


async def start_tracking(bot):
    """Start tracking only if not already running"""
    global tracking_task, is_tracking
    
    async with _task_lock:
        if tracking_task and not tracking_task.done():
            logger.debug("Tracking already running")
            return
        
        tracking_task = bot.loop.create_task(tracking_loop(bot))
        is_tracking = True
        logger.info("Migration tracking started")


async def stop_tracking():
    """Stop tracking"""
    global tracking_task, is_tracking, log_websocket, method_websocket
    
    async with _task_lock:
        if log_websocket:
            try:
                await log_websocket.close()
            except:
                pass
            log_websocket = None
            
        if method_websocket:
            try:
                await method_websocket.close()
            except:
                pass
            method_websocket = None
            
        if tracking_task and not tracking_task.done():
            tracking_task.cancel()
            try:
                await tracking_task
            except asyncio.CancelledError:
                pass
            
        is_tracking = False
        logger.info("Migration tracking stopped")


async def tracking_loop(bot):
    """Main tracking loop - manages both subscription streams"""
    global last_check_time
    
    try:
        while True:
            try:
                # Skip if no active channels
                if not _active_channels:
                    logger.debug("No active enabled channels, exiting tracking loop")
                    break
                
                # Create tasks for both subscriptions with different tokens
                log_task = asyncio.create_task(
                    handle_log_based_stream(bot, BITQUERY_SUBSCRIPTION_API_KEY_2)
                )
                method_task = asyncio.create_task(
                    handle_method_based_stream(bot, BITQUERY_SUBSCRIPTION_API_KEY_3)
                )
                
                # Wait for either task to complete or fail
                done, pending = await asyncio.wait(
                    [log_task, method_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Check if any task failed
                for task in done:
                    exc = task.exception()
                    if exc:
                        raise exc
                        
            except Exception as e:
                logger.error(f"Bitquery connection error for migration tracker: {e}")
                await asyncio.sleep(5)
                
    except asyncio.CancelledError:
        logger.info("Tracking loop cancelled")
    except Exception as e:
        logger.error(f"Fatal tracking error: {e}")
    finally:
        is_tracking = False
        log_websocket = None
        method_websocket = None


async def handle_log_based_stream(bot, api_key):
    """Handle log-based migrations stream (Pump.fun)"""
    global log_websocket
    
    try:
        # Create transport with log-based token
        transport = WebsocketsTransport(
            url=f"wss://streaming.bitquery.io/eap?token={api_key}",
            headers={
                "Sec-WebSocket-Protocol": "graphql-ws"
            }
        )
        
        logger.debug("Connecting to Bitquery streaming API for log-based migrations...")
        async with Client(
            transport=transport,
            fetch_schema_from_transport=False,
        ) as session:
            log_websocket = transport.websocket if hasattr(transport, 'websocket') else None
            
            async for result in session.subscribe(log_based_query):
                await process_stream_result(bot, result, "log_based")
                
    except Exception as e:
        logger.error(f"Error in log-based stream: {e}")
    finally:
        log_websocket = None


async def handle_method_based_stream(bot, api_key):
    """Handle method-based migrations stream (Boop, Meteora, Bonk, Moonshot)"""
    global method_websocket
    
    try:
        # Create transport with method-based token
        transport = WebsocketsTransport(
            url=f"wss://streaming.bitquery.io/eap?token={api_key}",
            headers={
                "Sec-WebSocket-Protocol": "graphql-ws"
            }
        )
        
        logger.debug("Connecting to Bitquery streaming API for method-based migrations...")
        async with Client(
            transport=transport,
            fetch_schema_from_transport=False,
        ) as session:
            method_websocket = transport.websocket if hasattr(transport, 'websocket') else None
            
            async for result in session.subscribe(method_based_query):
                await process_stream_result(bot, result, "method_based")
                
    except Exception as e:
        logger.error(f"Error in method-based stream: {e}")
    finally:
        method_websocket = None


async def process_stream_result(bot, result, stream_type):
    """Process result from either stream"""
    try:
        last_check_time = datetime.now()
        
        # Check if we still have active channels
        if not _active_channels:
            logger.debug("No active channels, stopping subscription")
            return
        
        instructions = result.get("Solana", {}).get("Instructions", [])
        if not instructions:
            return
        
        # Process the first instruction
        asyncio.create_task(process_raw_instruction(bot, instructions[0]))
        
    except Exception as e:
        logger.error(f"Error processing {stream_type} stream result: {e}")


async def process_raw_instruction(bot, instruction_data):
    """Process raw instruction data - extract and delegate further"""
    try:
        logger.debug(f"New raw migration detected: {instruction_data}")
        
        # Extract token mint
        token_address = extract_token_mint(instruction_data)
        if not token_address or token_address == "Unknown Token":
            return
        
        logger.debug(f"New migration detected: {token_address}")
        
        # Delegate to graduation processor
        asyncio.create_task(process_graduation_async(bot, token_address))
        
    except Exception as e:
        logger.error(f"Error processing raw instruction: {e}")


def extract_token_mint(instruction_data):
    """Extract token mint address from instruction data based on method name"""
    try:
        program_method = instruction_data["Instruction"]["Program"].get("Method", "")
        accounts = instruction_data["Instruction"]["Accounts"]
        
        # Define account index mapping based on method name
        method_index_map = {
            "migrate_meteora_damm": 7,    # 8th (index 7)
            "migration_damm_v2": 13,      # 14th (index 13)
            "migrate_to_cpswap": 1,       # 2nd (index 1)
            "migrate": 2,                 # 3rd (index 2)
            "graduate": 0,                # 1st (index 0)
            "migrateFunds" : 3            # 4th (index 3)
        }
        
        # Get the expected account index based on method
        expected_index = method_index_map.get(program_method)
        
        if expected_index is not None:
            # Try to get mint from expected index
            token_mint = get_mint_from_account_index(accounts, expected_index)
            if token_mint:
                return token_mint
        
        # Fallback: find first non-SOL mint in accounts
        for account in accounts:
            if (account.get("Token") and 
                account.get("Token").get("Mint") and
                account["Token"]["Mint"] != "So11111111111111111111111111111111111111112"):
                return account["Token"]["Mint"]
        
        logger.warning(f"No token mint found for method {program_method}")
        return "Unknown Token"
        
    except Exception as e:
        logger.error(f"Error extracting token mint: {e}")
        return "Unknown Token"


def get_mint_from_account_index(accounts, target_index):
    """Get mint from specific account index, fallback to address if mint not available"""
    try:
        # Check if target index exists
        if target_index >= len(accounts):
            return None
        
        account = accounts[target_index]
        
        # Try to get mint from token info
        if (account.get("Token") and 
            account.get("Token").get("Mint") and
            account["Token"]["Mint"] != "So11111111111111111111111111111111111111112"):
            return account["Token"]["Mint"]
        
        # Fallback to account address if mint not available
        if account.get("Address"):
            return account["Address"]
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting mint from account index {target_index}: {e}")
        return None


def get_protocol_name(address):
    """Get protocol name from program address"""
    protocols = {
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "Pump.fun",
        "boop8hVGQGqehUK2iVEMEnMrL5RbjywRzHKBmBE7ry4": "Boop",
        "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN": "Meteora DBC",
        "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "Bonk",
        "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG": "Moonshot"
    }
    return protocols.get(address, "Unknown Protocol")


async def process_graduation_async(bot, token_address):
    """Process graduated token completely asynchronously"""
    try:
        if not token_address:
            return
       
        # Initialize variables
        final_token_info = None
        mobula_data = None
        bitquery_data = None
        
        # Step 1: Get token info from DexScreener first
        dex_data = await bot.services.dexscreener.get_token_info([token_address], chain_id="solana")
        
        # Extract token info if available
        if dex_data:
            final_token_info = dex_data[token_address]
       
        # Check if DexScreener has image/header/links
        needs_mobula = True
        if final_token_info:
            token_info = final_token_info.get('info', {})
            if token_info.get('imageUrl') or token_info.get('header'):
                needs_mobula = False
       
        # Get Mobula data if needed for image
        if needs_mobula:
            mobula_data = await bot.services.mobula.get_token_data(token_address, blockchain="solana")
       
        # If no data from DexScreener or Mobula, try BitQuery
        if not final_token_info and not mobula_data:
            variables = {"contractAddress": token_address}
            bitquery_data = await bot.services.bitquery.execute_query(info_query, variables)
       
        # Skip if no data at all
        if not final_token_info and not mobula_data and not bitquery_data:
            return
       
        # Create embed with available data sources
        embed = await create_migration_tracker_embed(final_token_info, mobula_data, bitquery_data, token_address)
        if not embed:
            return
       
        # Send to channels and alerts using tasks
        asyncio.create_task(send_to_all_channels(bot, embed))
        asyncio.create_task(send_graduation_alerts(bot, token_address, embed))
       
    except Exception as e:
        logger.error(f"Error processing graduation {token_address}: {e}")
        

async def send_to_all_channels(bot, embed):
    """Send embed to all active channels"""
    try:
        if not embed:
            logger.error("No embed provided to send_to_all_channels")
            return
        
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
        logger.error(f"Error sending to channels: {e}")


async def send_graduation_alerts(bot, token_address, embed):
    """Send graduation alerts to first callers"""
    try:
        from service.mysql_service import fetch_all
        
        # Get all first calls for this token
        first_calls = await fetch_all(
            "SELECT user_id, channel_id, message_id FROM token_first_calls WHERE token_address = %s",
            (token_address,)
        )
        
        if not first_calls:
            return
        
        # Send alerts
        tasks = []
        for user_id, call_channel_id, message_id in first_calls:
            if user_id and call_channel_id:
                tasks.append(send_individual_alert(
                    bot, user_id, call_channel_id, message_id, embed, token_address
                ))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    except Exception as e:
        logger.error(f"Error sending graduation alerts for {token_address}: {e}")


async def send_individual_alert(bot, user_id, call_channel_id, message_id, embed, token_address):
    """Send individual graduation alert"""
    try:
        call_channel = bot.get_channel(int(call_channel_id))
        if not call_channel:
            return
        
        notification = f"<@{user_id}> Your token call graduated!"
        
        # Create alert embed (copy of original with different footer)
        import discord
        alert_embed = discord.Embed.from_dict(embed.to_dict())
        alert_embed.set_footer(text="Migration Alert", icon_url=embed.footer.icon_url if embed.footer else None)
        
        if message_id:
            try:
                orig_msg = await call_channel.fetch_message(int(message_id))
                await orig_msg.reply(content=notification, embed=alert_embed)
                return
            except:
                pass
        
        await call_channel.send(content=notification, embed=alert_embed)
        
    except Exception as e:
        logger.error(f"Error sending alert to user {user_id}: {e}")


def get_tracking_status() -> Dict:
    """Get current tracking status"""
    return {
        'is_tracking': is_tracking,
        'last_check': last_check_time,
        'guild_count': len(_active_channels),
        'channel_count': sum(len(channels) for channels in _active_channels.values()),
        'log_websocket_connected': log_websocket is not None and not log_websocket.closed if log_websocket else False,
        'method_websocket_connected': method_websocket is not None and not method_websocket.closed if method_websocket else False
    }