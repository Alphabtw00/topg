"""
Discord embed creation for different types of data
"""
import discord
import asyncio
import dateutil.parser as date_parse
import re
from datetime import datetime
from typing import List, Dict, Optional, Any
from urllib.parse import quote
from config import TWITTER_SEARCH_URL, TRADING_PLATFORMS, VERIFIED_EMOJI
from utils.formatters import (
    format_value, format_date, format_size, 
    relative_time, get_color_from_change, score_bar, clean_html,
    format_metrics, proxy_url, format_category
)
from utils.helper import safe_add_field, fetch_token_metadata_from_uri, get_token_metadata_and_links, calculate_mc_range
from utils.logger import get_logger
from repository.truth_repo import get_guild_settings as get_truth_settings
from repository.migration_tracker_repo import get_guild_settings as get_migration_settings
from repository.about_to_graduate_repo import get_guild_settings as get_graduate_settings
from repository.dex_tracker_repo import get_guild_settings as get_dex_settings


logger = get_logger()

def create_token_embed(entry: dict, address: str, order_status: str) -> discord.Embed:
    """
    Create an embed for token information
    
    Args:
        entry: Token data
        address: Token address
        order_status: Order status string
        
    Returns:
        discord.Embed: Formatted embed
    """
    try:
        # EXTRACT ALL NESTED DATA ONCE - FASTEST APPROACH
        price_data = entry.get("priceChange", {})
        volume_data = entry.get("volume", {})
        txns_data = entry.get("txns", {}).get("m5", {})
        base_token = entry.get("baseToken", {})
        info_data = entry.get("info", {})
        liquidity_data = entry.get("liquidity", {})
        
        # Now use direct variables - no more nested .get() calls
        change = float(price_data.get("m5", 0))
        current_price = float(entry.get("priceUsd", 0))
        current_fdv = float(entry.get("fdv", 0))
        liquidity = float(liquidity_data.get("usd", 0))
        volume_5m = volume_data.get("m5", 0)
        buys = txns_data.get("buys", 0)
        sells = txns_data.get("sells", 0)
        pair_created_at = entry.get("pairCreatedAt")
        symbol = base_token.get("symbol", "")
        
        # Pre-format expensive operations once
        fdv_str = format_value(current_fdv)
        price_str = format_value(current_price)
        liquidity_str = format_value(liquidity)
        volume_str = format_value(volume_5m)
        change_str = format_value(change)
        buys_str = format_value(buys)
        sells_str = format_value(sells)
        
        # Create embed
        embed = discord.Embed(color=get_color_from_change(change))
        
        # Add fields with pre-formatted strings
        embed.add_field(name="💰 FDV", value=f"**`${fdv_str}`**", inline=True)
        embed.add_field(name="💵 USD Price", value=f"**`${price_str}`**", inline=True)
        embed.add_field(name="💧 Liquidity", value=f"**`${liquidity_str}`**", inline=True)
        embed.add_field(name="🏆 ATH", value="**`N/A`**", inline=True)
        
        # Direct emoji assignment
        emoji = "📈" if change >= 0 else "📉"
        embed.add_field(name="📊 5m Volume", value=f"**`${volume_str}`**", inline=True)
        embed.add_field(name=f"{emoji} 5m Change", value=f"**`{change_str}%`**", inline=True)
        
        embed.add_field(
            name="🔄 5m Transactions",
            value=f"🟢 **`{buys_str}`** | 🔴 **`{sells_str}`**",
            inline=False,
        )
        
        # Build links section efficiently
        links_parts = []
        websites = info_data.get("websites", [])
        if websites:
            sites_links = " | ".join(f"[{site.get('label') or 'Website'}]({site['url']})" for site in websites)
            links_parts.append(f"**Websites:** {sites_links}")
        
        socials = info_data.get("socials", [])
        if socials:
            social_links = " | ".join(f"[{soc.get('type', 'Social').title()}]({soc['url']})" for soc in socials)
            links_parts.append(f"**Socials:** {social_links}")
        
        links_parts.append(f"**Chart:** [DEX]({entry.get('url', '#')})")
        
        if links_parts:
            embed.add_field(name="🔗 Links", value="\n".join(links_parts), inline=False)
        
        # Twitter search with pre-encoded symbol
        embed.add_field(
            name="👀 Twitter Search",
            value=f"[CA]({TWITTER_SEARCH_URL.format(query=address)})    |    [TICKER]({TWITTER_SEARCH_URL.format(query=quote(f'${symbol}'))})",
            inline=False
        )
        
        embed.add_field(name="🔑 Contact Address", value=f"`{address}`", inline=False)
        
        # Pre-build trading platforms
        platforms = [f"[{name}]({url.format(address=address)})" 
                     for name, url in TRADING_PLATFORMS.items()]
        embed.add_field(name="💱 Trade On", value=" | ".join(platforms), inline=False)
        
        # Set optional fields
        banner = info_data.get("header")
        if banner:
            embed.set_image(url=banner)
        
        if pair_created_at:
            embed.set_footer(text=f"🕒 {relative_time(pair_created_at, include_ago=True)}")
        
        img = info_data.get("imageUrl")
        if img:
            embed.set_thumbnail(url=img)
            
        return embed
        
    except Exception as e:
        logger.error(f"Embed creation error: {e}")
        return None

def create_header_message(entry: dict) -> str:
    """
    Create a header message for token information
    
    Args:
        entry: Token data
        
    Returns:
        str: Formatted header message
    """
    try:
        base = entry["baseToken"]
        quote = entry.get("quoteToken", {})
        market_cap = format_value(entry.get("marketCap", 0)).replace("$", "")
        chain = entry.get("chainId", "N/A").upper()
        dex = entry.get("dexId", "N/A").title()
        symbol_pair = f"${base['symbol']}/{quote.get('symbol', '')}" if quote else base["symbol"]
        chain_dex = f"({chain} @ {dex})" if chain != "N/A" and dex != "N/A" else ""
        return f"✨ [**{base['name']}**]({entry.get('url', '#')}) **[${market_cap}]** - **{symbol_pair}** **{chain_dex}**"
    except Exception as e:
        logger.error(f"Header creation error: {e}")
        return "Token Information"

def update_ath_in_embed(embed_dict, ath_price, ath_timestamp, current_price, current_fdv):
    """
    Update the ATH field in an embed dictionary
   
    Args:
        embed_dict: Embed dictionary
        ath_price: All-time high price
        ath_timestamp: All-time high timestamp
        current_price: Current price
        current_fdv: Current fully diluted valuation
       
    Returns:
        dict: Updated embed dictionary
    """
    from utils.formatters import calculate_ath_marketcap
    # Find the ATH field
    for field in embed_dict["fields"]:
        if field["name"] == "🏆 ATH":
            if ath_price and ath_timestamp:
                # Calculate ATH market cap
                ath_mcap = calculate_ath_marketcap(ath_price, current_price, current_fdv)
                
                if ath_mcap:
                    if current_fdv > ath_mcap:
                        field["value"] = f"**`${format_value(current_fdv)}` [Now!]**"
                    else:
                        # Format time ago
                        time_display = relative_time(ath_timestamp, include_ago=True)
                        field["value"] = f"**`${format_value(ath_mcap)}` [{time_display}]**"
                else:
                    field["value"] = "**`N/A`**"
            else:
                field["value"] = "**`N/A`**"
            break
   
    return embed_dict

