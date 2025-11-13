#!/bin/bash
# Basic usage examples for WaybackPress

# Example 1: Quick recovery of a site
# This runs the complete pipeline in one command
waybackpress run example.com

# Example 2: Step-by-step recovery with more control
waybackpress discover example.com
waybackpress validate --output wayback-data/example.com
waybackpress fetch-media --output wayback-data/example.com
waybackpress export --output wayback-data/example.com

# Example 3: Recovery without media (faster)
waybackpress run example.com --skip-media

# Example 4: Conservative fetching (slower but more reliable)
waybackpress run example.com \
  --delay 10 \
  --concurrency 1

# Example 5: Multi-pass media fetching
waybackpress fetch-media --output wayback-data/example.com --pass 1
# Review success rate, then run pass 2
waybackpress fetch-media --output wayback-data/example.com --pass 2

# Example 6: Custom output directory
waybackpress run example.com --output /path/to/recovery

# Example 7: Custom WordPress settings
waybackpress export \
  --output wayback-data/example.com \
  --title "My Recovered Blog" \
  --url "https://newsite.com" \
  --author-name "John Doe" \
  --author-email "john@example.com"

# Example 8: Verbose logging for debugging
waybackpress run example.com --verbose

# Example 9: Resume from failed run
# If a previous run was interrupted, simply run the same command again
# WaybackPress will resume from where it left off
waybackpress run example.com

