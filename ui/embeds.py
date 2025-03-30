"""
Discord embed creation for different types of data
"""
import discord
import asyncio
from datetime import datetime
from config import TWITTER_SEARCH_URL, TRADING_PLATFORMS
from utils.formatters import (
    format_value, format_date, format_size, 
    relative_time, get_color_from_change, score_bar
)
from utils.logger import get_logger


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
        # Extract core data once to avoid repeated dictionary lookups
        # Use .get() with defaults to prevent errors if keys are missing
        change = float(entry.get("priceChange", {}).get("m5", 0))
        current_price = float(entry.get("priceUsd", 0))
        current_fdv = float(entry.get("fdv", 0))
        liquidity = float(entry.get("liquidity", {}).get("usd", 0))
        volume_5m = entry.get("volume", {}).get("m5", 0)
        txns = entry.get("txns", {}).get("m5", {})
        buys = txns.get("buys", 0)
        sells = txns.get("sells", 0)
        pair_created_at = entry.get("pairCreatedAt")
        
        # Set color based on price change
        embed = discord.Embed(color=get_color_from_change(change))
        
        # Section 1: Core Metrics (FDV, Price, Liquidity)
        embed.add_field(name="💰 FDV", value=f"**`${format_value(current_fdv)}`**", inline=True)
        embed.add_field(name="💵 USD Price", value=f"**`${format_value(current_price)}`**", inline=True)
        embed.add_field(name="💧 Liquidity", value=f"**`${format_value(liquidity)}`**", inline=True)
        
        # Section 2: Performance Metrics (ATH, Volume, Change) - Reverted to old layout
        embed.add_field(name="🏆 ATH", value="**`Fetching...`**", inline=True)
        
        # Price change indicators
        emoji = "📉" if change < 0 else "📈"
        embed.add_field(name="📊 5m Volume", value=f"**`${format_value(volume_5m)}`**", inline=True)
        embed.add_field(name=f"{emoji} 5m Change", value=f"**`{format_value(change)}%`**", inline=True)
        
        # Section 3: Transactions
        embed.add_field(
            name="🔄 5m Transactions",
            value=f"🟢 **`{format_value(buys)}`** | 🔴 **`{format_value(sells)}`**",
            inline=False,
        )
        
        # Section 4: Links - build efficiently in a single pass
        info = entry.get("info", {})
        links_parts = []
        
        # Websites
        websites = info.get("websites", [])
        if websites:
            sites_links = " ".join(f"[{site.get('label') or 'Website'}]({site['url']})" for site in websites)
            links_parts.append(f"**Websites:** {sites_links}")
        
        # Socials
        socials = info.get("socials", [])
        if socials:
            social_links = " ".join(f"[{soc.get('type', 'Social').title()}]({soc['url']})" for soc in socials)
            links_parts.append(f"**Socials:** {social_links}")
        
        # Chart
        links_parts.append(f"**Chart:** [DEX]({entry.get('url', '#')})")
        
        if links_parts:
            embed.add_field(name="🔗 Links", value="\n".join(links_parts), inline=False)
        
        # Section 5: Twitter Search
        base_token = entry.get('baseToken', {})
        symbol = base_token.get('symbol', '')
        
        from urllib.parse import quote
        embed.add_field(
            name="👀 Twitter Search",
            value=f"[CA]({TWITTER_SEARCH_URL.format(query=address)})       [TICKER]({TWITTER_SEARCH_URL.format(query=quote(f'${symbol}'))})",
            inline=False
        )
        
        # Section 6: Contract Address
        embed.add_field(name="🔑 Contact Address", value=f"`{address}`", inline=False)
        
        # Section 7: Trading Platforms
        platforms = [f"[{name}]({url.format(pair=entry.get('pairAddress', address), address=address)})" 
                     for name, url in TRADING_PLATFORMS.items()]
        embed.add_field(name="💱 Trade On", value=" | ".join(platforms), inline=False)
        
        # Set banner image if available
        banner = info.get("header")
        if banner:
            embed.set_image(url=banner)
        
        #created ago
        if pair_created_at:
            embed.set_footer(text=f"🕒 {relative_time(pair_created_at, include_ago=True)}")
        
        # Set token logo as thumbnail
        img = info.get("imageUrl")
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
    from api.mobula import calculate_ath_marketcap
    # Find the ATH field
    for field in embed_dict["fields"]:
        if field["name"] == "🏆 ATH":
            if ath_price and ath_timestamp:
                # Calculate ATH market cap
                ath_mcap = calculate_ath_marketcap(ath_price, current_price, current_fdv)
                
                if ath_mcap:
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
            first_call_text = f"⚡ You're First! @ ${format_value(initial_fdv)}"
        else:
            if price_multiple >= 2:
                first_call_text = f"🏆 {user_name} @ ${format_value(initial_fdv)} ({int(price_multiple)}x)"
            else:
                first_call_text = f"🏆 {user_name} @ ${format_value(initial_fdv)}"
        
        # Get existing footer text if it exists
        existing_footer_text = ""
        if "footer" in embed_dict and "text" in embed_dict["footer"]:
            existing_footer_text = embed_dict["footer"]["text"]
        
        # Combine footer texts
        combined_footer = f"{first_call_text} • {existing_footer_text}" if existing_footer_text else first_call_text
        
        # Update embed footer
        embed_dict["footer"] = {"text": combined_footer}
            
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

