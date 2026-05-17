#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Weibo (微博) User Feed Generator.

Configuration:
1. WEIBO_USER_ID env var (comma-separated). Accepts:
     - pure uid     "1234567890"
     - full URL     "https://weibo.com/u/<uid>"
     - screen name URL "https://weibo.com/<screen_name>"  (auto-resolved if possible)

2. Optional video download (default off): WEIBO_DOWNLOAD_VIDEOS=true
   Single-file mp4 from f.video.weibocdn.com or similar — no ffmpeg needed.

Example:
    WEIBO_USER_ID="1234567890" python scripts/run_single.py weibo_user
"""

import hashlib
import logging
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytz

from generators.base import Article, BaseFeedGenerator
from generators.social.weibo.scraper import (
    check_weibo_ready,
    create_weibo_browser,
    WEIBO_PROFILE_DIR,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DOWNLOAD_DIR = PROJECT_ROOT / "downloads" / "weibo"


def _parse_user_input(raw: str) -> tuple[str, str]:
    """
    Resolve a Weibo user input into (uid, profile_url).

    Accepts:
      - pure uid         "1234567890"
      - URL /u/<uid>     "https://weibo.com/u/1234567890"
      - URL /<screen>    "https://weibo.com/screen_name"  (kept as-is, no uid)
    """
    raw = (raw or "").strip()
    if not raw:
        return "", ""

    if raw.startswith(("http://", "https://")):
        m = re.search(r"/u/(\d+)", raw)
        if m:
            uid = m.group(1)
            return uid, f"https://weibo.com/u/{uid}"
        # Could be a screen-name URL — keep as is, let the page render and
        # resolve internally. The "uid" we return is the URL path so dedup
        # at least works.
        m2 = re.search(r"weibo\.com/([^/?#]+)", raw)
        if m2:
            return m2.group(1), raw
        return raw, raw

    # Pure uid (all digits) — wrap in /u/
    if raw.isdigit():
        return raw, f"https://weibo.com/u/{raw}"
    # Otherwise treat as screen-name
    return raw, f"https://weibo.com/{raw}"


class WeiboUserGenerator(BaseFeedGenerator):
    """RSS generator for Weibo user posts."""

    FEED_NAME = "weibo_user"
    FEED_TITLE = "Weibo User Posts"
    FEED_URL = "https://weibo.com/"
    FEED_DESCRIPTION = "Latest posts from Weibo users"
    FEED_LANGUAGE = "zh-CN"
    FEED_LOGO = "https://weibo.com/favicon.ico"

    USER_INPUTS = [
        u.strip()
        for u in os.environ.get("WEIBO_USER_ID", "").split(",")
        if u.strip()
    ]

    MAX_POSTS = int(os.environ.get("WEIBO_MAX_POSTS", "20"))
    DOWNLOAD_VIDEOS = os.environ.get("WEIBO_DOWNLOAD_VIDEOS", "false").lower() == "true"

    def __init__(self):
        super().__init__()
        if not self.USER_INPUTS:
            self.logger.warning("No users configured. Set WEIBO_USER_ID environment variable.")
            self.logger.warning(
                "Example: WEIBO_USER_ID='1234567890' "
                "or full URL 'https://weibo.com/u/1234567890'"
            )

    def fetch_articles(self) -> list[Article]:
        ready, msg = check_weibo_ready()
        if not ready:
            self.logger.error(msg)
            return []

        browser = create_weibo_browser(headless=False)
        if not browser:
            return []

        articles = []

        per_user_cap = self.MAX_POSTS
        run_cap = getattr(self, "_run_max_articles", None)
        if run_cap is not None and run_cap < per_user_cap:
            self.logger.info(
                f"Run cap (--max {run_cap}) overrides WEIBO_MAX_POSTS={per_user_cap}"
            )
            per_user_cap = run_cap

        try:
            for raw in self.USER_INPUTS:
                uid, profile_url = _parse_user_input(raw)
                self.logger.info(f"Fetching posts from user {uid} (URL: {profile_url})")
                posts = self._fetch_user_posts(browser, uid, profile_url, max_posts=per_user_cap)
                articles.extend(posts)
                self.logger.info(f"Found {len(posts)} posts from {uid}")
        finally:
            browser.quit()

        return articles

    def _fetch_user_posts(
        self,
        browser,
        uid: str,
        profile_url: str,
        max_posts: int = 20,
    ) -> list[Article]:
        articles = []

        try:
            self.logger.info(f"Accessing user profile: {profile_url}")
            browser.get(profile_url)

            delay = random.uniform(3, 5)
            self.logger.info(f"Waiting {delay:.1f}s to avoid anti-scraping...")
            browser.wait(delay)

            current_url = browser.url
            self.logger.info(f"Current URL after loading: {current_url}")

            if "passport.weibo" in (current_url or "") or "/login" in (current_url or ""):
                self.logger.error("Redirected to login — Weibo profile may have expired")
                return []

            author_name = self._extract_author_name(browser, uid)
            self.logger.info(f"Author: {author_name}")

            # Scroll for more posts
            self._scroll_for_posts(browser, max_posts)

            post_items = self._find_post_items(browser)
            if not post_items:
                self.logger.warning("No post items found with any selector")
                return []

            self.logger.info(f"Found {len(post_items)} post cards on page")

            parsed = 0
            for item in post_items:
                if parsed >= max_posts:
                    break
                try:
                    article = self._parse_post_item(item, uid, author_name)
                    if article:
                        articles.append(article)
                        parsed += 1
                except Exception as e:
                    self.logger.debug(f"Parse failed for one item: {e}")
                    continue

            if self.DOWNLOAD_VIDEOS and articles:
                for art in articles:
                    self._maybe_download_video(art, uid, browser)

        except Exception as e:
            self.logger.error(f"Error fetching posts for {uid}: {e}")

        return articles

    def _extract_author_name(self, browser, uid: str) -> str:
        """Weibo's profile page <title> is reliably '@<nickname> 的个人主页'."""
        try:
            title = (getattr(browser, "title", "") or "").strip()
            m = re.match(r'^@?(.+?)\s*的个人主页', title)
            if m:
                return m.group(1).strip()
        except Exception:
            pass

        # Fall back to in-DOM markers (dynamic hash suffixes — fragile)
        for sel in [
            'css:[class*="ProfileHeader_name"]',
            'css:[class*="_name_"]',
            'css:h1',
        ]:
            try:
                el = browser.ele(sel, timeout=0.5)
                if el and (el.text or "").strip():
                    return el.text.strip()
            except Exception:
                continue
        return f"User{uid}"

    def _scroll_for_posts(self, browser, target: int):
        max_scrolls = 8
        no_change = 0
        prev_count = 0
        for i in range(max_scrolls):
            browser.scroll.to_bottom()
            browser.wait(2)
            try:
                links = browser.eles('tag:a', timeout=1)
                cnt = len([a for a in links if re.search(r'/\d+/[A-Za-z0-9]+', a.attr('href') or '')])
            except Exception:
                cnt = 0
            if cnt >= target * 2:
                self.logger.info(f"Reached target ({cnt} >= {target}*2), stopping scroll")
                return
            if cnt == prev_count:
                no_change += 1
                if no_change >= 2:
                    self.logger.info(f"No new posts after 2 attempts, stopping scroll")
                    return
            else:
                no_change = 0
            prev_count = cnt

    def _find_post_items(self, browser) -> list:
        """Each post on a weibo profile is wrapped in an <article> tag."""
        selectors = [
            'css:article',
            'css:[class*="wbpro-feed-content"]',
            'css:.WB_feed_detail',
            'css:.card-wrap[mid]',
        ]
        for sel in selectors:
            try:
                items = browser.eles(sel, timeout=1)
                if items:
                    self.logger.info(f"Using selector: {sel} ({len(items)} items)")
                    return items
            except Exception:
                continue
        return []

    def _parse_post_item(self, item, uid: str, author_name: str) -> Optional[Article]:
        """Extract one weibo Article from an <article>.

        Handles three content types:
          - pure text:      ogText only
          - text+images:    ogText + <img>s
          - video post:     ogText + <a href="//video.weibo.com/...">
        """
        # 1) Post permalink: <a href="https://weibo.com/<uid>/<bid>">
        href = None
        post_id = None
        try:
            for a in (item.eles('tag:a', timeout=0.5) or []):
                h = a.attr('href') or ''
                m = re.search(r'weibo\.com/(\d+)/([A-Za-z0-9]+)(?:\?|$|/)', h)
                if m:
                    href = h
                    post_id = m.group(2)
                    break
        except Exception:
            pass

        if not href:
            return None
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = 'https://weibo.com' + href

        # 2) Body text from wbpro-feed-ogText (always present, even for media-only posts)
        body_text = ""
        try:
            body_el = item.ele('css:[class*="wbpro-feed-ogText"]', timeout=0.5)
            if body_el:
                body_text = (body_el.text or "").strip()
        except Exception:
            pass
        # Fall back to legacy WB_text
        if not body_text:
            try:
                body_el = item.ele('css:.WB_text', timeout=0.3)
                if body_el:
                    body_text = (body_el.text or "").strip()
            except Exception:
                pass

        # 3) Collect image URLs (for image / image+text posts)
        image_urls = []
        try:
            for img in (item.eles('tag:img', timeout=0.5) or []):
                src = img.attr('src') or ''
                if not src:
                    continue
                # Skip icons, emoji, default avatars, etc.
                low = src.lower()
                if any(skip in low for skip in (
                    'face/', 'emoji/', 'icon', 'timeline_card_small', 'face.t.sinajs',
                )):
                    continue
                if 'sinaimg.cn' not in low and 'weibocdn' not in low:
                    continue
                if src.startswith('//'):
                    src = 'https:' + src
                # Upgrade thumbnail URLs to large versions
                src = src.replace('/thumb150/', '/large/').replace('/orj360/', '/large/')
                if src not in image_urls:
                    image_urls.append(src)
        except Exception:
            pass

        # 4) Detect a video link inside the post (video.weibo.com/show?fid=...)
        video_link = None
        try:
            for a in (item.eles('tag:a', timeout=0.3) or []):
                h = a.attr('href') or ''
                if 'video.weibo.com' in h or 'weibocdn.com' in h:
                    video_link = h
                    break
        except Exception:
            pass
        if video_link and video_link.startswith('//'):
            video_link = 'https:' + video_link

        # 5) Title derivation: prefer text, then "[图]" / "[视频]" fallback
        if body_text:
            title = body_text[:50] + ('...' if len(body_text) > 50 else '')
        elif image_urls:
            title = f"[{len(image_urls)} 张图片]"
        elif video_link:
            title = "[视频]"
        else:
            title = f"post_{post_id}"

        pub_date = datetime.now(pytz.timezone("Asia/Shanghai"))

        # 6) Build HTML content with full text + images
        html_parts = ['<div style="font-size:16px;line-height:1.8;color:#333">']
        if body_text:
            # Convert simple line breaks; HTML-escape minimally
            from html import escape as _esc
            esc = _esc(body_text).replace('\n', '<br>')
            html_parts.append(f'<p>{esc}</p>')
        if image_urls:
            html_parts.append('<div>')
            for src in image_urls[:9]:  # weibo shows max 9
                html_parts.append(
                    f'<p><img src="{src}" '
                    f'style="max-width:100%;height:auto;border-radius:8px;margin:4px 0" /></p>'
                )
            html_parts.append('</div>')
        if video_link:
            html_parts.append(
                f'<p>📹 <a href="{video_link}">查看视频</a></p>'
            )
        html_parts.append(
            f'<p style="margin-top:12px"><a href="{href}" '
            f'style="color:#ff8200">查看原微博 &rarr;</a></p>'
        )
        html_parts.append('</div>')

        return Article(
            url=href,
            title=f"[{author_name}] {title}",
            published_at=pub_date,
            content='\n'.join(html_parts),
            summary=body_text[:200] if body_text else title,
            author=author_name,
            images=image_urls,
            category="微博",
        )

    def _maybe_download_video(self, article: Article, uid: str, browser) -> None:
        """If the post links to a weibo video, try to capture and download it."""
        try:
            from curl_cffi import requests as _creq
        except ImportError:
            self.logger.warning("curl_cffi not installed; skipping video download")
            return

        out_dir = DOWNLOAD_DIR / uid
        out_dir.mkdir(parents=True, exist_ok=True)
        # post_id is the tail of the URL
        m = re.search(r'/(\d+)/([A-Za-z0-9]+)', article.url)
        if not m:
            return
        post_id = m.group(2)
        out_path = out_dir / f"{post_id}.mp4"
        if out_path.exists() and out_path.stat().st_size > 0:
            return

        try:
            browser.listen.start()
            browser.get(article.url)
            time.sleep(8)
        except Exception as e:
            self.logger.debug(f"Load post failed: {e}")
            try: browser.listen.stop()
            except Exception: pass
            return

        cdn_url = None
        try:
            for pkt in browser.listen.steps(count=999, timeout=2):
                u = pkt.url
                low = u.lower()
                if '.mp4' not in low:
                    continue
                if any(h in low for h in ('weibocdn.com', 'sina.com.cn', 'weibo.com')):
                    cdn_url = u
                    break
        finally:
            try: browser.listen.stop()
            except Exception: pass

        if not cdn_url:
            return  # not a video post — silent

        cookies = browser.cookies(all_domains=True)
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get('name'))
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": article.url,
            "Cookie": cookie_header,
        }
        r = None
        try:
            self.logger.info(f"Downloading weibo video {post_id}.mp4 ...")
            r = _creq.get(cdn_url, headers=headers, impersonate="chrome",
                          timeout=180, stream=True)
            if r.status_code != 200:
                self.logger.error(f"HTTP {r.status_code}")
                return
            with open(out_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
            size_mb = out_path.stat().st_size / (1024 * 1024)
            if out_path.stat().st_size < 10_000:
                out_path.unlink(missing_ok=True)
                return
            self.logger.info(f"Downloaded: {out_path.name} ({size_mb:.1f} MB)")
        except Exception as e:
            self.logger.error(f"Download of {post_id} failed: {e}")
        finally:
            if r is not None:
                try: r.close()
                except Exception: pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate Weibo User RSS")
    parser.add_argument("--max", type=int, default=20)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    gen = WeiboUserGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
