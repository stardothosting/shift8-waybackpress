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


def test_extract_slug_long_filename():
    """Test that extremely long slugs are handled correctly."""
    # Create a URL with a very long path segment (simulating the batman-news.com error)
    long_segment = "a" * 400  # 400 character slug
    url = f"https://example.com/{long_segment}/"
    
    slug = extract_slug_from_url(url)
    
    # Should not be None
    assert slug is not None
    
    # Should be truncated with hash appended
    assert len(slug) <= 200, f"Slug too long: {len(slug)} chars"
    
    # Should end with underscore + hash
    assert "_" in slug, "Long slug should contain hash separator"
    
    # Filename with .html extension should be under filesystem limit
    filename = f"{slug}.html"
    assert len(filename) < 250, f"Filename too long: {len(filename)} chars"


def test_extract_slug_boundary_cases():
    """Test slug extraction at various length boundaries."""
    # Just under the limit (should pass through unchanged)
    slug_199 = "a" * 199
    url_199 = f"https://example.com/{slug_199}/"
    result_199 = extract_slug_from_url(url_199)
    assert result_199 == slug_199, "199-char slug should pass through unchanged"
    
    # Exactly at the limit (should pass through unchanged)
    slug_200 = "a" * 200
    url_200 = f"https://example.com/{slug_200}/"
    result_200 = extract_slug_from_url(url_200)
    assert result_200 == slug_200, "200-char slug should pass through unchanged"
    
    # Just over the limit (should be truncated and hashed)
    slug_201 = "a" * 201
    url_201 = f"https://example.com/{slug_201}/"
    result_201 = extract_slug_from_url(url_201)
    assert result_201 != slug_201, "201-char slug should be modified"
    assert len(result_201) < 200, "Truncated slug should be under 200 chars"


def test_extract_slug_url_encoded():
    """Test slug extraction with URL-encoded characters."""
    # URL with encoded characters (like the batman-news.com error)
    encoded_slug = "%20the%20comic%20features%20" + ("encoded" * 50)
    url = f"https://example.com/{encoded_slug}/"
    
    slug = extract_slug_from_url(url)
    
    # Should handle encoded URLs
    assert slug is not None
    assert len(slug) <= 200, "Even encoded slugs should respect length limits"


def test_extract_slug_uniqueness():
    """Test that different long slugs produce different results."""
    # Two different long slugs should produce different hashed results
    slug1 = "a" * 250
    slug2 = "b" * 250
    
    url1 = f"https://example.com/{slug1}/"
    url2 = f"https://example.com/{slug2}/"
    
    result1 = extract_slug_from_url(url1)
    result2 = extract_slug_from_url(url2)
    
    assert result1 != result2, "Different long slugs should produce different results"


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

