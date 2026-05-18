#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
TikTok user video scraper.
Scrapes recent videos from configured users (no login required).

Configuration:
1. Environment variable TIKTOK_USER (usernames, comma-separated)
2. Or configure the USERS list in code

Example:
    TIKTOK_USER="@username1,@username2" python scripts/run_single.py tiktok_user
"""

import logging
import os
from datetime import datetime
from typing import Optional

import pytz

from generators.base import Article, BaseFeedGenerator

logger = logging.getLogger(__name__)


class TikTokUserGenerator(BaseFeedGenerator):
    """RSS generator for TikTok user videos."""
    
    FEED_NAME = "tiktok_user"
    FEED_TITLE = "TikTok User Videos"
    FEED_URL = "https://www.tiktok.com/"
    FEED_DESCRIPTION = "Latest videos from TikTok users"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://www.tiktok.com/favicon.ico"
    
    # User list (from env var or code config)
    USERS = os.environ.get("TIKTOK_USER", "").split(",")
    USERS = [u.strip().lstrip('@') for u in USERS if u.strip()]
    
    # Whether to download videos (default: false, RSS only)
    DOWNLOAD_VIDEOS = os.environ.get("TIKTOK_DOWNLOAD_VIDEOS", "false").lower() == "true"
    
    def __init__(self):
        super().__init__()

        if not self.USERS:
            self.logger.warning("No users configured. Set TIKTOK_USER environment variable.")
            self.logger.warning("Example: TIKTOK_USER='@username1,@username2'")

    def run(self, full_refresh: bool = False, max_articles: int = 50) -> bool:
        # No config = nothing to do; treat as success so CI doesn't fail for fork users
        # who haven't opted into this platform yet.
        if not self.USERS:
            self.logger.info("Skipping tiktok_user: TIKTOK_USER not configured")
            return True
        return super().run(full_refresh=full_refresh, max_articles=max_articles)

    def fetch_articles(self) -> list[Article]:
        """Fetch latest videos from configured users."""
        try:
            import yt_dlp
        except ImportError:
            self.logger.error("yt-dlp not installed. Run: pip install yt-dlp")
            return []
        
        articles = []
        
        for user in self.USERS:
            self.logger.info(f"Fetching videos from user: @{user}")
            videos = self._fetch_user_videos(user)
            articles.extend(videos)
            self.logger.info(f"Found {len(videos)} videos from @{user}")
        
        return articles
    
    def _fetch_user_videos(self, username: str, max_videos: int = 20) -> list[Article]:
        """Fetch videos from a single user."""
        import yt_dlp
        
        articles = []
        
        try:
            user_url = f"https://www.tiktok.com/@{username}"
            
            # 使用yt-dlp获取用户视频列表
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,  # list only, do not download
                'playlist_items': f'1-{max_videos}',  # 限制数量
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(user_url, download=False)
                
                if not info or 'entries' not in info:
                    self.logger.warning(f"No videos found for user: @{username}")
                    return []
                
                for entry in info['entries']:
                    if not entry:
                        continue
                    
                    try:
                        article = self._parse_video_entry(entry, username)
                        if article:
                            articles.append(article)
                    except Exception as e:
                        self.logger.error(f"Error parsing video: {e}")
                        continue
        
        except Exception as e:
            self.logger.error(f"Error fetching user @{username}: {e}")
        
        return articles
    
    def _parse_video_entry(self, entry: dict, username: str) -> Optional[Article]:
        """Parse a single video entry."""
        try:
            video_id = entry.get('id')
            if not video_id:
                return None
            
            video_url = entry.get('url') or entry.get('webpage_url')
            if not video_url:
                video_url = f"https://www.tiktok.com/@{username}/video/{video_id}"
            
            title = entry.get('title') or entry.get('description', '')[:100] or video_id
            description = entry.get('description', '')
            
            # Get thumbnail
            thumbnail = entry.get('thumbnail', '')
            
            # 获取时长
            duration = entry.get('duration', 0)
            duration_str = f"{int(duration)}s" if duration else "Unknown"
            
            # 获取播放量、点赞数
            view_count = entry.get('view_count', 0)
            like_count = entry.get('like_count', 0)
            
            # 获取发布时间
            timestamp = entry.get('timestamp')
            if timestamp:
                pub_date = datetime.fromtimestamp(timestamp, tz=pytz.UTC)
            else:
                pub_date = datetime.now(pytz.UTC)
            
            # 构建内容
            content_parts = []
            if thumbnail:
                content_parts.append(f'<div style="margin-bottom: 20px;"><a href="{video_url}"><img src="{thumbnail}" style="max-width: 100%; height: auto;" /></a></div>')
            
            content_parts.append(f'<p><strong>User:</strong> @{username}</p>')
            content_parts.append(f'<p><strong>Duration:</strong> {duration_str}</p>')
            
            if view_count:
                content_parts.append(f'<p><strong>Views:</strong> {view_count:,} | <strong>Likes:</strong> {like_count:,}</p>')
            
            if description:
                content_parts.append(f'<p>{description}</p>')
            
            content_parts.append(f'<p><a href="{video_url}">Watch on TikTok</a></p>')
            
            # 可选：下载视频
            if self.DOWNLOAD_VIDEOS:
                self.logger.info(f"Downloading video {video_id}...")
                video_path = self._download_video(video_url, video_id)
                if video_path:
                    content_parts.append(f'<p><strong>Downloaded to:</strong> {video_path}</p>')
            
            content = '\n'.join(content_parts)
            
            return Article(
                url=video_url,
                title=f"[@{username}] {title}",
                published_at=pub_date,
                content=content,
                summary=description[:200] if description else f"Video by @{username}",
                category="Video",
                author=f"@{username}",
            )
        
        except Exception as e:
            self.logger.error(f"Error parsing video entry: {e}")
            return None
    
    def _download_video(self, url: str, video_id: str) -> Optional[str]:
        """Download video using yt-dlp."""
        import yt_dlp
        from pathlib import Path
        
        output_dir = Path(__file__).parent.parent.parent / "downloads" / "tiktok"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_template = str(output_dir / f"{video_id}.%(ext)s")
        
        ydl_opts = {
            'outtmpl': output_template,
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                self.logger.info(f"Downloaded: {filename}")
                return filename
        except Exception as e:
            self.logger.error(f"Failed to download {video_id}: {e}")
            return None
    
    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch full article content (already done in fetch_articles)."""
        return None


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=50)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--user", type=str, help="用户名，多个用逗号分隔")
    parser.add_argument("--download", action="store_true", help="是否下载视频")
    args = parser.parse_args()
    
    # 临时设置用户
    if args.user:
        os.environ["TIKTOK_USER"] = args.user
    
    if args.download:
        os.environ["TIKTOK_DOWNLOAD_VIDEOS"] = "true"
    
    logging.basicConfig(level=logging.INFO)
    
    gen = TikTokUserGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)