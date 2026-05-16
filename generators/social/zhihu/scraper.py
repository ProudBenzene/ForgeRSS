#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Zhihu base utilities for all Zhihu generators.

Base scraping tools for Zhihu

Requires:
1. DrissionPage installed
2. Logged-in browser profile at ZHIHU_PROFILE_DIR
3. Desktop environment (non-headless mode)

Usage:
1. First time: run `python -m generators.social.zhihu.scraper --login`
2. Then run generators normally
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default profile directory (can be overridden by env var)
# 3 levels up from generators/social/zhihu to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PROFILES_ROOT = PROJECT_ROOT / "profiles"

# Zhihu profile directory (can be overridden by env var)
ZHIHU_PROFILE_DIR = Path(
    os.environ.get("ZHIHU_PROFILE_DIR", PROFILES_ROOT / "zhihu")
)

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    HAS_DRISSION = True
except ImportError:
    HAS_DRISSION = False
    ChromiumPage = None
    ChromiumOptions = None


def check_zhihu_ready() -> tuple[bool, str]:
    """
    Check if Zhihu scraping is ready.
    Returns (ready, message).
    """
    if not HAS_DRISSION:
        return False, "DrissionPage not installed. Run: pip install DrissionPage"
    
    if not ZHIHU_PROFILE_DIR.exists():
        return False, f"Profile not found at {ZHIHU_PROFILE_DIR}. Run: python -m generators.social.zhihu.scraper --login"
    
    return True, "Ready"


def create_zhihu_browser(headless: bool = False) -> Optional["ChromiumPage"]:
    """
    Create browser with Zhihu login session.
    
    Args:
        headless: Whether to run headless (may trigger anti-bot)
    
    Returns:
        ChromiumPage instance or None if not ready
    """
    ready, msg = check_zhihu_ready()
    if not ready:
        logger.error(msg)
        return None
    
    co = ChromiumOptions()
    co.set_user_data_path(str(ZHIHU_PROFILE_DIR))
    
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


def verify_zhihu_login(browser: "ChromiumPage", notify_on_failure: bool = True) -> bool:
    """
    Check if browser is logged into Zhihu.
    
    Args:
        browser: ChromiumPage browser instance
        notify_on_failure: Whether to notify on login failure
        
    Returns:
        True if logged in, False otherwise
    """
    try:
        from generators.utils.login_checker import Platform, LoginChecker
        
        checker = LoginChecker()
        status, message = checker.check_login(Platform.ZHIHU, browser)
        
        # Login verified
        if status.value == "logged_in":
            logger.info(f"Zhihu login verified: {message}")
            return True
        
        # Login failed
        logger.warning(f"Zhihu login failed: {message}")
        
        if notify_on_failure:
            checker.notify_login_expired(Platform.ZHIHU, method="all")
            logger.error(f"Please re-login to Zhihu: {checker.get_login_command(Platform.ZHIHU)}")
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to verify login: {e}")
        return False


def do_zhihu_login():
    """Interactive login flow."""
    if not HAS_DRISSION:
        print("ERROR: DrissionPage not installed")
        print("Run: pip install DrissionPage")
        return
    
    print("=" * 60)
    print("Zhihu Login Setup")
    print("=" * 60)
    print(f"Profile directory: {ZHIHU_PROFILE_DIR}")
    print()
    print("Browser will open. Please:")
    print("1. Login to Zhihu (scan QR code or use phone)")
    print("2. After login success, come back and press Enter")
    print("=" * 60)
    
    # Clean old profile if exists
    if ZHIHU_PROFILE_DIR.exists():
        confirm = input(f"\nProfile exists. Delete and create new? [y/N]: ")
        if confirm.lower() == 'y':
            shutil.rmtree(ZHIHU_PROFILE_DIR)
            print("Old profile removed.")
        else:
            print("Keeping existing profile.")
    
    co = ChromiumOptions()
    co.set_user_data_path(str(ZHIHU_PROFILE_DIR))
    co.set_argument("--disable-blink-features=AutomationControlled")
    
    browser = ChromiumPage(co)
    browser.get("https://www.zhihu.com/signin")
    
    input("\nPress Enter after you've logged in...")
    
    # Verify
    if verify_zhihu_login(browser):
        print("\nLogin successful! Profile saved.")
        print(f"Profile location: {ZHIHU_PROFILE_DIR}")
    else:
        print("\nLogin verification failed. Please try again.")
    
    browser.quit()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Zhihu login setup")
    parser.add_argument("--login", action="store_true", help="Start login flow")
    parser.add_argument("--check", action="store_true", help="Check login status")
    args = parser.parse_args()
    
    if args.login:
        do_zhihu_login()
    elif args.check:
        ready, msg = check_zhihu_ready()
        print(f"Ready: {ready}")
        print(f"Message: {msg}")
        
        if ready:
            browser = create_zhihu_browser(headless=False)
            if browser:
                logged_in = verify_zhihu_login(browser)
                print(f"Logged in: {logged_in}")
                browser.quit()
    else:
        parser.print_help()
