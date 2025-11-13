"""
Unit tests for utility functions.
"""

import pytest
from waybackpress.utils import (
    normalize_url,
    is_post_url,
    extract_slug_from_url,
    extract_date_from_url,
)


def test_normalize_url():
    """Test URL normalization."""
    assert normalize_url("https://example.com/path/") == "example.com/path"
    assert normalize_url("http://www.example.com/path") == "example.com/path"
    assert normalize_url("example.com/path?query=1") == "example.com/path"


def test_is_post_url():
    """Test post URL detection."""
    domain = "example.com"
    
    # Valid post URLs
    assert is_post_url("https://example.com/2020/01/15/my-post/", domain)
    assert is_post_url("https://example.com/my-post/", domain)
    
    # Invalid URLs
    assert not is_post_url("https://example.com/category/news/", domain)
    assert not is_post_url("https://example.com/2020/01/15/", domain)
    assert not is_post_url("https://example.com/feed/", domain)


def test_extract_slug_from_url():
    """Test slug extraction from URLs."""
    assert extract_slug_from_url("https://example.com/2020/01/15/my-post/") == "my-post"
    assert extract_slug_from_url("https://example.com/my-post/") == "my-post"
    assert extract_slug_from_url("https://example.com/") is None


def test_extract_date_from_url():
    """Test date extraction from URLs."""
    from datetime import datetime
    
    date = extract_date_from_url("https://example.com/2020/01/15/my-post/")
    assert date is not None
    assert date.year == 2020
    assert date.month == 1
    assert date.day == 15
    
    assert extract_date_from_url("https://example.com/my-post/") is None


# Add more tests as needed

