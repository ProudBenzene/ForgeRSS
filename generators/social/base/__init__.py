"""
Shared utilities for social platform generators.

Provides cross-platform building blocks:
- Anti-throttling download helpers (yt-dlp + requests)
"""

from .download import (
    get_safe_ydl_opts,
    download_with_ytdlp,
    download_with_requests,
)

__all__ = [
    "get_safe_ydl_opts",
    "download_with_ytdlp",
    "download_with_requests",
]
