"""
Formatting utilities for values, dates, and other display elements
"""
from datetime import datetime
from typing import Dict, Set, Any
from functools import lru_cache
import re
import urllib.parse

from utils.logger import get_logger


logger = get_logger()


def format_value(value) -> str:
    """
    Format a numerical value for display, with appropriate suffix
    
    Args:
        value: Number to format
        
    Returns:
        str: Formatted string
    """
    if value is None:
        return "N/A"
        
    value = float(value)
    abs_value = abs(value)
    
    if abs_value >= 1e9:
        return f"{value / 1e9:.1f}".rstrip("0").rstrip(".") + "B"
    if abs_value >= 1e6:
       return f"{value / 1e6:.1f}".rstrip("0").rstrip(".") + "M"
    if abs_value >= 1e3:
        return f"{value / 1e3:.1f}".rstrip("0").rstrip(".") + "K"
    if abs_value < 1:
        # Handle small values efficiently
        return f"{value:.6f}".rstrip('0').rstrip('.')
    
    # Format normal values efficiently
    if abs_value == int(abs_value):
        return str(int(value))
    return f"{value:.2f}".rstrip('0').rstrip('.')

def format_date(date_str):
    """
    Format an ISO date string to a more readable format
    
    Args:
        date_str: ISO date string
        
    Returns:
        str: Formatted date string or 'Unknown' if invalid
    """
    if not date_str or date_str == "Unknown":
        return "Unknown"
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except Exception:
        return date_str

def format_size(size_kb):
    """
    Convert size in KB to a human-readable format (KB, MB, or GB)
    
    Args:
        size_kb: Size in kilobytes
        
    Returns:
        str: Formatted size string
    """
    try:
        size = float(size_kb)
    except (ValueError, TypeError):
        return "Unknown"
    if size < 1024:
        return f"{size:.0f} KB"
    elif size < 1024 * 1024:
        size_mb = size / 1024
        return f"{size_mb:.2f} MB"
    else:
        size_gb = size / (1024 * 1024)
        return f"{size_gb:.2f} GB"

def relative_time(timestamp, include_ago=False) -> str:
    """
    Convert a timestamp to a relative time string
    
    Args:
        timestamp: Unix timestamp in milliseconds
        include_ago: Whether to append 'ago' to the result
        
    Returns:
        str: Relative time string
    """
    try:
        delta = datetime.now() - datetime.fromtimestamp(timestamp / 1000)
        
        if delta.seconds <= 5 and delta.days == 0:
            return "Just now"
            
        # Format the time unit
        if delta.days >= 365:
            time_str = f"{delta.days//365}y"
        elif delta.days > 30:
            time_str = f"{delta.days//30}mo"
        elif delta.days:
            time_str = f"{delta.days}d"
        elif delta.seconds >= 3600:
            time_str = f"{delta.seconds//3600}h"
        elif delta.seconds >= 60:
            time_str = f"{delta.seconds//60}m"
        else:
            time_str = f"{delta.seconds}s"
        
        return f"{time_str} ago" if include_ago else time_str
    except Exception:
        return "N/A"

def get_color_from_change(change: float) -> int:
    """
    Determine color based on a numerical change
    
    Args:
        change: Numerical change value
        
    Returns:
        int: Discord color code
    """
    if change > 0:
        return 0x00FF00  # Green
    elif change < 0:
        return 0xFF0000  # Red
    else:
        return 0x0000FF  # Blue

def create_progress_bar(percentage: float, max_bars: int = 10) -> str:
    """
    Create a progress bar with appropriate color indicator
    
    Args:
        percentage: Value between 0 and 100
        max_bars: Maximum number of bars in the progress indicator
        
    Returns:
        str: Formatted progress bar
    """
    filled = int(round(percentage / 100 * max_bars))
    color = (
        "🟢" if percentage < 50 else
        "🟡" if percentage < 75 else
        "🔴"
    )
    return f"{color} {'█' * filled}{'░' * (max_bars - filled)}"

def score_bar(percentage: float) -> str:
    """
    Create a visual score bar for better readability
    
    Args:
        percentage: Value between 0 and 100
        
    Returns:
        str: Emoji-based score bar
    """
    if percentage <= 0:
        return "⬜⬜⬜⬜⬜"
    
    # Calculate filled and empty blocks
    filled = min(5, max(0, round(percentage / 20)))
    
    # Determine color based on score
    if percentage >= 80:
        filled_char = "🟩"
    elif percentage >= 60:
        filled_char = "🟨"
    elif percentage >= 40:
        filled_char = "🟧"
    else:
        filled_char = "🟥"
    
    # Create bar with appropriate coloring
    return filled_char * filled + "⬜" * (5 - filled)

