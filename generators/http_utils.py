#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
HTTP utilities with automatic fallback strategy.
Priority: curl_cffi (fast, TLS fingerprint) -> selenium (JS rendering)
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import pytz
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ========== Constants ==========

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

# Check available engines
try:
    from curl_cffi.requests import Session as CurlSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    HAS_DRISSION = True
except ImportError:
    HAS_DRISSION = False

logger.info(
    f"HTTP engines: curl_cffi={HAS_CURL_CFFI}, "
    f"selenium={HAS_SELENIUM}, drission={HAS_DRISSION}"
)


# ========== Core Fetch Functions ==========

def fetch_html(url: str, timeout: int = 30) -> Optional[str]:
    """
    Simple HTTP fetch using requests.
    For static pages only.
    """
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.error(f"requests failed for {url}: {e}")
        return None


def fetch_with_curl_cffi(url: str, timeout: int = 30) -> Optional[str]:
    """
    Fetch using curl_cffi with Chrome TLS fingerprint.
    Fast (~5-7s), good for SSR/static sites.
    """
    if not HAS_CURL_CFFI:
        logger.warning("curl_cffi not installed")
        return None
    
    try:
        with CurlSession(impersonate="chrome120") as session:
            resp = session.get(
                url, 
                headers=BROWSER_HEADERS, 
                timeout=timeout,
                allow_redirects=True,
                verify=False
            )
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        logger.error(f"curl_cffi failed for {url}: {e}")
        return None


def fetch_with_selenium(
    url: str,
    wait_time: int = 5,
    wait_for_selector: str = None,
    click_more_selector: str = None,
    max_clicks: int = 0
) -> Optional[str]:
    """
    Fetch using Selenium + webdriver-manager.
    Slower (~30s), but handles JS-rendered pages.
    
    Args:
        url: Page URL
        wait_time: Seconds to wait after page load
        wait_for_selector: CSS selector to wait for (optional)
        click_more_selector: Selector for "Load more" button
        max_clicks: Max clicks on load more button
    """
    if not HAS_SELENIUM:
        logger.warning("selenium not installed")
        return None
    
    driver = None
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=en-US")
        options.add_argument(f"--user-agent={BROWSER_HEADERS['User-Agent']}")
        
        # Force English language preference
        prefs = {
            "intl.accept_languages": "en-US,en",
            "profile.default_content_setting_values.notifications": 2
        }
        options.add_experimental_option("prefs", prefs)
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        logger.info(f"Selenium fetching: {url}")
        driver.get(url)
        time.sleep(wait_time)
        
        # Wait for specific element
        if wait_for_selector:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
                )
                logger.info(f"Found: {wait_for_selector}")
            except Exception:
                logger.warning(f"Timeout waiting for: {wait_for_selector}")
        
        # Click "Load more" buttons
        if click_more_selector and max_clicks > 0:
            clicks = 0
            while clicks < max_clicks:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, click_more_selector)
                    if btn and btn.is_displayed():
                        logger.info(f"Clicking load more ({clicks + 1}/{max_clicks})")
                        driver.execute_script("arguments[0].click();", btn)
                        clicks += 1
                        time.sleep(2)
                    else:
                        break
                except Exception:
                    break
        
        return driver.page_source
        
    except Exception as e:
        logger.error(f"Selenium failed for {url}: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def fetch_with_drission(
    url: str,
    wait_time: int = 5,
    headless: bool = False,
    use_fresh_profile: bool = True,
) -> Optional[str]:
    """
    Fetch using DrissionPage (non-headless by default).
    Bypasses advanced anti-bot systems like RuiShu that block headless browsers.

    Args:
        url: Target URL
        wait_time: Seconds to wait after page load
        headless: Use headless mode (usually fails for anti-bot sites)
        use_fresh_profile: Create a fresh browser profile (recommended for anti-bot)
    
    Note:
        - Non-headless mode REQUIRES a display (X server on Linux, desktop on Windows)
        - For Linux servers without desktop, use Xvfb (but may not bypass advanced anti-bot)
        - Fresh profile helps avoid being flagged by anti-bot systems
    """
    if not HAS_DRISSION:
        logger.warning("DrissionPage not installed")
        return None

    import tempfile
    import shutil

    page = None
    temp_dir = None

    try:
        co = ChromiumOptions()
        co.headless(headless)
        co.set_argument("--no-sandbox")
        co.set_argument("--window-size=1920,1080")
        co.set_argument("--disable-dev-shm-usage")

        # Anti-detection settings
        co.set_argument("--disable-blink-features=AutomationControlled")
        co.set_argument("--disable-infobars")
        co.set_argument("--lang=zh-CN")

        # Fresh profile for each request (avoids being flagged)
        if use_fresh_profile:
            temp_dir = tempfile.mkdtemp(prefix="drission_profile_")
            co.set_argument(f"--user-data-dir={temp_dir}")
            logger.debug(f"Using fresh profile: {temp_dir}")

        page = ChromiumPage(co)

        # Additional anti-detection JS
        try:
            page.run_js('''
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            ''')
        except Exception:
            pass

        logger.info(f"DrissionPage fetching: {url}")
        page.get(url)
        time.sleep(wait_time)

        html = page.html
        if html and len(html) > 100:
            logger.info(f"DrissionPage succeeded ({len(html)} chars)")
            return html
        else:
            logger.warning(f"DrissionPage got empty/short page ({len(html or '')} chars)")
            return None

    except Exception as e:
        logger.error(f"DrissionPage failed for {url}: {e}")
        return None
    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass
        # Cleanup temp profile
        if temp_dir:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


