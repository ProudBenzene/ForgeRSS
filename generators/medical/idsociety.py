#!/usr/bin/env python3
# Copyright (c) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
IDSociety Science Speaks Blog RSS Generator.
Requires Selenium because the site uses React for rendering.
"""

import re
from datetime import datetime
from typing import Optional

import pytz
from bs4 import BeautifulSoup

from generators.base import Article, BaseFeedGenerator, stable_fallback_date
from generators.utils import (
    smart_fetch,
    fetch_html,
    parse_date,
    extract_text,
    extract_images,
    clean_html_content,
    normalize_url,
)


class IDSocietyGenerator(BaseFeedGenerator):
    """RSS generator for IDSociety Science Speaks Blog."""
    
    FEED_NAME = "idsociety"
    FEED_TITLE = "IDSociety Science Speaks Blog"
    FEED_URL = "https://www.idsociety.org/science-speaks-blog/"
    FEED_DESCRIPTION = "Latest posts from IDSA's Science Speaks blog on infectious diseases"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://www.idsociety.org/favicon.ico"
    
    BASE_URL = "https://www.idsociety.org"
    
    # This site requires JS rendering
    REQUIRE_JS = True
    CONTENT_CHECK = "/science-speaks-blog/20"
    
    def fetch_articles(self) -> list[Article]:
        """Fetch article list from the blog homepage."""
        html = smart_fetch(
            self.FEED_URL,
            require_js=True,
            content_check=self.CONTENT_CHECK,
            selenium_wait=8,
            selenium_selector="a[href*='/science-speaks-blog/20']"
        )
        
        if not html:
            self.logger.error("Failed to fetch blog list page")
            return []
        
        return self._parse_article_list(html)
    
    def _parse_article_list(self, html: str) -> list[Article]:
        """Parse article list from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        seen_urls = set()
        
        # Find gridlisting-card links (the actual article cards)
        post_links = soup.select('a.gridlisting-card[href*="/science-speaks-blog/20"]')
        
        # Fallback: any link with the blog path
        if not post_links:
            post_links = soup.select('a[href*="/science-speaks-blog/20"]')
        
        self.logger.info(f"Found {len(post_links)} potential article links")
        
        for link in post_links:
            href = link.get("href", "")
            if not href:
                continue
            
            url = normalize_url(href, self.BASE_URL)
            
            if url in seen_urls:
                continue
            if url.rstrip("/").endswith("/science-speaks-blog") or "#" in url:
                continue
            
            seen_urls.add(url)
            
            title = self._extract_title(link)
            if not title or len(title) < 10:
                continue
            
            # Skip navigation/menu items
            if "View all" in title or "Guidelines" in title:
                self.logger.debug(f"Skipping nav item: {title}")
                continue
            
            date = self._extract_date(link, url)
            
            articles.append(Article(
                url=url,
                title=title,
                published_at=date,
                category="Medical",
            ))
        
        self.logger.info(f"Extracted {len(articles)} articles")
        return articles
    
    def _extract_title(self, element) -> Optional[str]:
        """Extract title from element."""
        # Prefer h4 (main article title in gridlisting-card)
        h4 = element.find("h4")
        if h4:
            title = extract_text(h4)
            if title and len(title) >= 10 and "View all" not in title:
                return title
        
        # Try img alt attribute (reliable fallback)
        img = element.find("img")
        if img and img.get("alt"):
            alt = img.get("alt", "").replace(" thumbnail", "").strip()
            if alt and len(alt) >= 10 and "View all" not in alt:
                return alt
        
        # Try other heading tags (but NOT h6 which is used for nav)
        for tag in ["h3", "h2"]:
            heading = element.find(tag)
            if heading:
                title = extract_text(heading)
                if title and "View all" not in title and len(title) >= 10:
                    return title
        
        # Try common class patterns
        for selector in [".gridlisting-card-title", ".title", ".headline"]:
            title_elem = element.select_one(selector)
            if title_elem:
                title = extract_text(title_elem)
                if title and len(title) >= 10 and "View all" not in title:
                    return title
        
        return None
    
    def _extract_date(self, element, url: str) -> Optional[datetime]:
        """Extract date from element or URL."""
        # Try to find date elements
        date_selectors = [
            "time", ".date", "[class*='date']", 
            ".meta", "[class*='meta']"
        ]
        
        for selector in date_selectors:
            date_elem = element.select_one(selector)
            if date_elem:
                date = parse_date(date_elem.text)
                if date:
                    return date
        
        # Extract from URL pattern /science-speaks-blog/YYYY/MM/DD/
        match = re.search(r'/(\d{4})/(\d{1,2})/(\d{1,2})/', url)
        if match:
            try:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                return datetime(year, month, day, tzinfo=pytz.UTC)
            except ValueError:
                pass
        
        # Fallback
        return stable_fallback_date(url)
    
    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full article content from detail page."""
        from generators.utils import fetch_html
        
        html = fetch_html(url)
        if not html:
            self.logger.warning(f"Failed to fetch article: {url}")
            return None
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract main content - look for article body
        content = None
        content_selectors = [
            ".content-area",
            ".article-content", 
            ".post-content",
            "article",
            ".main-content",
            "main .content",
        ]
        
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # Remove nav, footer, sidebar elements
                for tag in content_elem.select("nav, footer, aside, .sidebar, .navigation"):
                    tag.decompose()
                
                # Get text content
                paragraphs = content_elem.find_all(["p", "h2", "h3", "li"])
                if paragraphs:
                    content = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                    if content and len(content) > 100:
                        break
        
        if not content:
            # Fallback: get all paragraphs
            paragraphs = soup.find_all("p")
            texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50]
            if texts:
                content = "\n\n".join(texts[:20])  # Limit to first 20 paragraphs
        
        if not content or len(content) < 100:
            self.logger.warning(f"No content found for: {url}")
            return None
        
        # Create summary from content
        summary = content[:500] + "..." if len(content) > 500 else content
        
        # Extract images
        images = []
        for img in soup.select("article img, .content img, main img"):
            src = img.get("src") or img.get("data-src")
            if src and not src.startswith("data:"):
                if src.startswith("/"):
                    src = f"{self.BASE_URL}{src}"
                images.append(src)
        
        return Article(
            url=url,
            title="",  # Will be replaced by original title
            published_at=None,  # Will be replaced by original date
            content=content,
            summary=summary,
            images=images[:5],  # Limit images
            category="Medical",
        )


if __name__ == "__main__":
    import argparse
    import logging
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=20)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    gen = IDSocietyGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
