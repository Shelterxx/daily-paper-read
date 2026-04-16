# 每日文献推送系统

自动化文献搜索、AI 分析、飞书推送管线。每天定时从多个学术数据库搜索相关论文，用大模型评分和深度分析，将高相关论文推送到飞书群，可选归档到 Zotero 和 Obsidian。

## 功能

- **多源搜索**：arXiv、sci_search (Supabase)、OpenAlex、Semantic Scholar
- **AI 四阶段分析**：评分 → 深度分析 → 方法论评估 → 历史对比
- **飞书折叠卡片**：概览信息直接可见，详细分析折叠展开，支持交互按钮
- **交互式感兴趣按钮**（可选）：点击「感兴趣」一键归档到 Zotero
- **Zotero 归档**（可选）：元数据、AI 标签、分析笔记、PDF 附件
- **Obsidian 知识库**（可选）：论文卡片、每日摘要、wiki-link backlinks

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，设置研究主题和搜索源。

### 3. 环境变量

创建 `.env` 文件：

```env
# 必需：LLM API
LLM_API_KEY=your-api-key

# 必需：飞书应用（折叠卡片推送）
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx
FEISHU_CHAT_ID=oc_xxxxx

# 搜索源（可选）
SCI_SEARCH_API_TOKEN=
OPENALEX_EMAIL=          # 加速 OpenAlex 访问
S2_API_KEY=              # Semantic Scholar 提高限额

# 集成（可选）
ZOTERO_USER_ID=
ZOTERO_API_KEY=
OBSIDIAN_VAULT_PAT=

# 飞书交互按钮（可选，需部署回调服务）
FEISHU_VERIFICATION_TOKEN=
FEISHU_ENCRYPT_KEY=
```

### 4. 飞书应用配置

