#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""OpenAI Research Feed Generator."""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from generators.base import Article, BaseFeedGenerator, stable_fallback_date
from generators.http_utils import smart_fetch, parse_date

logger = logging.getLogger(__name__)


class OpenAIResearchGenerator(BaseFeedGenerator):
    """RSS feed generator for OpenAI Research."""
    
    FEED_NAME = "openai_research"
    FEED_TITLE = "OpenAI Research News"
    FEED_URL = "https://openai.com/news/research/?limit=100"
    FEED_DESCRIPTION = "Latest research news and updates from OpenAI"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://openai.com/favicon.ico"
    
    REQUIRE_JS = False
    CONTENT_CHECK = "/index"
    
    def fetch_articles(self) -> list[Article]:
        """Fetch article list from OpenAI research page."""
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
        
        # Find news items with /index in href
        items = soup.select("a[href*='/index']")
        self.logger.info(f"Found {len(items)} potential links")
        
        for item in items:
            try:
                href = item.get("href", "")
                
                # Skip main index page
                if href == "/research/index/" or href == "/index/":
                    continue
                
                # Build URL
                url = urljoin("https://openai.com", href)
                
                # Extract title and date from full text
                # Format: "TitleCategoryDate" e.g. "Introducing GPT-5.5ProductApr 23, 2026"
                full_text = item.get_text(strip=True)
                
                # Try to extract date from text
                import re
                date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}', full_text)
                
                if date_match:
                    date = parse_date(date_match.group(), ["%b %d, %Y"])
                    # Title is text before the category/date
                    title = full_text[:date_match.start()].strip()
                    # Remove trailing category if present
                    for cat in ["Publication", "Product", "Research", "Announcement"]:
                        if title.endswith(cat):
                            title = title[:-len(cat)].strip()
                            break
                else:
                    title = full_text
                    date = None
                
                if not title or len(title) < 5:
                    continue
                
                if not date:
                    date = stable_fallback_date(url)
                
                articles.append(Article(
                    url=url,
                    title=title,
                    published_at=date,
                    summary=title,
                    category="Research",
                ))
                
            except Exception as e:
                self.logger.warning(f"Skipping article: {e}")
                continue
        
        self.logger.info(f"Extracted {len(articles)} articles")
        return articles
    
    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full article content."""
        html = smart_fetch(url, require_js=False, content_check="openai")
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
    
    gen = OpenAIResearchGenerator()
    gen.run(max_articles=args.max)
