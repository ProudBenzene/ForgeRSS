#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Weibo (微博) scraping utilities.

Requires:
1. DrissionPage installed
2. Logged-in browser profile at WEIBO_PROFILE_DIR
3. Desktop environment (non-headless mode)

Usage:
1. First time:  python -m generators.social.weibo.scraper --login
2. Then run generators normally.
"""

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PROFILES_ROOT = PROJECT_ROOT / "profiles"

WEIBO_PROFILE_DIR = Path(
    os.environ.get("WEIBO_PROFILE_DIR", PROFILES_ROOT / "weibo")
)

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    HAS_DRISSION = True
except ImportError:
    HAS_DRISSION = False
    ChromiumPage = None
    ChromiumOptions = None


def check_weibo_ready() -> tuple[bool, str]:
    if not HAS_DRISSION:
        return False, "DrissionPage not installed. Run: pip install DrissionPage"
    if not WEIBO_PROFILE_DIR.exists():
        return (
            False,
            f"Profile not found at {WEIBO_PROFILE_DIR}. "
            f"Run: python -m generators.social.weibo.scraper --login",
        )
    return True, "Ready"


def create_weibo_browser(headless: bool = False) -> Optional["ChromiumPage"]:
    ready, msg = check_weibo_ready()
    if not ready:
        logger.error(msg)
        return None

    co = ChromiumOptions()
    co.set_user_data_path(str(WEIBO_PROFILE_DIR))
    if headless:
        co.headless()
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    co.set_argument("--disable-infobars")

    try:
        return ChromiumPage(co)
    except Exception as e:
        logger.error(f"Failed to create browser: {e}")
        return None


def verify_weibo_login(browser: "ChromiumPage", notify_on_failure: bool = True) -> bool:
    try:
        from generators.utils.login_checker import Platform, LoginChecker

        checker = LoginChecker()
        status, message = checker.check_login(Platform.WEIBO, browser)

        if status.value == "logged_in":
            logger.info(f"Weibo login verified: {message}")
            return True

        logger.warning(f"Weibo login verification failed: {message}")
        if notify_on_failure:
            checker.notify_login_expired(Platform.WEIBO, method="all")
            logger.error(
                f"Please re-login to Weibo: {checker.get_login_command(Platform.WEIBO)}"
            )
        return False

    except Exception as e:
        logger.error(f"Failed to verify login: {e}")
        return False


def do_weibo_login(wait_seconds: int = 180):
    """Polling-based login flow (no interactive input needed)."""
    if not HAS_DRISSION:
        print("ERROR: DrissionPage not installed")
        return

    print("=" * 60)
    print("Weibo Login Setup")
    print("=" * 60)
    print(f"Profile directory: {WEIBO_PROFILE_DIR}")
    print(f"Will poll every 5s for up to {wait_seconds}s.")
    print()
    print(">>> 浏览器即将打开，请扫码登录微博，登录成功后脚本会自动检测。<<<")
    print("=" * 60)

    WEIBO_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    co = ChromiumOptions()
    co.set_user_data_path(str(WEIBO_PROFILE_DIR))
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")

    browser = ChromiumPage(co)
    try:
        # Hit the login page directly so the QR is shown immediately
        browser.get("https://passport.weibo.com/sso/signin")
        time.sleep(3)

        from generators.utils.login_checker import LoginChecker, Platform
        checker = LoginChecker()
        not_in_markers = checker._not_logged_in_keywords(Platform.WEIBO)
        in_keywords = checker._logged_in_keywords(Platform.WEIBO)

        elapsed = 0
        # After scanning, weibo redirects to weibo.com homepage; the login URL
        # itself contains 'passport.weibo' so we also watch for that.
        while elapsed <= wait_seconds:
            try:
                url = browser.url or ""
            except Exception:
                url = ""
            try:
                html = browser.html
            except Exception:
                html = ""

            on_login_page = "passport.weibo" in url
            hit_not_in = [kw for kw in not_in_markers if kw in html]
            hit_in = [kw for kw in in_keywords if kw in html]

            if hit_in and not on_login_page:
                print(f"\n[t+{elapsed}s] LOGGED IN  (detected: {hit_in})")
                break
            if not on_login_page and not_in_markers and not hit_not_in:
                print(f"\n[t+{elapsed}s] LOGGED IN by absence  "
                      f"(not_logged_in markers {not_in_markers} no longer found, url={url})")
                break

            if on_login_page:
                state = f"on login page ({url})"
            elif hit_not_in:
                state = f"on login wall (markers {hit_not_in})"
            else:
                state = f"ambiguous, url={url}"
            print(f"  [t+{elapsed:>3}s] {state} - waiting...")
            time.sleep(5)
            elapsed += 5
        else:
            print(f"\nTimed out after {wait_seconds}s. Profile saved at "
                  f"{WEIBO_PROFILE_DIR}; rerun to retry.")
            return

        print(f"\nProfile saved at: {WEIBO_PROFILE_DIR}")
    finally:
        try:
            browser.quit()
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Weibo login setup")
    parser.add_argument("--login", action="store_true", help="Start login flow")
    parser.add_argument("--check", action="store_true", help="Check login status")
    args = parser.parse_args()

    if args.login:
        do_weibo_login()
    elif args.check:
        ready, msg = check_weibo_ready()
        print(f"Ready: {ready}")
        print(f"Message: {msg}")
        if ready:
            browser = create_weibo_browser(headless=False)
            if browser:
                logged_in = verify_weibo_login(browser)
                print(f"Logged in: {logged_in}")
                browser.quit()
    else:
        parser.print_help()
