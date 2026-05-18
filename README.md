<div align="center">

# ForgeRSS

### 将任意网站转换为 RSS 订阅源 | 多引擎抓取 + 反爬突破 + 社交媒体支持 | 完全开源免费

**完全开源 | 免费使用 | 自动更新 | 多引擎抓取 | 政府网站反爬突破 | Docker 支持**

[![GitHub stars](https://img.shields.io/github/stars/tmwgsicp/ForgeRSS?style=for-the-badge&logo=github)](https://github.com/tmwgsicp/ForgeRSS/stargazers)
[![License](https://img.shields.io/badge/License-AGPL%203.0-blue?style=for-the-badge)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/tmwgsicp/forgerss?style=for-the-badge&logo=docker&logoColor=white)](https://hub.docker.com/r/tmwgsicp/forgerss)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)

> **100% 开源，100% 免费。** 代码完全公开，私有化部署无任何限制，不搞"开源"之名行收费之实。

</div>

---

## 功能特性

- **多引擎抓取** — curl_cffi + Selenium + DrissionPage，自动选择最优方案
- **AI 编程工具文档订阅** — 支持 OpenAI Codex、Claude Code、Cursor、Qwen Code 等完整开发文档抓取
- **社交媒体订阅** — 知乎、B 站、小红书、知识星球，统一登录态管理 + URL/纯 ID 双输入
- **公司公告订阅** — 巨潮资讯网，支持「关键词主题 / 分类 / 全市场最新」三种模式 + PDF 自动下载
- **附件归档** — 知识星球帖子内的 PDF / 音频 / 图片按 `<群名>_<群ID>/<话题>_<topicID>/` 自动归档；B 站视频可选下载
- **智能登录态检测** — URL 重定向 + HTML 关键词三层判断，登录态过期自动通知，Profile 复用零配置
- **流式 RSS 生成** — 内存优化的批量处理，支持数百篇长文档
- **政府网站反爬突破** — 支持绕过瑞数信息等商用反爬系统（需桌面环境）
- **智能去重** — 基于 URL 哈希，避免重复文章
- **双存储方案** — JSON 缓存 (GitHub 托管) + SQLite (本地/Docker)
- **标准 RSS 2.0** — CDATA 包裹 + 内联样式，兼容 Readwise、FreshRSS 等阅读器
- **灵活更新频率** — 新闻每 6 小时更新，文档每周更新，节省资源
- **GitHub Actions** — 全自动定时更新，CI 自动构建 Docker 镜像 + tar 包
- **Docker 支持** — 一键部署，适合自托管

---

## 可用 RSS 订阅源

以下是已部署的 RSS 源，可直接在 RSS 阅读器中订阅：

| 信息源 | 订阅链接 |
|--------|----------|
| **Anthropic News** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_anthropic_news.xml) |
| **Anthropic Research** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_anthropic_research.xml) |
| **Anthropic Engineering** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_anthropic_engineering.xml) |
| **OpenAI Research** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_openai_research.xml) |
| **OpenAI Codex Docs** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_openai_codex_docs.xml) |
| **Claude Code Docs** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_claude_code_docs.xml) |
| **Cursor Docs** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_cursor_docs.xml) |
| **Qwen Code Docs** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_qwen_code_docs.xml) |
| **IDSociety Science Speaks** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_idsociety.xml) |
| **巨潮资讯网公司公告** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_cninfo_announcements.xml) |
| **小宇宙播客（示例订阅）** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_xiaoyuzhou.xml) |
| **雪球用户动态（示例订阅）** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_xueqiu_user.xml) |
| **国家药监局药品公告** | 需本地运行（见下方说明） |
| **知乎热榜** | 需本地运行（见下方说明） |
| **知乎用户动态** | 需本地运行（见下方说明） |
| **B 站 UP 主视频** | 需本地运行（见下方说明） |
| **小红书用户笔记** | 需本地运行（见下方说明） |
| **知识星球话题** | 需本地运行（见下方说明） |
| **抖音用户视频** | 需本地运行（见下方说明） |
| **快手用户视频** | 需本地运行（见下方说明） |
| **微博用户动态** | 需本地运行（见下方说明） |

> **更新频率**：新闻类 Feed 每 6 小时自动更新，文档类 Feed 每周更新一次（周一 00:00 UTC）。所有 Feed 包含完整文章内容，使用 jsDelivr CDN 托管，兼容所有 RSS 阅读器。