def update_first_call_in_embed(embed_dict, first_call_data, current_price, current_user):
    """
    Update embed with first call information
    """
    try:
        if not first_call_data:
            return embed_dict
           
        # Extract first call data
        initial_price = float(first_call_data.get('initial_price', 0))
        initial_fdv = float(first_call_data.get('initial_fdv', 0))
        user_name = first_call_data.get('user_name', 'Unknown')
        user_id = first_call_data.get('user_id', 0)
        is_first_call = first_call_data.get('is_first_call', False)
       
        # Calculate price multiple (x)
        price_multiple = 0
        if initial_price > 0:
            price_multiple = current_price / initial_price
           
        # Create first call text
        if is_first_call:
            # This is the first call - current user is the first caller
            first_call_text = f"You're First! @ ${format_value(initial_fdv)}"
            footer_icon_url = "https://s14.gifyu.com/images/bx87h.gif"

        else:
            if price_multiple >= 2:
                first_call_text = f"{user_name} @ ${format_value(initial_fdv)} 🚀{int(price_multiple)}x"
            else:
                first_call_text = f"{user_name} @ ${format_value(initial_fdv)}"
            footer_icon_url = "https://s14.gifyu.com/images/bx87l.gif"
       
        # Get existing footer text if it exists
        existing_footer_text = ""
        if "footer" in embed_dict and "text" in embed_dict["footer"]:
            existing_footer_text = embed_dict["footer"]["text"]
       
        # Combine footer texts
        combined_footer = f"{first_call_text} • {existing_footer_text}" if existing_footer_text else first_call_text
       
        # Update embed footer
        embed_dict["footer"] = {
            "text": combined_footer,
            "icon_url": footer_icon_url
        }
           
        return embed_dict
        
    except Exception as e:
        logger.error(f"Error updating first call in embed: {e}")
        return embed_dict

def update_dex_in_embed(embed_dict: dict, order_status: str) -> dict:
    """
    Update the DEX order status in an embed dictionary
    
    Args:
        embed_dict: Embed dictionary
        order_status: DEX order status string
        
    Returns:
        dict: Updated embed dictionary
    """
    try:
        if not order_status:
            return embed_dict
            
        # Get existing footer text if it exists
        footer_text = embed_dict.get("footer", {}).get("text", "")
        
        # Combine footer texts
        if footer_text:
            footer_text = f"{order_status} • {footer_text}"
        else:
            # No footer yet, just use DEX info
            footer_text = order_status
            
        # Update embed footer
        embed_dict["footer"] = {"text": footer_text}
        
        return embed_dict
    except Exception as e:
        logger.error(f"Error updating DEX status in embed: {e}")
        return embed_dict

def create_dex_tracker_embed(token_data, token_info, token_address, symbol, name ):
    """
    Create a simplified embed for a newly paid DexScreener token
    
    Args:
        token_data: Basic token data from the latest tokens API
        token_info: Detailed token info from the tokens API
        
    Returns:
        discord.Embed: Formatted embed
    """
    try:
        if not token_info:
            return
        
        # Extract token data
        chain_id = token_data.get("chainId", "UNKNOWN").upper()
        description = token_data.get("description", "No description")
        
        # Token icon and header
        icon_url = token_data.get("icon", "")
        header_url = token_data.get("header", "")
        
        fdv = float(token_info.get("fdv", 0))
        
        # Create embed with brand color
        embed = discord.Embed(
            title=f"<a:cashbag:1392650510879952926> DEX PAID FOR: {name} (${symbol})",
            url=f"https://dexscreener.com/sol/{token_address}",
            description=clean_html(description),
            color=0xFF5C77,  # DexScreener red
            timestamp=datetime.now()
        )
        
        # Add market cap (FDV)
        embed.add_field(
            name="💰 Market Cap",
            value=f"**`${format_value(fdv)}`**",
            inline=False
        )
        
        # Add links
        links = token_data.get("links", [])
        
        link_text = []
        website = ""
        twitter = ""
        
        for link in links:
            link_type = link.get("type", "")
            link_label = link.get("label", "")
            link_url = link.get("url", "")
            
            if not link_url:
                continue
                
            if link_type == "twitter" or "twitter" in link_url or "x.com" in link_url:
                twitter = link_url
                link_text.append(f"[Twitter]({link_url})")
            elif link_label == "Website" or not link_type:
                website = link_url
                link_text.append(f"[Website]({link_url})")
            else:
                link_text.append(f"[{link_label or link_type.capitalize()}]({link_url})")
        
        if link_text:
            embed.add_field(name="🔗 Links", value=" | ".join(link_text), inline=False)
        
        # Add contract info
        embed.add_field(
            name=f"",
            value=f"```{token_address}```",
            inline=False
        )
        
        # Set thumbnail and images
        if icon_url:
            embed.set_thumbnail(url=icon_url)
            
        if header_url:
            embed.set_image(url=header_url)
        
        platforms = [f"[{name}]({url.format(address=token_address)})" 
                     for name, url in TRADING_PLATFORMS.items()]
        embed.add_field(name="💱 Trade On", value=" | ".join(platforms), inline=False)
        
        # Set footer with logo and timestamp
        embed.set_footer(
            text="Dex Tracker",
            icon_url="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSPVUi95mpqU3Q-UQZ7Ge82bhGABTToQQ3cLg&s"
        )
        
        return embed
        
    except Exception as e:
        from utils.logger import get_logger
        logger = get_logger()
        logger.error(f"Error creating DexScreener tracker embed: {e}")
        return None

async def create_migration_tracker_embed(dex_data, mobula_data, bitquery_data, token_address):
    """Create optimized migration tracker embed with multiple data sources"""
    try:
        # Initialize defaults
        name = "Unknown"
        symbol = "Unknown"
        market_cap = 0
        volume_5m = 0
        price_change_5m = 0
        image_url = None
        header_url = None
        links = []
        
        # Data source priority: DexScreener > Mobula > BitQuery
        if dex_data:
            # Extract DexScreener data
            name = dex_data.get('baseToken', {}).get('name', 'Unknown')
            symbol = dex_data.get('baseToken', {}).get('symbol', 'Unknown')
            market_cap = dex_data.get('fdv', 0)
            volume_5m = dex_data.get('volume', {}).get('m5', 0)
            price_change_5m = dex_data.get('priceChange', {}).get('m5', 0)
            
            # DexScreener images/links
            info = dex_data.get('info', {})
            image_url = info.get('imageUrl')
            header_url = info.get('header')
            links = info.get('websites', []) + info.get('socials', [])
            
            # Use Mobula image if DexScreener doesn't have one
            if not image_url and mobula_data:
                image_url = mobula_data.get('data', {}).get('logo')
                # If missing volume/price change, use Mobula data
                if not volume_5m:
                    volume_5m = mobula_data.get('data', {}).get('volume', 0)
                if not price_change_5m:
                    price_change_5m = mobula_data.get('data', {}).get('price_change_1h', 0)
            
        elif mobula_data:
            # Use Mobula data
            data = mobula_data.get('data', {})
            name = data.get('name', 'Unknown')
            symbol = data.get('symbol', 'Unknown')
            market_cap = data.get('market_cap', 0)
            volume_5m = data.get('volume', 0)
            price_change_5m = data.get('price_change_1h', 0)
            image_url = data.get('logo')
            
        elif bitquery_data:
            # Extract BitQuery data
            solana_data = bitquery_data.get("Solana", {})
            token_data = solana_data.get("DEXTradeByTokens", [])
            supply_data = solana_data.get("TokenSupplyUpdates", [])
            
            if token_data:
                trade_data = token_data[0]["Trade"]
                currency = trade_data["Currency"]
                
                name = currency.get("Name", "Unknown")
                symbol = currency.get("Symbol", "Unknown")
                
                # Calculate market cap
                price = trade_data.get("PriceInUSD", 0)
                if supply_data and price:
                    supply = float(supply_data[0]["TokenSupplyUpdate"]["PostBalance"])
                    market_cap = supply * price
                
                # Get dev address and URI
                dev_address = trade_data.get("Account", {}).get("Owner")
                if dev_address:
                     links.append({"label": "Dev", "url": f"https://solscan.io/account/{dev_address}"})
                
                uri = currency.get("Uri")                   
                if uri:
                    image_url, metadata_links = await get_token_metadata_and_links(uri)
                    links.extend(metadata_links)                    
        else:
            return None
        
        # Build embed
        embed = discord.Embed(
            title=f"<a:upvote:1380578405757489294> {name} (${symbol}) Graduated!",
            color=0x00ff00,
            url=f"https://dexscreener.com/sol/{token_address}",
            timestamp=datetime.now()
        )

        if header_url:
            embed.set_image(url=header_url)
        
        if image_url:
            embed.set_thumbnail(url=image_url)

        # Add market cap
        if market_cap:
            embed.add_field(
                name="💰 Market Cap (3s ago)",
                value=f"**`${format_value(market_cap)}`**",
                inline=True
            )

        # Add stats if available
        if volume_5m or price_change_5m:
            change_emoji = "🚀" if price_change_5m > 0 else "🔻"
            time_suffix = "(5m)" if dex_data else "(1h)" if mobula_data else ""
            
            stats_parts = []
            if volume_5m:
                stats_parts.append(f"🔥 VOL: **`{format_value(volume_5m)}`**")
            if price_change_5m:
                stats_parts.append(f"{change_emoji} PC: **`{format_value(price_change_5m)}%`** {time_suffix}")
            
            if stats_parts:
                embed.add_field(
                    name="📊 Stats",
                    value="\n".join(stats_parts),
                    inline=True
                )
       
        # Add links if available
        if links:
            links_text = []
            for link in links:
                label = link.get('label') or link.get('type', 'Link')
                url = link.get('url')
                if url:
                    links_text.append(f"[{label}]({url})")
           
            if links_text:
                embed.add_field(
                    name="🔗 Links",
                    value=" • ".join(links_text),
                    inline=False
                )

        embed.add_field(
            name="💸 Contract",
            value=f"```{token_address}```",
            inline=False
        )
        
        # Add trading platforms
        platforms = [f"[{name}]({url.format(address=token_address)})" 
                    for name, url in TRADING_PLATFORMS.items()]
        embed.add_field(
            name="💱 Trade On", 
            value=" | ".join(platforms), 
            inline=False
        )
        
        embed.set_footer(text="Migration Tracker", icon_url="https://s14.gifyu.com/images/bxicv.gif")
        return embed
       
    except Exception as e:
        logger.error(f"Error creating migration embed: {e}")
        return None

