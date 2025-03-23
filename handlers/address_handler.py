"""
Solana address detection and processing - Optimized
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

# Optimal concurrent requests - adjust based on API limits and performance
MAX_ITEMS_PER_MESSAGE = 5 

# async def process_addresses(message: discord.Message, session, addresses):
#     """
#     Process a set of Solana addresses from a message in the most efficient way
    
#     Args:
#         message: Discord message
#         session: HTTP session
#         addresses: Set of addresses to process
#     """
#     # If no addresses, return immediately
#     if not addresses:
#         return
        
#     # Convert to list once
#     address_list = list(addresses)
    
#     # Use a semaphore to limit concurrent API calls
#     semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
#     # Create tasks for all addresses at once
#     tasks = []
#     for addr in address_list:
#         task = process_single_address(message, session, addr, semaphore)
#         tasks.append(task)
    
#     # Execute all tasks with the semaphore control
#     await asyncio.gather(*tasks, return_exceptions=True)

# async def process_single_address(message, session, address, semaphore):
#     """
#     Process a single address with semaphore control
    
#     Args:
#         message: Discord message
#         session: HTTP session
#         address: Address to process
#         semaphore: Semaphore to limit concurrency
#     """
#     async with semaphore:
#         # Get token info with the new API format
#         addr_map = await get_token_info(session, [address])
        
#         if not addr_map:
#             return
        
#         addr_lower = address.lower()
#         if addr_lower in addr_map and addr_map[addr_lower]:
#             # Process the token with the most liquid pair data
#             await process_token_entry(message, session, addr_map[addr_lower], address)

async def process_addresses(message: discord.Message, session, addresses, semaphore):
    """
    Process a set of Solana addresses from a message in the most efficient way

    Args:
        message: Discord message
        session: HTTP session
        addresses: Set of addresses to process
        semaphore: Semaphore for concurrency control
    """
    # If no addresses, return immediately
    if not addresses:
        return
    

     # Get token info for all addresses in a single API call - more efficient
    addr_map = await get_token_info(session, addresses)
    
    if not addr_map:
        return
    
    tasks = []
    for addr in addresses:
        if addr in addr_map:
            tasks.append(process_token_with_semaphore(
                message, session, addr_map[addr], addr, semaphore
            ))
    
    # Execute all tasks (they will be limited by the semaphore)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def process_token_with_semaphore(message, session, entry, address, semaphore):
    """
    Process a token with semaphore control
    
    Args:
        message: Discord message
        session: HTTP session
        entry: Token data
        address: Token address
        semaphore: Semaphore for concurrency control
    """
    async with semaphore:
        try:
            await process_token_entry(message, session, entry, address)
        except Exception as e:
            logger.error(f"Token processing error {address}: {e}")


async def process_tickers(message, session, tickers, semaphore):
    """
    Process a list of ticker symbols with rate limiting
    
    Args:
        message: Discord message
        session: HTTP session
        tickers: List of ticker symbols
        semaphore: Semaphore for concurrency control
    """
    # Create tasks with semaphore control
    tasks = []
    for ticker in tickers:
        task = process_ticker(message, session, ticker, semaphore)
        tasks.append(task)
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def process_ticker(message, session, ticker, semaphore):
    """
    Process a single ticker symbol with semaphore control
    
    Args:
        message: Discord message
        session: HTTP session
        ticker: Ticker symbol
        semaphore: Semaphore for concurrency control
    """
    async with semaphore:
        try:
            # Clean ticker
            ticker_clean = ticker.strip()
            if not ticker_clean:
                return
            
            # Use a shorter timeout and caching for ticker searches
            pair = await asyncio.wait_for(
                search_token(session, quote(ticker_clean)),
                timeout=4.0  # Reduced timeout for ticker search
            )
            
            if not pair:
                logger.debug(f"No results found for ticker: ${ticker_clean}")
                return
            
            # Get token address
            address = pair["baseToken"]["address"]
            
            # Check if address is already in message content
            if address in message.content:
                logger.debug(f"Address {address} already in message, skipping ticker ${ticker_clean}")
                return
            
            # Process token entry (already under semaphore control)
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
        creation_timestamp = entry.get("pairCreatedAt")
        chain_id = entry.get("chainId", "solana")

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
        tasks = {}
        
        tasks["order_status"] = asyncio.create_task(get_order_status(session, address))
        tasks["first_call"] = asyncio.create_task(get_first_call(address))
        
        if address:
            tasks["ath"] = asyncio.create_task(
                get_all_time_high(session, address, creation_timestamp, chain_id)
            )

        # Use a short timeout for auxiliary data to keep responses fast
        completed, pending = await asyncio.wait(tasks.values())
        
        # Cancel any pending tasks to avoid resource leaks
        for task in pending:
            task.cancel()
        
        # Process results and update embed only once
        embed_dict = initial_embed.to_dict()
        updates_made = False

        # Process order status
        if "order_status" in tasks and tasks["order_status"] in completed:
            try:
                order_status = tasks["order_status"].result()
                if order_status and not isinstance(order_status, Exception):
                    embed_dict = update_dex_in_embed(embed_dict, order_status)
                    updates_made = True
            except Exception as e:
                logger.warning(f"Error processing order status: {e}")

        # Process first call data
        if "first_call" in tasks and tasks["first_call"] in completed:
            try:
                first_call_data = tasks["first_call"].result()
                if not first_call_data or isinstance(first_call_data, Exception):
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
                
                if first_call_data:
                    embed_dict = update_first_call_in_embed(
                        embed_dict,
                        first_call_data,
                        current_price,
                        message.author
                    )
                    updates_made = True
            except Exception as e:
                logger.warning(f"Error processing first call: {e}")

        # Process ATH data  
        if "ath" in tasks and tasks["ath"] in completed:
            try:
                result = tasks["ath"].result()
                if isinstance(result, tuple) and len(result) == 2:
                    ath_price, ath_timestamp = result
                    embed_dict = update_ath_in_embed(embed_dict, ath_price, ath_timestamp, current_price, current_fdv)
                    updates_made = True
            except Exception as e:
                logger.warning(f"Error processing ATH data: {e}")

        # Update only once if needed
        if updates_made:
            await response.edit(embed=discord.Embed.from_dict(embed_dict))

        # Record processing time
        processing_time = datetime.now().timestamp() - start_time
        
        logger.debug(f"Token {address} processed in {processing_time:.2f}s")
    except Exception as e:
        logger.error(f"Processing error for {address}: {e}")