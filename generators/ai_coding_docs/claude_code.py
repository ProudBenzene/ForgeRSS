#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""Claude Code Documentation Crawler."""

from generators.ai_coding_docs.base_docs_crawler import BaseDocsCrawler


class ClaudeCodeDocsGenerator(BaseDocsCrawler):
    """RSS generator for Claude Code documentation."""
    
    FEED_NAME = "claude_code_docs"
    FEED_TITLE = "Claude Code Documentation"
    FEED_URL = "https://code.claude.com/docs/en/overview"
    FEED_DESCRIPTION = "Claude Code AI coding assistant documentation"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://code.claude.com/favicon.ico"
    
    BASE_URL = "https://code.claude.com/docs"
    DOCS_PATH_PATTERN = r"/docs/en/"
    REQUIRE_JS = True  # Needs JavaScript rendering
    INDEX_FILES = ["llms.txt"]  # Claude Code provides llms.txt
    
    # Claude Code docs structure
    CONTENT_SELECTORS = [
        "article",
        ".markdown-body",
        "main",
        ".content",
        "[class*='content']",
    ]


if __name__ == "__main__":
    import argparse
    import logging
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=100)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    gen = ClaudeCodeDocsGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