### 详细信息源列表

| 信息源 | 分类 | 抓取方式 | Feed 文件 | 更新频率 | 运行环境 |
|--------|------|----------|-----------|----------|----------|
| Anthropic News | AI | curl_cffi | `feed_anthropic_news.xml` | 6小时 | CI/本地 |
| Anthropic Research | AI | curl_cffi | `feed_anthropic_research.xml` | 6小时 | CI/本地 |
| Anthropic Engineering | AI | curl_cffi | `feed_anthropic_engineering.xml` | 6小时 | CI/本地 |
| OpenAI Research | AI | curl_cffi | `feed_openai_research.xml` | 6小时 | CI/本地 |
| OpenAI Codex Docs | AI 编程工具 | curl_cffi + Selenium | `feed_openai_codex_docs.xml` | **每周** | CI/本地 |
| Claude Code Docs | AI 编程工具 | Selenium | `feed_claude_code_docs.xml` | **每周** | CI/本地 |
| Cursor Docs | AI 编程工具 | Selenium | `feed_cursor_docs.xml` | **每周** | CI/本地 |
| Qwen Code Docs | AI 编程工具 | curl_cffi | `feed_qwen_code_docs.xml` | **每周** | CI/本地 |
| IDSociety Science Speaks | 医学 | Selenium | `feed_idsociety.xml` | 6小时 | CI/本地 |
| **国家药监局 (NMPA)** | 政府 | **DrissionPage** | `feed_nmpa_drug.xml` | **手动** | **仅本地** |
| 巨潮资讯网 | 金融 | curl_cffi | `feed_cninfo_announcements.xml` | 6小时 | CI/本地 |
| **知乎热榜** | 社交媒体 | **DrissionPage + 登录** | `feed_zhihu_hot.xml` | **手动** | **仅本地** |
| **知乎用户动态** | 社交媒体 | **DrissionPage + 登录** | `feed_zhihu_user.xml` | **手动** | **仅本地** |
| **B 站 UP 主** | 社交媒体 | **DrissionPage + 登录** | `feed_bilibili_up.xml` | **手动** | **仅本地** |
| **小红书用户** | 社交媒体 | **DrissionPage + 登录** | `feed_xiaohongshu_user.xml` | **手动** | **仅本地** |
| **知识星球话题** | 社交媒体 | **DrissionPage + 登录** | `feed_zsxq_topics.xml` | **手动** | **仅本地** |
| **抖音用户** | 社交媒体 | **DrissionPage + 登录 + CDP + ffmpeg** | `feed_douyin_user.xml` | **手动** | **仅本地** |
| **快手用户** | 社交媒体 | **DrissionPage + 登录 + CDP** | `feed_kuaishou_user.xml` | **手动** | **仅本地** |
| **微博用户** | 社交媒体 | **DrissionPage + 登录** | `feed_weibo_user.xml` | **手动** | **仅本地** |
| 小宇宙播客 | 播客 | curl_cffi (Next.js SSR) | `feed_xiaoyuzhou.xml` | 6小时 | **CI/本地** |
| 雪球用户 | 金融 | DrissionPage headless（无登录） | `feed_xueqiu_user.xml` | 6小时 | **CI/本地** |

---

## 快速使用

### 方式一：直接订阅（推荐）

复制上方订阅链接到你的 RSS 阅读器即可使用。

如需自定义，可 Fork 本项目，启用 GitHub Actions，Feed 会自动生成到 `feeds/` 目录：

```
https://cdn.jsdelivr.net/gh/你的用户名/ForgeRSS@main/feeds/feed_anthropic_news.xml
```

> 使用 jsDelivr CDN 链接可确保正确的 Content-Type，兼容 FreshRSS、Inoreader 等阅读器。

### 方式二：Docker 部署

```bash
# 方式一：使用 docker-compose（推荐）
git clone https://github.com/tmwgsicp/ForgeRSS.git
cd forgerss
docker-compose up

# 方式二：直接运行
docker run -v ./feeds:/app/feeds tmwgsicp/ForgeRSS:latest
```

### 方式三：本地运行