async def create_about_to_graduate_embed(pool_data: dict, token_address: str):
    """Create embed for graduation alert using reusable metadata method"""
    try:
        # Extract pool data structure
        pool = pool_data.get("Pool", {})
        market_data = pool.get("Market", {})
        base_currency = market_data.get("BaseCurrency", {})
        base_data = pool.get("Base", {})
        quote_data = pool.get("Quote", {})
        transaction = pool_data.get("Transaction", {})
        
        # Extract token data
        name = base_currency.get('Name', 'Unknown Token')
        symbol = base_currency.get('Symbol', 'Unknown')
        uri = base_currency.get('Uri', '')
        dev_address = transaction.get('Signer', '')
        
        # Calculate market cap
        market_cap = 0
        try:
            base_amount = float(base_data.get('PostAmount', 0))
            quote_amount_usd = float(quote_data.get('PostAmountInUSD', 0))
            
            if base_amount > 0 and quote_amount_usd > 0:
                market_cap = 1_000_000_000 * (quote_amount_usd / base_amount)
        except (ValueError, ZeroDivisionError, TypeError):
            pass
        
        # Create embed
        embed = discord.Embed(
            title=f"<a:right_arrow:1380903999598887023> {name} (${symbol}) - About to Graduate",
            color=0xFFFFFF,
            url=f"https://dexscreener.com/sol/{token_address}",
            timestamp=datetime.now()
        )
        
        # Get metadata and links using reusable method
        image_url, links = await get_token_metadata_and_links(uri, dev_address)
        
        # Add thumbnail
        if image_url:
            embed.set_thumbnail(url=image_url)
        
        # Add market cap
        if market_cap > 0:
            embed.add_field(
                name="💰 Market Cap (3s ago)",
                value=f"**`${format_value(market_cap)}`**",
                inline=True
            )
        
        # Add links if available
        if links:
            links_text = [f"[{link['label']}]({link['url']})" for link in links]
            embed.add_field(
                name="🔗 Links",
                value=" | ".join(links_text),
                inline=False
            )
        
        # Add contract address
        embed.add_field(
            name="💸 Contract Address",
            value=f"```{token_address}```",
            inline=False
        )
        
                
        platforms = [f"[{name}]({url.format(address=token_address)})" 
                    for name, url in TRADING_PLATFORMS.items()]
        embed.add_field(
            name="💱 Trade On", 
            value=" | ".join(platforms), 
            inline=False
        )
        
        embed.set_footer(
            text="Migration Tracker",
            icon_url="https://s14.gifyu.com/images/bxicv.gif"
        )
        
        return embed
        
    except Exception as e:
        logger.error(f"Error creating graduation alert embed: {e}")
        return None
    
async def create_wallet_finder_embed(
    token_info: Dict,
    matching_holders: List[Dict],
    target_mc: float,
    cutoff_value: Optional[float],
    buy_amount_filter: Optional[Dict[str, Any]],
    market_cap_input: str,
    cutoff_input: Optional[str],
    buy_amount_input: Optional[str],
    page: int = 1,
    total_pages: int = 1
) -> Optional[discord.Embed]:
    """
    Create embed for wallet finder results
    
    Args:
        token_info: Token information from BitQuery
        matching_holders: List of holders for current page
        target_mc: Target market cap value
        cutoff_value: Optional cutoff value
        buy_amount_filter: Optional buy amount filter dict
        market_cap_input: Original market cap input
        cutoff_input: Original cutoff input
        buy_amount_input: Original buy amount input
        page: Current page number
        total_pages: Total number of pages
        
    Returns:
        Discord embed or None
    """
    try:
        if not matching_holders:
            return None
        
        # Extract token details
        token_name = token_info.get("Name", "Unknown")
        token_symbol = token_info.get("Symbol", "Unknown")
        token_uri = token_info.get("Uri", "")
        
        # Create embed
        embed = discord.Embed(
            color=0x2ECC71,
            timestamp=datetime.now()
        )
        
        metadata = await fetch_token_metadata_from_uri(token_uri)
        # Add thumbnail from metadata
        if metadata and metadata.get('image'):
            embed.set_author(
                name=f"{token_name} (${token_symbol}) • Page {page}/{total_pages}",
                icon_url=metadata['image']
            )
            embed.set_thumbnail(url=metadata['image'])
        else:
            embed.title = f"{token_name} (${token_symbol}) • Page {page}/{total_pages}"
            

        # Build description
        description_parts = []
        
        # Market cap criteria
        if cutoff_value:
            min_mc, max_mc = calculate_mc_range(target_mc, cutoff_value)
            description_parts.append(f"# <a:cash:1391203587102867507> Market Cap Range: {format_value(min_mc)} - {format_value(max_mc)}")
        else:
            description_parts.append(f"# <a:cash:1391203587102867507> Target Market Cap: {format_value(target_mc)}")
        
        # Buy amount criteria if provided
        if buy_amount_filter:
            currency_symbol = "SOL" if buy_amount_filter["currency"] == "SOL" else "$"
            amount_str = f"{buy_amount_filter['amount']:.2f}" if buy_amount_filter['amount'] % 1 != 0 else f"{int(buy_amount_filter['amount'])}"
            if buy_amount_filter["currency"] == "SOL":
                description_parts.append(f"# 🪙 Buy Amount Filter: {amount_str} {currency_symbol}")
            else:
                description_parts.append(f"# 🪙 Buy Amount Filter: {currency_symbol}{amount_str}")
        
        description_parts.append("")  # Empty line
        
        # Add holder information
        for i, holder in enumerate(matching_holders):
            wallet_address = holder["wallet"]
            total_sol = holder["total_sol"]
            total_usd = holder["total_usd"]
            buy_count = holder["buy_count"]
            avg_mc = holder["avg_mc"]
            
            # Calculate wallet number (accounting for pagination)
            wallet_number = (page - 1) * 10 + i + 1
            
            # Format wallet info
            wallet_text = f"## Wallet #{wallet_number}\n"
            wallet_text += f"**Wallet:** **`{wallet_address}`**\n"
            wallet_text += f"**Average MC:** **`${format_value(avg_mc)}`**\n"
            wallet_text += f"**Buy Volume:** **`{total_sol:.2f} SOL (${total_usd:,.2f})`**\n"
            wallet_text += f"**Total Buys:** **`{buy_count}`**\n"
            
            description_parts.append(wallet_text)
        
        # Add note about accuracy
        description_parts.append("")
        description_parts.append(
            "**Note:** Average market cap shown in trading charts and other platforms may differ slightly from our calculations. "
            "For more precise wallet matching, consider using the buy amount filter to narrow down results."
        )
        
        # Join all parts
        embed.description = "\n".join(description_parts)
        
        # Add footer
        embed.set_footer(
            text="Wallet Finder",
            icon_url="https://media1.tenor.com/m/Zu-MORJkq7IAAAAC/dollar-sign-money.gif"
        )
        
        return embed
        
    except Exception as e:
        logger.error(f"Error creating wallet finder embed: {e}")
        return None
    