def smart_fetch(
    url: str,
    require_js: bool = False,
    content_check: str = None,
    timeout: int = 30,
    selenium_wait: int = 5,
    selenium_selector: str = None,
    use_drission: bool = False,
    drission_headless: bool = False,
    anti_bot_level: int = 0,
) -> Optional[str]:
    """
    Smart fetch with automatic fallback and multi-strategy support.
    
    Strategy (ordered by speed, from fast to slow):
    1. curl_cffi - Fastest, good for static/SSR sites
    2. Selenium headless - For JS-rendered sites without strong anti-bot
    3. DrissionPage headless - Slightly better anti-detection than Selenium
    4. DrissionPage headed - Last resort for sites with advanced anti-bot (RuiShu etc.)
    
    Args:
        url: Page URL
        require_js: Skip curl_cffi, go straight to browser-based methods
        content_check: String that must exist in result (for validation)
        timeout: HTTP request timeout
        selenium_wait: Browser wait time after page load
        selenium_selector: CSS selector to wait for in Selenium
        use_drission: Prefer DrissionPage (for known anti-bot sites)
        drission_headless: DrissionPage headless mode
        anti_bot_level: 0=normal, 1=medium (use drission headless), 2=high (use drission headed)
    
    Anti-bot level guide:
        - 0: Normal sites, use curl_cffi -> Selenium
        - 1: Medium anti-bot, try DrissionPage headless first
        - 2: Strong anti-bot (RuiShu), use DrissionPage headed (requires display)
    
    Returns:
        HTML content or None
    """

    def validate(html: str) -> bool:
        """Check if fetched content is valid."""
        if not html or len(html) < 100:
            return False
        if content_check and content_check not in html:
            return False
        return True

    # Determine strategy based on anti_bot_level
    if anti_bot_level >= 2 or (use_drission and not drission_headless):
        # Level 2: Strong anti-bot - try DrissionPage headed first (requires display)
        logger.info(f"Anti-bot level 2: trying DrissionPage headed for {url}")
        html = fetch_with_drission(url, wait_time=selenium_wait, headless=False)
        if validate(html):
            return html
        logger.warning("DrissionPage headed failed, this site may require real display")

    elif anti_bot_level == 1 or (use_drission and drission_headless):
        # Level 1: Medium anti-bot - try DrissionPage headless first
        logger.info(f"Anti-bot level 1: trying DrissionPage headless for {url}")
        html = fetch_with_drission(url, wait_time=selenium_wait, headless=True)
        if validate(html):
            return html
        # Fallback to headed mode
        logger.info("DrissionPage headless failed, trying headed mode")
        html = fetch_with_drission(url, wait_time=selenium_wait, headless=False)
        if validate(html):
            return html

    # Level 0 or fallback: Standard strategy
    # Strategy 1: curl_cffi (fastest)
    if not require_js and HAS_CURL_CFFI:
        logger.info(f"Trying curl_cffi for {url}")
        html = fetch_with_curl_cffi(url, timeout)
        if validate(html):
            logger.info("curl_cffi succeeded")
            return html
        logger.debug("curl_cffi failed or content check failed")

    # Strategy 2: Selenium headless
    if HAS_SELENIUM:
        logger.info(f"Trying Selenium headless for {url}")
        html = fetch_with_selenium(
            url,
            wait_time=selenium_wait,
            wait_for_selector=selenium_selector
        )
        if validate(html):
            logger.info("Selenium succeeded")
            return html

    # Strategy 3: DrissionPage headless (better than Selenium for some sites)
    if HAS_DRISSION and anti_bot_level == 0:
        logger.info(f"Trying DrissionPage headless for {url}")
        html = fetch_with_drission(url, wait_time=selenium_wait, headless=True)
        if validate(html):
            logger.info("DrissionPage headless succeeded")
            return html

    # Strategy 4: DrissionPage headed (last resort, requires display)
    if HAS_DRISSION and anti_bot_level == 0:
        logger.info(f"Last resort: trying DrissionPage headed for {url}")
        html = fetch_with_drission(url, wait_time=selenium_wait, headless=False)
        if validate(html):
            logger.info("DrissionPage headed succeeded")
            return html

    # Final fallback: simple requests
    logger.info(f"Falling back to simple requests for {url}")
    return fetch_html(url, timeout)


