# service/nword_service.py (update the entire file)
"""
N-word tracking service - Zero-overhead word detection
"""
import re
from typing import Optional
import repository.nword_tracking_repo as nword_db
from utils.logger import get_logger
from config import ENABLE_NWORD_TRACKING, NWORD_TARGET_WORDS

logger = get_logger()

# Compile regex pattern for all words at module load for maximum speed
# Creates pattern like: \b(neighbour|neighborhood)\b
_WORD_PATTERN = None
if ENABLE_NWORD_TRACKING and NWORD_TARGET_WORDS:
    escaped_words = [re.escape(word.lower()) for word in NWORD_TARGET_WORDS]
    pattern_string = r'\b(' + '|'.join(escaped_words) + r')\b'
    _WORD_PATTERN = re.compile(pattern_string, re.IGNORECASE)

def count_word_occurrences(text: str) -> int:
    """
    Ultra-fast word counting using pre-compiled regex
    
    Args:
        text: Message content to check
        
    Returns:
        Number of occurrences found (counts all tracked words)
    """
    if not ENABLE_NWORD_TRACKING or not text or not _WORD_PATTERN:
        return 0
    
    return len(_WORD_PATTERN.findall(text))

async def process_message_for_nword(user_id: int, guild_id: int, content: str) -> None:
    """
    Process message for N-word tracking - fire and forget
    
    Args:
        user_id: Discord user ID
        guild_id: Discord guild ID
        content: Message content
    """
    if not ENABLE_NWORD_TRACKING:
        return
    
    count = count_word_occurrences(content)
    if count > 0:
        # to prevent spam, only counts 3 per message
        count = min(count, 3)
        await nword_db.increment_count(user_id, guild_id, count)