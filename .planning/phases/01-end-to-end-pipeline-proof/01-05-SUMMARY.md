---
phase: 01-end-to-end-pipeline-proof
plan: 05
subsystem: pipeline, infra
tags: [github-actions, asyncio, pipeline-orchestrator, cron, workflow-dispatch]

# Dependency graph
requires:
  - phase: 01-01
    provides: "AppConfig, Paper, AnalyzedPaper, SearchQuery, StateManager, load_config"
  - phase: 01-02
    provides: "ArxivSource, deduplicate_papers, fetch_and_enrich_paper"
  - phase: 01-03
    provides: "PaperAnalyzer, extract_keywords, prompt templates"
  - phase: 01-04
    provides: "FeishuNotifier with tiered formatting and message splitting"
provides:
  - "Pipeline orchestrator (src/main.py) wiring all components into 7-stage async pipeline"
  - "GitHub Actions workflow with cron and manual triggers"
affects: [phase-02-multi-source-search, phase-03-advanced-analysis]

# Tech tracking
tech-stack:
  added: [github-actions, asyncio.Semaphore]
  patterns: [7-stage-pipeline, error-isolation-per-topic, seen-paper-filter-before-analysis, topic-tracked-paper-association]

key-files:
  created:
    - src/main.py
    - .github/workflows/daily-push.yml
  modified: []

key-decisions:
  - "State saved only after successful notification to prevent duplicate pushes on retry"
  - "Papers tracked by originating topic during search; analysis only scores against that topic (no cross-topic duplication)"
  - "PDF fetch uses asyncio.Semaphore(5) to respect rate limits"
  - "GitHub Actions concurrency group prevents parallel runs that could corrupt state"
  - "Exit code 1 on total failure (no papers + errors), 0 on partial/complete success"

patterns-established:
  - "Topic-tracked paper association: papers_by_topic dict preserves which topic produced each paper through dedup+filter+analysis"
  - "Error isolation: per-topic try/except in search and analysis stages, one failure does not block others"

requirements-completed: [PIPE-01, PIPE-02, PIPE-03, PIPE-04, SRCH-07]

# Metrics
duration: 5min
completed: 2026-04-14
---

# Phase 01 Plan 05: Pipeline Orchestrator and GitHub Actions Summary

**7-stage async pipeline orchestrator wiring config/keywords/search/fetch/analysis/notification/state with GitHub Actions cron+dispatch workflow**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-14T03:40:00Z
- **Completed:** 2026-04-14T03:45:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Complete pipeline orchestrator (src/main.py) with 7 stages and per-topic error isolation
- GitHub Actions workflow with daily cron (UTC 01:00 / Beijing 09:00) and manual workflow_dispatch trigger
- Papers tracked by originating topic to prevent cross-topic duplication in analysis
- Seen-paper filtering via state.filter_new() before processing (SRCH-07)
- State saved only after successful notification to prevent re-push on failure

## Task Commits

Each task was committed atomically:

1. **Task 1: Create pipeline orchestrator (src/main.py)** - `0c4e604` (feat)
2. **Task 2: Create GitHub Actions workflow** - `25a64aa` (feat)

## Files Created/Modified
- `src/main.py` - Pipeline orchestrator: wires all components into 7-stage async pipeline with error isolation
- `.github/workflows/daily-push.yml` - GitHub Actions workflow with cron and workflow_dispatch triggers

## Decisions Made
- State saved only after successful notification -- if notification fails, papers remain unseen so they will be retried next run
- Papers associated with their originating topic during search persist through dedup+filter, ensuring analysis only scores against that topic's research interests
- PDF download concurrency limited to 5 via asyncio.Semaphore to respect arXiv rate limits
- GitHub Actions concurrency group with cancel-in-progress: false ensures state file integrity
- Pipeline step uses `id: run-pipeline` and state commit step references `steps.run-pipeline.outcome` for correct conditional execution

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- PyYAML parses YAML `on` key as Python boolean `True` -- verification script adjusted to handle this known quirk. The workflow file itself is correct; only the test script needed adaptation.

## User Setup Required

None - no external service configuration required beyond what previous plans established (LLM_API_KEY and FEISHU_WEBHOOK_URL GitHub Secrets).

## Next Phase Readiness
- Complete end-to-end pipeline is functional: config -> keywords -> search -> dedup -> PDF fetch -> AI analysis -> Feishu notification -> state save
- Phase 1 is now complete with all 5 plans executed
- Ready for Phase 2: Multi-Source Search and PDF Fetching (PubMed, OpenAlex, Semantic Scholar, DOI resolution)
- The pipeline orchestrator is designed to accommodate new search sources by adding to the per-topic search loop

## Self-Check: PASSED

- FOUND: src/main.py
- FOUND: .github/workflows/daily-push.yml
- FOUND: 01-05-SUMMARY.md
- FOUND: 0c4e604 (Task 1 commit)
- FOUND: 25a64aa (Task 2 commit)

---
*Phase: 01-end-to-end-pipeline-proof*
*Completed: 2026-04-14*
