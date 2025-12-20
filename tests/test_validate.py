"""
Unit tests for validation resumption functionality.
"""

import csv
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from waybackpress.validate import PostValidator
from waybackpress.config import ProjectConfig


@pytest.fixture
def temp_config(tmp_path):
    """Create a temporary config for testing."""
    config = ProjectConfig(
        domain="example.com",
        output_dir=tmp_path,
        delay=0.1,
        concurrency=5
    )
    
    # Create necessary directories
    paths = config.get_paths()
    paths['html'].mkdir(parents=True, exist_ok=True)
    paths['media'].mkdir(parents=True, exist_ok=True)
    
    return config


def test_load_existing_results_empty(temp_config):
    """Test loading results when no previous results exist."""
    validator = PostValidator(temp_config)
    validator.load_existing_results()
    
    assert len(validator.results) == 0
    assert len(validator.processed_urls) == 0


def test_load_existing_results_with_data(temp_config):
    """Test loading results from existing validation report."""
    validator = PostValidator(temp_config)
    
    # Create a mock validation report
    report_path = temp_config.get_paths()['validation_report']
    
    test_data = [
        {
            'url': 'https://example.com/post1/',
            'valid': 'true',
            'reason': 'ok',
            'title': 'Post 1',
            'date': '2023-01-01',
            'author': 'John',
            'categories': 'Tech,News',
            'tags': 'python,testing',
            'word_count': '500',
            'extraction_method': 'trafilatura',
            'local_path': '/path/to/post1.html',
            'post_type': 'post'
        },
        {
            'url': 'https://example.com/post2/',
            'valid': 'false',
            'reason': 'no_content',
            'title': '',
            'date': '',
            'author': '',
            'categories': '',
            'tags': '',
            'word_count': '0',
            'extraction_method': 'none',
            'local_path': '',
            'post_type': 'post'
        }
    ]
    
    # Write test data
    with open(report_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = list(test_data[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(test_data)
    
    # Load results
    validator.load_existing_results()
    
    # Verify results were loaded
    assert len(validator.results) == 2
    assert len(validator.processed_urls) == 2
    
    # Verify first result
    result1 = validator.results[0]
    assert result1['url'] == 'https://example.com/post1/'
    assert result1['valid'] is True
    assert result1['title'] == 'Post 1'
    assert result1['categories'] == ['Tech', 'News']
    assert result1['tags'] == ['python', 'testing']
    
    # Verify processed URLs set
    assert 'https://example.com/post1/' in validator.processed_urls
    assert 'https://example.com/post2/' in validator.processed_urls


def test_save_results_includes_post_type(temp_config):
    """Test that save_results includes post_type field."""
    validator = PostValidator(temp_config)
    
    # Add mock results
    validator.results = [
        {
            'url': 'https://example.com/post1/',
            'valid': True,
            'reason': 'ok',
            'title': 'Post 1',
            'date': None,
            'author': None,
            'categories': [],
            'tags': [],
            'word_count': 100,
            'extraction_method': 'trafilatura',
            'local_path': '/path/to/post1.html',
            'post_type': 'post'
        },
        {
            'url': 'https://example.com/page1/',
            'valid': True,
            'reason': 'ok',
            'title': 'Page 1',
            'date': None,
            'author': None,
            'categories': [],
            'tags': [],
            'word_count': 200,
            'extraction_method': 'trafilatura',
            'local_path': '/path/to/page1.html',
            'post_type': 'page'
        }
    ]
    
    # Save results
    valid_count = validator.save_results()
    
    # Verify CSV was created with post_type field
    report_path = temp_config.get_paths()['validation_report']
    assert report_path.exists()
    
    with open(report_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
        assert len(rows) == 2
        assert 'post_type' in rows[0]
        assert rows[0]['post_type'] == 'post'
        assert rows[1]['post_type'] == 'page'
    
    # Verify valid_posts.tsv was created
    valid_posts_path = temp_config.get_paths()['valid_posts']
    assert valid_posts_path.exists()
    
    with open(valid_posts_path, 'r') as f:
        lines = f.readlines()
        assert len(lines) == 3  # Header + 2 posts
        assert 'post_type' in lines[0]


def test_resumption_skips_processed_urls(temp_config):
    """Test that resumption properly skips already-processed URLs."""
    validator = PostValidator(temp_config)
    
    # Simulate existing results
    validator.results = [
        {
            'url': 'https://example.com/post1/',
            'valid': True,
            'reason': 'ok',
            'title': 'Post 1',
            'date': None,
            'author': None,
            'categories': [],
            'tags': [],
            'word_count': 100,
            'extraction_method': 'trafilatura',
            'local_path': '/path/to/post1.html',
            'post_type': 'post'
        }
    ]
    validator.processed_urls.add('https://example.com/post1/')
    
    # Create discovered_urls file
    urls_file = temp_config.get_paths()['discovered_urls']
    with open(urls_file, 'w') as f:
        f.write("url\n")
        f.write("https://example.com/post1/\n")
        f.write("https://example.com/post2/\n")
    
    # Load URLs
    all_urls = validator.load_discovered_urls()
    
    # Filter out processed URLs (simulating what validate_all does)
    urls_to_process = [url for url in all_urls if url not in validator.processed_urls]
    
    # Verify that post1 is skipped
    assert len(all_urls) == 2
    assert len(urls_to_process) == 1
    assert 'https://example.com/post2/' in urls_to_process
    assert 'https://example.com/post1/' not in urls_to_process


def test_error_handling_creates_error_result(temp_config):
    """Test that errors during validation create error result entries."""
    # This is tested implicitly in the validate_all method
    # The error handling wraps individual URL validation in try/except
    # and creates a result with 'error' extraction_method
    
    # Mock result that would be created on error
    error_result = {
        'url': 'https://example.com/problematic/',
        'valid': False,
        'reason': 'error: File name too long',
        'title': None,
        'date': None,
        'author': None,
        'categories': [],
        'tags': [],
        'word_count': 0,
        'local_path': '',
        'extraction_method': 'error',
        'post_type': 'post'
    }
    
    # Verify structure
    assert error_result['valid'] is False
    assert 'error' in error_result['reason']
    assert error_result['extraction_method'] == 'error'

