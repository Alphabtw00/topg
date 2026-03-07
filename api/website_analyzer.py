"""
Optimized Website Analyzer for crypto projects with fast concurrent checks
"""
import asyncio
import time
import re
import ssl
import socket
import whois
import imagehash
from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List, Set, Tuple
import concurrent.futures
from cachetools import TTLCache
from api.client import ApiClient, ApiEndpoint
from config import VIRUS_TOTAL_API_KEY
from utils.logger import get_logger
import aiohttp
import certifi
import functools

# Constants for request optimization
CONCURRENCY_LIMIT = 15  # Increased from 10
REQUEST_TIMEOUT = 8  # Reduced from 10
SSL_TIMEOUT = 4  # Reduced from 5
CACHE_SIZE = 100  # Increased from 100
CACHE_TTL = 3600  # 1 hour

# Create caches with larger sizes
website_cache = TTLCache(maxsize=CACHE_SIZE, ttl=CACHE_TTL)
whois_cache = TTLCache(maxsize=CACHE_SIZE, ttl=86400)  # 24 hours
dns_cache = TTLCache(maxsize=CACHE_SIZE, ttl=3600)  # 1 hour
virustotal_cache = TTLCache(maxsize=CACHE_SIZE, ttl=43200)

# Tech detection patterns
TECH_PATTERNS = {
    "React": (r'react\.js|reactjs|"react":|\'react\':|react-dom', "JavaScript Framework"),
    "Vue.js": (r'vue\.js|vuejs|"vue":|\'vue\':|Vue\.', "JavaScript Framework"),
    "Angular": (r'angular\.js|angularjs|ng\-app|ng\-controller|angular\-|ng\-', "JavaScript Framework"),
    "jQuery": (r'jquery\.js|jquery\-|jquery.min.js', "JavaScript Library"),
    "Bootstrap": (r'bootstrap\.css|bootstrap\.js|bootstrap\.min|class="container"|class="row"|class="col-', "CSS Framework"),
    "Tailwind CSS": (r'tailwind\.css|tailwindcss|class="flex"|class="grid"|class="px-|class="py-|class="text-', "CSS Framework"),
    "WordPress": (r'wp-content|wp-includes|wp-admin|wordpress', "CMS"),
    "Shopify": (r'cdn\.shopify\.com|shopify\.com|Shopify\.theme', "E-commerce Platform"),
    "Wix": (r'wix\.com|wixsite\.com|_wixCssPath|wix-', "Website Builder"),
    "Next.js": (r'next\.js|nextjs|"next":|\'next\':|__NEXT_DATA__', "React Framework"),
    "Gatsby": (r'gatsby\.js|gatsbyjs|"gatsby":|\'gatsby\':|__GATSBY', "React Framework"),
    "Web3.js": (r'web3\.js|web3.min.js|"web3":|\'web3\':|ethereum', "Blockchain"),
    "Ethers.js": (r'ethers\.js|ethers.min.js|"ethers":|\'ethers\':|ethereum', "Blockchain"),
    "Solana Web3": (r'solana\.js|@solana/web3.js|"solana":|\'solana\':|solana', "Blockchain"),
    "Phantom": (r'phantom|phantom wallet|"phantom":|connect phantom', "Crypto Wallet"),
    "MetaMask": (r'metamask|ethereum provider|"ethereum":', "Crypto Wallet"),
    "Coinbase Wallet": (r'coinbase\s+wallet|walletlink', "Crypto Wallet"),
    "WalletConnect": (r'walletconnect|wallet\s+connect', "Crypto Wallet"),
    "Foundation": (r'foundation\.js|foundation\.css|foundation\.min\.js', "CSS Framework"),
    "Material UI": (r'material-ui|mui\.com|@mui/material', "UI Framework"),
    "Chakra UI": (r'chakra-ui|@chakra-ui/react', "UI Framework"),
    "Bulma": (r'bulma\.css|bulma\.io', "CSS Framework"),
    "Three.js": (r'three\.js|three\.min\.js', "3D Graphics"),
    "D3.js": (r'd3\.js|d3\.min\.js', "Data Visualization"),
    "Chart.js": (r'chart\.js|chart\.min\.js', "Data Visualization")
}

COMPILED_TECH_PATTERNS = {
    tech_name: (re.compile(pattern, re.IGNORECASE), category)
    for tech_name, (pattern, category) in TECH_PATTERNS.items()
}

# Social media patterns
SOCIAL_PATTERNS = {
    'twitter.com': 'Twitter',
    'x.com': 'Twitter',
    't.me': 'Telegram',
    'telegram.me': 'Telegram',
    'facebook.com': 'Facebook',
    'instagram.com': 'Instagram',
    'linkedin.com': 'LinkedIn',
    'github.com': 'GitHub',
    'medium.com': 'Medium',
    'discord.gg': 'Discord',
    'discord.com': 'Discord',
    'youtube.com': 'YouTube',
    'reddit.com': 'Reddit',
    'tiktok.com': 'TikTok'
}

# Blockchain explorer patterns
BLOCKCHAIN_PATTERNS = {
    'etherscan.io': 'Ethereum',
    'bscscan.com': 'BNB Chain',
    'polygonscan.com': 'Polygon',
    'arbiscan.io': 'Arbitrum',
    'optimistic.etherscan.io': 'Optimism',
    'ftmscan.com': 'Fantom',
    'explorer.solana.com': 'Solana',
    'solscan.io': 'Solana',
    'solanafm.com': 'Solana',
    'solanabeach.io': 'Solana',
    'explorer.near.org': 'NEAR Protocol',
    'explorer.aptoslabs.com': 'Aptos',
    'explorer.sui.io': 'Sui',
    'explorer.zksync.io': 'zkSync',
    'explorer.starknet.io': 'StarkNet',
    'explorer.immutable.com': 'Immutable X',
    'scan.manta.network': 'Manta Network'
}

# Security headers to check
SECURITY_HEADERS = [
    "content-security-policy",
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "x-xss-protection",
    "referrer-policy",
    "permissions-policy"
]

# Resource patterns
CDN_PATTERNS = ['cdn', 'cloudfront', 'cloudflare', 'akamai', 'jsdelivr', 'unpkg', 'fastly', 'bunny.net', 'edgecast']
MINIFIED_PATTERNS = ['.min.js', '.min.css', '.bundle.js', '.bundle.css', '.compressed.js']

# Crypto-specific keywords for content analysis
CRYPTO_KEYWORDS = [
    "token", "blockchain", "crypto", "cryptocurrency", "bitcoin", "ethereum", 
    "solana", "nft", "defi", "web3", "wallet", "dao", "dapp", "staking", 
    "mining", "yield", "liquidity", "airdrop", "whitepaper", "roadmap",
    "layer2", "governance", "rollup", "burn", "tokenomics", "smart contract",
    "presale", "ico", "initial coin offering", "mainnet", "testnet", "decentralized",
    "centralized", "trustless", "permissionless", "erc20", "erc721", "erc1155",
    "spl", "bep20", "bridge", "swap", "exchange", "farm", "mint", "apy", 
    "airdrop", "peg", "oracle", "consensus", "proof of stake", "proof of work"
]

# Initialize logger
logger = get_logger()

