#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Douyin (抖音) User Video Feed Generator.

Configuration:
1. Environment variable DOUYIN_USER_ID (comma-separated)
   - Accepts pure sec_uid:  "MS4wLjABAAAA..."
   - Or full profile URL:    "https://www.douyin.com/user/MS4wLjABAAAA...?from_tab_name=..."

Example:
    DOUYIN_USER_ID="MS4wLjABAAAAxxxx" python scripts/run_single.py douyin_user
"""

import hashlib
import logging
import os
import random
import re
import time
from datetime import datetime
from typing import Optional

import pytz

from generators.base import Article, BaseFeedGenerator
from generators.social.douyin.scraper import (
    check_douyin_ready,
    create_douyin_browser,
    DOUYIN_PROFILE_DIR,
)

logger = logging.getLogger(__name__)


def _parse_user_input(raw: str) -> tuple[str, str]:
    """
    Resolve a Douyin user input into (sec_uid, profile_url).

    Accepts:
      - pure sec_uid:  "MS4wLjABAAAA..."
      - full URL:      "https://www.douyin.com/user/MS4wLjABAAAA...?from_tab_name=..."
      - short URL:     "https://v.douyin.com/<code>/"  (auto-follows redirect)
    """
    raw = (raw or "").strip()
    if not raw:
        return "", ""

    if raw.startswith(("http://", "https://")):
        # Short URL like v.douyin.com/xxx/ → follow redirect to find the sec_uid.
        # The redirect typically lands on iesdouyin.com/share/user/<sec_uid> (the
        # mobile share landing page), but we always normalize back to the
        # desktop-site URL since that is what the scraper is built for.
        if "v.douyin.com" in raw:
            try:
                import requests as _req
                r = _req.head(raw, allow_redirects=True, timeout=10,
                              headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                final = r.url
                m = re.search(r"/user/([^/?#]+)", final)
                if m:
                    sec_uid = m.group(1)
                    return sec_uid, f"https://www.douyin.com/user/{sec_uid}"
                logger.warning(f"Short URL {raw} did not resolve to a user page (got {final})")
                return raw, final
            except Exception as e:
                logger.warning(f"Failed to expand short URL {raw}: {e}")
                return raw, raw

        # Regular long URL — also normalize to canonical form (drop tracking query)
        m = re.search(r"/user/([^/?#]+)", raw)
        if m:
            sec_uid = m.group(1)
            return sec_uid, f"https://www.douyin.com/user/{sec_uid}"
        return raw, raw

    # Pure sec_uid
    return raw, f"https://www.douyin.com/user/{raw}"


class DouyinUserGenerator(BaseFeedGenerator):
    """RSS generator for Douyin user videos."""

    FEED_NAME = "douyin_user"
    FEED_TITLE = "Douyin User Videos"
    FEED_URL = "https://www.douyin.com/"
    FEED_DESCRIPTION = "Latest videos from Douyin users"
    FEED_LANGUAGE = "zh-CN"
    FEED_LOGO = "https://lf1-cdn-tos.bytescm.com/obj/static/ies/douyin_web/img/favicon.ico"

    USER_INPUTS = [u.strip() for u in os.environ.get("DOUYIN_USER_ID", "").split(",") if u.strip()]

    # Per-user fetch cap (defaults to 20). Run-level --max N overrides this.
    MAX_VIDEOS = int(os.environ.get("DOUYIN_MAX_VIDEOS", "20"))

    def __init__(self):
        super().__init__()

        if not self.USER_INPUTS:
            self.logger.warning("No users configured. Set DOUYIN_USER_ID environment variable.")
            self.logger.warning(
                "Example: DOUYIN_USER_ID='MS4wLjABAAAAxxxx' "
                "or full URL 'https://www.douyin.com/user/MS4wLjABAAAA...'"
            )

    def fetch_articles(self) -> list[Article]:
        """Fetch latest videos from configured users using logged-in browser."""
        ready, msg = check_douyin_ready()
        if not ready:
            self.logger.error(msg)
            return []

        browser = create_douyin_browser(headless=False)
        if not browser:
            return []

        articles = []

        # Honor run-level cap (`--max N`).
        per_user_cap = self.MAX_VIDEOS
        run_cap = getattr(self, "_run_max_articles", None)
        if run_cap is not None and run_cap < per_user_cap:
            self.logger.info(
                f"Run cap (--max {run_cap}) overrides DOUYIN_MAX_VIDEOS={per_user_cap}"
            )
            per_user_cap = run_cap

        try:
            for raw in self.USER_INPUTS:
                sec_uid, profile_url = _parse_user_input(raw)
                self.logger.info(
                    f"Fetching videos from user {sec_uid[:24]}... (URL: {profile_url})"
                )
                videos = self._fetch_user_videos(browser, sec_uid, profile_url, max_videos=per_user_cap)
                articles.extend(videos)
                self.logger.info(f"Found {len(videos)} videos from {sec_uid[:24]}")
        finally:
            browser.quit()

        return articles

    def _fetch_user_videos(
        self,
        browser,
        sec_uid: str,
        profile_url: str,
        max_videos: int = 20,
    ) -> list[Article]:
        """Open the user's profile and scrape their video list."""
        articles = []

        try:
            self.logger.info(f"Accessing user profile: {profile_url}")
            browser.get(profile_url)

            # Anti-bot delay
            delay = random.uniform(3, 5)
            self.logger.info(f"Waiting {delay:.1f}s to avoid anti-scraping...")
            browser.wait(delay)

            current_url = browser.url
            self.logger.info(f"Current URL after loading: {current_url}")

            # Detect login/captcha walls
            html = browser.html
            if "验证" in html and "verify" in html.lower():
                self.logger.error("Captcha detected, please solve in browser and rerun")
                return []
            if "扫码登录" in html or "登录抖音" in html:
                self.logger.error("Login required — Douyin profile may have expired")
                return []

            # Extract author display name
            author_name = self._extract_author_name(browser, sec_uid)
            self.logger.info(f"Author: {author_name}")

            # Scroll to load more videos
            self._scroll_for_videos(browser, max_videos)

            # Parse video cards (selectors WILL drift; keep flexible fallbacks)
            video_items = self._find_video_items(browser)
            if not video_items:
                self.logger.warning("No video items found with any selector")
                return []

            self.logger.info(f"Found {len(video_items)} video cards on page")

            parsed = 0
            for item in video_items:
                if parsed >= max_videos:
                    break
                try:
                    article = self._parse_video_item(item, sec_uid, author_name)
                    if article:
                        articles.append(article)
                        parsed += 1
                except Exception as e:
                    self.logger.debug(f"Parse failed for one item: {e}")
                    continue

        except Exception as e:
            self.logger.error(f"Error fetching videos for {sec_uid[:24]}: {e}")

        return articles

    def _extract_author_name(self, browser, sec_uid: str) -> str:
        """Best-effort: pull the display nickname from the profile header."""
        for sel in [
            'css:[data-e2e="user-info-nickname"]',
            'css:.user-info-nickname',
            'css:h1[class*="nickname"]',
            'css:h1',
        ]:
            try:
                el = browser.ele(sel, timeout=0.5)
                if el and (el.text or "").strip():
                    return el.text.strip()
            except Exception:
                continue
        return f"User{sec_uid[:8]}"

    def _scroll_for_videos(self, browser, target: int):
        """Scroll the profile page until we have enough video cards (or give up)."""
        max_scrolls = 8
        no_change = 0
        prev_count = 0
        for i in range(max_scrolls):
            browser.scroll.to_bottom()
            browser.wait(2)
            try:
                links = browser.eles('tag:a', timeout=1)
                cnt = len([a for a in links if '/video/' in (a.attr('href') or '')])
            except Exception:
                cnt = 0
            if cnt >= target * 2:
                self.logger.info(f"Reached target ({cnt} >= {target}*2), stopping scroll")
                return
            if cnt == prev_count:
                no_change += 1
                if no_change >= 2:
                    self.logger.info(f"No new videos after 2 attempts, stopping scroll")
                    return
            else:
                no_change = 0
            prev_count = cnt

    def _find_video_items(self, browser) -> list:
        """Try several CSS selectors to locate video cards."""
        selectors = [
            'css:[data-e2e="user-post-item"]',  # current douyin layout marker
            'css:.user-post-item',
            'css:ul li[data-index]',
            'css:.video-card',
        ]
        for sel in selectors:
            try:
                items = browser.eles(sel, timeout=1)
                if items:
                    self.logger.info(f"Using selector: {sel} ({len(items)} items)")
                    return items
            except Exception:
                continue
        # Last resort: every <a href="/video/..."> on page
        try:
            links = browser.eles('tag:a', timeout=1)
            return [a for a in links if '/video/' in (a.attr('href') or '')]
        except Exception:
            return []

    def _parse_video_item(self, item, sec_uid: str, author_name: str) -> Optional[Article]:
        """Extract one video Article from a list-page item."""
        # Find the video link
        if item.tag == 'a':
            link_elem = item
        else:
            link_elem = None
            for a in (item.eles('tag:a', timeout=0.5) or []):
                href = a.attr('href') or ''
                if '/video/' in href:
                    link_elem = a
                    break
            if not link_elem:
                return None

        href = link_elem.attr('href') or ''
        if not href:
            return None
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = 'https://www.douyin.com' + href

        m = re.search(r'/video/(\d+)', href)
        if not m:
            return None
        video_id = m.group(1)

        # Title: try multiple sources
        title = None
        for sel in [
            'css:[data-e2e="user-post-item-desc"]',
            'css:.title',
            'css:p[class*="title"]',
        ]:
            try:
                el = item.ele(sel, timeout=0.3)
                if el:
                    txt = (el.attr('title') or el.text or "").strip()
                    if txt:
                        title = txt
                        break
            except Exception:
                continue
        if not title:
            # fall back to img alt
            try:
                img = item.ele('tag:img', timeout=0.3)
                if img:
                    alt = (img.attr('alt') or "").strip()
                    if alt:
                        title = alt
            except Exception:
                pass
        if not title:
            title = f"video_{video_id}"

        # Cover image
        thumbnail = ""
        try:
            img = item.ele('tag:img', timeout=0.3)
            if img:
                src = img.attr('src') or ""
                if src.startswith('//'):
                    src = 'https:' + src
                thumbnail = src
        except Exception:
            pass

        # Stable URL hash for dedup. Douyin URLs are already unique (contain video_id),
        # so URL itself is the dedup key — but keep author prefix in title for readability.
        url_hash = hashlib.md5(href.encode()).hexdigest()[:12]

        # Use current time as a best-effort published_at (real time requires detail page)
        pub_date = datetime.now(pytz.timezone("Asia/Shanghai"))

        html_parts = [
            f'<div style="font-size:16px;line-height:1.8;color:#333">',
            f'<p><strong>作者：</strong>{author_name}</p>',
        ]
        if thumbnail:
            html_parts.append(
                f'<p><a href="{href}"><img src="{thumbnail}" alt="{title}" '
                f'style="max-width:100%;height:auto;border-radius:8px" /></a></p>'
            )
        html_parts.append(f'<p>{title}</p>')
        html_parts.append(
            f'<p style="margin-top:12px"><a href="{href}" '
            f'style="color:#fe2c55">查看原视频 &rarr;</a></p>'
        )
        html_parts.append('</div>')
        content = '\n'.join(html_parts)

        return Article(
            url=href,
            title=f"[{author_name}] {title}",
            published_at=pub_date,
            content=content,
            summary=title,
            author=author_name,
            images=[thumbnail] if thumbnail else [],
            category="抖音",
        )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate Douyin User RSS")
    parser.add_argument("--max", type=int, default=20, help="Max videos per user")
    parser.add_argument("--full", action="store_true", help="Full refresh")
    args = parser.parse_args()
    gen = DouyinUserGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
