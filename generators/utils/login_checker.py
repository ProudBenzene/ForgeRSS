#!/usr/bin/env python3
"""
Unified Login Status Checker and Notification Module

Features:
1. Check if platform login status is valid
2. Provide clear re-login instructions
3. Support multiple notification methods (log/file/email)

Login keywords are loaded from config/login_keywords.json so they can be
updated without changing code.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, List
from enum import Enum

logger = logging.getLogger(__name__)

# Project root: generators/utils/login_checker.py -> generators -> project_root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGIN_KEYWORDS_FILE = PROJECT_ROOT / "config" / "login_keywords.json"


class Platform(Enum):
    """Supported platforms"""
    ZHIHU = "zhihu"
    BILIBILI = "bilibili"
    XIAOHONGSHU = "xiaohongshu"
    ZSXQ = "zsxq"
    DOUYIN = "douyin"
    KUAISHOU = "kuaishou"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"


class LoginStatus(Enum):
    """Login status"""
    LOGGED_IN = "logged_in"
    NOT_LOGGED_IN = "not_logged_in"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


# Fallback config used only when config/login_keywords.json is missing.
# Keep these in sync with config/login_keywords.json as best-effort defaults.
_FALLBACK_KEYWORDS: Dict[Platform, Dict[str, List[str]]] = {
    Platform.ZHIHU: {
        "check_url": "https://www.zhihu.com/",
        "signin_url_markers": ["/signin", "/login"],
        "logged_in": ["写文章", "创作中心"],
        "not_logged_in": ["登录", "注册"],
    },
    Platform.BILIBILI: {
        "check_url": "https://www.bilibili.com/",
        "signin_url_markers": ["/login", "passport.bilibili.com"],
        "logged_in": ["投稿", "动态"],
        "not_logged_in": ["登录", "注册"],
    },
    Platform.XIAOHONGSHU: {
        "check_url": "https://www.xiaohongshu.com/",
        "signin_url_markers": ["/login", "/passport"],
        "logged_in": ["发布笔记", "创作中心"],
        "not_logged_in": ["登录", "扫码登录"],
    },
    Platform.ZSXQ: {
        "check_url": "https://wx.zsxq.com/",
        "signin_url_markers": ["/login", "/sign"],
        "logged_in": ["退出登录", "group-list", "user-avatar"],
        "not_logged_in": ["微信登录", "扫码登录"],
    },
    Platform.DOUYIN: {
        "check_url": "https://www.douyin.com/",
        "signin_url_markers": [],  # 抖音不重定向到 /login，登录后会从 / 跳到 /jingxuan
        "logged_in": ["退出登录", "semi-avatar", "avatar-component"],
        "not_logged_in": ["扫码登录", "登录抖音"],
    },
    Platform.KUAISHOU: {
        "check_url": "https://www.kuaishou.com/",
        "signin_url_markers": [],
        "logged_in": ["text-name"],
        "not_logged_in": ["sidebar-login-button"],
    },
}


# Re-login commands for each platform (kept in code since they reference module paths).
LOGIN_COMMANDS = {
    Platform.ZHIHU: "python -m generators.social.zhihu.scraper --login",
    Platform.BILIBILI: "python -m generators.social.bilibili.scraper --login",
    Platform.XIAOHONGSHU: "python -m generators.social.xiaohongshu.scraper --login",
    Platform.ZSXQ: "python -m generators.social.zsxq.scraper --login",
    Platform.DOUYIN: "python -m generators.social.douyin.scraper --login",
    Platform.KUAISHOU: "python -m generators.social.kuaishou.scraper --login",
}


def _load_keywords_from_config() -> Dict[Platform, Dict[str, List[str]]]:
    """Load login keywords from config/login_keywords.json. Falls back to defaults on error."""
    if not LOGIN_KEYWORDS_FILE.exists():
        logger.warning(
            f"Login keywords config not found at {LOGIN_KEYWORDS_FILE}, using fallback defaults"
        )
        return _FALLBACK_KEYWORDS

    try:
        with open(LOGIN_KEYWORDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        platforms_cfg = data.get("platforms", {})
        loaded: Dict[Platform, Dict[str, List[str]]] = {}
        for platform_name, cfg in platforms_cfg.items():
            try:
                platform = Platform(platform_name)
            except ValueError:
                logger.warning(f"Unknown platform in config: {platform_name}")
                continue
            keywords = cfg.get("keywords", {})
            loaded[platform] = {
                "check_url": cfg.get("check_url", ""),
                "login_url": cfg.get("login_url", ""),
                "signin_url_markers": cfg.get("signin_url_markers", []),
                "logged_in": keywords.get("logged_in", []),
                "not_logged_in": keywords.get("not_logged_in", []),
            }

        # Fill any missing platforms from fallback
        for platform, fb in _FALLBACK_KEYWORDS.items():
            loaded.setdefault(platform, fb)

        return loaded
    except Exception as e:
        logger.error(f"Failed to load login keywords from {LOGIN_KEYWORDS_FILE}: {e}")
        return _FALLBACK_KEYWORDS


class LoginChecker:
    """Login status checker"""

    def __init__(self, notification_file: Optional[Path] = None):
        self.notification_file = notification_file or Path("login_notifications.log")
        self._keywords = _load_keywords_from_config()

    def _logged_in_keywords(self, platform: Platform) -> List[str]:
        return self._keywords.get(platform, {}).get("logged_in", [])

    def _not_logged_in_keywords(self, platform: Platform) -> List[str]:
        return self._keywords.get(platform, {}).get("not_logged_in", [])

    def _signin_url_markers(self, platform: Platform) -> List[str]:
        return self._keywords.get(platform, {}).get("signin_url_markers", [])

    def _login_url(self, platform: Platform) -> str:
        return self._keywords.get(platform, {}).get("login_url", "")

    def _check_url(self, platform: Platform) -> str:
        url = self._keywords.get(platform, {}).get("check_url", "")
        if url:
            return url
        # Fallback to default URLs
        defaults = {
            Platform.ZHIHU: "https://www.zhihu.com/",
            Platform.BILIBILI: "https://www.bilibili.com/",
            Platform.XIAOHONGSHU: "https://www.xiaohongshu.com/",
            Platform.ZSXQ: "https://wx.zsxq.com/",
        }
        return defaults.get(platform, "")

    def check_login(self, platform: Platform, browser) -> Tuple[LoginStatus, str]:
        """
        Three-tier login detection:

        1. URL signin markers: navigate to check_url; if the final URL contains
           `/signin`, `/login`, etc., user is logged out (server-side decision —
           most reliable when applicable). Some platforms (B站) won't redirect.

        2. NOT-LOGGED-IN HTML markers: high-specificity CSS classes or button
           text that ONLY appear when logged out (e.g. 'header-login-entry',
           '立即登录'). One hit = definitively logged out.

        3. LOGGED-IN HTML keywords: page text that should only appear when
           logged in (e.g. '写文章', '创作中心').
        """
        check_url = self._check_url(platform)
        if not check_url:
            return LoginStatus.UNKNOWN, f"Unsupported platform: {platform.value}"

        try:
            browser.get(check_url)
            browser.wait(2)

            # Tier 1: URL redirect check
            final_url = getattr(browser, "url", check_url) or check_url
            url_markers = self._signin_url_markers(platform)
            lower_url = final_url.lower()
            hit_url_marker = next((m for m in url_markers if m.lower() in lower_url), None)
            if hit_url_marker:
                return (
                    LoginStatus.NOT_LOGGED_IN,
                    f"Redirected to login URL '{final_url}' (matched marker '{hit_url_marker}')",
                )

            html = browser.html

            # Tier 2: explicit NOT-LOGGED-IN markers (high specificity)
            not_in_markers = self._not_logged_in_keywords(platform)
            found_not_in = [kw for kw in not_in_markers if kw in html]
            if found_not_in:
                return (
                    LoginStatus.NOT_LOGGED_IN,
                    f"Logged-out markers found in HTML at '{final_url}': {', '.join(found_not_in)}",
                )

            # Tier 3: LOGGED-IN keywords
            in_keywords = self._logged_in_keywords(platform)
            if not in_keywords and not not_in_markers:
                return LoginStatus.UNKNOWN, f"No keywords configured for {platform.value}"

            found_in = [kw for kw in in_keywords if kw in html]
            if found_in:
                return (
                    LoginStatus.LOGGED_IN,
                    f"Logged in (URL '{final_url}', detected keywords: {', '.join(found_in)})",
                )

            # No signals fired. If we have not_logged_in markers configured but none
            # hit, assume logged in (because we'd expect them on a logged-out page).
            if not_in_markers and not in_keywords:
                return (
                    LoginStatus.LOGGED_IN,
                    f"No logged-out markers present at '{final_url}' (logged_in keywords not configured)",
                )

            return (
                LoginStatus.NOT_LOGGED_IN,
                f"URL '{final_url}' clean, no logged_in keywords found",
            )

        except Exception as e:
            logger.error(f"Failed to check {platform.value} login status: {e}")
            return LoginStatus.UNKNOWN, f"Check failed: {str(e)}"

    def verify_login_with_keywords(self, html: str, platform: Platform) -> Tuple[bool, str]:
        """Verify login status using keywords (for pre-fetched HTML content)"""
        keywords = self._logged_in_keywords(platform)
        found = [kw for kw in keywords if kw in html]

        if found:
            return True, f"Logged in (detected: {', '.join(found)})"
        return False, "Not logged in or session expired"

    def notify_login_expired(self, platform: Platform, method: str = "all"):
        """Notify when login expires"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        login_cmd = LOGIN_COMMANDS.get(platform, "Unknown command")

        message = f"""
{'=' * 60}
[Login Expired Notification]
{'=' * 60}
Platform: {platform.value}
Time: {timestamp}
Status: Login expired or not logged in

Please re-login to continue:
  {login_cmd}

{'=' * 60}
"""

        if method in ("log", "all"):
            logger.warning(f"\n{message}")

        if method in ("file", "all"):
            try:
                with open(self.notification_file, "a", encoding="utf-8") as f:
                    f.write(message + "\n")
                logger.info(f"Login expired notification written to: {self.notification_file}")
            except Exception as e:
                logger.error(f"Failed to write notification file: {e}")

        if method == "email":
            logger.warning("Email notification not implemented yet")

    def get_login_command(self, platform: Platform) -> str:
        """Get re-login command for platform"""
        return LOGIN_COMMANDS.get(platform, "Unknown command")

    def clear_notifications(self):
        """Clear notification file"""
        try:
            if self.notification_file.exists():
                self.notification_file.unlink()
                logger.info(f"Cleared notification file: {self.notification_file}")
        except Exception as e:
            logger.error(f"Failed to clear notification file: {e}")


def check_and_notify(platform: Platform, browser,
                     notification_method: str = "all") -> Tuple[bool, str]:
    """Convenience function: check login and send notification if expired."""
    checker = LoginChecker()
    status, message = checker.check_login(platform, browser)

    if status in (LoginStatus.NOT_LOGGED_IN, LoginStatus.EXPIRED):
        checker.notify_login_expired(platform, method=notification_method)
        return False, message
    if status == LoginStatus.LOGGED_IN:
        return True, message
    return False, message


def verify_login_simple(html: str, platform_name: str) -> bool:
    """Simplified login verification (returns boolean only)."""
    try:
        platform = Platform(platform_name)
    except ValueError:
        logger.error(f"Unsupported platform: {platform_name}")
        return False
    checker = LoginChecker()
    is_logged_in, _ = checker.verify_login_with_keywords(html, platform)
    return is_logged_in
