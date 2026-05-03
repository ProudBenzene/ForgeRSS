#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""Anthropic Research Feed Generator."""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import pytz
from bs4 import BeautifulSoup

from generators.base import Article, BaseFeedGenerator, stable_fallback_date
from generators.utils import smart_fetch, parse_date

logger = logging.getLogger(__name__)


class AnthropicResearchGenerator(BaseFeedGenerator):
    """RSS feed generator for Anthropic Research."""
    
    FEED_NAME = "anthropic_research"
    FEED_TITLE = "Anthropic Research"
    FEED_URL = "https://www.anthropic.com/research"
    FEED_DESCRIPTION = "Latest research publications from Anthropic"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://www.anthropic.com/favicon.ico"
    
    REQUIRE_JS = False
    CONTENT_CHECK = "/research/"
    
    def _extract_title(self, card) -> Optional[str]:
        """Extract title from article card."""
        for selector in ["h3", "h2", "h1", "[class*='title']"]:
            elem = card.select_one(selector)
            if elem and elem.text.strip():
                title = " ".join(elem.text.strip().split())
                if len(title) >= 5:
                    return title
        
        if hasattr(card, 'text'):
            text = " ".join(card.text.strip().split())
            if len(text) >= 5:
                return text
        return None
    
    def _extract_date(self, card) -> Optional[datetime]:
        """Extract date from article card."""
        selectors = ["p.detail-m", ".detail-m", "time", "[class*='date']"]
        formats = ["%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"]
        
        for element in [card, card.parent] if card.parent else [card]:
            for selector in selectors:
                date_elem = element.select_one(selector)
                if date_elem:
                    date = parse_date(date_elem.text.strip(), formats)
                    if date:
                        return date
        return None
    
    def fetch_articles(self) -> list[Article]:
        """Fetch article list from Anthropic research page."""
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
        
        links = soup.select('a[href*="/research/"]')
        self.logger.info(f"Found {len(links)} potential links")
        
        for card in links:
            href = card.get("href", "")
            if not href:
                continue
            
            url = urljoin("https://www.anthropic.com", href)
            
            if url in seen_urls:
                continue
            if url.endswith("/research") or url.endswith("/research/"):
                continue
            
            seen_urls.add(url)
            
            title = self._extract_title(card)
            if not title:
                continue
            
            date = self._extract_date(card) or stable_fallback_date(url)
            
            articles.append(Article(
                url=url,
                title=title,
                published_at=date,
                summary=title,
                category="Research",
            ))
        
        self.logger.info(f"Extracted {len(articles)} articles")
        return articles
    
    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full article content."""
        from generators.utils import smart_fetch
        
        html = smart_fetch(url, require_js=False, content_check="anthropic")
        if not html:
            return None
        
        soup = BeautifulSoup(html, "html.parser")
        
        content = None
        for selector in ["article", ".post-content", "main", "[class*='content']"]:
            elem = soup.select_one(selector)
            if elem:
                for tag in elem.select("nav, footer, aside, script, style"):
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
            category="Research",
        )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=50)
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    gen = AnthropicResearchGenerator()
    gen.run(max_articles=args.max)