1. 在 [open.feishu.cn](https://open.feishu.cn) 创建企业自建应用
2. 添加「机器人」能力
3. 权限管理中开通「获取与发送单聊、群组消息」（`im:message`）
4. 发布应用（企业内自建应用一般免审核）
5. 将机器人添加到推送群
6. 从群设置中获取 `chat_id`，连同 `App ID`、`App Secret` 填入 `.env`

### 5. 运行

```bash
python -m src.main
```

## 配置说明

```yaml
research_topics:
  - name: "主题名称"
    description: "研究方向的自然语言描述"
    max_push: 5                    # 每次运行推送上限
    relevance_thresholds:
      high: 9                      # ≥9 分为高相关，触发深度分析
      medium: 7                    # ≥7 分为中相关（不推送）

sources:
  arxiv:
    enabled: true
    max_results: 20
  sci_search:
    enabled: true
    max_results: 20
  openalex:
    enabled: true
    max_results: 20
  semantic_scholar:
    enabled: false
    max_results: 20

llm:
  scoring_model: "deepseek-chat"
  analysis_model: "deepseek-chat"
  base_url: "https://api.deepseek.com"
  api_key_env: "LLM_API_KEY"

notification:
  feishu_webhook_env: "FEISHU_WEBHOOK_URL"  # Webhook 备用模式
  language: "zh"                   # zh / en / mixed

# Zotero 归档
zotero:
  enabled: false
  collection_root: "DailyPapers"
  archive_threshold: 9             # 仅归档评分 ≥ 此阈值的论文

obsidian:
  enabled: false
  vault_repo_url: ""

# 飞书应用（推荐，支持折叠面板和交互按钮）
feishu_app:
  enabled: true
  app_id_env: "FEISHU_APP_ID"
  app_secret_env: "FEISHU_APP_SECRET"
  chat_id_env: "FEISHU_CHAT_ID"
  callback_base_url: ""           # 交互按钮回调地址（可选）
```

## 管线流程

```
搜索 → 去重 → DOI 补全 → AI 评分 → PDF 获取
  → 深度分析 → 方法论评估 → 对比分析
  → 飞书推送 → Zotero 归档 → Obsidian 推送
```

| 步骤 | 说明 |
|------|------|
| 1-3 | 加载配置、初始化状态、多源搜索 |
| 4 | 去重 + 过滤已推送论文 |
| 5 | LLM 批量评分（abstract only） |
| 6 | HIGH 论文多通道 PDF 获取 |
| 7 | HIGH 论文深度分析（summary + contributions） |
| 8 | HIGH 论文方法论评估（limitations + future directions） |
| 9 | 9-10 分论文与历史论文对比分析 |
| 10 | 飞书折叠卡片推送 + 保存状态 |
| 11 | Zotero 归档（按 archive_threshold 筛选）或保存论文数据（交互模式） |
| 12 | Obsidian 推送（可选） |

## 飞书卡片布局

通过飞书应用 API 发送，支持折叠面板组件。HIGH 相关论文布局：

**始终可见**：
- 标题 + 相关性评分 + 来源链接
- 作者 + 发表日期
- 短摘要（200 字）
- 核心贡献

**点击展开**：
- 🔧 潜在应用
- 🔬 方法论评估
- ⚠️ 局限性分析
- 🚀 未来研究方向
- 📊 对比分析（9-10 分论文）

**元数据页脚**：DOI 链接、关键词

**操作按钮**：查看论文、PDF 下载、感兴趣（可选）

## 交互式「感兴趣」按钮（可选）

启用后用户可在飞书卡片中点击「感兴趣」一键归档论文到 Zotero，需部署回调服务。

### 部署回调服务器

```bash
uvicorn src.callback_server:app --host 0.0.0.0 --port $PORT
```

| 端点 | 说明 |
|------|------|
| `GET /api/archive` | 处理「感兴趣」按钮点击，归档到 Zotero，返回 HTML 结果页 |
| `POST /feishu/callback` | 飞书卡片回调（需飞书应用注册回调订阅） |
| `GET /health` | 健康检查 |

启用交互按钮后管线行为：
- 仅 `archive_threshold` 以下的论文不自动归档，用户可按需点击归档
- 论文数据保存到 `state/papers_for_callback.json`，供回调服务读取

## 项目结构

```
src/
├── main.py              # 管线编排
├── callback_server.py   # 飞书回调服务器（交互按钮）
├── config/
│   ├── models.py        # Pydantic 配置模型
│   └── loader.py        # YAML 加载器
├── search/
│   ├── models.py        # Paper, AnalysisResult 数据模型
│   ├── base.py          # SearchSource 基类
│   ├── arxiv_source.py  # arXiv 搜索
│   ├── sci_search_source.py  # sci_search 搜索
│   ├── openalex_source.py    # OpenAlex 搜索
│   ├── semantic_scholar_source.py  # Semantic Scholar 搜索
│   ├── doi_resolver.py  # DOI 元数据补全
│   └── dedup.py         # 去重
├── analysis/
│   ├── analyzer.py      # 四阶段 AI 分析
│   ├── prompts.py       # Prompt 模板
│   └── keyword_extractor.py  # LLM 关键词提取
├── fetch/
│   ├── multi_channel_fetcher.py  # 多通道 PDF 获取
│   ├── pdf_fetcher.py
│   └── text_extractor.py
├── delivery/
│   ├── base.py          # Notifier 基类
│   └── feishu.py        # 飞书卡片推送（App API + 折叠面板）
├── integrations/
│   ├── zotero.py        # Zotero 归档（批量 + 单篇按需）
│   └── obsidian.py      # Obsidian 知识库
└── state/
    └── manager.py       # 状态管理 + 历史论文库 + 回调数据持久化
```

## LLM 兼容性

通过 OpenAI-compatible API 支持多种模型：

| 提供商 | base_url | 备注 |
|--------|----------|------|
| DeepSeek | `https://api.deepseek.com` | 默认配置 |
| OpenAI | `https://api.openai.com/v1/` | Claude/Anthropic 也走兼容接口 |
| 本地模型 | `http://localhost:8000/v1/` | Ollama, vLLM 等 |

## 定时运行

GitHub Actions 示例：

```yaml
on:
  schedule:
    - cron: '0 8 * * *'  # 每天 UTC 8:00（北京 16:00）
  workflow_dispatch:
```

或本地 cron：

```bash
# crontab -e
0 8 * * * cd /path/to/project && python -m src.main >> logs/pipeline.log 2>&1
```
