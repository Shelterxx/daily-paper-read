---
phase: 01-end-to-end-pipeline-proof
plan: 03
subsystem: analysis
tags: [openai, llm, scoring, analysis, keywords, prompt-engineering]

# Dependency graph
requires:
  - phase: 01-end-to-end-pipeline-proof
    plan: 01
    provides: "LLMConfig, RelevanceThresholds from config/models; Paper, AnalysisResult, AnalyzedPaper, RelevanceTier from search/models"
provides:
  - "PaperAnalyzer: two-stage AI analysis pipeline (batch scoring + deep analysis)"
  - "Prompt templates for scoring, analysis, and keyword extraction"
  - "extract_keywords: LLM-based keyword extraction from natural language descriptions"
  - "_safe_json_parse: robust JSON parsing for LLM output"
affects: [notification, pipeline-orchestration]

# Tech tracking
tech-stack:
  added: [openai-sdk]
  patterns: [two-stage-analysis, tiered-output, json-object-response-format]

key-files:
  created:
    - src/analysis/__init__.py
    - src/analysis/prompts.py
    - src/analysis/keyword_extractor.py
    - src/analysis/analyzer.py
  modified: []

key-decisions:
  - "Use OpenAI SDK with custom base_url for multi-model support (Claude, GLM, DeepSeek via OpenAI-compatible endpoints)"
  - "Two-stage analysis: Haiku for batch scoring all papers, Sonnet for deep analysis of high-relevance only"
  - "Scoring done paper-by-paper rather than true batch to simplify error handling"
  - "Full text capped at 8000 chars for analysis, 2000 for scoring to manage token costs"
  - "Keyword extraction falls back to word splitting when LLM is unavailable"

patterns-established:
  - "Two-stage analysis pattern: cheap model for filtering, capable model for deep work"
  - "Safe JSON parsing: direct parse -> regex extract -> empty dict fallback"
  - "Configurable thresholds via RelevanceThresholds model for tier classification"

requirements-completed: [ANLY-01, ANLY-02, ANLY-05]

# Metrics
duration: 4min
completed: 2026-04-14
---

# Phase 1 Plan 3: AI Analysis Pipeline Summary

**Two-stage paper analysis with Haiku scoring + Sonnet deep analysis, tiered output (high/medium/low), and LLM keyword extraction via OpenAI-compatible SDK**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-14T03:14:26Z
- **Completed:** 2026-04-14T03:19:24Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- PaperAnalyzer class with two-stage analysis pipeline: batch scoring (fast model) then deep analysis (capable model) for high-relevance papers only
- Prompt templates for scoring (1-10 scale with reason), analysis (summary + contributions + applications), and keyword extraction
- Keyword extractor with LLM-based extraction from natural language descriptions and automatic fallback to word splitting
- Robust _safe_json_parse handling malformed LLM JSON output (extra text, partial JSON)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create prompt templates and keyword extractor** - `b517343` (feat)
2. **Task 2: Create PaperAnalyzer with two-stage analysis pipeline** - `65d52b0` (feat)

## Files Created/Modified
- `src/analysis/__init__.py` - Package init with re-exports for PaperAnalyzer and extract_keywords
- `src/analysis/prompts.py` - SCORING_PROMPT, ANALYSIS_PROMPT, KEYWORD_EXTRACTION_PROMPT templates with {placeholder} syntax
- `src/analysis/keyword_extractor.py` - extract_keywords function with LLM call + word-based fallback; _safe_json_parse helper
- `src/analysis/analyzer.py` - PaperAnalyzer class with score_paper, analyze_paper, analyze_papers methods; two-stage pipeline

## Decisions Made
- Used OpenAI SDK (not anthropic SDK) with custom base_url for multi-model support per CONTEXT.md decisions
- Scoring is done one-by-one (not true batch API) to simplify error handling; each paper is independent
- Full text capped at 8000 chars for deep analysis, 2000 for scoring to manage token costs per PITFALLS.md cost control
- __init__.py initially used try/except import for PaperAnalyzer to allow incremental module creation; updated to direct import after analyzer.py was created

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Analysis layer complete, ready for notification formatting (Plan 04) and pipeline orchestration (Plan 05)
- PaperAnalyzer.analyze_papers() produces AnalyzedPaper list that notification templates can consume
- extract_keywords() ready to be called by pipeline orchestrator for keyword extraction from ResearchTopic descriptions

---
*Phase: 01-end-to-end-pipeline-proof*
*Completed: 2026-04-14*

## Self-Check: PASSED
- All 4 key files verified on disk
- Both task commits (b517343, 65d52b0) verified in git log
