#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Kuaishou (快手) User Video Feed Generator.

Configuration:
1. KUAISHOU_USER_ID env var (comma-separated). Accepts:
     - pure user id (Kuaishou calls it `principalId` or `eid`)
     - full profile URL  "https://www.kuaishou.com/profile/<id>"
     - short share URL   "https://v.kuaishou.com/<code>"  (auto-resolved)

2. Optional video download (default off):  KUAISHOU_DOWNLOAD_VIDEOS=true
   Uses the same CDP-capture + curl_cffi (+ optional ffmpeg mux) approach as
   the douyin generator.

Example:
    KUAISHOU_USER_ID="3xxxxxxxxxxxxxx" python scripts/run_single.py kuaishou_user
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
from generators.social.kuaishou.scraper import (
    check_kuaishou_ready,
    create_kuaishou_browser,
    KUAISHOU_PROFILE_DIR,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DOWNLOAD_DIR = PROJECT_ROOT / "downloads" / "kuaishou"


def _parse_user_input(raw: str) -> tuple[str, str]:
    """
    Resolve a Kuaishou user input into (user_id, profile_url).

    Accepts:
      - pure user id
      - full URL  https://www.kuaishou.com/profile/<id>
      - short URL https://v.kuaishou.com/<code>  (auto-follows redirect)
    """
    raw = (raw or "").strip()
    if not raw:
        return "", ""

    if raw.startswith(("http://", "https://")):
        if "v.kuaishou.com" in raw:
            try:
                import requests as _req
                r = _req.head(raw, allow_redirects=True, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 Chrome/122.0.0.0"
                })
                final = r.url
                m = re.search(r"/profile/([^/?#]+)", final)
                if m:
                    uid = m.group(1)
                    return uid, f"https://www.kuaishou.com/profile/{uid}"
                logger.warning(f"Short URL {raw} did not resolve to a profile (got {final})")
                return raw, final
            except Exception as e:
                logger.warning(f"Failed to expand short URL {raw}: {e}")
                return raw, raw

        m = re.search(r"/profile/([^/?#]+)", raw)
        if m:
            uid = m.group(1)
            return uid, f"https://www.kuaishou.com/profile/{uid}"
        return raw, raw

    return raw, f"https://www.kuaishou.com/profile/{raw}"