def create_github_analysis_embed(repo_info, analysis, start_time, interaction):
    """
    Create an enhanced embed for GitHub repository analysis.
    
    Args:
        repo_info: Repository information dictionary
        analysis: Analysis data with scores and review information
        start_time: Analysis start time for tracking performance
        interaction: Discord interaction object
        
    Returns:
        discord.Embed: Formatted embed with comprehensive analysis
    """
    # Core metrics - most important data
    legitimacy_score = analysis.get("legitimacyScore", 0)
    trust_score = analysis.get("trustScore", 0)
    detailed_scores = analysis.get("detailedScores", {})
    code_review = analysis.get("codeReview", {})
    ai_analysis = code_review.get("aiAnalysis", {})
    
    # Get investment rating
    ranking = code_review.get("investmentRanking", {})
    rating = ranking.get("rating", "Unknown")
    confidence = ranking.get("confidence", 0)
    
    # Calculate technical quality average
    code_quality = detailed_scores.get("codeQuality", 0)
    project_structure = detailed_scores.get("projectStructure", 0)
    implementation = detailed_scores.get("implementation", 0)
    documentation = detailed_scores.get("documentation", 0)
    
    # Get verdict from the analysis - already calculated in analyzer
    verdict_data = analysis.get("verdict", {})
    if not verdict_data:
        # Fallback if verdict wasn't pre-calculated (shouldn't happen)
        verdict_data = {
            "color": 0x00FF00,
            "verdict": "INVESTMENT RECOMMENDED",
            "emoji": "✅",
            "investment_advice": "Appears to be a solid project with good technical foundation"
        }
        
    embed_color = verdict_data["color"]
    verdict = verdict_data["verdict"]
    verdict_emoji = verdict_data["emoji"]
    investment_advice = verdict_data["investment_advice"]
    
    # Format repository name
    repo_name = repo_info["name"]
    owner = repo_info["owner"]
    
    # Create main embed
    embed = discord.Embed(
        title=f"GitHub Analysis: {owner}/{repo_name}",                   
        url=f"https://github.com/{owner}/{repo_name}",
        color=embed_color,
        timestamp=datetime.now()
    )
    
    # GitHub logo
    embed.set_author(
        name="GitHub Repository Analyzer", 
        icon_url="https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png"
    )

    # Owner avatar
    embed.set_thumbnail(url=repo_info["owner_avatar"])
    
    # Top summary section with verdict
    # Check for LARP indicators and critical path issues
    larp_indicators = code_review.get("larpIndicators", [])
    critical_path = code_review.get("criticalPath", [])
    
    warning_text = ""
    if larp_indicators:
        warning_text += f"⚠️ **IMPORTANT:** This project may have misleading claims.\n"
    
    if critical_path:
        if warning_text:
            warning_text += "\n"
        warning_text += f"⚠️ **NOTE:** Critical implementation issues detected.\n"
    
    
    # Get the project summary from the analysis
    summary = code_review.get("projectSummary", "")

    embed.description = (
        f"## {verdict_emoji} VERDICT: {verdict} {verdict_emoji}\n"
        f"### {investment_advice}\n"
        f"{warning_text}"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{summary}\n"
    )
                
    # --- SCORE SECTION (MOST IMPORTANT) ---

    # Overall assessment
    # Include implementation quality if available
    ai_score = ai_analysis.get('score', 0)
    impl_quality = ai_analysis.get('implementationQuality', '')
    ai_score_text = f"**AI Implementation:** {score_bar(ai_score)} `{ai_score}%`"
    if impl_quality and impl_quality != "N/A":
        ai_score_text += f" - `{impl_quality}`"
    

    embed.add_field(
        name="🛡️ Overall Assessment",
        value=(
            f"**Legitimacy Score:** {score_bar(legitimacy_score)} `{legitimacy_score}%`\n"
            f"**Trust Score:** {score_bar(trust_score)} `{trust_score}%`\n"
            f"{ai_score_text}\n"
        ),
        inline=False
    )
    
    # Detailed scores
    embed.add_field(
        name="📚 Technical Quality",
        value=(
            f"**Code Quality:** {score_bar(code_quality*4)} `{code_quality}/25`\n"
            f"**Project Structure:** {score_bar(project_structure*4)} `{project_structure}/25`\n"
            f"**Implementation:** {score_bar(implementation*4)} `{implementation}/25`\n"
            f"**Documentation:** {score_bar(documentation*4)} `{documentation}/25`"
        ),
        inline=False
    )

    # Investment assessment 
    rating_emoji = {
        "Strong Buy": "🟢", 
        "Buy": "🟢",
        "High": "🟢",
        "Medium": "🟡",
        "Medium-High": "🟡",
        "Hold": "🟡", 
        "Sell": "🔴",
        "Strong Sell": "🔴",
        "Low": "🔴"
    }.get(rating, "⚪")
    
    if not rating:
        rating = "Unknown"
    
    embed.add_field(
        name="💰 Investment Rating",
        value=(
            f"**Rating:** {rating_emoji} `{rating}`\n"
            f"**Confidence in rating:** {score_bar(confidence)} `{confidence}%`\n"
        ),
        inline=False
    )

    # Enhanced repo info with more details
    created_date = format_date(repo_info.get("created_at", "Unknown"))
    updated_date = format_date(repo_info.get("updated_at", "Unknown"))
    size = format_size(repo_info.get("size", 0))        
    language = repo_info.get("language", "Unknown")
    license_info = repo_info.get("license", "No license")

    # Group basic repository details under "General Info"
    general_info = "\n".join([
        f"**Primary Language:** `{language}`",
        f"**License:** `{license_info}`",
        f"**Size:** `{size}`",
        f"**Created:** `{created_date}`",
        f"**Updated:** `{updated_date}`",
    ])

    stars = repo_info.get("stars", 0)
    forks = repo_info.get("forks", 0)
    watchers = repo_info.get("watchers", 0)
    open_issues = repo_info.get("open_issues", 0)

    # Group engagement metrics under "Community Stats"
    community_stats = "\n".join([
        f"**Owner:** [{owner}](https://github.com/{owner})",
        f"**Stars:** `{stars:,}`",
        f"**Forks:** `{forks:,}`",
        f"**Watchers:** `{watchers:,}`",
        f"**Open Issues:** `{open_issues:,}`",
    ])

    # Add two inline fields to the embed with the new headings
    embed.add_field(
        name="📁 Repo Info",
        value=general_info,
        inline=True
    )
    embed.add_field(
        name="⭐ Community Stats",
        value=community_stats,
        inline=True
    )
            
    # Red flags
    red_flags = code_review.get("redFlags", [])
    if red_flags:
        flags_formatted = "\n".join(f"📉 {flag}" for flag in red_flags[:3])
        embed.add_field(
            name="🚩 Security Concerns",
            value=flags_formatted if flags_formatted else "No significant issues detected",
            inline=False
        )
    else:
        embed.add_field(
            name="🚩 Security Concerns",
            value="No significant issues detected",
            inline=False
        )
    
    def format_with_markers(items):
        """
        Format items list with positive/negative markers
        
        Args:
            items: List of items to format
            
        Returns:
            Formatted text with appropriate emojis and 
            a boolean indicating if a marker was found
        """
        improvement_markers = ["Areas needing improvement:", "Areas for improvement:", "Missing:"]
        marker_index = -1
        has_marker = False
        
        for marker in improvement_markers:
            if marker in items:
                marker_index = items.index(marker)
                has_marker = True
                break
        
        formatted_text = ""
        if has_marker:
            # Format with positive/negative markers
            positive_items = items[:marker_index]
            negative_items = items[marker_index+1:]  # Skip the marker itself
            
            # Add up to 2 positive items
            if positive_items:
                formatted_text += "\n".join(f"✅ {item}" for item in positive_items[:2])
            
            # Add up to 2 negative items
            if negative_items:
                if formatted_text:
                    formatted_text += "\n"
                formatted_text += "\n".join(f"⚠️ {item}" for item in negative_items[:2])
        
        return formatted_text, has_marker

    # Process insights section
    reasoning = ranking.get("reasoning", [])
    if reasoning:
        # Use the helper method for formatting
        insights_text, has_marker = format_with_markers(reasoning)
        
        # If no marker was found, use neutral emoji formatting
        if not has_marker:
            insights_text = "\n".join(f"📍 {item}" for item in reasoning[:4])
        
        embed.add_field(
            name="⚡ Key Insights",
            value=insights_text if insights_text else "No insights available",
            inline=False
        )

    # Process AI implementation section
    if ai_analysis.get("hasAI", False):
        ai_components = ai_analysis.get("components", [])
        ai_concerns = ai_analysis.get("concerns", [])
        
        if ai_components:
            # Use the helper method for formatting
            ai_text, has_marker = format_with_markers(ai_components)
            
            # If no marker was found, use neutral emoji formatting
            if not has_marker:
                ai_text = "\n".join(f"🔹 {item}" for item in ai_components[:4])
            
            # Add concerns with neutral emoji
            if ai_concerns:
                if ai_text:
                    ai_text += "\n"
                ai_text += "\n".join(f"🔹 {concern}" for concern in ai_concerns[:2])
            
            embed.add_field(
                name="🤖 AI Implementation",
                value=ai_text if ai_text else "No AI implementation details available",
                inline=False
            )
    
    # Add misleading level warning if it exists and is not "None"
    misleading_level = ai_analysis.get("misleadingLevel")
    if misleading_level and misleading_level.lower() not in ["none", "n/a", ""]:
        embed.add_field(
            name="⚠️ Misleading Assessment",
            value=f"**Level:** `{misleading_level}`",
            inline=False
        )
    
    # Overall Assessment (Expert Opinion)
    overall_assessment = code_review.get("overallAssessment", "")
    if overall_assessment:
        embed.add_field(
            name="🧠 Expert Opinion",
            value=f"> {overall_assessment.replace('\\n', '\\n> ')}",
            inline=False
        )
    
    # Footer
    embed.set_footer(
        text=f"Requested by {interaction.user.display_name} • ⌛Analysis Time: {(datetime.now().timestamp() - start_time):.1f}s", 
        icon_url=interaction.user.display_avatar.url
    )
    
    return embed

