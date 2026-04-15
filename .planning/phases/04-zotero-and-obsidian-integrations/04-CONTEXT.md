# Phase 4: Zotero and Obsidian Integrations - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

自动归档高相关论文到 Zotero（含元数据、AI 标签、分析笔记、PDF 附件），并生成 Obsidian 知识库（每日摘要 + 论文卡片 + backlinks）。两个集成完全可选，未配置时管线正常运行。

ZTR-01~05：Zotero 归档（元数据、AI 标签、笔记、PDF、去重）
OBS-01~04：Obsidian 知识库（论文卡片、每日摘要、backlinks、Git 推送）

不涉及：新搜索源、新分析能力、交互式飞书卡片按钮、新通知渠道。

</domain>

<decisions>
## Implementation Decisions

### Zotero 归档策略
- **归档范围**：仅 HIGH 论文（≥7 分），与深度分析触发条件一致
- **集合结构**：`DailyPapers` 根集合 → 每个 research topic 一个子集合（如 "LLM Reasoning", "Environmental CS"）
- **元数据映射**：title → title, authors → creators, doi → DOI, abstract → abstractNote, published_date → date, source_url → url
- **AI 标签**：AnalysisResult.extracted_keywords 直接作为 Zotero item Tags
- **AI 分析笔记**：单条 Zotero note，结构化包含 summary + key_contributions + methodology_evaluation + limitations + future_directions
- **PDF 附件**：如果论文有 pdf_url 且已下载，附加到 Zotero item
- **去重机制（ZTR-05）**：用 DOI 查询已有 items，DOI 缺失时用 title 模糊匹配。已存在则跳过创建（不更新）
- **认证**：ZOTERO_USER_ID + ZOTERO_API_KEY 环境变量，使用 pyzotero 库

### Obsidian 知识库结构
- **双层级文件**：
  - `daily/YYYY-MM-DD-daily-summary.md` — 每日摘要，包含当日所有论文的简要列表和 [[wiki-link]] 到论文卡片
  - `papers/{doi-or-hash}.md` — 论文卡片，固定模板结构
- **论文卡片固定模板**：
  ```markdown
  ---
  title: "论文标题"
  authors: [作者列表]
  doi: "10.xxx"
  score: 8
  date: 2026-04-15
  topics: [研究主题]
  keywords: [AI 提取关键词]
  source: arxiv
  ---

  ## Summary
  {summary}

  ## Key Contributions
  {key_contributions}

  ## Methodology
  {methodology_evaluation}

  ## Limitations
  {limitations}

  ## Future Directions
  {future_directions}

  ## Related Papers
  {backlinks}
  ```
- **Backlinks（OBS-03）**：同主题的论文互相 `[[wiki-link]]` 链接，形成主题知识图谱。加上 `[[topic-name]]` 链接到主题标签页
- **去重**：用 DOI 或 dedup_key 作为文件名键，已有卡片则更新内容而非创建新文件
- **语言**：中文分析内容（复用现有 language 配置），学术术语保留英文

### Obsidian Git 推送
- **认证**：HTTPS + GitHub Personal Access Token (PAT)，通过 `OBSIDIAN_VAULT_PAT` 环境变量配置
- **仓库 URL**：通过 `obsidian.vault_repo_url` 配置（如 `https://github.com/user/literature-vault.git`）
- **分支**：直接推送到 main 分支
- **推送时机**：每次 pipeline 运行后自动 commit + push
- **冲突处理**：失败时 pull --rebase 后重试一次，再失败则日志记录跳过
- **commit message**：`docs(daily): {date} — {N} papers archived`
- **本地目录**：在 state_dir 下创建临时目录 clone + 生成 + push

### 集成顺序和容错
- **执行位置**：Step 11 (Zotero), Step 12 (Obsidian) — 在 Step 10 飞书通知之后
- **顺序执行**：先 Zotero 归档，再 Obsidian 推送
- **独立容错**：每个集成用 try/except 包裹，一个失败不影响另一个，也不影响已发送的通知
- **处理范围**：仅当次运行中新产生的 HIGH 论文
- **完全可选**：未配置 Zotero/Obsidian 时，Step 11/12 跳过，管线正常结束

### 配置设计
- `config.yaml` 顶级块，各自有 `enabled` 开关：
  ```yaml
  zotero:
    enabled: false
    user_id_env: "ZOTERO_USER_ID"
    api_key_env: "ZOTERO_API_KEY"
    collection_root: "DailyPapers"

  obsidian:
    enabled: false
    vault_repo_url: ""  # Git HTTPS URL
    vault_pat_env: "OBSIDIAN_VAULT_PAT"
  ```

