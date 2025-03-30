"""
GitHub repository analysis API client
"""
import aiohttp
import asyncio
from datetime import datetime
from utils.logger import get_logger
from typing import Dict, Any, Optional, List
from cachetools import TTLCache
from config import GITHUB_ANALYSIS_CACHE_SIZE, GITHUB_ANALYSIS_CACHE_TTL, GITHUB_MAX_FILES_TO_FETCH
from utils.validators import parse_github_url, extract_code_review, extract_scores
from utils.formatters import calculate_final_legitimacy_score, calculate_trust_score, calculate_verdict
from utils.helper import sanitize_code_content, get_file_extension

# Cache for GitHub analysis results
GITHUB_ANALYSIS_CACHE = TTLCache(maxsize=GITHUB_ANALYSIS_CACHE_SIZE, ttl=GITHUB_ANALYSIS_CACHE_TTL)

logger = get_logger()

async def analyze_github_repo(session: aiohttp.ClientSession, repo_url: str) -> Dict[str, Any]:
    """
    Main function to analyze a GitHub repository.
    
    Args:
        session: HTTP session
        repo_url: GitHub repository URL
        
    Returns:
        Analysis results or None on failure
    """
    # Import tokens from config if not provided
    from config import GITHUB_TOKEN, ANTHROPIC_API_KEY
    
    if not GITHUB_TOKEN:
        logger.error("GitHub token not found in configuration")
        return None
            
    if not ANTHROPIC_API_KEY:
        logger.error("Anthropic API key not found in configuration")
        return None
        
    repo_info = await parse_github_url(repo_url)
    if not repo_info:
        logger.warning(f"Could not parse the GitHub repository URL: {repo_url}")
        return None
    
    cache_key = f"{repo_info['owner'].lower()}/{repo_info['repo'].lower()}"
    
   # Check cache first using the normalized cache key
    if cache_key in GITHUB_ANALYSIS_CACHE:
        logger.debug(f"Serving cached analysis for {repo_url}")
        result = GITHUB_ANALYSIS_CACHE[cache_key]
        result['cached'] = True
        return result
    
    start_time = datetime.now()
    
    try:
        # Start both operations concurrently
        repo_details_task = asyncio.create_task(
            get_repo_details(session, repo_info, GITHUB_TOKEN)
        )
        
        files_task = asyncio.create_task(
            get_repo_contents(session, repo_info, GITHUB_TOKEN)
        )
        
        # Wait for both to complete
        repo_details, files = await asyncio.gather(repo_details_task, files_task)
        
        # Check results
        if not repo_details:
            logger.warning(f"Failed to get repo details for {repo_url}")
            return None
        
        
        # logger.info(f"Fetched {len(files)} files from {repo_info['owner']}/{repo_info['repo']}")
        
        # Analyze code
        # logger.info(f"Analyzing files from {repo_info['owner']}/{repo_info['repo']}")
        analysis = await analyze_repo_code(session, repo_details, files, ANTHROPIC_API_KEY)
        
        if not analysis:
            logger.warning(f"Analysis failed for {repo_url}")
            return None

        # Extract license information safely
        license_obj = repo_details.get('license')
        license_name = "No license"
        if license_obj and isinstance(license_obj, dict):
            license_name = license_obj.get('name', "No license")
        
        # Extract owner safely
        owner_obj = repo_details.get('owner', {})
        owner_login = "Unknown"
        owner_avatar = "https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png"
        
        if owner_obj and isinstance(owner_obj, dict):
            owner_login = owner_obj.get('login', "Unknown")
            owner_avatar = owner_obj.get('avatar_url', 
                           "https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png")
            
        # Prepare result with safe access to nested properties
        result = {
            'repo_info': {
                'name': repo_details.get('name', 'Unknown'),
                'owner': owner_login,
                'owner_avatar': owner_avatar,
                'stars': repo_details.get('stargazers_count', 0),
                'forks': repo_details.get('forks_count', 0),
                'watchers': repo_details.get('watchers_count', 0),
                'open_issues': repo_details.get('open_issues_count', 0),
                'language': repo_details.get('language', 'Unknown'),
                'size': repo_details.get('size', 0),
                'created_at': repo_details.get('created_at', 'Unknown'),
                'updated_at': repo_details.get('updated_at', 'Unknown'),
                'license': license_name
            },
            'analysis': analysis,
            'timestamp': datetime.now(),
            'cached': False
        }
        
        # Cache the result
        GITHUB_ANALYSIS_CACHE[cache_key] = result
        
        # Log performance metrics
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.debug(f"Analysis of {repo_url} completed in {elapsed_time:.2f}s")
        
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing repository {repo_url}: {str(e)}", exc_info=True)
        return None