class KuaishouUserGenerator(BaseFeedGenerator):
    """RSS generator for Kuaishou user videos."""

    FEED_NAME = "kuaishou_user"
    FEED_TITLE = "Kuaishou User Videos"
    FEED_URL = "https://www.kuaishou.com/"
    FEED_DESCRIPTION = "Latest videos from Kuaishou users"
    FEED_LANGUAGE = "zh-CN"
    FEED_LOGO = "https://www.kuaishou.com/favicon.ico"

    USER_INPUTS = [
        u.strip()
        for u in os.environ.get("KUAISHOU_USER_ID", "").split(",")
        if u.strip()
    ]

    MAX_VIDEOS = int(os.environ.get("KUAISHOU_MAX_VIDEOS", "20"))
    DOWNLOAD_VIDEOS = os.environ.get("KUAISHOU_DOWNLOAD_VIDEOS", "false").lower() == "true"

    def __init__(self):
        super().__init__()
        if not self.USER_INPUTS:
            self.logger.warning("No users configured. Set KUAISHOU_USER_ID environment variable.")
            self.logger.warning(
                "Example: KUAISHOU_USER_ID='3xxxxxxxxxxxxxx' "
                "or full URL 'https://www.kuaishou.com/profile/<id>' "
                "or short URL 'https://v.kuaishou.com/<code>'"
            )

    def fetch_articles(self) -> list[Article]:
        ready, msg = check_kuaishou_ready()
        if not ready:
            self.logger.error(msg)
            return []

        browser = create_kuaishou_browser(headless=False)
        if not browser:
            return []

        articles = []

        per_user_cap = self.MAX_VIDEOS
        run_cap = getattr(self, "_run_max_articles", None)
        if run_cap is not None and run_cap < per_user_cap:
            self.logger.info(
                f"Run cap (--max {run_cap}) overrides KUAISHOU_MAX_VIDEOS={per_user_cap}"
            )
            per_user_cap = run_cap

        try:
            for raw in self.USER_INPUTS:
                uid, profile_url = _parse_user_input(raw)
                self.logger.info(f"Fetching videos from user {uid} (URL: {profile_url})")
                videos = self._fetch_user_videos(browser, uid, profile_url, max_videos=per_user_cap)
                articles.extend(videos)
                self.logger.info(f"Found {len(videos)} videos from {uid}")
        finally:
            browser.quit()

        return articles

    def _fetch_user_videos(
        self,
        browser,
        uid: str,
        profile_url: str,
        max_videos: int = 20,
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

            html = browser.html
            if "验证" in html and "verify" in html.lower():
                self.logger.error("Captcha detected, please solve in browser and rerun")
                return []
            if "扫码登录" in html or "登录快手" in html:
                self.logger.error("Login required — Kuaishou profile may have expired")
                return []

            author_name = self._extract_author_name(browser, uid)
            self.logger.info(f"Author: {author_name}")

            self._scroll_for_videos(browser, max_videos)

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
                    article = self._parse_video_item(item, uid, author_name)
                    if article:
                        articles.append(article)
                        parsed += 1
                except Exception as e:
                    self.logger.debug(f"Parse failed for one item: {e}")
                    continue

            if self.DOWNLOAD_VIDEOS and articles:
                for art in articles:
                    self._download_video(art.url, uid, browser=browser)

        except Exception as e:
            self.logger.error(f"Error fetching videos for {uid}: {e}")

        return articles

    def _extract_author_name(self, browser, uid: str) -> str:
        for sel in [
            'css:.profile-user-name',
            'css:.user-name',
            'css:h1[class*="name"]',
            'css:h1',
        ]:
            try:
                el = browser.ele(sel, timeout=0.5)
                if el and (el.text or "").strip():
                    return el.text.strip()
            except Exception:
                continue
        return f"User{uid[:8]}"

    def _scroll_for_videos(self, browser, target: int):
        max_scrolls = 8
        no_change = 0
        prev_count = 0
        for i in range(max_scrolls):
            browser.scroll.to_bottom()
            browser.wait(2)
            try:
                links = browser.eles('tag:a', timeout=1)
                cnt = len([a for a in links if '/short-video/' in (a.attr('href') or '')])
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
        """Kuaishou profile shows videos as .photo-card divs (no <a href>).
        Click handlers do navigation in JS. We parse the cover-img URL to
        extract the photo_id from `clientCacheKey=<id>.jpg`.
        """
        selectors = [
            'css:.photo-card',          # current layout (verified 2026-05)
            'css:[class*="photo-card"]',
            'css:.card-container',
            'css:.feed-card',
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

    def _parse_video_item(self, item, uid: str, author_name: str) -> Optional[Article]:
        """Parse one .photo-card. photo_id comes from cover img's clientCacheKey."""
        # Cover image carries the photo id in its CDN URL: ...&clientCacheKey=<id>.jpg
        thumbnail = ""
        video_id = None
        try:
            img = item.ele('css:.cover-img', timeout=0.3) or item.ele('tag:img', timeout=0.3)
            if img:
                src = img.attr('src') or ""
                if src.startswith('//'):
                    src = 'https:' + src
                thumbnail = src
                m = re.search(r'clientCacheKey=([a-zA-Z0-9]+)', src)
                if m:
                    video_id = m.group(1)
        except Exception:
            pass

        if not video_id:
            return None

        href = f"https://www.kuaishou.com/short-video/{video_id}"

        # Title from caption div (visible text)
        title = None
        try:
            cap = item.ele('css:.caption', timeout=0.3)
            if cap and (cap.text or "").strip():
                title = cap.text.strip()
        except Exception:
            pass
        # Fall back to img alt
        if not title:
            try:
                img = item.ele('css:.cover-img', timeout=0.3) or item.ele('tag:img', timeout=0.3)
                if img:
                    alt = (img.attr('alt') or "").strip()
                    if alt:
                        title = alt
            except Exception:
                pass
        if not title:
            title = f"video_{video_id}"

        # Author name on the card (overrides the user-level one if present)
        try:
            name_el = item.ele('css:.name', timeout=0.3)
            if name_el and (name_el.text or "").strip():
                author_name = name_el.text.strip()
        except Exception:
            pass

        pub_date = datetime.now(pytz.timezone("Asia/Shanghai"))

        html_parts = [
            '<div style="font-size:16px;line-height:1.8;color:#333">',
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
            f'style="color:#ff5500">查看原视频 &rarr;</a></p>'
        )
        html_parts.append('</div>')

        return Article(
            url=href,
            title=f"[{author_name}] {title}",
            published_at=pub_date,
            content='\n'.join(html_parts),
            summary=title,
            author=author_name,
            images=[thumbnail] if thumbnail else [],
            category="快手",
        )

    def _download_video(self, video_page_url: str, uid: str, browser=None) -> Optional[Path]:
        """Download via CDP capture + curl_cffi (mirrors douyin approach).

        Kuaishou's web player typically issues a single mp4 (not DASH-split),
        so ffmpeg muxing is usually not required. The capture watches for
        *.kuaishou.com/*.mp4 or known CDN hosts (txmov2.a.kwimgs.com etc.).
        """
        if not browser:
            self.logger.warning("No browser; cannot download")
            return None

        m = re.search(r'/short-video/(\w+)', video_page_url)
        if not m:
            return None
        video_id = m.group(1)

        out_dir = DOWNLOAD_DIR / uid
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{video_id}.mp4"
        if out_path.exists() and out_path.stat().st_size > 0:
            self.logger.info(f"Already downloaded: {out_path.name}")
            return out_path

        try:
            browser.listen.start()
            self.logger.info(f"Rendering video page {video_page_url[:80]} ...")
            browser.get(video_page_url)
            time.sleep(8)
        except Exception as e:
            self.logger.error(f"Failed to load video page: {e}")
            try: browser.listen.stop()
            except Exception: pass
            return None

        # Kuaishou serves single-file mp4 over short-lived signed CDN URLs.
        # Hosts seen (2026-05): *.djvod.ndcimgs.com (primary), *.yximgs.com,
        # *.gifshow.com, *.kwimgs.com. We just grab the first `.mp4` URL from
        # any of these hosts.
        cdn_url = None
        try:
            for pkt in browser.listen.steps(count=999, timeout=2):
                u = pkt.url
                low = u.lower()
                if '.mp4' not in low:
                    continue
                if any(host in low for host in (
                    'ndcimgs.com', 'yximgs.com', 'kwimgs.com', 'gifshow.com',
                    'kuaishou.com', 'kuaishoupro.com',
                )):
                    cdn_url = u
                    break
        finally:
            try: browser.listen.stop()
            except Exception: pass

        if not cdn_url:
            self.logger.error(f"No video CDN url captured for {video_id}")
            return None
        self.logger.info(f"Got CDN url ({cdn_url[:100]}...)")

        try:
            from curl_cffi import requests as _creq
        except ImportError:
            self.logger.error("curl_cffi not installed")
            return None

        cookies = browser.cookies(all_domains=True)
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get('name'))
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": video_page_url,
            "Cookie": cookie_header,
        }
        r = None
        try:
            self.logger.info(f"Downloading {out_path.name} ...")
            r = _creq.get(cdn_url, headers=headers, impersonate="chrome",
                          timeout=180, stream=True)
            if r.status_code != 200:
                self.logger.error(f"HTTP {r.status_code}")
                return None
            with open(out_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
            size_mb = out_path.stat().st_size / (1024 * 1024)
            if out_path.stat().st_size < 10_000:
                self.logger.error(f"Downloaded file too small ({size_mb:.2f} MB)")
                out_path.unlink(missing_ok=True)
                return None
            self.logger.info(f"Downloaded: {out_path.name} ({size_mb:.1f} MB)")
            return out_path
        except Exception as e:
            self.logger.error(f"Download of {video_id} failed: {e}")
            return None
        finally:
            if r is not None:
                try: r.close()
                except Exception: pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate Kuaishou User RSS")
    parser.add_argument("--max", type=int, default=20)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    gen = KuaishouUserGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
