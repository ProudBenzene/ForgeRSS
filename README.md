# ForgeRSS

🔥 **ForgeRSS** - 社交媒体和专业内容的统一RSS生成器

将社交媒体平台（知乎、B站、小红书、知识星球等）和专业内容源转换为标准RSS feeds，让你通过RSS阅读器随时订阅更新。

---

## ✨ 特性

- 🎯 **多平台支持** - 知乎、B站、小红书、知识星球等
- 🔐 **登录态管理** - 自动检测和提醒登录过期
- 📥 **媒体下载** - 可选的视频/图片本地下载
- 🚀 **高性能** - 基于DrissionPage和curl_cffi
- 📝 **RSS 2.0** - 标准RSS格式，兼容所有阅读器
- 🐳 **Docker支持** - 一键部署（开发中）

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# Python 3.10+
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，配置你需要的平台
```

### 3. 登录平台

```bash
# 知乎
python -m generators.social.zhihu.scraper --login

# B站
python -m generators.social.bilibili.scraper --login

# 小红书
python -m generators.social.xiaohongshu.scraper --login

# 知识星球
python -m generators.social.zsxq.scraper --login
```

### 4. 生成RSS

```bash
# 单个平台
python scripts/run_single.py zhihu_hot

# 全部平台
python scripts/run_all.py
```

RSS feed会生成在 `feeds/` 目录。

---

## 📚 支持的平台

### 社交媒体

| 平台 | 状态 | 功能 | 需要登录 |
|------|------|------|---------|
| 知乎热榜 | ✅ | 热门话题 | ✅ |
| 知乎用户 | ✅ | 用户动态 | ✅ |
| B站UP主 | ✅ | 视频动态 + 可选下载 | ✅ |
| 小红书 | ✅ | 用户笔记 + 可选媒体下载 | ✅ |
| 知识星球 | ✅ | 星球话题 + 附件下载（PDF/音频/图片） | ✅ |
| TikTok | 🚧 | 计划中 | - |
| YouTube | 🚧 | 计划中 | - |

### AI 与技术

| 平台 | 状态 | 功能 |
|------|------|------|
| Anthropic | ✅ | 新闻 / 研究 / 工程博客 |
| OpenAI | ✅ | 研究博客 |
| OpenAI Codex Docs | ✅ | 文档更新 |
| Claude Code Docs | ✅ | 文档更新 |
| Cursor Docs | ✅ | 文档更新 |
| Qwen Code Docs | ✅ | 文档更新 |

### 专业内容

| 平台 | 状态 | 功能 |
|------|------|------|
| 巨潮资讯 | ✅ | 公司公告：关键词主题 / 分类 / 全市场最新 + 可选 PDF 下载 |
| NMPA | ✅ | 药品审批 |
| IDSociety | ✅ | 感染病指南 |

---

## 📖 文档

- [配置指南](docs/CONFIGURATION.md) - 详细的环境变量和参数说明
- [登录态管理](docs/LOGIN_STATUS_MANAGEMENT.md) - 登录检测和通知系统
- [知识星球指南](docs/ZSXQ_GUIDE.md) - 知识星球特定配置
- [巨潮资讯订阅](generators/finance/README.md) - 巨潮三种订阅模式

---

## ⚙️ 配置说明

### 必需配置

```bash
# B站UP主（多个用逗号分隔）
BILIBILI_UP_MID=546195,另一个UP主ID

# 小红书用户：纯 user_id 或完整主页 URL 都可以
XHS_USER_ID=664f367c00000000070064da
# XHS_USER_ID=https://www.xiaohongshu.com/user/profile/664f367c00000000070064da?xsec_token=...

# 知识星球：纯 group_id 或完整 URL 都可以（多个用逗号分隔）
ZSXQ_GROUP_ID=88514182418182
# ZSXQ_GROUP_ID=https://wx.zsxq.com/group/88514182418182

# 知乎用户（可选）
ZHIHU_USER_ID=excited-vczh

# 巨潮资讯（三选一，详见 generators/finance/README.md）
# 1) 按主题关键词
CNINFO_KEYWORDS=股权激励,业绩快报
# 2) 按分类
# CNINFO_CATEGORY=category_ndbg_szsh
# 3) 不配 → 按市场（默认 szse,sse）拉最新
```

### 可选功能

```bash
# B站视频下载（默认 false）
BILIBILI_DOWNLOAD_VIDEOS=true

# 小红书媒体下载（默认 false）
XHS_DOWNLOAD_MEDIA=true

# 知识星球附件下载（默认 false；开启后下载帖子内 PDF/音频/图片）
ZSXQ_DOWNLOAD_ATTACHMENTS=true

# 巨潮公告 PDF 下载（默认 true）
CNINFO_DOWNLOAD_PDF=true

# 自定义 Profile 路径
ZHIHU_PROFILE_DIR=/custom/path/zhihu
```

---

## 🔧 高级功能

### 登录态自动检测

系统会自动检测登录态是否过期，并通过日志和文件通知你。详见 [登录态管理文档](docs/LOGIN_STATUS_MANAGEMENT.md)。

### 视频下载

B站和小红书支持自动下载视频到本地：

```bash
# 开启B站视频下载
BILIBILI_DOWNLOAD_VIDEOS=true python scripts/run_single.py bilibili_up

# 下载位置
downloads/bilibili/
downloads/xiaohongshu/
```

**存储空间估算**: 每天抓取20个视频约200MB（B站）+ 50MB（小红书）

---

## 🐳 Docker部署（开发中）

```bash
docker-compose up -d
```

---

## 📊 性能

- 知乎热榜: ~5秒（30个话题）
- B站UP主: ~2分钟（20个视频）
- 小红书: ~10分钟（20个笔记）
- 知识星球: ~30秒（20个话题）

---

## 🛠️ 开发

### 项目结构

```
forgerss/
├── generators/             # 生成器模块
│   ├── social/             # 社交媒体
│   │   ├── zhihu/
│   │   ├── bilibili/
│   │   ├── xiaohongshu/
│   │   ├── zsxq/
│   │   ├── youtube/        # 计划中
│   │   ├── tiktok/         # 计划中
│   │   └── base/           # 通用下载/反风控工具
│   ├── ai/                 # Anthropic / OpenAI
│   ├── ai_coding_docs/     # 编程工具文档（Cursor / Claude Code / ...）
│   ├── finance/            # 巨潮资讯
│   ├── medical/            # 医疗健康
│   └── utils/              # 登录态检测等
├── config/                 # 平台关键词、配置 JSON
├── scripts/                # 入口脚本 + generator 注册表
├── tools/                  # 登录诊断工具
├── feeds/                  # RSS 输出
├── profiles/               # 浏览器 Profile（gitignored）
└── downloads/              # 媒体下载（gitignored）
```

### 添加新平台

1. 在 `generators/social/` 创建平台目录
2. 实现 `scraper.py` （数据抓取）
3. 实现 `generator.py` （RSS生成）
4. 更新 `scripts/run_single.py`

---

## 🤝 贡献

欢迎提交Issue和Pull Request！

---

## 📄 许可

AGPL-3.0 License

---

## ⚠️ 免责声明

本项目仅供学习和个人使用。使用时请遵守各平台的服务条款，不要用于商业用途。频繁抓取可能触发平台的反爬机制，请合理设置抓取频率。

---

## 🙏 致谢

- [DrissionPage](https://github.com/g1879/DrissionPage) - 强大的浏览器自动化
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 视频下载
- [curl_cffi](https://github.com/yifeikong/curl_cffi) - 快速HTTP请求

---

**Made with ❤️ by ForgeRSS Contributors**
