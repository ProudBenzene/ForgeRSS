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

logger.info(f"HTTP engines: curl_cffi={HAS_CURL_CFFI}, selenium={HAS_SELENIUM}")


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
        options.add_argument(f"--user-agent={BROWSER_HEADERS['User-Agent']}")
        
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


def smart_fetch(
    url: str,
    require_js: bool = False,
    content_check: str = None,
    timeout: int = 30,
    selenium_wait: int = 5,
    selenium_selector: str = None
) -> Optional[str]:
    """
    Smart fetch with automatic fallback.
    
    Strategy:
    1. If require_js=False, try curl_cffi first
    2. If curl_cffi fails or content_check not found, use selenium
    
    Args:
        url: Page URL
        require_js: Skip curl_cffi, go straight to selenium
        content_check: String that must exist in result (e.g., '/news/')
        timeout: Request timeout
        selenium_wait: Selenium wait time
        selenium_selector: Selenium wait-for selector
    
    Returns:
        HTML content or None
    """
    # Strategy 1: Try curl_cffi (fast)
    if not require_js and HAS_CURL_CFFI:
        logger.info(f"Trying curl_cffi for {url}")
        html = fetch_with_curl_cffi(url, timeout)
        
        if html:
            # Check if content is valid
            if content_check is None or content_check in html:
                logger.info("curl_cffi succeeded")
                return html
            else:
                logger.info(f"curl_cffi got page but missing '{content_check}', trying selenium")
    
    # Strategy 2: Selenium (handles JS)
    if HAS_SELENIUM:
        logger.info(f"Trying selenium for {url}")
        html = fetch_with_selenium(
            url,
            wait_time=selenium_wait,
            wait_for_selector=selenium_selector
        )
        if html:
            logger.info("Selenium succeeded")
            return html
    
    # Strategy 3: Fallback to simple requests
    logger.info(f"Falling back to requests for {url}")
    return fetch_html(url, timeout)


# ========== Parsing Utilities ==========

def parse_date(date_str: str, formats: list[str] = None) -> Optional[datetime]:
    """Parse date string with multiple format support."""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
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

def extract_article_content(
    soup,
    selectors=None,
    min_length=100
):
    """
    Extract article content from HTML, returning both HTML and plain text.
    
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
