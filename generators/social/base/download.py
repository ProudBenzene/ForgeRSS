"""
Shared download helpers for social-platform media (anti-throttling defaults).
"""
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_safe_ydl_opts(
    output_template: str,
    format_spec: str = 'best',
    referer: str = None,
    rate_limit_mb: float = 2.0,
    extra_opts: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Build a yt-dlp options dict with anti-throttling defaults.

    Args:
        output_template: yt-dlp output path template (e.g. "downloads/video_%(id)s.%(ext)s").
        format_spec: yt-dlp format selector (e.g. 'best', 'bestvideo+bestaudio/best').
        referer: HTTP Referer header.
        rate_limit_mb: Rate limit in MB/s (default 2 MB/s).
        extra_opts: Additional yt-dlp options to merge in.

    Returns:
        yt-dlp options dict.
    """
    ydl_opts = {
        'outtmpl': output_template,
        'format': format_spec,
        'quiet': True,
        'no_warnings': True,

        # Anti-throttling defaults
        'retries': 10,
        'fragment_retries': 10,
        'file_access_retries': 5,
        'extractor_retries': 3,
        'ratelimit': int(rate_limit_mb * 1024 * 1024),
        'throttledratelimit': int(rate_limit_mb * 0.5 * 1024 * 1024),  # 50% when throttled
        'sleep_interval': 1,
        'max_sleep_interval': 3,
        'sleep_interval_requests': 1,

        # HTTP headers
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        }
    }

    if referer:
        ydl_opts['http_headers']['Referer'] = referer

    if extra_opts:
        ydl_opts.update(extra_opts)

    return ydl_opts


def download_with_ytdlp(
    url: str,
    output_dir: Path,
    filename_base: str,
    platform: str = 'generic',
    format_spec: str = 'best',
    rate_limit_mb: float = 2.0,
    cookies_jar=None
) -> Optional[Path]:
    """
    Download media with yt-dlp (generic helper).

    Args:
        url: Media URL or page URL.
        output_dir: Output directory.
        filename_base: Base filename without extension.
        platform: Platform key used to pick Referer ('xiaohongshu', 'bilibili', 'weixin', ...).
        format_spec: yt-dlp format selector.
        rate_limit_mb: Rate limit in MB/s.
        cookies_jar: Optional cookiejar to pass to yt-dlp.

    Returns:
        Path to downloaded file, or None on failure.
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp not installed. Run: pip install yt-dlp")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / f"{filename_base}.%(ext)s")

    referer_map = {
        'xiaohongshu': 'https://www.xiaohongshu.com/',
        'bilibili': 'https://www.bilibili.com/',
        'weixin': 'https://channels.weixin.qq.com/',
        'douyin': 'https://www.douyin.com/',
        'kuaishou': 'https://www.kuaishou.com/',
    }
    referer = referer_map.get(platform)

    ydl_opts = get_safe_ydl_opts(
        output_template=output_template,
        format_spec=format_spec,
        referer=referer,
        rate_limit_mb=rate_limit_mb,
    )

    if cookies_jar:
        ydl_opts['cookiejar'] = cookies_jar

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            result_path = Path(filename)

            if result_path.exists():
                logger.info(
                    f"Downloaded: {result_path} "
                    f"({result_path.stat().st_size / (1024 * 1024):.1f} MB)"
                )
                return result_path
            logger.error(f"Download completed but file not found: {filename}")
            return None
    except Exception as e:
        logger.error(f"Failed to download with yt-dlp: {e}")
        return None


def download_with_requests(
    url: str,
    output_path: Path,
    referer: str = None,
    timeout: int = 60,
    chunk_size: int = 8192
) -> Optional[Path]:
    """
    Download media with requests (fallback path).

    Args:
        url: Direct media URL.
        output_path: Output file path.
        referer: HTTP Referer.
        timeout: Request timeout in seconds.
        chunk_size: Streaming chunk size.

    Returns:
        Path to downloaded file, or None on failure.
    """
    try:
        import requests
    except ImportError:
        logger.error("requests not installed")
        return None

    if output_path.exists():
        logger.info(f"File already exists: {output_path}")
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    if referer:
        headers['Referer'] = referer

    try:
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)

        if output_path.stat().st_size == 0:
            logger.error(f"Downloaded file is empty: {output_path}")
            output_path.unlink()
            return None

        logger.info(
            f"Downloaded: {output_path} "
            f"({output_path.stat().st_size / 1024:.1f} KB)"
        )
        return output_path
    except Exception as e:
        logger.error(f"Failed to download with requests: {e}")
        if output_path.exists():
            output_path.unlink()
        return None


if __name__ == "__main__":
    print("=== Xiaohongshu config example ===")
    opts = get_safe_ydl_opts(
        output_template="downloads/xhs_%(id)s.%(ext)s",
        format_spec='best',
        referer='https://www.xiaohongshu.com/',
        rate_limit_mb=2.0,
    )
    print(f"Retries: {opts['retries']}")
    print(f"Rate limit: {opts['ratelimit'] / (1024 * 1024):.1f} MB/s")
    print(f"Sleep interval: {opts['sleep_interval']}s")
    print()

    print("=== Bilibili config example ===")
    opts = get_safe_ydl_opts(
        output_template="downloads/bili_%(id)s.%(ext)s",
        format_spec='bestvideo+bestaudio/best',
        referer='https://www.bilibili.com/',
        rate_limit_mb=3.0,
        extra_opts={'merge_output_format': 'mp4'},
    )
    print(f"Format: {opts['format']}")
    print(f"Merge format: {opts.get('merge_output_format')}")
    print(f"Rate limit: {opts['ratelimit'] / (1024 * 1024):.1f} MB/s")
