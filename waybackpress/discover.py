"""
URL discovery from Wayback Machine CDX API.
"""

import asyncio
import logging
from typing import Set, List
from pathlib import Path
import aiohttp

from .config import ProjectConfig
from .utils import normalize_url, is_post_url


logger = logging.getLogger('waybackpress.discover')


class URLDiscoverer:
    """Discovers URLs for a domain from Wayback Machine."""
    
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.discovered_urls: Set[str] = set()
    
    async def query_cdx(self, session: aiohttp.ClientSession) -> List[str]:
        """
        Query Wayback CDX API for all URLs from domain.
        
        Args:
            session: aiohttp session for requests
            
        Returns:
            List of discovered URLs
        """
        cdx_url = (
            f"https://web.archive.org/cdx/search/cdx"
            f"?url={self.config.domain}"
            f"&matchType=domain"
            f"&output=txt"
            f"&fl=original"
            f"&collapse=urlkey"
        )
        
        logger.info(f"Querying Wayback CDX API for {self.config.domain}")
        logger.debug(f"CDX query: {cdx_url}")
        
        try:
            async with session.get(cdx_url) as response:
                if response.status != 200:
                    logger.error(f"CDX API returned status {response.status}")
                    return []
                
                text = await response.text()
                urls = [line.strip() for line in text.split('\n') if line.strip()]
                
                logger.info(f"Found {len(urls)} unique URLs in Wayback Machine")
                return urls
        
        except Exception as e:
            logger.error(f"Failed to query CDX API: {e}")
            return []
    
    def filter_post_urls(self, urls: List[str]) -> List[str]:
        """
        Filter URLs to keep only potential posts.
        
        Args:
            urls: List of URLs to filter
            
        Returns:
            List of filtered post URLs
        """
        logger.info("Filtering URLs to identify posts")
        
        post_urls = []
        for url in urls:
            if is_post_url(url, self.config.domain):
                post_urls.append(url)
        
        logger.info(f"Identified {len(post_urls)} potential post URLs")
        return post_urls
    
    def deduplicate_urls(self, urls: List[str]) -> List[str]:
        """
        Deduplicate URLs by normalizing and removing duplicates.
        
        Args:
            urls: List of URLs to deduplicate
            
        Returns:
            List of unique URLs
        """
        logger.info("Deduplicating URLs")
        
        seen = set()
        unique_urls = []
        
        for url in urls:
            normalized = normalize_url(url)
            if normalized not in seen:
                seen.add(normalized)
                unique_urls.append(url)
        
        removed = len(urls) - len(unique_urls)
        if removed > 0:
            logger.info(f"Removed {removed} duplicate URLs")
        
        return unique_urls
    
    def save_urls(self, urls: List[str]) -> None:
        """
        Save discovered URLs to file.
        
        Args:
            urls: List of URLs to save
        """
        output_file = self.config.get_paths()['discovered_urls']
        
        logger.info(f"Saving {len(urls)} URLs to {output_file}")
        
        with open(output_file, 'w') as f:
            f.write("url\n")
            for url in sorted(urls):
                f.write(f"{url}\n")
        
        logger.info(f"Saved to {output_file}")
    
    async def query_single_url(self, session: aiohttp.ClientSession, url: str) -> bool:
        """
        Query CDX API to verify a single URL exists in Wayback Machine.
        
        Args:
            session: aiohttp session for requests
            url: URL to query
            
        Returns:
            True if URL found in Wayback, False otherwise
        """
        cdx_url = (
            f"https://web.archive.org/cdx/search/cdx"
            f"?url={url}"
            f"&output=json"
            f"&limit=1"
        )
        
        logger.info(f"Querying Wayback Machine for: {url}")
        logger.debug(f"CDX query: {cdx_url}")
        
        try:
            async with session.get(cdx_url) as response:
                if response.status != 200:
                    logger.error(f"CDX API returned status {response.status}")
                    return False
                
                text = await response.text()
                # CDX returns JSON array, first item is headers
                if text.strip() and text.count('[') > 0:
                    logger.info(f"URL found in Wayback Machine")
                    return True
                else:
                    logger.warning(f"URL not found in Wayback Machine")
                    return False
        
        except Exception as e:
            logger.error(f"Failed to query CDX API: {e}")
            return False
    
    async def discover_single(self, url: str) -> int:
        """
        Discover a single URL from Wayback Machine.
        
        Args:
            url: Single URL to extract
            
        Returns:
            Number of URLs discovered (0 or 1)
        """
        logger.info(f"Starting single URL extraction for {url}")
        
        async with aiohttp.ClientSession(
            headers={'User-Agent': self.config.user_agent}
        ) as session:
            # Query CDX API for this URL
            found = await self.query_single_url(session, url)
            
            if not found:
                logger.error(f"URL not found in Wayback Machine: {url}")
                return 0
            
            # Load existing URLs if file exists
            existing_urls = set()
            output_file = self.config.get_paths()['discovered_urls']
            if output_file.exists():
                try:
                    with open(output_file, 'r') as f:
                        lines = f.readlines()
                        # Skip header
                        for line in lines[1:]:
                            if line.strip():
                                existing_urls.add(line.strip())
                except Exception as e:
                    logger.warning(f"Could not load existing URLs: {e}")
            
            # Add new URL
            existing_urls.add(url)
            
            # Save all URLs
            self.save_urls(list(existing_urls))
            
            # Update config
            self.config.discovered = True
            config_path = self.config.output_dir / 'config.json'
            self.config.save(config_path)
            
            logger.info(f"Single URL extraction complete")
            
            return 1
    
    async def discover(self) -> int:
        """
        Main discovery process.
        
        Returns:
            Number of URLs discovered
        """
        logger.info(f"Starting URL discovery for {self.config.domain}")
        
        async with aiohttp.ClientSession(
            headers={'User-Agent': self.config.user_agent}
        ) as session:
            # Query CDX API
            all_urls = await self.query_cdx(session)
            
            if not all_urls:
                logger.warning("No URLs found in Wayback Machine")
                return 0
            
            # Filter for posts
            post_urls = self.filter_post_urls(all_urls)
            
            # Deduplicate
            unique_urls = self.deduplicate_urls(post_urls)
            
            # Save results
            self.save_urls(unique_urls)
            
            # Update config
            self.config.discovered = True
            config_path = self.config.output_dir / 'config.json'
            self.config.save(config_path)
            
            logger.info(f"Discovery complete: {len(unique_urls)} post URLs found")
            
            return len(unique_urls)


async def discover_urls(config: ProjectConfig, single_url: str = None) -> int:
    """
    Discover URLs for a domain or extract a single URL.
    
    Args:
        config: Project configuration
        single_url: Optional single URL to extract instead of entire site
        
    Returns:
        Number of URLs discovered
    """
    discoverer = URLDiscoverer(config)
    if single_url:
        return await discoverer.discover_single(single_url)
    else:
        return await discoverer.discover()

