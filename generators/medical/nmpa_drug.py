#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
NMPA (National Medical Products Administration) Drug Announcements RSS Generator.
国家药品监督管理局 - 药品公告通告

This site uses RuiShu anti-bot protection (HTTP 412 for all automated requests).
Requires DrissionPage in non-headless mode to bypass the protection.
Due to this limitation, this generator can only run locally (not in CI/CD headless env).
"""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import pytz
from bs4 import BeautifulSoup

from generators.base import Article, BaseFeedGenerator
from generators.utils import (
    smart_fetch,
    parse_date,
    extract_text,
    normalize_url,
)

BASE_URL = "https://www.nmpa.gov.cn"


class NMPADrugGenerator(BaseFeedGenerator):
    """RSS generator for NMPA Drug Announcements."""

    FEED_NAME = "nmpa_drug"
    FEED_TITLE = "国家药品监督管理局 - 药品公告通告"
    FEED_URL = "https://www.nmpa.gov.cn/yaopin/ypggtg/index.html"
    FEED_DESCRIPTION = (
        "国家药品监督管理局药品公告通告，包括药品审批、监管、"
        "通告等官方信息 / NMPA Drug Announcements"
    )
    FEED_LANGUAGE = "zh-cn"
    FEED_LOGO = "https://www.nmpa.gov.cn/wbppimages/favicon.ico"

    # RuiShu anti-bot: requires DrissionPage non-headless (headed mode)
    # anti_bot_level=2 means strong anti-bot, use DrissionPage headed
    REQUIRE_JS = True
    ANTI_BOT_LEVEL = 2  # 0=normal, 1=medium, 2=strong (RuiShu)
    CONTENT_CHECK = "/xxgk/ggtg/ypggtg/"

    # Pagination settings
    MAX_PAGES = 3  # Max pages to fetch (each page has ~20 articles)
    MAX_ARTICLES_FROM_LIST = 50  # Stop fetching after this many articles

    def fetch_articles(self) -> list[Article]:
        """
        Fetch article list with pagination support.
        NMPA uses index.html, index_1.html, index_2.html pattern.
        """
        all_articles = []
        seen_urls = set()

        for page_num in range(self.MAX_PAGES):
            # Build page URL
            if page_num == 0:
                page_url = self.FEED_URL
            else:
                page_url = self.FEED_URL.replace("index.html", f"index_{page_num}.html")

            self.logger.info(f"Fetching page {page_num + 1}/{self.MAX_PAGES}: {page_url}")

            html = smart_fetch(
                page_url,
                anti_bot_level=self.ANTI_BOT_LEVEL,
                content_check=self.CONTENT_CHECK,
                selenium_wait=8,
            )

            if not html:
                self.logger.warning(f"Failed to fetch page {page_num + 1}, stopping pagination")
                break

            # Parse articles from this page
            page_articles = self._parse_article_list(html, seen_urls)
            if not page_articles:
                self.logger.info(f"No new articles on page {page_num + 1}, stopping")
                break

            all_articles.extend(page_articles)
            self.logger.info(
                f"Page {page_num + 1}: found {len(page_articles)} articles, "
                f"total: {len(all_articles)}"
            )

            # Stop if we have enough articles
            if len(all_articles) >= self.MAX_ARTICLES_FROM_LIST:
                self.logger.info(
                    f"Reached max articles limit ({self.MAX_ARTICLES_FROM_LIST}), stopping"
                )
                break

        return all_articles[:self.MAX_ARTICLES_FROM_LIST]

    def _parse_article_list(
        self, html: str, seen_urls: set = None
    ) -> list[Article]:
        """
        Parse article list from HTML.

        Args:
            html: Page HTML content
            seen_urls: Set of already seen URLs for deduplication across pages
        """
        if seen_urls is None:
            seen_urls = set()

        soup = BeautifulSoup(html, "html.parser")
        articles = []

        for a in soup.select("a[href]"):
            href = a.get("href", "")
            text = a.get_text(strip=True)

            if "/xxgk/ggtg/ypggtg/" not in href:
                continue
            if not text or len(text) < 10:
                continue

            url = self._resolve_url(href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            articles.append(Article(
                url=url,
                title=text,
                category="药品公告通告",
            ))

        self.logger.info(f"Extracted {len(articles)} articles from current page")
        return articles

    def _resolve_url(self, href: str) -> str:
        """Resolve relative URL to absolute."""
        if href.startswith("http"):
            return href
        if href.startswith("../../"):
            return BASE_URL + "/" + href.replace("../../", "")
        if href.startswith("/"):
            return BASE_URL + href
        return urljoin(self.FEED_URL, href)

    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full article content from detail page."""
        html = smart_fetch(
            url,
            anti_bot_level=self.ANTI_BOT_LEVEL,
            selenium_wait=5,
        )
        if not html:
            self.logger.warning(f"Failed to fetch article: {url}")
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Extract date: prefer <meta name="PubDate">
        published_at = self._extract_date(soup)

        # Extract title from h2.title or page title
        title = ""
        title_elem = soup.select_one("h2.title")
        if title_elem:
            title = extract_text(title_elem)
        if not title:
            title_meta = soup.select_one('meta[name="ArticleTitle"]')
            if title_meta:
                title = title_meta.get("content", "")

        # Extract content from .text div
        content_html = self._extract_content(soup, url)

        # Extract source / author from meta
        author = None
        source_meta = soup.select_one('meta[name="ContentSource"]')
        if source_meta:
            author = source_meta.get("content", "")

        summary = ""
        if content_html:
            text_soup = BeautifulSoup(content_html, "html.parser")
            summary_text = text_soup.get_text(strip=True)
            summary = summary_text[:300] + "..." if len(summary_text) > 300 else summary_text

        return Article(
            url=url,
            title=title,
            published_at=published_at,
            content=content_html,
            summary=summary,
            author=author,
            category="药品公告通告",
        )

    def _extract_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract publish date from detail page."""
        # <meta name="PubDate" content="2026-04-24 17:19">
        pub_meta = soup.select_one('meta[name="PubDate"]')
        if pub_meta:
            date_str = pub_meta.get("content", "")
            dt = parse_date(date_str)
            if dt:
                return dt

        # .date element: "发布时间：2026-04-24"
        date_elem = soup.select_one(".date")
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            # Extract date part after colon
            match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", date_text)
            if match:
                return parse_date(match.group(1))

        return None

    def _extract_content(self, soup: BeautifulSoup, url: str) -> Optional[str]:
        """Extract article content HTML from .text or .wenzhang div."""
        # Primary: .text div (main content area)
        text_div = soup.select_one(".text")
        if text_div:
            # Clean: remove script/style
            for tag in text_div.select("script, style"):
                tag.decompose()

            # Fix relative image/link URLs
            for img in text_div.select("img"):
                src = img.get("src", "")
                if src and not src.startswith("http"):
                    img["src"] = urljoin(url, src)

            for a in text_div.select("a[href]"):
                href = a.get("href", "")
                if href and not href.startswith(("http", "mailto:", "javascript:")):
                    a["href"] = urljoin(url, href)

            content = str(text_div)
            if len(content) > 50:
                return content

        # Fallback: .wenzhang div
        wz_div = soup.select_one(".wenzhang")
        if wz_div:
            for tag in wz_div.select("script, style, .date, h2.title"):
                tag.decompose()

            for img in wz_div.select("img"):
                src = img.get("src", "")
                if src and not src.startswith("http"):
                    img["src"] = urljoin(url, src)

            content = str(wz_div)
            if len(content) > 50:
                return content

        return None


if __name__ == "__main__":
    import argparse
    import logging

    parser = argparse.ArgumentParser(
        description="NMPA Drug Announcements RSS Generator"
    )
    parser.add_argument("--max", type=int, default=20, help="Max articles in feed")
    parser.add_argument("--pages", type=int, default=3, help="Max pages to fetch")
    parser.add_argument("--full", action="store_true", help="Full refresh (ignore cache)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    gen = NMPADrugGenerator()
    gen.MAX_PAGES = args.pages
    gen.run(full_refresh=args.full, max_articles=args.max)
