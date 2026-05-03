#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Run all feed generators.
Used by GitHub Actions for scheduled updates.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from generators.medical.idsociety import IDSocietyGenerator
from generators.ai.anthropic_news import AnthropicNewsGenerator
from generators.ai.anthropic_research import AnthropicResearchGenerator
from generators.ai.anthropic_engineering import AnthropicEngineeringGenerator
from generators.ai.openai_research import OpenAIResearchGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Registry of all generators
GENERATORS = {
    # Medical
    "idsociety": IDSocietyGenerator,
    # AI
    "anthropic_news": AnthropicNewsGenerator,
    "anthropic_research": AnthropicResearchGenerator,
    "anthropic_engineering": AnthropicEngineeringGenerator,
    "openai_research": OpenAIResearchGenerator,
}


def run_all(full_refresh: bool = False, max_articles: int = 50):
    """Run all registered generators."""
    results = {}
    
    for name, generator_class in GENERATORS.items():
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
        emoji = "OK" if status == "success" else "FAIL"
        logger.info(f"  [{emoji}] {name}: {status}")
    
    # Exit with error if any failed
    if any(s != "success" for s in results.values()):
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
    args = parser.parse_args()
    
    run_all(full_refresh=args.full, max_articles=args.max)


if __name__ == "__main__":
    main()
