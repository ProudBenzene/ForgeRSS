#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Collaborative login-detection diagnostic.

Workflow:
1. You run this with a platform name.
2. It opens the platform's logged-in profile in a non-headless browser, navigates
   to the check_url, and waits for you.
3. While the browser is in front of you, it dumps HTML + computes:
     - Which `logged_in` keywords from config/login_keywords.json hit / miss.
     - Which `not_logged_in` keywords hit / miss (HITs here = bad — you may not
       actually be logged in, or the keyword is too generic).
     - Candidate stable anchors (avatar, nav items, user-only buttons) extracted
       from the live DOM.
4. HTML is saved to `tools/login_dumps/<platform>_<timestamp>.html` so you can
   open it and diff against fresh fetches later.
5. You inspect the live page + the analysis, then tell me which keywords or
   selectors should be the canonical "logged in" signal.

Usage:
    python tools/diagnose_login.py zhihu
    python tools/diagnose_login.py bilibili --wait 5
    python tools/diagnose_login.py xiaohongshu --no-browser  # use only saved HTML
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Repo root: tools/diagnose_login.py -> tools -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from generators.utils.login_checker import Platform, _load_keywords_from_config

DUMP_DIR = PROJECT_ROOT / "tools" / "login_dumps"
DUMP_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# (module_path, factory_name, profile_dir_attr)
PLATFORM_BROWSERS = {
    "zhihu":       ("generators.social.zhihu.scraper",       "create_zhihu_browser",    "ZHIHU_PROFILE_DIR"),
    "bilibili":    ("generators.social.bilibili.scraper",    "create_bilibili_browser", "BILIBILI_PROFILE_DIR"),
    "xiaohongshu": ("generators.social.xiaohongshu.scraper", "create_xhs_browser",      "XHS_PROFILE_DIR"),
    "zsxq":        ("generators.social.zsxq.scraper",        "create_zsxq_browser",     "ZSXQ_PROFILE_DIR"),
}


def _kill_stale_chrome(profile_dir):
    """Kill any chrome process whose cmdline references this profile dir."""
    try:
        import psutil
    except ImportError:
        logger.warning("psutil not installed; skipping stale-process kill")
        return 0
    import time as _time
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
        logger.info(f"Killed {killed} stale chrome process(es) on this profile")
        _time.sleep(1)
    return killed


# Candidate DOM selectors per platform: things that are typically present ONLY when
# logged in. We probe each one against the live HTML to suggest a stable anchor.
# Keep these as suggestions for collaboration; final list is decided by the user.
CANDIDATE_SELECTORS = {
    "zhihu": [
        ".AppHeader-userInfo",                # 已登录: 顶部用户头像区
        ".Avatar.AppHeader-profileAvatar",    # 已登录: 头像
        ".AppHeader-Tabs",                    # 已登录: 关注/推荐/热榜导航
        "button[aria-label='写文章']",
        "a[href*='/creator']",                # 创作者入口
        ".SignFlow",                          # 未登录: 登录表单
        ".css-1gomreu",                       # 未登录: 登录按钮
    ],
    "bilibili": [
        ".header-avatar-wrap",                # 已登录: 头像
        ".bili-avatar",
        ".right-entry",                       # 投稿/消息/动态等右侧入口
        "a[href*='member.bilibili.com/platform/upload']",  # 投稿
        ".bili-header__bar",
        ".v-popover[name='avatar']",
        ".header-login-entry",                # 未登录: 登录入口
    ],
    "xiaohongshu": [
        ".user-info",                         # 已登录: 用户区
        ".avatar-wrapper",
        "a[href*='/profile/']",
        "[data-v-] .user.avatar",
        ".side-bar-component .channel",
        ".login-container",                   # 未登录
        ".reds-pavatar",                      # 已登录头像组件
    ],
    "zsxq": [
        ".my-icon",                           # 已登录: 我的
        ".group-list",                        # 已登录: 星球列表
        ".user-avatar",
        ".header-actions",
        ".login-btn",                         # 未登录
        "a[href*='/login']",
    ],
}


def open_browser_and_fetch(platform: str, wait_seconds: int) -> tuple[str, str]:
    """Returns (html, current_url)."""
    module_path, factory_name, profile_attr = PLATFORM_BROWSERS[platform]

    import importlib
    scraper_mod = importlib.import_module(module_path)
    create_browser = getattr(scraper_mod, factory_name)
    profile_dir = getattr(scraper_mod, profile_attr)

    keywords = _load_keywords_from_config()
    check_url = keywords[Platform(platform)]["check_url"]

    logger.info(f"Pre-clean: killing any stale Chrome on profile {profile_dir.name}...")
    _kill_stale_chrome(profile_dir)

    logger.info(f"Opening fresh browser for {platform}...")
    browser = create_browser(headless=False)
    if browser is None:
        raise RuntimeError(
            f"Could not create browser for {platform}. Is the profile set up? "
            f"Run: python -m {module_path} --login"
        )

    logger.info(f"Navigating to {check_url}")
    browser.get(check_url)
    logger.info(f"Waiting {wait_seconds}s for page to settle...")
    browser.wait(wait_seconds)

    # current_url after potential redirects
    current_url = getattr(browser, "url", check_url)
    html = browser.html

    # Intentionally do NOT quit the browser. The user inspects the live page
    # alongside the report and closes the window manually when done.
    logger.info("Browser left open for manual inspection — close it when finished.")
    return html, current_url


