#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
RSS Streaming Generator - Memory-efficient RSS generation
Based on wechat-download-api/saas streaming approach
"""

import logging
from datetime import datetime, timezone
from typing import Iterator, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    if not text:
        return ""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))


@dataclass
class Article:
    """Article data for RSS generation."""
    url: str
    title: str
    published_at: datetime
    content: str
    summary: str = ""
    category: str = "General"
    author: str = ""


def _build_item_xml(article: Article, include_original_link: bool = True) -> str:
    """
    Build RSS item XML string (pure string concatenation, no lxml required)
    """
    # Format date
    pub_date = article.published_at.strftime("%a, %d %b %Y %H:%M:%S +0000")
    
    # Build content HTML
    content_html = f'<div style="font-size:16px;line-height:1.8;color:#333">{article.content}</div>'
    
    if article.summary:
        content_html = f'<p style="color:#666;font-size:14px;margin-bottom:16px">{_escape_xml(article.summary)}</p>' + content_html
    
    # Most feeds benefit from an explicit original-article link. Generators
    # whose content already has a canonical clickable element can disable it
    # to avoid presenting the same destination multiple times.
    if include_original_link:
        content_html += (
            f'<hr style="margin:24px 0;border:none;border-top:1px solid #eee"/>'
            f'<p style="margin:12px 0 0"><a href="{_escape_xml(article.url)}" '
            f'style="color:#1890ff;text-decoration:none;font-size:14px">'
            f'View Original &rarr;</a></p>'
        )
    
    # Build XML
    xml_parts = ['<item>\n']
    xml_parts.append(f'  <title>{_escape_xml(article.title)}</title>\n')
    xml_parts.append(f'  <link>{_escape_xml(article.url)}</link>\n')
    xml_parts.append(f'  <guid isPermaLink="false">{_escape_xml(article.url)}</guid>\n')
    xml_parts.append(f'  <pubDate>{pub_date}</pubDate>\n')
    
    if article.category:
        xml_parts.append(f'  <category>{_escape_xml(article.category)}</category>\n')
    
    if article.author:
        xml_parts.append(f'  <author>{_escape_xml(article.author)}</author>\n')
    
    # Wrap description in CDATA
    xml_parts.append(f'  <description><![CDATA[{content_html}]]></description>\n')
    xml_parts.append(f'  <content:encoded><![CDATA[{content_html}]]></content:encoded>\n')
    xml_parts.append('</item>\n')
    
    return "".join(xml_parts)


def generate_rss_stream(
    title: str,
    link: str,
    description: str,
    articles: List[Article],
    language: str = "en",
    logo_url: Optional[str] = None,
    batch_size: int = 100,
    include_original_link: bool = True,
) -> Iterator[bytes]:
    """
    Stream-generate RSS feed.
    
    Memory advantage: Process articles in small batches (~100 at a time),
    releasing memory immediately after processing.
    
    Args:
        title: Feed title
        link: Feed link
        description: Feed description
        articles: List of articles (already sorted)
        language: Feed language
        logo_url: Optional logo URL
        batch_size: Articles per batch
    
    Yields:
        Bytes of XML content
    """
    
    # ==================== RSS Header ====================
    yield b'<?xml version="1.0" encoding="UTF-8"?>\n'
    yield b'<rss version="2.0" '
    yield b'xmlns:atom="http://www.w3.org/2005/Atom" '
    yield b'xmlns:content="http://purl.org/rss/1.0/modules/content/">\n'
    yield b'<channel>\n'
    
    # Channel metadata
    yield f'<title>{_escape_xml(title)}</title>\n'.encode('utf-8')
    yield f'<link>{_escape_xml(link)}</link>\n'.encode('utf-8')
    yield f'<description>{_escape_xml(description)}</description>\n'.encode('utf-8')
    yield f'<language>{_escape_xml(language)}</language>\n'.encode('utf-8')
    
    last_build = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    yield f'<lastBuildDate>{last_build}</lastBuildDate>\n'.encode('utf-8')
    yield b'<generator>ForgeRSS</generator>\n'
    
    # atom:link (self reference)
    atom_link = f'<atom:link href="{_escape_xml(link)}" rel="self" type="application/rss+xml"/>\n'
    yield atom_link.encode('utf-8')
    
    # Logo/Image
    if logo_url:
        yield b'<image>\n'
        yield f'  <url>{_escape_xml(logo_url)}</url>\n'.encode('utf-8')
        yield f'  <title>{_escape_xml(title)}</title>\n'.encode('utf-8')
        yield f'  <link>{_escape_xml(link)}</link>\n'.encode('utf-8')
        yield b'</image>\n'
    
    # ==================== Process Articles in Batches ====================
    total_articles = len(articles)
    article_count = 0
    
    for i in range(0, total_articles, batch_size):
        batch = articles[i:i + batch_size]
        
        for article in batch:
            try:
                item_xml = _build_item_xml(
                    article,
                    include_original_link=include_original_link,
                )
                yield item_xml.encode('utf-8')
                article_count += 1
            except Exception as e:
                logger.error(f"Failed to build XML for article {article.url}: {e}")
                continue
    
    # ==================== RSS Footer ====================
    yield b'</channel>\n'
    yield b'</rss>\n'
    
    logger.info(f"[RSS Stream] Generated feed with {article_count} articles (batches of {batch_size})")


def save_rss_stream(
    output_path: str,
    title: str,
    link: str,
    description: str,
    articles: List[Article],
    language: str = "en",
    logo_url: Optional[str] = None,
    batch_size: int = 100,
    include_original_link: bool = True,
) -> int:
    """
    Save RSS feed to file using streaming generation.
    
    Args:
        output_path: Path to save RSS file
        (other args same as generate_rss_stream)
    
    Returns:
        Number of articles written
    """
    article_count = 0
    
    with open(output_path, 'wb') as f:
        for chunk in generate_rss_stream(
            title=title,
            link=link,
            description=description,
            articles=articles,
            language=language,
            logo_url=logo_url,
            batch_size=batch_size,
            include_original_link=include_original_link,
        ):
            f.write(chunk)
            # Count articles (each item starts with <item>)
            if b'<item>' in chunk:
                article_count += chunk.count(b'<item>')
    
    return article_count
