#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
ZSXQ (Knowledge Planet) Topic Feed Generator

Supports scraping latest topics from specified groups, including:
- Topic content
- Attachment downloads (audio, PDF, images, etc.)
- Auto-categorized storage
"""

import logging
import os
import re
import shutil
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from pathlib import Path
import json
import time

import pytz
import requests

from generators.base import Article, BaseFeedGenerator
from generators.social.zsxq.scraper import (
    check_zsxq_ready,
    create_zsxq_browser,
    ZSXQ_PROFILE_DIR,
)

logger = logging.getLogger(__name__)

# Attachments download directory.
# generator.py path: generators/social/zsxq/generator.py
# -> .parent (zsxq) -> .parent (social) -> .parent (generators) -> .parent (project_root)
ATTACHMENTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "downloads" / "zsxq"


def _sanitize_for_path(name: str, max_len: int = 60) -> str:
    """Make a string safe to use as a Windows/POSIX file or directory name."""
    if not name:
        return ""
    # Strip the "[group] " prefix if present
    name = re.sub(r"^\s*\[[^\]]*\]\s*", "", name).strip()
    # Replace characters that Windows / many filesystems disallow
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    # Avoid trailing dots / spaces (Windows hates those)
    name = name.rstrip(". ")
    if len(name) > max_len:
        name = name[:max_len].rstrip(". ")
    return name


def _parse_group_input(raw: str) -> str:
    """
    Resolve a group input string to a pure group_id.

    Accepts:
      - pure group_id ("88514182418182")
      - full URL ("https://wx.zsxq.com/group/88514182418182")
      - URL with extra path/query ("https://wx.zsxq.com/group/88514182418182/topic/xxx")
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        m = re.search(r"/group/(\d+)", raw)
        if m:
            return m.group(1)
        # Unrecognized URL form — return empty so it gets filtered out
        return ""
    return raw


def _topic_dir_for(
    base: Path,
    group_name: str,
    group_id: str,
    topic_title: str,
    topic_id: str,
) -> Path:
    """Compose a human-readable but unique directory: <group>_<gid>/<title>_<tid>."""
    safe_group = _sanitize_for_path(group_name) or "group"
    safe_topic = _sanitize_for_path(topic_title) or "topic"
    group_dir_name = f"{safe_group}_{group_id}" if group_id else safe_group
    topic_dir_name = f"{safe_topic}_{topic_id}" if topic_id else safe_topic
    return base / group_dir_name / topic_dir_name