def analyze_html(platform: str, html: str, current_url: str):
    """Print a structured diagnostic report and return it."""
    keywords = _load_keywords_from_config()
    platform_cfg = keywords[Platform(platform)]
    logged_in_kws = platform_cfg["logged_in"]
    not_logged_in_kws = platform_cfg["not_logged_in"]

    print()
    print("=" * 72)
    print(f"  Login diagnostic for: {platform}")
    print(f"  Landed URL: {current_url}")
    print(f"  HTML length: {len(html):,} chars")
    print("=" * 72)

    print(f"\n[1/4] Configured `logged_in` keywords  ({len(logged_in_kws)}):")
    for kw in logged_in_kws:
        n = html.count(kw)
        flag = "HIT " if n > 0 else "MISS"
        print(f"    [{flag}] '{kw}'  (count={n})")

    print(f"\n[2/4] Configured `not_logged_in` keywords  ({len(not_logged_in_kws)}):")
    for kw in not_logged_in_kws:
        n = html.count(kw)
        flag = "HIT*" if n > 0 else "miss"
        suffix = "   <- present on this page (may be false positive or actually logged out)" if n > 0 else ""
        print(f"    [{flag}] '{kw}'  (count={n}){suffix}")

    print(f"\n[3/4] Candidate stable selectors (probed against HTML by substring match):")
    candidates = CANDIDATE_SELECTORS.get(platform, [])
    if not candidates:
        print("    (none configured yet for this platform)")
    else:
        for sel in candidates:
            present = sel in html  # naive substring check; ok for class names and href fragments
            flag = "FOUND   " if present else "absent  "
            print(f"    [{flag}] {sel}")
        print("    (note: substring match only — final confirmation should be CSS-selector eval)")

    # Heuristic suggestions: hunt for nicknames, user IDs, etc.
    print(f"\n[4/4] Quick heuristic scan for personalized signals:")
    HINTS = [
        ("avatar in DOM",         "avatar"),
        ("user-info container",   "user-info"),
        ("profile link",          "/profile/"),
        ("creator entry",         "creator"),
        ("logout / 退出",          "退出"),
        ("nickname-bearing div",  "nickname"),
        ("messages bell",         "message"),
    ]
    for label, needle in HINTS:
        n = html.count(needle)
        flag = "HIT " if n > 0 else "miss"
        print(f"    [{flag}] {label}  (substring '{needle}' x{n})")

    print()
    print("=" * 72)
    print("Next step (collaboration):")
    print("  - Look at the page in your browser.")
    print("  - Tell me a stable string (or CSS selector) that *only* shows up when")
    print("    logged in (e.g. your nickname, a 'creator' button, a UID).")
    print("  - I'll update config/login_keywords.json and the checker code.")
    print("=" * 72)
    print()


def save_html(platform: str, html: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = DUMP_DIR / f"{platform}_{ts}.html"
    out.write_text(html, encoding="utf-8")
    return out


def main():
    parser = argparse.ArgumentParser(description="Login-detection diagnostic")
    parser.add_argument(
        "platform",
        choices=list(PLATFORM_BROWSERS.keys()),
        help="Which platform to diagnose",
    )
    parser.add_argument(
        "--wait", type=int, default=4,
        help="Seconds to wait after navigation (default: 4)",
    )
    parser.add_argument(
        "--from-file", type=str, default=None,
        help="Skip browser; analyze a previously-dumped HTML file at this path",
    )
    args = parser.parse_args()

    if args.from_file:
        html_path = Path(args.from_file)
        if not html_path.exists():
            print(f"ERROR: {html_path} not found")
            sys.exit(1)
        html = html_path.read_text(encoding="utf-8")
        analyze_html(args.platform, html, current_url=f"(from file: {html_path})")
        return

    try:
        html, current_url = open_browser_and_fetch(args.platform, args.wait)
    except Exception as e:
        logger.error(f"Browser launch failed: {e}")
        sys.exit(1)

    dump = save_html(args.platform, html)
    print(f"\n[saved] {dump}")

    analyze_html(args.platform, html, current_url)


if __name__ == "__main__":
    main()
