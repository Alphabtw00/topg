"""
Formatting utilities for values, dates, and other display elements
"""
from datetime import datetime
from typing import Dict, Set, Any

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
        return None
    
    try:
        fdv_price_ratio = current_fdv / current_price
        return ath_price * fdv_price_ratio
    except (ZeroDivisionError, TypeError, ValueError):
        return None

def calculate_trust_score(code_review: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate trust score based on code review.
    
    Args:
        code_review: Code review data
        
    Returns:
        Dictionary with trust score and details
    """
    # Count issues
    red_flags_count = len(code_review.get("redFlags", []))
    larp_indicators_count = len(code_review.get("larpIndicators", []))
    
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
        "Low": 10,
        "Medium": 20,
        "High": 30
    }.get(misleading_level, 0)
    
    ai_concerns_penalty = len(ai_analysis.get("concerns", [])) * 5
    
    # Start with base trust score
    trust_score = 100
    
    # Apply penalties for issues
    penalties = {
        "red_flags": red_flags_count * 15,  # -15 points per red flag
        "larp_indicators": larp_indicators_count * 10,  # -10 points per LARP indicator
        "misrepresentation": misrepresentation_count * 20,  # -20 points per misrepresentation
        "ai_misleading": ai_misleading_penalty,
        "ai_concerns": ai_concerns_penalty
    }
    
    # Apply all penalties
    for penalty_name, penalty_value in penalties.items():
        trust_score -= penalty_value
    
    # Ensure range 0-100
    trust_score = max(0, min(100, trust_score))
    
    return {
        "score": trust_score,
        "penalties": penalties,
        "red_flags_count": red_flags_count,
        "larp_indicators_count": larp_indicators_count,
        "misleading_level": misleading_level
    }

def calculate_final_legitimacy_score(technical_score: int, trust_score: int) -> int:
    """
    Calculate final legitimacy score.
    
    Args:
        technical_score: Technical score (0-100)
        trust_score: Trust score (0-100)
        
    Returns:
        Final legitimacy score (0-100)
    """
    # Weight technical score more than trust score
    # Technical merit matters more than subjective trust factors
    return round((technical_score * 0.6) + (trust_score * 0.4))

def calculate_verdict(scores: Dict[str, Any], trust_result: Dict[str, Any], code_review: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate verdict with transparent weighting of factors.
    Optimistically biased to favor positive outcomes.
    
    Args:
        scores: Technical scores data
        trust_result: Trust calculation result
        code_review: Code review data
        
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
        "Medium": 70,
        "Medium-High": 75,
        "Hold": 65, 
        "Sell": 50,
        "Strong Sell": 40,
        "Low": 50
    }.get(rating, 60)  # Default is positive
    
    # Apply confidence adjustment to rating value
    # Low confidence reduces the impact of the rating
    adjusted_rating = rating_value * (confidence / 100) if confidence > 0 else rating_value * 0.5
    
    # Clear weighting of factors for transparency
    weights = {
        "technical": 0.5,    # Technical quality is most important
        "trust": 0.3,        # Trust factors matter but less than technical merit
        "rating": 0.2        # Investment rating has some influence
    }
    
    # Calculate composite score - with a small positive boost
    composite_score = (
        (technical_score * weights["technical"]) + 
        (trust_score * weights["trust"]) + 
        (adjusted_rating * weights["rating"]) +
        5  # Small positive boost to favor good outcomes
    )
    
    # Ensure score is within bounds
    composite_score = max(0, min(100, composite_score))
    
    # Determine verdict based on composite score with optimistic thresholds
    if composite_score >= 70:  # Lowered from traditional 75
        return {
            "color": 0x00FF00,  # Green
            "verdict": "INVESTMENT RECOMMENDED",
            "emoji": "✅",
            "investment_advice": "Appears to be a solid project with good technical foundation",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "weights": weights
            }
        }
    elif composite_score >= 55:  # Lowered from traditional 60
        return {
            "color": 0xFFD700,  # Gold
            "verdict": "POTENTIALLY VIABLE",
            "emoji": "⚠️",
            "investment_advice": "Shows promise but exercise caution and conduct additional research",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "weights": weights
            }
        }
    elif composite_score >= 40:  # Lowered from traditional 45
        return {
            "color": 0xFF8C00,  # Dark Orange
            "verdict": "HIGH RISK INVESTMENT",
            "emoji": "⚠️",
            "investment_advice": "Significant concerns detected - thorough investigation recommended",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "weights": weights
            }
        }
    else:
        return {
            "color": 0xFF0000,  # Red
            "verdict": "NOT RECOMMENDED",
            "emoji": "🚨",
            "investment_advice": "Multiple critical issues found - investment not advised",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "weights": weights
            }
        }