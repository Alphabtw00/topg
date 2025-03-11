"""
Solana address detection and processing
"""
import asyncio
import discord
from datetime import datetime
from api.dexscreener import get_token_info, get_order_status
from api.mobula import get_all_time_high
from ui.embeds import create_token_embed, create_header_message, update_ath_in_embed
from ui.views import CopyAddressView
from utils.logger import get_logger
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
    # Process addresses in chunks to avoid URL length limits
    for chunk in [list(addresses)[i:i+5] for i in range(0, len(addresses), 5)]:
        addr_map = await get_token_info(session, chunk)
        
        if not addr_map:
            continue
        
        # Process each address in the chunk
        tasks = []
        for addr in chunk:
            addr_lower = addr.lower()
            if addr_lower in addr_map:
                tasks.append(
                    asyncio.create_task(
                        process_address_with_semaphore(message, session, addr_map[addr_lower], addr)
                    )
                )
        
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
        # Start all API calls concurrently
        order_status_task = asyncio.create_task(get_order_status(session, address))
        
        # Initial embed with "Fetching..." for ATH
        initial_embed = create_token_embed(entry, address, "Fetching...")
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
        
        # Get core data for later use
        pair_address = entry.get("pairAddress")
        creation_timestamp = entry.get("pairCreatedAt")
        current_price = float(entry.get("priceUsd", 0))
        current_fdv = float(entry.get("fdv", 0))
        
        # Start ATH fetch in parallel with order status
        ath_task = None
        if pair_address:
            ath_task = asyncio.create_task(get_all_time_high(session, pair_address, creation_timestamp))
        
        # Wait for order status to complete
        order_status = await order_status_task
        
        # Update embed with order status first
        embed_dict = initial_embed.to_dict()
        
        # Update footer with order status
        footer_text = embed_dict.get("footer", {}).get("text", "")
        footer_parts = footer_text.split(" • ")
        for i, part in enumerate(footer_parts):
            if "Dex" in part or "Fetching" in part:
                footer_parts[i] = order_status
                break
        else:
            footer_parts.append(order_status)
        
        embed_dict["footer"] = {"text": " • ".join(footer_parts)}
        
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