def create_github_analysis_embed(repo_info, analysis, start_time, interaction):
        """
        Create an enhanced embed for GitHub repository analysis.
        
        Args:
            repo_info: Repository information dictionary
            analysis: Analysis data with scores and review information
            start_time: Analysis start time for tracking performance
            interaction: Discord interaction object
            is_cached: Whether this is from cache
            
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
        
        if warning_text:
            warning_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        embed.description = (
            f"## {verdict_emoji} VERDICT: {verdict} {verdict_emoji}\n"
            f"### {investment_advice}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{warning_text}"
            f"{analysis.get('summary', 'No summary available')}"
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
        
        # Overall assessment
        overall_assessment = code_review.get("overallAssessment")
        if overall_assessment:
            # # Split into paragraphs and get just the first one for brevity
            # paragraphs = overall_assessment.split("\n\n")
            # first_paragraph = paragraphs[0]
            formatted_assessment = overall_assessment.replace("\n", "\n> ")
            embed.add_field(
                name="👨‍💻 Expert Opinion",
                value=f"> {formatted_assessment}",
                inline=False
            )
        
        # Footer
        embed.set_footer(
            text=f"Requested by {interaction.user.display_name} • ⌛Analysis Time: {(datetime.now().timestamp() - start_time):.1f}s", 
            icon_url=interaction.user.display_avatar.url
        )
        
        return embed

async def create_health_embed(bot, user):
    """
    Create an optimized health status embed without system metrics
    
    Args:
        bot: Bot instance
        user: User who requested health info
        
    Returns:
        discord.Embed: Health information embed
    """
    from datetime import datetime, timedelta
    
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
    
    # Calculate average processing time from recent data only (last 5 minutes)
    current_time = datetime.now().timestamp()
    recent_processing = [
        t[0] for t in bot.metrics['processing_times'] 
        if current_time - t[1] < 300  # Only from last 5 minutes
    ]
    
    avg_time = 0 if not recent_processing else sum(recent_processing) / len(recent_processing)
    
    # Get most used commands
    top_commands = sorted(
        bot.metrics['command_usage'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:3]
    
    total_errors = bot.get_error_count()
    
    # Get top 3 errors
    top_errors = []
    if bot.metrics['errors']:
        top_errors = sorted(
            bot.metrics['errors'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

    # Database metrics
    from handlers.mysql_handler import get_db_pool_stats
    db_stats = await get_db_pool_stats()
    
    # Create embed
    embed = discord.Embed(
        title="🔍 Bot Health Monitor",
        description=f"Status snapshot taken <t:{int(datetime.now().timestamp())}:R>",
        timestamp=datetime.now(),
        color=color
    )
    
    banner = "https://i.imgur.com/fQOYDpO.gif"  # Direct GIF link
    embed.set_image(url=banner)

    # Bot metrics section
    bot_info = (
        f"**Uptime:** {uptime_str}\n"
        f"**Latency:** {latency}ms\n"
        f"**Messages Processed:** {bot.metrics['processed_count']}\n"
        f"**Avg. Processing:** {avg_time*1000:.1f}ms\n"
        f"**Total Errors:** {total_errors}"
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
    
    # API Performance section
    api_latency = ""
    if bot.metrics['api_latency']:
        for endpoint, latencies in sorted(bot.metrics['api_latency'].items())[:3]:  # Limit to top 3
            if latencies:
                # Only use recent latencies (last 5 minutes)
                avg_latency = sum(latencies[-20:]) / min(len(latencies), 20)
                api_latency += f"**{endpoint}:** {avg_latency*1000:.0f}ms\n"
        
        if api_latency:
            embed.add_field(name="🌐 API Performance", value=api_latency, inline=False)
    
    #top errors
    if top_errors:
        error_info = "\n".join([
            f"**{err_key}:** {count} times" 
            for err_key, count in top_errors
        ])
        embed.add_field(
            name="⚠️ Top Errors", 
            value=error_info,
            inline=True
        )

    # Command usage section if there are commands used
    if top_commands:
        usage_info = "\n".join([f"**{cmd}:** {count} uses" for cmd, count in top_commands])
        embed.add_field(name="📊 Top Commands", value=usage_info, inline=True)
    
    # Set footer with timestamp
    embed.set_footer(
        text=f"Requested by {user}", 
        icon_url=user.display_avatar.url
    )
    
    return embed