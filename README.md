# WaybackPress

Recover WordPress sites from the Internet Archive's Wayback Machine. This tool discovers, validates, and exports WordPress content from archived snapshots into a standard WordPress WXR import file.

## Features

- Automated URL discovery from Wayback Machine CDX API
- Intelligent post validation with content heuristics
- Multi-pass media fetching with automatic retries
- Clean WXR 1.2 export compatible with WordPress Importer
- Resumable operations with progress tracking
- Configurable request throttling to respect archive.org
- Detailed logging and reporting

## Legal and Ethical Use

**This tool is for personal archival and legitimate content recovery only.**

You are responsible for:
- Only recovering content you have legal rights to
- Complying with Internet Archive's Terms of Service
- Respecting copyright and intellectual property laws
- Using conservative rate limiting (default: 5s delay, 2 concurrency)
- Not using this for commercial scraping or bulk downloads

The tool has built-in safeguards (rate limiting, user-agent identification) but ultimately you are responsible for how you use it.

## Installation

### From Source

```bash
git clone https://github.com/stardothosting/shift8-waybackpress.git
cd shift8-waybackpress
pip install -r requirements.txt
pip install -e .
```

### Requirements

- Python 3.8 or higher
- Dependencies: beautifulsoup4, lxml, aiohttp, python-dateutil

## Quick Start

The simplest way to recover a site:

```bash
waybackpress run example.com
```

This will run the complete pipeline: discover URLs, validate posts, fetch media, and generate a WordPress import file.

## Usage

WaybackPress works in stages, allowing you to control each step of the recovery process.

### Stage 1: Discover URLs

Query the Wayback Machine to find all archived URLs for your domain:

```bash
waybackpress discover example.com
```

Options:
- `--output DIR`: Specify output directory (default: wayback-data/example.com)
- `--delay SECONDS`: Delay between requests (default: 5)
- `--concurrency N`: Concurrent requests (default: 2)

### Stage 2: Validate Posts

Download and validate discovered URLs to identify actual blog posts:

```bash
waybackpress validate --output wayback-data/example.com
```

This stage:
- Downloads HTML for each URL
- Extracts metadata (title, date, author, categories, tags)
- Identifies valid posts using content heuristics
- Filters out archives, category pages, and duplicates
- Generates a detailed validation report

### Stage 3: Fetch Media

Download images, CSS, and JavaScript referenced in posts:

```bash
waybackpress fetch-media --output wayback-data/example.com
```

Options:
- `--pass N`: Pass number for multi-pass fetching (default: 1)

The media fetcher:
- Parses HTML to extract all media URLs
- Queries CDX API for available snapshots
- Attempts multiple snapshots if initial fetch fails
- Tracks successes and failures for additional passes
- Saves progress incrementally

#### Multi-Pass Media Fetching

If the first pass has a low success rate, run additional passes:

```bash
waybackpress fetch-media --output wayback-data/example.com --pass 2
```

Each pass attempts different snapshots, increasing the likelihood of recovery.

### Stage 4: Export to WordPress

Generate a WordPress WXR import file:

```bash
waybackpress export --output wayback-data/example.com
```

