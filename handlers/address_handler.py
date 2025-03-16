"""
Solana address detection and processing
"""
import asyncio
import discord
from datetime import datetime
from api.dexscreener import get_token_info, get_order_status, search_token
from api.mobula import get_all_time_high
from ui.embeds import create_token_embed, create_header_message, update_ath_in_embed, update_first_call_in_embed, update_dex_in_embed
from ui.views import CopyAddressView
from utils.logger import get_logger
from handlers.mysql_handler import get_first_call, store_first_call
from urllib.parse import quote


logger = get_logger()

async def process_addresses(message: discord.Message, session, addresses):
    """
    Process a set of Solana addresses from a message in the most efficient way

    Args:
        message: Discord message
        session: HTTP session
        addresses: Set of addresses to process
    """
    # If no addresses, return immediately
    if not addresses:
        return
        
    # Convert to list once
    address_list = list(addresses)
    
    # Process in chunks of 5 for optimal API usage
    chunks = [address_list[i:i+5] for i in range(0, len(address_list), 5)]
    
    # For each chunk, create a task to execute concurrently
    chunk_tasks = []
    for chunk in chunks:
        chunk_tasks.append(process_address_chunk(message, session, chunk))
    
    # Process all chunks in parallel
    await asyncio.gather(*chunk_tasks)

async def process_address_chunk(message, session, chunk):
    """
    Process a chunk of addresses in parallel

    Args:
        message: Discord message
        session: HTTP session
        chunk: List of addresses to process
    """
    # Get token info for the entire chunk in one API call
    addr_map = await get_token_info(session, chunk)
    
    if not addr_map:
        return
    
    # Create tasks for parallel processing
    tasks = []
    for addr in chunk:
        addr_lower = addr.lower()
        if addr_lower in addr_map:
            # Create task without semaphore to avoid bottlenecks
            tasks.append(process_token_entry(message, session, addr_map[addr_lower], addr))
    
    # Execute all tasks in parallel
    if tasks:
        await asyncio.gather(*tasks)

async def process_tickers(message, session, tickers):
    """
    Process a list of ticker symbols
    
    Args:
        message: Discord message
        session: HTTP session
        tickers: List of ticker symbols
    """
    tasks = []
    for ticker in tickers:
        tasks.append(process_ticker(message, session, ticker))
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def process_ticker(message, session, ticker):
    """
    Process a single ticker symbol
    
    Args:
        message: Discord message
        session: HTTP session
        ticker: Ticker symbol
    """
    try:
        # Clean ticker
        ticker = ticker.strip()
        if not ticker:
            return
        
        pair = await asyncio.wait_for(
            search_token(session, quote(ticker)),
            timeout=5.0  # 5-second timeout for ticker search
        )

        if not pair:
            logger.debug(f"No results found for ticker: ${ticker}")
            return
        # Get token address
        address = pair["baseToken"]["address"]
        
        # Check if address is already in message content
        if address.lower() in message.content.lower():
            logger.debug(f"Address {address} already in message, skipping ticker ${ticker}")
            return
        
        # Process token entry
        await process_token_entry(message, session, pair, address)
    
    except asyncio.TimeoutError:
        logger.warning(f"Ticker search timed out for ${ticker}")
    except Exception as e:
        logger.error(f"Ticker processing error ${ticker}: {e}")

async def process_token_entry(message: discord.Message, session, entry: dict, address: str):
    """
    Process a token entry and send response to Discord

    Args:
        message: Discord message
        session: HTTP session
        entry: Token data
        address: Token address
    """
    start_time = datetime.now().timestamp()
    try:
        # Extract data once
        current_price = float(entry.get("priceUsd", 0))
        current_fdv = float(entry.get("fdv", 0))
        pair_address = entry.get("pairAddress")
        creation_timestamp = entry.get("pairCreatedAt")

        # Create and send initial embed
        initial_embed = create_token_embed(entry, address, "")
        if not initial_embed:
            logger.error(f"Failed to create embed for {address}")
            return
        
        response = await message.reply(
            content=create_header_message(entry),
            embed=initial_embed,
            view=CopyAddressView(address),
            mention_author=True
        )

        # Launch all tasks concurrently
        tasks = []
        
        order_status_task = asyncio.create_task(get_order_status(session, address))
        tasks.append(order_status_task)
        first_call_task = asyncio.create_task(get_first_call(address))
        tasks.append(first_call_task)    
        ath_task = None
        if pair_address:
            ath_task = asyncio.create_task(get_all_time_high(session, pair_address, creation_timestamp))
            tasks.append(ath_task)

        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and update embed only once
        embed_dict = initial_embed.to_dict()
        updates_made = False

        # Process order status
        try:
            order_status = order_status_task.result()
            if order_status:
                embed_dict = update_dex_in_embed(embed_dict, order_status)
                updates_made = True
        except Exception:
            pass

        # Process first call data
        try:
            first_call_data = first_call_task.result()
            if not first_call_data:
                user_id = message.author.id
                user_name = message.author.display_name
                await store_first_call(address, user_id, user_name, current_fdv, current_price)
                first_call_data = {
                    'user_id': user_id,
                    'user_name': user_name,
                    'initial_fdv': current_fdv,
                    'initial_price': current_price,
                    'call_timestamp': datetime.now(),
                    'is_first_call': True
                }
            
            embed_dict = update_first_call_in_embed(
                embed_dict,
                first_call_data,
                current_price,
                message.author
            )
            updates_made = True
        except Exception:
            pass

        # Process ATH data
        if ath_task:
            try:
                ath_price, ath_timestamp = ath_task.result()
                if ath_price or ath_timestamp:
                    embed_dict = update_ath_in_embed(
                        embed_dict,
                        ath_price,
                        ath_timestamp,
                        current_price,
                        current_fdv
                    )
                    updates_made = True
            except Exception:
                pass

        # Update only once if needed
        if updates_made:
            await response.edit(embed=discord.Embed.from_dict(embed_dict))

        # Record processing time
        processing_time = datetime.now().timestamp() - start_time
        logger.debug(f"Token {address} processed in {processing_time:.2f}s")

    except Exception as e:
        logger.error(f"Processing error for {address}: {e}")