```bash
# 克隆项目
git clone https://github.com/tmwgsicp/ForgeRSS.git
cd forgerss

# 安装依赖
pip install -r requirements.txt

# (可选) 抖音视频下载需要 ffmpeg
# Windows: scoop install ffmpeg   或   choco install ffmpeg
# macOS:   brew install ffmpeg
# Linux:   sudo apt install ffmpeg / sudo dnf install ffmpeg
# 验证：    ffmpeg -version

# 运行所有生成器
python scripts/run_all.py

# 运行单个生成器
python scripts/run_single.py anthropic_news --max 20

# 运行 AI 编程工具文档生成器
python scripts/run_single.py cursor_docs --max 100

# 运行社交媒体生成器（需先登录，见下方说明）
python scripts/run_single.py zhihu_hot --max 30
BILIBILI_UP_MID=546195 python scripts/run_single.py bilibili_up --max 10
XHS_USER_ID=664f367c00000000070064da python scripts/run_single.py xiaohongshu_user --max 10
ZSXQ_GROUP_ID=88514182418182 python scripts/run_single.py zsxq_topics --max 20

# 运行巨潮公告（按主题关键词）
CNINFO_KEYWORDS=股权激励 python scripts/run_single.py cninfo_announcements --max 20
```

---

## 抓取策略

### 多引擎抓取

| 方案 | 速度 | 适用场景 | 运行环境 |
|------|------|----------|----------|
| **curl_cffi** | ~5秒 | SSR/静态网站，模拟 Chrome TLS 指纹 | 任意 |
| **Selenium** | ~30秒 | 需要 JS 渲染的网站 | CI/本地 |
| **DrissionPage** | ~30秒 | 政府网站/强反爬网站（瑞数等） | **仅桌面环境** |

系统会自动选择最优方案：先尝试 curl_cffi，失败时降级到 Selenium，最后尝试 DrissionPage。

### 反爬等级 (anti_bot_level)

| 等级 | 说明 | 抓取策略 | 典型场景 |
|------|------|----------|----------|
| `0` | 普通网站 | curl_cffi → Selenium → DrissionPage | Anthropic, OpenAI |
| `1` | 中等反爬 | DrissionPage headless → headed | 部分企业网站 |
| `2` | 强反爬（瑞数等） | DrissionPage headed | 政府网站（NMPA） |
| `3+` | 需要登录态 | DrissionPage + 持久化登录 Profile | 社交媒体（知乎、B 站、小红书、知识星球） |

**说明**：
- **Level 0-2** 由 `smart_fetch` 自动处理
- **Level 3+** 需要各 generator 自行实现登录逻辑（每个平台一个 `scraper.py`，共享 `generators/utils/login_checker.py` 做登录态检测）

---

## 政府网站反爬突破方案

很多政府网站（如 NMPA 国家药监局）使用商用反爬系统（瑞数信息 RuiShu），会拦截所有自动化访问（HTTP 412）。本项目提供了专门的解决方案。

### 支持绕过的反爬系统

- **瑞数信息 (RuiShu)** — 国内政府网站常用
- **其他 JS 挑战类反爬** — 需要执行 JS 后才能访问的网站

### 技术原理

| 工具 | Headless 模式 | 非 Headless 模式 |
|------|--------------|------------------|
| Selenium | 被拦截 | 被拦截 |
| Playwright | 被拦截 | 被拦截 |
| **DrissionPage** | 被拦截 | **可以绕过** |

DrissionPage 使用 CDP 协议直接控制 Chrome，伪装更彻底，配合以下措施可绕过瑞数：
1. **非 Headless 模式** — 必须有真实显示器或虚拟显示
2. **干净的浏览器 Profile** — 每次请求使用新的临时 Profile
3. **反检测 JS 注入** — 隐藏 `navigator.webdriver` 等特征

### 运行环境要求

由于必须使用非 Headless 模式，政府网站抓取**无法在 GitHub Actions 等 CI 环境运行**。

| 环境 | 是否支持 | 说明 |
|------|---------|------|
| Windows 桌面 | 支持 | 推荐，直接运行 |
| Windows Server + RDP | 支持 | 需保持桌面会话 |
| Linux + 桌面环境 | 支持 | GNOME/KDE + VNC |
| Linux + Xvfb | 可能不支持 | 虚拟显示可能被检测 |
| Docker / CI | 不支持 | 无真实显示器 |

### 使用方式

```bash
# 运行 NMPA 药品公告抓取（需桌面环境）
python scripts/run_single.py nmpa_drug --max 30

# 或直接调用，支持翻页
python generators/medical/nmpa_drug.py --max 30 --pages 2 --full
```

### 定时运行建议