# Parse channel colors
def parse_channel_colors(colors_str: str, bot_input_channel_ids: Set[int]) -> Dict[int, int]:
    """Parse channel-specific colors from environment variable"""
    color_dict = {}
    
    # Check if we have channel-specific colors in format: channel_id:color,channel_id:color
    if ":" in colors_str:
        pairs = colors_str.split(",")
        for pair in pairs:
            if ":" in pair:
                ch_id, color = pair.strip().split(":")
                if ch_id.isdigit() and color.strip():
                    try:
                        color_dict[int(ch_id)] = int(color.strip(), 16)
                    except ValueError:
                        pass
    else:
        # Just a list of colors to assign sequentially
        colors = colors_str.split(",")
        colors = [int(color.strip(), 16) for color in colors if color.strip()]
        
        # Map colors to input channels
        for i, channel_id in enumerate(bot_input_channel_ids):
            # Use the corresponding color if available, otherwise use the first or default color
            color_index = min(i, len(colors) - 1) if colors else 0
            color_dict[channel_id] = colors[color_index] if colors else 0x3498db
    
    return color_dict

# def calculate_ath_marketcap(ath_price: float, current_price: float, current_fdv: float):
#     """
#     Calculate ATH market cap based on ATH price and current FDV
    
#     Args:
#         ath_price: All-time high price
#         current_price: Current price
#         current_fdv: Current fully diluted valuation
        
#     Returns:
#         float or None: Calculated ATH market cap or None if input data is invalid
#     """
#     if not all([ath_price, current_price, current_fdv]):
#         return None
    
#     try:
#         fdv_price_ratio = current_fdv / current_price
#         return ath_price * fdv_price_ratio
#     except (ZeroDivisionError, TypeError, ValueError):
#         return None
    

def calculate_ath_marketcap(ath_price: float, current_price: float, current_fdv: float):
    """
    Calculate ATH market cap based on ATH price and current FDV
   
    Args:
        ath_price: All-time high price
        current_price: Current price
        current_fdv: Current fully diluted valuation
   
    Returns:
        float or None: Calculated ATH market cap or None if input data is invalid
    """
    if not all([ath_price, current_price, current_fdv]):
        logger.debug("[calc_ath_mcap] one or more inputs are falsy, returning None")
        return None
   
    try:
        if 0 < ath_price < 1e-6:
            ath_price *= 1e3

        # Calculate token supply
        supply = current_fdv / float(current_price)
        mcap = float(ath_price) * supply
        return mcap
        
    except (ZeroDivisionError, TypeError, ValueError) as e:
        logger.error(f"[calc_ath_mcap] error in calculation: {e}")
        return None

