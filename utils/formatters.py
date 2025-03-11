"""
Formatting utilities for values, dates, and other display elements
"""
from datetime import datetime

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