def create_website_embed(result, interaction, start_time):
    """Create a comprehensive embed for the website analysis result
    
    Args:
        result: The analysis result dictionary
        interaction: Discord interaction object
        start_time: Timestamp when analysis started
        
    Returns:
        discord.Embed: Formatted embed with all analysis results
    """
    # Extract key data
    url = result.get("url", "")
    domain = result.get("domain", "")
    title = result.get("title", "No title")
    description = result.get("description", "No description")
    
    # Get risk assessment
    risk = result.get("risk_assessment", {})
    risk_level = risk.get("risk_level", "UNKNOWN")
    risk_color = risk.get("color", 0x808080)  # Default gray
    risk_emoji = risk.get("emoji", "❓")
    risk_issues = risk.get("issues", [])
    risk_strengths = risk.get("strengths", [])
    investment_advice = risk.get("investment_advice", "")
    
    # Get scores
    scores = result.get("scores", {})
    overall_score = result.get("legitimacy_score", 0)
    
    # Create the embed
    embed = discord.Embed(
        title=f"Website Analysis: {domain}",
        description=f"{risk_emoji} **Risk Level: {risk_level}** {risk_emoji}\n{investment_advice}\n\n**{title}**\n{description}",
        color=risk_color,
        url=url,
        timestamp=datetime.now()
    )
    
    # Set favicon as thumbnail (will be replaced if we have the actual file)
    favicon_url = result.get("favicon_url")
    if favicon_url:
        if len(favicon_url) < 2000 and favicon_url.startswith(('http://', 'https://')):
            embed.set_thumbnail(url=favicon_url)

    
    # Overall score with visual bar
    embed.add_field(
        name="📊 Overall Score",
        value=f"{score_bar(overall_score)} `{overall_score}/100`",
        inline=False
    )
    
    # Domain info
    domain_info = result.get("domain_info", {})
    domain_age = domain_info.get("age_days", 0)
    domain_created = domain_info.get("creation_date", "Unknown")
    
    embed.add_field(
        name="🌐 Domain",
        value=f"Age: `{domain_age} days`\nCreated: `{domain_created}`",
        inline=True
    )
    
    # SSL info
    ssl_info = result.get("ssl_info", {})
    ssl_status = "✅ Enabled" if ssl_info.get("has_ssl", False) else "❌ Not enabled"
    ssl_expiry = ssl_info.get("expiry", "N/A") if ssl_info.get("has_ssl", False) else "N/A"
    
    embed.add_field(
        name="🔒 Security",
        value=f"SSL: `{ssl_status}`\nExpiry: `{ssl_expiry}`\nScore: `{scores.get('security', 0)}/100`",
        inline=True
    )
    
    # Technology
    tech_stack = result.get("tech_stack", [])
    tech_names = [tech["name"] for tech in tech_stack[:3]]
    tech_text = ", ".join(tech_names) if tech_names else "No technologies detected"
    if len(tech_stack) > 3:
        tech_text += f" (+{len(tech_stack) - 3} more)"
        
    embed.add_field(
        name="💻 Technology",
        value=f"{tech_text}\nScore: `{scores.get('tech', 0)}/100`",
        inline=True
    )
    
    # Blockchain integration
    blockchain_info = result.get("blockchain_info", {})
    has_integration = blockchain_info.get("has_integration", False)
    blockchains = blockchain_info.get("blockchains", [])
    wallet_connections = blockchain_info.get("wallet_connections", [])
    
    if has_integration:
        blockchain_text = "✅ Blockchain integration detected\n"
        if blockchains:
            blockchain_text += f"Chains: `{', '.join(blockchains[:2])}`\n"
        if wallet_connections:
            blockchain_text += f"Wallet: `{wallet_connections[0]}`"
        blockchain_text += f"\nScore: `{scores.get('blockchain', 0)}/100`"
    else:
        blockchain_text = "❌ No blockchain integration detected"
        
    embed.add_field(
        name="⛓️ Blockchain",
        value=blockchain_text,
        inline=True
    )
    
    # Social media
    social_media = result.get("social_media", {})
    platforms = social_media.get("platforms", [])
    
    if platforms:
        social_text = "\n".join([f"- **{p['name']}**" for p in platforms[:3]])
        if len(platforms) > 3:
            social_text += f"\n- *+{len(platforms) - 3} more*"
        social_text += f"\nScore: `{scores.get('social', 0)}/100`"
    else:
        social_text = "No social media links detected"
        
    embed.add_field(
        name="📱 Social Media",
        value=social_text,
        inline=True
    )
    
    # Content & SEO
    content_quality = result.get("content_quality", {})
    seo_info = result.get("seo_info", {})
    
    content_seo_text = (
        f"Word count: `{content_quality.get('word_count', 0)}`\n"
        f"Headings: `{content_quality.get('heading_count', 0)}`\n"
        f"SEO Score: `{seo_info.get('score', 0)}/100`\n"
        f"Content Score: `{scores.get('content', 0)}/100`"
    )
    
    embed.add_field(
        name="📝 Content & SEO",
        value=content_seo_text,
        inline=True
    )
    
    # Add issues and strengths section
    if risk_issues:
        issues_text = "\n".join([f"- {issue}" for issue in risk_issues])
        embed.add_field(
            name="⚠️ Issues Detected",
            value=issues_text,
            inline=False
        )
    
    if risk_strengths:
        strengths_text = "\n".join([f"- {strength}" for strength in risk_strengths])
        embed.add_field(
            name="💪 Strengths",
            value=strengths_text,
            inline=False
        )
    
    # Add performance information
    performance = result.get("performance", {})
    resources = result.get("resources", {})
    
    perf_text = (
        f"Load time: `{performance.get('load_time', 0):.2f}s`\n"
        f"Resources: `{resources.get('total_count', 0)}`\n"
        f"CDN Used: `{'Yes' if resources.get('has_cdn', False) else 'No'}`\n"
        f"Score: `{scores.get('performance', 0)}/100`"
    )
    
    embed.add_field(
        name="⚡ Performance",
        value=perf_text,
        inline=True
    )
    
    # Add template analysis information
    template = result.get("template_analysis", {})
    
    if template.get("is_template", False):
        template_text = (
            f"⚠️ **Template site detected**\n"
            f"Confidence: `{template.get('template_confidence', 0)}%`\n"
        )
        
        if template.get("template_indicators", []):
            indicators = template.get("template_indicators", [])[:2]
            template_text += f"Indicators: `{', '.join(indicators)}`"
    else:
        template_text = "✅ No template patterns detected"
    
    embed.add_field(
        name="🧩 Template Analysis",
        value=template_text,
        inline=True
    )
    
    # Add cache status if available
    cache_text = "🔄 Fresh analysis" if not result.get("cached", False) else "⏱️ Cached result"
    analysis_time_ms = result.get("analysis_time_ms", 0)
    
    embed.add_field(
        name="🔍 Analysis Info",
        value=f"{cache_text}\nTime: `{analysis_time_ms}ms`",
        inline=True
    )

    embed.set_footer(
        text=f"Requested by {interaction.user.display_name} • ⌛Analysis Time: {(datetime.now().timestamp() - start_time):.1f}s", 
        icon_url=interaction.user.display_avatar.url
    )
    
    return embed

