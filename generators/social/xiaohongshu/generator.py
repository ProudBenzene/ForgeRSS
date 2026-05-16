#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Xiaohongshu Content Scraper
Supports scraping notes (text and video) from specified users

Configuration:
1. Environment variable XHS_USER_ID (User IDs, comma-separated)
2. Or set USER_INPUTS list in code

XHS_USER_ID accepts either:
  - a pure user_id ("664f367c00000000070064da"), or
  - a full profile URL (pasted from browser) including ?xsec_token=... (preferred)

Example:
    XHS_USER_ID="user1,user2" python scripts/run_single.py xiaohongshu_user
"""

import logging
import os
import re
import time
import random
from datetime import datetime
from typing import Optional

import pytz

from generators.base import Article, BaseFeedGenerator
from generators.social.xiaohongshu.scraper import (
    create_xhs_browser,
    check_xhs_ready,
    download_media,
)

logger = logging.getLogger(__name__)


class XiaohongshuUserGenerator(BaseFeedGenerator):
    """RSS generator for Xiaohongshu user notes."""
    
    FEED_NAME = "xiaohongshu_user"
    FEED_TITLE = "Xiaohongshu User"
    FEED_URL = "https://www.xiaohongshu.com/"
    FEED_DESCRIPTION = "Xiaohongshu User - Notes and Posts"
    FEED_LANGUAGE = "zh-CN"
    FEED_LOGO = "https://fe-video-qc.xhscdn.com/fe-platform/b28422ec96a51e4d8ef8b00a48f8fb3a18da0bc2.png"
    
    # User input list (from env var or code config).
    # Accepts EITHER:
    #   - a pure user_id (e.g. "664f367c00000000070064da"), or
    #   - a full profile URL (e.g. "https://www.xiaohongshu.com/user/profile/{id}?xsec_token=...")
    # The full-URL form is preferred: pasting from the browser keeps xsec_token /
    # xsec_source which improves reliability against xhs anti-scraping changes.
    USER_INPUTS = os.environ.get("XHS_USER_ID", "").split(",")
    USER_INPUTS = [u.strip() for u in USER_INPUTS if u.strip()]

    # Whether to download media (default: no, only generate RSS feed; read dynamically in fetch_articles)
    DOWNLOAD_MEDIA = False

    # Number of notes to fetch per user (default: 20)
    MAX_NOTES = int(os.environ.get("XHS_MAX_NOTES", "20"))

    def __init__(self):
        super().__init__()

        if not self.USER_INPUTS:
            self.logger.warning("No users configured. Set XHS_USER_ID environment variable.")
            self.logger.warning("Example: XHS_USER_ID='664f367c00000000070064da'")
            self.logger.warning("Or paste full profile URL: XHS_USER_ID='https://www.xiaohongshu.com/user/profile/...?xsec_token=...'")

    @staticmethod
    def _parse_user_input(raw: str) -> tuple[str, str]:
        """
        Resolve a user input string into (user_id, profile_url).

        Accepts:
          - pure user_id:  "664f367c00000000070064da"
          - full URL:      "https://www.xiaohongshu.com/user/profile/<id>?xsec_token=..."

        For the full-URL form we keep the URL verbatim (including query string)
        because xsec_token may matter for the page render.
        """
        import re as _re
        raw = raw.strip()
        if raw.startswith(("http://", "https://")):
            # Try to pull the user_id out of the path
            m = _re.search(r"/user/profile/([^/?#]+)", raw)
            user_id = m.group(1) if m else raw
            return user_id, raw
        return raw, f"https://www.xiaohongshu.com/user/profile/{raw}"
    
    def fetch_articles(self) -> list[Article]:
        """Fetch latest notes from configured users."""
        # Dynamically read DOWNLOAD_MEDIA setting (supports CLI args)
        self.DOWNLOAD_MEDIA = os.environ.get("XHS_DOWNLOAD_MEDIA", "false").lower() == "true"
        if self.DOWNLOAD_MEDIA:
            self.logger.info("Video download is ENABLED (DOWNLOAD_MEDIA=True)")
        else:
            self.logger.info("Video download is DISABLED (DOWNLOAD_MEDIA=False)")
        
        ready, msg = check_xhs_ready()
        if not ready:
            self.logger.error(msg)
            return []
        
        browser = create_xhs_browser(headless=False)
        if not browser:
            return []
        
        articles = []
        
        # Honor the run-level cap so --max N doesn't over-scrape.
        per_user_cap = self.MAX_NOTES
        run_cap = getattr(self, "_run_max_articles", None)
        if run_cap is not None and run_cap < per_user_cap:
            self.logger.info(
                f"Run cap (--max {run_cap}) overrides MAX_NOTES={per_user_cap}"
            )
            per_user_cap = run_cap

        try:
            for raw in self.USER_INPUTS:
                user_id, profile_url = self._parse_user_input(raw)
                self.logger.info(
                    f"Fetching notes from user {user_id} (URL: {profile_url})"
                )
                notes = self._fetch_user_notes(
                    browser, user_id, profile_url, max_notes=per_user_cap,
                )
                articles.extend(notes)
                self.logger.info(f"Found {len(notes)} notes from user {user_id}")
        finally:
            browser.quit()

        return articles
    
    def _fetch_user_notes(
        self,
        browser,
        user_id: str,
        profile_url: str,
        max_notes: int = 20,
    ) -> list[Article]:
        """Fetch notes from a single user."""
        articles = []

        try:
            # Visit user profile (URL is provided verbatim — may include xsec_token)
            url = profile_url
            self.logger.info(f"Accessing user profile: {url}")
            browser.get(url)
            
            # Random delay to avoid anti-scraping
            delay = random.uniform(2, 4)
            self.logger.info(f"Waiting {delay:.1f}s to avoid anti-scraping...")
            browser.wait(delay)
            
            # Check actual URL (redirected?)
            current_url = browser.url
            self.logger.info(f"Current URL after loading: {current_url}")
            
            # If redirected to homepage, user ID invalid or login required
            if current_url == "https://www.xiaohongshu.com/" or "explore" in current_url:
                self.logger.error(f"Redirected to homepage! User ID {user_id} may be invalid or login required")
                self.logger.error(f"Expected: {url}")
                self.logger.error(f"Got: {current_url}")
                return []
            
            # Check for verification or login requirement
            html = browser.html
            if "验证" in html or "滑块" in html:
                self.logger.error("Detected verification challenge, please solve manually")
                return []
            
            if "登录" in html and "扫码登录" in html:
                self.logger.error("Not logged in or session expired")
                return []
            
            # Check page title to confirm user profile page
            page_title = browser.title
            self.logger.info(f"Page title: {page_title}")
            
            # XHS user profile title format is usually "username's homepage - Xiaohongshu"
            if "小红书" not in page_title and "发现" in page_title:
                self.logger.error(f"Not on user profile page! Page title: {page_title}")
                return []
            
            # Extract user info
            user_info = self._extract_user_info(browser)
            username = user_info.get('name', f"User{user_id}")
            
            self.logger.info(f"Fetching from: {username}")
            if user_info.get('description'):
                self.logger.info(f"Bio: {user_info['description'][:50]}...")
            if user_info.get('followers'):
                self.logger.info(f"Stats: {user_info['followers']} followers, {user_info.get('likes', 'N/A')} likes")
            
            # Scroll to load more notes (lazy loading, infinite scroll on XHS)
            self.logger.info("Scrolling to load more notes...")
            previous_count = 0
            no_change_count = 0  # Consecutive no-change count
            max_scroll_attempts = 20  # Max 20 scrolls (XHS may have many notes)
            
            for scroll_num in range(max_scroll_attempts):
                # Scroll to bottom
                browser.scroll.to_bottom()
                time.sleep(random.uniform(1.5, 2.5))
                
                # Check current loaded notes count
                current_notes = browser.eles('css:section.note-item')
                current_count = len(current_notes)
                
                # Strategy 1: Reached 2x target, can stop (with margin)
                if current_count >= max_notes * 2:
                    self.logger.info(f"Scroll {scroll_num + 1}: Loaded {current_count} notes (reached target {max_notes}*2)")
                    break
                
                # Strategy 2: Detect if new notes loaded
                if current_count == previous_count:
                    no_change_count += 1
                    self.logger.info(f"Scroll {scroll_num + 1}: {current_count} notes (no new {no_change_count}/3)")
                    
                    # 3 consecutive no-change means reached bottom
                    if no_change_count >= 3:
                        self.logger.info("No new notes loaded after 3 attempts, reached bottom")
                        break
                else:
                    # New notes loaded, reset counter
                    new_count = current_count - previous_count
                    no_change_count = 0
                    self.logger.info(f"Scroll {scroll_num + 1}: {current_count} notes (+{new_count})")
                
                previous_count = current_count
                
                # Strategy 3: Reached target, can stop (no need for exact 2x)
                if current_count >= max_notes:
                    self.logger.info(f"Loaded enough notes ({current_count} >= {max_notes})")
                    break
            
            # Get all note items
            note_items = browser.eles('css:section.note-item')
            self.logger.info(f"Total {len(note_items)} note items found after scrolling")
            
            if not note_items:
                self.logger.warning("No note items found")
                return []
            
            # Limit count
            note_items = note_items[:max_notes]
            self.logger.info(f"Processing {len(note_items)} notes...")
            
            # Extract basic info from list page first (without opening detail page)
            note_infos = []
            for idx, item in enumerate(note_items):
                try:
                    # Extract basic info from list item
                    title_elem = item.ele('css:a.title', timeout=1)
                    if not title_elem:
                        self.logger.warning(f"Note {idx+1}: No title found, skipping")
                        continue
                    
                    title_span = title_elem.ele('tag:span', timeout=1)
                    title = title_span.text.strip() if title_span else title_elem.text.strip()
                    if not title:
                        self.logger.warning(f"Note {idx+1}: Empty title, skipping")
                        continue
                    
                    # Get note URL
                    note_url = title_elem.attr('href')
                    if not note_url:
                        cover_elem = item.ele('css:a.cover', timeout=1)
                        if cover_elem:
                            note_url = cover_elem.attr('href')
                    
                    if not note_url:
                        self.logger.warning(f"Note {idx+1}: No URL found, skipping")
                        continue
                    
                    # Ensure full URL
                    if note_url.startswith('/'):
                        note_url = 'https://www.xiaohongshu.com' + note_url
                    elif not note_url.startswith('http'):
                        note_url = 'https://www.xiaohongshu.com' + note_url
                    
                    # Extract note ID (supports both explore and user/profile formats)
                    note_id_match = re.search(r'/([a-z0-9]{24})(?:\?|$)', note_url)
                    if not note_id_match:
                        self.logger.warning(f"Note {idx+1}: Cannot extract note ID from {note_url}")
                        continue
                    note_id = note_id_match.group(1)
                    
                    # Keep original URL (includes xsec_token etc, prevents redirect)
                    explore_url = note_url
                    self.logger.debug(f"Using original URL with auth params: {explore_url[:100]}...")
                    
                    # Determine if video (from list page)
                    is_video = self._is_video_note_from_list(item)
                    media_type = "Video" if is_video else "Photo"
                    
                    # Extract cover image (optional)
                    cover_url = self._extract_cover_from_list(item)
                    
                    note_infos.append({
                        'id': note_id,
                        'title': title,
                        'url': explore_url,  # Use standardized explore URL
                        'is_video': is_video,
                        'media_type': media_type,
                        'cover_url': cover_url,
                        'index': idx + 1
                        # Don't save element reference to avoid connection issues
                    })
                    
                    self.logger.info(f"Note {idx+1}/{len(note_items)}: [{media_type}] {title} ({note_id})")
                    
                except Exception as e:
                    self.logger.error(f"Error extracting note {idx+1} info: {e}")
                    continue
            
            self.logger.info(f"Extracted {len(note_infos)} note infos from list page")
            
            # Process by type (if need detailed content, open detail page)
            for note_info in note_infos:
                try:
                    # Random delay (anti-scraping)
                    if note_info['index'] > 1:
                        delay = random.uniform(2, 4)
                        self.logger.info(f"Waiting {delay:.1f}s before next note...")
                        time.sleep(delay)
                    
                    # Open detail page for both video and photo (need detailed content)
                    article = self._fetch_note_in_new_tab(
                        browser, 
                        note_info['id'], 
                        note_info['title'], 
                        username,
                        explore_url=note_info['url']  # Pass original URL (with token)
                    )
                    
                    if article:
                        articles.append(article)
                        self.logger.info(f"Success: processed note {note_info['index']}/{len(note_infos)}")
                    else:
                        self.logger.warning(f"Failed: could not process note {note_info['index']}/{len(note_infos)}")
                    
                except Exception as e:
                    self.logger.error(f"Error processing note {note_info['index']}: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                    continue
        
        except Exception as e:
            self.logger.error(f"Error fetching notes from user {user_id}: {e}")
        
        return articles
    
    def _is_video_note_from_list(self, item) -> bool:
        """Detect if video note from list page"""
        try:
            # Method 1: Check play icon
            if item.ele('css:.play-icon', timeout=0.5):
                return True
            
            # Method 2: Check video-related class
            if item.ele('css:[class*="video"]', timeout=0.5):
                return True
            
            # Method 3: Check video tag
            if item.ele('tag:video', timeout=0.5):
                return True
            
            return False
        except Exception as e:
            self.logger.debug(f"Video detection error: {e}")
            return False
    
    def _extract_cover_from_list(self, item) -> Optional[str]:
        """Extract cover image URL from list page"""
        try:
            # Try from img in cover link
            cover_link = item.ele('css:a.cover', timeout=1)
            if cover_link:
                img = cover_link.ele('tag:img', timeout=1)
                if img:
                    src = img.attr('src')
                    if src and 'xhscdn.com' in src:
                        return src
            
            # Fallback: find img directly
            img = item.ele('tag:img', timeout=1)
            if img:
                src = img.attr('src')
                if src and 'xhscdn.com' in src:
                    return src
        except Exception as e:
            self.logger.debug(f"Cover extraction error: {e}")
        
        return None
    
    def _build_video_article_from_list(self, note_info: dict, username: str) -> Article:
        """Build video Article from list info (without opening detail page, for video notes)"""
        pub_date = datetime.now(pytz.UTC)
        explore_url = note_info['url']
        note_id = note_info['id']
        title = note_info['title']
        cover_url = note_info.get('cover_url')
        
        # Build content HTML
        content_parts = []
        
        # Add type label
        content_parts.append('<div style="background:#f5f5f5;padding:8px 12px;border-radius:4px;margin-bottom:15px;">')
        content_parts.append('<strong>Type:</strong> Video')
        content_parts.append('</div>')
        
        # Add video content
        content_parts.append('<div style="margin-top: 20px;">')
        
        if self.DOWNLOAD_MEDIA:
            # Download video with yt-dlp
            self.logger.info(f"Downloading video with yt-dlp: {explore_url}")
            local_path = download_media(explore_url, note_id, "video")
            if local_path:
                content_parts.append('<div style="margin: 15px 0; background: #f8f8f8; padding: 15px; border-radius: 8px;">')
                content_parts.append('<p style="color:#333;font-size:14px;margin-bottom:8px;"><strong>Video Downloaded</strong></p>')
                content_parts.append(f'<p style="color:#666;font-size:13px;">File: {local_path.name}</p>')
                content_parts.append(f'<p style="color:#666;font-size:13px;">Size: {local_path.stat().st_size / (1024*1024):.1f} MB</p>')
                content_parts.append(f'<p style="margin-top:10px;"><a href="{explore_url}" target="_blank" style="color:#ff2442;">Open in Xiaohongshu</a></p>')
                content_parts.append('</div>')
            else:
                content_parts.append('<div style="margin: 15px 0; background: #fff3cd; padding: 15px; border-radius: 8px;">')
                content_parts.append('<p style="color:#856404;">Video download failed</p>')
                content_parts.append(f'<p style="margin-top:10px;"><a href="{explore_url}" target="_blank" style="color:#ff2442;">Open in Xiaohongshu</a></p>')
                content_parts.append('</div>')
        else:
            # No download, show cover and link
            if cover_url:
                content_parts.append(f'<img src="{cover_url}" style="max-width: 100%; margin: 10px 0; border-radius: 8px;" alt="Video Cover" />')
            
            content_parts.append('<div style="margin: 15px 0; text-align: center;">')
            content_parts.append('<p style="color:#666;font-size:14px;">📹 Video Note</p>')
            content_parts.append(f'<p style="margin-top:10px;"><a href="{explore_url}" target="_blank" style="color:#ff2442; font-weight:bold;">Watch on Xiaohongshu</a></p>')
            content_parts.append('</div>')
        
        content_parts.append('</div>')
        
        # Add view original link
        content_parts.append('<hr style="margin: 20px 0; border: none; border-top: 1px solid #eee;" />')
        content_parts.append('<p style="text-align: center; margin: 15px 0;">')
        content_parts.append(f'<a href="{explore_url}" target="_blank" style="color: #ff2442; text-decoration: none; font-weight: bold;">View Original Note</a>')
        content_parts.append('</p>')
        
        content = '\n'.join(content_parts)
        
        # Build summary
        summary = "[Video]"
        
        # Extract image list
        image_urls = [cover_url] if cover_url else []
        media_list = [{"type": "image", "url": cover_url}] if cover_url else []
        
        return Article(
            url=explore_url,
            title=f"[{username}] {title}",
            published_at=pub_date,
            content=content,
            summary=summary,
            category="Video",
            author=username,
            images=image_urls,
            media=media_list,
        )
    
    def _extract_user_info(self, browser) -> dict:
        """Extract detailed user information from profile page."""
        info = {
            'name': None,
            'description': None,
            'followers': None,
            'likes': None,
            'ip_location': None,
        }
        
        try:
            # Extract username
            name_selectors = [
                'css:.user-name',
                'css:.user-nickname .user-name',
                'css:.basic-info .user-name',
            ]
            for selector in name_selectors:
                elem = browser.ele(selector, timeout=1)
                if elem:
                    info['name'] = elem.text.strip()
                    break
            
            # Extract bio
            desc_elem = browser.ele('css:.user-desc', timeout=1)
            if desc_elem:
                info['description'] = desc_elem.text.strip()
            
            # Extract stats (followers, likes)
            stat_elems = browser.eles('css:.user-interactions > div', timeout=1)
            for elem in stat_elems:
                text = elem.text.strip()
                if '粉丝' in text:
                    info['followers'] = text.replace('粉丝', '').strip()
                elif '获赞与收藏' in text or '获赞' in text:
                    info['likes'] = text.replace('获赞与收藏', '').replace('获赞', '').strip()
            
            # Extract IP location
            ip_elem = browser.ele('css:.user-IP', timeout=1)
            if ip_elem:
                ip_text = ip_elem.text.strip()
                if 'IP属地：' in ip_text:
                    info['ip_location'] = ip_text.replace('IP属地：', '').strip()
            
            self.logger.debug(f"Extracted user info: {info}")
        except Exception as e:
            self.logger.warning(f"Error extracting user info: {e}")
        
        return info
    
    def _get_username(self, browser) -> Optional[str]:
        """Get username from page (deprecated, use _extract_user_info instead)."""
        try:
            # Try multiple possible selectors
            selectors = [
                'css:.user-name',
                'css:.user-nickname .user-name',
                'css:.username',
                'css:.nickname',
                'css:.basic-info .user-name',
            ]
            
            for selector in selectors:
                name_elem = browser.ele(selector, timeout=1)
                if name_elem:
                    text = name_elem.text.strip()
                    if text and len(text) > 0:
                        self.logger.info(f"Found username: {text}")
                        return text
        except Exception as e:
            self.logger.warning(f"Error getting username: {e}")
        return None
    
    def _fetch_note_in_new_tab(self, main_browser, note_id: str, title: str, username: str, explore_url: str = None) -> Optional[Article]:
        """Open note detail in new tab and extract content"""
        new_tab = None
        try:
            # Use passed URL (with token), or construct if not provided
            if not explore_url:
                explore_url = f"https://www.xiaohongshu.com/explore/{note_id}"
            
            # Create new tab directly (use URL with token)
            self.logger.info(f"Opening note with auth URL: {explore_url[:80]}...")
            new_tab = main_browser.new_tab(explore_url)
            time.sleep(1)
            
            # Wait for page load (SPA needs longer)
            self.logger.debug("Waiting for SPA to render...")
            time.sleep(random.uniform(8, 10))  # Increase initial wait time
            
            # Check if loaded successfully (not homepage)
            current_url = new_tab.url
            if note_id not in current_url:
                self.logger.warning(f"Page redirected: expected {note_id}, got {current_url}")
                # May be redirected, but still try extracting
            
            # Scroll multiple times to trigger lazy load and ensure DOM rendered
            try:
                for i in range(5):  # Increase scroll count
                    new_tab.scroll.to_bottom()
                    time.sleep(1)
                    new_tab.scroll.to_top()
                    time.sleep(1)
                self.logger.debug("Scrolling completed")
            except Exception as e:
                self.logger.debug(f"Scrolling error: {e}")
            
            # Wait again to ensure rendering complete
            time.sleep(3)
            
            # Check page status
            html = new_tab.html
            if "验证" in html or "滑块" in html:
                self.logger.warning("Detected verification challenge")
                return None
            
            # Determine if video note
            is_video = self._check_if_video_note(new_tab)
            media_type = "Video" if is_video else "Photo"
            self.logger.info(f"Note type: {media_type}")
            
            # Extract content
            description = self._extract_note_description(new_tab, note_id)
            
            # Extract media
            media_urls = self._extract_note_media(new_tab, note_id, is_video)
            
            # Build Article
            article = self._build_article(
                note_id=note_id,
                title=title,
                username=username,
                description=description,
                media_type=media_type,
                is_video=is_video,
                media_urls=media_urls,
                explore_url=explore_url
            )
            
            return article
            
        except Exception as e:
            self.logger.error(f"Error fetching note in new tab: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
        finally:
            # Close new tab
            if new_tab:
                try:
                    new_tab.close()
                    time.sleep(0.5)
                except:
                    pass
    
    def _check_if_video_note(self, browser) -> bool:
        """Check if video note (multiple methods)"""
        # Method 1: Check from page state
        try:
            js_check = """
            try {
                // Check __INITIAL_STATE__
                if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.note) {
                    const noteData = window.__INITIAL_STATE__.note.noteDetailMap;
                    for (let key in noteData) {
                        const note = noteData[key].note;
                        if (note && note.type === 'video') {
                            return true;
                        }
                        if (note && note.video && note.video.media) {
                            return true;
                        }
                    }
                }
                // Check DOM elements
                if (document.querySelector('video')) return true;
                if (document.querySelector('.xgplayer')) return true;
                if (document.querySelector('[class*="video-player"]')) return true;
                const container = document.querySelector('#noteContainer');
                if (container && container.getAttribute('data-type') === 'video') return true;
            } catch(e) {
                console.error(e);
            }
            return false;
            """
            is_video = browser.run_js(js_check)
            if is_video:
                self.logger.info("Detected video note via JavaScript check")
                return True
        except Exception as e:
            self.logger.debug(f"JS video check failed: {e}")
        
        # Method 2: Check noteContainer data-type attribute
        try:
            note_container = browser.ele('css:#noteContainer', timeout=8)
            if note_container:
                data_type = note_container.attr('data-type')
                if data_type == 'video':
                    self.logger.info("Detected video note via data-type='video'")
                    return True
        except:
            pass
        
        # Method 3: Check xgplayer video player class
        try:
            if browser.ele('css:.xgplayer', timeout=8):
                self.logger.info("Detected video note via xgplayer class")
                return True
        except:
            pass
        
        # Method 4: Check video tag
        try:
            if browser.ele('tag:video', timeout=8):
                self.logger.info("Detected video note via video tag")
                return True
        except:
            pass
        
        # Method 5: Check elements with class containing video-player
        try:
            if browser.ele('css:[class*="video-player"]', timeout=5):
                self.logger.info("Detected video note via video-player class")
                return True
        except:
            pass
        
        return False
    
    def _extract_note_description(self, browser, note_id: str) -> str:
        """Extract note description/content"""
        description = ""
        
        # Method 1: Extract from JavaScript state (most accurate)
        try:
            js_extract = """
            try {
                if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.note) {
                    const noteData = window.__INITIAL_STATE__.note.noteDetailMap;
                    for (let key in noteData) {
                        const note = noteData[key].note;
                        if (note && note.desc) {
                            return note.desc;
                        }
                        if (note && note.title) {
                            return note.title;
                        }
                    }
                }
            } catch(e) {
                console.error(e);
            }
            return null;
            """
            desc_from_js = browser.run_js(js_extract)
            if desc_from_js and len(desc_from_js) > 10:
                self.logger.info(f"Found description from __INITIAL_STATE__: {desc_from_js[:100]}...")
                return desc_from_js
        except Exception as e:
            self.logger.debug(f"JS description extraction failed: {e}")
        
        # Method 2: Extract from DOM selectors
        desc_selectors = [
            ('css:#detail-desc span.note-text', 10),
            ('css:#detail-desc .note-text', 10),
            ('css:.note-content .note-text', 8),
            ('css:div[id*="desc"] .note-text', 8),
            ('css:.desc', 8),
            ('css:#detail-desc', 8),
            ('css:.note-content', 8),
            ('css:.note-text', 8),
        ]
        
        for selector, timeout in desc_selectors:
            try:
                elem = browser.ele(selector, timeout=timeout)
                if elem:
                    text = elem.text.strip()
                    self.logger.debug(f"Selector {selector} found text length: {len(text)}")
                    
                    if text and len(text) > 10:
                        # Exclude navigation/system text
                        skip_keywords = ["发现", "直播", "发布", "通知", "消息", "我的", "首页"]
                        if not any(kw == text[:20].strip() for kw in skip_keywords):
                            description = text
                            self.logger.info(f"Found description via {selector}: {description[:100]}...")
                            break
            except Exception as e:
                self.logger.debug(f"Selector {selector} error: {e}")
                continue
        
        if not description:
            self.logger.warning(f"No valid description found for note {note_id}")
        
        return description
    
    def _extract_note_media(self, browser, note_id: str, is_video: bool) -> list:
        """Extract note media (images or real video URL)"""
        media_urls = []
        
        if is_video:
            # Video note - extract real video URL
            try:
                # Method 1: Extract real video URL from window.__INITIAL_STATE__ (most reliable)
                js_code = """
                // Extract real video URL from window.__INITIAL_STATE__
                try {
                    if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.note) {
                        const noteData = window.__INITIAL_STATE__.note.noteDetailMap;
                        for (let key in noteData) {
                            const note = noteData[key].note;
                            if (note && note.video && note.video.media) {
                                // Method 1: Get from stream.h264
                                if (note.video.media.stream && note.video.media.stream.h264 
                                    && note.video.media.stream.h264[0]) {
                                    const h264 = note.video.media.stream.h264[0];
                                    if (h264.masterUrl) return h264.masterUrl;
                                    if (h264.backupUrls && h264.backupUrls[0]) return h264.backupUrls[0];
                                }
                                // Method 2: Get from video.consumer.originVideoKey
                                if (note.video.consumer && note.video.consumer.originVideoKey) {
                                    return 'https://sns-video-bd.xhscdn.com/' + note.video.consumer.originVideoKey;
                                }
                            }
                        }
                    }
                } catch(e) {
                    console.error(e);
                }
                return null;
                """
                
                video_url = browser.run_js(js_code)
                if video_url:
                    self.logger.info(f"Found video URL from JavaScript: {video_url[:100]}...")
                    media_urls.append(('video', video_url))
                    return media_urls
                
                # Method 3: Extract poster image
                poster = browser.ele('css:.xgplayer-poster', timeout=3)
                if poster:
                    style = poster.attr('style')
                    if style:
                        import re
                        url_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', style)
                        if url_match:
                            cover_url = url_match.group(1)
                            self.logger.info(f"Found video poster: {cover_url[:100]}...")
                            media_urls.append(('image', cover_url))
                
                if not media_urls:
                    self.logger.warning(f"No video URL found for video note {note_id}")
                
            except Exception as e:
                self.logger.error(f"Error extracting video URL: {e}")
            
            return media_urls
        
        else:
            # Photo note - extract all images
            img_selectors = [
                'css:.note-scroller img',
                'css:.carousel-container img',
                'css:[class*="slide"] img',
                'css:[class*="swiper"] img',
                'css:img',  # Most generic image selector
            ]
            
            for selector in img_selectors:
                img_elems = browser.eles(selector, timeout=5)
                if img_elems:
                    for img in img_elems[:9]:  # Max 9 images
                        img_url = img.attr('src')
                        if img_url and 'xhscdn.com' in img_url:
                            if ('image', img_url) not in media_urls:
                                media_urls.append(('image', img_url))
                    if media_urls:
                        self.logger.info(f"Found {len(media_urls)} images in note")
                        break
        
        return media_urls
    
    def _build_article(self, note_id: str, title: str, username: str, description: str,
                      media_type: str, is_video: bool, media_urls: list, explore_url: str) -> Article:
        """Build Article object"""
        pub_date = datetime.now(pytz.UTC)
        
        # Debug log
        self.logger.info(f"_build_article called with {len(media_urls)} media items")
        if media_urls:
            self.logger.debug(f"Media URLs: {media_urls[:2]}")  # Only show first 2 to avoid clutter
        
        # Build content HTML
        content_parts = []
        
        # Add type label
        content_parts.append(f'<div style="background:#f5f5f5;padding:8px 12px;border-radius:4px;margin-bottom:15px;">')
        content_parts.append(f'<strong>Type:</strong> {media_type}')
        if media_urls:
            content_parts.append(f' | <strong>Media Count:</strong> {len(media_urls)}')
        content_parts.append('</div>')
        
        # Add text content
        if description:
            content_parts.append('<div style="margin: 15px 0; line-height: 1.8; font-size: 15px;">')
            desc_html = description.replace('\n', '<br>')
            content_parts.append(desc_html)
            content_parts.append('</div>')
        
        # Add media content
        if is_video:
            # Video note
            content_parts.append('<div style="margin-top: 20px;">')
            
            if self.DOWNLOAD_MEDIA:
                # Prefer extracted real video URL, otherwise use yt-dlp
                video_url = None
                for mtype, murl in media_urls:
                    if mtype == "video":
                        video_url = murl
                        break
                
                if not video_url:
                    # No real video URL, try yt-dlp (needs explore format)
                    # Extract note_id and token from explore_url, build yt-dlp supported URL
                    import re
                    from urllib.parse import urlparse, parse_qs, urlencode
                    
                    parsed = urlparse(explore_url)
                    query_params = parse_qs(parsed.query)
                    
                    # Build yt-dlp supported URL format
                    video_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                    if query_params:
                        video_url += '?' + urlencode({k: v[0] for k, v in query_params.items()}, doseq=True)
                
                self.logger.info(f"Downloading video from: {video_url[:100]}...")
                local_path = download_media(video_url, note_id, "video")
                if local_path:
                    content_parts.append(f'<div style="margin: 15px 0; background: #f8f8f8; padding: 15px; border-radius: 8px;">')
                    content_parts.append(f'<p style="color:#333;font-size:14px;margin-bottom:8px;"><strong>Video Downloaded</strong></p>')
                    content_parts.append(f'<p style="color:#666;font-size:13px;">File: {local_path.name}</p>')
                    content_parts.append(f'<p style="color:#666;font-size:13px;">Size: {local_path.stat().st_size / (1024*1024):.1f} MB</p>')
                    content_parts.append(f'<p style="margin-top:10px;"><a href="{explore_url}" target="_blank" style="color:#ff2442;">Open in Xiaohongshu</a></p>')
                    content_parts.append('</div>')
                else:
                    content_parts.append(f'<div style="margin: 15px 0; background: #fff3cd; padding: 15px; border-radius: 8px;">')
                    content_parts.append(f'<p style="color:#856404;">Video download failed</p>')
                    content_parts.append(f'<p style="margin-top:10px;"><a href="{explore_url}" target="_blank" style="color:#ff2442;">Open in Xiaohongshu</a></p>')
                    content_parts.append('</div>')
            else:
                # No download, show cover and link
                if media_urls:
                    for mtype, murl in media_urls:
                        if mtype == "image":
                            content_parts.append(f'<img src="{murl}" style="max-width: 100%; margin: 10px 0; border-radius: 8px;" alt="Video Cover" />')
                
                content_parts.append(f'<div style="margin: 15px 0; text-align: center;">')
                content_parts.append(f'<p style="color:#666;font-size:14px;">📹 Video Note</p>')
                content_parts.append(f'<p style="margin-top:10px;"><a href="{explore_url}" target="_blank" style="color:#ff2442; font-weight:bold;">Watch on Xiaohongshu</a></p>')
                content_parts.append('</div>')
            
            content_parts.append('</div>')
        elif media_urls:
            # Photo note
            content_parts.append('<div style="margin-top: 20px;">')
            
            for idx, (mtype, murl) in enumerate(media_urls):
                if self.DOWNLOAD_MEDIA:
                    local_path = download_media(murl, f"{note_id}_{idx}", mtype)
                    if local_path:
                        content_parts.append(f'<img src="{murl}" style="max-width: 100%; margin: 10px 0; border-radius: 8px;" alt="Image{idx+1}" />')
                else:
                    content_parts.append(f'<img src="{murl}" style="max-width: 100%; margin: 10px 0; border-radius: 8px;" alt="Image{idx+1}" />')
            
            content_parts.append('</div>')
        
        # Add view original link
        content_parts.append('<hr style="margin: 20px 0; border: none; border-top: 1px solid #eee;" />')
        content_parts.append(f'<p style="text-align: center; margin: 15px 0;">')
        content_parts.append(f'<a href="{explore_url}" target="_blank" style="color: #ff2442; text-decoration: none; font-weight: bold;">View Original Note</a>')
        content_parts.append('</p>')
        
        content = '\n'.join(content_parts)
        
        # Build summary
        summary_parts = []
        if description:
            summary_parts.append(description[:200])
        summary_parts.append(f"[{media_type}]")
        summary = ' '.join(summary_parts)
        
        # Extract pure image URL list
        image_urls = [murl for mtype, murl in media_urls if mtype == "image"]
        
        return Article(
            url=explore_url,
            title=f"[{username}] {title}",
            published_at=pub_date,
            content=content,
            summary=summary,
            category=media_type,
            author=username,
            images=image_urls,
            media=[{"type": mtype, "url": murl} for mtype, murl in media_urls],
        )
    
    
    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full article content (already done in fetch_articles)."""
        return None


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=50)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--user", type=str, help="User ID, comma-separated for multiple")
    parser.add_argument("--download", action="store_true", help="Whether to download media")
    args = parser.parse_args()
    
    # Set user temporarily
    if args.user:
        os.environ["XHS_USER_ID"] = args.user
    
    if args.download:
        os.environ["XHS_DOWNLOAD_MEDIA"] = "true"
    
    logging.basicConfig(level=logging.INFO)
    
    gen = XiaohongshuUserGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
