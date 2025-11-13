"""
WordPress WXR 1.2 export generation.
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from xml.dom import minidom

from bs4 import BeautifulSoup

from .config import ProjectConfig
from .utils import parse_flexible_date, extract_date_from_url, extract_slug_from_url


logger = logging.getLogger('waybackpress.export')


class WXRExporter:
    """Generates WordPress WXR 1.2 import file."""
    
    def __init__(
        self,
        config: ProjectConfig,
        site_title: str = "Imported Site",
        site_url: str = "http://localhost",
        author_name: str = "admin",
        author_email: str = "admin@example.com",
    ):
        self.config = config
        self.site_title = site_title
        self.site_url = site_url
        self.author_name = author_name
        self.author_email = author_email
        
        self.categories: Dict[str, int] = {}
        self.tags: Dict[str, int] = {}
        self.next_term_id = 1
        self.next_post_id = 1
        
        self.stats = {
            'posts': 0,
            'categories': 0,
            'tags': 0,
        }
    
    def load_valid_posts(self) -> List[Dict[str, str]]:
        """Load validated posts."""
        posts_file = self.config.get_paths()['valid_posts']
        
        if not posts_file.exists():
            raise FileNotFoundError(
                "No valid posts found. Run 'validate' command first."
            )
        
        posts = []
        with open(posts_file, 'r') as f:
            next(f)  # Skip header
            for line in f:
                if line.strip():
                    url, local_path = line.strip().split('\t')
                    posts.append({'url': url, 'local_path': local_path})
        
        logger.info(f"Loaded {len(posts)} posts to export")
        return posts
    
    def strip_wayback_chrome(self, soup: BeautifulSoup) -> None:
        """Remove Wayback Machine UI elements."""
        to_remove = []
        
        for tag in soup.find_all():
            if tag is None:
                continue
            
            tag_id = str(tag.get('id', '')).lower()
            if any(x in tag_id for x in ['wombat', 'wayback', 'iconochive', 'replay', 'donato']):
                to_remove.append(tag)
                continue
            
            tag_class = ' '.join(tag.get('class', [])).lower()
            if any(x in tag_class for x in ['wombat', 'wayback', 'iconochive', 'replay']):
                to_remove.append(tag)
        
        for tag in to_remove:
            if tag and tag.parent:
                tag.decompose()
    
    def dewrap_wayback_urls(self, soup: BeautifulSoup) -> None:
        """Rewrite Wayback URLs to original URLs."""
        pattern = re.compile(r'https?://web\.archive\.org/web/\d+[a-z_]*/(https?://[^"\s]+)')
        
        for attr in ['href', 'src', 'srcset']:
            for tag in soup.find_all(**{attr: True}):
                value = tag[attr]
                tag[attr] = pattern.sub(r'\1', value)
    
    def extract_title(self, soup: BeautifulSoup) -> str:
        """Extract post title."""
        # Try common selectors
        selectors = [
            'h1.entry-title',
            'h1.post-title',
            '.entry-title',
            '.post-title',
            'h1',
        ]
        
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                title = elem.get_text(strip=True)
                # Remove site name
                title = re.sub(r'\s*[|\-–]\s*.*$', '', title)
                if title and len(title) > 3:
                    return title
        
        # Fallback to <title>
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            title = re.sub(r'\s*[|\-–]\s*.*$', '', title)
            if title:
                return title
        
        return "Untitled Post"
    
    def extract_date(self, soup: BeautifulSoup, url: str) -> datetime:
        """Extract post date."""
        # Try URL first
        url_date = extract_date_from_url(url)
        
        # Try DOM selectors
        date_selectors = [
            'time[datetime]',
            '.entry-date',
            '.post-date',
            '.published',
        ]
        
        for selector in date_selectors:
            elem = soup.select_one(selector)
            if elem:
                date_str = elem.get('datetime') or elem.get_text(strip=True)
                dom_date = parse_flexible_date(date_str)
                if dom_date:
                    return dom_date
        
        return url_date or datetime.now()
    
    def extract_content(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        """Extract main content and clean WordPress chrome."""
        content = None
        
        # Try to find content area
        selectors = [
            '.entry-content',
            '.post-content',
            'article .content',
            '.single-content',
            'article',
        ]
        
        for selector in selectors:
            content = soup.select_one(selector)
            if content:
                break
        
        if not content:
            return None
        
        # Make a copy to work with
        content = BeautifulSoup(str(content), 'lxml')
        
        # Remove unwanted elements
        remove_selectors = [
            'script', 'style', 'noscript',
            '.post-title', '.entry-title',
            '.entry-meta', '.post-meta', '.date',
            '#comments', '.comments',
            '.sharedaddy', '.sd-sharing',
            '.post-navigation',
            'nav', 'aside', 'header', 'footer',
        ]
        
        for selector in remove_selectors:
            for elem in content.select(selector):
                elem.decompose()
        
        # Remove empty paragraphs
        for p in content.find_all(['p', 'div']):
            if not p.get_text(strip=True) and not p.find('img'):
                p.decompose()
        
        return content
    
    def extract_categories(self, soup: BeautifulSoup) -> List[str]:
        """Extract post categories using rel attribute."""
        categories = []
        seen = set()
        
        # Find categories using rel="category tag" or rel="category"
        for link in soup.find_all('a', href=True, rel=True):
            rel = ' '.join(link.get('rel', []))
            href = link['href']
            text = link.get_text(strip=True)
            
            # Look for rel="category tag" or rel="category" with /category/ in URL
            if 'category' in rel and '/category/' in href and text:
                if text not in seen:
                    categories.append(text)
                    seen.add(text)
        
        return categories
    
    def extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """Extract post tags using rel attribute."""
        tags = []
        seen = set()
        
        # Find tags using rel="tag" (not "category tag")
        for link in soup.find_all('a', href=True, rel=True):
            rel = ' '.join(link.get('rel', []))
            href = link['href']
            text = link.get_text(strip=True)
            
            # Look for rel="tag" (not "category tag") with /tag/ in URL
            if rel == 'tag' and '/tag/' in href and text:
                if text not in seen:
                    tags.append(text)
                    seen.add(text)
        
        return tags
    
    def get_or_create_category(self, name: str) -> int:
        """Get or create category term ID."""
        if name in self.categories:
            return self.categories[name]
        
        term_id = self.next_term_id
        self.next_term_id += 1
        self.categories[name] = term_id
        self.stats['categories'] += 1
        
        return term_id
    
    def get_or_create_tag(self, name: str) -> int:
        """Get or create tag term ID."""
        if name in self.tags:
            return self.tags[name]
        
        term_id = self.next_term_id
        self.next_term_id += 1
        self.tags[name] = term_id
        self.stats['tags'] += 1
        
        return term_id
    
    def build_channel_element(self, root: ET.Element) -> ET.Element:
        """Build RSS channel element with site info."""
        channel = ET.SubElement(root, 'channel')
        
        ET.SubElement(channel, 'title').text = self.site_title
        ET.SubElement(channel, 'link').text = self.site_url
        ET.SubElement(channel, 'description').text = f"Import from {self.config.domain}"
        ET.SubElement(channel, 'pubDate').text = format_datetime(datetime.now())
        ET.SubElement(channel, 'language').text = "en"
        ET.SubElement(channel, 'wp:wxr_version').text = "1.2"
        ET.SubElement(channel, 'wp:base_site_url').text = self.site_url
        ET.SubElement(channel, 'wp:base_blog_url').text = self.site_url
        
        # Author
        author = ET.SubElement(channel, 'wp:author')
        ET.SubElement(author, 'wp:author_login').text = self.author_name
        ET.SubElement(author, 'wp:author_email').text = self.author_email
        ET.SubElement(author, 'wp:author_display_name').text = self.author_name
        ET.SubElement(author, 'wp:author_first_name').text = self.author_name
        
        return channel
    
    def add_taxonomies(self, channel: ET.Element) -> None:
        """Add category and tag terms to channel."""
        # Categories
        for name, term_id in self.categories.items():
            term = ET.SubElement(channel, 'wp:category')
            ET.SubElement(term, 'wp:term_id').text = str(term_id)
            ET.SubElement(term, 'wp:category_nicename').text = re.sub(r'\s+', '-', name.lower())
            ET.SubElement(term, 'wp:category_parent').text = ""
            ET.SubElement(term, 'wp:cat_name').text = f"<![CDATA[{name}]]>"
        
        # Tags
        for name, term_id in self.tags.items():
            term = ET.SubElement(channel, 'wp:tag')
            ET.SubElement(term, 'wp:term_id').text = str(term_id)
            ET.SubElement(term, 'wp:tag_slug').text = re.sub(r'\s+', '-', name.lower())
            ET.SubElement(term, 'wp:tag_name').text = f"<![CDATA[{name}]]>"
    
    def add_post_item(self, channel: ET.Element, post_data: Dict) -> None:
        """Add a post item to the channel."""
        item = ET.SubElement(channel, 'item')
        
        ET.SubElement(item, 'title').text = post_data['title']
        ET.SubElement(item, 'link').text = post_data['url']
        ET.SubElement(item, 'pubDate').text = format_datetime(post_data['date'])
        ET.SubElement(item, 'dc:creator').text = f"<![CDATA[{self.author_name}]]>"
        ET.SubElement(item, 'guid', isPermaLink="false").text = post_data['url']
        ET.SubElement(item, 'description')
        ET.SubElement(item, 'content:encoded').text = f"<![CDATA[{post_data['content']}]]>"
        ET.SubElement(item, 'excerpt:encoded').text = "<![CDATA[]]>"
        ET.SubElement(item, 'wp:post_id').text = str(post_data['post_id'])
        ET.SubElement(item, 'wp:post_date').text = post_data['date'].strftime('%Y-%m-%d %H:%M:%S')
        ET.SubElement(item, 'wp:post_date_gmt').text = post_data['date'].strftime('%Y-%m-%d %H:%M:%S')
        ET.SubElement(item, 'wp:comment_status').text = "open"
        ET.SubElement(item, 'wp:ping_status').text = "open"
        ET.SubElement(item, 'wp:post_name').text = post_data['slug']
        ET.SubElement(item, 'wp:status').text = "publish"
        ET.SubElement(item, 'wp:post_parent').text = "0"
        ET.SubElement(item, 'wp:menu_order').text = "0"
        ET.SubElement(item, 'wp:post_type').text = "post"
        ET.SubElement(item, 'wp:post_password').text = ""
        ET.SubElement(item, 'wp:is_sticky').text = "0"
        
        # Categories
        for cat_name in post_data.get('categories', []):
            cat = ET.SubElement(item, 'category', domain="category", nicename=re.sub(r'\s+', '-', cat_name.lower()))
            cat.text = f"<![CDATA[{cat_name}]]>"
        
        # Tags
        for tag_name in post_data.get('tags', []):
            tag = ET.SubElement(item, 'category', domain="post_tag", nicename=re.sub(r'\s+', '-', tag_name.lower()))
            tag.text = f"<![CDATA[{tag_name}]]>"
    
    def process_post(self, post: Dict[str, str]) -> Optional[Dict]:
        """Process a single post and extract all data."""
        try:
            html_path = Path(post['local_path'])
            if not html_path.exists():
                logger.warning(f"HTML file not found: {html_path}")
                return None
            
            with open(html_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'lxml')
            
            # Clean Wayback elements - IMPORTANT: dewrap URLs FIRST
            # Otherwise, content links with web.archive.org URLs get incorrectly removed
            self.dewrap_wayback_urls(soup)
            self.strip_wayback_chrome(soup)
            
            # Extract metadata
            title = self.extract_title(soup)
            date = self.extract_date(soup, post['url'])
            slug = extract_slug_from_url(post['url']) or f"post-{self.next_post_id}"
            content_elem = self.extract_content(soup)
            
            if not content_elem:
                logger.warning(f"No content found for {post['url']}")
                return None
            
            content = str(content_elem)
            
            # Extract taxonomies
            categories = self.extract_categories(soup)
            tags = self.extract_tags(soup)
            
            # Register taxonomies
            for cat in categories:
                self.get_or_create_category(cat)
            for tag in tags:
                self.get_or_create_tag(tag)
            
            post_data = {
                'post_id': self.next_post_id,
                'url': post['url'],
                'title': title,
                'date': date,
                'slug': slug,
                'content': content,
                'categories': categories,
                'tags': tags,
            }
            
            self.next_post_id += 1
            return post_data
        
        except Exception as e:
            logger.error(f"Failed to process {post['url']}: {e}")
            return None
    
    def export(self) -> Path:
        """
        Main export process.
        
        Returns:
            Path to generated WXR file
        """
        posts = self.load_valid_posts()
        
        logger.info(f"Starting WXR export for {len(posts)} posts")
        
        # Register namespaces
        ET.register_namespace('', 'http://purl.org/rss/1.0/modules/content/')
        ET.register_namespace('wp', 'http://wordpress.org/export/1.2/')
        ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
        ET.register_namespace('excerpt', 'http://wordpress.org/export/1.2/excerpt/')
        
        # Build XML structure
        root = ET.Element('rss', version="2.0")
        root.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')
        root.set('xmlns:wp', 'http://wordpress.org/export/1.2/')
        root.set('xmlns:dc', 'http://purl.org/dc/elements/1.1/')
        root.set('xmlns:excerpt', 'http://wordpress.org/export/1.2/excerpt/')
        
        channel = self.build_channel_element(root)
        
        # Process posts
        post_data_list = []
        for i, post in enumerate(posts, 1):
            if i % 50 == 0:
                logger.info(f"Processing: {i}/{len(posts)}")
                import sys
                sys.stdout.flush()
            
            post_data = self.process_post(post)
            if post_data:
                post_data_list.append(post_data)
                self.stats['posts'] += 1
        
        # Add taxonomies
        self.add_taxonomies(channel)
        
        # Add posts
        for post_data in post_data_list:
            self.add_post_item(channel, post_data)
        
        # Generate XML
        xml_str = minidom.parseString(ET.tostring(root, encoding='unicode')).toprettyxml(indent="  ")
        
        # Save to file
        output_path = self.config.get_paths()['wxr_export']
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_str)
        
        logger.info(f"Export complete:")
        logger.info(f"  Posts: {self.stats['posts']}")
        logger.info(f"  Categories: {self.stats['categories']}")
        logger.info(f"  Tags: {self.stats['tags']}")
        logger.info(f"  File: {output_path}")
        
        # Update config
        self.config.exported = True
        config_path = self.config.output_dir / 'config.json'
        self.config.save(config_path)
        
        return output_path


def export_wxr(
    config: ProjectConfig,
    site_title: Optional[str] = None,
    site_url: Optional[str] = None,
    author_name: str = "admin",
    author_email: str = "admin@example.com",
) -> Path:
    """
    Export posts to WordPress WXR format.
    
    Args:
        config: Project configuration
        site_title: Site title for WXR
        site_url: Site URL for WXR
        author_name: Post author name
        author_email: Post author email
        
    Returns:
        Path to generated WXR file
    """
    if site_title is None:
        site_title = config.domain
    if site_url is None:
        site_url = f"http://{config.domain}"
    
    exporter = WXRExporter(config, site_title, site_url, author_name, author_email)
    return exporter.export()

