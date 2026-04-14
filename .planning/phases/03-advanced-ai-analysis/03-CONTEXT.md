# Phase 3: Advanced AI Analysis - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

为高相关论文增加深度方法论分析和对比分析能力。在 Phase 1 的两阶段分析（Haiku 评分 + Sonnet 深度分析）基础上，新增 Stage 2b（方法论深度分析）和 Stage 3（对比分析），扩展 AnalysisResult 模型，增强飞书卡片展示，并建立历史论文积累机制供对比使用。

ANLY-03：方法论评估 + 局限性 + 未来研究建议
ANLY-04：与历史运行中的相关论文对比分析

不涉及：新搜索源、Zotero/Obsidian 集成、交互式卡片按钮、新通知渠道。

</domain>

<decisions>
## Implementation Decisions

### 深度分析内容（ANLY-03）
- **全面深度分析**：方法论评估（实验设计合理性、数据集规模、基线对比）+ 局限性分析（明确承认的 + 隐含的）+ 未来研究建议（具体可行动方向）
- **输入**：论文全文（full_text 最多 8000 字符）+ Stage 2a 的 summary/contributions 作为上下文
- **语言**：中文输出 + 学术术语保留英文（如 transformer, fine-tuning），复用现有 language 配置机制
- **触发条件**：所有 HIGH 论文（≥7 分），与现有 Stage 2 相同

### 对比分析策略（ANLY-04）
- **对比来源**：历史运行中的高相关论文（从 state.json 的 analyzed_papers_history 读取），不限于当次运行
- **每篇独立对比**：每篇目标论文单独生成对比段落，列出与 3-5 篇最相关历史论文的异同
- **输入深度**：摘要级对比（title + abstract + summary），每篇约 200-300 token
- **触发条件**：仅评分 9-10 分的论文执行对比分析
- **相关性匹配**：基于 topic keywords 重叠度选取最相关的历史论文，按关键词重叠数降序 + score 降序
- **论文选取**：优先同 topic，取前 3-5 篇

### 分析阶段架构
- **4 阶段流水线**：
  1. Stage 1：Haiku 批量评分（现有，abstract only）
  2. Stage 2a：Sonnet 深度分析（现有，扩展输出 summary + contributions + applications）
  3. Stage 2b：Sonnet 方法论深度分析（新增，输入：full_text + Stage 2a 结果）
  4. Stage 3：Sonnet 对比分析（新增，仅 9-10 分，输入：3-5 篇历史论文摘要）
- **各阶段独立容错**：Stage 2b 失败不影响 2a 结果；Stage 3 失败不影响深度分析。论文展示可用的分析部分
- **对比失败降级**：找不到足够历史论文时跳过对比分析，日志记录警告

### 飞书展示增强
- **追加新区块**：在现有 HIGH tier 展示（authors → summary → contributions → applications）下方追加
- **图标区分**：
  - 🔬 方法论评估
  - ⚠️ 局限性分析
  - 🚀 未来研究方向
  - 📊 对比分析
- **对比展示为精简摘要**：2-3 条核心差异 + "与 X 篇相关论文对比"
- MEDIUM 和 LOW tier 展示不变

### 成本控制
- **记录日志不设硬性上限**：每次运行记录 token 消耗日志，用户可监控
- **成本自然控制**：Stage 2b 只对 HIGH 论文，Stage 3 只对 9-10 分论文

### 数据模型设计
- **扩展现有 AnalysisResult**：直接添加新字段（methodology_evaluation, limitations, future_directions, comparative_analysis），不新建模型类
- **新字段**：
  - `methodology_evaluation: Optional[str]` — 方法论评估
  - `limitations: Optional[list[str]]` — 局限性列表
  - `future_directions: Optional[list[str]]` — 未来研究方向
  - `comparative_analysis: Optional[str]` — 对比分析摘要
  - `compared_with: Optional[list[str]]` — 对比论文的 title 列表（用于展示）

### 历史 State 管理
- **扩展现有 state.json**：增加 `analyzed_papers_history` 字段
- **保留策略**：最近 100 篇高相关论文，自动淘汰最旧的
- **每篇存储**：title, abstract, summary, score, date, topic_name, doi, extracted_keywords, confirmed（默认 True）
- **confirmed 字段**：Phase 3 默认所有 HIGH 论文 confirmed=True；Phase 4 加入交互按钮后改为用户确认制
- **每次运行后追加**：Stage 2b 完成后将 HIGH 论文的分析结果写入 history
- **排序选取**：按同 topic → keywords 重叠数降序 → score 降序 → date 降序

