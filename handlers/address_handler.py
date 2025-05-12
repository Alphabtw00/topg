# handlers/address_processor.py
"""
Solana address detection and processing - Optimized
"""
import asyncio
import discord
from datetime import datetime

from ui.embeds import create_token_embed, create_header_message, update_ath_in_embed, update_first_call_in_embed, update_dex_in_embed
from ui.views import CopyAddressView
from utils.logger import get_logger
from handlers.mysql_handler import get_first_call, store_first_call
from urllib.parse import quote
from config import MAX_ITEMS_PER_MESSAGE


logger = get_logger()

message_semaphore = asyncio.Semaphore(MAX_ITEMS_PER_MESSAGE)


async def process_addresses(message: discord.Message, addresses, bot):
    """
    Process a set of Solana addresses from a message in the most efficient way

    Args:
        message: Discord message
        addresses: Set of addresses to process
        bot: Bot client instance
    """
    # If no addresses, return immediately
    if not addresses:
        return
    
    batch = list(addresses)[:MAX_ITEMS_PER_MESSAGE]
    
    # Use the service provider
    addr_map = await bot.services.dexscreener.get_token_info(batch)

    if not addr_map:
        return
    
    tasks = []
    for addr in batch:
        if addr in addr_map:
            tasks.append(process_token_with_semaphore(
                message, addr_map[addr], addr, message_semaphore, bot
            ))
    
    # Execute all tasks (they will be limited by the semaphore)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def process_token_with_semaphore(message, entry, address, semaphore, bot):
    """
    Process a token with semaphore control
    
    Args:
        message: Discord message
        entry: Token data
        address: Token address
        semaphore: Semaphore for concurrency control
        bot: Bot client instance
    """
    async with semaphore:
        try:
            # Process token entry
            await process_token_entry(message, entry, address, bot)
        except Exception as e:
            logger.error(f"Token processing error {address}: {e}")

async def process_tickers(message, tickers, bot):
    """
    Process a list of ticker symbols with rate limiting
    
    Args:
        message: Discord message
        tickers: List of ticker symbols
        bot: Bot client instance
    """
    # Create tasks with semaphore control
    tasks = []
    for ticker in tickers:
        task = process_ticker(message, ticker, message_semaphore, bot)
        tasks.append(task)
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def process_ticker(message, ticker, semaphore, bot):
    """
    Process a single ticker symbol with semaphore control
    
    Args:
        message: Discord message
        ticker: Ticker symbol
        semaphore: Semaphore for concurrency control
        bot: Bot client instance
    """
    async with semaphore:
        try:
            # Clean ticker
            ticker_clean = ticker.strip()
            if not ticker_clean:
                return
            
            # Use a shorter timeout and caching for ticker searches
            pair = await asyncio.wait_for(
                bot.services.dexscreener.search_token(quote(ticker_clean)),
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
            await process_token_entry(message, pair, address, bot)
        
        except asyncio.TimeoutError:
            logger.warning(f"Ticker search timed out for ${ticker}")
        except Exception as e:
            logger.error(f"Ticker processing error ${ticker}: {e}")

async def process_token_entry(message: discord.Message, entry: dict, address: str, bot):
    """
    Process a token entry and send response to Discord
    
    Args:
        message: Discord message
        entry: Token data
        address: Token address
        bot: Bot client instance
    """
    start_time = datetime.now().timestamp()
    try:
        # Extract the guild ID
        guild_id = message.guild.id if message.guild else 0
        
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
        
        tasks["order_status"] = asyncio.create_task(bot.services.dexscreener.get_order_status(address))
        # Now get first call data for specific guild
        tasks["first_call"] = asyncio.create_task(get_first_call(address, guild_id))
        
        if address:
            tasks["ath"] = asyncio.create_task(
                bot.services.mobula.get_all_time_high(address, creation_timestamp, chain_id)
            )

        # Use a short timeout for auxiliary data to keep responses fast
        completed, pending = await asyncio.wait(tasks.values(), timeout=10)
        
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
                    # Store with guild_id, channel_id, and message_id
                    user_id = message.author.id
                    user_name = message.author.display_name
                    channel_id = message.channel.id
                    message_id = str(message.id)
                    
                    await store_first_call(
                        address, guild_id, user_id, user_name, 
                        current_fdv, current_price, channel_id, message_id
                    )
                    
                    first_call_data = {
                        'user_id': user_id,
                        'user_name': user_name,
                        'initial_fdv': current_fdv,
                        'initial_price': current_price,
                        'call_timestamp': datetime.now(),
                        'guild_id': guild_id,
                        'channel_id': channel_id,
                        'message_id': message_id,
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