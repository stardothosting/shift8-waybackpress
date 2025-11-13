"""
Command-line interface for WaybackPress.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from . import __version__
from .config import init_project, load_project, setup_logging
from .discover import discover_urls
from .validate import validate_posts
from .fetch import fetch_media
from .export import export_wxr


def cmd_discover(args):
    """Discover URLs from Wayback Machine."""
    config = init_project(
        domain=args.domain,
        output_dir=args.output,
        delay=args.delay,
        concurrency=args.concurrency,
    )
    
    logger = setup_logging(config, verbose=args.verbose)
    logger.info(f"WaybackPress v{__version__}")
    logger.info(f"Discovering URLs for {args.domain}")
    
    count = asyncio.run(discover_urls(config))
    
    if count > 0:
        logger.info(f"Success! Found {count} post URLs")
        logger.info(f"Next step: waybackpress validate --output {config.output_dir}")
    else:
        logger.error("No posts found in Wayback Machine")
        sys.exit(1)


def cmd_validate(args):
    """Validate discovered URLs and extract metadata."""
    try:
        config = load_project(Path(args.output))
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    logger = setup_logging(config, verbose=args.verbose)
    logger.info(f"Validating posts for {config.domain}")
    
    count = asyncio.run(validate_posts(config))
    
    if count > 0:
        logger.info(f"Success! Found {count} valid posts")
        if not config.skip_media:
            logger.info(f"Next step: waybackpress fetch-media --output {config.output_dir}")
        else:
            logger.info(f"Next step: waybackpress export --output {config.output_dir}")
    else:
        logger.error("No valid posts found")
        sys.exit(1)


def cmd_fetch_media(args):
    """Fetch media assets from Wayback Machine."""
    try:
        config = load_project(Path(args.output))
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    logger = setup_logging(config, verbose=args.verbose)
    logger.info(f"Fetching media for {config.domain} (pass {args.pass_number})")
    
    stats = asyncio.run(fetch_media(config, pass_number=args.pass_number))
    
    success_rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
    
    logger.info(f"Fetch complete: {stats['success']}/{stats['total']} successful ({success_rate:.1f}%)")
    
    if stats['failed'] > 0 and success_rate < 80:
        logger.info(f"Tip: Run another pass to retry failed downloads:")
        logger.info(f"  waybackpress fetch-media --output {config.output_dir} --pass {args.pass_number + 1}")
    else:
        logger.info(f"Next step: waybackpress export --output {config.output_dir}")


def cmd_export(args):
    """Export posts to WordPress WXR format."""
    try:
        config = load_project(Path(args.output))
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    logger = setup_logging(config, verbose=args.verbose)
    logger.info(f"Exporting {config.domain} to WordPress WXR")
    
    wxr_path = export_wxr(
        config,
        site_title=args.title or config.domain,
        site_url=args.url or f"http://{config.domain}",
        author_name=args.author_name,
        author_email=args.author_email,
    )
    
    logger.info(f"Export complete!")
    logger.info(f"Import file: {wxr_path}")
    logger.info(f"")
    logger.info(f"To import into WordPress:")
    logger.info(f"  1. Go to Tools → Import → WordPress")
    logger.info(f"  2. Upload {wxr_path.name}")
    logger.info(f"  3. Assign authors and import attachments")
    
    if not config.skip_media and config.media_fetched:
        media_dir = config.get_paths()['media']
        logger.info(f"")
        logger.info(f"Media files are in: {media_dir}")
        logger.info(f"Upload these to your WordPress wp-content/uploads/ directory")


def cmd_run(args):
    """Run complete pipeline: discover, validate, fetch, export."""
    logger = logging.getLogger('waybackpress')
    
    # Discover
    logger.info("=" * 60)
    logger.info("STEP 1: Discovering URLs")
    logger.info("=" * 60)
    args.domain = args.domain
    cmd_discover(args)
    
    # Validate
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 2: Validating posts")
    logger.info("=" * 60)
    cmd_validate(args)
    
    # Fetch media (if not skipped)
    if not args.skip_media:
        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 3: Fetching media")
        logger.info("=" * 60)
        args.pass_number = 1
        cmd_fetch_media(args)
    
    # Export
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"STEP {'4' if not args.skip_media else '3'}: Exporting to WXR")
    logger.info("=" * 60)
    cmd_export(args)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("COMPLETE!")
    logger.info("=" * 60)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='waybackpress',
        description='Personal archival tool for recovering WordPress content from Wayback Machine snapshots',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
LEGAL NOTICE: Use this tool responsibly and only for content you have rights to.
Respect Internet Archive's Terms of Service and all applicable laws.
See LEGAL_COMPLIANCE.md for details.

Examples:
  # Quick start - run everything
  waybackpress run example.com
  
  # Step by step with more control
  waybackpress discover example.com
  waybackpress validate --output wayback-data/example.com
  waybackpress fetch-media --output wayback-data/example.com
  waybackpress export --output wayback-data/example.com
  
  # Skip media fetching
  waybackpress run example.com --skip-media
  
  # Slower, more conservative fetching
  waybackpress fetch-media --output wayback-data/example.com --concurrency 1 --delay 10
        """
    )
    
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Discover command
    discover_parser = subparsers.add_parser('discover', help='Discover URLs from Wayback Machine')
    discover_parser.add_argument('domain', help='Domain to discover (e.g., example.com)')
    discover_parser.add_argument('--output', type=Path, help='Output directory')
    discover_parser.add_argument('--delay', type=float, default=5.0, help='Delay between requests (default: 5s)')
    discover_parser.add_argument('--concurrency', type=int, default=2, help='Concurrent requests (default: 2)')
    discover_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate discovered URLs')
    validate_parser.add_argument('--output', type=Path, required=True, help='Project directory')
    validate_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    # Fetch media command
    fetch_parser = subparsers.add_parser('fetch-media', help='Fetch media from Wayback Machine')
    fetch_parser.add_argument('--output', type=Path, required=True, help='Project directory')
    fetch_parser.add_argument('--pass', dest='pass_number', type=int, default=1, help='Pass number (default: 1)')
    fetch_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export to WordPress WXR format')
    export_parser.add_argument('--output', type=Path, required=True, help='Project directory')
    export_parser.add_argument('--title', help='Site title for export')
    export_parser.add_argument('--url', help='Site URL for export')
    export_parser.add_argument('--author-name', default='admin', help='Author name (default: admin)')
    export_parser.add_argument('--author-email', default='admin@example.com', help='Author email')
    export_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    # Run command (all-in-one)
    run_parser = subparsers.add_parser('run', help='Run complete recovery pipeline')
    run_parser.add_argument('domain', help='Domain to recover (e.g., example.com)')
    run_parser.add_argument('--output', type=Path, help='Output directory')
    run_parser.add_argument('--skip-media', action='store_true', help='Skip media fetching')
    run_parser.add_argument('--delay', type=float, default=5.0, help='Delay between requests (default: 5s)')
    run_parser.add_argument('--concurrency', type=int, default=2, help='Concurrent requests (default: 2)')
    run_parser.add_argument('--title', help='Site title for export')
    run_parser.add_argument('--url', help='Site URL for export')
    run_parser.add_argument('--author-name', default='admin', help='Author name')
    run_parser.add_argument('--author-email', default='admin@example.com', help='Author email')
    run_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Route to command
    commands = {
        'discover': cmd_discover,
        'validate': cmd_validate,
        'fetch-media': cmd_fetch_media,
        'export': cmd_export,
        'run': cmd_run,
    }
    
    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        logger = logging.getLogger('waybackpress')
        logger.error(f"Fatal error: {e}")
        if args.verbose:
            raise
        sys.exit(1)


if __name__ == '__main__':
    main()

