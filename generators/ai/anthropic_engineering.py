#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Anthropic Engineering Feed Generator.
Uses curl_cffi - the page embeds article data in Next.js script tags.
"""

import re
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import pytz
from bs4 import BeautifulSoup

from generators.base import Article, BaseFeedGenerator, stable_fallback_date
from generators.http_utils import smart_fetch, parse_date

logger = logging.getLogger(__name__)


class AnthropicEngineeringGenerator(BaseFeedGenerator):
    """RSS feed generator for Anthropic Engineering Blog."""
    
    FEED_NAME = "anthropic_engineering"
    FEED_TITLE = "Anthropic Engineering"
    FEED_URL = "https://www.anthropic.com/engineering"
    FEED_DESCRIPTION = "Engineering blog from Anthropic - MCP, Claude Code, and more"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://www.anthropic.com/favicon.ico"
    
    # curl_cffi works for this site (SSR with embedded JSON)
    REQUIRE_JS = False
    CONTENT_CHECK = "engineering"
    
    def fetch_articles(self) -> list[Article]:
        """Fetch articles from Anthropic engineering page."""
        html = smart_fetch(
            self.FEED_URL,
            require_js=self.REQUIRE_JS,
            content_check=self.CONTENT_CHECK
        )
        
        if not html:
            self.logger.error("Failed to fetch page")
            return []
        
        return self._parse_from_nextjs_data(html)
    
    def _parse_from_nextjs_data(self, html: str) -> list[Article]:
        """Parse articles from Next.js embedded JSON data."""
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        
        # Find the Next.js script tag containing article data
        script_tag = None
        for script in soup.find_all("script"):
            if script.string and "publishedOn" in script.string and "engineeringArticle" in script.string:
                script_tag = script
                break
        
        if not script_tag:
            self.logger.warning("Could not find Next.js data script, falling back to HTML parsing")
            return self._parse_from_html(soup)
        
        script_content = script_tag.string
        
        # Extract article data from the escaped JSON
        # Pattern: publishedOn, slug, title
        pattern = r'\\"publishedOn\\":\\"([^"]+?)\\",\\"slug\\":\{[^}]*?\\"current\\":\\"([^"]+?)\\"'
        matches = re.findall(pattern, script_content)
        
        self.logger.info(f"Found {len(matches)} articles from JSON data")
        
        for published_date, slug in matches:
            try:
                link = f"https://www.anthropic.com/engineering/{slug}"
                
                # Find title and summary for this slug
                slug_pos = script_content.find(f'\\"current\\":\\"{slug}\\"')
                if slug_pos == -1:
                    continue
                
                search_section = script_content[slug_pos:slug_pos + 2000]
                
                # Extract title
                title_match = re.search(r'\\"title\\":\\"(.*?)(?<!\\)\\"', search_section)
                title = title_match.group(1) if title_match else slug.replace("-", " ").title()
                
                # Unescape title
                title = re.sub(r'\\(.)', r'\1', title)
                
                # Extract summary
                summary = None
                summary_match = re.search(r'\\"summary\\":\\"(.*?)(?<!\\)\\"', search_section)
                if summary_match:
                    summary = re.sub(r'\\(.)', r'\1', summary_match.group(1))
                
                # Parse date
                date = parse_date(published_date)
                if not date:
                    date = stable_fallback_date(link)
                
                articles.append(Article(
                    url=link,
                    title=title,
                    published_at=date,
                    summary=summary or title,
                    category="Engineering",
                ))
                
            except Exception as e:
                self.logger.warning(f"Error parsing article {slug}: {e}")
                continue
        
        self.logger.info(f"Extracted {len(articles)} articles")
        return articles
    
    def _parse_from_html(self, soup: BeautifulSoup) -> list[Article]:
        """Fallback: parse articles from HTML links."""
        articles = []
        seen_urls = set()
        
        links = soup.select('a[href*="/engineering/"]')
        self.logger.info(f"Found {len(links)} potential links")
        
        for link in links:
            href = link.get("href", "")
            if not href:
                continue
            
            url = urljoin("https://www.anthropic.com", href)
            
            if url in seen_urls:
                continue
            if url.endswith("/engineering") or url.endswith("/engineering/"):
                continue
            
            seen_urls.add(url)
            
            # Extract title
            title = None
            for selector in ["h3", "h2", "h4", "[class*='title']"]:
                elem = link.select_one(selector)
                if elem and elem.text.strip():
                    title = elem.text.strip()
                    break
            
            if not title:
                title = link.get_text(strip=True)
            
            if not title or len(title) < 5:
                continue
            
            articles.append(Article(
                url=url,
                title=title,
                published_at=stable_fallback_date(url),
                summary=title,
                category="Engineering",
            ))
        
        self.logger.info(f"Extracted {len(articles)} articles from HTML")
        return articles
    
    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full article content."""
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
                
                paragraphs = elem.find_all(["p", "h2", "h3", "li", "pre", "code"])
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
            category="Engineering",
        )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=50)
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    gen = AnthropicEngineeringGenerator()
    gen.run(max_articles=args.max)
