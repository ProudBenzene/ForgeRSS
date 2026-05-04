#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Run a single feed generator by name.
Useful for testing and debugging.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from generators.medical.idsociety import IDSocietyGenerator
from generators.medical.nmpa_drug import NMPADrugGenerator
from generators.ai.anthropic_news import AnthropicNewsGenerator
from generators.ai.anthropic_research import AnthropicResearchGenerator
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
    "nmpa_drug": NMPADrugGenerator,
    # AI
    "anthropic_news": AnthropicNewsGenerator,
    "anthropic_research": AnthropicResearchGenerator,
    "openai_research": OpenAIResearchGenerator,
}


def main():
    parser = argparse.ArgumentParser(description="Run a single ForgeRSS generator")
    parser.add_argument(
        "name",
        choices=list(GENERATORS.keys()),
        help="Generator name to run"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full refresh (ignore cache)"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=20,
        help="Max articles to fetch (default: 20)"
    )
    args = parser.parse_args()
    
    generator_class = GENERATORS[args.name]
    generator = generator_class()
    
    success = generator.run(
        full_refresh=args.full,
        max_articles=args.max
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