1. **Windows 任务计划程序** — 每天定时运行，生成后推送到 GitHub
2. **本地 cron** — Linux 桌面环境下配置定时任务
3. **手动运行** — 需要更新时手动执行

```bash
# 运行后推送到 GitHub
python scripts/run_single.py nmpa_drug --max 50
git add feeds/ cache/
git commit -m "chore: update NMPA feed"
git push
```

### 添加新的政府网站源

```python
from generators.base import Article, BaseFeedGenerator
from generators.utils import smart_fetch

class MyGovGenerator(BaseFeedGenerator):
    FEED_NAME = "my_gov"
    FEED_TITLE = "某政府网站"
    FEED_URL = "https://www.example.gov.cn/news/"
    
    # 设置反爬等级为 2（强反爬）
    ANTI_BOT_LEVEL = 2
    CONTENT_CHECK = "/news/"  # 验证抓取成功的字符串
    
    def fetch_articles(self) -> list[Article]:
        html = smart_fetch(
            self.FEED_URL,
            anti_bot_level=self.ANTI_BOT_LEVEL,
            content_check=self.CONTENT_CHECK,
            selenium_wait=8,
        )
        # 解析 HTML，返回 Article 列表
        ...
```

---

## 社交媒体订阅（需登录态）

知乎、B 站、小红书、知识星球需要**登录态**才能访问，统一使用 DrissionPage 复用浏览器登录会话。

### 首次设置（登录）

每个平台首次使用时扫码登录一次，Profile 落盘到 `profiles/<platform>/`，之后所有运行自动复用：

```bash
# 知乎
python -m generators.social.zhihu.scraper --login

# B 站
python -m generators.social.bilibili.scraper --login

# 小红书
python -m generators.social.xiaohongshu.scraper --login

# 知识星球
python -m generators.social.zsxq.scraper --login

# 抖音（视频下载需 ffmpeg）
python -m generators.social.douyin.scraper --login

# 快手
python -m generators.social.kuaishou.scraper --login

# 微博
python -m generators.social.weibo.scraper --login
```

> **小宇宙** 无需登录 / 浏览器 / 任何 setup —— curl_cffi 一击就过（吃 Next.js SSR
> 数据），见下方独立章节。
>
> **雪球** 无需登录，DrissionPage headless 模式直接过 Aliyun WAF，**CI 可跑**，
> 见下方独立章节。

### 验证登录态

随时确认 Profile 还有效（包含杀进程后重启验证、关键词命中报告）：

```bash
python tools/test_login_check.py zhihu
python tools/test_login_check.py bilibili
python tools/test_login_check.py xiaohongshu
python tools/test_login_check.py zsxq
```

### 使用方式

```bash
# 知乎热榜（无需额外配置）
python scripts/run_single.py zhihu_hot --max 50

# 知乎用户动态
ZHIHU_USER_ID=excited-vczh python scripts/run_single.py zhihu_user --max 20

# B 站 UP 主视频（多个用逗号分隔）
BILIBILI_UP_MID="546195,12345678" python scripts/run_single.py bilibili_up --max 20

# 小红书用户笔记（接受纯 user_id 或完整主页 URL，URL 形式更稳）
XHS_USER_ID="664f367c00000000070064da" python scripts/run_single.py xiaohongshu_user --max 10
XHS_USER_ID="https://www.xiaohongshu.com/user/profile/664f367c00000000070064da?xsec_token=..." \
  python scripts/run_single.py xiaohongshu_user --max 10

# 知识星球话题（接受纯 group_id 或完整 URL，可下载帖内附件）
ZSXQ_GROUP_ID="88514182418182" ZSXQ_DOWNLOAD_ATTACHMENTS=true \
  python scripts/run_single.py zsxq_topics --max 20

# 抖音用户视频（接受 sec_uid / 完整 URL / 分享短链；下载需 ffmpeg）
DOUYIN_SEC_UID="MS4wLjABAAAAxxxx" python scripts/run_single.py douyin_user --max 10
# 或：DOUYIN_SEC_UID="https://v.douyin.com/<code>/" ...
DOUYIN_SEC_UID="MS4wLjABAAAAxxxx" DOUYIN_DOWNLOAD_VIDEOS=true \
  python scripts/run_single.py douyin_user --max 5

# 快手用户视频（接受用户 id / 完整 URL / 分享短链；单文件 mp4，免 ffmpeg）
KUAISHOU_USER_ID="3xxxxxxxxxxxxxx" python scripts/run_single.py kuaishou_user --max 10
KUAISHOU_USER_ID="https://v.kuaishou.com/<code>/" KUAISHOU_DOWNLOAD_VIDEOS=true \
  python scripts/run_single.py kuaishou_user --max 5

# 微博用户（自动识别纯文字 / 图文 / 纯图 / 视频四种帖型）
WEIBO_USER_ID="1234567890" python scripts/run_single.py weibo_user --max 10
# 或粘贴完整 URL：
WEIBO_USER_ID="https://weibo.com/u/1234567890" python scripts/run_single.py weibo_user --max 10
```

