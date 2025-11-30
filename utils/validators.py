"""
Validation utilities
"""
import re
import discord
import base58
from typing import Dict, Optional, Any
from cachetools import TTLCache, cached, LRUCache
from config import GITHUB_REPO_REGEX_PATTERN, WEBSITE_REGEX_PATTERN, COMBINED_EXTRACTION_REGEX, ADDRESS_REGEX_PATTERN
from urllib.parse import urlparse
from utils.helper import fetch_channel_global
from utils.logger import get_logger
from functools import lru_cache


logger = get_logger()

# Compile regex patterns for efficiency
GITHUB_REPO_REGEX = re.compile(GITHUB_REPO_REGEX_PATTERN, re.IGNORECASE)
WEBSITE_REGEX = re.compile(WEBSITE_REGEX_PATTERN, re.IGNORECASE)


@lru_cache(maxsize=100)
def validate_solana_address(candidate: str) -> bool:
    """
    Validate if a string is a valid Solana address
    
    Args:
        candidate: String to validate
        
    Returns:
        bool: True if valid Solana address, False otherwise
    """
    try:
        return len(base58.b58decode(candidate)) == 32
    except Exception:
        return False
 
@lru_cache(maxsize=100)
def validate_github_url(url: str) -> bool:
    """
    Validate GitHub URL format.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not url:
        return False
        
    # Fast format check with compiled regex
    return bool(GITHUB_REPO_REGEX.search(url))

@lru_cache(maxsize=100)
def validate_url(url: str) -> bool:
    """
    Validate if a string is a valid URL
    
    Args:
        url: String to validate
        
    Returns:
        bool: True if valid URL, False otherwise
    """
    # Add http:// if missing
    if url and not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Fast regex check
    if not WEBSITE_REGEX.match(url):
        return False
    
    # More thorough validation
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def is_valid_webhook_url(url: str) -> bool:
    """Validate Discord webhook URL format"""
    if not url:
        return False
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        return "/api/webhooks/" in p.path and ("discord" in p.netloc or "discordapp" in p.netloc)
    except Exception:
        return False

async def validate_thread_for_webhook(thread_id: str, webhook_info: Dict, bot) -> Dict:
    result = {
        "ok": True,
        "warning": None,
        "display_name": None
    }

    if not thread_id:
        return result

    try:
        tid = int(thread_id)
    except ValueError:
        result["ok"] = False
        result["warning"] = "⚠️ Thread ID must be a numeric value."
        return result

    channel = await fetch_channel_global(bot, tid)
    if not channel:
        result["warning"] = "⚠️ Cannot verify thread. Bot may not be in the webhook's server."
        return result

    try:
        if not isinstance(channel, discord.Thread):
            result["ok"] = False
            result["warning"] = "⚠️ Provided ID is not a thread."
            return result

        result["display_name"] = f"🧵 {channel.name} (in #{channel.parent.name})"

        webhook_channel_id = webhook_info.get("channel_id")
        if webhook_channel_id and channel.parent_id != webhook_channel_id:
            result["ok"] = False
            result["warning"] = (
                f"⚠️ Thread **#{channel.name}** does not belong to the webhook's channel.\n"
                "Sending to this thread will fail. Use a thread from the same channel as the webhook."
            )
        return result
    except Exception as e:
        logger.error(f"Failed to validate thread for webhook: {e}", exc_info=True)
        result["warning"] = "⚠️ Error while validating thread."
        return result

@lru_cache(maxsize=100)
def extract_tickers_and_addresses_single_regex(content: str) -> tuple:
    """
    Ultra-fast single regex extraction
    """
    matches = COMBINED_EXTRACTION_REGEX.findall(content)
    
    tickers = set()
    addresses = []
    
    for ticker_match, addr_match in matches:
        if ticker_match:
            tickers.add(ticker_match[1:].lower())  # Remove $ and lowercase
        if addr_match:
            addresses.append(addr_match)
    
    # Validate addresses
    valid_addresses = []
    for addr in addresses:
        if validate_solana_address(addr):
            valid_addresses.append(addr)
    
    # Remove ticker duplicates
    unique_tickers = list(tickers)
    
    return valid_addresses, unique_tickers

def extract_addresses(content: str) -> list:
    """Extract only addresses - even faster for alerts"""
    matches = ADDRESS_REGEX_PATTERN.findall(content)
    return [addr for addr in matches if validate_solana_address(addr)]

def crypto_quick_check(content: str) -> bool:
    """Lightning fast - ~0.002-0.008ms"""
    # Check for $ first (most common)
    if '$' in content:
        return True
    
    # Quick length check - if message is too short, no CA possible
    if len(content) < 26:
        return False
    
    # Look for any 26+ char alphanumeric sequence
    current_alnum_count = 0
    for char in content:
        if char.isalnum():
            current_alnum_count += 1
            if current_alnum_count >= 26:
                return True
        else:
            current_alnum_count = 0
    
    return False

def extract_event_ticker(input_str: str) -> Optional[str]:
        """
        Extract event ticker from URL or direct input
        
        Args:
            input_str: URL or event ticker
            
        Returns:
            Event ticker in uppercase or None
        """
        # Check if it's a URL
        if "kalshi.com" in input_str.lower():
            # Extract from URL pattern: /markets/SERIES/title/EVENT-TICKER
            match = re.search(r'/markets/[^/]+/[^/]+/([^/?]+)', input_str)
            if match:
                return match.group(1).upper()
        
        # Otherwise treat as direct ticker input
        return input_str.strip().upper() 

async def parse_github_url(url: str) -> Optional[Dict[str, str]]:
    """
    Parse a GitHub URL into owner and repo components.

    Args:
        url: GitHub repository URL

    Returns:
        Dict with owner and repo or None if invalid.
    """
    if not url:
        return None

    url = url.strip()
    match = GITHUB_REPO_REGEX.search(url)
    if not match:
        return None

    owner, repo = match.groups()
    return {
        'owner': owner,
        'repo': repo
    }

def extract_scores(analysis: str) -> Dict[str, Any]:
    """
    Extract scores from analysis text.
    
    Args:
        analysis: Analysis text
        
    Returns:
        Dictionary with scores
    """
    score_pattern = re.compile(r'(?:Code Quality|Project Structure|Implementation|Documentation)\s*\(Score:\s*(\d+)\/25\)')
    scores = {}
    total_score = 0
    count = 0
    
    # Extract individual category scores
    for match in score_pattern.finditer(analysis):
        score = int(match.group(1))
        category = match.group(0).split('(')[0].strip().replace(' ', '').lower()
        scores[category] = score
        total_score += score
        count += 1
    
    # Calculate legitimacy percentage based only on technical scores
    technical_score = round((total_score / (count * 25)) * 100) if count > 0 else 0
    
    return {
        "detailedScores": {
            "codeQuality": scores.get("codequality", 0),
            "projectStructure": scores.get("projectstructure", 0),
            "implementation": scores.get("implementation", 0),
            "documentation": scores.get("documentation", 0)
        },
        "technicalScore": technical_score  # Pure technical score without trust factors
    }

def extract_code_review(analysis: str) -> Dict[str, Any]:
    """
    Extract code review sections from analysis with enhanced logging.
    
    Args:
        analysis: Analysis text
        
    Returns:
        Structured code review
    """
    # logger.debug("Beginning code review extraction...")
    
    # Initialize structure
    code_review = {
        "logicFlow": [],
        "processArchitecture": [],
        "codeOrganization": [],
        "criticalPath": [],
        "misrepresentationChecks": [],
        "larpIndicators": [],
        "redFlags": [],
        "overallAssessment": "",
        "projectSummary": "",
        "investmentRanking": {
            "rating": "",
            "confidence": 0,
            "reasoning": []
        },
        "aiAnalysis": {
            "hasAI": False,
            "components": [],
            "score": 0,
            "misleadingLevel": "None",
            "implementationQuality": "N/A",
            "concerns": [],
            "details": ""
        }
    }
    
    # Define regex patterns for sections
    sections = {
        "projectSummary": r'# Project Summary\n([\s\S]*?)(?=\n#|$)',
        "logicFlow": r'## Logic Flow\n([\s\S]*?)(?=\n##|$)',
        "processArchitecture": r'## Process Architecture\n([\s\S]*?)(?=\n##|$)',
        "codeOrganization": r'## Code Organization Review\n([\s\S]*?)(?=\n##|$)',
        "criticalPath": r'## Critical Path Analysis\n([\s\S]*?)(?=\n##|$)',
        "misrepresentationChecks": r'## Misrepresentation Checks\n([\s\S]*?)(?=\n##|$)',
        "larpIndicators": r'## LARP Indicators\n([\s\S]*?)(?=\n##|$)',
        "redFlags": r'## Red Flags\n([\s\S]*?)(?=\n##|$)',
        "overallAssessment": r'## Overall Assessment\n([\s\S]*?)(?=\n##|$)',
        "investmentRanking": r'## Investment Ranking \(NFA\)\n([\s\S]*?)(?=\n##|$)'
    }
    
    
    # Extract sections using regex with detailed logging
    for key, pattern in sections.items():
        try:
            match = re.search(pattern, analysis)
            if match:                
                if key == "overallAssessment":
                    code_review[key] = match.group(1).strip()

                elif key == "projectSummary":
                    code_review[key] = match.group(1).strip()

                elif key == "investmentRanking":
                    investment_section = match.group(1)
                    rating_match = re.search(r'Rating:\s*(.*?)(?:\n|$)', investment_section)
                    confidence_match = re.search(r'Confidence:\s*(\d+)%', investment_section)
                    
                    rating = rating_match.group(1).strip() if rating_match else ""
                    confidence = int(confidence_match.group(1)) if confidence_match else 0
                    
                    # Extract reasoning lines
                    reasoning_lines = [
                        line.strip().replace('- ', '') 
                        for line in investment_section.split('\n') 
                        if line.strip().startswith('-')
                    ]
                    
                    code_review[key] = {
                        "rating": rating,
                        "confidence": confidence,
                        "reasoning": reasoning_lines[:5]  # Limit to 5 reasons
                    }
                                        
                else:
                    # Extract bullet points
                    code_review[key] = [
                        line.strip().replace('- ', '')
                        for line in match.group(1).split('\n')
                        if line.strip().startswith('-')
                    ]                    
        except Exception as e:
            logger.error(f"Error processing section {key}: {str(e)}")
    
    # Process AI section separately
    try:
        ai_section = re.search(r'## AI Implementation Analysis\n([\s\S]*?)(?=\n##|$)', analysis)
        
        if ai_section:
            ai_text = ai_section.group(1)
            
            # Extract AI components
            components = [
                line.strip().replace('- ', '')
                for line in ai_text.split('\n')
                if line.strip().startswith('-')
            ]
            
            
            # Extract scores and ratings with detailed logging
            score_match = re.search(r'AI Score:\s*(\d+)', ai_text)
                
            misleading_match = re.search(r'Misleading Level:\s*(None|Low|Medium|High)', ai_text)
                
            quality_match = re.search(r'Implementation Quality:\s*(Poor|Basic|Good|Excellent)', ai_text)
            
            # AI concerns extraction
            concerns = [
                comp for comp in components
                if any(word in comp.lower() for word in ['concern', 'issue', 'misleading', 'problem'])
            ]
                        
            code_review["aiAnalysis"] = {
                "hasAI": bool(components),
                "components": components,
                "score": int(score_match.group(1)) if score_match else 0,
                "misleadingLevel": misleading_match.group(1) if misleading_match else "None",
                "implementationQuality": quality_match.group(1) if quality_match else "N/A",
                "concerns": concerns,
                "details": ai_text.strip()
            }
        else:
            logger.warning("No AI Implementation Analysis section found")
    except Exception as e:
        logger.error(f"Error processing AI section: {str(e)}")
    
    return code_review



   

