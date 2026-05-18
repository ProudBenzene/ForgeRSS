#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Douyin (抖音) User Video Feed Generator.

Configuration:
1. Environment variable DOUYIN_SEC_UID (comma-separated for multiple users).
   Accepts THREE input forms — pick whichever is easiest:
     - pure sec_uid:    "MS4wLjABAAAA..."
     - desktop URL:     "https://www.douyin.com/user/MS4wLjABAAAA...?from_tab_name=..."
     - share short URL: "https://v.douyin.com/<code>/"  (auto-follows redirect)
   (Legacy `DOUYIN_USER_ID` is still accepted as an alias.)

2. Optional video download (default off):
     DOUYIN_DOWNLOAD_VIDEOS=true
   Uses yt-dlp; videos go to downloads/douyin/<sec_uid>/<video_id>.mp4

Example:
    DOUYIN_SEC_UID="MS4wLjABAAAAxxxx" python scripts/run_single.py douyin_user
"""

import hashlib
import json
import logging
import os
import random
import re
import time
from collections import OrderedDict
from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from typing import Optional

import pytz
from bs4 import BeautifulSoup

from generators.base import Article, BaseFeedGenerator
from generators.social.douyin.scraper import (
    check_douyin_ready,
    create_douyin_browser,
    DOUYIN_PROFILE_DIR,
)

CN_TZ = pytz.timezone("Asia/Shanghai")

# Image-post (note) photos sit under a stable URL marker. Related-post thumbnails
# use a different `tplv-dy-resize-*` token, so this filter is precise.
NOTE_IMG_MARKER = "tplv-dy-aweme-images"

logger = logging.getLogger(__name__)

# downloads/douyin/ (project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DOWNLOAD_DIR = PROJECT_ROOT / "downloads" / "douyin"


def _extract_note_metadata(html: str) -> tuple[str, Optional[datetime]]:
    """Pull desc + createTime out of the React Server Components stream.

    Douyin's note pages embed `aweme.detail` inside one of the
    `self.__pace_f.push([1,"<payload>"])` calls. We walk every push, decode the
    payload's JS string escapes via json.loads, then regex out the two fields
    we care about.
    """
    unescaped = ""
    for m in re.finditer(r'self\.__pace_f\.push\(\[1,"', html):
        i = m.end()
        out = []
        esc = False
        while i < len(html):
            c = html[i]
            if esc:
                out.append(c)
                esc = False
            elif c == "\\":
                out.append(c)
                esc = True
            elif c == '"':
                break
            else:
                out.append(c)
            i += 1
        raw = "".join(out)
        try:
            decoded = json.loads(f'"{raw}"')
        except Exception:
            decoded = raw.replace('\\"', '"').replace('\\\\', '\\')
        if '"desc":' in decoded and '"createTime":' in decoded and len(decoded) > len(unescaped):
            unescaped = decoded
    if not unescaped:
        return "", None

    desc = ""
    m_desc = re.search(r'"desc":"((?:[^"\\]|\\.)*)"', unescaped)
    if m_desc:
        raw_desc = m_desc.group(1)
        try:
            desc = json.loads(f'"{raw_desc}"')
        except Exception:
            desc = raw_desc

    create_time = None
    m_ct = re.search(r'"createTime":(\d+)', unescaped)
    if m_ct:
        ts = int(m_ct.group(1))
        if 10**9 < ts < 10**11:
            create_time = datetime.fromtimestamp(ts, tz=CN_TZ)

    return desc, create_time


def _extract_note_images(soup: BeautifulSoup) -> list[str]:
    """Return the gallery photos in DOM order, deduped by Douyin image hash.

    Filter: URL must contain `tplv-dy-aweme-images` (note-main-image marker;
    related-post thumbnails use `tplv-dy-resize-origshort-*` and are excluded).
    """
    seen = OrderedDict()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or NOTE_IMG_MARKER not in src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        m = re.search(r"/tos-cn-i-[^/]+/([A-Za-z0-9]+)", src)
        key = m.group(1) if m else src
        if key not in seen:
            seen[key] = src
    return list(seen.values())


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

    # Read DOUYIN_SEC_UID (preferred) or DOUYIN_USER_ID (legacy alias).
    USER_INPUTS = [
        u.strip()
        for u in (os.environ.get("DOUYIN_SEC_UID") or os.environ.get("DOUYIN_USER_ID") or "").split(",")
        if u.strip()
    ]

    # Per-user fetch cap (defaults to 20). Run-level --max N overrides this.
    MAX_VIDEOS = int(os.environ.get("DOUYIN_MAX_VIDEOS", "20"))

    # Whether to download videos as mp4 (default: false, RSS only).
    DOWNLOAD_VIDEOS = os.environ.get("DOUYIN_DOWNLOAD_VIDEOS", "false").lower() == "true"

    # Whether to download image-post photos as jpeg (default: false).
    DOWNLOAD_IMAGES = os.environ.get("DOUYIN_DOWNLOAD_IMAGES", "false").lower() == "true"

    def __init__(self):
        super().__init__()

        if not self.USER_INPUTS:
            self.logger.warning("No users configured. Set DOUYIN_SEC_UID environment variable.")
            self.logger.warning(
                "Example: DOUYIN_SEC_UID='MS4wLjABAAAAxxxx' "
                "or full URL 'https://www.douyin.com/user/MS4wLjABAAAA...' "
                "or short URL 'https://v.douyin.com/xxx/'"
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

            self.logger.info(f"Found {len(video_items)} post cards on page")

            # Phase 1: pull card-level info (href / type / list title / thumbnail).
            # We don't build Articles yet because note posts need a detail-page
            # visit, which would invalidate the surrounding list-item handles.
            cards = []
            for item in video_items:
                if len(cards) >= max_videos:
                    break
                try:
                    info = self._extract_card_info(item)
                    if info:
                        cards.append(info)
                except Exception as e:
                    self.logger.debug(f"Card extraction failed: {e}")
                    continue
            self.logger.info(
                f"Card mix: {sum(1 for c in cards if c['aweme_type']=='video')} videos, "
                f"{sum(1 for c in cards if c['aweme_type']=='note')} notes"
            )

            # Phase 2: build Articles. Videos are list-only (no detail visit);
            # notes navigate to the detail page to pull the 9-photo gallery + desc.
            for info in cards:
                try:
                    if info["aweme_type"] == "note":
                        article = self._build_note_article(
                            browser, info, sec_uid, author_name
                        )
                    else:
                        article = self._build_video_article(info, sec_uid, author_name)
                    if article:
                        articles.append(article)
                except Exception as e:
                    self.logger.debug(f"Article build failed for {info.get('href')}: {e}")
                    continue

            # Download media if enabled. Done after parsing so we only fetch
            # what made the cut.
            if self.DOWNLOAD_VIDEOS:
                for art in articles:
                    if "/video/" in art.url:
                        self._download_video(art.url, sec_uid, browser=browser)
            if self.DOWNLOAD_IMAGES:
                for art in articles:
                    if "/note/" in art.url:
                        self._download_note_images(art, sec_uid)

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
        """Scroll the profile page until we have enough post cards (or give up).

        Counts both /video/<id> (regular videos) and /note/<id> (image posts).
        """
        max_scrolls = 8
        no_change = 0
        prev_count = 0
        for i in range(max_scrolls):
            browser.scroll.to_bottom()
            browser.wait(2)
            try:
                links = browser.eles('tag:a', timeout=1)
                cnt = sum(
                    1 for a in links
                    if re.search(r'/(?:video|note)/', a.attr('href') or '')
                )
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

    def _find_video_items(self, browser) -> list:
        """Try several CSS selectors to locate post cards (videos + notes)."""
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
        # Last resort: every <a href="/video/..."> or /note/ on the page
        try:
            links = browser.eles('tag:a', timeout=1)
            return [
                a for a in links
                if re.search(r'/(?:video|note)/', a.attr('href') or '')
            ]
        except Exception:
            return []

    def _extract_card_info(self, item) -> Optional[dict]:
        """Return a card descriptor: aweme_type / href / id / list title / cover.

        Detail-page enrichment (notes) and Article construction (both types)
        happens later — this method only reads the list-item DOM.
        """
        if item.tag == 'a':
            link_elem = item
        else:
            link_elem = None
            for a in (item.eles('tag:a', timeout=0.5) or []):
                href = a.attr('href') or ''
                if re.search(r'/(?:video|note)/', href):
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

        m = re.search(r'/(video|note)/(\d+)', href)
        if not m:
            return None
        aweme_type, aweme_id = m.group(1), m.group(2)

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
            try:
                img = item.ele('tag:img', timeout=0.3)
                if img:
                    alt = (img.attr('alt') or "").strip()
                    if alt:
                        title = alt
            except Exception:
                pass

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

        return {
            "href": href,
            "aweme_type": aweme_type,
            "aweme_id": aweme_id,
            "list_title": title or f"{aweme_type}_{aweme_id}",
            "thumbnail": thumbnail,
        }

    def _build_video_article(
        self, info: dict, sec_uid: str, author_name: str
    ) -> Article:
        """Build an Article from a list-only video card (no detail-page visit)."""
        href = info["href"]
        title = info["list_title"]
        thumbnail = info["thumbnail"]
        pub_date = datetime.now(CN_TZ)

        html_parts = [
            f'<div style="font-size:16px;line-height:1.8;color:#333">',
            f'<p><strong>作者：</strong>{html_escape(author_name)}</p>',
        ]
        if thumbnail:
            html_parts.append(
                f'<p><a href="{html_escape(href)}"><img src="{html_escape(thumbnail)}" '
                f'alt="{html_escape(title)}" '
                f'style="max-width:100%;height:auto;border-radius:8px" /></a></p>'
            )
        html_parts.append(f'<p>{html_escape(title)}</p>')
        html_parts.append(
            f'<p style="margin-top:12px"><a href="{html_escape(href)}" '
            f'style="color:#fe2c55">查看原视频 &rarr;</a></p>'
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
            category="抖音",
        )

    def _build_note_article(
        self, browser, info: dict, sec_uid: str, author_name: str
    ) -> Optional[Article]:
        """Open the note detail page, pull desc + 9 gallery photos, build Article."""
        href = info["href"]
        self.logger.info(f"Note detail: {href}")
        try:
            browser.get(href)
        except Exception as e:
            self.logger.warning(f"Failed to open note {href}: {e}")
            return None
        browser.wait(random.uniform(3, 5))

        html = browser.html
        if not html or "扫码登录" in html or "登录抖音" in html:
            self.logger.warning(f"Note detail blocked by login: {href}")
            return None

        soup = BeautifulSoup(html, "html.parser")

        title_text = ""
        t = soup.find("title")
        if t and t.text:
            title_text = re.sub(r"\s*-\s*抖音\s*$", "", t.text).strip()

        desc, create_time = _extract_note_metadata(html)
        if not title_text:
            title_text = (desc[:50] + ("…" if len(desc) > 50 else "")) if desc else info["list_title"]

        images = _extract_note_images(soup)
        if not images and info.get("thumbnail"):
            images = [info["thumbnail"]]
        self.logger.info(f"Note {info['aweme_id']}: {len(images)} photos, desc {len(desc)} chars")

        pub_date = create_time or datetime.now(CN_TZ)

        body = [f'<div style="font-size:16px;line-height:1.8;color:#333">']
        body.append(
            f'<p style="color:#888;font-size:13px">'
            f'<strong>作者：</strong>{html_escape(author_name)} · 图文笔记 · {len(images)} 张</p>'
        )
        for src in images:
            body.append(
                f'<p><img src="{html_escape(src)}" '
                f'style="max-width:100%;height:auto;border-radius:8px;margin:6px 0" /></p>'
            )
        if desc:
            body.append(
                f'<div style="margin-top:12px;white-space:pre-wrap">{html_escape(desc)}</div>'
            )
        body.append(
            f'<p style="margin-top:16px"><a href="{html_escape(href)}" '
            f'style="color:#fe2c55">在抖音查看 &rarr;</a></p>'
        )
        body.append('</div>')

        return Article(
            url=href,
            title=f"[{author_name}] {title_text}",
            published_at=pub_date,
            content='\n'.join(body),
            summary=(desc or title_text)[:280],
            author=author_name,
            images=images,
            category="抖音",
        )

    def _download_note_images(self, article: Article, sec_uid: str) -> None:
        """Download every photo from a note Article to downloads/douyin/<sec_uid>/notes/<id>/."""
        if not article.images:
            return
        try:
            from curl_cffi import requests as _creq
        except ImportError:
            self.logger.error("curl_cffi not installed; cannot download note images")
            return

        m = re.search(r'/note/(\d+)', article.url)
        if not m:
            return
        note_id = m.group(1)
        out_dir = DOWNLOAD_DIR / sec_uid[:24] / "notes" / note_id
        out_dir.mkdir(parents=True, exist_ok=True)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": article.url,
        }
        for idx, src in enumerate(article.images, 1):
            ext = ".jpg"
            sl = src.lower()
            if ".webp" in sl:
                ext = ".webp"
            elif ".png" in sl:
                ext = ".png"
            dest = out_dir / f"{idx:02d}{ext}"
            if dest.exists() and dest.stat().st_size > 0:
                continue
            r = None
            try:
                r = _creq.get(src, headers=headers, impersonate="chrome",
                              timeout=60, stream=True)
                if r.status_code != 200:
                    self.logger.warning(f"img {idx} HTTP {r.status_code}")
                    continue
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            f.write(chunk)
            except Exception as e:
                self.logger.warning(f"img {idx} download failed: {e}")
            finally:
                if r is not None:
                    try: r.close()
                    except Exception: pass
        self.logger.info(f"Note {note_id} photos -> {out_dir}")

    def _download_video(self, video_page_url: str, sec_uid: str, browser=None) -> Optional[Path]:
        """Download a Douyin video.

        Douyin web serves DASH-style separated streams (video + audio) over
        douyinvod.com CDN. The URLs are not in the page HTML — they're issued
        by the player JS. We capture them via CDP network listening, then
        download each stream fully (each URL returns a complete mp4) and mux
        them with ffmpeg.

        Why not yt-dlp: its Douyin extractor relies on the legacy
        /aweme/v1/web/aweme/detail/ API, which now requires JS-generated
        msToken / X-Bogus / _signature query params and returns HTTP 200 with
        empty body otherwise.
        """
        if not browser:
            self.logger.warning("No browser provided — cannot download douyin video")
            return None

        m = re.search(r'/video/(\d+)', video_page_url)
        if not m:
            self.logger.debug(f"Cannot extract video id from {video_page_url}")
            return None
        video_id = m.group(1)

        out_dir = DOWNLOAD_DIR / sec_uid[:24]
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{video_id}.mp4"

        if out_path.exists() and out_path.stat().st_size > 0:
            self.logger.info(f"Already downloaded: {out_path.name}")
            return out_path

        # 1. Render video page + listen for stream URLs from douyinvod.com
        try:
            browser.listen.start()
            self.logger.info(f"Rendering video page {video_page_url[:80]} ...")
            browser.get(video_page_url)
            time.sleep(10)  # let the player fetch initial chunks
        except Exception as e:
            self.logger.error(f"Failed to load video page: {e}")
            try: browser.listen.stop()
            except Exception: pass
            return None

        video_stream_url, audio_stream_url = None, None
        try:
            for pkt in browser.listen.steps(count=999, timeout=2):
                url = pkt.url
                if "douyinvod.com" not in url:
                    continue
                if "media-video" in url and not video_stream_url:
                    video_stream_url = url
                elif "media-audio" in url and not audio_stream_url:
                    audio_stream_url = url
                if video_stream_url and audio_stream_url:
                    break
        finally:
            try: browser.listen.stop()
            except Exception: pass

        if not video_stream_url:
            self.logger.error(f"No douyinvod.com video stream captured for {video_id}")
            return None
        self.logger.info(f"Got video stream URL ({video_stream_url[:80]}...)")
        if audio_stream_url:
            self.logger.info(f"Got audio stream URL ({audio_stream_url[:80]}...)")
        else:
            self.logger.warning("No audio stream captured — output will be silent")

        # 2. Download both streams with browser-grade TLS + cookies
        try:
            from curl_cffi import requests as _creq
        except ImportError:
            self.logger.error("curl_cffi not installed; cannot download")
            return None

        cookies = browser.cookies(all_domains=True)
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get('name'))
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": video_page_url,
            "Cookie": cookie_header,
        }

        video_tmp = out_dir / f".{video_id}.video.mp4"
        if not self._curl_download(_creq, video_stream_url, headers, video_tmp):
            return None

        audio_tmp = None
        if audio_stream_url:
            audio_tmp = out_dir / f".{video_id}.audio.mp4"
            if not self._curl_download(_creq, audio_stream_url, headers, audio_tmp):
                audio_tmp = None  # proceed video-only

        # 3. Mux with ffmpeg if both streams present
        if audio_tmp:
            if self._ffmpeg_mux(video_tmp, audio_tmp, out_path):
                video_tmp.unlink(missing_ok=True)
                audio_tmp.unlink(missing_ok=True)
                size_mb = out_path.stat().st_size / (1024 * 1024)
                self.logger.info(f"Downloaded + muxed: {out_path.name} ({size_mb:.1f} MB)")
                return out_path
            else:
                # ffmpeg missing or failed — keep raw streams as fallback
                self.logger.warning(
                    f"ffmpeg mux failed; keeping raw streams {video_tmp.name} + {audio_tmp.name}"
                )
                return video_tmp
        else:
            # Video-only (no audio): rename .video.mp4 → final name
            video_tmp.rename(out_path)
            size_mb = out_path.stat().st_size / (1024 * 1024)
            self.logger.info(f"Downloaded (video only): {out_path.name} ({size_mb:.1f} MB)")
            return out_path

    def _curl_download(self, _creq, url: str, headers: dict, dest: Path) -> bool:
        """Stream-download a URL via curl_cffi with chrome TLS fingerprint.

        Note: curl_cffi's Response is NOT a context manager (unlike `requests`),
        so we close it manually.
        """
        r = None
        try:
            self.logger.info(f"Downloading -> {dest.name} ...")
            r = _creq.get(url, headers=headers, impersonate="chrome",
                          timeout=180, stream=True)
            if r.status_code != 200:
                self.logger.error(f"HTTP {r.status_code} for {dest.name}")
                return False
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
            size_mb = dest.stat().st_size / (1024 * 1024)
            if dest.stat().st_size < 10_000:
                self.logger.error(f"Downloaded {dest.name} too small ({size_mb:.2f} MB)")
                dest.unlink(missing_ok=True)
                return False
            self.logger.info(f"  -> {dest.name} ({size_mb:.1f} MB)")
            return True
        except Exception as e:
            self.logger.error(f"Download of {dest.name} failed: {e}")
            return False
        finally:
            if r is not None:
                try: r.close()
                except Exception: pass

    @staticmethod
    def _ffmpeg_mux(video_in: Path, audio_in: Path, mp4_out: Path) -> bool:
        """Mux a video stream and an audio stream into one mp4 via ffmpeg.

        Returns False if ffmpeg is missing or fails — caller should keep the
        raw streams as a fallback so user can mux manually.
        """
        import shutil, subprocess
        if shutil.which("ffmpeg") is None:
            return False
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_in),
            "-i", str(audio_in),
            "-c", "copy",
            str(mp4_out),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120)
            return r.returncode == 0 and mp4_out.exists() and mp4_out.stat().st_size > 0
        except Exception:
            return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate Douyin User RSS")
    parser.add_argument("--max", type=int, default=20, help="Max videos per user")
    parser.add_argument("--full", action="store_true", help="Full refresh")
    args = parser.parse_args()
    gen = DouyinUserGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
