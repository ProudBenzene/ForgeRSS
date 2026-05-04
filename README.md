<div align="center">

# ForgeRSS

### 将任意网站转换为 RSS 订阅源

**完全开源 | 免费使用 | 自动更新 | 双引擎抓取 | Docker 支持**

[![GitHub stars](https://img.shields.io/github/stars/tmwgsicp/ForgeRSS?style=for-the-badge&logo=github)](https://github.com/tmwgsicp/ForgeRSS/stargazers)
[![License](https://img.shields.io/badge/License-AGPL%203.0-blue?style=for-the-badge)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/tmwgsicp/ForgeRSS?style=for-the-badge&logo=docker&logoColor=white)](https://hub.docker.com/r/tmwgsicp/ForgeRSS)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)

> **100% 开源，100% 免费。** 代码完全公开，私有化部署无任何限制，不搞"开源"之名行收费之实。

</div>

---

## 功能特性

- **双引擎抓取** — curl_cffi (Chrome TLS 指纹) + Selenium (JS 渲染)，自动选择最优方案
- **智能去重** — 基于 URL 哈希，避免重复文章
- **双存储方案** — JSON 缓存 (GitHub 托管) + SQLite (本地/Docker)
- **标准 RSS 2.0** — RFC 822 时间格式，兼容所有阅读器
- **GitHub Actions** — 每 6 小时自动更新，零运维
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
| **IDSociety Science Speaks** | [订阅](https://cdn.jsdelivr.net/gh/tmwgsicp/ForgeRSS@main/feeds/feed_idsociety.xml) |

> Feed 每 6 小时自动更新，包含完整文章内容。使用 jsDelivr CDN 托管，兼容所有 RSS 阅读器。

### 详细信息源列表

| 信息源 | 分类 | 抓取方式 | Feed 文件 |
|--------|------|----------|-----------|
| Anthropic News | AI | curl_cffi | `feed_anthropic_news.xml` |
| Anthropic Research | AI | curl_cffi | `feed_anthropic_research.xml` |
| Anthropic Engineering | AI | curl_cffi | `feed_anthropic_engineering.xml` |
| OpenAI Research | AI | curl_cffi | `feed_openai_research.xml` |
| IDSociety Science Speaks | 医学 | Selenium | `feed_idsociety.xml` |

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

# 运行所有生成器
python scripts/run_all.py

# 运行单个生成器
python scripts/run_single.py anthropic_news --max 20

# 验证 Feed
python scripts/validate_feeds.py
```

---

## 抓取策略

| 方案 | 速度 | 适用场景 |
|------|------|----------|
| **curl_cffi** | ~5秒 | SSR/静态网站，模拟 Chrome TLS 指纹 |
| **Selenium** | ~30秒 | 需要 JS 渲染的网站 |

系统会自动选择最优方案：先尝试 curl_cffi，失败或内容不完整时自动降级到 Selenium。

---

## 添加新信息源

1. 在 `generators/` 下创建新文件
2. 继承 `BaseFeedGenerator`
3. 实现 `fetch_articles()` 方法
4. 在 `scripts/run_all.py` 注册

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

---

## 项目结构

```
forgerss/
├── generators/           # Feed 生成器
│   ├── base.py          # 基类（缓存、去重、RSS生成）
│   ├── utils.py         # HTTP工具（curl_cffi + Selenium）
│   ├── ai/              # AI 公司信息源
│   │   ├── anthropic_news.py
│   │   ├── anthropic_research.py
│   │   ├── anthropic_engineering.py
│   │   └── openai_research.py
│   └── medical/         # 医学信息源
│       └── idsociety.py
├── cache/               # JSON 缓存
├── feeds/               # 生成的 RSS 文件
├── data/                # SQLite 数据库
├── scripts/             # 运行脚本
├── .github/workflows/   # GitHub Actions
├── Dockerfile           # Docker 镜像
└── docker-compose.yml   # Docker Compose
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
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) — HTML 解析库
- [jsDelivr](https://www.jsdelivr.com/) — 免费 CDN 服务

---

<div align="center">

**如果觉得项目有用，请给个 Star 支持一下！**

[![Star History Chart](https://api.star-history.com/svg?repos=tmwgsicp/ForgeRSS&type=Date)](https://star-history.com/#tmwgsicp/ForgeRSS&Date)

Made with love by [tmwgsicp](https://github.com/tmwgsicp)

</div>
