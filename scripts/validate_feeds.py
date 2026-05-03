#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Validate generated RSS feeds.
Checks XML validity and basic RSS structure.
"""

import logging
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def validate_feed(feed_path: Path) -> bool:
    """
    Validate a single RSS feed file.
    Returns True if valid, False otherwise.
    """
    try:
        # Parse XML
        tree = ET.parse(feed_path)
        root = tree.getroot()
        
        # Check root element
        if root.tag != "rss":
            logger.error(f"{feed_path.name}: Root element is not 'rss'")
            return False
        
        # Check channel
        channel = root.find("channel")
        if channel is None:
            logger.error(f"{feed_path.name}: Missing 'channel' element")
            return False
        
        # Check required channel elements
        title = channel.find("title")
        link = channel.find("link")
        description = channel.find("description")
        
        if title is None or not title.text:
            logger.warning(f"{feed_path.name}: Missing or empty 'title'")
        if link is None or not link.text:
            logger.warning(f"{feed_path.name}: Missing or empty 'link'")
        if description is None or not description.text:
            logger.warning(f"{feed_path.name}: Missing or empty 'description'")
        
        # Count items
        items = channel.findall("item")
        logger.info(f"{feed_path.name}: Valid RSS with {len(items)} items")
        
        # Check each item has required fields
        for i, item in enumerate(items):
            item_title = item.find("title")
            item_link = item.find("link")
            if item_title is None or item_link is None:
                logger.warning(f"{feed_path.name}: Item {i} missing title or link")
        
        return True
        
    except ET.ParseError as e:
        logger.error(f"{feed_path.name}: XML parse error: {e}")
        return False
    except Exception as e:
        logger.error(f"{feed_path.name}: Validation error: {e}")
        return False


def main():
    feeds_dir = Path(__file__).parent.parent / "feeds"
    
    if not feeds_dir.exists():
        logger.error(f"Feeds directory not found: {feeds_dir}")
        sys.exit(1)
    
    feed_files = list(feeds_dir.glob("*.xml"))
    
    if not feed_files:
        logger.warning("No feed files found")
        sys.exit(0)
    
    logger.info(f"Validating {len(feed_files)} feed(s)...")
    
    results = []
    for feed_path in feed_files:
        valid = validate_feed(feed_path)
        results.append((feed_path.name, valid))
    
    # Summary
    logger.info("")
    logger.info("Validation Summary:")
    all_valid = True
    for name, valid in results:
        status = "OK" if valid else "FAIL"
        logger.info(f"  [{status}] {name}")
        if not valid:
            all_valid = False
    
    sys.exit(0 if all_valid else 1)


if __name__ == "__main__":
    main()
