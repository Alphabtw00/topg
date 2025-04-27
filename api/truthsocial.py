"""
Truth Social API service with improved Cloudflare handling
"""
import time
import asyncio
import random
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
from utils.logger import get_logger
from curl_cffi import requests as curl_requests
from config import (
    TRUTH_ACCOUNTS,
    TRUTH_DEFAULT_INTERVAL
)

logger = get_logger()

# Constants
BASE_URL = "https://truthsocial.com"
API_BASE_URL = "https://truthsocial.com/api"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

# OAuth client credentials from Truth Social
CLIENT_ID = "9X1Fdd-pxNsAgEDNi_SfhJWi8T-vLuV2WVzKIbkTCw4"
CLIENT_SECRET = "ozF8jzI4968oTKFkEnsBC-UbLPCdrSv0MkXGQu2o_-M"

class TruthSocialService:
    """Service for Truth Social API interactions"""
    
    def __init__(self, api_client):
        """Initialize with API client"""
        self.api_client = api_client
        self.auth_tokens = {}  # Map username to token
        self.current_account_index = 0
        self.account_last_used = {}  # Track when account was last used
        self.account_rate_limited_until = {}  # Store timestamps when rate limits expire
        self.MIN_ACCOUNT_USAGE_INTERVAL = 2  # seconds between account usage
    
    async def setup(self):
        """Set up the service by authenticating all accounts"""
        if not TRUTH_ACCOUNTS:
            logger.error("No Truth Social accounts configured")
            return False
            
        # Pre-authenticate all accounts
        logger.info(f"Setting up {len(TRUTH_ACCOUNTS)} Truth Social accounts...")
        tasks = []
        for account in TRUTH_ACCOUNTS:
            tasks.append(self._authenticate_account(account))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful authentications
        success_count = sum(1 for result in results if result is True)
        logger.info(f"Successfully authenticated {success_count}/{len(TRUTH_ACCOUNTS)} Truth Social accounts")
        try:
            from handlers.truth_tracker import get_cached_guilds, start_tracking
            enabled_guilds = await get_cached_guilds()
            if enabled_guilds:
                await start_tracking(self)
                logger.info(f"Found {len(enabled_guilds)} guilds with tracking enabled, Auto-started Truth Social tracking")
        except Exception as e:
            logger.error(f"Error auto-starting tracking: {e}")
        
        return success_count > 0
    
    async def _authenticate_account(self, account_data):
        """Authenticate a single account"""
        try:
            username = account_data.get('username')
            password = account_data.get('password')
            
            if not username or not password:
                logger.error(f"Missing username or password for Truth Social account")
                return False
                
            # Check if we already have a token
            if username in self.auth_tokens:
                return True
                
            # Get authentication token
            token = await self._get_auth_token(username, password)
            if token:
                self.auth_tokens[username] = token
                logger.info(f"Authenticated Truth Social account: {username}")
                return True
            
            logger.error(f"Failed to authenticate Truth Social account: {username}")
            return False
        except Exception as e:
            logger.error(f"Error authenticating Truth Social account: {e}")
            return False
    
    async def _get_auth_token(self, username, password):
        """Get authentication token for an account using curl_cffi like truthbrush"""
        try:
            url = f"{BASE_URL}/oauth/token"
            payload = {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "password",
                "username": username,
                "password": password,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "scope": "read"
            }
            
            # Use curl_cffi which handles Cloudflare better
            response = curl_requests.post(
                url,
                json=payload,
                impersonate="chrome123",  # This helps bypass Cloudflare
                headers={"User-Agent": USER_AGENT},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    return data["access_token"]
            
            logger.error(f"Auth error: Status {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting auth token: {e}")
            return None
    
    async def _get_next_account_credentials(self):
        """Get the next account credentials with rotation and rate limit handling"""
        if not TRUTH_ACCOUNTS:
            logger.error("No Truth Social accounts configured")
            return None, None
            
        # Try to find an account that hasn't been used recently and isn't rate limited
        current_time = time.time()
        best_account_idx = self.current_account_index
        best_wait_time = float('inf')
        
        # Look through all accounts to find the one with the shortest wait time
        for i in range(len(TRUTH_ACCOUNTS)):
            idx = (self.current_account_index + i) % len(TRUTH_ACCOUNTS)
            account = TRUTH_ACCOUNTS[idx]
            username = account['username']
            account_key = f"{username}:{account['password']}"
            
            # Check if account is rate limited
            rate_limited_until = self.account_rate_limited_until.get(username, 0)
            if rate_limited_until > current_time:
                # Skip this account, it's rate limited
                continue
                
            # Check when account was last used
            last_used = self.account_last_used.get(account_key, 0)
            wait_time = last_used + self.MIN_ACCOUNT_USAGE_INTERVAL - current_time
            
            if wait_time <= 0:
                # This account is ready to use now
                best_account_idx = idx
                break
            
            if wait_time < best_wait_time:
                best_wait_time = wait_time
                best_account_idx = idx
        
        # Update the current index for next time
        self.current_account_index = (best_account_idx + 1) % len(TRUTH_ACCOUNTS)
        
        # Get the selected account
        account = TRUTH_ACCOUNTS[best_account_idx]
        username = account['username']
        account_key = f"{username}:{account['password']}"
        
        # Update last used time
        self.account_last_used[account_key] = time.time()
        
        return username, self.auth_tokens.get(username)
    
    def _handle_rate_limit(self, account: str, headers: Dict):
        """Handle rate limiting from response headers"""
        # Use a simple timestamp-based approach
        current_time = time.time()
        
        # Default cooldown of 60 seconds for low rate limit
        cooldown = 60
        
        # Check for retry-after header
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                cooldown = int(retry_after) + 5  # Add a small buffer
            except (ValueError, TypeError):
                cooldown = 300  # Default 5-minute cooldown if parse fails
        
        # Set rate limit expiry as a timestamp
        self.account_rate_limited_until[account] = current_time + cooldown
        logger.warning(f"Account {account} rate limited, cooling down for {cooldown}s")
    
    async def _api_request(self, method, url, params=None, json_data=None, proxy=None, retry_count=2):
        """Make an API request with account rotation and rate limiting"""
        for attempt in range(retry_count + 1):
            # Get account credentials 
            account, token = await self._get_next_account_credentials()
            if not account or not token:
                logger.error("No valid Truth Social account available")
                if attempt < retry_count:
                    await asyncio.sleep(1)
                    continue
                return None
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": USER_AGENT,
                "Accept": "application/json"
            }
            
            try:
                # Use curl_cffi which handles Cloudflare better
                request_kwargs = {
                    "headers": headers,
                    "impersonate": "chrome123",  # Bypass Cloudflare
                    "timeout": 15
                }
                
                if params:
                    request_kwargs["params"] = params
                    
                if json_data:
                    request_kwargs["json"] = json_data
                
                # Add proxy if provided
                if proxy:
                    request_kwargs["proxies"] = {"http": proxy, "https": proxy}
                
                # Make the request using curl_cffi
                if method.upper() == "GET":
                    response = curl_requests.get(url, **request_kwargs)
                elif method.upper() == "POST":
                    response = curl_requests.post(url, **request_kwargs)
                else:
                    logger.error(f"Unsupported HTTP method: {method}")
                    return None
                    
                # Handle rate limiting
                if response.status_code == 429:  # Rate limited
                    self._handle_rate_limit(account, response.headers)
                    
                    if attempt < retry_count:
                        # Try again with a different account
                        continue
                        
                # Check for other issues
                if response.status_code != 200:
                    logger.warning(f"API error: Status {response.status_code}")
                    
                    if attempt < retry_count:
                        await asyncio.sleep(1)
                        continue
                        
                    return None
                    
                # Success case
                return response.json()
                        
            except Exception as e:
                logger.error(f"Error in API request: {e}")
                if attempt < retry_count:
                    await asyncio.sleep(1)
                    continue
        
        return None
    
    async def get_user_info(self, handle: str, proxy=None) -> Optional[Dict]:
        """Get user information for a Truth Social account"""
        try:
            url = f"{API_BASE_URL}/v1/accounts/lookup"
            params = {"acct": handle.lstrip('@')}
            
            return await self._api_request("GET", url, params=params, proxy=proxy)
        except Exception as e:
            logger.error(f"Error in get_user_info for {handle}: {e}")
            return None
    
    async def get_user_statuses(self, account_id: str, exclude_replies=True, max_id=None, limit=20, proxy=None) -> List[Dict]:
        """Get posts from a user (their timeline)"""
        url = f"{API_BASE_URL}/v1/accounts/{account_id}/statuses"
        
        params = {}
        if exclude_replies:
            params["exclude_replies"] = "true"
        if max_id:
            params["max_id"] = max_id
        if limit:
            params["limit"] = str(limit)
        
        return await self._api_request("GET", url, params=params, proxy=proxy)
    
    async def get_new_posts(self, handle: str, last_post_id: Optional[str] = None, exclude_replies=True, proxy=None) -> List[Dict]:
        """Get new posts since the last checked post ID"""
        # Get user info
        user_info = await self.get_user_info(handle, proxy=proxy)
        if not user_info or "id" not in user_info:
            logger.error(f"Failed to get user info for handle: {handle}")
            return []
        
        account_id = user_info["id"]
        
        # If no last_post_id, just get the latest post
        if not last_post_id or last_post_id == "DISABLED" or last_post_id == "0":
            posts = await self.get_user_statuses(account_id, exclude_replies=exclude_replies, limit=1, proxy=proxy)
            return posts if posts and isinstance(posts, list) else []
        
        # Get posts since last_post_id
        params = {
            "exclude_replies": "true" if exclude_replies else "false",
            "since_id": last_post_id,
        }
        
        url = f"{API_BASE_URL}/v1/accounts/{account_id}/statuses"
        response = await self._api_request("GET", url, params=params, proxy=proxy)
        
        if not response or not isinstance(response, list):
            return []
        
        return response
    
    # Add methods from truthbrush
    async def search(self, searchtype: str, query: str, limit: int = 40, resolve: bool = 4, 
                    offset: int = 0, min_id: str = "0", max_id: str = None, proxy=None) -> Optional[dict]:
        """Search users, statuses or hashtags."""
        params = {
            "q": query,
            "resolve": resolve,
            "limit": limit,
            "type": searchtype,
            "offset": offset,
            "min_id": min_id
        }
        
        if max_id:
            params["max_id"] = max_id
            
        url = f"{API_BASE_URL}/v2/search"
        return await self._api_request("GET", url, params=params, proxy=proxy)
    
    async def trending(self, limit=10, proxy=None):
        """Return trending truths."""
        url = f"{API_BASE_URL}/v1/truth/trending/truths"
        params = {"limit": limit}
        return await self._api_request("GET", url, params=params, proxy=proxy)
    
    async def tags(self, proxy=None):
        """Return trending tags."""
        url = f"{API_BASE_URL}/v1/trends"
        return await self._api_request("GET", url, proxy=proxy)
    
    async def suggested(self, maximum: int = 50, proxy=None) -> dict:
        """Return a list of suggested users to follow."""
        url = f"{API_BASE_URL}/v2/suggestions"
        params = {"limit": maximum}
        return await self._api_request("GET", url, params=params, proxy=proxy)
    
    async def trending_groups(self, limit=10, proxy=None):
        """Return trending group truths."""
        url = f"{API_BASE_URL}/v1/truth/trends/groups"
        params = {"limit": limit}
        return await self._api_request("GET", url, params=params, proxy=proxy)
    
    async def group_tags(self, proxy=None):
        """Return trending group tags."""
        url = f"{API_BASE_URL}/v1/groups/tags"
        return await self._api_request("GET", url, proxy=proxy)
    
    async def suggested_groups(self, maximum: int = 50, proxy=None) -> dict:
        """Return a list of suggested groups to follow."""
        url = f"{API_BASE_URL}/v1/truth/suggestions/groups"
        params = {"limit": maximum}
        return await self._api_request("GET", url, params=params, proxy=proxy)
    
    async def ads(self, device: str = "desktop", proxy=None) -> dict:
        """Return a list of ads from Rumble's Ad Platform via Truth Social API."""
        url = f"{API_BASE_URL}/v3/truth/ads"
        params = {"device": device}
        return await self._api_request("GET", url, params=params, proxy=proxy)
    
    async def user_likes(self, post: str, include_all: bool = False, top_num: int = 40, proxy=None):
        """Return the top_num most recent (or all) users who liked the post."""
        post = post.split("/")[-1]
        url = f"{API_BASE_URL}/v1/statuses/{post}/favourited_by"
        params = {"limit": 80}
        
        response = await self._api_request("GET", url, params=params, proxy=proxy)
        if not response:
            return []
            
        # Limit results if not including all
        if not include_all and top_num > 0:
            return response[:top_num]
        return response
    
    async def pull_comments(self, post: str, include_all: bool = False, only_first: bool = False, 
                            top_num: int = 40, proxy=None):
        """Return the replies to a post."""
        post = post.split("/")[-1]
        url = f"{API_BASE_URL}/v1/statuses/{post}/context/descendants"
        params = {"sort": "oldest"}
        
        response = await self._api_request("GET", url, params=params, proxy=proxy)
        if not response:
            return []
            
        # Filter responses if only getting direct replies
        if only_first:
            response = [r for r in response if r.get("in_reply_to_id") == post]
            
        # Limit results if not including all
        if not include_all and top_num > 0:
            return response[:top_num]
        return response
    
    async def group_posts(self, group_id: str, limit=20, proxy=None):
        """Get posts from a group's timeline"""
        url = f"{API_BASE_URL}/v1/timelines/group/{group_id}"
        params = {"limit": limit}
        
        posts = await self._api_request("GET", url, params=params, proxy=proxy)
        if not posts:
            return []
            
        timeline = posts
        
        # If we need more posts and have some already, paginate
        while len(timeline) < limit and posts:
            max_id = posts[-1]["id"]
            next_params = {"limit": limit - len(timeline), "max_id": max_id}
            posts = await self._api_request("GET", url, params=next_params, proxy=proxy)
            
            if not posts:
                break
                
            timeline.extend(posts)
            
        return timeline