### Claude's Discretion
- Stage 2b 和 Stage 3 prompt 的具体措辞和结构
- history 存储的具体 JSON schema
- token 日志记录的格式和输出位置
- 关键词重叠匹配的具体算法（Jaccard 系数或简单交集计数）
- 历史论文的淘汰时机（写入时还是读取时）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — 项目愿景、约束、设计原则
- `.planning/REQUIREMENTS.md` — 需求列表（Phase 3 涉及 ANLY-03, ANLY-04）
- `.planning/ROADMAP.md` — Phase 3 定义和成功标准
- `.planning/STATE.md` — 当前状态

### Existing Code to Build On
- `src/analysis/analyzer.py` — PaperAnalyzer 两阶段分析管线（需扩展为四阶段）
- `src/analysis/prompts.py` — 现有 prompt 模板（需新增 DEEP_ANALYSIS_PROMPT 和 COMPARATIVE_PROMPT）
- `src/search/models.py` — AnalysisResult、AnalyzedPaper 模型（需扩展字段）
- `src/delivery/feishu.py` — FeishuNotifier 飞书卡片展示（需扩展 HIGH tier 展示）
- `src/main.py` — 管线编排（需在 PDF 获取后插入新分析阶段）
- `src/config/models.py` — 配置模型（可能需要新增对比分析阈值配置）

### Prior Phase Context
- `.planning/phases/01-end-to-end-pipeline-proof/01-CONTEXT.md` — Phase 1 分析管线决策
- `.planning/phases/02-multi-source-search/02-CONTEXT.md` — Phase 2 多源搜索和 PDF 决策

### Research
- `.planning/research/STACK.md` — 技术栈选型
- `.planning/research/ARCHITECTURE.md` — 管线架构设计
- `.planning/research/PITFALLS.md` — 陷阱预防（特别是成本控制相关）

### Reference Code
- `paperRead/paperRead-main/main.py` — 两阶段 LLM 分析参考（Phase 1 已参考）
- `literature-search/scripts/literature_search/components/` — API 调用模式参考

</canonical_refs>

<code_context>
## Existing Code Insights

### Architecture (established in Phase 1 & 2)
- **PaperAnalyzer** (`analyzer.py`): 两阶段管线，score_paper() + analyze_paper()，使用 OpenAI SDK
- **Prompts** (`prompts.py`): get_language_instruction() 处理中文输出，{placeholder} 格式
- **AnalysisResult** (`models.py`): relevance_score, tier, summary, key_contributions, potential_applications, extracted_keywords, scoring_reason
- **FeishuNotifier** (`feishu.py`): _build_high_details() 展示 authors/summary/contributions/applications，_build_medium_details() 紧凑展示
- **Pipeline** (`main.py`): 8 步流程，Stage 1 评分 → PDF 获取 → Stage 2 深度分析 → 通知

### Key Integration Points
- `analyzer.py:analyze_paper()` → 需要拆分为 2a + 2b，或新增 `deep_analyze_methodology()` 方法
- `analyzer.py` → 需要新增 `compare_paper()` 方法（Stage 3）
- `models.py:AnalysisResult` → 直接添加 5 个 Optional 字段
- `feishu.py:_build_high_details()` → 追加 4 个新区块（方法论/局限性/未来方向/对比）
- `main.py` → 在 Stage 2a 之后插入 Stage 2b 和 Stage 3 调用，更新 state history 写入逻辑

### Patterns to Follow
- 现有 prompt 使用 `{placeholder}` + str.format() 模式
- JSON response parsing 使用 `_safe_json_parse()`
- 语言控制使用 `get_language_instruction(language)` 追加到 prompt
- 每个分析阶段独立 try/except，失败返回上一阶段结果
- OpenAI SDK 的 response_format={"type": "json_object"} 确保 JSON 输出

</code_context>

<specifics>
## Specific Ideas

- 深度分析要"具体可行动"，不要泛泛而谈（如不要"需要更多数据"，要说"需要扩展到 X 领域的数据集"）
- 对比分析应该帮助用户快速理解"这篇论文比之前看到的有什么新东西"
- 历史 state 的 confirmed 字段为 Phase 4 的交互确认机制预留接口
- token 消耗日志要记录每个阶段的 input/output token 数，方便用户优化

</specifics>

<deferred>
## Deferred Ideas

- 飞书交互式卡片按钮（"加入对比库"/"感兴趣"）— Phase 4
- 用户确认机制（confirmed 字段已在 Phase 3 预留，Phase 4 实现交互触发）
- Zotero/Obsidian 集成 — Phase 4
- Embedding 语义相似度匹配（当前用关键词重叠，未来可升级）
- Email 通知渠道 — v2
- 趋势检测（跨多次运行的研究趋势发现）— v2

---

*Phase: 03-advanced-ai-analysis*
*Context gathered: 2026-04-14*