class WebsiteAnalyzer:
    """Fast, optimized website analyzer for crypto projects"""
    
    def __init__(self, api_client: ApiClient):
        """Initialize with API client for requests"""
        self.api_client = api_client
        self.semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        logger.info("WebsiteAnalyzer initialized with concurrency limit of %d", CONCURRENCY_LIMIT)
        
    async def analyze_website(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Analyze a website using optimized concurrent checks
        
        Args:
            url: Website URL to analyze
            
        Returns:
            Analysis results or None if failed
        """
        start_time = time.time()
        logger.info(f"Starting website analysis for {url}")
        
        # Normalize URL
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
            logger.info(f"URL normalized to {url}")
        
        # Parse domain
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        logger.info(f"Parsed domain: {domain}")
        
        # Generate cache key
        cache_key = domain.lower()
        logger.info(f"Generated cache key: {cache_key}")
        
        # Check cache
        if cache_key in website_cache:
            logger.info(f"Cache hit for {cache_key}")
            cached_result = website_cache[cache_key]
            cached_result["cached"] = True
            return cached_result
        
        logger.info(f"Cache miss for {cache_key}, running analysis")
        
        try:
            # Fetch the main page with our API client using a semaphore to limit concurrency
            async with self.semaphore:
                try:
                    response = await self.api_client.get(url, ApiEndpoint.WEBSITE)
                    logger.info(f"Successfully fetched main page for {url}")
                except Exception as e:
                    logger.error(f"Failed to fetch main page for {url}: {str(e)}")
                    return None
            
            if not response:
                logger.error(f"Failed to fetch {url}")
                return None
            
            # Extract HTML and create soup
            html = response.get('text', '') if isinstance(response, dict) else response
            
            if not html:
                logger.error(f"No HTML content retrieved from {url}")
                return None
            html = self._sanitize_html(html)
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract basic text and metadata
            text_content = soup.get_text(separator=' ', strip=True)
            metadata = self._extract_metadata(soup, url)
            favicon_url = self._get_favicon_url(soup, url)
            
            # Track success/failure of each check
            check_results = {}
            
            # Run all checks concurrently for maximum speed with individual try/except blocks
            async def run_check(name, coro):
                try:
                    start = time.time()
                    result = await coro
                    duration = time.time() - start
                    logger.info(f"Check '{name}' completed in {duration:.3f}s")
                    check_results[name] = {"success": True, "duration": duration}
                    return result
                except Exception as e:
                    duration = time.time() - start
                    logger.error(f"Check '{name}' failed in {duration:.3f}s: {str(e)}")
                    check_results[name] = {"success": False, "duration": duration, "error": str(e)}
                    return e
            
            checks = await asyncio.gather(
                run_check("domain_info", self._check_domain_info(domain)),
                run_check("ssl_certificate", self._check_ssl_certificate(domain)),
                run_check("security_headers", self._check_security_headers(url)),
                run_check("virustotal", self._check_virustotal(domain)),
                run_check("wayback_history", self._check_wayback_history(domain)),
                run_check("favicon", self._fetch_favicon(favicon_url)),
                return_exceptions=True
            )
            
            # Process HTML-based checks (no need for additional requests)
            tech_check_start = time.time()
            tech_stack = self._analyze_tech_stack(html)
            check_results["tech_stack"] = {"success": True, "duration": time.time() - tech_check_start}
            
            links_check_start = time.time()
            links = self._extract_links(soup, url)
            check_results["links"] = {"success": True, "duration": time.time() - links_check_start}
            
            resources_check_start = time.time()
            resources = self._analyze_resources(soup, url)
            check_results["resources"] = {"success": True, "duration": time.time() - resources_check_start}
            
            performance = {"load_time": time.time() - start_time}
            
            social_check_start = time.time()
            social_media = self._analyze_social_media(links)
            check_results["social_media"] = {"success": True, "duration": time.time() - social_check_start}
            
            blockchain_check_start = time.time()
            blockchain_info = self._analyze_blockchain_integration(html, links)
            check_results["blockchain"] = {"success": True, "duration": time.time() - blockchain_check_start}
            
            seo_check_start = time.time()
            seo_info = self._analyze_seo(soup, metadata)
            check_results["seo"] = {"success": True, "duration": time.time() - seo_check_start}
            
            content_check_start = time.time()
            content_quality = self._analyze_content_quality(soup, text_content)
            check_results["content"] = {"success": True, "duration": time.time() - content_check_start}
            
            template_check_start = time.time()
            template_analysis = self._detect_template_site(soup, html)
            check_results["template"] = {"success": True, "duration": time.time() - template_check_start}
            
            # Process the results from concurrent checks
            domain_info = checks[0] if not isinstance(checks[0], Exception) else {}
            ssl_info = checks[1] if not isinstance(checks[1], Exception) else {}
            security_headers = checks[2] if not isinstance(checks[2], Exception) else {}
            virustotal_results = checks[3] if not isinstance(checks[3], Exception) else None
            wayback_results = checks[4] if not isinstance(checks[4], Exception) else None
            favicon_data = checks[5] if not isinstance(checks[5], Exception) else None
            
            # Log summary of check results
            succeeded = sum(1 for result in check_results.values() if result["success"])
            failed = len(check_results) - succeeded
            logger.info(f"Check summary: {succeeded} succeeded, {failed} failed")
            
            # Calculate scores
            score_start = time.time()
            scores = {
                "domain": self._calculate_domain_score(domain_info),
                "security": self._calculate_security_score(ssl_info, security_headers),
                "tech": self._calculate_tech_score(tech_stack, blockchain_info),
                "performance": self._calculate_perf_score(performance, resources),
                "social": self._calculate_social_score(social_media),
                "content": self._calculate_content_score(content_quality, seo_info, metadata),
                "blockchain": blockchain_info.get("score", 0)
            }
            
            # Calculate weighted legitimacy score
            legitimacy_score = self._calculate_overall_score(scores)
            
            # Generate risk assessment
            risk_assessment = self._generate_risk_assessment(
                domain_info, ssl_info, security_headers, tech_stack,
                blockchain_info, template_analysis, virustotal_results,
                scores, legitimacy_score
            )
            logger.info(f"Scores and risk assessment calculated in {time.time() - score_start:.3f}s")
            
            # Create the final result
            result = {
                "url": url,
                "domain": domain,
                "favicon_url": favicon_url,
                "favicon_data": favicon_data,
                "title": metadata.get("title", ""),
                "description": metadata.get("description", ""),
                
                # Core data
                "domain_info": domain_info,
                "ssl_info": ssl_info,
                "security_headers": security_headers,
                "tech_stack": tech_stack,
                "links": links,
                "resources": resources,
                "performance": performance,
                "social_media": social_media,
                "blockchain_info": blockchain_info,
                "content_quality": content_quality,
                "seo_info": seo_info,
                "template_analysis": template_analysis,
                "virustotal": virustotal_results,
                "wayback": wayback_results,
                
                # Scores and assessment
                "scores": scores,
                "legitimacy_score": legitimacy_score,
                "risk_assessment": risk_assessment,
                
                # Metadata
                "cached": False,
                "timestamp": datetime.now().timestamp(),
                "analysis_time_ms": int((time.time() - start_time) * 1000),
                "check_results": check_results  # Add diagnostics
            }
            
            # Cache the result
            website_cache[cache_key] = result
            logger.info(f"Analysis of {url} completed in {time.time() - start_time:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing {url}: {str(e)}", exc_info=True)
            return None
    
    async def clear_from_cache(self, url: str) -> bool:
        """Clear a specific URL from the cache"""
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
            
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        
        if domain in website_cache:
            del website_cache[domain]
            logger.info(f"Cleared {domain} from cache")
            return True
        
        return False
    
    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, str]:
        """Extract metadata from page"""
        metadata = {
            "title": "",
            "description": "",
            "keywords": "",
            "og_title": "",
            "og_description": "",
            "og_image": "",
            "twitter_card": "",
            "twitter_title": "",
            "twitter_description": "",
            "twitter_image": ""
        }
        
        # Extract title
        title_tag = soup.find('title')
        if title_tag:
            metadata["title"] = title_tag.text.strip()
        
        # Process meta tags
        for meta in soup.find_all('meta'):
            name = meta.get('name', '').lower()
            property = meta.get('property', '').lower()
            content = meta.get('content', '')
            
            if name == 'description' or property == 'og:description':
                metadata["description"] = content
            elif name == 'keywords':
                metadata["keywords"] = content
                
            # Open Graph data
            if property == 'og:title':
                metadata["og_title"] = content
            elif property == 'og:description':
                metadata["og_description"] = content
            elif property == 'og:image':
                metadata["og_image"] = content
                
            # Twitter Card data
            if name == 'twitter:card':
                metadata["twitter_card"] = content
            elif name == 'twitter:title':
                metadata["twitter_title"] = content
            elif name == 'twitter:description':
                metadata["twitter_description"] = content
            elif name == 'twitter:image':
                metadata["twitter_image"] = content
        
        return metadata
    
    def _get_favicon_url(self, soup: BeautifulSoup, url: str) -> str:
        """Extract favicon URL from page"""
        favicon_url = None
        
        # Try standard favicon link
        favicon_link = soup.find('link', rel=lambda r: r and ('icon' in r.lower() or 'shortcut icon' in r.lower()))
        if favicon_link and 'href' in favicon_link.attrs:
            favicon_url = favicon_link['href']
            
        # If not found, try default location
        if not favicon_url:
            parsed_url = urlparse(url)
            favicon_url = f"{parsed_url.scheme}://{parsed_url.netloc}/favicon.ico"
            
        # Make sure it's an absolute URL
        if favicon_url and not favicon_url.startswith(('http://', 'https://')):
            favicon_url = urljoin(url, favicon_url)
            
        return favicon_url
    
    async def _check_domain_info(self, domain: str) -> Dict[str, Any]:
        """Check domain information asynchronously"""
        domain_info = {
            "domain": domain,
            "age_days": 0,
            "creation_date": None,
            "expiration_date": None,
            "registrar": "",
            "privacy_protected": False,
            "days_until_expiry": 0,
            "is_new": True
        }
        
        try:
            # Strip www. if present
            if domain.startswith('www.'):
                domain = domain[4:]
                
            # Check cache first
            if domain in whois_cache:
                whois_data = whois_cache[domain]
                logger.info(f"Using cached WHOIS data for {domain}")
            else:
                # Use ThreadPoolExecutor for the blocking whois lookup
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    loop = asyncio.get_event_loop()
                    whois_data = await loop.run_in_executor(
                        executor, 
                        functools.partial(whois.whois, domain)
                    )
                logger.info(f"Fetched fresh WHOIS data for {domain}")
                whois_cache[domain] = whois_data
            
            # Extract creation date
            creation_date = whois_data.creation_date
            if isinstance(creation_date, list):
                creation_date = creation_date[0] if creation_date else None
                
            # Extract expiration date
            expiration_date = whois_data.expiration_date
            if isinstance(expiration_date, list):
                expiration_date = expiration_date[0] if expiration_date else None
                
            # Calculate domain age
            if creation_date and isinstance(creation_date, datetime):
                domain_info["creation_date"] = creation_date.strftime("%Y-%m-%d")
                domain_info["age_days"] = (datetime.now() - creation_date).days
                domain_info["is_new"] = domain_info["age_days"] < 180  # Less than 6 months
                
            # Calculate expiration info
            if expiration_date and isinstance(expiration_date, datetime):
                domain_info["expiration_date"] = expiration_date.strftime("%Y-%m-%d")
                domain_info["days_until_expiry"] = (expiration_date - datetime.now()).days
                
            # Extract registrar
            domain_info["registrar"] = whois_data.registrar or ""
            
            # Check for privacy protection
            org = getattr(whois_data, 'org', '') or ''
            if isinstance(org, list):
                org = org[0] if org else ''
                
            domain_info["privacy_protected"] = any(term in org.lower() 
                for term in ['privacy', 'private', 'whois', 'protect', 'withheld'])
                
        except Exception as e:
            logger.error(f"Error checking domain info for {domain}: {str(e)}")
            
        return domain_info
    
    async def _check_ssl_certificate(self, domain: str) -> Dict[str, Any]:
        """Check SSL certificate info asynchronously with improved error handling"""
        ssl_info = {
            "has_ssl": False,
            "issuer": "",
            "expiry": None,
            "days_remaining": 0,
            "version": "",
            "subject": "",
            "key_size": 0
        }
        
        # Use ThreadPoolExecutor for the blocking SSL connection
        with concurrent.futures.ThreadPoolExecutor() as executor:
            try:
                # Strip port if present
                if ":" in domain:
                    domain = domain.split(":")[0]
                    
                def check_ssl():
                    try:
                        # Use certifi's certificates for more reliable SSL connections
                        context = ssl.create_default_context(cafile=certifi.where())
                        conn = context.wrap_socket(socket.socket(socket.AF_INET), server_hostname=domain)
                        conn.settimeout(SSL_TIMEOUT)
                        conn.connect((domain, 443))
                        cert = conn.getpeercert()
                        version = conn.version()
                        cipher = conn.cipher()
                        conn.close()
                        return {"cert": cert, "version": version, "cipher": cipher, "error": None}
                    except (socket.gaierror, socket.error) as e:
                        return {"error": f"Connection error: {str(e)}"}
                    except ssl.SSLError as e:
                        return {"error": f"SSL error: {str(e)}"}
                    except Exception as e:
                        return {"error": f"Unexpected error: {str(e)}"}
                
                # Execute in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(executor, check_ssl)
                
                if result.get("error"):
                    logger.warning(f"SSL check failed for {domain}: {result['error']}")
                    return ssl_info
                
                # Process certificate
                ssl_info["has_ssl"] = True
                ssl_info["version"] = result["version"]
                
                cert = result["cert"]
                if cert:
                    # Parse expiry date
                    try:
                        expiry = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                        ssl_info["expiry"] = expiry.strftime("%Y-%m-%d")
                        ssl_info["days_remaining"] = (expiry - datetime.now()).days
                    except (ValueError, KeyError) as e:
                        logger.warning(f"Error parsing SSL certificate expiry for {domain}: {str(e)}")
                    
                    # Get issuer
                    try:
                        issuer = dict(x[0] for x in cert['issuer'])
                        ssl_info["issuer"] = issuer.get('organizationName', '')
                    except (ValueError, KeyError) as e:
                        logger.warning(f"Error parsing SSL certificate issuer for {domain}: {str(e)}")
                    
                    # Get subject
                    try:
                        subject = dict(x[0] for x in cert['subject'])
                        ssl_info["subject"] = subject.get('commonName', '')
                    except (ValueError, KeyError) as e:
                        logger.warning(f"Error parsing SSL certificate subject for {domain}: {str(e)}")
                    
                    # Get key details if available
                    cipher = result.get("cipher")
                    if cipher:
                        ssl_info["cipher"] = cipher[0]
                        ssl_info["key_size"] = cipher[2]
                
                logger.info(f"Successfully checked SSL certificate for {domain}")
                    
            except Exception as e:
                logger.error(f"Unexpected error checking SSL for {domain}: {str(e)}")
                    
        return ssl_info
    
    async def _check_security_headers(self, url: str) -> Dict[str, Any]:
        """Check security headers asynchronously with improved error handling"""
        security_headers = {header: "" for header in SECURITY_HEADERS}
        security_headers["implemented_count"] = 0
        security_headers["total_count"] = len(SECURITY_HEADERS)
        security_headers["grade"] = "F"
        
        try:
            async with self.semaphore:
                try:
                    response = await self.api_client.get(url, ApiEndpoint.WEBSITE)
                    
                    # More robust response validation
                    if not response:
                        raise ValueError("Empty response from server")
                    
                    if not isinstance(response, dict):
                        logger.warning(f"Unexpected response type for {url}: {type(response)}")
                        return security_headers
                    
                    if 'headers' not in response:
                        logger.warning(f"No headers in response for {url}")
                        return security_headers
                    
                    headers = response['headers']
                    
                    # Ensure headers are a dictionary
                    if not isinstance(headers, dict):
                        logger.warning(f"Headers is not a dictionary for {url}: {type(headers)}")
                        return security_headers
                    
                    # Check for each security header with case-insensitive matching
                    header_matches = {}
                    for key in headers:
                        key_lower = key.lower()
                        for header in SECURITY_HEADERS:
                            if header.lower() == key_lower:
                                header_matches[header] = headers[key]
                    
                    # Update security headers with matches
                    for header, value in header_matches.items():
                        security_headers[header] = value
                        security_headers["implemented_count"] += 1
                    
                    # Calculate security grade
                    implemented = security_headers["implemented_count"]
                    if implemented >= 6:
                        security_headers["grade"] = "A"
                    elif implemented >= 5:
                        security_headers["grade"] = "B"
                    elif implemented >= 3:
                        security_headers["grade"] = "C"
                    elif implemented >= 1:
                        security_headers["grade"] = "D"
                    
                except Exception as e:
                    logger.error(f"Error fetching security headers for {url}: {str(e)}")
                    # Even if fetching failed, we'll return the default headers
            
        except Exception as e:
            logger.error(f"Unexpected error checking security headers for {url}: {str(e)}")
            
        return security_headers
    
    async def _check_virustotal(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Check domain reputation on VirusTotal
        
        This is a placeholder - you would need to implement the actual API call
        """

        
        # Example implementation with API key:
        api_key = VIRUS_TOTAL_API_KEY
        url = f"https://www.virustotal.com/api/v3/domains/{domain}"
        
        try:
            async with self.semaphore:
                response = await self.api_client.get(
                    url, 
                    ApiEndpoint.WEBSITE,
                    headers={"x-apikey": api_key}
                )
            
            if response:
                data = response
                last_analysis_stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                malicious = last_analysis_stats.get("malicious", 0)
                suspicious = last_analysis_stats.get("suspicious", 0)
                
                return {
                    "malicious_count": malicious,
                    "suspicious_count": suspicious,
                    "detection_ratio": f"{malicious}/{sum(last_analysis_stats.values())}"
                }
        except Exception as e:
            logger.error(f"Error checking VirusTotal for {domain}: {str(e)}")
            
        return None

    async def _check_wayback_history(self, domain: str) -> Dict[str, Any]:
        """Check site history in Wayback Machine with proper SSL context"""
        result = {
            "has_history": False,
            "first_seen": "",
            "snapshot_url": "",
            "status": "",
            "error": None
        }
        
        try:
            # Use explicit SSL context with certifi's certificates
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            
            wb_url = f"https://archive.org/wayback/available?url={domain}"
            
            async with self.semaphore:
                # Modified to use custom SSL context
                async with aiohttp.ClientSession() as session:
                    async with session.get(wb_url, ssl=ssl_context, timeout=REQUEST_TIMEOUT) as response:
                        if response.status == 200:
                            data = await response.json()
                            snapshots = data.get("archived_snapshots", {})
                            
                            if snapshots:
                                closest = snapshots.get("closest", {})
                                result["has_history"] = True
                                result["first_seen"] = closest.get("timestamp", "")
                                result["snapshot_url"] = closest.get("url", "")
                                result["status"] = closest.get("status", "")
                            
                            logger.info(f"Successfully checked Wayback Machine for {domain}")
                        else:
                            result["error"] = f"HTTP {response.status} from Wayback Machine API"
                            logger.warning(f"HTTP {response.status} from Wayback Machine API for {domain}")
            
        except Exception as e:
            error_msg = f"Error checking Wayback Machine for {domain}: {str(e)}"
            logger.error(error_msg)
            result["error"] = error_msg
            
        return result
    
    async def _fetch_favicon(self, favicon_url: str) -> Optional[bytes]:
        """Fetch favicon data asynchronously"""
        if not favicon_url:
            return None

        try:
            response = await self.api_client.get(favicon_url, ApiEndpoint.WEBSITE)
            if isinstance(response, bytes):
                return response
        except Exception as e:
            logger.warning(f"Error fetching favicon from {favicon_url}: {str(e)}")

        return None
    



    def _sanitize_html(self, html: str) -> str:
        """Sanitize HTML content to prevent security issues"""
        from bs4 import BeautifulSoup
        
        # Create a safe parser that removes dangerous elements
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove potentially dangerous tags
        for tag in soup.find_all(['script', 'iframe', 'object', 'embed', 'form']):
            tag.decompose()
        
        # Remove on* attributes (event handlers)
        for tag in soup.find_all(True):
            attrs = dict(tag.attrs)
            for attr in attrs:
                if attr.startswith('on'):
                    del tag.attrs[attr]
        
        # Return sanitized HTML
        return str(soup)

    def _analyze_tech_stack(self, html: str) -> List[Dict[str, Any]]:
        """Analyze technology stack from HTML"""
        tech_stack = []
        detected_techs = set()

        # Check using regex patterns
        for tech_name, (pattern, category) in COMPILED_TECH_PATTERNS.items():
            if pattern.search(html):
                detected_techs.add((tech_name, category, "High"))

        # Create soup for additional checks
        soup = BeautifulSoup(html, 'html.parser')

        # Check meta generator tags
        generator = soup.find('meta', attrs={'name': 'generator'})
        if generator and 'content' in generator.attrs:
            content = generator['content'].lower()
            if 'wordpress' in content:
                detected_techs.add(("WordPress", "CMS", "Very High"))
            elif 'wix' in content:
                detected_techs.add(("Wix", "Website Builder", "Very High"))
            elif 'shopify' in content:
                detected_techs.add(("Shopify", "E-commerce Platform", "Very High"))

        # Check for cryptocurrency-specific technology
        crypto_terms = ['blockchain', 'token', 'crypto', 'nft', 'defi', 'dao', 'web3']
        for term in crypto_terms:
            if re.search(r'\b' + re.escape(term) + r'\b', html, re.IGNORECASE):
                detected_techs.add((f"{term.upper()}", "Blockchain Terminology", "Medium"))

        # Convert to list of dictionaries
        for name, category, confidence in detected_techs:
            tech_stack.append({
                "name": name,
                "category": category,
                "confidence": confidence
            })

        # Sort by category
        tech_stack.sort(key=lambda x: x["category"])

        return tech_stack

    def _extract_links(self, soup: BeautifulSoup, url: str) -> Dict[str, List[Any]]:
        """Extract and categorize links"""
        links = {
            "internal": [],
            "external": [],
            "social": [],
            "blockchain": []
        }

        base_domain = urlparse(url).netloc

        # Process all links
        for a_tag in soup.select('a[href]'):
            href = a_tag.get('href', '')

            # Skip anchors, javascript, and mailto
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue

            # Normalize URL
            if not href.startswith(('http://', 'https://')):
                href = urljoin(url, href)

            # Parse URL
            parsed_href = urlparse(href)
            href_domain = parsed_href.netloc

            # Check for blockchain explorer links
            is_blockchain = False
            for explorer_domain, blockchain in BLOCKCHAIN_PATTERNS.items():
                if explorer_domain in href_domain:
                    links["blockchain"].append({
                        "url": href,
                        "blockchain": blockchain,
                        "text": a_tag.get_text(strip=True) or blockchain
                    })
                    is_blockchain = True
                    break

            if is_blockchain:
                continue

            # Check for social media links
            is_social = False
            for social_domain, platform in SOCIAL_PATTERNS.items():
                if social_domain in href_domain:
                    if not any(s.get("url") == href for s in links["social"]):
                        links["social"].append({
                            "url": href,
                            "platform": platform,
                            "text": a_tag.get_text(strip=True) or platform
                        })
                        is_social = True
                        break

            if is_social:
                continue

            # Categorize as internal or external
            if href_domain == base_domain or not href_domain:
                if href not in links["internal"]:
                    links["internal"].append(href)
            else:
                if href not in links["external"]:
                    links["external"].append(href)

        return links

    def _analyze_resources(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Analyze website resources"""
        resources = {
            "images": [],
            "scripts": [],
            "styles": [],
            "total_count": 0,
            "has_minified": False,
            "has_cdn": False
        }

        # Extract images (up to 20)
        for img in soup.find_all('img', src=True)[:20]:
            img_src = img['src']

            if not img_src.startswith(('http://', 'https://', 'data:')):
                img_src = urljoin(url, img_src)

            if img_src not in resources["images"] and not img_src.startswith('data:'):
                resources["images"].append(img_src)

        # Extract scripts (up to 20)
        for script in soup.find_all('script', src=True)[:20]:
            script_src = script['src']

            if not script_src.startswith(('http://', 'https://')):
                script_src = urljoin(url, script_src)

            if script_src not in resources["scripts"]:
                resources["scripts"].append(script_src)

                # Check for minified resources
                if any(pattern in script_src.lower() for pattern in MINIFIED_PATTERNS):
                    resources["has_minified"] = True

                # Check for CDN usage
                if any(pattern in script_src.lower() for pattern in CDN_PATTERNS):
                    resources["has_cdn"] = True

        # Extract stylesheets (up to 10)
        for link in soup.find_all('link', rel='stylesheet')[:10]:
            if 'href' in link.attrs:
                css_href = link['href']

                if not css_href.startswith(('http://', 'https://')):
                    css_href = urljoin(url, css_href)

                if css_href not in resources["styles"]:
                    resources["styles"].append(css_href)

                    # Check for minified resources
                    if any(pattern in css_href.lower() for pattern in MINIFIED_PATTERNS):
                        resources["has_minified"] = True

                    # Check for CDN usage
                    if any(pattern in css_href.lower() for pattern in CDN_PATTERNS):
                        resources["has_cdn"] = True

        # Calculate totals
        resources["total_count"] = len(resources["images"]) + len(resources["scripts"]) + len(resources["styles"])

        return resources

    def _analyze_social_media(self, links: Dict[str, List[Any]]) -> Dict[str, Any]:
        """Analyze social media presence"""
        social_links = links.get("social", [])
        platforms = {}

        # Count unique platforms
        for link in social_links:
            platform = link.get("platform", "")
            if platform:
                platforms[platform] = platforms.get(platform, 0) + 1

        # Calculate platform count
        platform_count = len(platforms)

        result = {
            "platforms": [{"name": p, "count": c, "url": next((l["url"] for l in social_links if l["platform"] == p), "")} 
                        for p, c in platforms.items()],
            "total_count": len(social_links),
            "unique_platforms": platform_count,
            "has_twitter": "Twitter" in platforms,
            "has_telegram": "Telegram" in platforms,
            "has_discord": "Discord" in platforms,
            "has_github": "GitHub" in platforms,
            "platform_count": platform_count,  # Store raw data needed for scoring
            "platform_data": platforms         # Store raw data needed for scoring
        }

        return result

    def _calculate_social_score(self, social_media: Dict[str, Any]) -> int:
        """Calculate social media presence score"""
        # Extract needed data
        platform_count = social_media.get("platform_count", 0)
        platforms = social_media.get("platform_data", {})
        
        # Base score based on number of platforms
        if platform_count >= 5:
            score = 80 + min(20, (platform_count - 5) * 4)
        elif platform_count >= 3:
            score = 60 + ((platform_count - 3) * 10)
        elif platform_count >= 1:
            score = 30 + (platform_count * 15)
        else:
            score = 0

        # Bonus for crypto-important platforms
        if "Twitter" in platforms:
            score += 5
        if "Telegram" in platforms:
            score += 5
        if "Discord" in platforms:
            score += 5
        if "GitHub" in platforms:
            score += 10

        return min(100, score)
    
    def _analyze_blockchain_integration(self, html: str, links: Dict[str, List[Any]]) -> Dict[str, Any]:
        """Analyze blockchain integration"""
        blockchain_links = links.get("blockchain", [])
        result = {
            "has_integration": False,
            "blockchains": [],
            "wallet_connections": [],
            "contract_addresses": [],
            "has_wallet_connect": False,
            "score": 0
        }
        
        # Check blockchain explorer links
        blockchains = set()
        for link in blockchain_links:
            blockchain = link.get("blockchain", "")
            if blockchain:
                blockchains.add(blockchain)
        
        result["blockchains"] = list(blockchains)
        
        # Check for wallet connection UI
        wallet_patterns = [
            (r'connect\s+wallet', "Connect Wallet"),
            (r'connect\s+to\s+wallet', "Connect to Wallet"),
            (r'wallet\s+connect', "Wallet Connect"),
            (r'sign\s+in\s+with\s+wallet', "Sign in with Wallet"),
            (r'login\s+with\s+wallet', "Login with Wallet")
        ]
        
        for pattern, name in wallet_patterns:
            if re.search(pattern, html, re.IGNORECASE):
                result["has_wallet_connect"] = True
                result["wallet_connections"].append(name)
                break
                
        # Check for wallet providers
        wallet_providers = {
            "metamask": "MetaMask",
            "phantom": "Phantom",
            "walletconnect": "WalletConnect",
            "coinbase wallet": "Coinbase Wallet",
            "trust wallet": "Trust Wallet",
            "solflare": "Solflare",
            "slope": "Slope",
            "glow": "Glow",
            "ledger": "Ledger",
            "trezor": "Trezor",
        }
        
        detected_wallets = []
        for keyword, provider in wallet_providers.items():
            if re.search(r'\b' + re.escape(keyword) + r'\b', html, re.IGNORECASE):
                detected_wallets.append(provider)
                
        if detected_wallets:
            result["wallet_connections"].extend(detected_wallets)
            result["has_wallet_connect"] = True
            
        # Extract blockchain addresses
        eth_address_pattern = r'0x[a-fA-F0-9]{40}'
        solana_address_pattern = r'[1-9A-HJ-NP-Za-km-z]{32,44}'
        
        eth_addresses = set(re.findall(eth_address_pattern, html))
        solana_addresses = set(re.findall(solana_address_pattern, html))
        
        for addr in eth_addresses:
            result["contract_addresses"].append({"address": addr, "blockchain": "Ethereum"})
            
        for addr in solana_addresses:
            result["contract_addresses"].append({"address": addr, "blockchain": "Solana"})
            
        # Determine if site has blockchain integration
        result["has_integration"] = (
            len(blockchains) > 0 or 
            result["has_wallet_connect"] or 
            len(result["contract_addresses"]) > 0
        )
        
        # Calculate blockchain integration score
        score = 0
        
        # Points for blockchain explorer links
        score += min(40, len(blockchains) * 20)
        
        # Points for wallet connections
        if result["has_wallet_connect"]:
            score += 30
            
        # Points for each wallet provider
        score += min(20, len(detected_wallets) * 10)
        
        # Points for contract addresses
        score += min(10, len(result["contract_addresses"]) * 5)
        
        result["score"] = score
        
        return result

    def _analyze_content_quality(self, soup: BeautifulSoup, text_content: str) -> Dict[str, Any]:
        """Analyze content quality with protection against excessive content"""
        # Set a reasonable limit for content size
        MAX_CONTENT_SIZE = 500_000  # ~500KB
        
        result = {
            "word_count": 0,
            "has_headings": False,
            "heading_count": 0,
            "paragraph_count": 0,
            "image_count": 0,
            "list_count": 0,
            "has_footer": False,
            "has_proper_structure": False,
            "crypto_terms": [],
            "score": 0
        }
        
        # Check if content is too large
        if len(text_content) > MAX_CONTENT_SIZE:
            logger.warning(f"Content size exceeds limit ({len(text_content)} bytes) - truncating")
            text_content = text_content[:MAX_CONTENT_SIZE]
        
        # Word count with protection against excessive regex computation
        words = re.findall(r'\b\w+\b', text_content[:100_000])  # Limit regex search
        result["word_count"] = len(words)
        
        # Apply limits to DOM queries to prevent excessive resource usage
        MAX_ELEMENTS = 1000
        
        # Count headings with limit
        headings = list(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'], limit=MAX_ELEMENTS))
        result["heading_count"] = len(headings)
        result["has_headings"] = result["heading_count"] > 0
        
        # Count paragraphs with limit
        paragraphs = list(soup.find_all('p', limit=MAX_ELEMENTS))
        result["paragraph_count"] = len(paragraphs)
        
        # Count images with limit
        images = list(soup.find_all('img', limit=MAX_ELEMENTS))
        result["image_count"] = len(images)
        
        # Count lists with limit
        lists = list(soup.find_all(['ul', 'ol'], limit=MAX_ELEMENTS))
        result["list_count"] = len(lists)
        
        # Check for footer with limit
        footer = soup.find('footer')
        result["has_footer"] = footer is not None
        
        # Proper structure check
        # A well-structured page typically has h1, multiple paragraphs, and some images
        h1 = soup.find('h1')
        result["has_proper_structure"] = (
            h1 is not None and 
            result["paragraph_count"] >= 3 and 
            result["image_count"] >= 1
        )
        
        # Check for crypto-specific terms
        crypto_terms = [
            "token", "blockchain", "crypto", "cryptocurrency", "bitcoin", "ethereum", 
            "solana", "nft", "defi", "web3", "wallet", "dao", "dapp", "staking", 
            "mining", "yield", "liquidity", "airdrop", "whitepaper", "roadmap"
        ]
        
        found_terms = []
        for term in crypto_terms:
            if re.search(r'\b' + re.escape(term) + r'\b', text_content, re.IGNORECASE):
                found_terms.append(term)
                
        result["crypto_terms"] = found_terms
        
        # Calculate content score
        score = 0
        
        # Points for word count
        if result["word_count"] >= 1000:
            score += 20
        elif result["word_count"] >= 500:
            score += 15
        elif result["word_count"] >= 200:
            score += 10
        elif result["word_count"] >= 100:
            score += 5
            
        # Points for structure
        if result["has_proper_structure"]:
            score += 20
        else:
            # Partial points for partial structure
            if result["has_headings"]:
                score += 5
            if result["paragraph_count"] >= 3:
                score += 5
            if result["image_count"] >= 1:
                score += 5
                
        # Points for rich content
        if result["list_count"] > 0:
            score += 5
        if result["has_footer"]:
            score += 5
            
        # Points for crypto terms (max 20)
        score += min(20, len(found_terms) * 4)
        
        result["score"] = score
        
        return result

    def _analyze_seo(self, soup: BeautifulSoup, metadata: Dict[str, str]) -> Dict[str, Any]:
        """Analyze SEO factors"""
        result = {
            "title_present": False,
            "title_length": 0,
            "title_quality": 0,
            "description_present": False,
            "description_length": 0,
            "description_quality": 0,
            "has_meta_tags": False,
            "has_og_tags": False,
            "has_twitter_tags": False,
            "has_h1": False,
            "mobile_friendly": False,
            "score": 0
        }
        
        # Title analysis
        title = metadata.get("title", "")
        result["title_present"] = bool(title)
        result["title_length"] = len(title)
        
        if result["title_present"]:
            # Score title (optimal length: 50-60 characters)
            if 50 <= result["title_length"] <= 60:
                result["title_quality"] = 100
            elif 40 <= result["title_length"] <= 70:
                result["title_quality"] = 80
            elif 30 <= result["title_length"] <= 80:
                result["title_quality"] = 60
            else:
                result["title_quality"] = 40
        
        # Description analysis
        description = metadata.get("description", "")
        result["description_present"] = bool(description)
        result["description_length"] = len(description)
        
        if result["description_present"]:
            # Score description (optimal length: 150-160 characters)
            if 150 <= result["description_length"] <= 160:
                result["description_quality"] = 100
            elif 140 <= result["description_length"] <= 170:
                result["description_quality"] = 80
            elif 120 <= result["description_length"] <= 190:
                result["description_quality"] = 60
            else:
                result["description_quality"] = 40
        
        # Check for Open Graph tags
        result["has_og_tags"] = any(key.startswith("og_") and value for key, value in metadata.items())
        
        # Check for Twitter Card tags
        result["has_twitter_tags"] = any(key.startswith("twitter_") and value for key, value in metadata.items())
        
        # Check for h1 tag
        result["has_h1"] = soup.find('h1') is not None
        
        # Check for mobile viewport meta tag
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        result["mobile_friendly"] = viewport is not None and 'content' in viewport.attrs
        
        # Calculate SEO score
        factors = [
            result["title_present"] * 15,  # Title presence
            (result["title_quality"] / 100) * 10,  # Title quality
            result["description_present"] * 15,  # Description presence
            (result["description_quality"] / 100) * 10,  # Description quality
            result["has_og_tags"] * 10,  # Open Graph
            result["has_twitter_tags"] * 5,  # Twitter Cards
            result["has_h1"] * 10,  # H1 heading
            result["mobile_friendly"] * 15  # Mobile friendly
        ]
        
        result["score"] = round(sum(factors))
        return result

    def _detect_template_site(self, soup: BeautifulSoup, html: str) -> Dict[str, Any]:
        """Detect if website uses common templates or has repetitive structure"""
        result = {
            "is_template": False,
            "template_indicators": [],
            "repetitive_structure": False,
            "generic_sections": 0,
            "template_confidence": 0
        }
        
        # Check for template indicators
        template_patterns = {
            r'pancakeswap': "PancakeSwap Clone",
            r'uniswap': "Uniswap Clone",
            r'id="countdown"': "Presale Countdown Template",
            r'class="token\-?metrics"': "Token Metrics Template",
            r'class="roadmap"': "Generic Roadmap Section",
            r'class="team\-?member"': "Generic Team Section",
            r'id="tokenomics"': "Generic Tokenomics Section",
            r'class="(token|coin)\-?distribution"': "Token Distribution Template"
        }
        
        # Check each pattern
        for pattern, indicator in template_patterns.items():
            if re.search(pattern, html, re.IGNORECASE):
                result["template_indicators"].append(indicator)
        
        # Check for repetitive structure
        sections = soup.find_all(['section', 'div'], {'class': ['section', 'container']})
        
        if len(sections) >= 4:
            # Count sections with similar structure
            similar_sections = 0
            
            for i in range(len(sections) - 1):
                current = sections[i]
                next_section = sections[i + 1]
                
                # Check if they have similar structure
                if (current.name == next_section.name and
                    len(current.find_all()) > 3 and
                    abs(len(current.find_all()) - len(next_section.find_all())) <= 3):
                    similar_sections += 1
            
            result["generic_sections"] = similar_sections
            result["repetitive_structure"] = similar_sections >= 2
        
        # Generic crypto sections check
        generic_sections = [
            'hero', 'about', 'features', 'roadmap', 'tokenomics', 
            'team', 'partners', 'faq', 'contact'
        ]
        
        found_generic = 0
        for section in generic_sections:
            # Check for section id, class, or heading containing the section name
            if (soup.find(id=section) or 
                soup.find(class_=section) or 
                soup.find(id=re.compile(section, re.I)) or 
                soup.find(class_=re.compile(section, re.I)) or
                soup.find(['h1', 'h2', 'h3'], string=re.compile(section, re.I))):
                found_generic += 1
        
        result["generic_sections"] += found_generic
        
        # Determine if it's a template site
        result["is_template"] = (
            len(result["template_indicators"]) > 0 or
            result["repetitive_structure"] or
            result["generic_sections"] >= 4
        )
        
        # Calculate confidence
        if len(result["template_indicators"]) >= 2:
            result["template_confidence"] = 90
        elif len(result["template_indicators"]) == 1 and result["repetitive_structure"]:
            result["template_confidence"] = 80
        elif result["repetitive_structure"]:
            result["template_confidence"] = 70
        elif result["generic_sections"] >= 5:
            result["template_confidence"] = 60
        elif result["generic_sections"] >= 3:
            result["template_confidence"] = 50
        else:
            result["template_confidence"] = 30 if result["is_template"] else 0
        
        return result

    def _calculate_domain_score(self, domain_info: Dict[str, Any]) -> int:
        """Calculate domain score focusing on crypto-specific factors"""
        # Start with neutral score - new domains are common in crypto
        score = 60
        
        # Domain age (less punishing for crypto projects)
        age_days = domain_info.get("age_days", 0)
        
        if age_days < 7:  # Very new (less than a week)
            score -= 10
        elif age_days < 30:  # New (less than a month)
            score -= 5
        elif age_days > 180:  # More than 6 months
            score += 10
        elif age_days > 365:  # More than a year
            score += 20
        
        # Registrar reputation
        registrar = domain_info.get("registrar", "").lower()
        reputable_registrars = [
            "namecheap", "godaddy", "name.com", "cloudflare", "google domains",
            "amazon", "namesilo", "porkbun", "dynadot", "hover"
        ]
        
        if any(r in registrar for r in reputable_registrars):
            score += 10
        
        # Domain expiration
        days_until_expiry = domain_info.get("days_until_expiry", 0)
        if days_until_expiry > 180:  # More than 6 months
            score += 10
        elif days_until_expiry < 30:  # Less than a month
            score -= 20
        
        # Privacy protection (good for crypto projects)
        if domain_info.get("privacy_protected", False):
            score += 10
        
        # Ensure score is within 0-100 range
        return max(0, min(100, score))

    def _calculate_security_score(self, ssl_info: Dict[str, Any], security_headers: Dict[str, Any]) -> int:
        """Calculate security score"""
        score = 0
        
        # SSL adds up to 50 points
        if ssl_info.get("has_ssl", False):
            score += 30  # Base points for having SSL
            
            # Bonus points for SSL days remaining (max 10)
            days_remaining = ssl_info.get("days_remaining", 0)
            if days_remaining > 90:
                score += 10
            elif days_remaining > 60:
                score += 7
            elif days_remaining > 30:
                score += 5
            elif days_remaining > 14:
                score += 2
            
            # Bonus for recognized certificate authority (max 10)
            issuer = ssl_info.get("issuer", "").lower()
            trusted_issuers = ["let's encrypt", "digicert", "comodo", "godaddy", "globalsign", "amazon", "sectigo"]
            if any(trusted in issuer for trusted in trusted_issuers):
                score += 10
            else:
                score += 5
        
        # Security headers add up to 50 points
        header_count = security_headers.get("implemented_count", 0)
        total_headers = security_headers.get("total_count", 7)
        
        # Calculate proportion of implemented headers
        if total_headers > 0:
            header_score = round((header_count / total_headers) * 50)
            score += header_score
            
            # Bonus for critical security headers
            if security_headers.get("content-security-policy"):
                score += 5
            if security_headers.get("strict-transport-security"):
                score += 5
        
        # Ensure score is within 0-100 range
        return max(0, min(100, score))

    def _calculate_tech_score(self, tech_stack: List[Dict[str, Any]], blockchain_info: Dict[str, Any]) -> int:
        """Calculate technology implementation score"""
        score = 50  # Start with neutral score
        
        # Points for technology diversity (max 20)
        tech_count = len(tech_stack)
        tech_categories = set(tech["category"] for tech in tech_stack)
        
        if tech_count >= 5:
            score += 15
        elif tech_count >= 3:
            score += 10
        elif tech_count >= 1:
            score += 5
            
        # Bonus for diverse categories
        if len(tech_categories) >= 3:
            score += 5
            
        # Points for modern frameworks (max 15)
        modern_techs = ["React", "Vue.js", "Next.js", "Tailwind CSS"]
        used_modern_techs = sum(1 for tech in tech_stack if tech["name"] in modern_techs)
        score += min(15, used_modern_techs * 5)
        
        # Points for blockchain tech specifically (max 30)
        blockchain_techs = ["Web3.js", "Ethers.js", "Solana Web3", "Phantom", "MetaMask"]
        used_blockchain_techs = sum(1 for tech in tech_stack if tech["name"] in blockchain_techs)
        score += min(30, used_blockchain_techs * 10)
        
        # Blockchain integration (max 30)
        if blockchain_info.get("has_integration", False):
            score += 15
            
            # Bonus for wallet connect
            if blockchain_info.get("has_wallet_connect", False):
                score += 10
                
            # Bonus for contract addresses
            if len(blockchain_info.get("contract_addresses", [])) > 0:
                score += 5
                
        # Ensure score is within 0-100 range
        return max(0, min(100, score))

    def _calculate_perf_score(self, performance: Dict[str, Any], resources: Dict[str, Any]) -> int:
        """Calculate performance score"""
        # Start with neutral score
        score = 70
        
        # Points for fast loading time
        load_time = performance.get("load_time", 0)
        if load_time < 1.0:
            score += 20
        elif load_time < 2.0:
            score += 15
        elif load_time < 3.0:
            score += 10
        elif load_time < 4.0:
            score += 5
        elif load_time > 6.0:
            score -= 10
        elif load_time > 8.0:
            score -= 20
            
        # Points for resource optimization
        if resources.get("has_minified", False):
            score += 10
        if resources.get("has_cdn", False):
            score += 10
            
        # Penalty for excessive resources
        resource_count = resources.get("total_count", 0)
        if resource_count > 100:
            score -= 20
        elif resource_count > 50:
            score -= 10
        elif resource_count > 30:
            score -= 5
            
        # Ensure score is within 0-100 range
        return max(0, min(100, score))

    def _calculate_content_score(self, content_quality: Dict[str, Any], seo_info: Dict[str, Any], metadata: Dict[str, str]) -> int:
        """Calculate content quality score"""
        # Use the content quality score as base
        score = content_quality.get("score", 0)
        
        # Add SEO points (max 30)
        score += round(seo_info.get("score", 0) * 0.3)
        
        # Add points for good metadata
        if metadata.get("title") and metadata.get("description"):
            score += 10
            
            # Bonus for crypto keywords in metadata
            crypto_keywords = ["token", "blockchain", "crypto", "nft", "defi", "web3"]
            if any(keyword in (metadata.get("title", "") + metadata.get("description", "")).lower() for keyword in crypto_keywords):
                score += 10
                
        # Ensure score is within 0-100 range
        return max(0, min(100, score))

    def _calculate_overall_score(self, scores: Dict[str, int]) -> int:
        """Calculate overall legitimacy score with weighted factors"""
        # Define weights for each factor (sum should be 1.0)
        weights = {
            "domain": 0.10,      # Domain age and registrar
            "security": 0.20,    # SSL and security headers
            "tech": 0.25,        # Technical implementation (most important for crypto)
            "content": 0.15,     # Content quality and SEO
            "performance": 0.05, # Site performance
            "social": 0.15,      # Social media presence
            "blockchain": 0.10   # Blockchain integration
        }
        
        # Calculate weighted score
        weighted_score = sum(scores.get(key, 0) * weight for key, weight in weights.items())
        
        # Round to nearest integer
        return round(weighted_score)

    def _generate_risk_assessment(self, 
                            domain_info: Dict[str, Any], 
                            ssl_info: Dict[str, Any], 
                            security_headers: Dict[str, Any],
                            tech_stack: List[Dict[str, Any]],
                            blockchain_info: Dict[str, Any],
                            template_analysis: Dict[str, Any],
                            virustotal_results: Optional[Dict[str, Any]],
                            scores: Dict[str, int],
                            legitimacy_score: int) -> Dict[str, Any]:
        """Generate risk assessment based on all factors"""
        # Initialize risk assessment
        risk_assessment = {
            "risk_level": "",
            "color": 0,  # Discord color code
            "emoji": "",
            "issues": [],
            "strengths": [],
            "investment_advice": "",
            "template_concern": False,
            "security_concern": False,
            "blockchain_concern": False,
            "domain_concern": False,
            "score": legitimacy_score
        }
        
        # Identify issues
        issues = []
        strengths = []
        
        # Domain issues
        age_days = domain_info.get("age_days", 0)
        if age_days < 7:
            issues.append("Domain is extremely new (less than 1 week old)")
            risk_assessment["domain_concern"] = True
        elif age_days < 30:
            issues.append("Domain is very new (less than 1 month old)")
            risk_assessment["domain_concern"] = True
        elif age_days > 180:
            strengths.append(f"Domain is well established ({age_days} days old)")
            
        if domain_info.get("privacy_protected", False):
            strengths.append("Domain has WHOIS privacy protection")
            
        # SSL issues
        if not ssl_info.get("has_ssl", False):
            issues.append("No SSL certificate (site not using HTTPS)")
            risk_assessment["security_concern"] = True
        else:
            strengths.append("Site uses HTTPS encryption")
            
            days_remaining = ssl_info.get("days_remaining", 0)
            if days_remaining < 14:
                issues.append(f"SSL certificate expiring soon ({days_remaining} days)")
                risk_assessment["security_concern"] = True
            elif days_remaining > 60:
                strengths.append(f"SSL certificate valid for {days_remaining} days")
                
        # Security headers
        header_count = security_headers.get("implemented_count", 0)
        if header_count == 0:
            issues.append("No security headers implemented")
            risk_assessment["security_concern"] = True
        elif header_count < 3:
            issues.append("Few security headers implemented")
        elif header_count >= 5:
            strengths.append("Good security header implementation")
            
        # Template concerns
        if template_analysis.get("is_template", False):
            confidence = template_analysis.get("template_confidence", 0)
            if confidence > 70:
                issues.append("Site uses a generic crypto template")
                risk_assessment["template_concern"] = True
            elif confidence > 50:
                issues.append("Site structure appears to use common templates")
            
        # Blockchain integration
        if blockchain_info.get("has_integration", False):
            strengths.append("Site has blockchain integration")
            
            if blockchain_info.get("has_wallet_connect", False):
                strengths.append("Wallet connection functionality")
                
            if len(blockchain_info.get("contract_addresses", [])) > 0:
                strengths.append("Contract addresses found on site")
        elif any("blockchain" in tech["category"] for tech in tech_stack):
            issues.append("Uses blockchain libraries but no wallet integration")
            risk_assessment["blockchain_concern"] = True
            
        # VirusTotal results
        if virustotal_results and virustotal_results.get("malicious_count", 0) > 0:
            issues.append(f"Domain flagged by {virustotal_results.get('malicious_count')} security vendors")
            risk_assessment["security_concern"] = True
            
        # Social media presence
        social_score = scores.get("social", 0)
        if social_score < 30:
            issues.append("Limited or no social media presence")
        elif social_score > 70:
            strengths.append("Strong social media presence")
            
        # Technology assessment
        tech_score = scores.get("tech", 0)
        if tech_score < 30:
            issues.append("Limited technical implementation")
        elif tech_score > 70:
            strengths.append("Solid technical implementation")
            
        # Store identified issues and strengths
        risk_assessment["issues"] = issues[:5]  # Limit to top 5
        risk_assessment["strengths"] = strengths[:5]  # Limit to top 5
        
        # Calculate overall risk level based on legitimacy score
        if legitimacy_score >= 80:
            risk_assessment["risk_level"] = "LOW RISK"
            risk_assessment["color"] = 0x4CAF50  # Green
            risk_assessment["emoji"] = "✅"
            risk_assessment["investment_advice"] = "Project appears technically legitimate"
        elif legitimacy_score >= 65:
            risk_assessment["risk_level"] = "MODERATE RISK"
            risk_assessment["color"] = 0xFFD700  # Gold
            risk_assessment["emoji"] = "⚠️"
            risk_assessment["investment_advice"] = "Acceptable implementation with some concerns"
        elif legitimacy_score >= 50:
            risk_assessment["risk_level"] = "ELEVATED RISK"
            risk_assessment["color"] = 0xFF9800  # Orange
            risk_assessment["emoji"] = "⚠️"
            risk_assessment["investment_advice"] = "Exercise caution - several concerns detected"
        elif legitimacy_score >= 30:
            risk_assessment["risk_level"] = "HIGH RISK"
            risk_assessment["color"] = 0xFF5722  # Deep Orange
            risk_assessment["emoji"] = "🔶"
            risk_assessment["investment_advice"] = "Multiple significant concerns identified"
        else:
            risk_assessment["risk_level"] = "VERY HIGH RISK"
            risk_assessment["color"] = 0xF44336  # Red
            risk_assessment["emoji"] = "🚨"
            risk_assessment["investment_advice"] = "Critical issues detected - exercise extreme caution"
            
        # Adjust for critical concerns that might override the score
        critical_concerns = sum([
            risk_assessment["security_concern"],
            risk_assessment["domain_concern"] and age_days < 7,
            risk_assessment["template_concern"] and template_analysis.get("template_confidence", 0) > 80,
            bool(virustotal_results and virustotal_results.get("malicious_count", 0) > 2)
        ])
        
        if critical_concerns >= 2 and legitimacy_score >= 50:
            # Downgrade by one level due to critical concerns
            if risk_assessment["risk_level"] == "LOW RISK":
                risk_assessment["risk_level"] = "MODERATE RISK"
                risk_assessment["color"] = 0xFFD700
                risk_assessment["emoji"] = "⚠️"
                risk_assessment["investment_advice"] = "Some concerns despite good implementation"
            elif risk_assessment["risk_level"] == "MODERATE RISK":
                risk_assessment["risk_level"] = "ELEVATED RISK"
                risk_assessment["color"] = 0xFF9800
                risk_assessment["emoji"] = "⚠️"
                risk_assessment["investment_advice"] = "Notable concerns despite acceptable implementation"
                
        return risk_assessment