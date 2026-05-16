#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Base class for documentation site crawlers.
Supports recursive crawling, content extraction, and RSS generation.
"""

import logging
import re
from datetime import datetime
from typing import Optional, Set, List
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import pytz
from bs4 import BeautifulSoup, Tag

from generators.base import Article, BaseFeedGenerator, stable_fallback_date
from generators.http_utils import smart_fetch, extract_text, clean_html_content, fetch_html


class BaseDocsCrawler(BaseFeedGenerator):
    """Base class for documentation site crawlers with index file support."""
    
    # Subclasses should override these
    BASE_URL = ""  # e.g., "https://docs.example.com"
    DOCS_PATH_PATTERN = r""  # Regex to match doc URLs, e.g., r"/docs/"
    
    # Index files to try (in order)
    INDEX_FILES = [
        "llms.txt",      # AI-optimized documentation index
        "sitemap.xml",   # Standard XML sitemap
    ]
    
    # URL patterns to EXCLUDE (blog, news, showcase, etc.)
    EXCLUDE_PATTERNS = [
        r'/blog/',
        r'/news/',
        r'/showcase/',
        r'/changelog',
        r'/releases',
        r'/pricing',
        r'/about',
        r'/zh/',        # Chinese docs
        r'/zh-CN/',     # Chinese (Simplified)
        r'/zh-TW/',     # Chinese (Traditional)  
        r'/ja/',        # Japanese
        r'/ko/',        # Korean
        r'/fr/',        # French
        r'/de/',        # German
        r'/es/',        # Spanish
        r'/pt/',        # Portuguese
        r'/ru/',        # Russian
    ]
    
    # Content extraction selectors (in priority order)
    CONTENT_SELECTORS = [
        "article",
        "main",
        ".content",
        ".documentation",
        "[role='main']",
    ]
    
    # Elements to remove from content
    REMOVE_SELECTORS = [
        "nav",
        "header",
        "footer",
        ".navigation",
        ".toc",
        ".sidebar",
        "script",
        "style",
        "[class*='nav']",
        "[class*='breadcrumb']",
    ]
    
    MAX_DEPTH = 3  # Maximum recursion depth
    MAX_PAGES = 300  # Maximum pages to crawl
    
    def __init__(self):
        super().__init__()
        self._visited_urls: Set[str] = set()
        self._discovered_urls: Set[str] = set()
    
    def fetch_doc_index(self) -> Optional[List[str]]:
        """Try to fetch documentation index from llms.txt or sitemap.xml."""
        for index_file in self.INDEX_FILES:
            # Ensure BASE_URL ends with /
            base = self.BASE_URL if self.BASE_URL.endswith('/') else self.BASE_URL + '/'
            index_url = urljoin(base, index_file)
            self.logger.info(f"Trying index file: {index_url}")
            
            try:
                content = fetch_html(index_url)
                if not content:
                    self.logger.debug(f"No content returned from {index_url}")
                    continue
                
                self.logger.debug(f"Fetched {len(content)} bytes from {index_url}")
                
                if index_file.endswith('.txt'):
                    urls = self._parse_llms_txt(content)
                elif index_file.endswith('.xml'):
                    urls = self._parse_sitemap_xml(content)
                else:
                    continue
                
                if urls:
                    self.logger.info(f"Found {len(urls)} URLs in {index_file}")
                    return urls
                else:
                    self.logger.debug(f"Parsed {index_file} but found 0 URLs")
            except Exception as e:
                self.logger.warning(f"Failed to fetch {index_file}: {e}", exc_info=True)
                continue
        
        self.logger.warning("No index file found, will use recursive crawling")
        return None
    
    def _parse_llms_txt(self, content: str) -> List[str]:
        """Parse llms.txt format (Markdown with links)."""
        urls = []
        # Match Markdown links: [text](url)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        
        for match in re.finditer(link_pattern, content):
            url = match.group(2)
            # Remove .md extension and anchors
            url = re.sub(r'\.md(#.*)?$', '', url)
            
            # Make absolute URL
            if not url.startswith(('http://', 'https://')):
                url = urljoin(self.BASE_URL, url)
            
            if self.is_docs_url(url):
                urls.append(url)
        
        return urls
    
    def _parse_sitemap_xml(self, content: str) -> List[str]:
        """Parse sitemap.xml format."""
        urls = []
        
        try:
            root = ET.fromstring(content)
            # Handle namespace
            namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            # Try with namespace
            url_elements = root.findall('.//ns:loc', namespace)
            if not url_elements:
                # Try without namespace
                url_elements = root.findall('.//loc')
            
            for elem in url_elements:
                url = elem.text.strip() if elem.text else ""
                if url and self.is_docs_url(url):
                    urls.append(url)
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse sitemap XML: {e}")
        
        return urls
    
    def is_docs_url(self, url: str) -> bool:
        """Check if URL belongs to documentation."""
        if not url or not url.startswith(("http://", "https://")):
            return False
        
        # Must be same domain (case-insensitive)
        base_domain = urlparse(self.BASE_URL).netloc.lower()
        url_domain = urlparse(url).netloc.lower()
        if base_domain != url_domain:
            return False
        
        # Must match path pattern
        if self.DOCS_PATH_PATTERN:
            if not re.search(self.DOCS_PATH_PATTERN, url):
                return False
        
        # Skip anchors, downloads, etc.
        skip_patterns = [
            r'#',  # Anchors
            r'\.(pdf|zip|tar|gz|jpg|png|gif)$',  # Downloads/images
        ]
        for pattern in skip_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        
        # Exclude non-documentation content
        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                self.logger.debug(f"Excluded URL (matches {pattern}): {url}")
                return False
        
        return True
    
    def discover_links(self, html: str, base_url: str) -> Set[str]:
        """Discover documentation links from page."""
        soup = BeautifulSoup(html, "html.parser")
        links = set()
        
        # Try navigation selectors first
        for selector in self.NAV_SELECTORS:
            nav_links = soup.select(selector)
            if nav_links:
                for link in nav_links:
                    href = link.get("href", "")
                    if href:
                        full_url = urljoin(base_url, href)
                        if self.is_docs_url(full_url):
                            links.add(full_url)
        
        # If no nav links found, try all links on page
        if not links:
            all_links = soup.find_all("a", href=True)
            for link in all_links:
                href = link["href"]
                full_url = urljoin(base_url, href)
                if self.is_docs_url(full_url):
                    links.add(full_url)
        
        return links
    
    def extract_doc_content(self, html: str, url: str) -> Optional[dict]:
        """Extract documentation content from page."""
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract title
        title = None
        title_elem = soup.find("h1")
        if title_elem:
            title = extract_text(title_elem)
        
        if not title:
            # Fallback to page title
            title_tag = soup.find("title")
            if title_tag:
                title = extract_text(title_tag)
        
        if not title or len(title) < 3:
            return None
        
        # Extract main content
        content_elem = None
        for selector in self.CONTENT_SELECTORS:
            elem = soup.select_one(selector)
            if elem:
                content_elem = elem
                break
        
        if not content_elem:
            self.logger.warning(f"No content found for {url}")
            return None
        
        # Remove unwanted elements
        for selector in self.REMOVE_SELECTORS:
            for elem in content_elem.select(selector):
                elem.decompose()
        
        # Clean and extract content
        content_html = clean_html_content(str(content_elem))
        
        # Extract plain text for summary
        text_content = content_elem.get_text(separator="\n", strip=True)
        summary = text_content[:500] + "..." if len(text_content) > 500 else text_content
        
        return {
            "title": title,
            "content": content_html,
            "summary": summary,
            "text_length": len(text_content),
        }
    
    def crawl_page(self, url: str, depth: int = 0) -> Optional[Article]:
        """Crawl a single documentation page."""
        if url in self._visited_urls:
            return None
        
        self._visited_urls.add(url)
        
        # Fetch page (use JS if needed)
        require_js = getattr(self, 'REQUIRE_JS', False)
        html = smart_fetch(url, require_js=require_js)
        if not html:
            self.logger.warning(f"Failed to fetch {url}")
            return None
        
        # Extract content
        doc_data = self.extract_doc_content(html, url)
        if not doc_data:
            self.logger.debug(f"No content extracted from {url}")
            return None
        
        # Create article
        article = Article(
            url=url,
            title=doc_data["title"],
            published_at=stable_fallback_date(url),
            content=doc_data["content"],
            summary=doc_data["summary"],
            category=self._extract_category_from_url(url),
        )
        
        return article
    
    def _extract_category_from_url(self, url: str) -> str:
        """Extract category from URL path for better organization."""
        from urllib.parse import urlparse
        
        path = urlparse(url).path.lower()
        
        # Common documentation categories
        category_keywords = {
            "getting-started": "Getting Started",
            "quickstart": "Getting Started",
            "intro": "Getting Started",
            "guide": "Guides",
            "tutorial": "Tutorials",
            "api": "API Reference",
            "reference": "Reference",
            "integration": "Integrations",
            "plugin": "Plugins",
            "extension": "Extensions",
            "agent": "Agent",
            "model": "Models",
            "cli": "CLI",
            "skill": "Skills",
            "rule": "Rules",
            "mcp": "MCP",
            "cloud": "Cloud",
            "configuration": "Configuration",
            "config": "Configuration",
            "setup": "Setup",
            "installation": "Installation",
            "deployment": "Deployment",
            "advanced": "Advanced",
            "best-practice": "Best Practices",
            "troubleshoot": "Troubleshooting",
            "faq": "FAQ",
        }
        
        for keyword, category in category_keywords.items():
            if keyword in path:
                return category
        
        return "Documentation"
    
    def fetch_articles(self) -> list[Article]:
        """Fetch documentation pages from index file or recursive crawling."""
        self._visited_urls.clear()
        self._discovered_urls.clear()
        
        # Try to get URLs from index file first
        index_urls = self.fetch_doc_index()
        
        if index_urls:
            # Use index file
            self.logger.info(f"Using index file with {len(index_urls)} URLs")
            urls_to_crawl = index_urls[:self.MAX_PAGES]
        else:
            # Fallback to recursive crawling
            self.logger.info("Using recursive crawling")
            urls_to_crawl = [self.FEED_URL]
        
        articles = []
        
        for i, url in enumerate(urls_to_crawl):
            if len(articles) >= self.MAX_PAGES:
                break
            
            self.logger.info(f"[{i+1}/{len(urls_to_crawl)}] Crawling {url}")
            article = self.crawl_page(url, depth=0)
            if article:
                articles.append(article)
        
        # Sort articles by category and title for better organization
        category_order = {
            "Getting Started": 0,
            "Setup": 1,
            "Installation": 2,
            "Guides": 3,
            "Tutorials": 4,
            "Agent": 5,
            "Models": 6,
            "CLI": 7,
            "Skills": 8,
            "Rules": 9,
            "MCP": 10,
            "Integrations": 11,
            "Plugins": 12,
            "Extensions": 13,
            "Cloud": 14,
            "API Reference": 15,
            "Reference": 16,
            "Configuration": 17,
            "Advanced": 18,
            "Best Practices": 19,
            "Troubleshooting": 20,
            "FAQ": 21,
            "Documentation": 99,
        }
        
        articles.sort(key=lambda a: (
            category_order.get(a.category, 99),
            a.title.lower()
        ))
        
        self.logger.info(f"Crawled {len(articles)} documentation pages")
        return articles
    
    def fetch_article_content(self, url: str) -> Optional[Article]:
        """Fetch is already done in fetch_articles, return None."""
        return None
