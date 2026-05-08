#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Run all AI coding tools documentation generators.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from generators.ai_coding_docs.openai_codex import OpenAICodexDocsGenerator
from generators.ai_coding_docs.claude_code import ClaudeCodeDocsGenerator
from generators.ai_coding_docs.cursor_docs import CursorDocsGenerator
from generators.ai_coding_docs.qwen_code import QwenCodeDocsGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

GENERATORS = [
    ("OpenAI Codex", OpenAICodexDocsGenerator),
    ("Claude Code", ClaudeCodeDocsGenerator),
    ("Cursor", CursorDocsGenerator),
    ("Qwen Code", QwenCodeDocsGenerator),
]


def main():
    parser = argparse.ArgumentParser(
        description="Generate RSS feeds for AI coding tools documentation"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=100,
        help="Maximum pages to crawl per site (default: 100)"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full refresh (ignore cache)"
    )
    parser.add_argument(
        "--generator",
        choices=["openai", "claude", "cursor", "qwen", "all"],
        default="all",
        help="Which generator to run (default: all)"
    )
    
    args = parser.parse_args()
    
    # Filter generators
    if args.generator != "all":
        gen_map = {
            "openai": OpenAICodexDocsGenerator,
            "claude": ClaudeCodeDocsGenerator,
            "cursor": CursorDocsGenerator,
            "qwen": QwenCodeDocsGenerator,
        }
        selected = [(args.generator.title(), gen_map[args.generator])]
    else:
        selected = GENERATORS
    
    logger.info(f"Running {len(selected)} documentation generators")
    
    success_count = 0
    fail_count = 0
    
    for name, GeneratorClass in selected:
        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {name}")
        logger.info(f"{'='*60}")
        
        try:
            gen = GeneratorClass()
            gen.run(full_refresh=args.full, max_articles=args.max)
            success_count += 1
            logger.info(f"✓ {name} completed successfully")
        except Exception as e:
            fail_count += 1
            logger.error(f"✗ {name} failed: {e}", exc_info=True)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Summary: {success_count} succeeded, {fail_count} failed")
    logger.info(f"{'='*60}")
    
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
