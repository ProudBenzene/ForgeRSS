#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Douyin (抖音) scraping utilities.

Requires:
1. DrissionPage installed
2. Logged-in browser profile at DOUYIN_PROFILE_DIR
3. Desktop environment (non-headless mode — Douyin detects headless)

Usage:
1. First time:  python -m generators.social.douyin.scraper --login
2. Then run generators normally.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# generators/social/douyin/scraper.py -> .parent x4 -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PROFILES_ROOT = PROJECT_ROOT / "profiles"

DOUYIN_PROFILE_DIR = Path(
    os.environ.get("DOUYIN_PROFILE_DIR", PROFILES_ROOT / "douyin")
)

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    HAS_DRISSION = True
except ImportError:
    HAS_DRISSION = False
    ChromiumPage = None
    ChromiumOptions = None


def check_douyin_ready() -> tuple[bool, str]:
    """Check if Douyin scraping is ready."""
    if not HAS_DRISSION:
        return False, "DrissionPage not installed. Run: pip install DrissionPage"
    if not DOUYIN_PROFILE_DIR.exists():
        return (
            False,
            f"Profile not found at {DOUYIN_PROFILE_DIR}. "
            f"Run: python -m generators.social.douyin.scraper --login",
        )
    return True, "Ready"


def create_douyin_browser(headless: bool = False) -> Optional["ChromiumPage"]:
    """Create a browser instance with Douyin login state."""
    ready, msg = check_douyin_ready()
    if not ready:
        logger.error(msg)
        return None

    co = ChromiumOptions()
    co.set_user_data_path(str(DOUYIN_PROFILE_DIR))

    if headless:
        co.headless()

    # Anti-detection (Douyin has strong anti-bot)
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


def verify_douyin_login(browser: "ChromiumPage", notify_on_failure: bool = True) -> bool:
    """Check if browser is logged into Douyin."""
    try:
        from generators.utils.login_checker import Platform, LoginChecker

        checker = LoginChecker()
        status, message = checker.check_login(Platform.DOUYIN, browser)

        if status.value == "logged_in":
            logger.info(f"Douyin login verified: {message}")
            return True

        logger.warning(f"Douyin login verification failed: {message}")

        if notify_on_failure:
            checker.notify_login_expired(Platform.DOUYIN, method="all")
            logger.error(
                f"Please re-login to Douyin: {checker.get_login_command(Platform.DOUYIN)}"
            )

        return False

    except Exception as e:
        logger.error(f"Failed to verify login: {e}")
        return False


def do_douyin_login(wait_seconds: int = 180):
    """
    Polling-based login flow (no interactive input needed).

    Opens a browser to douyin.com, polls every 5s for up to wait_seconds.
    Login is detected by the absence of 'not_logged_in' markers in the HTML.
    """
    if not HAS_DRISSION:
        print("ERROR: DrissionPage not installed")
        print("Run: pip install DrissionPage")
        return

    import time as _time

    print("=" * 60)
    print("Douyin Login Setup")
    print("=" * 60)
    print(f"Profile directory: {DOUYIN_PROFILE_DIR}")
    print(f"Will poll every 5s for up to {wait_seconds}s.")
    print()
    print(">>> 浏览器即将打开，请扫码登录抖音，登录成功后脚本会自动检测。<<<")
    print("=" * 60)

    DOUYIN_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    co = ChromiumOptions()
    co.set_user_data_path(str(DOUYIN_PROFILE_DIR))
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")

    browser = ChromiumPage(co)
    try:
        browser.get("https://www.douyin.com/")
        _time.sleep(3)

        # Pull not_logged_in markers from config so we don't hard-code
        from generators.utils.login_checker import LoginChecker, Platform
        checker = LoginChecker()
        not_in_markers = checker._not_logged_in_keywords(Platform.DOUYIN)
        in_keywords = checker._logged_in_keywords(Platform.DOUYIN)

        elapsed = 0
        while elapsed <= wait_seconds:
            try:
                html = browser.html
            except Exception:
                html = ""

            hit_not_in = [kw for kw in not_in_markers if kw in html]
            hit_in = [kw for kw in in_keywords if kw in html]

            if hit_in:
                print(f"\n[t+{elapsed}s] LOGGED IN  (detected: {hit_in})")
                break
            if not_in_markers and not hit_not_in:
                print(f"\n[t+{elapsed}s] LOGGED IN by absence  "
                      f"(not_logged_in markers {not_in_markers} no longer found)")
                break

            if hit_not_in:
                state = f"on login wall (markers {hit_not_in})"
            else:
                state = "ambiguous (no markers fired)"
            print(f"  [t+{elapsed:>3}s] {state} - waiting...")
            _time.sleep(5)
            elapsed += 5
        else:
            print(f"\nTimed out after {wait_seconds}s. Profile saved anyway "
                  f"at {DOUYIN_PROFILE_DIR}; rerun to retry.")
            return

        print(f"\nProfile saved at: {DOUYIN_PROFILE_DIR}")
    finally:
        try:
            browser.quit()
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Douyin login setup")
    parser.add_argument("--login", action="store_true", help="Start login flow")
    parser.add_argument("--check", action="store_true", help="Check login status")
    args = parser.parse_args()

    if args.login:
        do_douyin_login()
    elif args.check:
        ready, msg = check_douyin_ready()
        print(f"Ready: {ready}")
        print(f"Message: {msg}")

        if ready:
            browser = create_douyin_browser(headless=False)
            if browser:
                logged_in = verify_douyin_login(browser)
                print(f"Logged in: {logged_in}")
                browser.quit()
    else:
        parser.print_help()