async def get_repo_details(session: aiohttp.ClientSession, 
                           repo_info: Dict[str, str], 
                           github_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch repository details from GitHub API with improved error handling.
    
    Args:
        session: HTTP session for making requests
        repo_info: Dictionary with owner and repo
        github_token: GitHub API token
        
    Returns:
        Repository details or None on failure
    """
    if not repo_info or 'owner' not in repo_info or 'repo' not in repo_info:
        logger.error("Invalid repository info provided")
        return None
        
    owner, repo = repo_info['owner'], repo_info['repo']
    url = f"https://api.github.com/repos/{owner}/{repo}"
    
    # Set up headers with authentication
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'DiscordCryptoBot'
    }
    
    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
                
            if response.status == 404:
                logger.warning(f"Repository {owner}/{repo} not found")
                return None
                
            logger.warning(f"GitHub API returned status {response.status} for {owner}/{repo}")
            return None
            
    except aiohttp.ClientError as e:
        logger.error(f"HTTP error for {owner}/{repo}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting repo details: {str(e)}")
        return None

async def get_repo_contents(session: aiohttp.ClientSession, 
                           repo_info: Dict[str, str], 
                           github_token: str, 
                           max_files= GITHUB_MAX_FILES_TO_FETCH) -> List[Dict[str, Any]]:
    """
    Fetch repository contents using the Git Trees API for maximum efficiency.
    
    Args:
        session: HTTP session for making requests
        repo_info: Dictionary with owner and repo
        github_token: GitHub API token
        max_files: Maximum number of files to fetch
        
    Returns:
        List of files with contents
    """
    owner, repo = repo_info['owner'], repo_info['repo']
    
    # Set up headers
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'DiscordCryptoBot'
    }
    
    # Define file prioritization constants
    PRIORITY_FILES = [
        "readme.md", "package.json", "setup.py", "cargo.toml", 
        "gemfile", "composer.json", "build.gradle", "pom.xml",
        "main.js", "main.py", "index.js", "app.js", "app.py"
    ]
    
    # Get the main branch name first (could be main or master)
    async def get_default_branch():
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}"
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    repo_data = await response.json()
                    return repo_data.get('default_branch', 'main')
                return 'main'  # Default fallback
        except Exception:
            return 'main'  # Default fallback
    
    # Get all files in one request using the git/trees API with recursive=1
    async def get_repository_tree(branch):
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    tree_data = await response.json()
                    # Check if truncated - if so, log a warning
                    if tree_data.get('truncated', False):
                        logger.warning(f"Repository tree was truncated due to size for {owner}/{repo}")
                    return tree_data.get('tree', [])
                return []
        except Exception as e:
            logger.error(f"Error getting repository tree: {str(e)}")
            return []
    
    # Get content for a specific file using blob URL
    async def get_blob_content(blob_url, path):
        try:
            async with session.get(blob_url, headers=headers) as response:
                if response.status == 200:
                    blob_data = await response.json()
                    content = blob_data.get('content', '')
                    encoding = blob_data.get('encoding', '')
                    
                    if encoding == 'base64':
                        import base64
                        try:
                            decoded = base64.b64decode(content).decode('utf-8', errors='replace')
                            return {
                                'path': path,
                                'content': sanitize_code_content(decoded)
                            }
                        except Exception as e:
                            logger.error(f"Error decoding content for {path}: {str(e)}")
                return None
        except Exception as e:
            logger.error(f"Error fetching blob content for {path}: {str(e)}")
            return None
    
    # Helper function to prioritize files
    def prioritize_files(files):
        # First, extract just the files (not directories)
        file_items = [f for f in files if f.get('type') == 'blob']
        
        # Helper functions for sorting
        def is_priority_file(path):
            lower_path = path.lower()
            return any(lower_path.endswith(p.lower()) for p in PRIORITY_FILES)
        
        def get_depth(path):
            return path.count('/')
        
        def has_priority_extension(path):
            extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.sol', '.go', '.rs', 
                         '.java', '.md', '.json', '.yml', '.yaml']
            ext = '.' + path.split('.')[-1].lower() if '.' in path else ''
            return ext in extensions
        
        # Sort by multiple criteria
        sorted_files = sorted(file_items, key=lambda f: (
            not is_priority_file(f['path']),  # Priority files first
            get_depth(f['path']),             # Files in root directory next
            not has_priority_extension(f['path']),  # Files with priority extensions next
            f['path']                         # Alphabetical for stability
        ))
        
        return sorted_files[:max_files]  # Return only up to max_files
    
    # Execute the actual workflow
    try:
        # Get default branch first
        branch = await get_default_branch()
        
        # Get the full tree
        tree = await get_repository_tree(branch)
        if not tree:
            # Try alternate branch if the first attempt fails
            alternate_branch = 'main' if branch != 'main' else 'master'
            tree = await get_repository_tree(alternate_branch)
            if not tree:
                logger.warning(f"Could not fetch tree for {owner}/{repo}")
                return []
        
        # Prioritize files and limit to max_files
        prioritized_files = prioritize_files(tree)
        
        # Fetch content for prioritized files in parallel
        content_tasks = []
        for file in prioritized_files:
            blob_url = file.get('url')
            if blob_url:
                content_tasks.append(get_blob_content(blob_url, file.get('path')))
        
        # Execute all content fetches in parallel
        contents = await asyncio.gather(*content_tasks)
        
        # Filter out None results
        return [c for c in contents if c]
        
    except Exception as e:
        logger.error(f"Error in get_repo_contents: {str(e)}")
        return []

async def analyze_repo_code(session: aiohttp.ClientSession, 
                           repo_info: Dict[str, Any], 
                           files: List[Dict[str, str]],
                           anthropic_api_key: str) -> Dict[str, Any]:
    """
    Analyze repository code using Anthropic Claude API with improved error handling.
    
    Args:
        session: HTTP session
        repo_info: Repository information
        files: Repository file contents
        anthropic_api_key: Anthropic API key
        
    Returns:
        Analysis results
    """
    # logger.info(f"Analyzing {len(files)} files with total size: {sum(len(f.get('content', '')) for f in files)} characters")

    # Prepare analysis prompt
    code_content = "\n".join([
        f"File: {file['path']}\n```{get_file_extension(file['path'])}\n{file['content']}\n```"
        for file in files
    ])

    analysis_prompt = f"""# Analysis Categories

## Code Quality (Score: [0-25]/25)
- Architecture patterns and design principles
- Code organization and modularity
- Error handling and resilience
- Performance optimization
- Best practices adherence

## Project Structure (Score: [0-25]/25)
- Directory organization
- Dependency management
- Configuration approach
- Build system
- Resource organization

## Implementation (Score: [0-25]/25)
- Core functionality implementation
- API integrations and interfaces
- Data flow and state management
- Security practices
- Code efficiency and scalability

## Documentation (Score: [0-25]/25)
- Code comments and documentation
- API documentation
- Setup instructions
- Architecture documentation
- Usage examples and guides

## Misrepresentation Checks
- Check for code authenticity
- Verify claimed features
- Validate technical claims
- Cross-reference documentation

## LARP Indicators
- Code implementation depth
- Feature completeness
- Development history
- Technical consistency

## Red Flags
- Security concerns
- Implementation issues
- Documentation gaps
- Architectural problems

## Overall Assessment
Provide a comprehensive evaluation of the project's technical merit, implementation quality, and potential risks.

## Investment Ranking (NFA)
Rating: [High/Medium/Low]
Confidence: [0-100]%
- Include key factors influencing the rating
- List major considerations
- Note potential risks and opportunities

## AI Implementation Analysis
- Identify and list any AI/ML components
- Evaluate implementation quality and correctness
- Check for misleading AI claims
- Assess model integration and usage
- Verify data processing methods
- Compare claimed vs actual AI capabilities
- Note any AI-related security concerns
- Check for proper model attribution
- Evaluate AI performance considerations

Rate the AI implementation if present:
AI Score: [0-100]
Misleading Level: [None/Low/Medium/High]
Implementation Quality: [Poor/Basic/Good/Excellent]

Provide specific examples and evidence for any AI-related findings.

# Repository Details
Repository: {repo_info.get('full_name', 'Unknown')}
Description: {repo_info.get('description', 'N/A')}
Language: {repo_info.get('language', 'Unknown')}
Stars: {repo_info.get('stargazers_count', 0)}

# Code Review
{code_content}

# Technical Assessment

## AI Implementation Analysis
- Identify any AI/ML components
- Verify implementation correctness
- Evaluate model integration
- Assess data processing
- Validate AI claims against code

## Logic Flow
- Core application flow
- Data processing patterns
- Control flow architecture
- Error handling paths

## Process Architecture
- System components
- Service interactions
- Scalability approach
- Integration patterns

## Code Organization Review
- Module structure
- Dependency patterns
- Code reusability
- Architecture patterns

## Critical Path Analysis
- Performance bottlenecks
- Security considerations
- Scalability challenges
- Technical debt

Provide scores as "Score: X/25" format. Include specific code examples to support findings."""

    # logger.info(f"Analysis prompt size: {len(analysis_prompt)} characters")

    # Make Anthropic API request
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": anthropic_api_key,
        "anthropic-version": "2023-06-01"
    }
    
    analysis_request = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 4000, #todo add from config
        "temperature": 0.3,
        "messages": [
            {
                "role": "user",
                "content": f"You are a technical code reviewer. Analyze this repository and provide a detailed assessment. Start directly with the scores and analysis without any introductory text.\n\n{analysis_prompt}"
            }
        ]
    }
    
    # Implement retry mechanism with increasing timeouts
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # logger.info(f"Making Anthropic API request with model claude-3-5-sonnet (attempt {attempt+1}/{max_retries})")
            
            # Create a custom timeout that increases with each retry
            timeout = aiohttp.ClientTimeout(
                total=240,              # Overall timeout in seconds (4 minutes)
                connect=30,             # Connection timeout
                sock_connect=30,        # Socket connection timeout
                sock_read=180 + 60*attempt  # Socket read timeout increases with each retry
            )
            
            # Create a new ClientSession with our custom timeout just for this request
            async with aiohttp.ClientSession(timeout=timeout) as request_session:
                async with request_session.post(url, json=analysis_request, headers=headers) as response:
                    # logger.info(f"Received response with status {response.status}")
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Anthropic API error: {response.status} - {error_text}")
                        
                        # If rate limited, wait and retry
                        if response.status == 429 and attempt < max_retries - 1:
                            wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                            # logger.info(f"Rate limited, waiting {wait_time}s before retry")
                            await asyncio.sleep(wait_time)
                            continue
                            
                        return None
                    
                    # Read the response with explicit timeout handling
                    try:
                        response_data = await response.json()
                        
                        # Get analysis text from response
                        analysis = response_data.get("content", [{}])[0].get("text", "")
                        if not analysis:
                            logger.error("Received empty analysis from Claude API")
                            return None
                                                    
                        # Extract technical scores without penalties
                        try:
                            scores = extract_scores(analysis)
                            if scores is None:
                                logger.error("Failed to extract scores from analysis")
                                return None
                        except Exception as e:
                            logger.error(f"Error extracting scores: {str(e)}")
                            return None
                        
                        # Extract code review info
                        try:
                            code_review = extract_code_review(analysis)
                            if code_review is None:
                                logger.error("Failed to extract code review from analysis")
                                return None
                        except Exception as e:
                            logger.error(f"Error extracting code review: {str(e)}")
                            return None
                        
                        # Calculate trust score with detailed penalty breakdown
                        try:
                            trust_result = calculate_trust_score(code_review)
                            if trust_result is None:
                                logger.error("Failed to calculate trust score")
                                return None
                        except Exception as e:
                            logger.error(f"Error calculating trust score: {str(e)}")
                            return None
                        
                        # Calculate final verdict that combines technical merit and trust
                        technical_score = scores.get("technicalScore", 0)
                        trust_score = trust_result.get("score", 0)
                        
                        # Calculate legitimacy by combining technical score and trust score
                        try:
                            legitimacy_score = calculate_final_legitimacy_score(technical_score, trust_score)
                        except Exception as e:
                            logger.error(f"Error calculating legitimacy score: {str(e)}")
                            legitimacy_score = round((technical_score + trust_score) / 2)  # Fallback calculation
                        
                        # Calculate verdict with clear weighted factors - handle both function signatures
                        try:
                            # Try the 3-argument version first
                            verdict = calculate_verdict({
                                "technicalScore": technical_score
                            }, trust_result, code_review)
                        except TypeError:
                            try:
                                # If that fails, try the 1-argument version
                                verdict = calculate_verdict({
                                    "technicalScore": technical_score,
                                    "trustScore": trust_score,
                                    "codeReview": code_review
                                })
                            except Exception as e:
                                logger.error(f"Error calculating verdict: {str(e)}")
                                # Provide a default verdict as fallback
                                verdict = {
                                    "color": 0x00FF00,
                                    "verdict": "INVESTMENT RECOMMENDED",
                                    "emoji": "✅",
                                    "investment_advice": "Analysis completed, but verdict calculation failed."
                                }
                        
                        # Generate a concise summary
                        try:
                            summary = await generate_summary(session, analysis, anthropic_api_key)
                        except Exception as e:
                            logger.error(f"Error generating summary: {str(e)}")
                            summary = "Summary generation failed, but analysis is available."
                        
                        # Combine all results
                        logger.debug("Analysis completed successfully, returning results")
                        return {
                            "detailedScores": scores.get("detailedScores", {}),
                            "technicalScore": technical_score,
                            "trustScore": trust_score,
                            "legitimacyScore": legitimacy_score,
                            "codeReview": code_review,
                            "trustDetails": trust_result,
                            "verdict": verdict,  # Include pre-calculated verdict
                            "fullAnalysis": analysis,
                            "summary": summary
                        }
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout while reading response (attempt {attempt+1}/{max_retries})")
                        if attempt < max_retries - 1:
                            continue
                        return None
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout connecting to Claude API (attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                # Wait before retry with exponential backoff
                wait_time = 2 ** attempt  # 1, 2, 4 seconds
                await asyncio.sleep(wait_time)
                continue
            return None
            
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error during Claude API request: {str(e)} (attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error during code analysis: {str(e)}")
            return None
    
    # If we get here, all retries failed
    logger.error("All retry attempts failed for code analysis")
    return None

async def generate_summary(session: aiohttp.ClientSession, 
                          analysis: str, 
                          anthropic_api_key: str) -> str:
    """
    Generate a summary of the analysis.
    
    Args:
        session: HTTP session
        analysis: Full analysis text
        anthropic_api_key: Anthropic API key
        
    Returns:
        Concise summary
    """
    # Truncate analysis for summary generation
    truncated_analysis = analysis[:15000]
    
    summary_prompt = f"""Given this technical analysis, tell me what's most interesting and notable about this repository in 1-2 conversational sentences. Focus on unique features, technical achievements, or interesting implementation details. Be specific but natural in tone:

{truncated_analysis}

Remember to highlight what makes this repo special or noteworthy from a technical perspective."""

    # Make Anthropic API request
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": anthropic_api_key,
        "anthropic-version": "2023-06-01"
    }
    
    summary_request = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 300, #todo add from config
        "temperature": 0.7,
        "messages": [
            {
                "role": "user",
                "content": summary_prompt
            }
        ]
    }
    
    try:
        async with session.post(url, json=summary_request, headers=headers) as response:
            if response.status != 200:
                return "No summary available"
                
            response_data = await response.json()
            return response_data.get("content", [{}])[0].get("text", "").strip()
            
    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        return "No summary available"
        
def clear_repo_from_cache(repo_url: str) -> bool:
    """
    Clear a specific repository from the analysis cache
    
    Args:
        repo_url: GitHub repository URL
        
    Returns:
        bool: True if the repo was in cache and cleared, False otherwise
    """
    try:
        # Parse the repo URL to get owner/repo format
        repo_info = parse_github_url(repo_url)
        if not repo_info:
            return False
            
        # Generate the cache key in the same format used for storage
        cache_key = f"{repo_info['owner'].lower()}/{repo_info['repo'].lower()}"
        
        # Check if the key exists before removing
        if cache_key in GITHUB_ANALYSIS_CACHE:
            GITHUB_ANALYSIS_CACHE.pop(cache_key)
            return True
            
        return False
    except Exception as e:
        logger.error(f"Error clearing repo from cache: {str(e)}")
        return False