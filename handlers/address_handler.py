"""
Solana address detection and processing
"""
import asyncio
import discord
from datetime import datetime
from api.dexscreener import get_token_info, get_order_status
from api.mobula import get_all_time_high
from ui.embeds import create_token_embed, create_header_message, update_ath_in_embed, update_first_call_in_embed
from ui.views import CopyAddressView
from utils.logger import get_logger
from handlers.mysql_handler import get_first_call, store_first_call
from config import MAX_CONCURRENT_PROCESSES

logger = get_logger()

# Semaphore for limiting concurrent processing
processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROCESSES)

async def process_addresses(message: discord.Message, session, addresses):
    """
    Process a set of Solana addresses from a message

    Args:
        message: Discord message
        session: HTTP session
        addresses: Set of addresses to process
    """
    # Convert to list once
    address_list = list(addresses)
    
    chunks = [address_list[i:i+5] for i in range(0, len(address_list), 5)]
    
    # Process each chunk
    for chunk in chunks:
        # Get token info for the entire chunk in one API call
        addr_map = await get_token_info(session, chunk)

        if not addr_map:
            continue

        # Create tasks for parallel processing
        tasks = []
        for addr in chunk:
            addr_lower = addr.lower()
            if addr_lower in addr_map:
                tasks.append(
                    process_address_with_semaphore(message, session, addr_map[addr_lower], addr)
                )

        # Execute all tasks in parallel if there are any
        if tasks:
            await asyncio.gather(*tasks)

async def process_address_with_semaphore(message, session, entry, address):
    """
    Process a single address with semaphore for concurrency control

    Args:
        message: Discord message
        session: HTTP session
        entry: Token data
        address: Token address
    """
    async with processing_semaphore:
        await process_token_entry(message, session, entry, address)

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
        # Start all API calls concurrently to improve performance
        order_status_task = asyncio.create_task(get_order_status(session, address))

        # Extract data for first call tracking - do this once to avoid repeated lookups
        current_price = float(entry.get("priceUsd", 0))
        current_fdv = float(entry.get("fdv", 0))
        pair_address = entry.get("pairAddress")
        creation_timestamp = entry.get("pairCreatedAt")

        # Get first call data from database concurrently
        first_call_task = asyncio.create_task(get_first_call(address))

        # Start ATH fetch in parallel with order status and first call
        ath_task = None
        if pair_address:
            ath_task = asyncio.create_task(get_all_time_high(session, pair_address, creation_timestamp))

        # Get order status for initial embed
        order_status = await order_status_task
        
        # Initial embed with placeholder for ATH
        initial_embed = create_token_embed(entry, address, order_status)
        if not initial_embed:
            logger.error(f"Failed to create embed for {address}")
            return

        # Send initial response
        response = await message.reply(
            content=create_header_message(entry),
            embed=initial_embed,
            view=CopyAddressView(address),
            mention_author=True
        )

        # Wait for remaining async tasks to complete
        first_call_data = await first_call_task

        # If this is the first call, store it
        if not first_call_data:
            # Store first call information
            user_id = message.author.id
            user_name = message.author.display_name
            await store_first_call(address, user_id, user_name, current_fdv, current_price)

            # Update first call data for consistent handling
            first_call_data = {
                'user_id': user_id,
                'user_name': user_name,
                'initial_fdv': current_fdv,
                'initial_price': current_price,
                'call_timestamp': datetime.now(),
                'is_first_call': True
            }

        # Get embed dict for updates
        embed_dict = initial_embed.to_dict()

        # Update embed with first call information - updated footer
        embed_dict = update_first_call_in_embed(
            embed_dict,
            first_call_data,
            current_price,
            message.author
        )

        # If we have ATH task running, wait for it and update
        if ath_task:
            # Await ATH result
            ath_price, ath_timestamp = await ath_task

            # Update ATH in embed
            embed_dict = update_ath_in_embed(
                embed_dict, 
                ath_price, 
                ath_timestamp, 
                current_price, 
                current_fdv
            )

        # Update the message with the final embed
        await response.edit(embed=discord.Embed.from_dict(embed_dict))

        # Record processing time for metrics
        processing_time = datetime.now().timestamp() - start_time
        logger.debug(f"Token {address} processed in {processing_time:.2f}s")

    except Exception as e:
        logger.error(f"Processing error for {address}: {e}")