class ZSXQTopicsGenerator(BaseFeedGenerator):
    """RSS generator for ZSXQ group topics."""
    
    FEED_NAME = "zsxq_topics"
    FEED_TITLE = "ZSXQ Knowledge Planet"
    FEED_URL = "https://wx.zsxq.com/"
    FEED_DESCRIPTION = "ZSXQ Knowledge Planet - Group Updates"
    FEED_LANGUAGE = "zh-CN"
    FEED_LOGO = "https://wx.zsxq.com/favicon.ico"
    
    # Group input list. Accepts EITHER:
    #   - pure group_id (e.g. "88514182418182"), or
    #   - full URL (e.g. "https://wx.zsxq.com/group/88514182418182")
    # Comma-separated for multiple groups.
    GROUP_IDS = [
        _parse_group_input(g)
        for g in os.environ.get("ZSXQ_GROUP_ID", "").split(",")
        if _parse_group_input(g)
    ]

    # Whether to download attachments (disabled by default to avoid page refresh issues. Set ZSXQ_DOWNLOAD_ATTACHMENTS=true when needed)
    DOWNLOAD_ATTACHMENTS = os.environ.get("ZSXQ_DOWNLOAD_ATTACHMENTS", "false").lower() == "true"

    # Number of topics to fetch each time (default: 20)
    MAX_TOPICS = int(os.environ.get("ZSXQ_MAX_TOPICS", "20"))
    
    # Max attachments to download per topic (default: 999 for all)
    MAX_ATTACHMENTS_PER_TOPIC = int(os.environ.get("ZSXQ_MAX_ATTACHMENTS_PER_TOPIC", "999"))
    
    def __init__(self):
        super().__init__()
        
        if not self.GROUP_IDS:
            self.logger.warning("No groups configured. Set ZSXQ_GROUP_ID environment variable.")
            self.logger.warning("Example: ZSXQ_GROUP_ID='group1,group2'")
        
        # Create attachments directory
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    
    def fetch_articles(self) -> list[Article]:
        """Fetch latest topics from configured groups."""
        ready, msg = check_zsxq_ready()
        if not ready:
            self.logger.error(msg)
            return []
        
        browser = create_zsxq_browser(headless=False)
        if not browser:
            return []
        
        articles = []

        # Honor the run-level cap so --max N doesn't over-scrape.
        per_group_cap = self.MAX_TOPICS
        run_cap = getattr(self, "_run_max_articles", None)
        if run_cap is not None and run_cap < per_group_cap:
            self.logger.info(
                f"Run cap (--max {run_cap}) overrides MAX_TOPICS={per_group_cap}"
            )
            per_group_cap = run_cap

        try:
            for group_id in self.GROUP_IDS:
                self.logger.info(f"Fetching topics from group {group_id}")
                topics = self._fetch_group_topics(browser, group_id, max_topics=per_group_cap)
                articles.extend(topics)
                self.logger.info(f"Found {len(topics)} topics from {group_id}")
        finally:
            browser.quit()

        return articles
    
    def _fetch_group_topics(
        self,
        browser,
        group_id: str,
        max_topics: int = 20
    ) -> list[Article]:
        """
        Fetch topics from a single group.
        
        Args:
            browser: DrissionPage browser instance
            group_id: Group ID
            max_topics: Max number of topics to fetch
        """
        articles = []
        
        try:
            # Visit group homepage
            url = f"https://wx.zsxq.com/group/{group_id}"
            browser.get(url)
            browser.wait(5)  # Wait for loading
            
            # Get group name
            group_name = self._get_group_name(browser) or f"Group{group_id}"
            self.logger.info(f"Group name: {group_name}")
            
            # Wait for page fully loaded
            browser.wait(3)
            
            # Scroll to load more topics
            for i in range(3):
                browser.scroll.to_bottom()
                browser.wait(2)
            
            # Find topic cards. As of 2026-05 zsxq is an Angular SPA where each
            # topic is wrapped in an <app-topic> custom element. The legacy
            # `[class*="topic"]` selector over-matches (catches .topic-container,
            # .topic-flow-container, etc. — 58 hits for ~20 actual topics).
            topic_selectors = [
                'css:app-topic',              # Current (2026-05): one per real topic
                'css:[class*="topic"]',       # Legacy fallback (over-matches)
                'css:.topic-card',            # Legacy
                'css:.feed-item',             # Legacy
            ]
            
            topic_items = []
            for selector in topic_selectors:
                try:
                    self.logger.debug(f"Trying selector: {selector}")
                    items = browser.eles(selector, timeout=3)
                    self.logger.debug(f"  Found {len(items) if items else 0} items")
                    if items and len(items) > 0:
                        topic_items = items
                        self.logger.info(f"Using selector: {selector}, found {len(items)} items")
                        break
                except Exception as e:
                    self.logger.debug(f"  Selector failed: {e}")
                    continue
            
            if not topic_items:
                self.logger.warning(f"No topics found for group {group_id}")
                return []
            
            # Parse topics (collect basic info)
            # If max_topics < total, randomly select topics (avoid always same one)
            import random
            if max_topics < len(topic_items):
                selected_indices = random.sample(range(len(topic_items)), max_topics)
                selected_items = [(i+1, topic_items[i]) for i in selected_indices]
            else:
                selected_items = list(enumerate(topic_items[:max_topics], 1))
            
            for idx, item in selected_items:
                try:
                    article = self._parse_topic_item(item, idx, group_name, group_id)
                    if article:
                        articles.append(article)
                except Exception as e:
                    self.logger.error(f"Error parsing topic #{idx}: {e}")
                    continue
            
            # If need to download attachments, process each topic in new tab
            if self.DOWNLOAD_ATTACHMENTS and articles:
                self.logger.info(f"Processing {len(articles)} topics for attachments...")
                
                # Re-get topic list elements (may have expired)
                topic_items_refresh = self._get_topic_items(browser)
                
                for idx, article in enumerate(articles, 1):
                    try:
                        self.logger.info(f"[{idx}/{len(articles)}] Processing: {article.title}")

                        # Get corresponding list item element
                        item_index = article._item_index
                        if item_index <= len(topic_items_refresh):
                            item = topic_items_refresh[item_index - 1]

                            # Get real URL and download attachments in new tab.
                            # Pass group_name and topic_title so the on-disk
                            # directory uses human-readable names.
                            topic_url, attachments = self._process_topic_in_new_tab(
                                item,
                                article._group_id,
                                browser,
                                group_name=group_name,
                                topic_title=article.title,
                            )
                            
                            # Update article URL
                            if topic_url:
                                article.url = topic_url
                                article.content = article.content.replace(
                                    f'https://wx.zsxq.com/group/{group_id}',
                                    topic_url
                                )
                            
                            # Add attachments info
                            if attachments:
                                article.content = self._add_attachments_to_content(
                                    article.content,
                                    attachments
                                )
                                self.logger.info(f"  Downloaded {len(attachments)} attachments")
                            else:
                                self.logger.info(f"  - No attachments found")
                    except Exception as e:
                        self.logger.error(f"  Failed to process topic: {e}")
                        continue
        
        except Exception as e:
            self.logger.error(f"Error fetching topics from group {group_id}: {e}")
        
        return articles
    
    def _get_group_name(self, browser) -> Optional[str]:
        """Get the currently-viewed group's name."""
        # Primary: page <title> tag is "<group_name>-知识星球"
        try:
            title = (getattr(browser, "title", "") or "").strip()
            if title:
                cleaned = title.replace("-知识星球", "").replace(" - 知识星球", "").strip()
                if cleaned and cleaned != "知识星球":
                    return cleaned
        except Exception:
            pass

        # Fallback: explicit DOM elements specific to the current group
        try:
            selectors = [
                'css:.group-info .group-text',  # current layout main pane
                'css:.group-info',
                'css:.group-title',
                'css:h1',
            ]
            for selector in selectors:
                name_elem = browser.ele(selector, timeout=2)
                if name_elem:
                    text = (name_elem.text or "").strip()
                    if text:
                        return text
        except Exception:
            pass
        return None
    
    def _get_topic_items(self, browser):
        """Re-fetch topic list elements. MUST use the same selector as the
        original fetch in _fetch_group_topics so item_index mapping is stable."""
        selectors = [
            'css:app-topic',              # Current (2026-05): exactly N real topics
            'css:[class*="topic"]',       # Legacy fallback (over-matches)
            'css:.topic-item',            # Legacy
            'css:.feed-item',             # Legacy
        ]

        for selector in selectors:
            items = browser.eles(selector, timeout=3)
            if items and len(items) > 0:
                self.logger.info(f"Using selector: {selector}, found {len(items)} items")
                return items

        self.logger.warning("No topic items found with any selector")
        return []
    
    def _process_topic_in_new_tab(
        self,
        item,
        group_id: str,
        main_browser,
        group_name: str = "",
        topic_title: str = "",
    ) -> tuple[Optional[str], list]:
        """
        Process topic in new tab: get real URL + download attachments
        
        Args:
            item: Topic item element in list page
            group_id: Group ID
            main_browser: Main browser instance (stays on list page)
        
        Returns:
            (topic_url, attachments) tuple
        """
        topic_url = None
        attachments = []
        
        try:
            # 1. Click the share button to open share menu, then click "复制链接".
            # In the current (2026-05) Angular layout, the share button is a
            # `<div class="share-topic" title="分享">`. The legacy `.icon`
            # selector over-matched (like/comment/subscribe icons all use it).
            menu_btn = (
                item.ele('css:.share-topic', timeout=2)
                or item.ele('css:[title="分享"]', timeout=1)
                or item.ele('css:.share-wrapper .icon', timeout=1)
            )
            if not menu_btn:
                self.logger.warning("  No share button found (.share-topic)")
                return None, []

            menu_btn.click()
            time.sleep(0.8)

            copy_link_btn = (
                main_browser.ele('text:复制链接', timeout=2)
                or main_browser.ele('text:复制链接地址', timeout=1)
            )
            if not copy_link_btn:
                self.logger.warning("  Share menu opened but no 'Copy Link' entry found")
                main_browser.ele('tag:body').click()
                return None, []

            copy_link_btn.click()
            time.sleep(0.5)
            
            # 2. Read short URL
            import pyperclip
            short_url = pyperclip.paste()
            
            if not short_url or not short_url.startswith('http'):
                self.logger.warning(f"  Invalid short URL: {short_url}")
                return None, []
            
            self.logger.debug(f"  Got short URL: {short_url}")
            
            # 3. Open short URL in new tab
            new_tab = main_browser.new_tab(short_url)
            time.sleep(2)
            
            # 4. Get real URL
            topic_url = new_tab.url
            self.logger.info(f"  Topic URL: {topic_url}")
            
            # 5. Extract topic_id
            topic_id_match = re.search(r'topic/(\d+)', topic_url)
            topic_id = topic_id_match.group(1) if topic_id_match else ""
            
            # 6. Download attachments
            if self.DOWNLOAD_ATTACHMENTS:
                attachments = self._download_attachments_from_detail_page(
                    new_tab,
                    topic_id,
                    group_id,
                    group_name=group_name,
                    topic_title=topic_title,
                )
            
            # 7. Close new tab
            new_tab.close()
            
        except Exception as e:
            self.logger.error(f"  Error in new tab processing: {e}")
        
        return topic_url, attachments
    
    def _parse_topic_item(
        self,
        item,
        item_index: int,
        group_name: str,
        group_id: str
    ) -> Optional[Article]:
        """
        Parse single topic basic info from list page (no redirect)
        
        Args:
            item: Topic item element
            item_index: Item index in the list
            group_name: Group name
            group_id: Group ID
        
        Returns:
            Article object with basic info
        """
        try:
            # Topic content — the new Angular layout puts the topic text inside
            # .talk-content-container .content. Old layouts used .topic-content
            # or just .content. Use a 0.5s timeout to allow lazy render.
            content_elem = (
                item.ele('css:.talk-content-container .content', timeout=0.5)
                or item.ele('css:.topic-content', timeout=0.3)
                or item.ele('css:.content', timeout=0.3)
            )
            content_text = (content_elem.text or "").strip() if content_elem else ""

            # Author — '.role.owner' is the star owner; '.author-name' / '.username' are legacy.
            author_elem = (
                item.ele('css:.role.owner', timeout=0.3)
                or item.ele('css:.author .role', timeout=0.3)
                or item.ele('css:.author-name', timeout=0.3)
                or item.ele('css:.username', timeout=0.3)
            )
            author = (author_elem.text or "").strip() if author_elem else "Unknown"

            # Publish time. The page renders "2026-05-16 08:16" with minute
            # granularity — we keep both the raw string (for fallback titles)
            # and the parsed datetime (for pub_date).
            time_elem = (
                item.ele('css:.date', timeout=0.3)
                or item.ele('css:.time', timeout=0.3)
                or item.ele('css:.create-time', timeout=0.3)
            )
            time_text_raw = (time_elem.text or "").strip() if time_elem else ""
            pub_date = datetime.now(pytz.UTC)
            if time_text_raw:
                try:
                    pub_date = self._parse_time(time_text_raw)
                except Exception:
                    pass

            # Decide title: prefer real content snippet. If empty (image/file-only
            # topic), fall back to "<author> @ <time>" so it is human-readable
            # and stays unique even when the same author posts multiple times
            # the same day (because time has minute precision; we append a
            # 6-char content/seed hash to break same-minute ties).
            if content_text:
                title = content_text[:50] + ('...' if len(content_text) > 50 else '')
            else:
                # `time_text_raw` may include spaces / extra whitespace
                time_compact = " ".join(time_text_raw.split()) if time_text_raw else ""
                base = f"{author} @ {time_compact}".rstrip(" @") if time_compact else author
            
            # Like count, comment count (optional info)
            likes_elem = item.ele('css:.like-count', timeout=0.1)
            likes = likes_elem.text.strip() if likes_elem else ""
            
            comments_elem = item.ele('css:.comment-count', timeout=0.1)
            comments = comments_elem.text.strip() if comments_elem else ""
            
            # Skip attachment check (check in detail page)
            has_attachments = False

            # Per-topic placeholder URL. Real topic permalinks aren't in the
            # listing DOM (zsxq is an Angular SPA), so we derive a stable
            # fragment from the content hash. Same content -> same hash -> dedup
            # by URL works across runs. For empty-content (file-only) topics we
            # seed on author + time so multiple posts collide-rarely.
            import hashlib as _hashlib
            seed = content_text or f"{author}|{time_text_raw}|idx{item_index}"
            url_hash = _hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
            temp_url = f"https://wx.zsxq.com/group/{group_id}#topic-{url_hash}"

            # Now finalize the fallback title with a hash tail so two same-author
            # same-minute attachment-only posts can be told apart at a glance.
            if not content_text:
                title = f"{base} #{url_hash[:6]}"
            
            # Build content
            content_parts = []
            
            # Topic text
            if content_elem:
                full_content = content_elem.text.strip()
                content_parts.append(f'<blockquote>{full_content}</blockquote>')
            
            # Attachment indicator
            if has_attachments:
                content_parts.append(f'<p><em>📎 This topic contains attachments</em></p>')
            
            # Meta info
            content_parts.append(f'<p><strong>Group:</strong> {group_name}</p>')
            content_parts.append(f'<p><strong>Author:</strong> {author}</p>')
            
            if likes or comments:
                meta_parts = []
                if likes:
                    meta_parts.append(f'👍 {likes}')
                if comments:
                    meta_parts.append(f'💬 {comments}')
                content_parts.append(f'<p>{" | ".join(meta_parts)}</p>')
            
            content = '\n'.join(content_parts)
            
            article = Article(
                url=temp_url,
                title=f"[{group_name}] {title}",
                published_at=pub_date,
                content=content,
                summary=title[:200],
                category="Topic",
                author=author,
            )
            
            # Attach metadata for later processing
            article._has_attachments = has_attachments
            article._item_index = item_index
            article._group_id = group_id
            article._group_name = group_name
            
            return article
        
        except Exception as e:
            self.logger.error(f"Error parsing topic item #{item_index}: {e}")
            return None
    
    def _parse_time(self, time_text: str) -> datetime:
        """Parse time string"""
        try:
            # ZSXQ time format:
            # "Just now", "1 minute ago", "1 hour ago", "Yesterday 12:30", "05-08 12:30"
            
            now = datetime.now(pytz.timezone('Asia/Shanghai'))
            
            if '刚刚' in time_text:
                return now
            elif '分钟前' in time_text:
                minutes = int(re.search(r'(\d+)', time_text).group(1))
                return now - timedelta(minutes=minutes)
            elif '小时前' in time_text:
                hours = int(re.search(r'(\d+)', time_text).group(1))
                return now - timedelta(hours=hours)
            elif '昨天' in time_text:
                time_part = time_text.split()[-1]
                h, m = map(int, time_part.split(':'))
                yesterday = now - timedelta(days=1)
                return yesterday.replace(hour=h, minute=m, second=0)
            elif re.match(r'\d{2}-\d{2}', time_text):
                # "05-08 12:30" format
                month_day, time_part = time_text.split()
                month, day = map(int, month_day.split('-'))
                h, m = map(int, time_part.split(':'))
                year = now.year
                dt = datetime(year, month, day, h, m, tzinfo=pytz.timezone('Asia/Shanghai'))
                return dt.astimezone(pytz.UTC)
            else:
                return now
        except:
            return datetime.now(pytz.UTC)
    
    def _download_file(
        self,
        url: str,
        output_path: Path,
        browser
    ) -> Optional[Path]:
        """
        Download file (using browser's cookies)
        
        Args:
            url: Download URL
            output_path: Output file path
            browser: Browser instance (for cookies)
        
        Returns:
            Path to downloaded file or None
        """
        try:
            # Get cookies from browser
            cookies = {}
            try:
                browser_cookies = browser.cookies(all_domains=True)
                for cookie in browser_cookies:
                    cookies[cookie.get('name')] = cookie.get('value')
            except:
                pass
            
            # Download file
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://wx.zsxq.com/'
            }
            
            response = requests.get(
                url,
                headers=headers,
                cookies=cookies,
                stream=True,
                timeout=300  # 5 minute timeout
            )
            
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return output_path
            else:
                self.logger.error(f"Download failed: HTTP {response.status_code}")
                return None
        
        except Exception as e:
            self.logger.error(f"Error downloading file: {e}")
            return None
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"
    
    def _get_file_icon(self, file_type: str) -> str:
        """Get emoji icon for file type."""
        icons = {
            'MP3': '🎵',
            'MP4': '🎬',
            'PDF': '📄',
            'DOC': '📝',
            'DOCX': '📝',
            'XLS': '📊',
            'XLSX': '📊',
            'PPT': '📽️',
            'PPTX': '📽️',
            'ZIP': '📦',
            'RAR': '📦',
            'PNG': '🖼️',
            'JPG': '🖼️',
            'JPEG': '🖼️',
            'GIF': '🖼️',
        }
        return icons.get(file_type.upper(), '📎')
    
    def _extract_topic_id(self, topic_url: str) -> str:
        """Extract topic ID from topic URL"""
        # URL format: https://wx.zsxq.com/group/88514182418182/topic_xxxxxxxx
        # or /group/88514182418182/topic_xxxxxxxx
        match = re.search(r'topic_([a-zA-Z0-9]+)', topic_url)
        if match:
            return match.group(1)
        return topic_url.split('/')[-1]
    
    def _download_attachments_from_detail_page(
        self,
        browser,
        topic_id: str,
        group_id: str,
        group_name: str = "",
        topic_title: str = "",
    ) -> List[Dict[str, str]]:
        """
        Download attachments from topic detail page (already opened)
        
        Args:
            browser: Browser instance (already on detail page)
            topic_id: Topic ID
            group_id: Group ID
            
        Returns:
            List of downloaded attachments
        """
        attachments = []
        
        try:
            # Wait for page load
            time.sleep(2)
            
            # Find attachment elements (attachment list in detail page)
            file_selector = 'css:.file-gallery-container .item'
            file_count = 0
            
            try:
                elems = browser.eles(file_selector, timeout=2)
                if elems and len(elems) > 0:
                    file_count = len(elems)
                    self.logger.info(f"    Found {file_count} files")
                else:
                    # Try fallback selector
                    elems = browser.eles('css:app-file-gallery .item', timeout=1)
                    if elems and len(elems) > 0:
                        file_selector = 'css:app-file-gallery .item'
                        file_count = len(elems)
                        self.logger.info(f"    Found {file_count} files (alt selector)")
            except Exception as e:
                self.logger.warning(f"    Failed to find files: {e}")
            
            if not file_selector or file_count == 0:
                self.logger.debug("    No file elements found")
                return []
            
            # Create topic-specific directory with human-readable names.
            topic_dir = _topic_dir_for(
                ATTACHMENTS_DIR, group_name, group_id, topic_title, topic_id,
            )
            topic_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"    Saving to: {topic_dir.relative_to(ATTACHMENTS_DIR.parent.parent)}")
            
            # Process each attachment (use filename dedup to avoid re-download)
            # Configurable download limit (set to 999 in production to download all)
            max_downloads = min(file_count, self.MAX_ATTACHMENTS_PER_TOPIC)
            self.logger.info(f"    Will download {max_downloads} of {file_count} files")
            
            downloaded_filenames = set()  # Track successfully downloaded filenames
            failed_attempts = {}  # Track failure count for each file
            attempts = 0
            max_retries = 3  # Max 3 retries per file
            
            while len(downloaded_filenames) < max_downloads and attempts < file_count * 3:
                attempts += 1
                
                try:
                    # Re-find all attachment elements
                    file_elements = browser.eles(file_selector, timeout=2)
                    if not file_elements:
                        self.logger.warning(f"      No file elements found (attempt {attempts})")
                        break
                    
                    # Find first undownloaded attachment
                    target_elem = None
                    target_filename = None
                    
                    for elem in file_elements:
                        fname_elem = elem.ele('css:.file-name', timeout=0.3)
                        if fname_elem:
                            fname = fname_elem.text.strip()
                            # Skip successfully downloaded files and files with excessive retries
                            if fname and fname not in downloaded_filenames:
                                if failed_attempts.get(fname, 0) < max_retries:
                                    target_elem = elem
                                    target_filename = fname
                                    break
                    
                    if not target_elem or not target_filename:
                        self.logger.debug(f"      No more files to download")
                        break
                    
                    filename = target_filename
                    self.logger.info(f"      [{len(downloaded_filenames)+1}/{max_downloads}] Processing: {filename}")
                    
                    # Click attachment item to open preview window
                    target_elem.click()
                    time.sleep(1.5)
                    
                    # Find download button in preview window (prefer text search)
                    download_btn = browser.ele('text:下载文件', timeout=2)
                    if not download_btn:
                        download_btn = browser.ele('css:.download', timeout=1)
                    if not download_btn:
                        download_btn = browser.ele('css:.btn-wrapper .btn', timeout=1)
                    
                    if not download_btn:
                        self.logger.warning(f"      No download button in preview for {filename}")
                        self.logger.debug(f"      Page HTML: {browser.html[:500]}")
                        # Close preview (click outside popup)
                        try:
                            browser.run_js("document.elementFromPoint(50, 50).click();")
                            time.sleep(0.3)
                        except:
                            pass
                        continue
                    
                    # Clean filename
                    filename = re.sub(r'[\\/:*?"<>|]', '_', filename)
                    target_path = topic_dir / filename
                    
                    # Get default download directory (usually C:\Users\xxx\Downloads)
                    default_download_dir = Path(os.path.expanduser("~")) / "Downloads"
                    
                    # Record file list before click
                    before_files = set(f.name for f in default_download_dir.glob('*') if f.is_file())
                    
                    # Click download button, browser will auto-download to default location
                    self.logger.debug(f"      Clicking download button...")
                    download_btn.click()
                    
                    # Wait for download complete
                    max_wait = 60  # Max wait 60 seconds
                    downloaded_file = None
                    
                    for wait_count in range(max_wait):
                        time.sleep(1)
                        
                        # Check if new file exists and no .crdownload temp file
                        current_files = [f for f in default_download_dir.glob('*') if f.is_file()]
                        
                        # Find new file
                        for f in current_files:
                            if f.name not in before_files and f.suffix != '.crdownload':
                                # Ensure file is not being downloaded
                                crdownload_exists = any(cf.suffix == '.crdownload' for cf in current_files)
                                if not crdownload_exists:
                                    downloaded_file = f
                                    self.logger.info(f"      Downloaded to: {f.name}")
                                    break
                        
                        if downloaded_file:
                            break
                    
                    if downloaded_file and downloaded_file.exists():
                        # Move and rename file to target directory
                        try:
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            # Use shutil.move to support cross-disk move
                            shutil.move(str(downloaded_file), str(target_path))
                            
                            file_size = target_path.stat().st_size
                            
                            # Integrity check
                            is_valid = True
                            if file_size == 0:
                                self.logger.error(f"      File is empty (0 bytes): {filename}")
                                is_valid = False
                            elif file_size < 100:  # Less than 100 bytes definitely has issue
                                self.logger.warning(f"      File too small ({file_size} bytes): {filename}")
                                is_valid = False
                            elif target_path.suffix.lower() == '.pdf':
                                # Check PDF file header
                                try:
                                    with open(target_path, 'rb') as f:
                                        header = f.read(4)
                                        if not header.startswith(b'%PDF'):
                                            self.logger.error(f"      Invalid PDF file: {filename}")
                                            is_valid = False
                                except:
                                    pass
                            
                            if is_valid:
                                file_size_str = self._format_file_size(file_size)
                                file_type = target_path.suffix[1:].upper() if target_path.suffix else "FILE"
                                
                                attachments.append({
                                    'name': filename,
                                    'type': file_type,
                                    'size': file_size_str,
                                    'url': f"zsxq://{group_id}/{topic_id}/{filename}",
                                    'local_path': str(target_path.relative_to(ATTACHMENTS_DIR.parent))
                                })
                                
                                self.logger.info(f"      Saved: {filename} ({file_size_str})")
                                downloaded_filenames.add(filename)  # Mark as successfully downloaded
                                # Clear failure record
                                if filename in failed_attempts:
                                    del failed_attempts[filename]
                            else:
                                # Delete invalid file and record failure
                                try:
                                    target_path.unlink()
                                except:
                                    pass
                                
                                # Record failure count
                                failed_attempts[filename] = failed_attempts.get(filename, 0) + 1
                                retry_count = failed_attempts[filename]
                                
                                if retry_count >= max_retries:
                                    self.logger.error(f"      Failed after {retry_count} attempts: {filename}")
                                    # Mark as tried (avoid infinite loop)
                                    downloaded_filenames.add(filename)
                                else:
                                    self.logger.warning(f"      Invalid file, will retry ({retry_count}/{max_retries}): {filename}")
                                    # Don't add to downloaded_filenames, will retry next loop
                        except Exception as e:
                            self.logger.error(f"      Failed to move file: {e}")
                    else:
                        # Download timeout or failed, record failure count
                        failed_attempts[filename] = failed_attempts.get(filename, 0) + 1
                        retry_count = failed_attempts[filename]
                        
                        if retry_count >= max_retries:
                            self.logger.error(f"      Download timeout after {retry_count} attempts: {filename}")
                            downloaded_filenames.add(filename)  # Give up retry
                        else:
                            self.logger.warning(f"      Download timeout, will retry ({retry_count}/{max_retries}): {filename}")
                    
                    # Close attachment preview (click outside popup area)
                    self.logger.debug(f"      Closing preview window...")
                    closed = False
                    
                    # Method 1: Use JavaScript to click top-left corner of page (outside popup)
                    try:
                        browser.run_js("document.elementFromPoint(50, 50).click();")
                        time.sleep(0.5)
                        closed = True
                        self.logger.debug(f"      Closed by JS click")
                    except Exception as e:
                        self.logger.debug(f"      JS click failed: {e}")
                    
                    # Method 2: Find and click mask layer
                    if not closed:
                        try:
                            mask = browser.ele('css:.modal-mask', timeout=0.5)
                            if not mask:
                                mask = browser.ele('css:.mask', timeout=0.5)
                            if not mask:
                                mask = browser.ele('css:[class*="mask"]', timeout=0.5)
                            if mask:
                                mask.click()
                                time.sleep(0.5)
                                closed = True
                                self.logger.debug(f"      Closed by clicking mask")
                        except:
                            pass
                    
                    if not closed:
                        self.logger.warning(f"      Warning: Could not close preview")
                
                except Exception as e:
                    self.logger.warning(f"      Failed to download attachment: {e}")
                    if 'target_filename' in locals() and target_filename:
                        # Record failure count
                        failed_attempts[target_filename] = failed_attempts.get(target_filename, 0) + 1
                        retry_count = failed_attempts[target_filename]
                        
                        if retry_count >= max_retries:
                            self.logger.error(f"      Exception after {retry_count} attempts: {target_filename}")
                            downloaded_filenames.add(target_filename)  # Give up retry
                        else:
                            self.logger.warning(f"      Will retry after exception ({retry_count}/{max_retries}): {target_filename}")
                    
                    # Try to close possibly opened popup (click outside)
                    try:
                        browser.run_js("document.elementFromPoint(50, 50).click();")
                        time.sleep(0.3)
                    except:
                        pass
                    continue
        
        except Exception as e:
            self.logger.error(f"    Error downloading attachments: {e}")
        
        # Output statistics
        if 'failed_attempts' in locals() and failed_attempts:
            total_failures = sum(failed_attempts.values())
            failed_files = [f for f, c in failed_attempts.items() if c >= max_retries]
            if failed_files:
                self.logger.warning(f"    Failed to download {len(failed_files)} files after {max_retries} retries")
        
        return attachments
    
    def _add_attachments_to_content(self, original_content: str, attachments: List[Dict[str, str]]) -> str:
        """Add attachments info to article content"""
        if not attachments:
            return original_content
        
        # Remove original "contains attachments" prompt
        content = original_content.replace('<p><em>📎 This topic contains attachments</em></p>', '')
        
        # Build attachments list HTML
        attachments_html = [f'<h3>📎 Attachments ({len(attachments)})</h3>', '<ul>']
        
        for att in attachments:
            file_icon = self._get_file_icon(att['type'])
            size_str = f" ({att['size']})" if att.get('size') else ""
            attachments_html.append(
                f'<li>{file_icon} <a href="{att["url"]}">{att["name"]}</a>{size_str} '
                f'<br><small>Local: {att["local_path"]}</small></li>'
            )
        
        attachments_html.append('</ul>')
        
        # Insert attachments list before meta info
        meta_marker = '<p><strong>Group:</strong>'
        if meta_marker in content:
            content = content.replace(meta_marker, '\n'.join(attachments_html) + '\n' + meta_marker)
        else:
            # If marker not found, append to end
            content += '\n' + '\n'.join(attachments_html)
        
        return content
    
    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full article content (already done in fetch_articles)."""
        return None


if __name__ == "__main__":
    import argparse
    from datetime import timedelta
    
    parser = argparse.ArgumentParser(description="ZSXQ Topic Feed Generator")
    parser.add_argument("--max", type=int, default=50, help="Max number of articles")
    parser.add_argument("--full", action="store_true", help="Full refresh (ignore cache)")
    parser.add_argument("--group", type=str, help="Group ID, comma-separated for multiple")
    args = parser.parse_args()
    
    # Set group ID temporarily
    if args.group:
        os.environ["ZSXQ_GROUP_ID"] = args.group
    
    logging.basicConfig(level=logging.INFO)
    
    gen = ZSXQTopicsGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