def calculate_trust_score(code_review: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate trust score based on code review with improved balancing.
    
    Args:
        code_review: Code review data
        
    Returns:
        Dictionary with trust score and details
    """
    # Count issues
    red_flags = code_review.get("redFlags", [])
    larp_indicators = code_review.get("larpIndicators", [])
    
    # Classify red flags by severity
    severe_flags = []
    moderate_flags = []
    minor_flags = []
    
    severe_keywords = ["vulnerability", "security", "exploit", "critical", "breach", "unsafe"]
    moderate_keywords = ["warning", "concern", "issue", "problem", "limitation"]
    
    for flag in red_flags:
        flag_lower = flag.lower()
        if any(keyword in flag_lower for keyword in severe_keywords):
            severe_flags.append(flag)
        elif any(keyword in flag_lower for keyword in moderate_keywords):
            moderate_flags.append(flag)
        else:
            minor_flags.append(flag)
    
    # Check for misrepresentation concerns
    misrepresentation_count = sum(
        1 for check in code_review.get("misrepresentationChecks", [])
        if any(term in check.lower() for term in ["suspicious", "concern", "issue", "problem"])
    )
    
    # AI-specific factors
    ai_analysis = code_review.get("aiAnalysis", {})
    
    misleading_level = ai_analysis.get("misleadingLevel", "None")
    ai_misleading_penalty = {
        "None": 0,
        "Low": 7,
        "Medium": 15,
        "High": 25
    }.get(misleading_level, 0)
    
    ai_concerns_penalty = min(15, len(ai_analysis.get("concerns", [])) * 5)
    
    # Start with base trust score
    trust_score = 100
    
    # Apply penalties for issues with reduced severity
    penalties = {
        "severe_flags": len(severe_flags) * 15,  # -15 points per severe flag
        "moderate_flags": len(moderate_flags) * 10,  # -10 points per moderate flag
        "minor_flags": len(minor_flags) * 5,    # -5 points per minor flag
        "larp_indicators": min(30, len(larp_indicators) * 7),  # -7 points per LARP indicator, max 30
        "misrepresentation": min(30, misrepresentation_count * 15),  # -15 points per misrepresentation, max 30
        "ai_misleading": ai_misleading_penalty,
        "ai_concerns": ai_concerns_penalty
    }
    
    # Add positive factors
    positive_factors = {}
    
    # Look for positive indicators in repo review
    if ai_analysis.get("implementationQuality") in ["Good", "Excellent"]:
        positive_factors["good_ai_implementation"] = 10
    
    # Check investment ranking
    investment = code_review.get("investmentRanking", {})
    if investment.get("rating") in ["High", "Strong Buy", "Buy"]:
        confidence = investment.get("confidence", 0)
        # Only boost if confidence is high
        if confidence >= 70:
            positive_factors["positive_investment"] = 15
    
    # Apply all penalties
    for penalty_name, penalty_value in penalties.items():
        trust_score -= penalty_value
    
    # Apply positive factors
    for factor_name, factor_value in positive_factors.items():
        trust_score += factor_value
    
    # Cap the total penalty - ensure even repos with issues don't go below 30
    trust_score = max(30, trust_score)
    
    # Ensure range 0-100
    trust_score = min(100, trust_score)
    
    return {
        "score": trust_score,
        "penalties": penalties,
        "positive_factors": positive_factors,
        "red_flags_count": len(red_flags),
        "severe_flags_count": len(severe_flags),
        "moderate_flags_count": len(moderate_flags),
        "minor_flags_count": len(minor_flags),
        "larp_indicators_count": len(larp_indicators),
        "misleading_level": misleading_level
    }

def calculate_final_legitimacy_score(technical_score: int, trust_score: int, repo_info: Dict = None) -> int:
    """
    Calculate final legitimacy score with adaptive weighting.
    
    Args:
        technical_score: Technical score (0-100)
        trust_score: Trust score (0-100)
        repo_info: Repository information (optional)
        
    Returns:
        Final legitimacy score (0-100)
    """
    # Default weights
    tech_weight = 0.6
    trust_weight = 0.4
    
    # Adjust weights based on technical score
    if technical_score >= 85:
        # For excellent technical repos, reduce trust impact
        tech_weight = 0.7
        trust_weight = 0.3
    elif technical_score <= 50:
        # For poor technical repos, increase trust impact
        tech_weight = 0.5
        trust_weight = 0.5
    
    # Additional adjustment for ML/AI projects
    if repo_info and repo_info.get("description"):
        description = repo_info.get("description", "").lower()
        if any(term in description for term in ["ml", "ai", "machine learning", "artificial intelligence", "neural", "model"]):
            # Further reduce trust impact for ML/AI projects which often have inherent limitations
            tech_weight += 0.05
            trust_weight -= 0.05
    
    return round((technical_score * tech_weight) + (trust_score * trust_weight))

def calculate_verdict(scores: Dict[str, Any], trust_result: Dict[str, Any], 
                    code_review: Dict[str, Any], repo_info: Dict = None) -> Dict[str, Any]:
    """
    Calculate verdict with transparent weighting of factors and popularity recognition.
    
    Args:
        scores: Technical scores data
        trust_result: Trust calculation result
        code_review: Code review data
        repo_info: Repository information (optional)
        
    Returns:
        Verdict information
    """
    # Get core scores
    technical_score = scores.get("technicalScore", 0)
    trust_score = trust_result.get("score", 0)
    
    # Get additional metrics that influence the verdict
    ranking = code_review.get("investmentRanking", {})
    rating = ranking.get("rating", "Unknown")
    confidence = ranking.get("confidence", 0)
    
    # First, convert investment rating to a numeric value
    rating_value = {
        "Strong Buy": 95,
        "Buy": 85,
        "High": 85, 
        "Medium-High": 75,
        "Medium": 70,
        "Hold": 65, 
        "Low": 50,
        "Sell": 50,
        "Strong Sell": 40
    }.get(rating, 60)  # Default is positive
    
    # Apply confidence adjustment to rating value
    # Low confidence reduces the impact of the rating
    adjusted_rating = rating_value * (confidence / 100) if confidence > 0 else rating_value * 0.5
    
    # Calculate popularity boost for starred repos
    popularity_boost = 0
    if repo_info:
        stars = repo_info.get("stargazers_count", 0)
        if stars > 5000:
            popularity_boost = 10
        elif stars > 1000:
            popularity_boost = 7
        elif stars > 500:
            popularity_boost = 5
        elif stars > 100:
            popularity_boost = 3
    
    # Clear weighting of factors for transparency
    weights = {
        "technical": 0.5,    # Technical quality is most important
        "trust": 0.3,        # Trust factors matter but less than technical merit
        "rating": 0.2        # Investment rating has some influence
    }
    
    # Calculate composite score with adjustments
    base_boost = 5  # Base positive boost
    
    # Higher boost for highly technical projects
    if technical_score >= 85:
        base_boost += 2
    
    composite_score = (
        (technical_score * weights["technical"]) + 
        (trust_score * weights["trust"]) + 
        (adjusted_rating * weights["rating"]) +
        base_boost +
        popularity_boost
    )
    
    # Ensure score is within bounds
    composite_score = max(0, min(100, composite_score))
    
    # Adjust threshold for excellent technical implementations
    recommend_threshold = 80  # Default threshold
    if technical_score >= 85:
        recommend_threshold = 75  # Lower threshold for excellent projects
    
    # Determine verdict based on composite score with adjusted thresholds
    if composite_score >= recommend_threshold:
        return {
            "color": 0x00FF00,  # Green
            "verdict": "INVESTMENT RECOMMENDED",
            "emoji": "✅",
            "investment_advice": "Appears to be a solid project with good technical foundation. 📝 NFA-DYOR",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "popularity_boost": popularity_boost,
                "weights": weights
            }
        }
    elif composite_score >= 55:
        return {
            "color": 0xFFD700,  # Gold
            "verdict": "POTENTIALLY VIABLE",
            "emoji": "⚠️",
            "investment_advice": "Shows promise but exercise caution and conduct additional research. 📝 NFA-DYOR",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "popularity_boost": popularity_boost,
                "weights": weights
            }
        }
    elif composite_score >= 40:
        return {
            "color": 0xFF8C00,  # Dark Orange
            "verdict": "HIGH RISK INVESTMENT",
            "emoji": "⚠️",
            "investment_advice": "Significant concerns detected - thorough investigation recommended. 📝 NFA-DYOR",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "popularity_boost": popularity_boost,
                "weights": weights
            }
        }
    else:
        return {
            "color": 0xFF0000,  # Red
            "verdict": "NOT RECOMMENDED",
            "emoji": "🚨",
            "investment_advice": "Multiple critical issues found - investment not advised. 📝 NFA-DYOR",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "popularity_boost": popularity_boost,
                "weights": weights
            }
        }

@lru_cache(maxsize=100)
def proxy_url(url: str) -> str:
    """
    Convert any URL to a proxied version through images.weserv.nl
    
    Args:
        url: Original image URL
        
    Returns:
        str: Proxied URL that will work in Discord embeds
    """
    if not url:
        return ""
        
    # Make sure URL is properly encoded
    return f"https://images.weserv.nl/?url={urllib.parse.quote(url)}"

# Add this utility function for extreme cases where automatic handling isn't enough
def safe_text(text):
    """
    Make any text safe for logging by replacing non-ASCII characters
    For use in extreme cases where automatic handling isn't sufficient
    """
    if text is None:
        return "None"
    
    if not isinstance(text, str):
        try:
            text = str(text)
        except:
            return "Unstringable object"
    
    return text.encode('ascii', 'replace').decode('ascii')

def clean_html(html_content: str) -> str:
    """
    Remove HTML tags from content
    
    Args:
        html_content: HTML content string
        
    Returns:
        str: Plain text content
    """
    if not html_content:
        return ""
    
    # Remove <br/> with newlines before removing all tags
    content = html_content.replace("<br/>", "\n").replace("<br>", "\n")
    
    # Simple regex-based HTML tag removal
    content = re.sub(r'<[^>]+>', '', content)
    
    # Clean up extra spaces and newlines
    content = re.sub(r'\n\s*\n', '\n\n', content)
    return content.strip()

def format_metrics(post: Dict[str, Any]) -> str:
    """
    Format post metrics (replies, reblogs, likes)
    
    Args:
        post: Truth Social post data
        
    Returns:
        str: Formatted metrics string
    """
    metrics = []
    
    reply_count = post.get('replies_count', 0)
    reblogs_count = post.get('reblogs_count', 0)
    faves_count = post.get('favourites_count', 0) or post.get('upvotes_count', 0)
    
    if reply_count > 0:
        metrics.append(f"💬 {format_value(reply_count)}")
    
    if reblogs_count > 0:
        metrics.append(f"🔄 {format_value(reblogs_count)}")
    
    if faves_count > 0:
        metrics.append(f"❤️ {format_value(faves_count)}")
    
    return " • ".join(metrics) if metrics else ""