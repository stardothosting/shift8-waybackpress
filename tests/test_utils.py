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


# Tests for get_local_path_for_url (media filename length handling)

def test_get_local_path_normal():
    """Test get_local_path_for_url with normal-length filenames."""
    from pathlib import Path
    from waybackpress.utils import get_local_path_for_url
    
    url = "https://example.com/images/photo.jpg"
    base_dir = Path("/tmp/test")
    
    result = get_local_path_for_url(url, base_dir)
    
    # Should preserve the original filename
    assert result.name == "photo.jpg"
    assert "example.com" in str(result)
    assert "images" in str(result)


def test_get_local_path_long_filename():
    """Test get_local_path_for_url with extremely long filename (like fbcdn error)."""
    from pathlib import Path
    from waybackpress.utils import get_local_path_for_url
    
    # The actual problematic URL from the batman-news.com error
    long_filename = "tcw2GCrONSnJ3tfifSrEDIbhNuGHP_1kVgj08kobLA4ixwHfQDRF3kx7g9G_ymiJ9RTN6vXXzuPqxWTehjwxIwymglkeAxgaJlzGopZf6N0Egb4Xa1SDhjYfR1IjDQuHdPFi4Jr6krxoX4i4j70Rg_chV0SrWv9Sivw9-fAozIMNFBkkw1JtOGoHMq0Lud-_SLey5mDURRE7xhrdu1tkd57K2S-nu_Slhf0i_YyBHl-lElGzTHLytctlDrzau-DNq4XdKsc9Ol6Gkjq0OVeavkZc4HIHnC8wypiAW_bfk0L-xMLewjyxVHsl91YGT8hC1LYw5WWi7I.js"
    url = f"https://static.xx.fbcdn.net/rsrc.php/v4i1mX4/yn/l/fr_FR-j/{long_filename}"
    base_dir = Path("/tmp/test")
    
    result = get_local_path_for_url(url, base_dir)
    filename = result.name
    
    # Filename should be truncated
    assert len(filename) <= 200, f"Filename too long: {len(filename)} chars"
    
    # Should preserve .js extension
    assert filename.endswith(".js"), "Should preserve file extension"
    
    # Should contain hash for uniqueness
    assert "_" in filename, "Should contain hash separator"
    
    # Total path should work on filesystem (under 255 chars for filename)
    assert len(filename) < 250, f"Filename still too long for filesystem: {len(filename)}"


def test_get_local_path_preserves_extension():
    """Test that file extensions are preserved when truncating."""
    from pathlib import Path
    from waybackpress.utils import get_local_path_for_url
    
    extensions = ['.js', '.css', '.jpg', '.png', '.gif', '.svg', '.woff2']
    
    for ext in extensions:
        long_name = "a" * 300 + ext
        url = f"https://example.com/path/{long_name}"
        base_dir = Path("/tmp/test")
        
        result = get_local_path_for_url(url, base_dir)
        
        assert result.name.endswith(ext), f"Should preserve {ext} extension"
        assert len(result.name) <= 200, f"Filename too long even after truncation"


def test_get_local_path_uniqueness():
    """Test that different long filenames produce different paths."""
    from pathlib import Path
    from waybackpress.utils import get_local_path_for_url
    
    # Two different long filenames
    long_name1 = "a" * 300 + ".js"
    long_name2 = "b" * 300 + ".js"
    
    url1 = f"https://example.com/path/{long_name1}"
    url2 = f"https://example.com/path/{long_name2}"
    base_dir = Path("/tmp/test")
    
    result1 = get_local_path_for_url(url1, base_dir)
    result2 = get_local_path_for_url(url2, base_dir)
    
    # Different URLs should produce different filenames
    assert result1.name != result2.name, "Different long filenames should hash differently"
    
    # Both should be under the limit
    assert len(result1.name) <= 200
    assert len(result2.name) <= 200


def test_get_local_path_no_extension():
    """Test handling of long filenames without extensions."""
    from pathlib import Path
    from waybackpress.utils import get_local_path_for_url
    
    # Long filename with no extension
    long_name = "a" * 300
    url = f"https://example.com/path/{long_name}"
    base_dir = Path("/tmp/test")
    
    result = get_local_path_for_url(url, base_dir)
    
    # Should still truncate and hash
    assert len(result.name) <= 200, "Should truncate even without extension"
    assert "_" in result.name, "Should contain hash"


def test_get_local_path_boundary_length():
    """Test filenames at the boundary of 200 characters."""
    from pathlib import Path
    from waybackpress.utils import get_local_path_for_url
    
    base_dir = Path("/tmp/test")
    
    # Just under the limit (should pass through unchanged)
    name_199 = "a" * 195 + ".jpg"  # 199 chars total
    url_199 = f"https://example.com/{name_199}"
    result_199 = get_local_path_for_url(url_199, base_dir)
    assert result_199.name == name_199, "199-char filename should pass through"
    
    # Just over the limit (should be truncated)
    name_201 = "a" * 197 + ".jpg"  # 201 chars total
    url_201 = f"https://example.com/{name_201}"
    result_201 = get_local_path_for_url(url_201, base_dir)
    assert result_201.name != name_201, "201-char filename should be truncated"
    assert len(result_201.name) <= 200, "Truncated filename should be under limit"