### 内容说明

- **知乎热榜**：包含排名、标题、热度、摘要、封面图
- **知乎用户动态**：包含回答、文章、赞同等活动
- **B 站 UP 主**：视频标题、BV 链接、封面、播放/弹幕/时长，可选下载 mp4
- **小红书用户**：笔记标题、作者、完整 URL（带 xsec_token 防失效），可选下载图片/视频
- **知识星球**：话题文本、作者、发布时间，可选下载帖内 PDF / 音频 / 图片附件（按 `<群名>_<群ID>/<话题>_<topicID>/` 归档）
- **抖音**：自动识别两种贴型 —— **视频帖** `/video/`（标题含 hashtag、作者、真实视频 URL；可选 mp4 下载，通过 CDP 拦截 douyinvod.com CDN 流，video + audio 分两路用 curl_cffi 下载后 ffmpeg 合并，**需本机安装 ffmpeg**）；**图文笔记** `/note/`（自动进详情页拉取全部画廊图片 + 文案 + 发布时间塞进 RSS；可选 `DOUYIN_DOWNLOAD_IMAGES=true` 落盘到 `downloads/douyin/<sec_uid>/notes/<note_id>/`）
- **快手**：视频标题、作者、`/short-video/<id>` 真实链接；可选 mp4 下载——CDP 拦截 djvod.ndcimgs.com，**单文件 mp4 免 ffmpeg**
- **微博**：标题（前 50 字正文 / 「N 张图片」/「视频」自适应）、作者、`weibo.com/<uid>/<bid>` 链接；图文帖自动嵌入图片（最多 9 张，自动升级到 /large/）；可选 `WEIBO_DOWNLOAD_VIDEOS=true` 下载视频帖的 mp4

### 法律风险提示

⚠️ **重要提醒**：
- 上述平台均明确禁止爬取，知乎已有相关法律判例（2025 年判刑 3 年）
- 本功能**仅供个人学习研究**，用户自用自担风险
- **禁止商业化使用**，禁止转卖数据
- 建议低频使用（每日 1–4 次为宜），避免触发风控

---

## 巨潮资讯（公司公告）

支持三种订阅模式（详见 [`generators/finance/README.md`](generators/finance/README.md)）：

```bash
# 1) 按主题关键词（推荐）：股权激励、回购、业绩快报等
CNINFO_KEYWORDS="股权激励,业绩快报" python scripts/run_single.py cninfo_announcements

# 2) 按分类：全市场年报、半年报、季报等
CNINFO_CATEGORY=category_ndbg_szsh python scripts/run_single.py cninfo_announcements

# 3) 默认：按市场拉最新（sze + sse）
python scripts/run_single.py cninfo_announcements

# 同时下载 PDF（默认 true）
CNINFO_DOWNLOAD_PDF=true python scripts/run_single.py cninfo_announcements
```

PDF 自动归档到 `downloads/cninfo_pdfs/<公司名>_<股票代码>/<标题>.pdf`。

---

## 雪球用户动态订阅（**无需登录 / 无需浏览器登录**）

雪球用户主页走的是阿里云 WAF，不能直接 curl 抓。用 DrissionPage **headless** 模式启动一次真实 Chrome 进程过 WAF 拿到 HTML，再解析时间线。整个流程不需要登录态、不需要 cookie、不依赖 Display，**CI 可跑**。

```bash
# 订阅一个用户，自动追新（接受 uid / 完整 URL）
XUEQIU_USER_ID="8353550788" python scripts/run_single.py xueqiu_user --max 20
XUEQIU_USER_ID="https://xueqiu.com/u/8353550788" python scripts/run_single.py xueqiu_user --max 20

# 多账号合并到同一 Feed（逗号分隔）
XUEQIU_USER_ID="8353550788,1247347556" python scripts/run_single.py xueqiu_user --max 20
```