### Claude's Discretion
- Zotero note 的具体 HTML 格式（Zotero 用 HTML 格式的 note）
- Obsidian 卡片模板的具体 markdown 格式细节
- 每日摘要的内容组织方式
- Git clone/push 的具体命令和临时目录管理
- Zotero API 调用的重试逻辑和 rate limiting
- PDF 附件的上传方式（link vs file upload）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — 项目愿景、约束、设计原则
- `.planning/REQUIREMENTS.md` — 需求列表（Phase 4 涉及 ZTR-01~05, OBS-01~04）
- `.planning/ROADMAP.md` — Phase 4 定义和成功标准
- `.planning/STATE.md` — 当前状态

### Existing Code to Build On
- `src/search/models.py` — AnalysisResult（含所有分析字段）、AnalyzedPaper、Paper 模型
- `src/config/models.py` — 配置模型（需添加 ZoteroConfig、ObsidianConfig）
- `src/main.py` — 管线编排（需在 Step 10 后添加 Step 11/12）
- `src/delivery/base.py` — Notifier ABC（可参考创建集成基类）

### Reference Code
- `paperRead/paperRead-main/zotero_indexer.py` — pyzotero 使用模式（集合创建/查找、item 操作、retry_sync）
- `paperRead/paperRead-main/main.py` — 管线编排参考

### Prior Phase Context
- `.planning/phases/01-end-to-end-pipeline-proof/01-CONTEXT.md` — Phase 1 分析管线和配置决策
- `.planning/phases/02-multi-source-search/02-CONTEXT.md` — Phase 2 多源搜索决策
- `.planning/phases/03-advanced-ai-analysis/03-CONTEXT.md` — Phase 3 分析扩展决策

### Research
- `.planning/research/STACK.md` — 技术栈选型
- `.planning/research/ARCHITECTURE.md` — 管线架构设计

</canonical_refs>

<code_context>
## Existing Code Insights

### Architecture (established in Phase 1-3)
- **Pipeline** (`main.py`): 10 步流程，通知在 Step 10。集成应在 Step 11/12。
- **AnalysisResult** (`models.py`): 已包含 summary, key_contributions, methodology_evaluation, limitations, future_directions, comparative_analysis, extracted_keywords
- **Paper model**: paper_id, title, abstract, authors, doi, source, source_url, pdf_url, published_date, full_text
- **Config** (`config/models.py`): Pydantic BaseModel，field_validator，环境变量引用模式（`xxx_env` 字段）

### Key Integration Points
- `main.py` Step 10 之后 → 插入 Zotero 归档 (Step 11) 和 Obsidian 推送 (Step 12)
- `config/models.py:AppConfig` → 添加 `zotero: Optional[ZoteroConfig]` 和 `obsidian: Optional[ObsidianConfig]`
- `src/search/models.py:AnalyzedPaper` → Zotero/Obsidian 消费此模型的数据
- 新建 `src/integrations/zotero.py` 和 `src/integrations/obsidian.py`（或 `src/delivery/zotero.py` 和 `src/delivery/obsidian.py`）

### Reference: Zotero patterns from paperRead
- pyzotero 库：`zotero.Zotero(user_id, 'user', api_key)`
- 集合操作：`zot.collections()`, `zot.create_collections()`, `zot.collection_items()`
- Item 操作：`zot.create_items()`, item children for notes
- 重试模式：`retry_sync(operation, name, retries=3)`
- 去重：通过 collection_items() 遍历已有 titles

### Patterns to Follow
- 配置用 Pydantic BaseModel + 环境变量引用
- 异步操作用 httpx（Zotero API 可用 pyzotero 同步库或 httpx 直接调用）
- 独立 try/except 容错，日志记录
- 每个集成模块独立，不互相依赖

</code_context>

<specifics>
## Specific Ideas

- "DailyPapers" 根集合名可配置（默认 DailyPapers）
- Obsidian 每日摘要开头显示统计：今日新论文总数、各等级数量、归档到 Zotero 数量
- Zotero note 用 HTML 格式（pyzotero 要求 HTML）
- Obsidian 卡片文件名用 DOI（如有）或 dedup_key，避免特殊字符问题
- PAT 存 GitHub Secrets，pipeline 自动读取
- 需要验证 Phase 2 搜索源对环境科学领域的覆盖效果

</specifics>

<deferred>
## Deferred Ideas

- 飞书交互式卡片按钮（"加入 Zotero"/"感兴趣"）— 需要飞书 app 注册，v2
- 用户确认机制（Phase 3 预留了 confirmed 字段）— v2
- Embedding 语义相似度匹配替代关键词重叠 — v2
- Zotero collection 按日期二级组织 — 未来可选
- Obsidian 跨主题关键词自动链接 — 未来可选
- Email 通知渠道 — v2

---

*Phase: 04-zotero-and-obsidian-integrations*
*Context gathered: 2026-04-15*
