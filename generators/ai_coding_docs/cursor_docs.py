#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""Cursor Documentation Crawler."""

from generators.ai_coding_docs.base_docs_crawler import BaseDocsCrawler


class CursorDocsGenerator(BaseDocsCrawler):
    """RSS generator for Cursor documentation."""
    
    FEED_NAME = "cursor_docs"
    FEED_TITLE = "Cursor Documentation"
    FEED_URL = "https://cursor.com/en-US/docs"
    FEED_DESCRIPTION = "Cursor AI code editor documentation - Agent, Rules, MCP, Skills & CLI"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://cursor.com/favicon.ico"
    
    BASE_URL = "https://cursor.com"
    DOCS_PATH_PATTERN = r"/(en-US/)?docs"
    INDEX_FILES = []  # Cursor 没有索引文件，需要动态发现
    REQUIRE_JS = True  # 需要 JS 渲染
    
    CONTENT_SELECTORS = [
        "article",
        "main",
        "[role='main']",
        ".docs-content",
        ".content",
    ]
    
    def fetch_articles(self):
        """Override to use dynamic link discovery from rendered page."""
        from generators.utils import smart_fetch
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        
        self.logger.info("Fetching Cursor docs homepage with JS rendering")
        html = smart_fetch(self.FEED_URL, require_js=True, selenium_wait=10)
        
        if not html:
            self.logger.error("Failed to fetch homepage")
            return []
        
        # 发现所有文档链接
        soup = BeautifulSoup(html, "html.parser")
        all_links = soup.find_all("a", href=True)
        
        doc_urls = set()
        for link in all_links:
            href = link["href"]
            # 拼接完整 URL
            if href.startswith("/"):
                full_url = urljoin("https://cursor.com", href)
            elif href.startswith("http"):
                full_url = href
            else:
                continue
            
            # 只要包含 /docs 且是 cursor.com 域名
            if "/docs" in full_url and "cursor.com" in full_url and self.is_docs_url(full_url):
                doc_urls.add(full_url)
        
        self.logger.info(f"Discovered {len(doc_urls)} doc URLs from homepage")
        
        # 抓取每个页面
        articles = []
        for i, url in enumerate(list(doc_urls)[:self.MAX_PAGES]):
            self.logger.info(f"[{i+1}/{len(doc_urls)}] Crawling {url}")
            article = self.crawl_page(url)
            if article:
                articles.append(article)
        
        return articles


if __name__ == "__main__":
    import argparse
    import logging
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=100)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    gen = CursorDocsGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
