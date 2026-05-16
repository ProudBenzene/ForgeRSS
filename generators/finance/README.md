# 财经数据 RSS 生成器

## 巨潮资讯网公告订阅

### 三种订阅方式

#### 1) 按主题关键词（推荐）

适合订阅「事件类公告」：股权激励、业绩快报、回购等。

```bash
# 单个主题
CNINFO_KEYWORDS="股权激励" python scripts/run_single.py cninfo_announcements

# 多主题
CNINFO_KEYWORDS="股权激励,业绩快报,回购" python scripts/run_single.py cninfo_announcements
```

#### 2) 按分类

适合订阅「特定类型公告」：年报、半年报、季报等。

```bash
# 全市场年报
CNINFO_CATEGORY=category_ndbg_szsh python scripts/run_single.py cninfo_announcements

# 业绩快报
CNINFO_CATEGORY=category_yjkb_szsh python scripts/run_single.py cninfo_announcements
```

常用分类代码：

| 代码 | 含义 |
|---|---|
| `category_ndbg_szsh` | 年度报告 |
| `category_bndbg_szsh` | 半年度报告 |
| `category_yjdbg_szsh` | 一季度报告 |
| `category_sjdbg_szsh` | 三季度报告 |
| `category_yjkb_szsh` | 业绩快报 |
| `category_yjygjxz_szsh` | 业绩预告 |
| `category_gqjl_szsh` | 股权激励 |
| `category_zj_szsh` | 增减持 |
| `category_dshgg_szsh` | 董事会公告 |
| `category_gddh_szsh` | 股东大会 |

#### 3) 按市场（默认）

不配置任何关键词/分类时，按市场拉最新公告。

```bash
# 沪深两市最新（默认）
python scripts/run_single.py cninfo_announcements

# 只看深市
CNINFO_MARKETS=szse python scripts/run_single.py cninfo_announcements
```

### 命令行参数

```bash
python -m generators.finance.cninfo_announcements \
  --keywords "股权激励" \         # 主题关键词
  --category "" \                  # 分类（可选）
  --markets "szse,sse" \           # 市场
  --days 7 \                       # 最近 N 天
  --max 30 \                       # 最多获取多少条
  --download-pdf                   # 同时下载 PDF
```

### 输出位置

- **RSS Feed**：`feeds/feed_cninfo_announcements.xml`
- **PDF 文件**：`downloads/cninfo_pdfs/<公司名>_<股票代码>/<标题>.pdf`

### 频率建议

- 个人使用：6 小时更新一次
- 请求间隔：默认 2 秒（`CNINFO_REQUEST_INTERVAL`）
- 默认获取最近 7 天

### 风险提示

⚠️ 仅供个人学习使用，不得用于商业目的。建议控制请求频率，避免被封 IP。
