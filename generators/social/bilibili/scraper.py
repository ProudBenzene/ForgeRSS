#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Bilibili base utilities for all Bilibili generators.
Bilibili scraper utilities

Requires:
1. DrissionPage installed
2. Logged-in browser profile at BILIBILI_PROFILE_DIR
3. Desktop environment (non-headless mode)
4. yt-dlp for video downloads (optional)

Usage:
1. First time: run `python -m generators.social.bilibili.scraper --login`
2. Then run generators normally
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Unified profile root directory (browser profile for all platforms)
# generators/social/bilibili -> project root: 4 parent() calls
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PROFILES_ROOT = PROJECT_ROOT / "profiles"

# Bilibili profile directory (can be overridden by env var)
BILIBILI_PROFILE_DIR = Path(
    os.environ.get("BILIBILI_PROFILE_DIR", PROFILES_ROOT / "bilibili")
)

# Video download directory (<project_root>/downloads/bilibili)
VIDEO_DOWNLOAD_DIR = Path(
    os.environ.get("VIDEO_DOWNLOAD_DIR", PROJECT_ROOT / "downloads" / "bilibili")
)

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    HAS_DRISSION = True
except ImportError:
    HAS_DRISSION = False
    ChromiumPage = None
    ChromiumOptions = None


def check_bilibili_ready() -> tuple[bool, str]:
    """
    Check if Bilibili scraping is ready.
    Returns (ready, message).
    """
    if not HAS_DRISSION:
        return False, "DrissionPage not installed. Run: pip install DrissionPage"
    
    if not BILIBILI_PROFILE_DIR.exists():
        return False, f"Profile not found at {BILIBILI_PROFILE_DIR}. Run: python -m generators.social.bilibili.scraper --login"
    
    return True, "Ready"


def create_bilibili_browser(headless: bool = False) -> Optional["ChromiumPage"]:
    """
    Create browser with Bilibili login session.
    
    Args:
        headless: Whether to run headless (may trigger anti-bot)
    
    Returns:
        ChromiumPage instance or None if not ready
    """
    ready, msg = check_bilibili_ready()
    if not ready:
        logger.error(msg)
        return None
    
    co = ChromiumOptions()
    co.set_user_data_path(str(BILIBILI_PROFILE_DIR))
    
    if headless:
        co.headless()
    
    # Anti-detection
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    co.set_argument("--disable-infobars")
    
    try:
        browser = ChromiumPage(co)
        return browser
    except Exception as e:
        logger.error(f"Failed to create browser: {e}")
        return None


def verify_bilibili_login(browser: "ChromiumPage", notify_on_failure: bool = True) -> bool:
    """
    Check if browser is logged into Bilibili.
    
    Args:
        browser: ChromiumPage browser instance
        notify_on_failure: Whether to notify on login failure
        
    Returns:
        True if logged in, False otherwise
    """
    try:
        from generators.utils.login_checker import Platform, LoginChecker
        
        checker = LoginChecker()
        status, message = checker.check_login(Platform.BILIBILI, browser)
        
        if status.value == "logged_in":
            logger.info(f"Bilibili login verified: {message}")
            return True
        
        logger.warning(f"Bilibili login verification failed: {message}")
        
        if notify_on_failure:
            checker.notify_login_expired(Platform.BILIBILI, method="all")
            logger.error(f"Please re-login to Bilibili: {checker.get_login_command(Platform.BILIBILI)}")
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to verify login: {e}")
        return False