# ========== Parsing Utilities ==========

def parse_date(date_str: str, formats: list[str] = None) -> Optional[datetime]:
    """Parse date string with multiple format support (EN + CN)."""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Handle Chinese date formats like "2026-04-24 17:19" or "2026年04月24日"
    cn_patterns = [
        (r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2})", "%Y-%m-%d %H:%M"),
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日", None),
    ]
    for pattern, fmt in cn_patterns:
        match = re.match(pattern, date_str)
        if match:
            if fmt:
                try:
                    dt = datetime.strptime(match.group(0), fmt)
                    return dt.replace(tzinfo=pytz.UTC)
                except ValueError:
                    pass
            else:
                try:
                    y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    return datetime(y, m, d, tzinfo=pytz.UTC)
                except (ValueError, IndexError):
                    pass

    default_formats = [
        "%B %d, %Y",          # January 15, 2026
        "%b %d, %Y",          # Jan 15, 2026
        "%Y-%m-%d",           # 2026-01-15
        "%m/%d/%Y",           # 01/15/2026
        "%d %B %Y",           # 15 January 2026
        "%d %b %Y",           # 15 Jan 2026
        "%Y-%m-%dT%H:%M:%S",  # ISO format
        "%Y-%m-%dT%H:%M:%SZ", # ISO with Z
        "%b %d %Y",           # Jan 15 2026
        "%B %d %Y",           # January 15 2026
    ]
    
    for fmt in (formats or default_formats):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=pytz.UTC)
            return dt
        except ValueError:
            continue
    
    return None


def extract_text(element, strip: bool = True) -> str:
    """Extract text from BeautifulSoup element."""
    if element is None:
        return ""
    text = element.get_text(separator=" ", strip=strip)
    return " ".join(text.split()) if strip else text


def extract_images(soup: BeautifulSoup, base_url: str = "") -> list[str]:
    """Extract all image URLs from parsed HTML."""
    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            if base_url and not src.startswith(("http://", "https://")):
                src = urljoin(base_url, src)
            images.append(src)
    return images


