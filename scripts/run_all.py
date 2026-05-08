#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Run all feed generators.
Used by GitHub Actions for scheduled updates.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from generators.medical.idsociety import IDSocietyGenerator
from generators.medical.nmpa_drug import NMPADrugGenerator
from generators.ai.anthropic_news import AnthropicNewsGenerator
from generators.ai.anthropic_research import AnthropicResearchGenerator
from generators.ai.anthropic_engineering import AnthropicEngineeringGenerator
from generators.ai.openai_research import OpenAIResearchGenerator
from generators.ai_coding_docs.openai_codex import OpenAICodexDocsGenerator
from generators.ai_coding_docs.claude_code import ClaudeCodeDocsGenerator
from generators.ai_coding_docs.cursor_docs import CursorDocsGenerator
from generators.ai_coding_docs.qwen_code import QwenCodeDocsGenerator
from generators.social.zhihu_hot import ZhihuHotGenerator
from generators.social.zhihu_user import ZhihuUserGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def is_ci_environment() -> bool:
    """Check if running in CI environment (no display available)."""
    return any([
        os.environ.get("CI"),           # GitHub Actions, GitLab CI, etc.
        os.environ.get("GITHUB_ACTIONS"),
        os.environ.get("GITLAB_CI"),
        os.environ.get("JENKINS_URL"),
    ])


# Generators that require desktop environment (non-headless browser)
# Also requires login session for some (zhihu)
DESKTOP_ONLY_GENERATORS = {"nmpa_drug", "zhihu_hot", "zhihu_user"}

# Documentation generators (update less frequently, run in separate workflow)
DOCS_GENERATORS = {"openai_codex_docs", "claude_code_docs", "cursor_docs", "qwen_code_docs"}

# Registry of all generators
GENERATORS = {
    # Medical / Government
    "idsociety": IDSocietyGenerator,
    "nmpa_drug": NMPADrugGenerator,
    # AI
    "anthropic_news": AnthropicNewsGenerator,
    "anthropic_research": AnthropicResearchGenerator,
    "anthropic_engineering": AnthropicEngineeringGenerator,
    "openai_research": OpenAIResearchGenerator,
    # AI Coding Docs
    "openai_codex_docs": OpenAICodexDocsGenerator,
    "claude_code_docs": ClaudeCodeDocsGenerator,
    "cursor_docs": CursorDocsGenerator,
    "qwen_code_docs": QwenCodeDocsGenerator,
    # Social (requires login + desktop)
    "zhihu_hot": ZhihuHotGenerator,
    "zhihu_user": ZhihuUserGenerator,
}


def run_all(full_refresh: bool = False, max_articles: int = 50, exclude_docs: bool = False):
    """Run all registered generators."""
    results = {}
    in_ci = is_ci_environment()
    
    if in_ci:
        logger.info("Detected CI environment - desktop-only generators will be skipped")
    
    if exclude_docs:
        logger.info("Excluding documentation generators (run separately)")
    
    for name, generator_class in GENERATORS.items():
        # Skip desktop-only generators in CI environment
        if in_ci and name in DESKTOP_ONLY_GENERATORS:
            logger.info(f"=" * 60)
            logger.info(f"Skipping generator: {name} (requires desktop environment)")
            logger.info(f"=" * 60)
            results[name] = "skipped"
            continue
        
        # Skip documentation generators if exclude_docs is True
        if exclude_docs and name in DOCS_GENERATORS:
            logger.info(f"=" * 60)
            logger.info(f"Skipping generator: {name} (docs run in separate workflow)")
            logger.info(f"=" * 60)
            results[name] = "skipped"
            continue
        
        logger.info(f"=" * 60)
        logger.info(f"Running generator: {name}")
        logger.info(f"=" * 60)
        
        try:
            generator = generator_class()
            success = generator.run(
                full_refresh=full_refresh,
                max_articles=max_articles
            )
            results[name] = "success" if success else "failed"
        except Exception as e:
            logger.error(f"Generator {name} crashed: {e}", exc_info=True)
            results[name] = "error"
    
    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    for name, status in results.items():
        if status == "skipped":
            emoji = "SKIP"
        elif status == "success":
            emoji = "OK"
        else:
            emoji = "FAIL"
        logger.info(f"  [{emoji}] {name}: {status}")
    
    # Exit with error only if non-skipped generators failed
    failed = [n for n, s in results.items() if s not in ("success", "skipped")]
    if failed:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Run all ForgeRSS generators")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full refresh (ignore cache)"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=50,
        help="Max articles per feed (default: 50)"
    )
    parser.add_argument(
        "--exclude-docs",
        action="store_true",
        help="Exclude documentation generators (they run in separate workflow)"
    )
    args = parser.parse_args()
    
    run_all(full_refresh=args.full, max_articles=args.max, exclude_docs=args.exclude_docs)


if __name__ == "__main__":
    main()