def download_video(bvid: str, output_dir: Optional[Path] = None, browser=None) -> Optional[Path]:
    """
    Download Bilibili video using yt-dlp.
    
    Args:
        bvid: Bilibili video ID (e.g., "BV1xx411c7mD")
        output_dir: Output directory (default: VIDEO_DOWNLOAD_DIR)
        browser: DrissionPage browser instance (for cookies)
    
    Returns:
        Path to downloaded video or None if failed
    """
    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt-dlp not installed. Run: pip install yt-dlp")
        return None
    
    if output_dir is None:
        output_dir = VIDEO_DOWNLOAD_DIR
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    url = f"https://www.bilibili.com/video/{bvid}"
    output_template = str(output_dir / f"{bvid}.%(ext)s")
    
    ydl_opts = {
        'outtmpl': output_template,
        'format': 'bestvideo+bestaudio/best',  # merge best video + audio, or fallback to best single format
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',  # merge to mp4
        # Anti-throttling config
        'retries': 10,                    # auto retry 10 times
        'fragment_retries': 10,           # fragment retry 10 times
        'file_access_retries': 5,         # file access retry
        'extractor_retries': 3,           # extractor retry
        'ratelimit': 3 * 1024 * 1024,     # cap 3 MB/s (Bilibili tends to have generous bandwidth)
        'throttledratelimit': 1024 * 1024, # drop to 1 MB/s when throttled
        'sleep_interval': 1,              # request interval 1s
        'max_sleep_interval': 3,          # max interval 3s
        'sleep_interval_requests': 1,     # sleep 1s per request
    }
    
    # If a browser instance is provided, pass its cookies to yt-dlp
    if browser and HAS_DRISSION:
        try:
            from http.cookiejar import Cookie, CookieJar
            
            cookies = browser.cookies(all_domains=True)
            if cookies:
                # Create a CookieJar (natively supported by yt-dlp)
                cookiejar = CookieJar()
                
                for cookie in cookies:
                    # Convert to a standard Cookie object
                    cookie_obj = Cookie(
                        version=0,
                        name=cookie.get('name', ''),
                        value=cookie.get('value', ''),
                        port=None,
                        port_specified=False,
                        domain=cookie.get('domain', '.bilibili.com'),
                        domain_specified=True,
                        domain_initial_dot=cookie.get('domain', '').startswith('.'),
                        path=cookie.get('path', '/'),
                        path_specified=True,
                        secure=cookie.get('secure', False),
                        expires=cookie.get('expires'),
                        discard=False,
                        comment=None,
                        comment_url=None,
                        rest={},
                    )
                    cookiejar.set_cookie(cookie_obj)
                
                # Use the cookiejar parameter (more stable)
                ydl_opts['cookiejar'] = cookiejar
                logger.info(f"Using {len(cookies)} cookies from browser for download")
        except Exception as e:
            logger.warning(f"Failed to extract cookies: {e}, downloading without login")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            logger.info(f"Downloaded video: {filename}")
            return Path(filename)
    except Exception as e:
        logger.error(f"Failed to download video {bvid}: {e}")
        return None


def do_bilibili_login():
    """Interactive login flow."""
    if not HAS_DRISSION:
        print("ERROR: DrissionPage not installed")
        print("Run: pip install DrissionPage")
        return
    
    print("=" * 60)
    print("Bilibili Login Setup")
    print("=" * 60)
    print(f"Profile directory: {BILIBILI_PROFILE_DIR}")
    print()
    print("Browser will open. Please:")
    print("1. Login to Bilibili (scan QR code or use SMS)")
    print("2. After login success, come back and press Enter")
    print("=" * 60)
    
    # Clean old profile if exists
    if BILIBILI_PROFILE_DIR.exists():
        confirm = input(f"\nProfile exists. Delete and create new? [y/N]: ")
        if confirm.lower() == 'y':
            shutil.rmtree(BILIBILI_PROFILE_DIR)
            print("Old profile removed.")
        else:
            print("Keeping existing profile.")
    
    co = ChromiumOptions()
    co.set_user_data_path(str(BILIBILI_PROFILE_DIR))
    co.set_argument("--disable-blink-features=AutomationControlled")
    
    browser = ChromiumPage(co)
    browser.get("https://passport.bilibili.com/login")
    
    input("\nPress Enter after you've logged in...")
    
    # Verify
    if verify_bilibili_login(browser):
        print("\nLogin successful! Profile saved.")
        print(f"Profile location: {BILIBILI_PROFILE_DIR}")
    else:
        print("\nLogin verification failed. Please try again.")
    
    browser.quit()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Bilibili login setup")
    parser.add_argument("--login", action="store_true", help="Start login flow")
    parser.add_argument("--check", action="store_true", help="Check login status")
    args = parser.parse_args()
    
    if args.login:
        do_bilibili_login()
    elif args.check:
        ready, msg = check_bilibili_ready()
        print(f"Ready: {ready}")
        print(f"Message: {msg}")
        
        if ready:
            browser = create_bilibili_browser(headless=False)
            if browser:
                logged_in = verify_bilibili_login(browser)
                print(f"Logged in: {logged_in}")
                browser.quit()
    else:
        parser.print_help()