每条 RSS item 自适应两种帖型：

- **长文型**（机构号常见）：列表只给摘要，自动追抓详情页拿完整正文 + 标题；保留页内股票链接 `$股票名(代码)$` 等富文本
- **回复型**（个人 V 常见）：直接使用列表 DOM（已含完整对话上下文），**不**追抓详情页（详情页只剩自己说的话，反而丢失被回复人原帖上下文）；嵌套引用的他人帖子保留作者 + 时间 + 计数 + 跳转链接，不再递归

### 局限

- 仅抓主页第一屏（约 20 条），不翻页 — 对「追新」场景够用，对历史回溯不够
- 付费内容 / 仅好友可见 — 抓不到（需登录态）
- "关注的博主回复在最上方"这种登录后个性化排序拿不到 — RSS 按时间倒序天然合理

---

## 小宇宙播客订阅（**无需登录 / 无需浏览器**）

小宇宙 web 是 Next.js SSG，节目页 HTML 已经包含最近 15 集的完整元数据（标题/封面/简介/音频 URL）。整个抓取流程是纯 curl_cffi + JSON 解析，**0 资源占用，CI 可跑**。

```bash
# 订阅一个节目，自动追新
XIAOYUZHOU_PODCAST_ID="63b7c6697dcc05cd33b51cd5" \
  python scripts/run_single.py xiaoyuzhou --max 10

# 也可以直接粘贴节目主页 URL
XIAOYUZHOU_PODCAST_ID="https://www.xiaoyuzhoufm.com/podcast/63b7c6697dcc05cd33b51cd5" \
  python scripts/run_single.py xiaoyuzhou --max 10

# 可选：下载每集 mp3 到本地（默认 false）
XIAOYUZHOU_PODCAST_ID="<id>" XIAOYUZHOU_DOWNLOAD_AUDIO=true \
  python scripts/run_single.py xiaoyuzhou --max 5
```

每条 RSS item 包含：
- 节目品牌色 header strip + 主播列表
- Episode 封面 + 时长 + shownotes 全文
- HTML5 `<audio controls>` 内嵌播放器（多数 RSS 阅读器原生支持）
- 标准 `<enclosure>` 音频附件协议
- 节目简介 footer + 订阅数 + 总集数

### ⚠️ 局限：付费节目

当前实现为**无登录**模式，意味着：

| 节目类型 | 支持情况 |
|---|---|
| 完全免费节目 | ✅ 完整支持，所有集都能抓 + 下载 |
| 付费节目的试听集（`PREVIEW`） | ✅ 试听段能抓到 |
| 付费节目的已购集（`PAID` + 你已购买） | ⚠️ 当前**无法访问**，audio URL 会被服务端屏蔽 |
| 付费节目的未购集 | ❌ 注定无法访问 |

如果需要订阅付费节目，需要扩展为「DrissionPage + 登录态」模式（跟知乎/B 站等同款方案）。当前版本不支持。

### 仅取最近 15 集

小宇宙节目主页 SSR 数据只塞最近 15 集，更早的需要异步翻页加载。**对「追新」场景够用**（cron 6 小时一次，根本不会遗漏新发布）；**对历史回溯不够**（一次性导出全部历史集需要额外开发）。

---

## 添加新信息源

1. 在 `generators/` 下创建新文件
2. 继承 `BaseFeedGenerator`
3. 实现 `fetch_articles()` 方法
4. 在 `scripts/run_all.py` 注册

### 普通网站示例

```python
from generators.base import Article, BaseFeedGenerator
from generators.utils import smart_fetch

class MyGenerator(BaseFeedGenerator):
    FEED_NAME = "my_source"
    FEED_TITLE = "My Source"
    FEED_URL = "https://example.com/blog"
    FEED_DESCRIPTION = "Example blog feed"
    
    # curl_cffi 能抓到设为 False，需要 JS 渲染设为 True
    REQUIRE_JS = False
    CONTENT_CHECK = "/blog/"  # 验证抓取成功的字符串
    
    def fetch_articles(self) -> list[Article]:
        html = smart_fetch(self.FEED_URL, require_js=self.REQUIRE_JS)
        # 解析 HTML，返回 Article 列表
        ...
```

### 政府/强反爬网站示例

