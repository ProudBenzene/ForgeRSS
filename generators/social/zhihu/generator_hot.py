#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Zhihu Hot List RSS Generator.

Requires logged-in browser profile.
"""

import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import pytz
from bs4 import BeautifulSoup

from generators.base import Article, BaseFeedGenerator
from .scraper import (
    check_zhihu_ready,
    create_zhihu_browser,
    verify_zhihu_login,
    ZHIHU_PROFILE_DIR,
)


class ZhihuHotGenerator(BaseFeedGenerator):
    """RSS generator for Zhihu Hot List."""

    FEED_NAME = "zhihu_hot"
    FEED_TITLE = "Zhihu Hot List"
    FEED_URL = "https://www.zhihu.com/hot"
    FEED_DESCRIPTION = "Zhihu Hot List - Daily Hot Topics"
    FEED_LANGUAGE = "zh-cn"
    FEED_LOGO = "https://static.zhihu.com/heifetz/favicon.ico"

    # Requires desktop environment with login session
    REQUIRE_JS = True
    ANTI_BOT_LEVEL = 3  # Special: requires login session
    DESKTOP_ONLY = True

    def fetch_articles(self) -> list[Article]:
        """Fetch hot list items."""
        ready, msg = check_zhihu_ready()
        if not ready:
            self.logger.error(f"Zhihu not ready: {msg}")
            return []

        browser = create_zhihu_browser(headless=False)
        if not browser:
            self.logger.error("Failed to create browser")
            return []

        try:
            # Verify login
            if not verify_zhihu_login(browser):
                self.logger.error("Not logged in. Run: python -m generators.social.zhihu.scraper --login")
                return []

            # Fetch hot list
            self.logger.info(f"Fetching {self.FEED_URL}")
            browser.get(self.FEED_URL)
            browser.wait(3)

            html = browser.html
            return self._parse_hot_list(html)

        finally:
            browser.quit()

    def _parse_hot_list(self, html: str) -> list[Article]:
        """Parse hot list page."""
        soup = BeautifulSoup(html, "html.parser")
        articles = []

        # Find hot items - they have class HotItem
        hot_items = soup.select(".HotItem")
        self.logger.info(f"Found {len(hot_items)} hot items")

        for item in hot_items:
            try:
                article = self._parse_hot_item(item)
                if article:
                    articles.append(article)
            except Exception as e:
                self.logger.warning(f"Failed to parse hot item: {e}")

        return articles

    def _parse_hot_item(self, item) -> Optional[Article]:
        """Parse a single hot item."""
        # Get rank number
        rank_elem = item.select_one(".HotItem-rank")
        rank = rank_elem.get_text(strip=True) if rank_elem else ""

        # Get title and link
        title_elem = item.select_one(".HotItem-content a")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        url = title_elem.get("href", "")
        if url and not url.startswith("http"):
            url = urljoin("https://www.zhihu.com", url)

        if not title or not url:
            return None

        # Get heat/metrics
        metrics_elem = item.select_one(".HotItem-metrics")
        heat = metrics_elem.get_text(strip=True) if metrics_elem else ""

        # Get excerpt
        excerpt_elem = item.select_one(".HotItem-excerpt")
        excerpt = excerpt_elem.get_text(strip=True) if excerpt_elem else ""

        # Get image if any
        img_elem = item.select_one(".HotItem-img img")
        image_url = img_elem.get("src") if img_elem else None

        # Build content
        content_parts = []
        if rank:
            content_parts.append(f"<p><strong>Rank: {rank}</strong></p>")
        if heat:
            content_parts.append(f"<p><em>{heat}</em></p>")
        if excerpt:
            content_parts.append(f"<p>{excerpt}</p>")
        if image_url:
            content_parts.append(f'<p><img src="{image_url}" alt="{title}"></p>')
        content_parts.append(f'<p><a href="{url}">View Details</a></p>')

        content = "\n".join(content_parts)

        return Article(
            title=f"#{rank} {title}" if rank else title,
            url=url,
            content=content,
            summary=excerpt or heat,
            published_at=datetime.now(pytz.timezone("Asia/Shanghai")),
            author="Zhihu Hot List",
            images=[image_url] if image_url else [],
        )

    def fetch_article_content(self, url: str) -> Optional[Article]:
        """
        Fetch full content for a hot item (question page).
        Optional - hot list already has summaries.
        """
        # Hot list items link to questions, which require more complex parsing
        # For now, we just return None and use the summary
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate Zhihu Hot List RSS")
    parser.add_argument("--max", type=int, default=50, help="Max articles")
    parser.add_argument("--full", action="store_true", help="Full refresh")
    args = parser.parse_args()

    gen = ZhihuHotGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
