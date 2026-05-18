#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
YouTube channel video scraper.
Scrapes recent videos from configured channels (no login required).

Configuration:
1. Environment variable YOUTUBE_CHANNEL (channel ID or URL, comma-separated)
2. Or configure the CHANNELS list in code

Example:
    YOUTUBE_CHANNEL="@YouTube,UCxxxxxx" python scripts/run_single.py youtube_channel
"""

import logging
import os
import re
from datetime import datetime
from typing import Optional

import pytz

from generators.base import Article, BaseFeedGenerator

logger = logging.getLogger(__name__)


class YouTubeChannelGenerator(BaseFeedGenerator):
    """RSS generator for YouTube channel videos."""
    
    FEED_NAME = "youtube_channel"
    FEED_TITLE = "YouTube Channel Videos"
    FEED_URL = "https://www.youtube.com/"
    FEED_DESCRIPTION = "Latest videos from YouTube channels"
    FEED_LANGUAGE = "en"
    FEED_LOGO = "https://www.youtube.com/favicon.ico"
    
    # Channel list (from env var or code config)
    CHANNELS = os.environ.get("YOUTUBE_CHANNEL", "").split(",")
    CHANNELS = [ch.strip() for ch in CHANNELS if ch.strip()]
    
    # Whether to download videos (default: false, RSS only)
    DOWNLOAD_VIDEOS = os.environ.get("YOUTUBE_DOWNLOAD_VIDEOS", "false").lower() == "true"
    
    def __init__(self):
        super().__init__()

        if not self.CHANNELS:
            self.logger.warning("No channels configured. Set YOUTUBE_CHANNEL environment variable.")
            self.logger.warning("Example: YOUTUBE_CHANNEL='@YouTube,UCxxxxxx'")

    def run(self, full_refresh: bool = False, max_articles: int = 50) -> bool:
        # No config = nothing to do; treat as success so CI doesn't fail for fork users
        # who haven't opted into this platform yet.
        if not self.CHANNELS:
            self.logger.info("Skipping youtube_channel: YOUTUBE_CHANNEL not configured")
            return True
        return super().run(full_refresh=full_refresh, max_articles=max_articles)

    def fetch_articles(self) -> list[Article]:
        """Fetch latest videos from configured channels."""
        try:
            import yt_dlp
        except ImportError:
            self.logger.error("yt-dlp not installed. Run: pip install yt-dlp")
            return []
        
        articles = []
        
        for channel in self.CHANNELS:
            self.logger.info(f"Fetching videos from channel: {channel}")
            videos = self._fetch_channel_videos(channel)
            articles.extend(videos)
            self.logger.info(f"Found {len(videos)} videos from {channel}")
        
        return articles
    
    def _fetch_channel_videos(self, channel: str, max_videos: int = 20) -> list[Article]:
        """Fetch videos from a single channel."""
        import yt_dlp
        
        articles = []
        
        try:
            # 构建频道URL
            if channel.startswith('@'):
                channel_url = f"https://www.youtube.com/{channel}/videos"
            elif channel.startswith('UC'):
                channel_url = f"https://www.youtube.com/channel/{channel}/videos"
            elif channel.startswith('http'):
                channel_url = channel
            else:
                self.logger.warning(f"Unknown channel format: {channel}")
                return []
            
            # 使用yt-dlp获取频道视频列表
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,  # list only, do not download
                'playlist_items': f'1-{max_videos}',  # 限制数量
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
                
                if not info or 'entries' not in info:
                    self.logger.warning(f"No videos found for channel: {channel}")
                    return []
                
                channel_name = info.get('uploader') or info.get('channel') or channel
                
                for entry in info['entries']:
                    if not entry:
                        continue
                    
                    try:
                        article = self._parse_video_entry(entry, channel_name)
                        if article:
                            articles.append(article)
                    except Exception as e:
                        self.logger.error(f"Error parsing video: {e}")
                        continue
        
        except Exception as e:
            self.logger.error(f"Error fetching channel {channel}: {e}")
        
        return articles
    
    def _parse_video_entry(self, entry: dict, channel_name: str) -> Optional[Article]:
        """Parse a single video entry."""
        try:
            video_id = entry.get('id')
            if not video_id:
                return None
            
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            title = entry.get('title', video_id)
            description = entry.get('description', '')
            
            # Get thumbnail
            thumbnail = entry.get('thumbnail') or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            
            # 获取时长
            duration = entry.get('duration', 0)
            duration_str = self._format_duration(duration) if duration else "Unknown"
            
            # 获取发布时间
            upload_date = entry.get('upload_date')
            if upload_date:
                try:
                    pub_date = datetime.strptime(upload_date, '%Y%m%d')
                    pub_date = pub_date.replace(tzinfo=pytz.UTC)
                except:
                    pub_date = datetime.now(pytz.UTC)
            else:
                pub_date = datetime.now(pytz.UTC)
            
            # 构建内容
            content = f"""
<div style="margin-bottom: 20px;">
    <a href="{video_url}">
        <img src="{thumbnail}" style="max-width: 100%; height: auto;" />
    </a>
</div>
<p><strong>Channel:</strong> {channel_name}</p>
<p><strong>Duration:</strong> {duration_str}</p>
{f'<p>{description[:500]}...</p>' if description else ''}
<p><a href="{video_url}">Watch on YouTube</a></p>
"""
            
            # 可选：下载视频
            if self.DOWNLOAD_VIDEOS:
                self.logger.info(f"Downloading video {video_id}...")
                video_path = self._download_video(video_url, video_id)
                if video_path:
                    content += f'<p><strong>Downloaded to:</strong> {video_path}</p>'
            
            return Article(
                url=video_url,
                title=f"[{channel_name}] {title}",
                published_at=pub_date,
                content=content,
                summary=description[:200] if description else f"Video by {channel_name}",
                category="Video",
                author=channel_name,
            )
        
        except Exception as e:
            self.logger.error(f"Error parsing video entry: {e}")
            return None
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to HH:MM:SS."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    def _download_video(self, url: str, video_id: str) -> Optional[str]:
        """Download video using yt-dlp."""
        import yt_dlp
        from pathlib import Path
        
        output_dir = Path(__file__).parent.parent.parent / "downloads" / "youtube"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_template = str(output_dir / f"{video_id}.%(ext)s")
        
        ydl_opts = {
            'outtmpl': output_template,
            'format': 'best[ext=mp4]/best',  # 优先MP4格式
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
    parser.add_argument("--channel", type=str, help="频道ID或@handle，多个用逗号分隔")
    parser.add_argument("--download", action="store_true", help="是否下载视频")
    args = parser.parse_args()
    
    # 临时设置频道
    if args.channel:
        os.environ["YOUTUBE_CHANNEL"] = args.channel
    
    if args.download:
        os.environ["YOUTUBE_DOWNLOAD_VIDEOS"] = "true"
    
    logging.basicConfig(level=logging.INFO)
    
    gen = YouTubeChannelGenerator()
    gen.run(full_refresh=args.full, max_articles=args.max)
