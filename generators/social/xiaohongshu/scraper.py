#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Xiaohongshu (Little Red Book) base utilities.
小红书抓取基础工具

Requires:
1. DrissionPage installed
2. Logged-in browser profile at XHS_PROFILE_DIR
3. Desktop environment (non-headless mode)

Usage:
1. First time: run `python -m generators.social.xiaohongshu.scraper --login`
2. Then run generators normally
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Unified profile root directory
# generators/social/xiaohongshu -> project root: 4 parent() calls
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PROFILES_ROOT = PROJECT_ROOT / "profiles"

# Xiaohongshu profile directory (can be overridden by env var)
XHS_PROFILE_DIR = Path(
    os.environ.get("XHS_PROFILE_DIR", PROFILES_ROOT / "xiaohongshu")
)

# Media download directory (<project_root>/downloads/xiaohongshu)
MEDIA_DOWNLOAD_DIR = Path(
    os.environ.get("MEDIA_DOWNLOAD_DIR", PROJECT_ROOT / "downloads" / "xiaohongshu")
)

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    HAS_DRISSION = True
except ImportError:
    HAS_DRISSION = False
    ChromiumPage = None
    ChromiumOptions = None


def check_xhs_ready() -> tuple[bool, str]:
    """
    Check if Xiaohongshu scraping is ready.
    Returns (ready, message).
    """
    if not HAS_DRISSION:
        return False, "DrissionPage not installed. Run: pip install DrissionPage"
    
    if not XHS_PROFILE_DIR.exists():
        return False, f"Profile not found at {XHS_PROFILE_DIR}. Run: python -m generators.social.xiaohongshu.scraper --login"
    
    return True, "Ready"


def create_xhs_browser(headless: bool = False) -> Optional["ChromiumPage"]:
    """
    Create browser with Xiaohongshu login session.
    
    Args:
        headless: Whether to run headless (may trigger anti-bot)
    
    Returns:
        ChromiumPage instance or None if not ready
    """
    ready, msg = check_xhs_ready()
    if not ready:
        logger.error(msg)
        return None
    
    co = ChromiumOptions()
    co.set_user_data_path(str(XHS_PROFILE_DIR))
    
    if headless:
        co.headless()
    
    # Anti-detection (Xiaohongshu has relatively strict anti-bot)
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    co.set_argument("--disable-infobars")
    
    # Additional stealth options for XHS
    co.set_argument("--disable-web-security")
    co.set_argument("--allow-running-insecure-content")
    
    try:
        browser = ChromiumPage(co)
        return browser
    except Exception as e:
        logger.error(f"Failed to create browser: {e}")
        return None


def verify_xhs_login(browser: "ChromiumPage", notify_on_failure: bool = True) -> bool:
    """
    Check if browser is logged into Xiaohongshu.
    
    Args:
        browser: ChromiumPage browser instance
        notify_on_failure: 登录失败时是否发送通知
        
    Returns:
        True if logged in, False otherwise
    """
    try:
        from generators.utils.login_checker import Platform, LoginChecker
        
        checker = LoginChecker()
        status, message = checker.check_login(Platform.XIAOHONGSHU, browser)
        
        if status.value == "logged_in":
            logger.info(f"Xiaohongshu login verified: {message}")
            return True
        
        logger.warning(f"Xiaohongshu login verification failed: {message}")
        
        if notify_on_failure:
            checker.notify_login_expired(Platform.XIAOHONGSHU, method="all")
            logger.error(f"Please re-login to Xiaohongshu: {checker.get_login_command(Platform.XIAOHONGSHU)}")
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to verify login: {e}")
        return False


