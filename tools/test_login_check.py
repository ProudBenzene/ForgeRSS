#!/usr/bin/env python3
"""End-to-end test of LoginChecker against a real browser, with polling.

Workflow:
  1. Kill any existing Chrome on this profile.
  2. Open a fresh browser and navigate to the platform's check_url.
  3. Poll every 5 seconds for up to MAX_WAIT seconds:
       - Read browser.url
       - If URL contains a signin marker -> still logged out (waiting for you).
       - Else verify HTML against logged_in keywords -> LOGGED IN.
  4. Quit the browser cleanly when done (success, timeout, or error).
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PLATFORMS = {
    "zhihu":       ("generators.social.zhihu.scraper",       "create_zhihu_browser",    "ZHIHU_PROFILE_DIR"),
    "bilibili":    ("generators.social.bilibili.scraper",    "create_bilibili_browser", "BILIBILI_PROFILE_DIR"),
    "xiaohongshu": ("generators.social.xiaohongshu.scraper", "create_xhs_browser",      "XHS_PROFILE_DIR"),
    "zsxq":        ("generators.social.zsxq.scraper",        "create_zsxq_browser",     "ZSXQ_PROFILE_DIR"),
    "douyin":      ("generators.social.douyin.scraper",      "create_douyin_browser",   "DOUYIN_PROFILE_DIR"),
    "kuaishou":    ("generators.social.kuaishou.scraper",    "create_kuaishou_browser", "KUAISHOU_PROFILE_DIR"),
}

MAX_WAIT_SECONDS = 120
POLL_INTERVAL = 5


def kill_chrome_using_profile(profile_dir: Path) -> int:
    try:
        import psutil
    except ImportError:
        print("  [warn] psutil not installed; skipping process kill")
        return 0
    target = str(profile_dir).lower()
    killed = 0
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name not in ("chrome.exe", "msedge.exe", "chromium.exe"):
                continue
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if target in cmdline:
                proc.kill()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        time.sleep(1)
    return killed


def main(platform_name: str):
    from generators.utils.login_checker import LoginChecker, Platform, LoginStatus

    module_path, factory_name, profile_attr = PLATFORMS[platform_name]
    import importlib
    mod = importlib.import_module(module_path)
    create_browser = getattr(mod, factory_name)
    profile_dir = getattr(mod, profile_attr)

    print(f"[{platform_name}] Pre-clean: killing stale Chrome on profile...")
    n = kill_chrome_using_profile(profile_dir)
    if n:
        print(f"  killed {n} stale processes")

    print(f"[{platform_name}] Opening fresh browser...")
    browser = create_browser(headless=False)
    if not browser:
        print("FAIL: could not create browser")
        sys.exit(1)

    checker = LoginChecker()
    platform = Platform(platform_name)

    check_url = checker._check_url(platform)
    login_url = checker._login_url(platform)
    url_markers = checker._signin_url_markers(platform)
    in_keywords = checker._logged_in_keywords(platform)
    not_in_keywords = checker._not_logged_in_keywords(platform)

    print(f"[{platform_name}] check_url           : {check_url}")
    print(f"[{platform_name}] login_url (fallback): {login_url}")
    print(f"[{platform_name}] signin URL markers  : {url_markers}")
    print(f"[{platform_name}] logged_in keywords  : {in_keywords}")
    print(f"[{platform_name}] not_logged_in markers: {not_in_keywords}")
    print(f"[{platform_name}] Polling every {POLL_INTERVAL}s for up to {MAX_WAIT_SECONDS}s.\n")

    try:
        browser.get(check_url)
        time.sleep(2)

        # If we land on a logged-out state, jump straight to the login URL so the
        # user can see the QR / form without hunting for a button on the page.
        url_lower = (getattr(browser, "url", "") or "").lower()
        on_signin_url = any(m.lower() in url_lower for m in url_markers)
        try:
            html0 = browser.html
        except Exception:
            html0 = ""
        hit_logged_out_in_html = any(kw in html0 for kw in not_in_keywords)

        if (on_signin_url or hit_logged_out_in_html) and login_url:
            print(f"  [hint] Detected logged-out state — opening login page directly: {login_url}\n")
            browser.get(login_url)
            time.sleep(2)
        else:
            print(f"  [hint] User appears logged-in already, or no login_url configured.\n")

        elapsed = 0
        final_status = LoginStatus.UNKNOWN
        final_msg = "Timed out"

        while elapsed <= MAX_WAIT_SECONDS:
            url_display = getattr(browser, "url", "") or ""
            url_lower = url_display.lower()
            hit_url_marker = next((m for m in url_markers if m.lower() in url_lower), None)

            if hit_url_marker:
                state_hint = f"on signin URL ({url_display}) - waiting for login..."
            else:
                # URL clean; pull HTML and apply 3-tier check
                try:
                    html = browser.html
                except Exception:
                    html = ""

                hit_not_in = [kw for kw in not_in_keywords if kw in html]
                hit_in = [kw for kw in in_keywords if kw in html]

                if hit_not_in:
                    state_hint = (
                        f"on '{url_display}' - found logged-out markers "
                        f"{hit_not_in}, waiting..."
                    )
                elif hit_in:
                    final_status = LoginStatus.LOGGED_IN
                    final_msg = (
                        f"Logged in (URL '{url_display}', "
                        f"detected keywords: {', '.join(hit_in)})"
                    )
                    break
                elif not_in_keywords and not in_keywords:
                    # absence-based: not_logged_in markers configured but none hit,
                    # and no logged_in keywords configured. Treat as logged in.
                    final_status = LoginStatus.LOGGED_IN
                    final_msg = (
                        f"Logged in by absence (URL '{url_display}', "
                        f"no logged-out markers {not_in_keywords} found)"
                    )
                    break
                else:
                    state_hint = f"on '{url_display}' - ambiguous (no markers fired), waiting..."

            print(f"  [t+{elapsed:>3}s] {state_hint}")
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

        if final_status != LoginStatus.LOGGED_IN:
            final_status = LoginStatus.NOT_LOGGED_IN
            final_msg = f"Polling timeout after {MAX_WAIT_SECONDS}s. Last URL: {getattr(browser, 'url', '?')}"

        print()
        print("=" * 60)
        print(f"  Final status : {final_status.value}")
        print(f"  Message      : {final_msg}")
        print("=" * 60)

    finally:
        print("\nClosing browser...")
        try:
            browser.quit()
            print("Browser closed.")
        except Exception as e:
            print(f"Failed to quit browser: {e}")


if __name__ == "__main__":
    plat = sys.argv[1] if len(sys.argv) > 1 else "zhihu"
    main(plat)
