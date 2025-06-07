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
from config import BITQUERY_API_KEY_1

logger = get_logger()

# Simple tracking state
tracking_task = None
is_tracking = False
last_check_time = None
websocket = None

# Active channels cache - only enabled guilds with channels
_active_channels = {}  # guild_id -> [channel_ids]

# Task lock
_task_lock = asyncio.Lock()

# migration_query = gql("""
# subscription DefinitiveMigrationTracker {
#   Solana {
#     Instructions(
#       where: {
#         Transaction: {
#           Result: {Success: true}
#         },
#         Instruction: {
#           Program: {
#             Address: {
#               in: [
#                 "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
#                 "boop8hVGQGqehUK2iVEMEnMrL5RbjywRzHKBmBE7ry4",
#                 "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj"
#               ]
#             },
#             Method: {
#               in: [
#                 "graduate",
#                 "migrate_to_amm",
#                 "migrate_to_cpswap"
#               ]
#             }
#           },
#           Logs: {includes: {includes: "Migrate"}}
#         }
#       }
#       orderBy: {descending: Block_Time}
#     ) {
#       Instruction {
#         Program {
#           Name
#           Address
#           Method
#         }
#         Accounts {
#           Address
#           IsWritable
#           Token {
#             Mint
#             Owner
#           }
#         }
#         Logs
#       }
#       Transaction {
#         Signature
#         Signer
#       }
#       Block {
#         Time
#         Slot
#       }
#     }
#   }
# }
# """)


migration_query = gql("""
subscription DefinitiveMigrationTracker {
  Solana {
    Instructions(
      where: {
        Transaction: {
          Result: {Success: true}
        },
        Instruction: {
          Program: {
            Address: {
              in: [
                "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
              ]
            },
          },
          Logs: {
            includes: {includes: "Migrate"}
            excludes: {includes: "already migrated"}
          }
        }
      }
      orderBy: {descending: Block_Time}
    ) {
      Instruction {
        Program {
          Name
          Address
          Method
        }
        Accounts {
          Address
          IsWritable
          Token {
            Mint
            Owner
          }
        }
        Logs
      }
      Transaction {
        Signature
        Signer
      }
      Block {
        Time
        Slot
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
            logger.info("No enabled guilds with channels, stopping tracking")
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
    global tracking_task, is_tracking, websocket
    
    async with _task_lock:
        if websocket:
            try:
                await websocket.close()
            except:
                pass
            websocket = None
            
        if tracking_task and not tracking_task.done():
            tracking_task.cancel()
            try:
                await tracking_task
            except asyncio.CancelledError:
                pass
            
        is_tracking = False
        logger.info("Migration tracking stopped")


async def tracking_loop(bot):
    """Main tracking loop - only tracks and delegates processing"""
    global last_check_time, websocket
    
    try:
        while True:
            try:
                # Skip if no active channels
                if not _active_channels:
                    logger.debug("No active enabled channels, exiting tracking loop")
                    break
                
                # Create transport with proper headers
                transport = WebsocketsTransport(
                    url=f"wss://streaming.bitquery.io/eap?token={BITQUERY_API_KEY_1}",
                     headers={
                        "Sec-WebSocket-Protocol": "graphql-ws"
                    }
                )
                
                logger.debug("Connecting to Bitquery streaming API...")
                async with Client(
                    transport=transport,
                    fetch_schema_from_transport=False,
                ) as session:
                    
                    async for result in session.subscribe(migration_query):
                        try:
                            last_check_time = datetime.now()
                            
                            # Check if we still have active channels
                            if not _active_channels:
                                logger.debug("No active channels, stopping subscription")
                                break
                            
                            instructions = result.get("Solana", {}).get("Instructions", [])
                            if not instructions:
                                continue
                            
                            # Just delegate to processor - fire and forget
                            asyncio.create_task(process_raw_instruction(bot, instructions[0]))
                            
                        except Exception as e:
                            logger.error(f"Error in tracking loop: {e}")
                            
            except Exception as e:
                logger.error(f"Bitquery connection error for migration tracker: {e}")
                await asyncio.sleep(5)
                
    except asyncio.CancelledError:
        logger.info("Tracking loop cancelled")
    except Exception as e:
        logger.error(f"Fatal tracking error: {e}")
    finally:
        is_tracking = False
        websocket = None


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
    """Extract token mint address from instruction data"""
    program_address = instruction_data["Instruction"]["Program"]["Address"]
    accounts = instruction_data["Instruction"]["Accounts"]
    
    # Protocol-specific extraction logic
    if program_address == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":  # PumpFun
        for i, account in enumerate(accounts):
            if (i == 2 and account.get("IsWritable") and 
                account.get("Token") and account.get("Token").get("Mint")):
                return account["Token"]["Mint"]
    
    elif program_address == "boop8hVGQGqehUK2iVEMEnMrL5RbjywRzHKBmBE7ry4":  # Boop
        for i, account in enumerate(accounts):
            if (i == 1 and account.get("IsWritable") and 
                account.get("Token") and account.get("Token").get("Mint")):
                return account["Token"]["Mint"]
    
    elif program_address == "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj":  # Raydium LaunchPad
        for i, account in enumerate(accounts):
            if (i == 3 and account.get("IsWritable") and 
                account.get("Token") and account.get("Token").get("Mint")):
                return account["Token"]["Mint"]
    
    # Fallback: find any non-SOL mint
    for account in accounts:
        if (account.get("Token") and account.get("Token").get("Mint") and
            account["Token"]["Mint"] != "So11111111111111111111111111111111111111112"):
            return account["Token"]["Mint"]
    
    return "Unknown Token"

def get_protocol_name(address):
    """Get protocol name from program address"""
    protocols = {
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "PumpFun",
        "boop8hVGQGqehUK2iVEMEnMrL5RbjywRzHKBmBE7ry4": "Boop",
        "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "Raydium LaunchPad"
    }
    return protocols.get(address, "Unknown Protocol")


async def process_graduation_async(bot, token_address):
    """Process graduated token completely asynchronously"""
    try:
        if not token_address:
            return
        
        # Get token info from DexScreener first
        dex_data = await bot.services.dexscreener.get_token_info(token_address)
        mobula_data = None
        
        # Check if DexScreener has image/header/links
        needs_mobula = True
        if dex_data:
            final_token_info = dex_data[token_address]
            token_info = final_token_info.get('info', {})
            if token_info.get('imageUrl') or token_info.get('header'):
                needs_mobula = False
        
        # Get Mobula data if needed for image
        if needs_mobula:
            mobula_data = await bot.services.mobula.get_token_data(token_address, blockchain="solana")
        
        # Skip if no data at all
        if not final_token_info and not mobula_data:
            return
        
        # Create embed with both data sources
        from ui.embeds import create_migration_tracker_embed
        embed = create_migration_tracker_embed(final_token_info, mobula_data, token_address)
        if not embed:
            return
        
        # Send to channels and alerts
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
        'websocket_connected': websocket is not None and not websocket.closed if websocket else False
    }