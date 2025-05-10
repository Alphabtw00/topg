"""
GitHub repository analyzer
"""
import asyncio
import aiohttp
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import re
from api.client import ApiClient, ApiEndpoint
from utils.logger import get_logger
from utils.validators import validate_github_url, parse_github_url, extract_scores, extract_code_review
from utils.formatters import calculate_trust_score, calculate_verdict, calculate_final_legitimacy_score
from utils.helper import sanitize_code_content, get_file_extension
from cachetools import TTLCache
from config import (
    GITHUB_ANALYSIS_CACHE_SIZE, GITHUB_ANALYSIS_CACHE_TTL, 
    GITHUB_MAX_FILES_TO_FETCH, GITHUB_TOKEN, ANTHROPIC_API_KEY
)

# Cache for GitHub analysis results
GITHUB_ANALYSIS_CACHE = TTLCache(maxsize=GITHUB_ANALYSIS_CACHE_SIZE, ttl=GITHUB_ANALYSIS_CACHE_TTL)

logger = get_logger()

class GitHubAnalyzer:
    """Analyzer for GitHub repositories"""
    
    def __init__(self, api_client: ApiClient):
        """Initialize with API client"""
        self.client = api_client
    
    async def analyze_repo(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """
        Analyze a GitHub repository for legitimacy
        
        Args:
            repo_url: GitHub repository URL
            
        Returns:
            dict or None: Analysis result or None if analysis failed
        """
        # Remove trailing slash if present for consistency
        repo_url = repo_url.rstrip("/")
        
        # Parse the GitHub URL
        repo_info = await parse_github_url(repo_url)
        if not repo_info:
            logger.warning(f"Failed to parse GitHub URL: {repo_url}")
            return None
            
        owner = repo_info["owner"]
        repo = repo_info["repo"]
        
        # Generate cache key
        cache_key = f"{owner.lower()}/{repo.lower()}"
        
        # Check cache first
        if cache_key in GITHUB_ANALYSIS_CACHE:
            logger.info(f"Serving cached analysis for {repo_url}")
            cached_result = GITHUB_ANALYSIS_CACHE[cache_key]
            cached_result['cached'] = True
            return cached_result
        
        try:
            # Fetch repository information
            repo_info_task = self._fetch_repo_info(owner, repo)
            repo_contents_task = self._fetch_repo_contents(owner, repo)

            # Await both tasks
            repo_details, repo_contents = await asyncio.gather(repo_info_task, repo_contents_task)

            # Check if repo_details failed
            if not repo_details:
                logger.warning(f"Failed to fetch repository info for {owner}/{repo}")
                return None
            
            # Analyze repository code
            code_analysis = await self._analyze_code(repo_details, repo_contents)
            
            if not code_analysis:
                logger.warning(f"Analysis failed for {repo_url}")
                return None

            # Calculate scores
            scores = extract_scores(code_analysis)
            code_review = extract_code_review(code_analysis)
            
            # Calculate trust score
            trust_result = calculate_trust_score(code_review)
            trust_score = trust_result["score"]
            
            # Calculate final legitimacy score
            technical_score = scores.get("technicalScore", 0)
            legitimacy_score = calculate_final_legitimacy_score(technical_score, trust_score)
            
            # Determine final verdict
            verdict = calculate_verdict(scores, trust_result, code_review)
            
            
            # Create full analysis result
            analysis_result = {
                "legitimacyScore": legitimacy_score,
                "trustScore": trust_score,
                "technicalScore": technical_score,
                "detailedScores": scores["detailedScores"],
                "codeReview": code_review,
                "verdict": verdict
            }
            
            # Prepare result for caching
            result = {
                "repo_info": repo_details,
                "analysis": analysis_result,
                "timestamp": datetime.now().timestamp(),
                "cached": False
            }
            
            # Cache the result
            GITHUB_ANALYSIS_CACHE[cache_key] = result
            
            return result
            
        except aiohttp.ClientError as ce:
            logger.warning(f"HTTP error during repo analysis for {repo_url}: {str(ce)}")
            return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout during repo analysis for {repo_url}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during repo analysis for {repo_url}: {str(e)}", exc_info=True)
            return None
    
    async def _fetch_repo_info(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """
        Fetch repository information from GitHub API
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            dict or None: Repository information or None if failed
        """
        url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        try:
            data = await self.client.get(
                url, 
                ApiEndpoint.GITHUB,
                headers=headers
            )
            
            if not data:
                return None
                
            # Extract relevant information
            return {
                "name": data.get("name", "Unknown"),
                "owner": data.get("owner", {}).get("login", "Unknown"),
                "owner_avatar": data.get("owner", {}).get("avatar_url", "https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png"),
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "watchers": data.get("watchers_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "language": data.get("language", "Unknown"),
                "size": data.get("size", 0),
                "created_at": data.get("created_at", "Unknown"),
                "updated_at": data.get("updated_at", "Unknown"),
                "license": data.get("license", {}).get("name", "No license") if data.get("license") else "No license",
                "description": data.get("description", "No description"),
                "full_name": data.get("full_name", f"{owner}/{repo}")
            }
        except Exception as e:
            logger.error(f"Error fetching repo info for {owner}/{repo}: {e}")
            return None
    
    async def _fetch_repo_contents(self, owner: str, repo: str):
        """Fetch repository contents efficiently for all repository sizes"""
        
        # First, get the default branch from repo info API
        repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        
        try:
            # Get repo info to check default branch
            repo_data = await self.client.get(repo_api_url, ApiEndpoint.GITHUB, headers=headers)
            default_branch = repo_data.get("default_branch", "main")
            
            # Use Git Tree API to get all files in one request (MAJOR performance boost)
            tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
            tree_data = await self.client.get(tree_url, ApiEndpoint.GITHUB, headers=headers)
            
            if not tree_data or "tree" not in tree_data:
                logger.warning(f"Tree API failed for {owner}/{repo}")
                return []
                
            # Filter for code files we're interested in
            code_files = []
            for item in tree_data["tree"]:
                if item["type"] == "blob":  # It's a file
                    path = item.get("path", "")
                    
                    # Skip unwanted files/dirs
                    if any(excluded in path.lower() for excluded in [
                        'node_modules/', '.git/', 'dist/', 'build/', '.venv/', 'venv/',
                        '.jpg', '.png', '.gif', '.pdf', '.zip', '.exe', '.dll', '.so', '.min.js',
                        '.lock', '.map', '.md5', '.woff', '.woff2', '.ttf', '.eot'
                    ]):
                        continue
                        
                    # Check extensions
                    ext = path.split(".")[-1].lower() if "." in path else ""
                    if ext in ['js', 'jsx', 'ts', 'tsx', 'py', 'sol', 'java', 'go', 'rs', 'c', 'cpp', 'php']:
                        code_files.append(item)
            
            # Smart file sorting for all repository types
            def file_sort_key(item):
                path = item.get("path", "").lower()
                file_name = path.split('/')[-1]
                
                # 1. Essential project files
                essential_files = ['readme.md', 'package.json', 'setup.py', 'cargo.toml', 
                                'gemfile', 'requirements.txt', 'compose.yaml', 'dockerfile']
                if file_name.lower() in essential_files:
                    return 0
                    
                # 2. Main entry points
                main_files = ['index.js', 'main.py', 'app.js', 'app.py', 'server.js', 
                            'main.go', 'main.rs', 'main.c', 'main.cpp', 'Main.java']
                if file_name in main_files:
                    return 1
                    
                # 3. Root-level important files
                if '/' not in path:
                    return 2
                    
                # 4. Core source files (usually in src/lib/core directories)
                if any(f'/{dir}/' in f'/{path}/' for dir in ['src', 'lib', 'core', 'app']):
                    return 3
                    
                # 5. Config files (usually important)
                config_files = ['config', 'settings', '.env.example']
                if any(config in file_name for config in config_files):
                    return 4
                    
                # 6. Everything else
                return 5
                    
            code_files.sort(key=file_sort_key)
                    
            # Limit to max files
            selected_files = code_files[:GITHUB_MAX_FILES_TO_FETCH]
            
            # Fetch file contents in parallel with a small concurrency limit to avoid rate limiting
            semaphore = asyncio.Semaphore(10)  # Max 5 concurrent requests
            
            async def fetch_file(file_path):
                async with semaphore:  # Limit concurrent requests
                    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
                    content = await self._fetch_file_content(url)
                    return {
                        "name": file_path.split("/")[-1],
                        "path": file_path,
                        "type": "file",
                        "content": content,
                        "extension": get_file_extension(file_path)
                    } if content else None
            
            # Gather all file content requests in parallel
            contents = await asyncio.gather(
                *[fetch_file(item["path"]) for item in selected_files]
            )
            
            # Filter out None results
            valid_contents = [c for c in contents if c]
            
            # Log success
            logger.debug(f"Successfully fetched {len(valid_contents)} files from {owner}/{repo}")
            
            return valid_contents
            
        except Exception as e:
            logger.error(f"Error fetching repo contents for {owner}/{repo}: {e}")
            return []
    
    async def _fetch_file_content(self, url: str) -> Optional[str]:
        """
        Fetch file content from GitHub API
        
        Args:
            url: File URL
            
        Returns:
            str or None: File content or None if failed
        """
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        try:
            data = await self.client.get(
                url, 
                ApiEndpoint.GITHUB,
                headers=headers
            )
            
            if not data or "content" not in data:
                return None
                
            import base64
            content = data["content"]
            content = content.replace('\n', '')  # Remove any newlines in the base64 encoding
            
            # Decode content and sanitize it
            decoded = base64.b64decode(content).decode('utf-8', errors='replace')
            return sanitize_code_content(decoded)  # Use the helper function
            
        except Exception as e:
            logger.error(f"Error fetching file content: {e}")
            return None
    
    async def _analyze_code(self, repo_info: Dict[str, Any], 
                          repo_contents: List[Dict[str, Any]]) -> Optional[str]:
        """
        Analyze repository code using Claude API
        
        Args:
            repo_info: Repository information
            repo_contents: Repository file contents
            
        Returns:
            str: Analysis results in structured format
        """
        # Prepare code content for analysis
        code_content = "\n".join([
            f"File: {file['path']}\n```{file['extension']}\n{file['content']}\n```"
            for file in repo_contents
        ])

        analysis_prompt = f"""# Project Summary
Tell me what's most interesting and notable about this repository in 1-2 conversational sentences. Focus on unique features, technical achievements, or interesting implementation details. Be specific but natural in tone. Remember to highlight what makes this repo special or noteworthy from a technical perspective.

# Analysis Categories

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
Stars: {repo_info.get('stars', 0)}

# Code Review
{code_content}

# Technical Assessment

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

        # Make Anthropic API request
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        }
        
        analysis_request = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 4000,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "user",
                    "content": f"You are a technical code reviewer. Analyze this repository and provide a detailed assessment. Start directly with the Project Summary, followed by the scores and analysis without any introductory text.\n\n{analysis_prompt}"
                }
            ]
        }
        
        # Implement retry mechanism with increasing timeouts
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Create a timeout that increases with each retry
                timeout = 240 + 60 * attempt  # 4 minutes + 1 minute per retry
                
                response_data = await self.client.post(
                    url, 
                    ApiEndpoint.GITHUB,
                    json_data=analysis_request,
                    headers=headers,
                    timeout=timeout
                )
                
                if not response_data:
                    logger.error("Empty response from Claude API")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    return None
                
                # Get analysis text from response
                analysis = response_data.get("content", [{}])[0].get("text", "")
                if not analysis:
                    logger.error("Received empty analysis from Claude API")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return None
                
                return analysis
                
            except asyncio.TimeoutError:
                logger.error(f"Timeout connecting to Claude API (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
                
            except Exception as e:
                logger.error(f"Unexpected error during code analysis: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
        
        # If we get here, all retries failed
        logger.error("All retry attempts failed for code analysis")
        return None
    
    async def clear_from_cache(self, repo_url: str) -> bool:
        """
        Clear a specific repository from the analysis cache
        
        Args:
            repo_url: GitHub repository URL
            
        Returns:
            bool: True if found and cleared, False otherwise
        """
        try:
            repo_info = await parse_github_url(repo_url)
            if not repo_info:
                return False
                
            # Generate the cache key 
            cache_key = f"{repo_info['owner'].lower()}/{repo_info['repo'].lower()}"
            
            if cache_key in GITHUB_ANALYSIS_CACHE:
                GITHUB_ANALYSIS_CACHE.pop(cache_key)
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error clearing repo from cache: {str(e)}")
            return False