Options:
- `--title TEXT`: Site title for export (default: domain name)
- `--url URL`: Site URL for export (default: http://domain)
- `--author-name NAME`: Post author name (default: admin)
- `--author-email EMAIL`: Post author email (default: admin@example.com)

### Complete Pipeline

Run all stages at once:

```bash
waybackpress run example.com
```

Options:
- `--skip-media`: Skip media fetching
- `--output DIR`: Output directory
- `--delay SECONDS`: Request delay
- `--concurrency N`: Concurrent requests
- All export options (--title, --url, --author-name, --author-email)

## Output Structure

WaybackPress creates the following directory structure:

```
wayback-data/
└── example.com/
    ├── config.json              # Project configuration
    ├── waybackpress.log         # Detailed logs
    ├── discovered_urls.tsv      # All discovered URLs
    ├── valid_posts.tsv          # Validated post URLs
    ├── validation_report.csv    # Detailed validation results
    ├── media_report.csv         # Media fetch results
    ├── wordpress-export.xml     # Final WXR import file
    ├── html/                    # Downloaded HTML files
    │   └── post-slug.html
    └── media/                   # Downloaded media assets
        └── example.com/
            └── wp-content/
                └── uploads/
```

## Configuration

Each project maintains a `config.json` file with settings and state:

```json
{
  "domain": "example.com",
  "output_dir": "wayback-data/example.com",
  "delay": 5.0,
  "concurrency": 2,
  "skip_media": false,
  "discovered": true,
  "validated": true,
  "media_fetched": true,
  "exported": true
}
```

## Best Practices

### Respecting Archive.org

The Wayback Machine is a free public resource. Be respectful:

- Use the default 5-second delay between requests
- Keep concurrency at 2 or lower
- Run during off-peak hours for large sites
- Consider multiple sessions for sites with thousands of posts

### Media Recovery

Media fetching has inherent limitations:

- Not all media is archived
- Some snapshots may be corrupted
- Success rates typically range from 30-50%

Strategies to improve recovery:
- Run multiple passes (2-3 recommended)
- Increase delay and decrease concurrency for better reliability
- Review `media_report.csv` to identify patterns in failures
- Consider manual recovery for high-value assets

### Validation Heuristics

The validator applies several filters:

- Minimum content length (200 characters)
- Duplicate detection (content hash)
- URL pattern matching (excludes /category/, /tag/, /feed/)
- Date validation

Review `validation_report.csv` to verify results and adjust if needed.

## Importing into WordPress

After generating the WXR file:

1. Log into your WordPress admin panel
2. Go to Tools → Import → WordPress
3. Install the WordPress Importer if prompted
4. Upload `wordpress-export.xml`
5. Assign post authors and choose import options
6. Click "Run Importer"

### Media Files

Media files must be uploaded separately:

1. Connect to your server via SFTP/SSH
2. Navigate to `wp-content/uploads/`
3. Upload the contents of the `media/` directory
4. Preserve the directory structure (domain/wp-content/uploads/)

Alternatively, use WP-CLI:

```bash
wp media regenerate --yes
```

## Troubleshooting

### No Posts Found

- Verify the domain is archived: https://web.archive.org/
- Check if posts use non-standard URL patterns
- Review `discovered_urls.tsv` to see what was found
- Adjust URL filtering logic in `utils.py` if needed

### Low Media Success Rate

- Run additional passes with `--pass 2`, `--pass 3`
- Reduce concurrency: `--concurrency 1`
- Increase delay: `--delay 10`
- Check `media_report.csv` for failure patterns

### Import Errors

- Validate XML: `xmllint --noout wordpress-export.xml`
- Check WordPress error logs
- Ensure server has adequate memory (php.ini: memory_limit)
- Split large imports into smaller batches

## Development

Run tests:

```bash
python -m pytest tests/
```

Format code:

```bash
black waybackpress/
```

Type checking:

```bash
mypy waybackpress/
```

## Project Structure

```
waybackpress/
├── __init__.py       # Package metadata
├── __main__.py       # Entry point for python -m
├── cli.py            # Command-line interface
├── config.py         # Configuration management
├── utils.py          # Shared utilities
├── discover.py       # URL discovery
├── validate.py       # Post validation
├── fetch.py          # Media fetching
└── export.py         # WXR generation
```

## Known Limitations

- Only works with WordPress sites (other CMSs not supported)
- Requires posts to be archived in Wayback Machine
- Media recovery depends on archive availability
- Some dynamic content (comments, widgets) may not preserve perfectly
- Wayback snapshots may have inconsistent timestamps

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## License

MIT License. See LICENSE file for details.

## Credits

Developed by [Shift8 Web](https://shift8web.ca) for the WordPress community.

Built using:
- BeautifulSoup4 for HTML parsing
- aiohttp for async HTTP requests
- python-dateutil for flexible date parsing
- lxml for XML processing

## Support

- Issues: https://github.com/stardothosting/shift8-waybackpress/issues
- Discussions: https://github.com/stardothosting/shift8-waybackpress/discussions
- Email: info@shift8web.ca

## Changelog

### 0.1.0 (Initial Release)

- URL discovery from Wayback CDX API
- Post validation with content heuristics
- Multi-pass media fetching
- WXR 1.2 export generation
- Resumable operations
- Progress tracking and reporting

