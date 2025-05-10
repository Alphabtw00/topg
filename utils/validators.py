"""
Validation utilities
"""
import re
import base58
from typing import Dict, Optional, Any
from cachetools import TTLCache, cached
from config import ADDRESS_REGEX_PATTERN, TICKER_REGEX_PATTERN, GITHUB_REPO_REGEX_PATTERN, WEBSITE_REGEX_PATTERN,  ADDRESS_CACHE_SIZE, ADDRESS_CACHE_TTL
from urllib.parse import urlparse
from utils.logger import get_logger

logger = get_logger()

# Compile regex patterns for efficiency
ADDRESS_REGEX = re.compile(ADDRESS_REGEX_PATTERN)
TICKER_REGEX = re.compile(TICKER_REGEX_PATTERN)
GITHUB_REPO_REGEX = re.compile(GITHUB_REPO_REGEX_PATTERN, re.IGNORECASE)
WEBSITE_REGEX = re.compile(WEBSITE_REGEX_PATTERN, re.IGNORECASE)

# Cache for address validation
ADDRESS_CACHE = TTLCache(maxsize=ADDRESS_CACHE_SIZE, ttl=ADDRESS_CACHE_TTL)

@cached(ADDRESS_CACHE)
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

def get_addresses_from_content(content: str) -> set:
    """
    Extract and validate Solana addresses from a string
    
    Args:
        content: String to analyze
        
    Returns:
        set: Set of valid Solana addresses
    """
    return {addr for addr in ADDRESS_REGEX.findall(content) if validate_solana_address(addr)}

def get_tickers_from_content(content: str) -> list:
    """
    Extract ticker symbols from a string
    
    Args:
        content: String to analyze
        
    Returns:
        list: List of ticker symbols without the $ prefix
    """
    return list(set(TICKER_REGEX.findall(content.lower())))

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