```python
class MyGovGenerator(BaseFeedGenerator):
    FEED_NAME = "my_gov"
    FEED_TITLE = "某政府网站"
    FEED_URL = "https://www.example.gov.cn/news/"
    
    ANTI_BOT_LEVEL = 2  # 强反爬
    CONTENT_CHECK = "/news/"
    
    def fetch_articles(self) -> list[Article]:
        html = smart_fetch(
            self.FEED_URL,
            anti_bot_level=self.ANTI_BOT_LEVEL,
            content_check=self.CONTENT_CHECK,
        )
        ...
```

---

## 项目结构

```
forgerss/
├── generators/                # Feed 生成器
│   ├── base.py                # 基类（缓存、去重、RSS 生成）
│   ├── utils.py               # HTTP 工具（curl_cffi + Selenium + DrissionPage）
│   ├── http_utils.py          # HTTP 引擎检测与调度
│   ├── rss_streaming.py       # 内存优化的流式 RSS 写入
│   ├── ai/                    # AI 公司信息源
│   │   ├── anthropic_news.py
│   │   ├── anthropic_research.py
│   │   ├── anthropic_engineering.py
│   │   └── openai_research.py
│   ├── ai_coding_docs/        # AI 编程工具文档
│   │   ├── base_docs_crawler.py  # 文档抓取共享基类
│   │   ├── claude_code.py
│   │   ├── cursor_docs.py
│   │   ├── openai_codex.py
│   │   └── qwen_code.py
│   ├── medical/               # 医学/政府信息源
│   │   ├── idsociety.py
│   │   └── nmpa_drug.py       # 国家药监局（需桌面环境）
│   ├── finance/               # 金融/公司公告
│   │   ├── cninfo_announcements.py
│   │   └── xueqiu/            # 雪球用户动态（无需登录）
│   ├── social/                # 社交媒体（每平台一个目录，scraper+generator）
│   │   ├── base/              # 通用下载工具
│   │   ├── zhihu/
│   │   ├── bilibili/
│   │   ├── xiaohongshu/
│   │   ├── zsxq/
│   │   ├── douyin/            # 抖音
│   │   ├── kuaishou/          # 快手
│   │   ├── weibo/             # 微博
│   │   ├── xiaoyuzhou/        # 小宇宙播客（无需登录/浏览器）
│   │   ├── youtube/           # 计划中
│   │   └── tiktok/            # 计划中
│   └── utils/                 # 登录态检测等
│       └── login_checker.py
├── config/                    # 关键词与平台配置 JSON
│   └── login_keywords.json
├── tools/                     # 诊断工具
│   ├── test_login_check.py    # 端到端登录态测试
│   └── diagnose_login.py      # DOM 关键词诊断
├── cache/                     # JSON 缓存
├── feeds/                     # 生成的 RSS 文件
├── data/                      # SQLite 数据库
├── profiles/                  # 浏览器 Profile（gitignored）
├── downloads/                 # 媒体/附件下载（gitignored）
├── scripts/                   # 运行脚本
│   ├── run_all.py
│   ├── run_single.py
│   └── registry.py            # 18 个 generator 共享注册表
├── .github/workflows/         # GitHub Actions（自动跑 + 构建 Docker 镜像与 tar 包）
├── Dockerfile                 # Docker 镜像
└── docker-compose.yml         # Docker Compose
```

---

## 环境变量

复制 `.env.example` 为 `.env`：

