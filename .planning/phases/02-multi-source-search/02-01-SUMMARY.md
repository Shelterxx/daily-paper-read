---
phase: 02-multi-source-search
plan: 01
subsystem: search
tags: [httpx, tenacity, openalex, semantic-scholar, supabase, async, search-adapter]

# Dependency graph
requires:
  - phase: 01-end-to-end-pipeline-proof
    provides: SearchSource ABC, Paper/SearchQuery models, SourcesConfig, ArxivSource reference pattern
provides:
  - SciSearchSource adapter for Supabase Edge Function API
  - OpenAlexSource adapter for OpenAlex Works API with inverted index abstract reconstruction
  - SemanticScholarSource adapter for S2 Graph API with optional API key auth
  - Expanded SourcesConfig with sci_search, openalex, semantic_scholar fields (default disabled)
affects: [02-02, 02-03, pipeline-orchestration, config]

# Tech tracking
tech-stack:
  added: [httpx, tenacity]
  patterns: [async-search-adapter, semaphore-rate-limiting, inverted-index-abstract-reconstruction]

key-files:
  created:
    - src/search/sci_search_source.py
    - src/search/openalex_source.py
    - src/search/semantic_scholar_source.py
  modified:
    - src/config/models.py
    - src/search/__init__.py

key-decisions:
  - "New sources default to enabled=False to preserve existing config behavior"
  - "tenacity retry only on 5xx server errors, not 4xx client errors"
  - "S2 uses 3 retry attempts vs 2 for other sources due to flakier API"
  - "S2 rate limiting: 3.0s anonymous, 1.0s with API key; OpenAlex 0.2s with polite pool"

patterns-established:
  - "SearchSource adapter pattern: httpx async client + tenacity retry + semaphore + inter-request delay + asyncio.gather parallel keywords"
  - "Graceful degradation when env vars missing (empty results, not crash)"

requirements-completed: [SRCH-02, SRCH-03, SRCH-04]

# Metrics
duration: 6min
completed: 2026-04-14
---

# Phase 2 Plan 1: Three New Search Source Adapters Summary

**Three SearchSource adapters (sci_search, OpenAlex, Semantic Scholar) with httpx/tenacity async pattern, expanded SourcesConfig with per-source toggles**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-14T12:29:14Z
- **Completed:** 2026-04-14T12:35:48Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- SciSearchSource adapter for Supabase Edge Function API with POST requests and x-api-key auth
- OpenAlexSource adapter with inverted index abstract reconstruction and polite pool support
- SemanticScholarSource adapter with optional API key auth and conservative rate limiting
- SourcesConfig expanded with 3 new source fields, all defaulting to enabled=False

## Task Commits

Each task was committed atomically:

1. **Task 1: Expand SourcesConfig and create SciSearchSource adapter** - `f4a1559` (feat)
2. **Task 2: Create OpenAlexSource and SemanticScholarSource adapters** - `631daac` (feat)

## Files Created/Modified
- `src/search/sci_search_source.py` - SciSearchSource adapter (POST to Supabase Edge Function, graceful token degradation)
- `src/search/openalex_source.py` - OpenAlexSource adapter (GET Works API, inverted index abstract reconstruction, polite pool)
- `src/search/semantic_scholar_source.py` - SemanticScholarSource adapter (GET Graph API, optional S2_API_KEY, year range filtering)
- `src/config/models.py` - SourcesConfig expanded with sci_search, openalex, semantic_scholar fields
- `src/search/__init__.py` - Package exports updated with all 3 new adapters

## Decisions Made
- New sources default to enabled=False so existing configs work unchanged (backward compatibility)
- tenacity retry logic simplified from conditional to inline 5xx check before raise_for_status (cleaner than conditional retry predicate)
- S2 uses 3 retry attempts (vs 2 for other sources) and longer delays due to flakier API behavior
- OpenAlex sorts by publication_date:desc (most recent first) vs cited_by_count:desc in reference (more relevant for daily digest use case)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

None - no external service configuration required. Adapters gracefully degrade when API keys are not set.

To enable sources, set these environment variables:
- `SCI_SEARCH_API_TOKEN` - required for sci_search
- `OPENALEX_EMAIL` - optional, enables polite pool (10 req/s)
- `S2_API_KEY` - optional, increases S2 rate limit from 100 req/5min to 1 req/sec

## Next Phase Readiness
- All 3 new adapters ready for integration into pipeline orchestrator (src/main.py Step 3)
- SourcesConfig ready for per-topic source override configuration
- Adapters follow identical pattern to ArxivSource, making orchestration straightforward

---
*Phase: 02-multi-source-search*
*Completed: 2026-04-14*

## Self-Check: PASSED

- FOUND: src/search/sci_search_source.py
- FOUND: src/search/openalex_source.py
- FOUND: src/search/semantic_scholar_source.py
- FOUND: .planning/phases/02-multi-source-search/02-01-SUMMARY.md
- FOUND: commit f4a1559 (Task 1)
- FOUND: commit 631daac (Task 2)