def download_media(url: str, note_id: str, media_type: str = "image", output_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Download Xiaohongshu media (image or video).
    
    Args:
        url: Media URL or note URL (for video)
        note_id: Note ID for filename
        media_type: "image" or "video"
        output_dir: Output directory (default: MEDIA_DOWNLOAD_DIR)
    
    Returns:
        Path to downloaded media or None if failed
    """
    if output_dir is None:
        output_dir = MEDIA_DOWNLOAD_DIR
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # For videos, try yt-dlp first (supports xiaohongshu)
    if media_type == "video":
        try:
            import yt_dlp
            
            output_template = str(output_dir / f"{note_id}.%(ext)s")
            ydl_opts = {
                'outtmpl': output_template,
                'format': 'best',
                'quiet': True,
                'no_warnings': True,
                # Anti-throttling config
                'retries': 10,                    # auto retry 10 times
                'fragment_retries': 10,           # fragment retry 10 times
                'file_access_retries': 5,         # file access retry
                'extractor_retries': 3,           # extractor retry
                'ratelimit': 2 * 1024 * 1024,     # cap 2 MB/s to avoid CDN throttle
                'throttledratelimit': 500 * 1024, # drop to 500 KB/s when throttled
                'sleep_interval': 1,              # request interval 1s
                'max_sleep_interval': 3,          # max interval 3s
                'sleep_interval_requests': 1,     # sleep 1s per request
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://www.xiaohongshu.com/'
                }
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                logger.info(f"Downloaded video: {filename}")
                return Path(filename)
        except ImportError:
            logger.warning("yt-dlp not installed, falling back to requests for video download")
        except Exception as e:
            logger.error(f"Failed to download video with yt-dlp: {e}")
            logger.info("Falling back to direct download...")
    
    # For images or fallback, use requests
    import requests
    
    # Check if the file already exists
    ext = "jpg" if media_type == "image" else "mp4"
    output_path = output_dir / f"{note_id}.{ext}"
    
    if output_path.exists():
        logger.info(f"Media already exists: {output_path}")
        return output_path
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.xiaohongshu.com/",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8" if media_type == "image" else "*/*"
        }
        
        response = requests.get(url, headers=headers, timeout=60, stream=True)
        response.raise_for_status()
        
        # Get file size
        total_size = int(response.headers.get('content-length', 0))
        
        with open(output_path, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
        
        # Verify file size
        if output_path.stat().st_size == 0:
            logger.error(f"Downloaded file is empty: {output_path}")
            output_path.unlink()
            return None
        
        logger.info(f"Downloaded {media_type}: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")
        return output_path
    except Exception as e:
        logger.error(f"Failed to download {media_type} from {url}: {e}")
        if output_path.exists():
            output_path.unlink()
        return None


def do_xhs_login():
    """Interactive login flow."""
    if not HAS_DRISSION:
        print("ERROR: DrissionPage not installed")
        print("Run: pip install DrissionPage")
        return
    
    print("=" * 60)
    print("Xiaohongshu Login Setup")
    print("=" * 60)
    print(f"Profile directory: {XHS_PROFILE_DIR}")
    print()
    print("Browser will open. Please:")
    print("1. Login to Xiaohongshu (scan QR code or use SMS)")
    print("2. After login success, come back and press Enter")
    print("=" * 60)
    
    # Clean old profile if exists
    if XHS_PROFILE_DIR.exists():
        confirm = input(f"\nProfile exists. Delete and create new? [y/N]: ")
        if confirm.lower() == 'y':
            shutil.rmtree(XHS_PROFILE_DIR)
            print("Old profile removed.")
        else:
            print("Keeping existing profile.")
    
    co = ChromiumOptions()
    co.set_user_data_path(str(XHS_PROFILE_DIR))
    co.set_argument("--disable-blink-features=AutomationControlled")
    
    browser = ChromiumPage(co)
    browser.get("https://www.xiaohongshu.com/")
    
    input("\nPress Enter after you've logged in...")
    
    # Verify
    if verify_xhs_login(browser):
        print("\nLogin successful! Profile saved.")
        print(f"Profile location: {XHS_PROFILE_DIR}")
    else:
        print("\nLogin verification failed. Please try again.")
    
    browser.quit()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Xiaohongshu login setup")
    parser.add_argument("--login", action="store_true", help="Start login flow")
    parser.add_argument("--check", action="store_true", help="Check login status")
    args = parser.parse_args()
    
    if args.login:
        do_xhs_login()
    elif args.check:
        ready, msg = check_xhs_ready()
        print(f"Ready: {ready}")
        print(f"Message: {msg}")
        
        if ready:
            browser = create_xhs_browser(headless=False)
            if browser:
                logged_in = verify_xhs_login(browser)
                print(f"Logged in: {logged_in}")
                browser.quit()
    else:
        parser.print_help()
