#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""Qwen Code Documentation Crawler."""

from generators.ai_coding_docs.base_docs_crawler import BaseDocsCrawler


class QwenCodeDocsGenerator(BaseDocsCrawler):
    """RSS generator for Qwen Code documentation."""
    
    FEED_NAME = "qwen_code_docs"
    FEED_TITLE = "Qwen Code Documentation"
    FEED_URL = "https://qwenlm.github.io/qwen-code-docs/en/users/overview/"
    FEED_DESCRIPTION = "Qwen Code AI coding agent documentation"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://qwenlm.github.io/qwen-code-docs/favicon.ico"
    
    BASE_URL = "https://qwenlm.github.io/qwen-code-docs"
    DOCS_PATH_PATTERN = r"/qwen-code-docs/en/"
    INDEX_FILES = ["sitemap.xml"]
    
    # VitePress structure
    CONTENT_SELECTORS = [
        ".vp-doc",
        ".content",
        "article",
        "main",
    ]
    
    # VitePress has more elements to remove
    REMOVE_SELECTORS = [
        "nav",
        "header",
        "footer",
        ".sidebar",
        ".toc",
        ".navigation",
        ".breadcrumb",
        "script",
        "style",
        ".edit-link",
        ".prev-next",
        "[class*='nav']",
    ]


if __name__ == "__main__":
    import argparse
    import logging
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=100)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    gen = QwenCodeDocsGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
