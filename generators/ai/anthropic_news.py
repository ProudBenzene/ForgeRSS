#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under MIT

"""
Anthropic News Feed Generator.
Uses curl_cffi (fast) since the site is SSR.
"""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import pytz
from bs4 import BeautifulSoup

from generators.base import Article, BaseFeedGenerator, stable_fallback_date
from generators.http_utils import smart_fetch, parse_date

logger = logging.getLogger(__name__)


class AnthropicNewsGenerator(BaseFeedGenerator):
    """RSS feed generator for Anthropic News."""
    
    FEED_NAME = "anthropic_news"
    FEED_TITLE = "Anthropic News"
    FEED_URL = "https://www.anthropic.com/news"
    FEED_DESCRIPTION = "Latest news and updates from Anthropic"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://www.anthropic.com/favicon.ico"
    
    # curl_cffi works for this site
    REQUIRE_JS = False
    CONTENT_CHECK = "/news/"
    
    DATE_FORMATS = [
        "%b %d, %Y",
        "%B %d, %Y",
        "%Y-%m-%d",
    ]
    
    def _extract_title(self, card) -> Optional[str]:
        """Extract title from article card."""
        selectors = [
            "h2[class*='featuredTitle']",
            "h4[class*='title']",
            "span[class*='title']",
            "h3", "h2",
        ]
        for selector in selectors:
            elem = card.select_one(selector)
            if elem and elem.text.strip():
                return elem.text.strip()
        return None
    
    def _extract_date(self, card) -> Optional[datetime]:
        """Extract date from article card."""
        selectors = ["time", "p.detail-m", "[class*='date']"]
        
        for selector in selectors:
            elems = card.select(selector)
            for elem in elems:
                date = parse_date(elem.text.strip(), self.DATE_FORMATS)
                if date:
                    return date
        return None
    
    def _extract_category(self, card) -> str:
        """Extract category from article card."""
        selectors = ["span[class*='subject']", "span.caption.bold"]
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        for selector in selectors:
            elem = card.select_one(selector)
            if elem:
                text = elem.text.strip()
                if not any(m in text for m in months):
                    return text
        return "News"
    
    def fetch_articles(self) -> list[Article]:
        """Fetch article list from Anthropic news page."""
        html = smart_fetch(
            self.FEED_URL,
            require_js=self.REQUIRE_JS,
            content_check=self.CONTENT_CHECK
        )
        
        if not html:
            self.logger.error("Failed to fetch page")
            return []
        
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        seen_urls = set()
        
        all_links = soup.select('a[href*="/news/"]')
        self.logger.info(f"Found {len(all_links)} potential links")
        
        for card in all_links:
            href = card.get("href", "")
            if not href:
                continue
            
            url = urljoin("https://www.anthropic.com", href)
            
            # Skip duplicates and main page
            if url in seen_urls:
                continue
            if url.endswith("/news") or url.endswith("/news/"):
                continue
            
            seen_urls.add(url)
            
            title = self._extract_title(card)
            if not title or len(title) < 5:
                continue
            
            date = self._extract_date(card) or stable_fallback_date(url)
            category = self._extract_category(card)
            
            articles.append(Article(
                url=url,
                title=title,
                published_at=date,
                summary=title,
                category=category,
            ))
        
        self.logger.info(f"Extracted {len(articles)} articles")
        return articles
    
    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full article content from detail page."""
        html = smart_fetch(url, require_js=False, content_check="anthropic")
        if not html:
            return None
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract main content
        content = None
        for selector in ["article", ".post-content", "main .content", "[class*='content']"]:
            elem = soup.select_one(selector)
            if elem:
                # Remove unwanted elements
                for tag in elem.select("nav, footer, aside, script, style, [class*='nav']"):
                    tag.decompose()
                
                paragraphs = elem.find_all(["p", "h2", "h3", "li"])
                if paragraphs:
                    content = "\n\n".join(
                        p.get_text(strip=True) for p in paragraphs 
                        if p.get_text(strip=True) and len(p.get_text(strip=True)) > 20
                    )
                    if content and len(content) > 200:
                        break
        
        if not content or len(content) < 100:
            return None
        
        summary = content[:500] + "..." if len(content) > 500 else content
        
        return Article(
            url=url,
            title="",
            published_at=None,
            content=content,
            summary=summary,
            category="News",
        )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=50)
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    gen = AnthropicNewsGenerator()
    gen.run(max_articles=args.max)
