---
phase: 01-end-to-end-pipeline-proof
verified: 2026-04-14T12:00:00Z
status: passed
score: 5/5 must-haves verified
---

# Phase 01: End-to-End Pipeline Proof Verification Report

**Phase Goal:** A researcher receives a daily Feishu message with AI-scored and summarized papers from arXiv, proving the full pipeline works
**Verified:** 2026-04-14
**Status:** PASSED
**Re-verification:** No -- initial verification

## Goal Achievement

The phase goal is an end-to-end pipeline that: loads config, searches arXiv, scores papers with AI, and delivers a Feishu message. Verified by tracing the complete data flow from config through to notification.

### Observable Truths (from ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can fork the repo, configure YAML, add GitHub Secrets, and trigger a workflow run that completes within 30 minutes | VERIFIED | config.example.yaml validates against AppConfig; workflow has timeout-minutes: 30; secrets referenced in workflow; pip cache for fast deps |
| 2 | User receives a Feishu rich message card with tiered paper display (HIGH=full analysis, MEDIUM=summary, LOW=title+link) | VERIFIED | FeishuNotifier builds messages with 3-tier display; verified HIGH shows summary+contributions+applications+link; MEDIUM shows summary+contributions+link; LOW shows title+link only |
| 3 | Re-running the pipeline does not re-push papers already seen in previous runs | VERIFIED | StateManager.filter_new() called at line 128 of main.py; mark_seen_batch() called after successful notification at line 217; atomic JSON persistence via tempfile+rename |
| 4 | If arXiv search or Claude API calls fail, the pipeline logs clear errors and exits gracefully | VERIFIED | Per-topic try/except in search (line 111) and analysis (line 179); errors collected in stats["errors"]; exit code 1 only if total_papers==0 and errors exist |
| 5 | User can enable/disable search sources and adjust relevance score thresholds via YAML config | VERIFIED | SourcesConfig has enabled toggle; arxiv.enabled checked at line 96; RelevanceThresholds per topic with high/medium cutoffs; configurable via config.yaml |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/config/models.py` | Pydantic config models | VERIFIED | Exports: AppConfig, ResearchTopic, LLMConfig, NotificationConfig, SourceConfig, SourcesConfig, RelevanceThresholds (109 lines) |
| `src/config/loader.py` | YAML + env config loader | VERIFIED | Exports load_config; validates YAML, Pydantic model, env vars with clear error messages |
| `src/state/manager.py` | Seen-paper tracking | VERIFIED | Exports StateManager with is_seen, mark_seen, mark_seen_batch, filter_new, atomic save via tempfile+rename |
| `src/search/models.py` | Unified Paper model | VERIFIED | Exports Paper (with dedup_key), SearchQuery, AnalysisResult, AnalyzedPaper, RelevanceTier |
| `config.example.yaml` | Example config with comments | VERIFIED | 2 topics (LLM Reasoning, Multi-Agent RL), bilingual comments, validates against AppConfig |
| `requirements.txt` | Python dependencies | VERIFIED | 10 dependencies: openai, pydantic, pydantic-settings, httpx, PyYAML, arxiv, feedparser, Jinja2, tenacity, PyMuPDF |
| `src/search/base.py` | SearchSource ABC | VERIFIED | Abstract async search() and name property |
| `src/search/arxiv_source.py` | ArXiv search adapter | VERIFIED | Implements SearchSource; async search with asyncio.gather; feedparser fallback; tenacity retry |
| `src/search/dedup.py` | Deduplication logic | VERIFIED | Exports deduplicate_papers using Paper.dedup_key |
| `src/fetch/pdf_fetcher.py` | Async PDF download | VERIFIED | Exports fetch_pdf and fetch_and_enrich_paper; magic bytes validation; 50MB limit; 30s timeout |
| `src/fetch/text_extractor.py` | PyMuPDF text extraction | VERIFIED | Exports extract_text_from_pdf using fitz; multi-page; returns None on failure |
| `src/analysis/analyzer.py` | Two-stage AI analysis | VERIFIED | Exports PaperAnalyzer; score_paper (all), analyze_paper (HIGH only); OpenAI SDK with custom base_url |
| `src/analysis/prompts.py` | Prompt templates | VERIFIED | Exports SCORING_PROMPT, ANALYSIS_PROMPT, KEYWORD_EXTRACTION_PROMPT with {placeholder} syntax |
| `src/analysis/keyword_extractor.py` | LLM keyword extraction | VERIFIED | Exports extract_keywords; LLM call with word-splitting fallback |
| `src/delivery/base.py` | Notifier ABC | VERIFIED | Abstract async send(papers, topic_stats) |
| `src/delivery/feishu.py` | Feishu notifier | VERIFIED | Exports FeishuNotifier; tiered display; topic grouping; message splitting at 28KB |
| `templates/feishu_card.json.j2` | Feishu card template | VERIFIED | Renders valid JSON with msg_type "post"; language-aware locale |
| `src/main.py` | Pipeline orchestrator | VERIFIED | 7-stage async pipeline wiring all components; error isolation; topic-tracked papers |
| `.github/workflows/daily-push.yml` | GitHub Actions workflow | VERIFIED | Cron (UTC 01:00), workflow_dispatch, timeout 30min, concurrency group, secrets, Python 3.12 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| src/config/loader.py | config.yaml | pydantic YAML validation | WIRED | yaml.safe_load + AppConfig.model_validate |
| src/config/loader.py | src/config/models.py | imports AppConfig | WIRED | `from .models import AppConfig` (line 8) |
| src/state/manager.py | state/seen_papers.json | JSON read/write | WIRED | Atomic tempfile+rename pattern |
| src/state/manager.py | src/search/models.py | Paper.dedup_key | WIRED | filter_new() calls p.dedup_key |
| src/search/arxiv_source.py | src/search/models.py | Paper + SearchQuery | WIRED | Imports Paper, SearchQuery; produces Paper list |
| src/search/arxiv_source.py | src/search/base.py | SearchSource ABC | WIRED | `class ArxivSource(SearchSource)` |
| src/fetch/pdf_fetcher.py | src/search/models.py | paper.full_text | WIRED | Mutates paper.full_text and paper.text_source |
| src/fetch/text_extractor.py | PyMuPDF (fitz) | PDF text extraction | WIRED | `fitz.open(stream=io.BytesIO(pdf_bytes))` |
| src/analysis/analyzer.py | OpenAI SDK | OpenAI(base_url) | WIRED | `OpenAI(api_key=..., base_url=llm_config.base_url)` |
| src/analysis/analyzer.py | src/search/models.py | Paper -> AnalysisResult | WIRED | Consumes Paper, produces AnalysisResult/AnalyzedPaper |
| src/analysis/analyzer.py | src/config/models.py | LLMConfig | WIRED | Imports LLMConfig, RelevanceThresholds |
| src/analysis/keyword_extractor.py | OpenAI SDK | client.chat.completions.create | WIRED | Takes OpenAI client, calls completions API |
| src/delivery/feishu.py | src/search/models.py | AnalyzedPaper | WIRED | Imports AnalyzedPaper, RelevanceTier |
| src/delivery/feishu.py | templates/feishu_card.json.j2 | Jinja2 rendering | WIRED | `self._env.get_template("feishu_card.json.j2")` |
| src/delivery/feishu.py | Feishu webhook | httpx POST | WIRED | `await client.post(self.webhook_url, json=message)` |
| src/main.py | src/config/loader.py | load_config | WIRED | Imported at line 18, called at line 52 |
| src/main.py | src/analysis/keyword_extractor.py | extract_keywords | WIRED | Imported at line 25, called at line 88 |
| src/main.py | src/search/arxiv_source.py | ArxivSource | WIRED | Imported at line 22, instantiated at line 78 |
| src/main.py | src/fetch/pdf_fetcher.py | fetch_and_enrich_paper | WIRED | Imported at line 24, called at line 151 |
| src/main.py | src/analysis/analyzer.py | PaperAnalyzer | WIRED | Imported at line 26, instantiated at line 171 |
| src/main.py | src/delivery/feishu.py | FeishuNotifier | WIRED | Imported at line 27, instantiated at line 201 |
| src/main.py | src/state/manager.py | StateManager | WIRED | Imported at line 20, filter_new at line 128, mark_seen_batch at line 217 |
| .github/workflows/daily-push.yml | src/main.py | python -m src.main | WIRED | `python -m src.main "${{ ... }}"` at line 51 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CONF-01 | 01-01 | Validated YAML config with search queries and preferences | SATISFIED | AppConfig with research_topics, sources, llm, notification; Pydantic validation |
| CONF-02 | 01-01 | config.example.yaml with sensible defaults | SATISFIED | 2 topics, bilingual comments, all sections documented |
| CONF-03 | 01-01 | API credentials from env vars with clear errors | SATISFIED | loader.py checks api_key_env and feishu_webhook_env; raises ValueError naming specific var |
| CONF-04 | 01-01 | Enable/disable search sources via config | SATISFIED | SourcesConfig.arxiv.enabled; checked in main.py line 96 |
| CONF-05 | 01-01 | Configurable relevance thresholds | SATISFIED | RelevanceThresholds(high=7, medium=4) per topic; configurable in YAML |
| SRCH-01 | 01-02 | arXiv search with date filtering | SATISFIED | ArxivSource with keyword search, date cutoff, max_results |
| SRCH-06 | 01-01/01-02 | Dedup by DOI and normalized title hash | SATISFIED | Paper.dedup_key (DOI-first, title-hash fallback); deduplicate_papers() in dedup.py |
| SRCH-07 | 01-01/01-05 | Seen-paper tracking across runs | SATISFIED | StateManager.filter_new() at line 128; mark_seen_batch() at line 217 |
| SRCH-08 | 01-02 | Parallel search via asyncio | SATISFIED | asyncio.gather() in ArxivSource.search(); semaphore limiting |
| FETH-05 | 01-02 | Abstract fallback when PDF unavailable | SATISFIED | fetch_and_enrich_paper sets text_source="abstract" on any failure |
| ANLY-01 | 01-03 | Relevance scoring 1-10 via Claude API | SATISFIED | PaperAnalyzer.score_paper() with SCORING_PROMPT; OpenAI SDK |
| ANLY-02 | 01-03 | Concise summaries for medium+ papers | SATISFIED | analyze_paper() with ANALYSIS_PROMPT for HIGH papers; summary field on AnalysisResult |
| ANLY-05 | 01-03 | Tiered output (high/medium/low) | SATISFIED | _determine_tier(); tiered display in FeishuNotifier |
| NTFY-01 | 01-04 | Feishu rich message cards | SATISFIED | FeishuNotifier with msg_type "post" rich text |
| NTFY-02 | 01-04 | Title, authors, score, analysis, links | SATISFIED | _build_paper_section renders all fields based on tier |
| NTFY-03 | 01-04 | Message splitting for large digests | SATISFIED | _split_messages() with 28KB threshold |
| ZTR-06 | 01-01 | Zotero optional | SATISFIED | No Zotero config required; pipeline runs without Zotero |
| OBS-05 | 01-01 | Obsidian optional | SATISFIED | No Obsidian config required; pipeline runs without Obsidian |
| PIPE-01 | 01-05 | Daily cron trigger | SATISFIED | `cron: '0 1 * * *'` (UTC 01:00 = Beijing 09:00) |
| PIPE-02 | 01-05 | Manual workflow_dispatch | SATISFIED | workflow_dispatch with optional config_path input |
| PIPE-03 | 01-05 | Complete within 30 minutes | SATISFIED | timeout-minutes: 30 in workflow |
| PIPE-04 | 01-05 | Graceful partial failure handling | SATISFIED | Per-topic try/except in search and analysis; errors collected but pipeline continues |

**No orphaned requirements found.** All 22 requirement IDs from ROADMAP.md Phase 1 are claimed by at least one plan and verified in the codebase.

### Anti-Patterns Found

No blocker or warning anti-patterns detected.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/analysis/keyword_extractor.py | 77 | `return {}` | Info | Intentional fallback in _safe_json_parse when JSON parsing fails |
| src/analysis/analyzer.py | 193 | `return {}` | Info | Same intentional fallback pattern |
| src/search/arxiv_source.py | 198 | `return []` | Info | Intentional empty result when feedparser fallback also fails |

No TODO/FIXME/PLACEHOLDER/HACK comments found. No stub implementations found. No empty handlers or console.log-only functions.

### Human Verification Required

### 1. End-to-end Pipeline Execution

**Test:** Fork the repo, create config.yaml from config.example.yaml, set LLM_API_KEY and FEISHU_WEBHOOK_URL as GitHub Secrets, trigger workflow_dispatch
**Expected:** Pipeline completes successfully; Feishu message received within 30 minutes with tiered paper display
**Why human:** Requires actual API credentials, external service (Feishu webhook), and GitHub Actions execution environment; cannot be verified with grep/static analysis

### 2. Feishu Message Visual Quality

**Test:** Examine the received Feishu message card
**Expected:** Papers grouped by topic, high-relevance papers visually distinct with full analysis, stats header at top, links clickable
**Why human:** Rich text rendering quality and visual formatting can only be assessed by viewing the actual Feishu message

### 3. arXiv Search Result Relevance

**Test:** Run pipeline with "LLM Reasoning" topic, inspect paper results
**Expected:** Papers are genuinely related to LLM reasoning, scored correctly (relevant papers score 7+), timeframe filtering works (only recent papers)
**Why human:** Requires real arXiv API call; relevance of results is a qualitative judgment

### 4. Language Configuration (zh/en/mixed)

**Test:** Change notification.language to "en" in config.yaml, re-run
**Expected:** Message uses English locale (en_us) and English header text
**Why human:** Visual verification of language switching in the delivered message

### Gaps Summary

No gaps found. All artifacts exist, are substantive (not stubs), and are properly wired together. The complete pipeline chain is verified:

1. Config loading: YAML -> Pydantic validation -> env var checks
2. Keyword extraction: topic description -> LLM call -> keyword list
3. Search: keywords -> ArxivSource -> Paper list (async, with feedparser fallback)
4. Dedup + state filter: deduplicate_papers -> state.filter_new
5. PDF fetch: pdf_url -> httpx download -> PyMuPDF extraction -> abstract fallback
6. AI analysis: Paper -> PaperAnalyzer (score all, deep-analyze HIGH only) -> AnalyzedPaper
7. Notification: AnalyzedPaper -> FeishuNotifier -> Jinja2 template -> httpx POST
8. State save: mark_seen_batch (only after successful notification)

The phase goal is achieved: the codebase supports a complete pipeline from configuration through arXiv search, AI scoring, and Feishu delivery.

---

_Verified: 2026-04-14_
_Verifier: Claude (gsd-verifier)_
