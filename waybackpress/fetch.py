"""
Media fetching from Wayback Machine with multi-pass retry.
"""

import asyncio
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Set, Optional
from urllib.parse import urlparse, urljoin

import aiohttp
from bs4 import BeautifulSoup

from .config import ProjectConfig
from .utils import (
    get_local_path_for_url,
    construct_wayback_url,
    truncate_string,
    format_bytes,
)


logger = logging.getLogger('waybackpress.fetch')


class MediaFetcher:
    """Fetches media assets from Wayback Machine."""
    
    def __init__(self, config: ProjectConfig, pass_number: int = 1):
        self.config = config
        self.pass_number = pass_number
        self.media_urls: Set[str] = set()
        self.results: List[Dict[str, Any]] = []
        self.semaphore = asyncio.Semaphore(config.concurrency)
    
    def load_valid_posts(self) -> List[Dict[str, str]]:
        """Load validated posts."""
        posts_file = self.config.get_paths()['valid_posts']
        
        if not posts_file.exists():
            raise FileNotFoundError(
                "No valid posts found. Run 'validate' command first."
            )
        
        posts = []
        with open(posts_file, 'r') as f:
            # Skip header
            next(f)
            for line in f:
                if line.strip():
                    url, local_path = line.strip().split('\t')
                    posts.append({'url': url, 'local_path': local_path})
        
        logger.info(f"Loaded {len(posts)} validated posts")
        return posts
    
    def extract_media_urls(self, html_path: Path, base_url: str) -> Set[str]:
        """
        Extract media URLs from HTML file.
        
        Args:
            html_path: Path to HTML file
            base_url: Base URL for resolving relative URLs
            
        Returns:
            Set of absolute media URLs
        """
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'lxml')
            
            media_urls = set()
            
            # Images
            for img in soup.find_all('img'):
                src = img.get('src')
                if src:
                    absolute_url = urljoin(base_url, src)
                    if absolute_url.startswith('http'):
                        media_urls.add(absolute_url)
            
            # CSS files
            for link in soup.find_all('link', rel='stylesheet'):
                href = link.get('href')
                if href:
                    absolute_url = urljoin(base_url, href)
                    if absolute_url.startswith('http'):
                        media_urls.add(absolute_url)
            
            # JavaScript files
            for script in soup.find_all('script'):
                src = script.get('src')
                if src:
                    absolute_url = urljoin(base_url, src)
                    if absolute_url.startswith('http'):
                        media_urls.add(absolute_url)
            
            return media_urls
        
        except Exception as e:
            logger.debug(f"Failed to extract media from {html_path}: {e}")
            return set()
    
    def discover_all_media(self, posts: List[Dict[str, str]]) -> None:
        """
        Discover all media URLs from posts.
        
        Args:
            posts: List of post dicts with url and local_path
        """
        logger.info("Discovering media URLs from posts")
        
        for post in posts:
            html_path = Path(post['local_path'])
            if not html_path.exists():
                continue
            
            media = self.extract_media_urls(html_path, post['url'])
            self.media_urls.update(media)
        
        logger.info(f"Found {len(self.media_urls)} unique media URLs")
    
    async def get_snapshots(
        self,
        session: aiohttp.ClientSession,
        url: str,
        limit: int = 20
    ) -> List[str]:
        """
        Get available Wayback snapshots for a URL.
        
        Args:
            session: aiohttp session
            url: URL to query
            limit: Maximum number of snapshots to return
            
        Returns:
            List of timestamps
        """
        cdx_url = (
            f"https://web.archive.org/cdx/search/cdx"
            f"?url={url}"
            f"&output=json"
            f"&limit={limit}"
        )
        
        try:
            async with session.get(cdx_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return []
                
                data = await response.json()
                if len(data) < 2:  # Header + at least one result
                    return []
                
                # Extract timestamps (skip header)
                timestamps = [row[1] for row in data[1:]]
                return timestamps
        
        except Exception as e:
            logger.debug(f"CDX query failed for {truncate_string(url)}: {e}")
            return []
    
    async def download_asset(
        self,
        session: aiohttp.ClientSession,
        url: str,
        max_attempts: int = 5
    ) -> Dict[str, Any]:
        """
        Download a single media asset with multi-snapshot retry.
        
        Args:
            session: aiohttp session
            url: Original URL to download
            max_attempts: Maximum snapshots to try
            
        Returns:
            Result dict with status and metadata
        """
        async with self.semaphore:
            local_path = get_local_path_for_url(url, self.config.get_paths()['media'])
            
            result = {
                'asset_url': url,
                'local_path': str(local_path),
                'status': 'FAIL',
                'snapshots_tried': 0,
                'snapshots_available': 0,
                'success_timestamp': None,
            }
            
            # Check if already downloaded
            if local_path.exists():
                result['status'] = 'SKIP'
                return result
            
            # Get available snapshots
            timestamps = await self.get_snapshots(session, url, limit=max_attempts)
            result['snapshots_available'] = len(timestamps)
            
            if not timestamps:
                logger.debug(f"No snapshots: {truncate_string(url)}")
                return result
            
            # Try each snapshot
            for i, timestamp in enumerate(timestamps):
                result['snapshots_tried'] = i + 1
                
                wayback_url = construct_wayback_url(url, timestamp, 'im_')
                
                try:
                    await asyncio.sleep(self.config.delay)
                    
                    async with session.get(
                        wayback_url,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status == 200:
                            content = await response.read()
                            
                            # Save file
                            local_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(local_path, 'wb') as f:
                                f.write(content)
                            
                            result['status'] = 'OK'
                            result['success_timestamp'] = timestamp
                            result['size'] = len(content)
                            
                            logger.debug(f"✓ Downloaded: {truncate_string(url)} ({format_bytes(len(content))})")
                            return result
                
                except Exception as e:
                    logger.debug(f"Attempt {i+1} failed for {truncate_string(url)}: {e}")
                    continue
            
            # All attempts failed
            logger.debug(f"✗ Failed after {result['snapshots_tried']} attempts: {truncate_string(url)}")
            return result
    
    def load_previous_results(self) -> Dict[str, str]:
        """
        Load results from previous passes to avoid re-downloading.
        
        Returns:
            Dict mapping URL to status
        """
        report_file = self.config.get_paths()['media_report']
        
        if not report_file.exists():
            return {}
        
        previous = {}
        with open(report_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                previous[row['asset_url']] = row['status']
        
        logger.info(f"Loaded {len(previous)} results from previous pass")
        return previous
    
    def save_results(self) -> None:
        """Save fetch results to CSV."""
        report_file = self.config.get_paths()['media_report']
        
        logger.info(f"Saving {len(self.results)} results to {report_file}")
        
        with open(report_file, 'w', newline='') as f:
            fieldnames = [
                'asset_url', 'local_path', 'status', 'snapshots_tried',
                'snapshots_available', 'success_timestamp', 'size'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in self.results:
                writer.writerow(result)
    
    async def fetch_all(self) -> Dict[str, int]:
        """
        Main media fetching process.
        
        Returns:
            Dict with statistics
        """
        # Load posts and discover media
        posts = self.load_valid_posts()
        self.discover_all_media(posts)
        
        if not self.media_urls:
            logger.warning("No media URLs found")
            return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}
        
        # Load previous results
        previous = self.load_previous_results()
        
        # Filter out already successful downloads
        to_fetch = [url for url in self.media_urls if previous.get(url) != 'OK']
        
        if len(to_fetch) < len(self.media_urls):
            already_done = len(self.media_urls) - len(to_fetch)
            logger.info(f"Skipping {already_done} already downloaded files")
        
        logger.info(f"Starting media fetch (pass {self.pass_number})")
        logger.info(f"URLs to fetch: {len(to_fetch)}")
        logger.info(f"Concurrency: {self.config.concurrency}")
        logger.info(f"Delay: {self.config.delay}s")
        
        async with aiohttp.ClientSession(
            headers={'User-Agent': self.config.user_agent}
        ) as session:
            
            tasks = [self.download_asset(session, url) for url in to_fetch]
            
            # Process with progress tracking
            for i, coro in enumerate(asyncio.as_completed(tasks), 1):
                result = await coro
                self.results.append(result)
                
                if i % 50 == 0:
                    success = sum(1 for r in self.results if r['status'] == 'OK')
                    logger.info(f"Progress: {i}/{len(to_fetch)} ({success} successful)")
                    import sys
                    sys.stdout.flush()
                    # Save intermediate results
                    self.save_results()
            
            # Final save
            self.save_results()
            
            # Statistics
            stats = {
                'total': len(self.results),
                'success': sum(1 for r in self.results if r['status'] == 'OK'),
                'failed': sum(1 for r in self.results if r['status'] == 'FAIL'),
                'skipped': sum(1 for r in self.results if r['status'] == 'SKIP'),
            }
            
            logger.info("Media fetch complete:")
            logger.info(f"  Total: {stats['total']}")
            logger.info(f"  Success: {stats['success']} ({stats['success']/stats['total']*100:.1f}%)")
            logger.info(f"  Failed: {stats['failed']}")
            logger.info(f"  Skipped: {stats['skipped']}")
            
            # Update config
            self.config.media_fetched = True
            config_path = self.config.output_dir / 'config.json'
            self.config.save(config_path)
            
            return stats


async def fetch_media(config: ProjectConfig, pass_number: int = 1) -> Dict[str, int]:
    """
    Fetch media assets from Wayback Machine.
    
    Args:
        config: Project configuration
        pass_number: Pass number for multi-pass fetching
        
    Returns:
        Statistics dict
    """
    fetcher = MediaFetcher(config, pass_number)
    return await fetcher.fetch_all()

