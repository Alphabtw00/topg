import re
from utils.logger import get_logger
from typing import Optional, Dict, Any
import aiohttp


logger = get_logger()


def sanitize_code_content(content: str) -> str:
    """
    Sanitize code content for analysis.
    
    Args:
        content: Raw file content
        
    Returns:
        Sanitized content
    """
    if not isinstance(content, str):
        return ""
        
    # Truncate large files
    content = content[:5000] #todo add from config
    
    # Remove Unicode control characters
    content = re.sub(r'[\u0000-\u0008\u000B-\u000C\u000E-\u001F\uD800-\uDFFF]', '', content)
    
    # Normalize newlines
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    
    return content


def get_file_extension(filename: str) -> str:
    """
    Get language identifier from file extension.
    
    Args:
        filename: Filename including extension
        
    Returns:
        Language name for syntax highlighting
    """
    # Fast extension extraction
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    # Language mapping
    language_map = {
        'js': 'javascript',
        'ts': 'typescript',
        'py': 'python',
        'java': 'java',
        'go': 'go',
        'rs': 'rust',
        'cpp': 'cpp',
        'c': 'c',
        'jsx': 'javascript',
        'tsx': 'typescript',
        'vue': 'vue',
        'php': 'php',
        'rb': 'ruby',
        'sol': 'solidity',
        'cs': 'csharp',
        'html': 'html',
        'css': 'css',
        'scss': 'scss',
        'md': 'markdown',
        'json': 'json',
        'yml': 'yaml',
        'yaml': 'yaml'
    }
    
    return language_map.get(ext, ext)

def safe_add_field(embed, name, content, inline=False):
    # If content is too long, truncate with an indicator
    if len(content) > 1024:
        content = content[:1020] + "..."
    embed.add_field(name=name, value=content, inline=False)

async def fetch_token_image_from_uri(uri: str) -> Optional[str]:
    """Fetch token metadata from URI and extract image URL"""
    if not uri:
        return None
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(uri, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    metadata = await response.json()
                    return metadata.get('image')
    except Exception as e:
        logger.debug(f"Error fetching token metadata from {uri}: {e}")
    
    return None

def parse_market_cap_value(value: str) -> Optional[float]:
    """
    Parse market cap value from string format
    
    Args:
        value: Market cap string (e.g., "50k", "2.5m", "1b", "250000")
    
    Returns:
        float: Parsed market cap value
        
    Raises:
        ValueError: If value format is invalid
    """
    if not value:
        return None
    
    # Remove spaces and convert to lowercase
    value = value.strip().lower()
    
    # Handle direct numeric values
    if value.replace('.', '').replace(',', '').isdigit():
        return float(value.replace(',', ''))
    
    # Regular expression to match number + suffix
    pattern = r'^(\d+(?:\.\d+)?)\s*([kmb]?)$'
    match = re.match(pattern, value)
    
    if not match:
        raise ValueError(f"Invalid market cap format: {value}")
    
    number = float(match.group(1))
    suffix = match.group(2)
    
    # Apply multipliers
    multipliers = {
        'k': 1_000,
        'm': 1_000_000,
        'b': 1_000_000_000
    }
    
    multiplier = multipliers.get(suffix, 1)
    return number * multiplier

def calculate_mc_range(target_mc: float, cutoff: Optional[float]) -> tuple[float, float]:
    """
    Calculate market cap range based on target and cutoff
    
    Args:
        target_mc: Target market cap value
        cutoff: Optional cutoff value to create range
        
    Returns:
        tuple: (min_mc, max_mc)
    """
    if cutoff is None:
        # Return exact value for precise matching
        return (target_mc, target_mc)
    
    # Create range around target with cutoff
    min_mc = max(0, target_mc - cutoff)
    max_mc = target_mc + cutoff
    
    return (min_mc, max_mc)

def get_auto_tolerance(target_mc: float) -> float:
    """
    Calculate automatic tolerance based on target MC value
    
    Args:
        target_mc: Target market cap value
        
    Returns:
        float: Tolerance value
    """
    if target_mc >= 1_000_000_000:  # 1B+
        return target_mc * 0.001  # 0.1%
    elif target_mc >= 100_000_000:  # 100M+
        return target_mc * 0.002  # 0.2%
    elif target_mc >= 10_000_000:  # 10M+
        return target_mc * 0.005  # 0.5%
    elif target_mc >= 1_000_000:  # 1M+
        return target_mc * 0.01  # 1%
    elif target_mc >= 100_000:  # 100K+
        return target_mc * 0.02  # 2%
    else:  # Under 100K
        return target_mc * 0.05  # 5%

def parse_buy_amount_value(value: str) -> Optional[Dict[str, Any]]:
    """
    Parse buy amount value from string format
    
    Args:
        value: Buy amount string (e.g., "2 sol", "$150", "1.5 solana", "300 usd")
        
    Returns:
        Dict with 'amount', 'currency', 'original' or None
        
    Raises:
        ValueError: If value format is invalid
    """
    if not value:
        return None
    
    # Remove extra spaces and convert to lowercase
    value = value.strip().lower()
    original_value = value
    
    # Check for SOL variants
    sol_patterns = [
        r'^(\d+(?:\.\d+)?)\s*sol(?:ana)?$',  # "2 sol", "2.5 solana"
        r'^sol(?:ana)?\s*(\d+(?:\.\d+)?)$',  # "sol 2", "solana 2.5"
    ]
    
    for pattern in sol_patterns:
        match = re.match(pattern, value)
        if match:
            amount = float(match.group(1))
            return {
                'amount': amount,
                'currency': 'SOL',
                'original': original_value
            }
    
    # Check for USD variants
    usd_patterns = [
        r'^\$(\d+(?:\.\d+)?)$',  # "$150"
        r'^(\d+(?:\.\d+)?)\$$',  # "150$"
        r'^(\d+(?:\.\d+)?)\s*usd$',  # "150 usd"
        r'^(\d+(?:\.\d+)?)\s*dollars?$',  # "150 dollar", "150 dollars"
    ]
    
    for pattern in usd_patterns:
        match = re.match(pattern, value)
        if match:
            amount = float(match.group(1))
            return {
                'amount': amount,
                'currency': 'USD',
                'original': original_value
            }
    
    # Check for plain numbers
    number_match = re.match(r'^(\d+(?:\.\d+)?)$', value)
    if number_match:
        amount = float(number_match.group(1))
        # If less than 10, assume SOL, otherwise USD
        currency = 'SOL' if amount < 10 else 'USD'
        return {
            'amount': amount,
            'currency': currency,
            'original': original_value
        }
    
    raise ValueError(f"Invalid buy amount format: {value}")

def get_buy_amount_tolerance(amount: float, currency: str) -> float:
    """
    Calculate tolerance for buy amount filtering
    
    Args:
        amount: Buy amount value
        currency: Currency type ('SOL' or 'USD')
        
    Returns:
        float: Tolerance value
    """
    if currency == 'SOL':
        if amount >= 10:
            return amount * 0.15  # 15% tolerance for large SOL amounts
        elif amount >= 1:
            return amount * 0.25  # 25% tolerance for medium SOL amounts
        else:
            return amount * 0.4   # 40% tolerance for small SOL amounts
    else:  # USD
        if amount >= 10000:
            return amount * 0.1   # 10% tolerance for large USD amounts
        elif amount >= 1000:
            return amount * 0.15  # 15% tolerance for medium USD amounts
        elif amount >= 100:
            return amount * 0.25  # 25% tolerance for smaller USD amounts
        else:
            return amount * 0.4   # 40% tolerance for very small USD amounts