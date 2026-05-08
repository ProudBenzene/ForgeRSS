#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check AI coding docs feeds statistics."""

import xml.etree.ElementTree as ET
import os

feeds = [
    'feeds/feed_openai_codex_docs.xml',
    'feeds/feed_claude_code_docs.xml',
    'feeds/feed_cursor_docs.xml',
    'feeds/feed_qwen_code_docs.xml'
]

print('=' * 60)
print('AI Coding Tools Documentation Statistics')
print('=' * 60)

total_articles = 0
for feed_path in feeds:
    if os.path.exists(feed_path):
        tree = ET.parse(feed_path)
        root = tree.getroot()
        channel = root.find('channel')
        title = channel.find('title').text
        items = channel.findall('item')
        count = len(items)
        total_articles += count
        size_kb = os.path.getsize(feed_path) // 1024
        print(f'\n[OK] {title}')
        print(f'     Articles: {count}')
        print(f'     File: {feed_path}')
        print(f'     Size: {size_kb} KB')
    else:
        print(f'\n[ERROR] {feed_path} - File not found')

print('\n' + '=' * 60)
print(f'Total: {total_articles} articles')
print('=' * 60)