async def create_health_embed(bot, user):
    """
    Create a comprehensive health status embed with server and tracking information
    
    Args:
        bot: Bot instance
        user: User who requested health info
        
    Returns:
        discord.Embed: Enhanced health information embed
    """
    
    # Calculate uptime
    uptime = datetime.now() - bot.startup_time
    days, remainder = divmod(uptime.total_seconds(), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Format uptime nicely
    uptime_str = ""
    if days > 0:
        uptime_str += f"{int(days)}d "
    if hours > 0 or days > 0:
        uptime_str += f"{int(hours)}h "
    uptime_str += f"{int(minutes)}m {int(seconds)}s"
    
    # Discord metrics
    latency = round(bot.latency * 1000)  # Convert to ms
    
    # Performance color coding
    if latency < 100:
        color = 0x4CAF50  # Green
    elif latency < 200:
        color = 0xFFC107  # Amber
    else:
        color = 0xF44336  # Red
    
    # Calculate average processing time from recent data only
    current_time = datetime.now().timestamp()
    recent_processing = [t[0] for t in bot.metrics['processing_times']]
    
    avg_time = 0 if not recent_processing else sum(recent_processing) / len(recent_processing)
    
    # Get most used commands
    top_commands = sorted(
        bot.metrics['command_usage'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:3]
    
    total_errors = bot.get_error_count()
    
    # Get top errors
    top_errors = []
    if bot.metrics['errors']:
        top_errors = sorted(
            bot.metrics['errors'].items(),
            key=lambda x: x[1],
            reverse=True
        )

    # Database metrics
    from service.mysql_service import get_db_pool_stats
    db_stats = await get_db_pool_stats()
    
    # Server information
    total_servers = len(bot.guilds)
    total_members = sum(guild.member_count for guild in bot.guilds)
    
    # Get server tracking information
    server_info = []
    guilds_sorted = sorted(bot.guilds, key=lambda x: x.member_count or 0, reverse=True)
    
    for guild in guilds_sorted[:5]:  # Top 5 servers by member count
        # Get tracking status for each service
        try:
            truth_enabled = (await get_truth_settings(guild.id)).get('enabled', False)
            migration_enabled = (await get_migration_settings(guild.id)).get('enabled', False)
            graduate_enabled = (await get_graduate_settings(guild.id)).get('enabled', False)
            dex_enabled = (await get_dex_settings(guild.id)).get('enabled', False)
            
            # Create status indicators
            status_indicators = []
            if truth_enabled:
                status_indicators.append("🟢TS")
            else:
                status_indicators.append("🔴TS")
                
            if migration_enabled:
                status_indicators.append("🟢MG")
            else:
                status_indicators.append("🔴MG")
                
            if graduate_enabled:
                status_indicators.append("🟢AG")
            else:
                status_indicators.append("🔴AG")
                
            if dex_enabled:
                status_indicators.append("🟢DX")
            else:
                status_indicators.append("🔴DX")
            
            status_str = " ".join(status_indicators)
            
            # Truncate server name if too long
            server_name = guild.name[:25] + "..." if len(guild.name) > 25 else guild.name
            member_count = guild.member_count or 0
            
            server_info.append(f"**{server_name}** ({member_count:,}) {status_str}")
            
        except Exception as e:
            # Fallback if tracking status check fails
            server_name = guild.name[:25] + "..." if len(guild.name) > 25 else guild.name
            member_count = guild.member_count or 0
            server_info.append(f"**{server_name}** ({member_count:,}) ❓❓❓❓")
    
    # Create embed
    embed = discord.Embed(
        title="🔍 Bot Health Monitor",
        description=f"Comprehensive status snapshot taken <t:{int(datetime.now().timestamp())}:R>",
        timestamp=datetime.now(),
        color=color
    )
    
    banner = "https://i.imgur.com/fQOYDpO.gif"  # Direct GIF link
    embed.set_image(url=banner)

    # Bot metrics section
    bot_info = (
        f"**Uptime:** {uptime_str}\n"
        f"**Latency:** {latency}ms\n"
        f"**Messages Processed:** {bot.metrics['processed_count']:,}\n"
        f"**Avg. Processing:** {avg_time*1000:.1f}ms\n"
        f"**Total Errors:** {total_errors:,}"
    )
    embed.add_field(name="🤖 Bot Status", value=bot_info, inline=True)
    
    # Database section
    if db_stats:
        db_info = (
            f"**Pool Size:** {db_stats.get('size', 'Unknown')}\n"
            f"**Free:** {db_stats.get('free', 'Unknown')}\n"
            f"**Used:** {db_stats.get('used', 'Unknown')}"
        )
        embed.add_field(name="🗄️ Database", value=db_info, inline=True)
    
    # Server overview section
    server_overview = (
        f"**Total Servers:** {total_servers:,}\n"
        f"**Total Members:** {total_members:,}\n"
        f"**Avg Members/Server:** {total_members//total_servers if total_servers > 0 else 0:,}"
    )
    embed.add_field(name="🌐 Server Overview", value=server_overview, inline=True)
    
    api_latency = ""
    if bot.metrics['api_latency']:
        for endpoint, latencies in sorted(bot.metrics['api_latency'].items()):
            if latencies:
                # Only use recent latencies
                avg_latency = sum(latencies) / (len(latencies))
                api_latency += f"**{endpoint}:** {avg_latency*1000:.0f}ms\n"
        
        if api_latency:
            embed.add_field(name="🌐 API Performance", value=api_latency, inline=False)
            
    
    # Top servers with tracking status
    if server_info:
        servers_text = "\n".join(server_info)
        embed.add_field(
            name="🏆 Top Servers (TS|MG|GR|DX)", 
            value=servers_text, 
            inline=False
        )
    
    # Top errors
    if top_errors:
        error_info = "\n".join([
            f"**{err_key}:** {count:,} times" 
            for err_key, count in top_errors
        ])
        embed.add_field(
            name="⚠️ Top Errors", 
            value=error_info,
            inline=True
        )

    # Command usage section if there are commands used
    if top_commands:
        usage_info = "\n".join([f"**{cmd}:** {count:,} uses" for cmd, count in top_commands])
        embed.add_field(name="📊 Top Commands", value=usage_info, inline=True)
    
    
    # Set footer with timestamp
    embed.set_footer(
        text=f"Requested by {user}", 
        icon_url=user.display_avatar.url
    )
    
    return embed

def create_bundle_embed(data, contract_address):
    """
    Create an embed for bundle distribution analysis
   
    Args:
        data: Bundle analysis data from TrenchBot
        contract_address: Token contract address
       
    Returns:
        discord.Embed: Formatted embed with bundle analysis
    """
   
    # Extract key data
    ticker = data.get("ticker", "Unknown")
    total_bundles = data.get("total_bundles", 0)
    total_percentage_bundled = data.get("total_percentage_bundled", 0)
    total_holding_percentage = data.get("total_holding_percentage", 0)
   

    if total_holding_percentage < 15:
        embed_color = 0x4CAF50  # Green
        status_emoji = "<a:GreenCheck:1380464968335626302>"
    elif total_holding_percentage < 30:
        embed_color = 0xFFC107  # Amber/Yellow
        status_emoji = "<a:Warning:1380467064761749584>"
    elif total_holding_percentage < 50:
        embed_color = 0xFF9800  # Orange
        status_emoji = "<a:red_alert:1380467108541894678>"
    else:
        embed_color = 0xF44336  # Red
        status_emoji = "<a:ao_Cross:1380466271736434811>"

   
    # Create main embed
    embed = discord.Embed(color=embed_color)
   
    # Set thumbnail
    # embed.set_thumbnail(url="https://www.nftgators.com/wp-content/uploads/2024/11/Pump.fun-logo-800x450.jpg")

    # Check if there are any bundles
    if total_bundles == 0:
        embed.description = f"## Bundle analysis for ${ticker}:\n\n❌ No bundles found"
        return embed
   
    # Get bundle data sorted by token percentage
    bundles = data.get("bundles", {})
    sorted_bundles = sorted(
        bundles.items(),
        key=lambda x: x[1].get("token_percentage", 0),
        reverse=True
    )[:5]  # Get top 5 bundles
   
    # Add header info with title and main stats in description field
    
    embed.description = (
        f"# {status_emoji} Bundle analysis for ${ticker}: \n\n"
        f"Total bundles found: **{total_bundles}**\n"
        f"Bundled Total: **{total_percentage_bundled:.2f}%**\n"
        f"Bundle Held %: **{total_holding_percentage:.2f}%**\n\n"
    )
   
    # Add each bundle to the description
    for i, (bundle_id, bundle_data) in enumerate(sorted_bundles):
        # Get bundle metrics
        token_percentage = bundle_data.get("token_percentage", 0)
        holding_percentage = bundle_data.get("holding_percentage", 0)
        primary_category = bundle_data.get("bundle_analysis", {}).get("primary_category", "unknown")
        unique_wallets = bundle_data.get("unique_wallets", 0)
       
        # Format primary category
        formatted_category = format_category(primary_category)

        remaining_percentage = (holding_percentage / token_percentage) * 100 if token_percentage > 0 else 0

        # Add bundle info to description
        embed.description += (
            f"## Bundle #{i+1} ({formatted_category})\n"
            f"Total Bundled %: **{token_percentage:.2f}%** (**{unique_wallets}** wallets)\n"
            f"Total Held %: **{holding_percentage:.2f}%**\n"
            f"Remaining bundle:\n"
            f"{score_bar(remaining_percentage, 10)} **{remaining_percentage:.2f}%**\n\n"
        )

    # Add note to description
    embed.description += (
        f"**Note:**\n"
        f"The bundle checker may produce wrong results, always do your due diligence before relying solely on its results!"
    )
       
    return embed

def create_truth_embed(post: Dict[str, Any]) -> discord.Embed:
    """
    Create a Discord embed for a Truth Social post with proper image handling
    
    Args:
        post: Truth Social post data
        
    Returns:
        discord.Embed: Formatted embed ready for Discord
    """
    # Extract basic post info
    post_id = post.get('id', '')
    content = clean_html(post.get('content', ''))
    created_at = post.get('created_at', '')
    media_attachments = post.get('media_attachments', [])
    
    # Extract account info
    account = post.get('account', {})
    display_name = account.get('display_name', 'Unknown')
    username = account.get('username', 'unknown')
    avatar_url = account.get('avatar', '')
    post_url = f"https://truthsocial.com/@{username}/posts/{post_id}"
    
    # Apply proxy to avatar URL if needed
    if avatar_url:
        avatar_url = proxy_url(avatar_url)
    
    # Create embed with Truth Social colors
    embed = discord.Embed(color=0xE12626)  # Truth Social red
    
    # Set post timestamp
    if created_at:
        try:
            embed.timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except Exception:
            pass
    
    # Set author without verification badge
    embed.set_author(
        name=f"{display_name} (@{username})",
        url=f"https://truthsocial.com/@{username}",
        icon_url=avatar_url
    )
    
    # Process by post type
    if post.get('reblog'):
        # 1. RETWEET: Show action first
        reblog = post.get('reblog', {})
        reblog_account = reblog.get('account', {})
        reblog_display_name = reblog_account.get('display_name', 'Unknown')
        reblog_username = reblog_account.get('username', 'unknown')
        reblog_verified = reblog_account.get('verified', False)
        reblog_content = clean_html(reblog.get('content', ''))
        
        # Add action field without verification emoji
        embed.add_field(
            name="",
            value=f"🔄 [{display_name} retruths {reblog_display_name}]({post_url})",
            inline=False
        )
        
        
        # 3. Quoted content block
        quoted_text = f"> **{reblog_display_name}** "
        quoted_text += f"[(@{reblog_username})](https://truthsocial.com/@{reblog_username})"
        if reblog_verified:
            quoted_text += f" {VERIFIED_EMOJI}\n"
        else:
            quoted_text += "\n"
            
        if reblog_content:
            lines = reblog_content.split('\n')
            quoted_text += "\n".join([f"> {line}" for line in lines])
        
        reblog_metrics = format_metrics(reblog)
        if reblog_metrics:
            quoted_text += f"\n> {reblog_metrics}"
        
        # Add quoted content
        safe_add_field(embed, "", quoted_text, False)
        
        # 4. Handle media attachments from reblog
        reblog_media = reblog.get('media_attachments', [])
        if reblog_media:
            # Display the first image/video
            media = reblog_media[0]
            
            # Prepare additional info text
            additional_info = []
            
            # Add attachment count info if needed
            if len(reblog_media) > 1:
                additional_info.append(f"⬇️ *+{len(reblog_media)-1} more quoted attachment(s)*")
            
            # Handle media display based on type
            if media.get('type') == 'image':
                embed.set_image(url=proxy_url(media.get('url', '')))
            elif media.get('type') == 'video' and media.get('preview_url'):
                embed.set_image(url=proxy_url(media.get('preview_url', '')))
                # Add video info with hyperlink to the actual video
                video_url = media.get('url', '')
                additional_info.append(f"⬇️📹 *Quoted post contains a [video]({video_url})*")
            
            # Add all additional info in a single field if we have any
            if additional_info:
                embed.add_field(
                    name="",
                    value="> " + "\n> ".join(additional_info),
                    inline=False
                )
                
    elif post.get('quote_id'):
        # 1. QUOTE: Show action first
        quote = post.get('quote', {})
        quote_account = quote.get('account', {})
        quote_display_name = quote_account.get('display_name', 'Unknown')
        quote_username = quote_account.get('username', 'unknown')
        quote_verified = quote_account.get('verified', False)
        quote_content = clean_html(quote.get('content', ''))
        
        # Add action field
        embed.add_field(
            name="",
            value=f"💬 [{display_name} quoted {quote_display_name}]({post_url})",
            inline=False
        )
        
        # 2. Add main post content if any
        if content:
            safe_add_field(embed, "", content, False)
        
        # 3. Add post metrics
        metrics = format_metrics(post)
        if metrics:
            embed.add_field(
                name="",
                value=metrics,
                inline=False
            )
        
        # 4. Handle main post attachments
        has_main_media = False
        if media_attachments:
            has_main_media = True
            
            # Display the first image/video
            media = media_attachments[0]
            
            # Prepare additional info text
            additional_info = []
            
            # Add attachment count info if needed
            if len(media_attachments) > 1:
                additional_info.append(f"⬇️ *+{len(media_attachments)-1} more attachment(s)*")
            
            # Handle media display based on type
            if media.get('type') == 'image':
                embed.set_image(url=proxy_url(media.get('url', '')))
            elif media.get('type') == 'video' and media.get('preview_url'):
                embed.set_image(url=proxy_url(media.get('preview_url', '')))
                # Add video info with hyperlink to the actual video
                video_url = media.get('url', '')
                additional_info.append(f"📹 *This post contains a [video]({video_url})*")
            
            # Add all additional info in a single field if we have any
            if additional_info:
                embed.add_field(
                    name="",
                    value="> " + "\n> ".join(additional_info),
                    inline=False
                )
        
        # 5. Add quoted content
        quoted_text = f"> **{quote_display_name}** "
        quoted_text += f"[(@{quote_username})](https://truthsocial.com/@{quote_username})"
        if quote_verified:
            quoted_text += f" {VERIFIED_EMOJI}\n"
        else:
            quoted_text += "\n"
            
        if quote_content:
            lines = quote_content.split('\n')
            quoted_text += "\n".join([f"> {line}" for line in lines])

        quote_metrics = format_metrics(quote)
        if quote_metrics:
            quoted_text += f"\n> {quote_metrics}" 

        safe_add_field(embed, "", quoted_text, False)
        
        # 6. Handle quoted post media
        quote_media = quote.get('media_attachments', [])
        if quote_media:
            media = quote_media[0]
            additional_info = []
            if has_main_media:
                if len(quote_media) > 1:
                    additional_info.append(f"📷 *Quoted post has {len(quote_media)} attachments*")
            else:
                if len(quote_media) > 1:
                    additional_info.append(f"⬇️ *+{len(quote_media)-1} more quoted attachment(s)*")

                if media.get('type') == 'image':
                    embed.set_image(url=proxy_url(media.get('url', '')))

                elif media.get('type') == 'video' and media.get('preview_url'):
                    embed.set_image(url=proxy_url(media.get('preview_url', '')))
                    video_url = media.get('url', '')
                    additional_info.append(f"⬇️📹 *Quoted [video]({video_url})*")
        
        if additional_info:
            embed.add_field(
                name="",
                value="> " + "\n> ".join(additional_info),
                inline=False
            )
            
    elif post.get('in_reply_to_id'):
        # 1. REPLY: Show action first
        reply_to = post.get('in_reply_to', {})
        reply_account = reply_to.get('account', {})
        reply_display_name = reply_account.get('display_name', 'Unknown')
        
        # Add action field
        embed.add_field(
            name="",
            value=f"↩️ [{display_name} replied to {reply_display_name}]({post_url})",
            inline=False
        )
        
        # 2. Add post content
        if content:
            safe_add_field(embed, "", content, False)
        
        # 3. Add metrics
        metrics = format_metrics(post)
        if metrics:
            embed.add_field(
                name="",
                value=metrics,
                inline=False
            )
        
        # 4. Handle media attachments
        if media_attachments:
            media = media_attachments[0]
            additional_info = []

            # If more than one attachment, add the count
            if len(media_attachments) > 1:
                additional_info.append(f"⬇️ *+{len(media_attachments)-1} more attachment(s)*")

            # Display the first media
            if media.get('type') == 'image':
                embed.set_image(url=proxy_url(media.get('url', '')))
            elif media.get('type') == 'video' and media.get('preview_url'):
                embed.set_image(url=proxy_url(media.get('preview_url', '')))
                video_url = media.get('url', '')
                additional_info.append(f"⬇️📹 *This post contains a [video]({video_url})*")
            
            # Add all additional info in a single field if we have any
            if additional_info:
                embed.add_field(
                    name="",
                    value="> " + "\n> ".join(additional_info),
                    inline=False
                )
    
    else:
        # 1. REGULAR POST: Show action first
        embed.add_field(
            name="",
            value=f"🔗 [{display_name} posted]({post_url})",
            inline=False
        )
        
        # 2. Add post content
        if content:
            safe_add_field(embed, "", content, False)
        
        # 3. Add metrics
        metrics = format_metrics(post)
        if metrics:
            embed.add_field(
                name="",
                value=metrics,
                inline=False
            )
        
        # 4. Handle media attachments
        if media_attachments:
            media = media_attachments[0]
            additional_info = []

            # If more than one attachment, add the count
            if len(media_attachments) > 1:
                additional_info.append(f"⬇️ *+{len(media_attachments)-1} more attachment(s)*")

            # Display the first media
            if media.get('type') == 'image':
                embed.set_image(url=proxy_url(media.get('url', '')))
            elif media.get('type') == 'video' and media.get('preview_url'):
                embed.set_image(url=proxy_url(media.get('preview_url', '')))
                video_url = media.get('url', '')
                additional_info.append(f"⬇️📹 *This post contains a [video]({video_url})*")
            
            # Add all additional info in a single field if we have any
            if additional_info:
                embed.add_field(
                    name="",
                    value="> " + "\n> ".join(additional_info),
                    inline=False
                )

    # Set footer with Truth Social branding
    embed.set_footer(
        text="Truth Social Tracker",
        icon_url="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTGQlZkYBgEbptbNjrWpJjzqEhPfY8ugpIsXA&s"
    )
    
    return embed