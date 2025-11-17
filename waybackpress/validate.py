"""
Post validation and metadata extraction with multi-strategy content extraction.

Handles sporadic Wayback Machine archives by trying multiple sources:
1. WordPress REST API (/wp-json/wp/v2/posts/ID)
2. RSS feeds (/feed/, /feed/atom)
3. Trafilatura (heuristic content extraction)
4. WordPress body class analysis
5. Fallback to largest text block
"""

import asyncio
import csv
import json
import logging
import re
import warnings
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning
import trafilatura

from .config import ProjectConfig
from .utils import (
    extract_date_from_url,
    extract_slug_from_url,
    parse_flexible_date,
    compute_content_hash,
    get_local_path_for_url,
    construct_wayback_url,
    truncate_string,
)


logger = logging.getLogger('waybackpress.validate')


class ContentExtractor:
    """
    Multi-strategy content extractor for WordPress posts.
    
    Tries multiple methods to extract content, designed to work with
    sporadic Wayback Machine archives where different snapshots may
    have different formats available.
    """
    
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def extract_all(
        self, 
        url: str, 
        html: str,
        soup: BeautifulSoup
    ) -> Dict[str, Any]:
        """
        Extract title, content, metadata using multiple strategies.
        
        Returns dict with: title, content, date, author, categories, tags, 
                          extraction_method, word_count
        """
        result = {
            'title': None,
            'content': None,
            'date': None,
            'author': None,
            'categories': [],
            'tags': [],
            'extraction_method': 'none',
            'word_count': 0,
            'post_type': 'post'
        }
        
        # Detect post type (post or page)
        post_type = self.detect_post_type(soup)
        result['post_type'] = post_type
        
        # Extract post ID from body classes (works for ALL WP themes)
        post_id = self.extract_post_id(soup)
        
        # Strategy 1: Try WordPress REST API (if post ID found)
        if post_id and self.session:
            logger.debug(f"Trying wp-json API for {post_type} ID {post_id}")
            if api_data := await self.try_wp_json(url, post_id, post_type):
                parsed = self.parse_wp_json(api_data)
                parsed['post_type'] = post_type  # Ensure post_type is set
                return parsed
        
        # Strategy 2: Try RSS feed content (check if URL is in a feed)
        # Note: This would require fetching /feed/ separately
        # Skipping for now as it requires additional HTTP requests
        
        # Strategy 3: Trafilatura (heuristic extraction - works on 80%+ of sites)
        logger.debug("Trying trafilatura extraction")
        if content := self.try_trafilatura(html):
            result.update({
                'content': content,
                'extraction_method': 'trafilatura',
                'word_count': len(content.split())
            })
        
        # Strategy 4: WordPress body class metadata extraction
        logger.debug("Extracting metadata from WordPress body classes")
        wp_metadata = self.extract_wordpress_metadata(soup)
        result.update(wp_metadata)
        
        # Strategy 5: Title extraction (multiple methods)
        if not result['title']:
            result['title'] = self.extract_title(soup)
        
        # Strategy 6: Date extraction (URL -> meta tags -> content)
        if not result['date']:
            result['date'] = self.extract_date(url, soup)
        
        # Strategy 7: Author extraction
        if not result['author']:
            result['author'] = self.extract_author(soup)
        
        # Strategy 8: Categories and tags
        if not result['categories']:
            result['categories'] = self.extract_categories(soup)
        if not result['tags']:
            result['tags'] = self.extract_tags(soup)
        
        return result
    
    def extract_post_id(self, soup: BeautifulSoup) -> Optional[int]:
        """
        Extract WordPress post ID from body classes.
        This works across ALL WordPress themes.
        
        Example: <body class="postid-191 single-post">
        """
        body = soup.find('body')
        if not body:
            return None
        
        classes = body.get('class', [])
        if isinstance(classes, str):
            classes = classes.split()
        
        for cls in classes:
            # Look for postid-XXX, post-XXX, or page-id-XXX patterns
            if match := re.match(r'postid-(\d+)', cls):
                return int(match.group(1))
            if match := re.match(r'post-(\d+)', cls):
                return int(match.group(1))
            if match := re.match(r'page-id-(\d+)', cls):
                return int(match.group(1))
        
        return None
    
    def detect_post_type(self, soup: BeautifulSoup) -> str:
        """
        Detect if content is a post or page from body classes.
        
        Returns: 'post' or 'page'
        """
        body = soup.find('body')
        if not body:
            return 'post'
        
        classes = body.get('class', [])
        if isinstance(classes, str):
            classes = classes.split()
        
        # Check for page indicators
        page_indicators = ['page-template', 'page-id-', 'page ', 'single-page']
        for cls in classes:
            for indicator in page_indicators:
                if indicator in cls:
                    return 'page'
        
        return 'post'
    
    async def try_wp_json(self, original_url: str, post_id: int, post_type: str = 'post') -> Optional[Dict]:
        """
        Try to fetch WordPress REST API JSON for this post or page.
        Many Wayback snapshots include wp-json endpoints.
        
        Example: https://example.com/wp-json/wp/v2/posts/191
                 https://example.com/wp-json/wp/v2/pages/123
        """
        if not self.session:
            return None
        
        # Construct wp-json URL
        from urllib.parse import urlparse
        parsed = urlparse(original_url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}"
        
        # Use 'posts' or 'pages' endpoint based on type
        endpoint = 'pages' if post_type == 'page' else 'posts'
        json_url = f"{base_domain}/wp-json/wp/v2/{endpoint}/{post_id}"
        
        # Try to find this in Wayback Machine
        wayback_json = await self.find_snapshot(json_url)
        if not wayback_json:
            return None
        
        try:
            await asyncio.sleep(self.config.delay)
            async with self.session.get(wayback_json, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Successfully extracted from wp-json API")
                    return data
        except Exception as e:
            logger.debug(f"wp-json fetch failed: {e}")
        
        return None
    
    async def find_snapshot(self, url: str) -> Optional[str]:
        """Find a Wayback Machine snapshot for a URL."""
        if not self.session:
            return None
        
        cdx_url = (
            f"https://web.archive.org/cdx/search/cdx"
            f"?url={url}"
            f"&output=json"
            f"&limit=1"
        )
        
        try:
            async with self.session.get(cdx_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if len(data) > 1:  # First row is headers
                        timestamp = data[1][1]
                        return construct_wayback_url(url, timestamp)
        except Exception as e:
            logger.debug(f"CDX query failed for {url}: {e}")
        
        return None
    
    def parse_wp_json(self, data: Dict) -> Dict[str, Any]:
        """
        Parse WordPress REST API JSON response.
        This gives us CLEAN content without theme chrome.
        """
        from html import unescape
        
        # Extract rendered HTML content
        content_html = data.get('content', {}).get('rendered', '')
        
        # Clean HTML to text
        if content_html:
            # Use trafilatura to clean the HTML
            content = trafilatura.extract(content_html, output_format='txt')
        else:
            content = ''
        
        # Parse date
        date_str = data.get('date_gmt') or data.get('date')
        date = parse_flexible_date(date_str) if date_str else None
        
        # Categories and tags are just IDs in the API response
        # We'd need additional API calls to resolve them
        # For now, extract what we can
        
        return {
            'title': unescape(data.get('title', {}).get('rendered', '')),
            'content': content,
            'date': date,
            'author': None,  # Would need /wp/v2/users/{id} call
            'categories': [],  # Would need /wp/v2/categories/{id} calls
            'tags': [],  # Would need /wp/v2/tags/{id} calls
            'extraction_method': 'wp-json',
            'word_count': len(content.split()) if content else 0
        }
    
    def try_trafilatura(self, html: str) -> Optional[str]:
        """
        Use trafilatura to extract main content.
        
        Trafilatura uses heuristics to identify main content:
        - Text density analysis
        - Link density
        - Structural analysis
        
        Works on 80-90% of websites regardless of theme.
        """
        try:
            # Extract with aggressive cleaning
            content = trafilatura.extract(
                html,
                output_format='txt',
                include_comments=False,
                include_tables=False,
                no_fallback=False,  # Use fallback methods if needed
            )
            
            if content and len(content.strip()) > 100:
                return content.strip()
        except Exception as e:
            logger.debug(f"Trafilatura extraction failed: {e}")
        
        return None
    
    def extract_wordpress_metadata(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Extract metadata from WordPress body classes.
        Works across ALL themes.
        
        Example body classes:
        - postid-191 / post-191
        - category-news, category-updates
        - tag-wordpress, tag-php
        - single-post / page
        - author-john-doe
        """
        result = {
            'categories': [],
            'tags': [],
            'author': None
        }
        
        body = soup.find('body')
        if not body:
            return result
        
        classes = body.get('class', [])
        if isinstance(classes, str):
            classes = classes.split()
        
        for cls in classes:
            # Extract categories
            if match := re.match(r'category-(.+)', cls):
                cat = match.group(1).replace('-', ' ').title()
                if cat not in result['categories']:
                    result['categories'].append(cat)
            
            # Extract tags
            if match := re.match(r'tag-(.+)', cls):
                tag = match.group(1).replace('-', ' ').title()
                if tag not in result['tags']:
                    result['tags'].append(tag)
            
            # Extract author
            if match := re.match(r'author-(.+)', cls):
                result['author'] = match.group(1).replace('-', ' ').title()
        
        return result
    
    def extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract post title using multiple strategies."""
        # Strategy 1: <title> tag
        if title_tag := soup.find('title'):
            title = title_tag.get_text(strip=True)
            # Remove site name suffix (common pattern: "Post Title | Site Name")
            if ' | ' in title:
                title = title.split(' | ')[0]
            if ' – ' in title:
                title = title.split(' – ')[0]
            if ' - ' in title:
                title = title.split(' - ')[0]
            if title:
                return title
        
        # Strategy 2: Open Graph
        if og_title := soup.find('meta', property='og:title'):
            if content := og_title.get('content'):
                return content.strip()
        
        # Strategy 3: h1 tag (usually post title)
        if h1 := soup.find('h1'):
            return h1.get_text(strip=True)
        
        # Strategy 4: First h2 in article/main
        for container in soup.select('article, main, .post, .entry'):
            if h2 := container.find('h2'):
                return h2.get_text(strip=True)
        
        return None
    
    def extract_date(self, url: str, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract date using multiple strategies."""
        # Strategy 1: URL structure (most reliable)
        if date := extract_date_from_url(url):
            return date
        
        # Strategy 2: Meta tags
        for meta in soup.find_all('meta'):
            name = meta.get('name', '').lower()
            prop = meta.get('property', '').lower()
            
            if any(x in name or x in prop for x in ['date', 'published', 'pubdate']):
                if content := meta.get('content'):
                    if date := parse_flexible_date(content):
                        return date
        
        # Strategy 3: <time> tags
        for time_tag in soup.find_all('time'):
            if datetime_attr := time_tag.get('datetime'):
                if date := parse_flexible_date(datetime_attr):
                    return date
            # Try text content
            if date := parse_flexible_date(time_tag.get_text(strip=True)):
                return date
        
        return None
    
    def extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract author using multiple strategies."""
        # Strategy 1: Meta tags
        for meta in soup.find_all('meta'):
            name = meta.get('name', '').lower()
            if 'author' in name:
                if content := meta.get('content'):
                    return content.strip()
        
        # Strategy 2: WordPress author links
        for link in soup.select('a[rel="author"], .author a, .by-author a'):
            author = link.get_text(strip=True)
            if author and len(author) < 100:
                return author
        
        # Strategy 3: <span class="author">
        for elem in soup.select('.author, .post-author, .entry-author'):
            author = elem.get_text(strip=True)
            if author and len(author) < 100:
                return author
        
        return None
    
    def extract_categories(self, soup: BeautifulSoup) -> List[str]:
        """Extract categories using multiple strategies."""
        categories = []
        
        # Strategy 1: WordPress category links
        for link in soup.select('a[rel="category"], a[rel="category tag"]'):
            cat = link.get_text(strip=True)
            if cat and cat not in categories:
                categories.append(cat)
        
        # Strategy 2: Common category containers
        for container in soup.select('.categories, .category, .post-categories'):
            for link in container.find_all('a'):
                cat = link.get_text(strip=True)
                if cat and cat not in categories and len(cat) < 50:
                    categories.append(cat)
        
        return categories
    
    def extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """Extract tags using multiple strategies."""
        tags = []
        
        # Strategy 1: WordPress tag links
        for link in soup.select('a[rel="tag"]'):
            tag = link.get_text(strip=True)
            if tag and tag not in tags:
                tags.append(tag)
        
        # Strategy 2: Common tag containers
        for container in soup.select('.tags, .post-tags, .tag-links'):
            for link in container.find_all('a'):
                tag = link.get_text(strip=True)
                if tag and tag not in tags and len(tag) < 50:
                    tags.append(tag)
        
        return tags


class PostValidator:
    """Validates discovered URLs and extracts post metadata."""
    
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.seen_hashes: Set[str] = set()
        self.seen_titles: Set[str] = set()
        self.results: List[Dict[str, Any]] = []
        self.extractor = ContentExtractor(config)
    
    def load_discovered_urls(self) -> List[str]:
        """Load URLs from discovery phase."""
        urls_file = self.config.get_paths()['discovered_urls']
        
        if not urls_file.exists():
            raise FileNotFoundError(
                f"No discovered URLs found. Run 'discover' command first."
            )
        
        with open(urls_file, 'r') as f:
            # Skip header
            next(f)
            return [line.strip() for line in f if line.strip()]
    
    async def find_snapshot(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Find a Wayback Machine snapshot for a URL."""
        cdx_url = (
            f"https://web.archive.org/cdx/search/cdx"
            f"?url={url}"
            f"&output=json"
            f"&limit=1"
        )
        
        try:
            async with session.get(cdx_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if len(data) > 1:  # First row is headers
                        timestamp = data[1][1]
                        return construct_wayback_url(url, timestamp)
        except Exception as e:
            logger.debug(f"CDX query failed for {url}: {e}")
        
        return None
    
    async def download_html(
        self,
        session: aiohttp.ClientSession,
        wayback_url: str,
        local_path: Path
    ) -> bool:
        """Download HTML from Wayback Machine."""
        # Check if already downloaded
        if local_path.exists():
            return True
        
        try:
            # Only delay if we're actually downloading
            await asyncio.sleep(self.config.delay)
            
            async with session.get(wayback_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Save HTML
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(local_path, 'w', encoding='utf-8') as f:
                        f.write(html)
                    
                    return True
                else:
                    logger.debug(f"Download failed with status {response.status}")
        except Exception as e:
            logger.debug(f"Download failed for {wayback_url}: {e}")
        
        return False
    
    def strip_wayback_chrome(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Remove Wayback Machine UI elements."""
        # Collect elements to remove
        to_remove = []
        
        # Wayback toolbar and scripts
        for tag in soup.find_all():
            if not tag.name:
                continue
            
            # Check ID
            tag_id = tag.get('id', '')
            if isinstance(tag_id, list):
                tag_id = ' '.join(tag_id)
            if any(x in tag_id.lower() for x in ['wm-', 'donato', 'wm_', 'wayback']):
                to_remove.append(tag)
                continue
            
            # Check class
            tag_class = tag.get('class', [])
            if isinstance(tag_class, str):
                tag_class = [tag_class]
            if any(any(x in c.lower() for x in ['wm-', 'wayback']) for c in tag_class):
                to_remove.append(tag)
                continue
            
            # Remove Wayback scripts
            if tag.name == 'script':
                src = tag.get('src', '')
                if 'archive.org' in src or 'wombat' in src.lower():
                    to_remove.append(tag)
        
        # Remove collected elements
        for tag in to_remove:
            if tag and tag.parent:
                tag.decompose()
        
        return soup
    
    async def validate_url(
        self,
        session: aiohttp.ClientSession,
        url: str
    ) -> Dict[str, Any]:
        """Validate a single URL and extract metadata."""
        result = {
            'url': url,
            'valid': False,
            'reason': '',
            'title': None,
            'date': None,
            'author': None,
            'categories': [],
            'tags': [],
            'word_count': 0,
            'local_path': '',
            'extraction_method': 'none',
            'post_type': 'post'
        }
        
        # Check if HTML already exists
        slug = extract_slug_from_url(url) or 'unknown'
        local_path = self.config.get_paths()['html'] / f"{slug}.html"
        
        if not local_path.exists():
            # Find snapshot only if we need to download
            wayback_url = await self.find_snapshot(session, url)
            if not wayback_url:
                result['reason'] = 'no_snapshot'
                return result
            
            # Download HTML
            downloaded = await self.download_html(session, wayback_url, local_path)
        else:
            # File already exists, skip download
            downloaded = True
        
        if not downloaded:
            result['reason'] = 'download_failed'
            return result
        
        # Read and parse HTML
        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                html = f.read()
        except Exception as e:
            logger.debug(f"Failed to read {local_path}: {e}")
            result['reason'] = 'read_failed'
            return result
        
        # Parse HTML
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, 'lxml')
        
        # Strip Wayback chrome
        soup = self.strip_wayback_chrome(soup)
        
        # Extract content and metadata using multi-strategy approach
        self.extractor.session = session
        extracted = await self.extractor.extract_all(url, html, soup)
        
        # Update result with extracted data
        result.update(extracted)
        result['local_path'] = str(local_path)
        
        # Apply heuristics
        return self.apply_heuristics(result)
    
    def apply_heuristics(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply minimal heuristics to filter out non-posts.
        
        Philosophy: Extract everything. Let the user decide what's valid.
        Only reject obvious non-posts (archives, duplicates, completely empty).
        """
        # Check for archive-looking URLs (these are category/tag pages, not posts)
        url = result['url']
        if re.search(r'/(category|tag|author|archive|page)/|/\d{4}/?$|/\d{4}/\d{2}/?$', url):
            result['reason'] = 'archive_page'
            return result
        
        # Check for completely empty content (nothing extractable at all)
        if not result.get('content') or not result['content'].strip():
            result['reason'] = 'no_content'
            return result
        
        # Check for duplicates by content hash (technical deduplication)
        content = result['content']
        content_hash = compute_content_hash(content)
        if content_hash in self.seen_hashes:
            result['reason'] = 'duplicate_content'
            return result
        
        # Valid post! Extract everything, even if:
        # - No title (some posts are titleless)
        # - Short content (could be image post, quote, announcement)
        # - Minimal text (not our job to judge content quality)
        result['valid'] = True
        result['reason'] = 'ok'
        self.seen_hashes.add(content_hash)
        
        return result
    
    def save_results(self) -> int:
        """Save validation results to CSV and TSV files."""
        paths = self.config.get_paths()
        
        # Save validation report (CSV with all fields except content)
        report_path = paths['validation_report']
        
        fieldnames = [
            'url', 'valid', 'reason', 'title', 'date', 'author',
            'categories', 'tags', 'word_count', 'extraction_method', 'local_path'
        ]
        
        with open(report_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in self.results:
                row = {k: result.get(k, '') for k in fieldnames}
                # Convert lists to strings
                row['categories'] = ','.join(row['categories']) if row['categories'] else ''
                row['tags'] = ','.join(row['tags']) if row['tags'] else ''
                writer.writerow(row)
        
        logger.info(f"Saved validation report to {report_path}")
        
        # Save valid posts (TSV)
        valid_posts = [r for r in self.results if r['valid']]
        valid_posts_path = paths['valid_posts']
        
        with open(valid_posts_path, 'w') as f:
            f.write("url\tlocal_path\n")
            for result in valid_posts:
                f.write(f"{result['url']}\t{result['local_path']}\n")
        
        logger.info(f"Saved {len(valid_posts)} valid posts to {valid_posts_path}")
        
        return len(valid_posts)
    
    async def validate_all(self) -> int:
        """Main validation process."""
        urls = self.load_discovered_urls()
        
        logger.info(f"Starting validation of {len(urls)} URLs")
        logger.info(f"Using delay of {self.config.delay}s between requests")
        
        async with aiohttp.ClientSession(
            headers={'User-Agent': self.config.user_agent}
        ) as session:
            # Process URLs (currently sequential, TODO: make concurrent)
            for i, url in enumerate(urls, 1):
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{len(urls)} ({i/len(urls)*100:.1f}%)")
                    import sys
                    sys.stdout.flush()
                
                logger.debug(f"Validating: {url}")
                result = await self.validate_url(session, url)
                self.results.append(result)
                
                # Save intermediate results every 50 URLs
                if i % 50 == 0:
                    self.save_results()
        
        # Final save
        valid_count = self.save_results()
        
        # Update config
        self.config.validated = True
        config_path = self.config.output_dir / 'config.json'
        self.config.save(config_path)
        
        # Print summary
        logger.info("Validation complete:")
        logger.info(f"  Total URLs: {len(urls)}")
        logger.info(f"  Valid posts: {valid_count} ({valid_count/len(urls)*100:.1f}%)")
        logger.info(f"  Invalid: {len(urls) - valid_count}")
        
        # Show extraction method breakdown
        methods = {}
        for r in self.results:
            method = r.get('extraction_method', 'none')
            methods[method] = methods.get(method, 0) + 1
        
        logger.info("Extraction methods used:")
        for method, count in sorted(methods.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {method}: {count}")
        
        return valid_count


async def validate_posts(config: ProjectConfig) -> int:
    """Run post validation."""
    validator = PostValidator(config)
    return await validator.validate_all()
