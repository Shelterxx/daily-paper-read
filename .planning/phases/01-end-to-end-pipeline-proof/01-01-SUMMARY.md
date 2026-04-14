---
phase: 01-end-to-end-pipeline-proof
plan: 01
subsystem: config, data-models, state
tags: [pydantic, pydantic-settings, yaml, openai-sdk, state-management, deduplication]

# Dependency graph
requires: []
provides:
  - "Typed Pydantic config models (AppConfig, ResearchTopic, LLMConfig, etc.)"
  - "YAML config loader with env var validation and clear error messages"
  - "Unified Paper model with dedup_key property (DOI-primary, title-hash fallback)"
  - "SearchQuery, AnalysisResult, AnalyzedPaper, RelevanceTier models"
  - "StateManager with atomic JSON persistence and seen-paper filtering"
  - "SearchSource ABC for source adapter pattern"
  - "deduplicate_papers() for cross-query dedup"
  - "config.example.yaml with bilingual comments"
affects: [01-02-search-layer, 01-03-analysis-layer, 01-04-delivery, 01-05-ci-workflow]

# Tech tracking
tech-stack:
  added: [pydantic>=2.7, pydantic-settings>=2.2, PyYAML>=6.0, openai>=1.0.0]
  patterns: [research-topic-centric YAML config, pydantic v2 BaseModel validation, atomic JSON write via tempfile+rename, dedup by DOI with title-hash fallback, multi-model support via OpenAI-compatible interface]

key-files:
  created:
    - src/__init__.py
    - src/config/__init__.py
    - src/config/models.py
    - src/config/loader.py
    - src/config/models.py
    - src/search/__init__.py
    - src/search/models.py
    - src/search/base.py
    - src/search/dedup.py
    - src/state/__init__.py
    - src/state/manager.py
    - config.example.yaml
    - requirements.txt
    - .gitignore
  modified: []

key-decisions:
  - "Use OpenAI SDK (not anthropic SDK) for multi-model support via OpenAI-compatible interface per CONTEXT.md"
  - "Research-topic-centric config: each topic has its own keywords, thresholds, and source overrides"
  - "Dedup key uses DOI first (most reliable), falls back to SHA256 of normalized title"
  - "Atomic write via tempfile+rename to prevent state corruption on Windows/Linux"
  - "Env vars referenced by name in config (api_key_env) rather than stored directly in YAML"

patterns-established:
  - "Config pattern: YAML file -> pydantic model validation -> env var checks at load time"
  - "Data model pattern: Pydantic BaseModel with Field descriptions, property methods for computed fields"
  - "State pattern: JSON file with atomic write, in-memory set for fast lookups, batch save"

requirements-completed: [CONF-01, CONF-02, CONF-03, CONF-04, CONF-05, SRCH-06, SRCH-07, ZTR-06, OBS-05]

# Metrics
duration: 11min
completed: 2026-04-14
---

# Phase 01 Plan 01: Foundation Summary

**Pydantic v2 config layer with research-topic-centric YAML, unified Paper model with DOI/title dedup, and atomic StateManager for seen-paper tracking**

## Performance

- **Duration:** 11 min
- **Started:** 2026-04-14T02:53:35Z
- **Completed:** 2026-04-14T03:04:41Z
- **Tasks:** 2
- **Files modified:** 14

## Accomplishments
- Complete typed config system: AppConfig with ResearchTopic, LLMConfig, NotificationConfig, SourcesConfig
- Unified Paper data model with dedup_key property for cross-source deduplication
- StateManager with atomic JSON persistence (tempfile+rename pattern) for seen-paper tracking
- SearchSource ABC and deduplicate_papers() ready for source adapter implementations
- config.example.yaml with 2 example topics and bilingual comments

## Task Commits

Each task was committed atomically:

1. **Task 1: Create project structure, requirements.txt, and configuration layer** - `255aa36` (feat)
2. **Task 2: Create unified Paper/SearchQuery data models and StateManager** - `ac1e8a1` (feat)

**Plan metadata:** pending (docs: complete foundation plan)

_Note: Task 2 models were committed as part of plan 01-02's first commit since they were prerequisites for the search layer. The code matches the plan specification exactly._

## Files Created/Modified
- `src/__init__.py` - Package init with version 0.1.0
- `src/config/__init__.py` - Re-exports load_config and AppConfig
- `src/config/models.py` - Pydantic v2 config models: AppConfig, ResearchTopic, LLMConfig, NotificationConfig, SourceConfig, SourcesConfig, RelevanceThresholds
- `src/config/loader.py` - YAML config loader with env var validation and clear error messages
- `src/search/__init__.py` - Re-exports Paper, SearchQuery, AnalyzedPaper, RelevanceTier
- `src/search/models.py` - Paper (with dedup_key), SearchQuery, AnalysisResult, AnalyzedPaper, RelevanceTier
- `src/search/base.py` - SearchSource ABC with async search() and name property
- `src/search/dedup.py` - deduplicate_papers() keeping first occurrence by dedup_key
- `src/state/__init__.py` - Re-exports StateManager
- `src/state/manager.py` - StateManager with is_seen, mark_seen, mark_seen_batch, filter_new, atomic save
- `config.example.yaml` - Example config with 2 topics and bilingual comments
- `requirements.txt` - Phase 1 dependencies (10 packages)
- `.gitignore` - Excludes config.yaml, state/, __pycache__/, .env

## Decisions Made
- Used OpenAI SDK (not anthropic) per CONTEXT.md decision for multi-model support via OpenAI-compatible interface with custom base_url
- Research-topic-centric config organization: all search settings live in each topic, global config is minimal
- Dedup key uses DOI first (most reliable identifier), falls back to SHA256 of normalized title when DOI unavailable
- Atomic write pattern: tempfile + rename ensures state file integrity across crashes and OS differences
- Env vars referenced by configurable names (api_key_env, feishu_webhook_env) so users can choose their own variable names
- Zotero and Obsidian integrations are omitted from Phase 1 config -- no config keys cause errors if absent

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all verification passed on first attempt.

## User Setup Required

None - no external service configuration required at this stage. Users will need to set LLM_API_KEY and FEISHU_WEBHOOK_URL env vars before running the pipeline, documented in config.example.yaml.

## Next Phase Readiness
- Config layer and data models are complete, ready for search layer implementation (Plan 01-02)
- StateManager is ready to filter seen papers during search
- SearchSource ABC defines the interface for source adapters
- Deduplication logic is ready to merge results from multiple queries

## Self-Check: PASSED

- All 13 files verified present on disk
- Task 1 commit `255aa36` found in git log
- Task 2 commit `ac1e8a1` found in git log
- All Python modules import without errors
- Paper dedup_key consistent for same DOI and normalized title
- config.example.yaml valid with 2 topics

---
*Phase: 01-end-to-end-pipeline-proof*
*Completed: 2026-04-14*
