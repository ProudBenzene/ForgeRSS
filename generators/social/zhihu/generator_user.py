#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Zhihu User Activity RSS Generator.

Supports tracking specific users' activities.
Requires logged-in browser profile.
"""

import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, quote

import pytz
from bs4 import BeautifulSoup

from generators.base import Article, BaseFeedGenerator
from .scraper import (
    check_zhihu_ready,
    create_zhihu_browser,
    verify_zhihu_login,
)


class ZhihuUserGenerator(BaseFeedGenerator):
    """RSS generator for Zhihu User Activities."""

    FEED_NAME = "zhihu_user"
    FEED_TITLE = "Zhihu User Activities"
    FEED_URL = "https://www.zhihu.com/people/"
    FEED_DESCRIPTION = "Zhihu User Activities - User Posts and Answers"
    FEED_LANGUAGE = "zh-cn"
    FEED_LOGO = "https://static.zhihu.com/heifetz/favicon.ico"

    REQUIRE_JS = True
    ANTI_BOT_LEVEL = 3
    DESKTOP_ONLY = True

    # Default users to track (can be customized via args)
    DEFAULT_USERS = [
        "excited-vczh",
    ]

    def __init__(self, users: list[str] = None):
        """
        Initialize with list of user IDs to track.
        
        Args:
            users: List of Zhihu user URL names (e.g., ["excited-vczh"])
        """
        super().__init__()
        self.users = users or self.DEFAULT_USERS

    def fetch_articles(self) -> list[Article]:
        """Fetch activities from tracked users."""
        ready, msg = check_zhihu_ready()
        if not ready:
            self.logger.error(f"Zhihu not ready: {msg}")
            return []

        browser = create_zhihu_browser(headless=False)
        if not browser:
            self.logger.error("Failed to create browser")
            return []

        try:
            if not verify_zhihu_login(browser):
                self.logger.error("Not logged in")
                return []

            all_articles = []

            for user_id in self.users:
                self.logger.info(f"Fetching user: {user_id}")
                articles = self._fetch_user_activities(browser, user_id)
                all_articles.extend(articles)
                time.sleep(2)  # Rate limiting

            return all_articles

        finally:
            browser.quit()

    def _fetch_user_activities(self, browser, user_id: str) -> list[Article]:
        """Fetch a single user's activities."""
        url = f"https://www.zhihu.com/people/{user_id}/activities"
        browser.get(url)
        browser.wait(3)

        html = browser.html
        soup = BeautifulSoup(html, "html.parser")

        # Get user name
        name_elem = soup.select_one(".ProfileHeader-name")
        user_name = name_elem.get_text(strip=True) if name_elem else user_id

        articles = []

        # Parse activity items
        activity_items = soup.select(".List-item")
        self.logger.info(f"Found {len(activity_items)} activities for {user_name}")

        for item in activity_items:
            try:
                article = self._parse_activity_item(item, user_name, user_id)
                if article:
                    articles.append(article)
            except Exception as e:
                self.logger.warning(f"Failed to parse activity: {e}")

        return articles

    def _parse_activity_item(self, item, user_name: str, user_id: str) -> Optional[Article]:
        """Parse a single activity item."""
        # Determine activity type
        activity_type = ""
        type_elem = item.select_one(".ActivityItem-meta")
        if type_elem:
            activity_type = type_elem.get_text(strip=True)

        # Get content card
        content_card = item.select_one(".ContentItem")
        if not content_card:
            return None

        # Get title
        title_elem = content_card.select_one(".ContentItem-title a")
        if not title_elem:
            # Try answer format
            title_elem = content_card.select_one("h2 a")
        
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        url = title_elem.get("href", "")
        if url and not url.startswith("http"):
            url = urljoin("https://www.zhihu.com", url)

        if not title or not url:
            return None

        # Get excerpt/content
        excerpt_elem = content_card.select_one(".RichContent-inner")
        excerpt = ""
        if excerpt_elem:
            excerpt = excerpt_elem.get_text(strip=True)[:500]

        # Get image
        img_elem = content_card.select_one(".RichContent img")
        image_url = img_elem.get("src") if img_elem else None

        # Get time
        time_elem = content_card.select_one(".ContentItem-time")
        pub_time = datetime.now(pytz.timezone("Asia/Shanghai"))
        if time_elem:
            time_text = time_elem.get_text(strip=True)
            # Parse relative time - can enhance later

        # Build content
        content_parts = []
        if activity_type:
            content_parts.append(f"<p><em>{user_name} {activity_type}</em></p>")
        if excerpt:
            content_parts.append(f"<p>{excerpt}</p>")
        if image_url:
            content_parts.append(f'<p><img src="{image_url}" alt="{title}"></p>')
        content_parts.append(f'<p><a href="{url}">Read more</a></p>')

        content = "\n".join(content_parts)

        return Article(
            title=f"[{user_name}] {title}",
            url=url,
            content=content,
            summary=excerpt[:200] if excerpt else activity_type,
            published_at=pub_time,
            author=user_name,
            images=[image_url] if image_url else [],
        )

    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full content - optional enhancement."""
        return None


def search_zhihu_users(keyword: str, limit: int = 10) -> list[dict]:
    """
    Search for Zhihu users by keyword.
    
    Returns list of {id, name, headline, followers}.
    """
    ready, msg = check_zhihu_ready()
    if not ready:
        print(f"Error: {msg}")
        return []

    browser = create_zhihu_browser(headless=False)
    if not browser:
        return []

    try:
        if not verify_zhihu_login(browser):
            print("Not logged in")
            return []

        # Search URL
        search_url = f"https://www.zhihu.com/search?type=people&q={quote(keyword)}"
        browser.get(search_url)
        browser.wait(3)

        html = browser.html
        soup = BeautifulSoup(html, "html.parser")

        users = []
        user_items = soup.select(".List-item")

        for item in user_items[:limit]:
            try:
                # User link
                link_elem = item.select_one("a.UserLink-link")
                if not link_elem:
                    continue

                href = link_elem.get("href", "")
                user_id = href.split("/")[-1] if href else ""

                # Name
                name_elem = item.select_one(".UserLink-name")
                name = name_elem.get_text(strip=True) if name_elem else user_id

                # Headline
                headline_elem = item.select_one(".PeopleItem-headline")
                headline = headline_elem.get_text(strip=True) if headline_elem else ""

                # Followers
                followers_elem = item.select_one(".PeopleItem-followersCount")
                followers = followers_elem.get_text(strip=True) if followers_elem else ""

                users.append({
                    "id": user_id,
                    "name": name,
                    "headline": headline,
                    "followers": followers,
                    "url": f"https://www.zhihu.com/people/{user_id}",
                })
            except Exception:
                continue

        return users

    finally:
        browser.quit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Zhihu User Activities RSS")
    parser.add_argument("--max", type=int, default=50, help="Max articles")
    parser.add_argument("--full", action="store_true", help="Full refresh")
    parser.add_argument("--users", nargs="+", help="User IDs to track")
    parser.add_argument("--search", type=str, help="Search for users by keyword")
    args = parser.parse_args()

    if args.search:
        print(f"\nSearching for users: {args.search}")
        print("=" * 60)
        users = search_zhihu_users(args.search)
        for u in users:
            print(f"  {u['name']} (@{u['id']})")
            print(f"    {u['headline']}")
            print(f"    Followers: {u['followers']}")
            print(f"    URL: {u['url']}")
            print()
    else:
        users = args.users if args.users else None
        gen = ZhihuUserGenerator(users=users)
        gen.run(full_refresh=args.full, max_articles=args.max)
