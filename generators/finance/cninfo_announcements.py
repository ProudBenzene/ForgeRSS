#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CNInfo Announcements RSS Generator
基于开源项目逆向工程成果
"""

import os
import re
import time
import json
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import pytz
from dataclasses import dataclass

from generators.base import BaseFeedGenerator, Article

# 配置常量
CNINFO_API_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE_URL = "http://static.cninfo.com.cn/"

# 附件下载目录（基于项目根的绝对路径，避免 cwd 依赖）。
# cninfo_announcements.py 位于 generators/finance/，向上 3 层到达项目根。
ATTACHMENTS_DIR = Path(__file__).resolve().parent.parent.parent / "downloads" / "cninfo_pdfs"

# 市场类型
MARKETS = {
    'szse': '深交所',
    'sse': '上交所', 
    'fund': '基金',
    'bond': '债券'
}


class CninfoAnnouncementsGenerator(BaseFeedGenerator):
    """CNInfo Announcements RSS Generator"""
    
    FEED_NAME = "cninfo_announcements"
    FEED_TITLE = "巨潮资讯网 - 公司公告"
    FEED_URL = "http://www.cninfo.com.cn/"
    FEED_DESCRIPTION = "巨潮资讯网公司公告RSS订阅"
    
    def __init__(self):
        super().__init__()

        # === 订阅方式（三选一）===
        # 1) 按主题关键词（推荐）：CNINFO_KEYWORDS="股权激励,业绩快报"
        #    会在公告全文里搜索这些关键词，适合按"事件类型"订阅。
        # 2) 按分类：CNINFO_CATEGORY=category_ndbg_szsh  → 全市场该分类
        # 3) 不配 → 按市场拉最新公告（默认 szse + sse）
        #
        # 旧字段 CNINFO_COMPANIES 作为 CNINFO_KEYWORDS 的别名（向下兼容）。
        keywords_raw = (
            os.getenv('CNINFO_KEYWORDS')
            or os.getenv('CNINFO_COMPANIES')
            or ''
        )
        self.keywords = [k.strip() for k in keywords_raw.split(',') if k.strip()]

        self.category = os.getenv('CNINFO_CATEGORY', '').strip()
        self.markets = [m.strip() for m in os.getenv('CNINFO_MARKETS', 'szse,sse').split(',') if m.strip()]
        self.days = int(os.getenv('CNINFO_DAYS', '7'))
        self.download_pdf = os.getenv('CNINFO_DOWNLOAD_PDF', 'true').lower() == 'true'
        self.max_items = int(os.getenv('CNINFO_MAX_ITEMS', '50'))

        # Rate limiting (avoid getting blocked)
        self.request_interval = float(os.getenv('CNINFO_REQUEST_INTERVAL', '2.0'))

        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

    def fetch_articles(self) -> List[Article]:
        """获取公告列表"""
        articles = []

        if self.keywords:
            # By theme keywords (full-text search)
            for kw in self.keywords:
                self.logger.info(f"Fetching announcements by keyword: {kw!r}")
                articles.extend(self._fetch_by_keyword(kw))
                time.sleep(self.request_interval)
        elif self.category:
            # By category (e.g., annual reports across all listed companies)
            self.logger.info(f"Fetching announcements by category: {self.category}")
            for market in self.markets:
                articles.extend(self._fetch_by_market(market, category=self.category))
                time.sleep(self.request_interval)
        else:
            # Default: latest from each configured market
            for market in self.markets:
                self.logger.info(f"Fetching latest announcements from market: {market}")
                articles.extend(self._fetch_by_market(market))
                time.sleep(self.request_interval)

        return articles
    
    def _fetch_by_keyword(self, keyword: str) -> List[Article]:
        """Fetch announcements containing a theme keyword (full-text search).

        Best used for topical subscriptions like '股权激励'、'回购'、'业绩快报' —
        the upstream search matches the keyword inside announcement titles
        and full text, returning announcements from many different listed
        companies. It is NOT a per-company filter; if you pass a stock code
        you'll get unrelated announcements that happen to mention that
        numeric string.
        """
        articles = []

        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=self.days)).strftime('%Y-%m-%d')

        payload = {
            'pageNum': 1,
            'pageSize': min(self.max_items, 50),
            'column': 'szse',
            'tabName': 'fulltext',
            'plate': '',
            'stock': '',
            'searchkey': keyword,
            'secid': '',
            'category': '',
            'trade': '',
            'seDate': f'{start_date}~{end_date}',
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'http://www.cninfo.com.cn/'
        }
        
        try:
            response = requests.post(
                CNINFO_API_URL, 
                data=payload, 
                headers=headers, 
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                announcements = data.get('announcements', [])
                
                self.logger.info(f"Found {len(announcements)} announcements for keyword {keyword!r}")
                
                for ann in announcements:
                    article = self._parse_announcement(ann)
                    if article:
                        articles.append(article)
            else:
                self.logger.error(f"Request failed: {response.status_code}")
        
        except Exception as e:
            self.logger.error(f"Error fetching keyword {keyword!r}: {e}")

        return articles

    def _fetch_by_market(self, market: str, category: str = '') -> List[Article]:
        """Fetch announcements from a market, optionally narrowed by category.

        `category` examples: 'category_ndbg_szsh' (annual reports),
        'category_yjkb_szsh' (preliminary results), 'category_gqjl_szsh'
        (equity incentives). When set, results across all listed companies
        are filtered to that category.
        """
        articles = []

        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=self.days)).strftime('%Y-%m-%d')

        payload = {
            'pageNum': 1,
            'pageSize': min(self.max_items, 30),
            'column': market,
            'tabName': 'fulltext',
            'plate': '',
            'stock': '',
            'searchkey': '',
            'secid': '',
            'category': category,
            'trade': '',
            'seDate': f'{start_date}~{end_date}',
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'http://www.cninfo.com.cn/'
        }
        
        try:
            response = requests.post(
                CNINFO_API_URL,
                data=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                announcements = data.get('announcements', [])
                
                self.logger.info(f"Found {len(announcements)} announcements for {MARKETS.get(market, market)}")
                
                for ann in announcements:
                    article = self._parse_announcement(ann)
                    if article:
                        articles.append(article)
            else:
                self.logger.error(f"Request failed: {response.status_code}")
        
        except Exception as e:
            self.logger.error(f"Error fetching market {market}: {e}")
        
        return articles
    
    def _parse_announcement(self, ann: Dict) -> Optional[Article]:
        """解析公告数据"""
        try:
            # 基本信息
            sec_code = ann.get('secCode', '')
            sec_name = ann.get('secName', '')
            title = ann.get('announcementTitle', '')
            ann_time = ann.get('announcementTime')
            
            # Convert timestamp (milliseconds)
            if ann_time:
                pub_date = datetime.fromtimestamp(ann_time / 1000, tz=pytz.UTC)
            else:
                pub_date = datetime.now(pytz.UTC)
            
            # PDF路径
            pdf_path = ann.get('adjunctUrl', '')
            pdf_url = f"{PDF_BASE_URL}{pdf_path}" if pdf_path else ""
            
            # Download PDF (if configured)
            local_pdf_path = None
            if self.download_pdf and pdf_url:
                local_pdf_path = self._download_pdf(pdf_url, sec_code, title, sec_name=sec_name)
            
            # 构建内容
            content_parts = [
                f'<h3>{title}</h3>',
                f'<p><strong>股票代码:</strong> {sec_code}</p>',
                f'<p><strong>股票名称:</strong> {sec_name}</p>',
                f'<p><strong>公告时间:</strong> {pub_date.strftime("%Y-%m-%d %H:%M:%S")}</p>',
            ]
            
            if pdf_url:
                content_parts.append(f'<p><strong>PDF下载:</strong> <a href="{pdf_url}">查看原文</a></p>')
            
            if local_pdf_path:
                content_parts.append(f'<p><strong>本地路径:</strong> <code>{local_pdf_path}</code></p>')
            
            content = '\n'.join(content_parts)
            
            # 创建Article对象
            article = Article(
                url=pdf_url if pdf_url else f"http://www.cninfo.com.cn/",
                title=f"[{sec_name}] {title}",
                published_at=pub_date,
                content=content,
                summary=title[:200],
                category="公司公告",
                author="巨潮资讯网",
            )
            
            return article
        
        except Exception as e:
            self.logger.error(f"Error parsing announcement: {e}")
            return None
    
    def _download_pdf(self, pdf_url: str, sec_code: str, title: str, sec_name: str = "") -> Optional[str]:
        """Download PDF locally."""
        try:
            # Sanitize filename (Windows/POSIX safe; cap at 50 chars to avoid
            # MAX_PATH on Windows).
            def _safe(s: str, max_len: int = 50) -> str:
                s = re.sub(r'[\\/:*?"<>|\r\n\t]', '_', (s or "").strip())
                s = re.sub(r'\s+', ' ', s).rstrip(". ")
                return s[:max_len].rstrip(". ")

            safe_title = _safe(title)
            filename = f"{sec_code}_{safe_title}.pdf"

            # 公司目录：用 <公司名>_<股票代码> 命名（可读+唯一），fallback 到纯代码。
            safe_name = _safe(sec_name, max_len=30)
            company_dir_name = f"{safe_name}_{sec_code}" if safe_name else sec_code
            company_dir = ATTACHMENTS_DIR / company_dir_name
            company_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = company_dir / filename
            
            # 如果文件已存在，跳过
            if file_path.exists():
                try:
                    return str(file_path.relative_to(self.base_dir))
                except:
                    return str(file_path)
            
            # 下载PDF
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'http://www.cninfo.com.cn/'
            }
            
            response = requests.get(pdf_url, headers=headers, stream=True, timeout=60)
            
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                file_size = file_path.stat().st_size
                self.logger.info(f"Downloaded: {filename} ({file_size / 1024:.1f} KB)")
                
                # 返回相对路径，如果失败则返回绝对路径
                try:
                    return str(file_path.relative_to(self.base_dir))
                except:
                    return str(file_path)
            else:
                self.logger.warning(f"PDF download failed: {response.status_code}")
                return None
        
        except Exception as e:
            self.logger.error(f"Error downloading PDF: {e}")
            return None


def main():
    """测试运行"""
    import argparse
    
    parser = argparse.ArgumentParser(description='CNInfo Announcements RSS Generator')
    parser.add_argument('--keywords', help='主题关键词，逗号分隔（如 "股权激励,业绩快报"）')
    parser.add_argument('--category', help='公告分类代码（如 category_ndbg_szsh）', default='')
    parser.add_argument('--markets', help='市场列表，逗号分隔（默认 szse,sse）', default='szse,sse')
    parser.add_argument('--days', type=int, help='获取最近N天的公告', default=7)
    parser.add_argument('--max', type=int, help='最多获取多少条公告', default=5)
    parser.add_argument('--download-pdf', action='store_true', help='是否下载PDF')
    parser.add_argument('--full', action='store_true', help='完整刷新（忽略缓存）')

    args = parser.parse_args()

    if args.keywords:
        os.environ['CNINFO_KEYWORDS'] = args.keywords
    if args.category:
        os.environ['CNINFO_CATEGORY'] = args.category
    if args.markets:
        os.environ['CNINFO_MARKETS'] = args.markets
    os.environ['CNINFO_DAYS'] = str(args.days)
    os.environ['CNINFO_MAX_ITEMS'] = str(args.max)
    os.environ['CNINFO_DOWNLOAD_PDF'] = 'true' if args.download_pdf else 'false'
    
    # Run generator
    generator = CninfoAnnouncementsGenerator()
    result = generator.run(full_refresh=args.full, max_articles=args.max)
    
    if result:
        print(f"\n[OK] 成功生成RSS feed")
    else:
        print(f"\n[ERROR] 生成失败")


if __name__ == '__main__':
    main()