def extract_media(soup: BeautifulSoup, base_url: str = "") -> list[dict]:
    """Extract media (video, audio, youtube) from HTML."""
    media = []
    
    for video in soup.find_all("video"):
        src = video.get("src")
        if not src:
            source = video.find("source")
            if source:
                src = source.get("src")
        if src:
            if base_url and not src.startswith(("http://", "https://")):
                src = urljoin(base_url, src)
            media.append({"type": "video", "url": src})
    
    for audio in soup.find_all("audio"):
        src = audio.get("src")
        if not src:
            source = audio.find("source")
            if source:
                src = source.get("src")
        if src:
            if base_url and not src.startswith(("http://", "https://")):
                src = urljoin(base_url, src)
            media.append({"type": "audio", "url": src})
    
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src") or ""
        if "youtube.com" in src or "youtu.be" in src:
            media.append({"type": "youtube", "url": src})
    
    return media


def clean_html_content(html: str) -> str:
    """Clean HTML for RSS content."""
    soup = BeautifulSoup(html, "html.parser")
    
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    
    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def extract_article_content(
    soup: BeautifulSoup,
    selectors: list[str] = None,
    min_length: int = 100
) -> tuple[Optional[str], Optional[str]]:
    """
    Extract article content from HTML, returning both HTML and plain text.
    
    Args:
        soup: BeautifulSoup object of the page
        selectors: CSS selectors to try for content area
        min_length: Minimum content length to accept
    
    Returns:
        Tuple of (content_html, content_text) or (None, None) if failed
    """
    if selectors is None:
        selectors = [
            "article", ".article-content", ".post-content", 
            ".content-area", ".main-content", "main .content", "main"
        ]
    
    for selector in selectors:
        elem = soup.select_one(selector)
        if not elem:
            continue
        
        # Remove unwanted elements
        for tag in elem.select("nav, footer, aside, script, style, header, .sidebar, .navigation"):
            tag.decompose()
        
        # Find content paragraphs
        paragraphs = elem.find_all(["p", "h2", "h3", "h4", "li", "pre", "code", "blockquote"])
        if not paragraphs:
            continue
        
        html_parts = []
        text_parts = []
        
        for p in paragraphs:
            text = p.get_text(strip=True)
            if not text or len(text) < 20:
                continue
            
            tag_name = p.name
            if tag_name in ["h2", "h3", "h4"]:
                html_parts.append(f"<{tag_name}>{text}</{tag_name}>")
            elif tag_name in ["pre", "code"]:
                html_parts.append(f"<pre><code>{text}</code></pre>")
            elif tag_name == "li":
                html_parts.append(f"<p>- {text}</p>")
            elif tag_name == "blockquote":
                html_parts.append(f"<blockquote>{text}</blockquote>")
            else:
                html_parts.append(f"<p>{text}</p>")
            text_parts.append(text)
        
        if html_parts and len("\n".join(text_parts)) >= min_length:
            return "\n".join(html_parts), "\n\n".join(text_parts)
    
    # Fallback: try all paragraphs
    paragraphs = soup.find_all("p")
    html_parts = []
    text_parts = []
    
    for p in paragraphs[:30]:
        text = p.get_text(strip=True)
        if len(text) > 50:
            html_parts.append(f"<p>{text}</p>")
            text_parts.append(text)
    
    if html_parts and len("\n".join(text_parts)) >= min_length:
        return "\n".join(html_parts), "\n\n".join(text_parts)
    
    return None, None


# ========== URL Utilities ==========

def normalize_url(url: str, base_url: str = "") -> str:
    """Normalize URL, resolve relative paths."""
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if base_url:
        return urljoin(base_url, url)
    return url


def extract_year_from_url(url: str) -> Optional[int]:
    """Extract year from URL path."""
    match = re.search(r'/(\d{4})/', url)
    if match:
        year = int(match.group(1))
        if 2000 <= year <= 2100:
            return year
    return None
