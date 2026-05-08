#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""OpenAI Codex Documentation Crawler."""

from generators.ai_coding_docs.base_docs_crawler import BaseDocsCrawler


class OpenAICodexDocsGenerator(BaseDocsCrawler):
    """RSS generator for OpenAI Codex documentation."""
    
    FEED_NAME = "openai_codex_docs"
    FEED_TITLE = "OpenAI Codex Documentation"
    FEED_URL = "https://developers.openai.com/codex"
    FEED_DESCRIPTION = "OpenAI Codex coding agent documentation"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://developers.openai.com/favicon.ico"
    
    BASE_URL = "https://developers.openai.com/codex"
    DOCS_PATH_PATTERN = r"/codex/"
    INDEX_FILES = ["llms.txt", "sitemap.xml"]
    
    CONTENT_SELECTORS = [
        "article",
        "main",
        ".docs-content",
        ".content",
    ]


if __name__ == "__main__":
    import argparse
    import logging
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=100)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    gen = OpenAICodexDocsGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
