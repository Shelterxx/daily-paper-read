# Phase 1: End-to-End Pipeline Proof - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

搭建完整管线骨架：YAML配置 → arXiv搜索（含PDF下载+全文提取）→ AI评分/摘要 → 飞书推送 → GitHub Actions工作流 + 状态管理 + 去重。用户fork后配置YAML和Secrets，10分钟内能跑通并收到第一条推送。

注意：Phase 1 包含 arXiv PDF 下载和全文提取（因为 arXiv PDF 直接可用），这比原 ROADMAP 中 Phase 2 的范围略大，但仅限于 arXiv 源。Phase 2 再扩展到其他源的 PDF 获取。

</domain>

<decisions>
## Implementation Decisions

### YAML 配置结构
- 采用**研究主题式**组织：每个主题包含关键词、描述、数据源、阈值等
- 全局配置最小化：只有通知设置、API密钥引用等全局项
- 主题为主，全局最小：所有搜索相关配置都在每个主题里
- 固定结构，用 pydantic 严格验证（不允许自定义字段）
- 搜索时间范围可配置（默认24小时）
- 软上限 + 记录全部：推送 Top N（可配置），但所有搜索结果保存到 state/ 目录
- 语言偏好可配置（中文/英文/混合）

### 飞书推送格式
- **单卡片 + 主题分区**：一条消息内按研究主题分区块展示
- **分级展示信息密度**：
  - 高相关：详细卡片（完整摘要、评分、关键贡献、应用场景）
  - 中相关：紧凑信息（评分 + 一句话总结 + 核心贡献）
  - 低相关：标题 + 链接 + 评分
- 卡片开头显示统计摘要：今日新论文总数、各等级数量
- 推送语言可通过配置选择（中文/英文/混合）

### AI 分析输出风格
- **分级自适应输出**：
  - 高相关（7-10分）：评分 + 总结 + 核心贡献（3条）+ 潜在应用场景
  - 中相关（4-6分）：评分 + 总结 + 核心贡献
  - 低相关（1-3分）：仅标题 + 链接 + 评分
- **模型策略**：Haiku 快速批量评分筛选 → Sonnet 逐篇深度分析（高相关的）
- **调用策略**：先批量评分筛选（一次 API 调用处理多篇），再逐篇深度分析（高相关的）
- **评分粒度**：10分制整数，阈值可配置（默认高>=7，中>=4）
- **分析基础**：基于 arXiv PDF 全文（下载+PyMuPDF提取），摘要作为 fallback
- **多模型支持**：用 OpenAI 兼容接口（openai SDK + 自定义 base_url），支持 Claude、GLM、DeepSeek、MiniMax 等
- 提取的关键词在推送消息和 Actions 日志中展示

### 搜索查询设计
- 用户用自然语言描述研究方向（如 "研究大语言模型的推理能力"）
- 系统用 LLM 自动从描述中提取搜索关键词
- 用户可以在 YAML 中手动添加 `keywords` 字段覆盖自动提取
- 逻辑：有 keywords → 直接用；没有 → 从 description 自动提取
- 提取的关键词展示给用户（推送消息中 + Actions 日志）
- 参考 literature-search 的 `adaptive_search_planner.py` 模式

### Claude's Discretion
- Python 项目结构（目录布局、模块划分）
- arXiv API 集成的具体实现
- PyMuPDF 文本提取的实现细节
- Jinja2 模板的具体设计
- GitHub Actions workflow YAML 的具体配置
- 状态文件（state/）的格式和存储策略
- 重试逻辑和错误处理的具体策略

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — 项目愿景、约束、设计原则
- `.planning/REQUIREMENTS.md` — Phase 1 需求列表（CONF-01到05, SRCH-01/06-08, FETH-05, ANLY-01/02/05, NTFY-01到03, PIPE-01到04, ZTR-06, OBS-05）
- `.planning/ROADMAP.md` — Phase 1 定义和成功标准
- `.planning/STATE.md` — 当前状态

### Research
- `.planning/research/STACK.md` — 技术栈选型（Python 3.10+, httpx, pydantic-settings, openai SDK等）
- `.planning/research/ARCHITECTURE.md` — 管线架构设计、目录结构、数据流
- `.planning/research/PITFALLS.md` — 陷阱预防（API限速、去重、成本控制等）

### Reference Code (existing tools to learn from)
- `literature-search/scripts/literature_search/` — 搜索管线架构、多API并行、数据模型
- `literature-search/scripts/literature_search/components/adaptive_search_planner.py` — 自然语言→关键词提取模式
- `literature-search/scripts/literature_search/data/models.py` — StructuredMetadata 数据模型参考
- `paperRead/paperRead-main/main.py` — arXiv管线完整实现、状态追踪、两阶段LLM分析
- `paperRead/paperRead-main/notifier.py` — FeishuNotifier 飞书通知实现
- `paperRead/paperRead-main/zotero_indexer.py` — Zotero 集成参考（Phase 4 用）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **paperRead/notifier.py 的 FeishuNotifier**: 飞书富文本格式化逻辑可直接参考，包括消息卡片结构和发送方式
- **paperRead/main.py 的两阶段LLM分析**: 第一阶段廉价筛选 + 第二阶段深度对比的模式值得复用
- **paperRead/main.py 的增量状态追踪**: date cursor + history set 的去重模式
- **paperRead/main.py 的 retry_sync()**: 带指数退避的重试逻辑
- **literature-search 的 StructuredMetadata**: 统一论文数据模型的设计参考
- **literature-search 的 api_client.py**: 多API并行搜索的 ThreadPoolExecutor 模式

### Established Patterns
- 所有三个参考项目都用 `.env` / 环境变量管理密钥
- paperRead 用 openai SDK + 自定义 base_url 实现多模型支持
- literature-search 用 LLM (litellm) 做相关性筛选和查询扩展

### Integration Points
- 本 Phase 是 greenfield 项目，无现有集成点
- 需要创建完整的项目结构（src/, templates/, .github/ 等）

</code_context>

<specifics>
## Specific Ideas

- "用户应该能写自然语言描述研究方向，系统自动提取关键词" — 参考 literature-search 的 adaptive_search_planner
- "提取的关键词要展示给用户" — 在推送消息开头和 Actions 日志中显示
- "加入人在回路" — 用户可以在 YAML 中覆盖自动提取的关键词
- "多模型支持" — 用 OpenAI 兼容接口，支持 Claude、GLM、DeepSeek、MiniMax 等
- "软上限 + 记录全部" — 推送 Top N 但保存所有结果
- Phase 1 就要包含 arXiv PDF 下载 + 全文提取（不限于摘要）

</specifics>

<deferred>
## Deferred Ideas

- 飞书交互式卡片按钮（"感兴趣"/"加入Zotero"）— Phase 4 或新 Phase
- 基于用户偏好的相关推荐算法 — 可能的 Phase 5
- Email 通知渠道 — v2（已确认不在 Phase 1）
- PubMed/OpenAlex/Semantic Scholar/DOI 搜索源 — Phase 2
- 非 arXiv 源的 PDF 获取 — Phase 2
- 深度方法论分析 + 对比分析 — Phase 3
- Zotero 归档 — Phase 4
- Obsidian 知识库 — Phase 4

</deferred>

---

*Phase: 01-end-to-end-pipeline-proof*
*Context gathered: 2026-04-13*
