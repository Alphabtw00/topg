"""
GitHub repository analysis API client
"""
import aiohttp
from datetime import datetime
from utils.cache import GITHUB_ANALYSIS_CACHE
from api.http_client import fetch_data_post
from utils.logger import get_logger

logger = get_logger()

async def analyze_github_repo(session: aiohttp.ClientSession, repo_url: str):
    """
    Analyze a GitHub repository for legitimacy
    
    Args:
        session: HTTP session
        repo_url: GitHub repository URL
        
    Returns:
        dict or None: Analysis result or None if analysis failed
    """
    # Remove trailing slash if present for consistency
    repo_url = repo_url.rstrip("/")
    
    # Check cache first - efficient memory usage
    if repo_url in GITHUB_ANALYSIS_CACHE:
        logger.info(f"Serving cached analysis for {repo_url}")
        return GITHUB_ANALYSIS_CACHE[repo_url]
    
    try:
        # Make the API request to the external analysis service
        data = await fetch_data_post(
            session,
            "http://localhost:3000/api/analyze",
            json_data={"repoUrl": repo_url},
            timeout=180  # Increased timeout for large repos
        )
        
        if not data or not data.get("success"):
            error_msg = data.get('error', 'Unknown error') if data else "No data returned"
            logger.error(f"API reported failure for {repo_url}: {error_msg}")
            return None
            
        # Extract result and cache it
        result = data["result"]
        
        # Extract repository info and analysis
        repo_info = _extract_repo_info(result)
        analysis = result["analysis"]
        
        # Cache the repository info and analysis
        cached_result = {
            'repo_info': repo_info,
            'analysis': analysis,
            'timestamp': datetime.now()
        }
        
        GITHUB_ANALYSIS_CACHE[repo_url] = cached_result
        return cached_result
        
    except Exception as e:
        logger.error(f"Repo analysis error for {repo_url}: {str(e)}")
        return None

def _extract_repo_info(result):
    """
    Extract repository info from API result, handling both cached and non-cached responses
    
    Args:
        result: API result data
        
    Returns:
        dict: Structured repository info
    """
    repo_info = {}
    
    if "repoDetails" in result:
        # First-time API response with full details
        repo_details = result["repoDetails"]
        
        repo_info["name"] = repo_details.get("name", "Unknown")

        owner = repo_details.get("owner", {})
        repo_info["owner"] = owner.get("login", "Unknown")
        repo_info["owner_avatar"] = owner.get("avatar_url", "https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png")
        
        # Repository stats
        repo_info["stars"] = repo_details.get("stargazers_count", 0)
        repo_info["forks"] = repo_details.get("forks_count", 0)
        repo_info["watchers"] = repo_details.get("watchers_count", 0)
        repo_info["open_issues"] = repo_details.get("open_issues_count", 0)
        repo_info["language"] = repo_details.get("language", "Unknown")
        repo_info["size"] = repo_details.get("size", 0)
        
        # Dates
        repo_info["created_at"] = repo_details.get("created_at", "Unknown")
        repo_info["updated_at"] = repo_details.get("updated_at", "Unknown")
        
        # License
        license_info = repo_details.get("license", {})
        repo_info["license"] = license_info.get("name", "No license") if license_info else "No license"
    
    else:
        # Cached API response with limited details - extract what we can
        repo_info["name"] = result.get("repoName", "Unknown")
        repo_info["owner"] = result.get("owner", "Unknown")
        repo_info["stars"] = result.get("stars", 0)
        repo_info["forks"] = result.get("forks", 0)
        repo_info["language"] = result.get("language", "Unknown")
        
        # Set defaults for missing fields
        repo_info["owner_avatar"] = "https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png"
        repo_info["watchers"] = 0
        repo_info["open_issues"] = 0
        repo_info["size"] = 0
        repo_info["created_at"] = "Unknown"
        repo_info["updated_at"] = "Unknown"
        repo_info["license"] = "Unknown"
    
    return repo_info

def clear_repo_from_cache(repo_url: str):
    """
    Clear a specific repository from the analysis cache
    
    Args:
        repo_url: GitHub repository URL
    """
    repo_url = repo_url.rstrip("/")  # Normalize URL
    GITHUB_ANALYSIS_CACHE.pop(repo_url, None)