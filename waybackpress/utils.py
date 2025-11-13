"""
Shared utility functions for WaybackPress.
"""

import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote
from dateutil import parser as dateparser


def normalize_url(url: str) -> str:
    """
    Normalize a URL by removing common variations.
    
    Args:
        url: The URL to normalize
        
    Returns:
        Normalized URL string
    """
    # Remove protocol
    url = re.sub(r'^https?://', '', url)
    
    # Remove www.
    url = re.sub(r'^www\.', '', url)
    
    # Remove trailing slash
    url = url.rstrip('/')
    
    # Remove query strings and fragments
    url = re.sub(r'[?#].*$', '', url)
    
    return url


def extract_slug_from_url(url: str) -> Optional[str]:
    """
    Extract the post slug from a WordPress URL.
    
    Args:
        url: WordPress post URL
        
    Returns:
        Post slug or None if not found
    """
    # Match WordPress permalink pattern: /YYYY/MM/DD/slug/
    match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/([^/]+)/?$', url)
    if match:
        return match.group(4)
    
    # Try simpler pattern: /slug/
    match = re.search(r'/([^/]+)/?$', url)
    if match:
        return match.group(1)
    
    return None


def extract_date_from_url(url: str) -> Optional[datetime]:
    """
    Extract the date from a WordPress URL pattern.
    
    Args:
        url: WordPress post URL
        
    Returns:
        datetime object or None if not found
    """
    match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
    if match:
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3))
            )
        except ValueError:
            return None
    return None


def parse_flexible_date(date_str: str) -> Optional[datetime]:
    """
    Parse a date string using flexible parsing.
    
    Args:
        date_str: Date string in various formats
        
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None
    
    try:
        dt = dateparser.parse(date_str, fuzzy=True)
        # Strip timezone for consistency
        if dt and dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def compute_content_hash(content: str) -> str:
    """
    Compute SHA1 hash of content for deduplication.
    
    Args:
        content: Content string to hash
        
    Returns:
        SHA1 hex digest
    """
    return hashlib.sha1(content.encode('utf-8')).hexdigest()


def strip_wayback_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract original URL and timestamp from Wayback Machine URL.
    
    Args:
        url: Wayback Machine URL
        
    Returns:
        Tuple of (original_url, timestamp) or (None, None)
    """
    # Match: https://web.archive.org/web/TIMESTAMP/ORIGINAL_URL
    match = re.match(
        r'https?://web\.archive\.org/web/(\d+)(?:[a-z_]*)/(.+)',
        url,
        re.IGNORECASE
    )
    if match:
        return match.group(2), match.group(1)
    
    return None, None


def construct_wayback_url(original_url: str, timestamp: str, modifier: str = '') -> str:
    """
    Construct a Wayback Machine URL.
    
    Args:
        original_url: Original URL to fetch
        timestamp: Wayback timestamp (YYYYMMDDhhmmss)
        modifier: Wayback modifier (e.g., 'id_', 'im_')
        
    Returns:
        Full Wayback URL
    """
    return f"https://web.archive.org/web/{timestamp}{modifier}/{original_url}"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove/replace invalid characters
    filename = re.sub(r'[<>:"|?*]', '', filename)
    filename = re.sub(r'[\s]+', '_', filename)
    return filename


def get_local_path_for_url(url: str, base_dir: Path) -> Path:
    """
    Generate a local file path for a given URL.
    
    Args:
        url: URL to generate path for
        base_dir: Base directory for storing files
        
    Returns:
        Path object for local storage
    """
    parsed = urlparse(url)
    
    # Remove leading slash
    path = parsed.path.lstrip('/')
    
    # Decode URL encoding
    path = unquote(path)
    
    # Construct full path
    full_path = base_dir / parsed.netloc / path
    
    # Ensure parent directory
    full_path.parent.mkdir(parents=True, exist_ok=True)
    
    return full_path


def is_post_url(url: str, domain: str) -> bool:
    """
    Check if URL matches WordPress post pattern.
    
    Args:
        url: URL to check
        domain: Site domain
        
    Returns:
        True if URL appears to be a post
    """
    # Normalize for comparison
    normalized = normalize_url(url)
    
    # Must be from correct domain
    if not normalized.startswith(domain.replace('www.', '')):
        return False
    
    # Exclude common non-post patterns
    exclude_patterns = [
        r'/feed/?$',
        r'/amp/?$',
        r'/page/\d+/?$',
        r'/category/',
        r'/tag/',
        r'/author/',
        r'/search/',
        r'/\d{4}/?$',  # Year only
        r'/\d{4}/\d{2}/?$',  # Year/month only
        r'/\d{4}/\d{2}/\d{2}/?$',  # Date only, no slug
        r'\.(jpg|jpeg|png|gif|css|js|xml|json)$',  # Media files
    ]
    
    for pattern in exclude_patterns:
        if re.search(pattern, normalized):
            return False
    
    # Must have post pattern: /YYYY/MM/DD/slug/ or /slug/
    post_patterns = [
        r'/\d{4}/\d{2}/\d{2}/[^/]+/?$',  # Date-based permalink
        r'/[^/]+/?$',  # Simple slug
    ]
    
    for pattern in post_patterns:
        if re.search(pattern, normalized):
            return True
    
    return False


def format_bytes(size: int) -> str:
    """
    Format byte size as human-readable string.
    
    Args:
        size: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def truncate_string(s: str, length: int = 60) -> str:
    """
    Truncate string to specified length with ellipsis.
    
    Args:
        s: String to truncate
        length: Maximum length
        
    Returns:
        Truncated string
    """
    if len(s) <= length:
        return s
    return s[:length-3] + '...'