```bash
# 日志级别
LOG_LEVEL=INFO

# 每个 Feed 最大文章数
MAX_ARTICLES=50

# 运行间隔（秒），Docker 持久运行模式
RUN_INTERVAL=21600  # 默认 6 小时

# 社交媒体配置
ZHIHU_USER_ID=excited-vczh                          # 知乎用户（逗号分隔多个）
BILIBILI_UP_MID=546195                              # B 站 UP 主（逗号分隔多个）
XHS_USER_ID=664f367c00000000070064da                # 小红书用户（也可以是完整 URL；逗号分隔多个）
ZSXQ_GROUP_ID=88514182418182                        # 知识星球群组（也可以是完整 URL；逗号分隔多个）
DOUYIN_SEC_UID=MS4wLjABAAAAxxxx                     # 抖音用户（也可以是完整 URL / 分享短链；逗号分隔多个）
KUAISHOU_USER_ID=3xxxxxxxxxxxxxx                    # 快手用户（也可以是完整 URL / 分享短链；逗号分隔多个）
WEIBO_USER_ID=1234567890                            # 微博用户（也可以是完整 URL；逗号分隔多个）
XIAOYUZHOU_PODCAST_ID=63b7c6697dcc05cd33b51cd5      # 小宇宙节目（也可以是完整 URL；逗号分隔多个）
XUEQIU_USER_ID=8353550788                           # 雪球用户（也可以是完整 URL；逗号分隔多个）

# 可选下载（默认 false）
BILIBILI_DOWNLOAD_VIDEOS=true                       # B 站视频下载
XHS_DOWNLOAD_MEDIA=true                             # 小红书媒体
ZSXQ_DOWNLOAD_ATTACHMENTS=true                      # 知识星球附件（PDF/音频/图片）
DOUYIN_DOWNLOAD_VIDEOS=true                         # 抖音视频下载（需 ffmpeg）
DOUYIN_DOWNLOAD_IMAGES=true                         # 抖音图文笔记图片下载（不需 ffmpeg）
KUAISHOU_DOWNLOAD_VIDEOS=true                       # 快手视频下载（单文件，免 ffmpeg）
WEIBO_DOWNLOAD_VIDEOS=true                          # 微博视频帖下载
XIAOYUZHOU_DOWNLOAD_AUDIO=true                      # 小宇宙音频下载（mp3）

# 巨潮资讯（三选一）
CNINFO_KEYWORDS="股权激励,业绩快报"                  # 按主题关键词
# CNINFO_CATEGORY=category_ndbg_szsh                # 或按分类（全市场年报等）
# 留空 = 按市场拉最新
CNINFO_DOWNLOAD_PDF=true                            # PDF 自动下载（默认 true）
```

### GitHub Actions 配置

通过 Repository Variables 可自定义：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MAX_ARTICLES` | 每个 Feed 最大文章数 | 50 |
| `LOG_LEVEL` | 日志级别 | INFO |

> 运行频率默认每 6 小时一次，如需调整可 Fork 后修改 `.github/workflows/generate_feeds.yml` 中的 cron 表达式

---

## 开源协议

本项目采用 **AGPL 3.0** 协议开源，**所有功能代码完整公开，私有化部署完全免费**。

| 使用场景 | 是否允许 |
|---------|---------|
| 个人学习和研究 | 允许，免费使用 |
| 企业内部使用 | 允许，免费使用 |
| 私有化部署 | 允许，免费使用 |
| 修改后对外提供网络服务 | 需开源修改后的代码 |

详见 [LICENSE](LICENSE) 文件。

### 免责声明

- 本软件按"原样"提供，不提供任何形式的担保
- 本项目仅供学习和研究目的，请遵守相关网站的服务条款
- 使用者对自己的操作承担全部责任
- 因使用本软件导致的任何损失，开发者不承担责任

---

## 参与贡献

由于个人精力有限，暂不接受代码合并请求，但非常欢迎：

- **提交 Issue** — 报告 Bug、提出功能建议、贡献新的信息源配置
- **Fork 项目** — 自由修改和定制
- **Star 支持** — 给项目点 Star，让更多人看到

---

## 联系方式

<table>
  <tr>
    <td align="center">
      <img src="assets/qrcode/wechat.jpg" width="200"><br>
      <b>个人微信</b><br>
      <em>技术交流 / 商务合作</em>
    </td>
    <td align="center">
      <img src="assets/qrcode/sponsor.jpg" width="200"><br>
      <b>赞赏支持</b><br>
      <em>开源不易，感谢支持</em>
    </td>
  </tr>
</table>

- **GitHub Issues**: [提交问题](https://github.com/tmwgsicp/ForgeRSS/issues)
- **邮箱**: creator@waytomaster.com

---

## 致谢

- [curl_cffi](https://github.com/lexiforest/curl_cffi) — 支持浏览器 TLS 指纹模拟的 HTTP 客户端
- [Selenium](https://www.selenium.dev/) — 浏览器自动化框架
- [DrissionPage](https://github.com/g1879/DrissionPage) — 强大的网页自动化工具，支持绕过多种反爬
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) — HTML 解析库
- [jsDelivr](https://www.jsdelivr.com/) — 免费 CDN 服务

---

<div align="center">

**如果觉得项目有用，请给个 Star 支持一下！**

[![Star History Chart](https://api.star-history.com/svg?repos=tmwgsicp/ForgeRSS&type=Date)](https://star-history.com/#tmwgsicp/ForgeRSS&Date)

Made with love by [tmwgsicp](https://github.com/tmwgsicp)

</div>
