#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
ZSXQ (Knowledge Planet) Base Utilities

Features:
1. Requires login (WeChat scan or phone number)
2. Can only access joined groups
3. Content types: topics, featured, Q&A

Requires:
1. DrissionPage installed
2. Logged-in browser profile at ZSXQ_PROFILE_DIR
3. Desktop environment (non-headless mode)

Usage:
1. First time: run `python -m generators.social.zsxq.scraper --login`
2. Then run generators normally
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Unified Profile root directory
# 3 levels up from generators/social/zsxq to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PROFILES_ROOT = PROJECT_ROOT / "profiles"

# System Edge browser config directory (Windows-only). On non-Windows hosts
# LOCALAPPDATA is unset, so guard against constructing Path(None).
_localappdata = os.environ.get("LOCALAPPDATA")
EDGE_USER_DATA = (
    Path(_localappdata) / "Microsoft" / "Edge" / "User Data"
    if _localappdata else None
)

# ZSXQ profile directory (can be overridden by env var)
# Priority: env var > system Edge (if exists) > create new profile
if os.environ.get("ZSXQ_PROFILE_DIR"):
    ZSXQ_PROFILE_DIR = Path(os.environ.get("ZSXQ_PROFILE_DIR"))
elif (
    os.environ.get("ZSXQ_USE_SYSTEM_EDGE", "").lower() == "true"
    and EDGE_USER_DATA
    and EDGE_USER_DATA.exists()
):
    ZSXQ_PROFILE_DIR = EDGE_USER_DATA
    logger.info(f"Using system Edge profile: {EDGE_USER_DATA}")
else:
    ZSXQ_PROFILE_DIR = PROFILES_ROOT / "zsxq"

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    HAS_DRISSION = True
except ImportError:
    HAS_DRISSION = False
    logger.warning("DrissionPage not installed. Social media scraping disabled.")


def check_zsxq_ready() -> tuple[bool, str]:
    """
    Check if ZSXQ scraping is ready.
    
    Returns:
        (ready, message)
    """
    if not HAS_DRISSION:
        return False, "DrissionPage not installed. Run: pip install DrissionPage"
    
    if not ZSXQ_PROFILE_DIR.exists():
        return False, f"ZSXQ profile not found at {ZSXQ_PROFILE_DIR}. Run: python -m generators.social.zsxq.scraper --login"
    
    return True, "ZSXQ ready"


def create_zsxq_browser(headless: bool = False) -> Optional["ChromiumPage"]:
    """
    Create a browser instance with ZSXQ login state.
    
    Args:
        headless: Run in headless mode (default: False, ZSXQ may detect headless)
    
    Returns:
        ChromiumPage instance or None if failed
    """
    ready, msg = check_zsxq_ready()
    if not ready:
        logger.error(msg)
        return None
    
    co = ChromiumOptions()
    co.set_user_data_path(str(ZSXQ_PROFILE_DIR))
    
    if headless:
        co.headless()
    
    # Anti-detection (ZSXQ has weak anti-scraping, basic settings are enough)
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


def verify_zsxq_login(browser: "ChromiumPage", notify_on_failure: bool = True) -> bool:
    """
    Check if browser is logged into ZSXQ.
    
    Args:
        browser: ChromiumPage browser instance
        notify_on_failure: Whether to notify on login failure
        
    Returns:
        True if logged in, False otherwise
    """
    try:
        from generators.utils.login_checker import Platform, LoginChecker
        
        checker = LoginChecker()
        status, message = checker.check_login(Platform.ZSXQ, browser)
        
        if status.value == "logged_in":
            logger.info(f"ZSXQ login verified: {message}")
            return True
        
        logger.warning(f"ZSXQ login failed: {message}")
        
        if notify_on_failure:
            checker.notify_login_expired(Platform.ZSXQ, method="all")
            logger.error(f"Please re-login: {checker.get_login_command(Platform.ZSXQ)}")
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to verify login: {e}")
        return False


def do_zsxq_login():
    """Interactive login flow."""
    if not HAS_DRISSION:
        print("ERROR: DrissionPage not installed")
        print("Run: pip install DrissionPage")
        return
    
    print("=" * 60)
    print("ZSXQ Login Setup")
    print("=" * 60)
    print(f"Profile directory: {ZSXQ_PROFILE_DIR}")
    print()
    print("Browser will open ZSXQ login page, please:")
    print("1. Login with WeChat scan or phone number")
    print("2. After login success, return to terminal and press Enter")
    
    if ZSXQ_PROFILE_DIR.exists():
        print(f"\nExisting profile found at: {ZSXQ_PROFILE_DIR}")
        print("1. Keep existing profile (reuse login)")
        print("2. Delete and create new profile")
        choice = input("\nChoose (1/2): ").strip()
        if choice == '2':
            shutil.rmtree(ZSXQ_PROFILE_DIR)
            print(f"Deleted old profile")
        else:
            print("Reusing existing profile")
    
    print()
    print("=" * 60)
    
    co = ChromiumOptions()
    co.set_user_data_path(str(ZSXQ_PROFILE_DIR))
    co.set_argument("--disable-blink-features=AutomationControlled")
    
    browser = ChromiumPage(co)
    browser.get("https://wx.zsxq.com/dweb2/index/login")
    
    input("\nPress Enter after login completes...")
    
    # Verify
    if verify_zsxq_login(browser):
        print("\n✓ Login successful!")
        print(f"Profile location: {ZSXQ_PROFILE_DIR}")
        
        # Get user info
        try:
            browser.get("https://wx.zsxq.com/dweb2/index")
            browser.wait(3)
            
            # Try to get joined groups count
            groups = browser.eles('css:.group-item')
            if groups:
                print(f"\nJoined {len(groups)} groups")
        except:
            pass
    else:
        print("\n✗ Login failed, please try again")
    
    browser.quit()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ZSXQ login setup")
    parser.add_argument("--login", action="store_true", help="Start login flow")
    parser.add_argument("--check", action="store_true", help="Check login status")
    args = parser.parse_args()
    
    if args.login:
        do_zsxq_login()
    elif args.check:
        ready, msg = check_zsxq_ready()
        print(f"Ready: {ready}")
        print(f"Message: {msg}")
        
        if ready:
            browser = create_zsxq_browser(headless=False)
            if browser:
                logged_in = verify_zsxq_login(browser)
                print(f"Logged in: {logged_in}")
                browser.quit()
    else:
        parser.print_help()
