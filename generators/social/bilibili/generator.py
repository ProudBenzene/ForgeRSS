#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Bilibili UP Master Video Feed Generator.

Configuration:
1. Environment variable: BILIBILI_UP_MID (comma-separated UP master IDs)
2. Or set UP_MIDS list in code

Example:
    BILIBILI_UP_MID="12345678,87654321" python scripts/run_single.py bilibili_up
"""

import logging
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import pytz

from generators.base import Article, BaseFeedGenerator
from generators.social.bilibili.scraper import (
    create_bilibili_browser,
    check_bilibili_ready,
    download_video,
    verify_bilibili_login,
)

logger = logging.getLogger(__name__)


def _positive_int_env(name: str, default: int) -> int:
    """Read a strictly positive integer environment option."""
    value = os.environ.get(name, str(default))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero, got {parsed}")
    return parsed


def _nonnegative_float_env(name: str, default: float) -> float:
    """Read a non-negative floating-point environment option."""
    value = os.environ.get(name, str(default))
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"{name} must not be negative, got {parsed}")
    return parsed


def _parse_bilibili_publish_time(
    text: str, now: Optional[datetime] = None
) -> datetime:
    """Parse the compact publish time shown on Bilibili space video cards."""
    local_tz = pytz.timezone("Asia/Shanghai")
    now = now or datetime.now(local_tz)
    if now.tzinfo is None:
        now = local_tz.localize(now)
    else:
        now = now.astimezone(local_tz)

    value = (text or "").strip()
    try:
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", value):
            parsed = datetime.strptime(value, "%Y-%m-%d")
            return local_tz.localize(parsed).astimezone(pytz.UTC)

        if re.fullmatch(r"\d{1,2}-\d{1,2}", value):
            month, day = (int(part) for part in value.split("-"))
            parsed = local_tz.localize(datetime(now.year, month, day))
            # A month/day later than today belongs to the previous year.
            if parsed > now + timedelta(days=1):
                parsed = local_tz.localize(datetime(now.year - 1, month, day))
            return parsed.astimezone(pytz.UTC)

        if value in ("刚刚", "刚才"):
            return now.astimezone(pytz.UTC)
        if value == "昨天":
            return (now - timedelta(days=1)).astimezone(pytz.UTC)

        relative_patterns = (
            (r"(\d+)分钟前", "minutes"),
            (r"(\d+)小时前", "hours"),
            (r"(\d+)天前", "days"),
        )
        for pattern, unit in relative_patterns:
            match = re.fullmatch(pattern, value)
            if match:
                return (now - timedelta(**{unit: int(match.group(1))})).astimezone(pytz.UTC)
    except (TypeError, ValueError):
        logger.warning("Could not parse Bilibili publish time: %r", value)

    return now.astimezone(pytz.UTC)


class BilibiliUPGenerator(BaseFeedGenerator):
    """RSS generator for Bilibili UP Master videos."""
    
    FEED_NAME = "bilibili_up"
    FEED_TITLE = "Bilibili UP Master"
    FEED_URL = "https://www.bilibili.com/"
    FEED_DESCRIPTION = "Bilibili UP Master - Video Updates"
    FEED_LANGUAGE = "zh-CN"
    FEED_LOGO = "https://www.bilibili.com/favicon.ico"
    
    def __init__(
        self,
        history_mode: Optional[bool] = None,
        mids: Optional[list[str]] = None,
        base_dir: Optional[Path] = None,
    ):
        super().__init__(base_dir=base_dir)

        configured_mids = (
            mids
            if mids is not None
            else os.environ.get("BILIBILI_UP_MID", "").split(",")
        )
        self.UP_MIDS = self._normalize_mids(configured_mids)
        self.DOWNLOAD_VIDEOS = (
            os.environ.get("BILIBILI_DOWNLOAD_VIDEOS", "false").lower()
            == "true"
        )
        configured_history_mode = (
            os.environ.get("BILIBILI_HISTORY_MODE", "false").lower() == "true"
        )
        self.HISTORY_MODE = (
            configured_history_mode if history_mode is None else history_mode
        )
        self.MAX_VIDEOS_HISTORY = _positive_int_env(
            "BILIBILI_MAX_VIDEOS_HISTORY", 100
        )
        self.MAX_VIDEOS_DAILY = _positive_int_env(
            "BILIBILI_MAX_VIDEOS_DAILY", 20
        )
        self.UP_DELAY_SECONDS = _nonnegative_float_env(
            "BILIBILI_UP_DELAY_SECONDS", 5
        )
        self.LEGACY_FEED_MID = os.environ.get(
            "BILIBILI_LEGACY_FEED_MID", ""
        ).strip()

        if not self.UP_MIDS:
            self.logger.warning(
                "No UP master configured. Set BILIBILI_UP_MID environment variable."
            )
            self.logger.warning("Example: BILIBILI_UP_MID='12345678,87654321'")

    @staticmethod
    def _normalize_mids(mids: list[str]) -> list[str]:
        """Validate and deduplicate Bilibili MIDs while preserving order."""
        normalized = []
        seen = set()
        for raw_mid in mids:
            mid = str(raw_mid).strip()
            if not mid:
                continue
            if not mid.isdigit():
                raise ValueError(f"Invalid Bilibili MID (digits only): {mid!r}")
            if mid not in seen:
                normalized.append(mid)
                seen.add(mid)
        return normalized

    def _max_videos_for_run(self) -> int:
        if self.HISTORY_MODE:
            max_videos = self.MAX_VIDEOS_HISTORY
            self.logger.info(
                "History mode: fetching up to %s videos per UP", max_videos
            )
        else:
            max_videos = self.MAX_VIDEOS_DAILY
            self.logger.info(
                "Daily mode: fetching latest %s videos per UP", max_videos
            )

        run_cap = getattr(self, "_run_max_articles", None)
        if run_cap is not None and run_cap < max_videos:
            self.logger.info(
                "Run cap (--max %s) overrides per-UP limit %s",
                run_cap,
                max_videos,
            )
            max_videos = run_cap
        return max_videos

    def _store_mid_feed(
        self,
        mid: str,
        up_name: str,
        new_articles: list[Article],
        full_refresh: bool,
        max_articles: int,
        use_db: bool,
    ) -> Path:
        """Persist one UP master in an isolated cache, DB namespace and XML."""
        original_metadata = (
            self.FEED_NAME,
            self.FEED_TITLE,
            self.FEED_URL,
            self.FEED_DESCRIPTION,
        )
        self.FEED_NAME = f"bilibili_up_{mid}"
        self.FEED_TITLE = f"{up_name} 的 Bilibili 投稿"
        self.FEED_URL = f"https://space.bilibili.com/{mid}/video"
        self.FEED_DESCRIPTION = f"Bilibili UP 主 {up_name} 的投稿视频更新"

        try:
            existing = [] if full_refresh else self.load_cache()
            if not existing and not full_refresh and use_db:
                existing = self.load_from_db(limit=max_articles)

            merged = self.merge_articles(new_articles, existing)
            final = merged[:max_articles]
            self.save_cache(final)
            if use_db:
                self.save_to_db(final)
            output = self.save_feed_streaming(final)
            output.chmod(0o644)
            return output
        finally:
            (
                self.FEED_NAME,
                self.FEED_TITLE,
                self.FEED_URL,
                self.FEED_DESCRIPTION,
            ) = original_metadata

    def _write_legacy_alias(self, mid: str, source: Path) -> Path:
        """Keep the original single-feed URL working during migration."""
        target = self.feeds_dir / "feed_bilibili_up.xml"
        temporary = self.feeds_dir / ".feed_bilibili_up.xml.tmp"
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
        target.chmod(0o644)
        self.logger.info("Updated legacy feed alias for MID %s: %s", mid, target)
        return target

    def run(
        self,
        full_refresh: bool = False,
        max_articles: int = 50,
        use_db: bool = True,
    ) -> bool:
        """Update one isolated feed per MID using a shared browser session."""
        if not self.UP_MIDS:
            return False
        if max_articles <= 0:
            raise ValueError("max_articles must be greater than zero")

        ready, message = check_bilibili_ready()
        if not ready:
            self.logger.error(message)
            return False

        browser = create_bilibili_browser(headless=False)
        if not browser:
            return False

        self._run_max_articles = max_articles
        outputs = {}
        failures = []

        try:
            if not verify_bilibili_login(browser):
                self.logger.error("Bilibili login is missing or expired")
                return False

            max_videos = self._max_videos_for_run()
            for index, mid in enumerate(self.UP_MIDS):
                try:
                    self.logger.info("Fetching videos from UP master %s", mid)
                    up_name, videos = self._fetch_up_videos(
                        browser,
                        mid,
                        max_videos=max_videos,
                        history_mode=self.HISTORY_MODE,
                    )
                    if not videos:
                        raise RuntimeError(
                            "No videos parsed; existing feed was preserved"
                        )
                    outputs[mid] = self._store_mid_feed(
                        mid,
                        up_name,
                        videos,
                        full_refresh=full_refresh,
                        max_articles=max_articles,
                        use_db=use_db,
                    )
                    self.logger.info(
                        "Updated independent feed for %s (%s videos)",
                        mid,
                        len(videos),
                    )
                except Exception as exc:
                    failures.append(mid)
                    self.logger.error(
                        "Failed to update independent feed for %s: %s",
                        mid,
                        exc,
                        exc_info=True,
                    )

                if index < len(self.UP_MIDS) - 1 and self.UP_DELAY_SECONDS:
                    self.logger.info(
                        "Waiting %.1f seconds before the next UP master",
                        self.UP_DELAY_SECONDS,
                    )
                    browser.wait(self.UP_DELAY_SECONDS)
        finally:
            browser.quit()

        legacy_mid = self.LEGACY_FEED_MID
        if not legacy_mid and len(self.UP_MIDS) == 1:
            legacy_mid = self.UP_MIDS[0]
        if legacy_mid:
            source = outputs.get(legacy_mid)
            if source:
                self._write_legacy_alias(legacy_mid, source)
            elif legacy_mid in self.UP_MIDS:
                failures.append(legacy_mid)
                self.logger.error(
                    "Could not update legacy alias because MID %s failed",
                    legacy_mid,
                )
            else:
                failures.append(legacy_mid)
                self.logger.error(
                    "BILIBILI_LEGACY_FEED_MID=%s is not in BILIBILI_UP_MID",
                    legacy_mid,
                )

        if failures:
            self.logger.error(
                "Bilibili batch finished with failures: %s",
                ", ".join(dict.fromkeys(failures)),
            )
            return False
        return len(outputs) == len(self.UP_MIDS)

    def fetch_articles(self) -> list[Article]:
        """Fetch all configured UPs as an aggregate for API compatibility."""
        ready, msg = check_bilibili_ready()
        if not ready:
            self.logger.error(msg)
            return []
        
        browser = create_bilibili_browser(headless=False)
        if not browser:
            return []
        
        articles = []
        
        try:
            if not verify_bilibili_login(browser):
                raise RuntimeError("Bilibili login is missing or expired")

            max_videos = self._max_videos_for_run()
            
            for index, mid in enumerate(self.UP_MIDS):
                try:
                    self.logger.info(f"Fetching videos from UP master {mid}")
                    _up_name, videos = self._fetch_up_videos(
                        browser,
                        mid,
                        max_videos=max_videos,
                        history_mode=self.HISTORY_MODE,
                    )
                    articles.extend(videos)
                    self.logger.info(
                        f"Found {len(videos)} videos from UP master {mid}"
                    )
                except Exception as exc:
                    self.logger.error(
                        "Failed to fetch UP master %s: %s", mid, exc
                    )

                if index < len(self.UP_MIDS) - 1 and self.UP_DELAY_SECONDS:
                    browser.wait(self.UP_DELAY_SECONDS)
        finally:
            browser.quit()
        
        return articles
    
    def _fetch_up_videos(
        self, 
        browser, 
        mid: str, 
        max_videos: int = 20,
        history_mode: bool = False
    ) -> tuple[str, list[Article]]:
        """
        Fetch videos from a single UP master using browser with login state.
        
        Args:
            browser: DrissionPage browser instance
            mid: UP master ID
            max_videos: Maximum number of videos to fetch
            history_mode: History mode
                - False (default): Daily mode, fetch latest max_videos only
                - True: History mode, fetch as many historical videos as possible
        """
        articles = []
        up_name = f"UP{mid}"
        
        try:
            # Visit UP master space video page
            url = f"https://space.bilibili.com/{mid}/video"
            browser.get(url)
            browser.wait(5)  # Wait for page load
            
            # Get UP master name
            up_name = self._get_up_name(browser) or up_name
            self.logger.info(f"UP master name: {up_name}")
            
            # Scroll to load more videos (smart scroll strategy)
            previous_count = 0
            max_scrolls = 30  # Max 30 scrolls
            no_change_count = 0  # Consecutive no-change count
            
            self.logger.info(f"Starting to scroll, target: {max_videos} videos")
            
            for i in range(max_scrolls):
                browser.scroll.to_bottom()
                browser.wait(2)  # Wait for lazy load
                
                # Check current video count
                current_links = browser.eles('tag:a')
                current_count = len([a for a in current_links if '/video/' in (a.attr('href') or '')])
                
                # Strategy 1: Reached target count
                if current_count >= max_videos * 2:  # Leave some margin
                    self.logger.info(f"Reached target ({current_count} >= {max_videos}*2), stopping scroll")
                    break
                
                # Strategy 2: Check for "no more" indicator
                no_more_elem = browser.ele('text:没有更多了', timeout=0.5)
                if no_more_elem:
                    self.logger.info("Detected no more content, stopping scroll")
                    break
                
                # Strategy 3: Consecutive no change
                if current_count == previous_count:
                    no_change_count += 1
                    self.logger.debug(f"Scroll {i+1}: no change ({no_change_count}/3)")
                    if no_change_count >= 3:  # 3 consecutive no-change, stop
                        self.logger.info(f"No new videos after 3 attempts, stopping scroll")
                        break
                else:
                    no_change_count = 0  # Reset counter
                    new_count = current_count - previous_count
                    self.logger.info(f"Scroll {i+1}: {current_count} videos (+{new_count})")
                
                previous_count = current_count
            
            # Final stats
            self.logger.info(f"Scroll completed: found {current_count} video links in total")
            
            # Get all video links
            all_links = browser.eles('tag:a')
            video_links = [a for a in all_links if '/video/' in (a.attr('href') or '')]
            self.logger.info(f"Total found {len(video_links)} video links on page")
            
            # Try multiple selectors to find video cards.
            # As of 2026-05 the B站 space page uses the new layout below; older
            # selectors are kept as fallbacks in case of A/B rollouts.
            video_selectors = [
                'css:.upload-video-card',     # Current (2026-05): wraps each card
                'css:.bili-video-card',       # Inner card container
                'css:li.small-item',          # Legacy
                'css:.small-item',            # Legacy
                'css:.list-list .list-item',  # Legacy
                'css:.video-list li',         # Legacy generic
            ]
            
            video_items = []
            for selector in video_selectors:
                try:
                    items = browser.eles(selector, timeout=2)
                    self.logger.info(f"Trying selector: {selector}, found {len(items)} items")
                    if items and len(items) > 0:
                        video_items = items
                        self.logger.info(f"Using selector: {selector}")
                        break
                except Exception as e:
                    self.logger.warning(f"Selector {selector} failed: {e}")
                    continue
            
            # If still not found, use direct video links
            if not video_items and video_links:
                self.logger.info(f"Falling back to direct video links")
                video_items = video_links[:max_videos]
            
            if not video_items:
                self.logger.warning(f"No videos found with any selector for UP master {mid}")
                return up_name, []
            
            # Parse videos
            parsed_count = 0
            for item in video_items:
                if parsed_count >= max_videos:
                    break
                try:
                    article = self._parse_video_item_browser(item, up_name, mid, browser)
                    if article:
                        articles.append(article)
                        parsed_count += 1
                except Exception as e:
                    self.logger.error(f"Error parsing video item: {e}")
                    continue
            
            # If parsing failed, try direct video links fallback
            if len(articles) == 0 and video_links:
                self.logger.info(f"Parse failed, falling back to direct video links ({len(video_links)} links)")
                for link in video_links[:max_videos]:
                    try:
                        article = self._parse_video_item_browser(link, up_name, mid, browser)
                        if article:
                            articles.append(article)
                    except Exception as e:
                        self.logger.error(f"Error parsing video link: {e}")
                        continue
        
        except Exception as e:
            self.logger.error(f"Error fetching videos from UP master {mid}: {e}")
            raise
        
        return up_name, articles
    
    def _get_up_name(self, browser) -> Optional[str]:
        """Get UP master name from page."""
        try:
            selectors = [
                'css:#h-name',
                'css:.h-name',
                'css:.username',
                'css:.nickname',
                'css:.user-name',
            ]
            for selector in selectors:
                name_elem = browser.ele(selector, timeout=2)
                if name_elem:
                    text = name_elem.text.strip()
                    if text:
                        return text

            # The current space page title is "<UP name>投稿视频-...".
            page_title = (browser.title or '').strip()
            match = re.match(r'(.+?)投稿视频(?:-|$)', page_title)
            if match:
                return match.group(1).strip()
        except Exception as exc:
            self.logger.debug("Failed to resolve UP master name: %s", exc)
        return None
    
    def _parse_video_item_browser(self, item, up_name: str, mid: str, browser=None) -> Optional[Article]:
        """Parse a single video item from browser."""
        try:
            # Find the anchor that points to /video/. Either the item itself is
            # an <a>, or we look inside it for any <a> with /video/ in href.
            if item.tag == 'a':
                link_elem = item
            else:
                link_elem = None
                for cand in item.eles('tag:a', timeout=1) or []:
                    href = cand.attr('href') or ''
                    if '/video/' in href:
                        link_elem = cand
                        break
                if not link_elem:
                    link_elem = item.ele('tag:a', timeout=1)
                if not link_elem:
                    return None

            video_url = link_elem.attr('href')
            if not video_url:
                return None

            if video_url.startswith('//'):
                video_url = 'https:' + video_url
            elif video_url.startswith('/'):
                video_url = 'https://www.bilibili.com' + video_url

            bv_match = re.search(r'BV[a-zA-Z0-9]+', video_url)
            av_match = re.search(r'av(\d+)', video_url)
            if bv_match:
                video_id = bv_match.group(0)
            elif av_match:
                video_id = f"av{av_match.group(1)}"
            else:
                return None

            # Title resolution ordered from most specific to most generic.
            # New B站 layout (2026-05) uses .bili-video-card__title which has
            # both a `title` attribute and inner anchor text.
            title = None

            def _from_card_title(scope):
                el = scope.ele('css:.bili-video-card__title', timeout=0.5)
                if not el:
                    return None
                t = el.attr('title')
                if t and t.strip() and t.strip() != '充电专属':
                    return t.strip()
                t = el.text.strip() if el.text else ''
                return t or None

            # 1. Look inside the item for .bili-video-card__title
            if item.tag != 'a':
                title = _from_card_title(item)

            # 2. From the link's `title` attribute (e.g. <a title="...">)
            if not title or title in ('', '充电专属'):
                title = (link_elem.attr('title') or '').strip() or None

            # 3. From the cover <img alt="..."> (new layout exposes it here)
            if not title or title in ('', '充电专属'):
                scope = item if item.tag != 'a' else link_elem
                img = scope.ele('css:.bili-cover-card__thumbnail img', timeout=0.5)
                if not img:
                    img = scope.ele('tag:img', timeout=0.5)
                if img:
                    alt = (img.attr('alt') or '').strip()
                    if alt:
                        title = alt

            # 4. aria-label on the link
            if not title or title in ('', '充电专属'):
                title = (link_elem.attr('aria-label') or '').strip() or None

            # 5. Legacy fallback: .title in parent or item
            if not title or title in ('', '充电专属'):
                parent = link_elem.parent()
                if parent:
                    legacy = parent.ele('css:.title', timeout=0.3)
                    if legacy:
                        title = (legacy.attr('title') or legacy.text or '').strip() or None
            if (not title or title in ('', '充电专属')) and item.tag != 'a':
                legacy = item.ele('css:.title', timeout=0.3)
                if legacy:
                    title = (legacy.attr('title') or legacy.text or '').strip() or None
            
            # Check if paid content
            is_paid = False
            item_html = item.html if hasattr(item, 'html') else ''
            parent_html = link_elem.parent().html if link_elem.parent() else ''
            is_paid = ('充电观看' in item_html or '充电专属' in item_html or 
                      '充电观看' in parent_html or '充电专属' in parent_html)
            
            # Clean title
            if title:
                title = ' '.join(title.split()).strip()
                # If title is pure digits or too short, use video_id
                if not title or len(title) < 2 or title.replace('.', '').replace(',', '').replace(':', '').isdigit():
                    title = video_id
            else:
                title = video_id
            
            # Get thumbnail
            img_elem = item.ele('tag:img', timeout=1) or link_elem.ele('tag:img', timeout=1)
            thumbnail = img_elem.attr('src') if img_elem else ""
            if thumbnail and not thumbnail.startswith('http'):
                thumbnail = 'https:' + thumbnail
            
            # Extract play count, danmaku, duration
            play_count = ""
            danmaku = ""
            duration = ""
            
            # Play count (usually .play or element containing "play")
            play_elem = item.ele('css:.play', timeout=0.5)
            if play_elem:
                play_text = play_elem.text.strip()
                if play_text and not play_text.startswith('http'):
                    play_count = play_text
            
            # Danmaku count (usually .dm or .danmaku)
            danmaku_elem = item.ele('css:.dm', timeout=0.5) or item.ele('css:.danmaku', timeout=0.5)
            if danmaku_elem:
                danmaku_text = danmaku_elem.text.strip()
                if danmaku_text and not danmaku_text.startswith('http'):
                    danmaku = danmaku_text
            
            # Duration (usually .length or .duration)
            duration_elem = item.ele('css:.length', timeout=0.5) or item.ele('css:.duration', timeout=0.5)
            if duration_elem:
                duration_text = duration_elem.text.strip()
                if duration_text and ':' in duration_text:
                    duration = duration_text

            # Current space cards expose views, danmaku and duration as three
            # ordered stats rather than the legacy named classes above.
            stats = item.eles('css:.bili-cover-card__stat', timeout=0.5) or []
            stat_text = [' '.join((stat.text or '').split()) for stat in stats]
            if len(stat_text) >= 3:
                play_count = play_count or stat_text[0]
                danmaku = danmaku or stat_text[1]
                duration = duration or stat_text[2]
            
            # Current cards expose a compact date such as MM-DD.
            subtitle = item.ele('css:.bili-video-card__subtitle', timeout=0.5)
            publish_text = subtitle.text.strip() if subtitle and subtitle.text else ''
            pub_date = _parse_bilibili_publish_time(publish_text)
            
            # Build content
            content_parts = []
            if thumbnail:
                content_parts.append(f'<div style="margin-bottom: 20px;"><a href="{video_url}"><img src="{thumbnail}" style="max-width: 100%; height: auto;" /></a></div>')
            
            content_parts.append(f'<p><strong>UP Master:</strong> {up_name}</p>')
            
            # Video info
            info_parts = []
            if play_count:
                info_parts.append(f'<strong>Views:</strong> {play_count}')
            if danmaku:
                info_parts.append(f'<strong>Danmaku:</strong> {danmaku}')
            if duration:
                info_parts.append(f'<strong>Duration:</strong> {duration}')
            
            if info_parts:
                content_parts.append(f'<p>{" | ".join(info_parts)}</p>')
            
            # Mark paid content
            if is_paid:
                content_parts.append(f'<p><strong>⚠️ Paid Content</strong></p>')
            
            content_parts.append(f'<p><a href="{video_url}">Watch Video</a></p>')
            
            # Optional: download video (paid content may not be downloadable)
            if self.DOWNLOAD_VIDEOS and not is_paid:
                self.logger.info(f"Downloading video {video_id}...")
                video_path = download_video(video_id, browser=browser)  # Pass browser to use cookies
                if video_path:
                    content_parts.append(f'<p><strong>Local Path:</strong> {video_path}</p>')
            elif self.DOWNLOAD_VIDEOS and is_paid:
                content_parts.append(f'<p><em>Paid content cannot be downloaded</em></p>')
            
            content = '\n'.join(content_parts)
            
            # Build summary (with key info)
            summary_parts = [title]
            if play_count:
                summary_parts.append(f"Views: {play_count}")
            if duration:
                summary_parts.append(duration)
            summary = ' | '.join(summary_parts)
            
            return Article(
                url=video_url,
                title=f"[{up_name}] {title}",
                published_at=pub_date,
                content=content,
                summary=summary[:200],
                category="Video",
                author=up_name,
            )
        
        except Exception as e:
            self.logger.error(f"Error parsing video item from browser: {e}")
            return None
    
    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full article content (already done in fetch_articles)."""
        return None


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Bilibili UP Master Video Feed Generator"
    )
    parser.add_argument("--max", type=int, default=50, help="Maximum articles")
    parser.add_argument("--full", action="store_true", help="Full refresh (ignore cache)")
    parser.add_argument("--mid", type=str, help="UP master ID, comma-separated for multiple")
    parser.add_argument("--download", action="store_true", help="Download videos")
    parser.add_argument(
        "--history", 
        action="store_true", 
        default=None,
        help="History mode: fetch more historical videos (recommended for first run)"
    )
    args = parser.parse_args()
    
    if args.download:
        os.environ["BILIBILI_DOWNLOAD_VIDEOS"] = "true"
    
    logging.basicConfig(level=logging.INFO)
    
    # Create generator (pass history_mode)
    mids = args.mid.split(",") if args.mid else None
    gen = BilibiliUPGenerator(history_mode=args.history, mids=mids)
    gen.run(full_refresh=args.full, max_articles=args.max)
