"""
Truth Social API service with improved authentication and caching
"""
import os
import time
import json
import asyncio
import random
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
from utils.logger import get_logger
from curl_cffi import requests as curl_requests
from config import (
    TRUTH_ACCOUNTS,
    TRUTH_DEFAULT_INTERVAL,
    MIN_ACCOUNT_USAGE_INTERVAL
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

# Token storage location
TOKEN_FILE = "data/truth_tokens.json"
TOKEN_EXPIRY = 86400 * 100  # 7 days in seconds

class TruthSocialService:
    """Service for Truth Social API interactions"""
    
    def __init__(self, api_client):
        """Initialize with API client"""
        self.api_client = api_client
        self.auth_tokens = {}  # Map username to token info
        self.current_account_index = 0
        self.account_last_used = {}  # Track when account was last used
        self.account_rate_limited_until = {}  # Store timestamps when rate limits expire
        
        # Create data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)

    
    async def setup(self):
        """Set up the service by authenticating all accounts"""
        if not TRUTH_ACCOUNTS:
            logger.error("No Truth Social accounts configured")
            return False
            
        # Load any existing tokens
        self._load_tokens()
        
        # Authenticate accounts with expired or missing tokens
        accounts_to_authenticate = []
        for account in TRUTH_ACCOUNTS:
            username = account.get('username')
            if not self._is_token_valid(username):
                accounts_to_authenticate.append(account)
        
        if accounts_to_authenticate:
            logger.info(f"Authenticating {len(accounts_to_authenticate)} Truth Social accounts with missing or expired tokens...")
            
            # Authenticate in parallel with batching to avoid overwhelming the API
            batch_size = 5
            for i in range(0, len(accounts_to_authenticate), batch_size):
                batch = accounts_to_authenticate[i:i+batch_size]
                tasks = [self._authenticate_account(account) for account in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Small delay between batches
                if i + batch_size < len(accounts_to_authenticate):
                    await asyncio.sleep(1)
        
        # Count valid tokens
        valid_tokens = sum(1 for username in self.auth_tokens if self._is_token_valid(username))
        logger.info(f"Successfully authenticated {valid_tokens}/{len(TRUTH_ACCOUNTS)} Truth Social accounts")
        
        # Save tokens to file
        self._save_tokens()
        
        return valid_tokens > 0
    
    def _load_tokens(self):
        """Load authentication tokens from file"""
        try:
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, 'r') as f:
                    token_data = json.load(f)
                    
                    # Check token format
                    if isinstance(token_data, dict):
                        self.auth_tokens = token_data
                        logger.info(f"Loaded {len(self.auth_tokens)} Truth Social tokens from file")
        except Exception as e:
            logger.error(f"Error loading Truth Social tokens: {e}")
            self.auth_tokens = {}
    
    def _save_tokens(self):
        """Save authentication tokens to file"""
        try:
            with open(TOKEN_FILE, 'w') as f:
                json.dump(self.auth_tokens, f)
            logger.info(f"Saved {len(self.auth_tokens)} Truth Social tokens to file")
        except Exception as e:
            logger.error(f"Error saving Truth Social tokens: {e}")
    
    def _is_token_valid(self, username):
        """Check if token is valid and not expired"""
        if username not in self.auth_tokens:
            return False
            
        token_info = self.auth_tokens[username]
        if not isinstance(token_info, dict) or 'token' not in token_info:
            return False
            
        # Check if token is expired
        expiry = token_info.get('expiry', 0)
        current_time = time.time()
        return expiry > current_time
    
    async def _authenticate_account(self, account_data):
        """Authenticate a single account"""
        try:
            username = account_data.get('username')
            password = account_data.get('password')
            
            if not username or not password:
                logger.error(f"Missing username or password for Truth Social account")
                return False
            
            # Get authentication token
            token = await self._get_auth_token(username, password)
            if token:
                # Store token with expiry time
                self.auth_tokens[username] = {
                    'token': token,
                    'expiry': time.time() + TOKEN_EXPIRY
                }
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
            wait_time = last_used + MIN_ACCOUNT_USAGE_INTERVAL - current_time
            
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
        
        # Get token
        token_info = self.auth_tokens.get(username, {})
        token = token_info.get('token') if isinstance(token_info, dict) else None
        
        return username, token
    
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
            
            # logger.info(f"polling truth social with account username: {account}, token: {token}")
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
                logger.error(f"Truthsocial request error: {e}")
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

    async def get_user_statuses(self, account_id: str, exclude_replies=True, max_id=None, 
                            limit=5, proxy=None, since_id=None) -> List[Dict]:
        """Get posts from a user (their timeline)"""
        url = f"{API_BASE_URL}/v1/accounts/{account_id}/statuses"
        
        params = {}
        if exclude_replies:
            params["exclude_replies"] = "true"
        if max_id:
            params["max_id"] = max_id
        if since_id:
            params["since_id"] = since_id
        if limit:
            params["limit"] = str(limit)
        
        return await self._api_request("GET", url, params=params, proxy=proxy)
    
    async def get_latest_posts(self, account_id: str, last_post_id: Optional[str] = None,
                            exclude_replies=True, proxy=None) -> List[Dict]:
        """
        Get latest posts for an account since the last_post_id
        Ultra-optimized for high-frequency polling
        
        Args:
            account_id: The Truth Social account ID
            last_post_id: The last post ID we've seen (for filtering)
            exclude_replies: Whether to exclude replies
            proxy: Optional proxy to use
            
        Returns:
            List of posts, sorted by recency (newest first)
        """
        try:
            # If this is the first run or disabled, just get the latest post
            if not last_post_id or last_post_id == "0" or last_post_id == "DISABLED":
                posts = await self.get_user_statuses(
                    account_id, 
                    exclude_replies=exclude_replies,
                    limit=1,
                    proxy=proxy
                )
                logger.info(f"First-time poll for {account_id}: found {len(posts) if posts else 0} posts")
                return posts if posts and isinstance(posts, list) else []
            
            # Get latest posts since last_post_id (up to 5 to handle bursts of activity)
            url = f"{API_BASE_URL}/v1/accounts/{account_id}/statuses"
            
            params = {
                "limit": "5",  # Get up to 5 posts to handle bursts of activity
                "since_id": last_post_id  # Only get posts newer than last_post_id
            }
            
            if exclude_replies:
                params["exclude_replies"] = "true"
            
            # Make the API request and handle rate limiting
            response = await self._api_request("GET", url, params=params, proxy=proxy)
            
            if not response or not isinstance(response, list):
                return []
            
            # Log the response for debugging
            username = "unknown"
            for account in TRUTH_ACCOUNTS:
                if account.get('username'):
                    username = account.get('username')
                    break
                    
            logger.debug(f"polling truth social with account username: {username}, token: {self.auth_tokens.get(username, {}).get('token', '')[:40]}")
            
            # Return the posts (sorted by recency in the pipeline)
            return response
        
        except Exception as e:
            logger.error(f"Error in get_latest_posts for {account_id}: {e}")
            return []
    