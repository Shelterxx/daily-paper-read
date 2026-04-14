---
phase: 01-end-to-end-pipeline-proof
plan: 02
subsystem: search
tags: [arxiv, pdf, pymupdf, httpx, tenacity, asyncio, feedparser, deduplication]

# Dependency graph
requires:
  - phase: 01-end-to-end-pipeline-proof
    plan: 01
    provides: "Paper and SearchQuery data models (src/search/models.py)"
provides:
  - "SearchSource ABC interface for pluggable search adapters"
  - "ArxivSource adapter with arxiv library + feedparser fallback"
  - "Cross-query deduplication by DOI/title hash"
  - "Async PDF downloader with magic bytes validation"
  - "PyMuPDF text extractor with graceful abstract fallback"
affects: [01-03-PLAN, 01-04-PLAN, 01-05-PLAN]

# Tech tracking
tech-stack:
  added: [arxiv>=2.4.0, feedparser>=6.0.11, httpx>=0.27, tenacity>=8.2, PyMuPDF>=1.24]
  patterns: [SearchSource ABC adapter pattern, asyncio.gather parallel search, PDF magic bytes validation, tenacity retry with exponential backoff, graceful abstract fallback]

key-files:
  created:
    - src/search/base.py
    - src/search/arxiv_source.py
    - src/search/dedup.py
    - src/search/models.py
    - src/fetch/__init__.py
    - src/fetch/pdf_fetcher.py
    - src/fetch/text_extractor.py
  modified: []

key-decisions:
  - "ArxivSource uses arxiv library as primary, feedparser+httpx as fallback for robustness"
  - "Parallel keyword search via asyncio.gather with semaphore limiting to 2 concurrent requests"
  - "PDF validation via magic bytes (%PDF) prevents processing non-PDF HTTP responses"
  - "Minimum 100 chars extracted text threshold avoids blank/title-only extraction being treated as full_text"

patterns-established:
  - "SearchSource ABC: all search adapters implement async search() + name property"
  - "Graceful degradation: PDF fetch failure -> abstract fallback, pipeline never crashes on fetch errors"
  - "Dedup at search layer: deduplicate_papers runs on combined results from parallel queries"

requirements-completed: [SRCH-01, SRCH-06, SRCH-08, FETH-05]

# Metrics
duration: 10min
completed: 2026-04-14
---

# Phase 1 Plan 2: ArXiv Search + PDF Pipeline Summary

**ArXiv search adapter with parallel keyword queries, cross-query dedup by DOI/title hash, async PDF download with PyMuPDF text extraction and abstract fallback**

## Performance

- **Duration:** 10 min
- **Started:** 2026-04-14T02:54:47Z
- **Completed:** 2026-04-14T03:04:47Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- SearchSource ABC establishes clean adapter interface for adding PubMed/OpenAlex in Phase 2
- ArxivSource runs parallel keyword searches via asyncio.gather with rate-limiting semaphore
- Deduplication by DOI (primary) and SHA256 title hash (fallback) per SRCH-06
- PDF fetch validates magic bytes, enforces 50MB size limit, retries on transient errors
- PyMuPDF text extraction with graceful fallback to abstract on any failure

## Task Commits

Each task was committed atomically:

1. **Task 1: Create SearchSource ABC and ArxivSource adapter** - `ac1e8a1` (feat)
2. **Task 2: Create PDF fetcher and PyMuPDF text extractor** - `5000f4a` (feat)

## Files Created/Modified
- `src/search/models.py` - Paper, SearchQuery, AnalysisResult, AnalyzedPaper data models (prerequisite from Plan 01)
- `src/search/__init__.py` - Search package re-exports
- `src/search/base.py` - SearchSource ABC with abstract search() and name property
- `src/search/arxiv_source.py` - ArxivSource adapter using arxiv library + feedparser fallback
- `src/search/dedup.py` - deduplicate_papers by dedup_key (DOI/title hash)
- `src/fetch/__init__.py` - Fetch package re-exports
- `src/fetch/pdf_fetcher.py` - Async PDF download with retry, validation, and enrichment
- `src/fetch/text_extractor.py` - PyMuPDF text extraction wrapper

## Decisions Made
- Used arxiv library (v2.4.0+) as primary interface with feedparser fallback for robustness against library-specific errors
- Semaphore-based concurrency limiting (2 concurrent) respects arXiv ~1 req/s rate limit while enabling parallelism
- 100-char minimum for extracted text prevents treating title-only or blank extraction as full_text
- All retry logic uses tenacity library with exponential backoff rather than custom retry loops

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Issue] Created prerequisite data models from Plan 01**
- **Found during:** Pre-task initialization
- **Issue:** Plan 01-01 has not been executed; src/search/models.py (Paper, SearchQuery) did not exist but is required by all Plan 02 files
- **Fix:** Created src/search/models.py, src/search/__init__.py with the exact models specified in Plan 01-01 Task 2
- **Files modified:** src/search/models.py, src/search/__init__.py
- **Verification:** All Plan 02 imports succeed, Task 1 and Task 2 verification tests pass
- **Committed in:** ac1e8a1 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking prerequisite)
**Impact on plan:** Minimal. Created only the prerequisite models.py from Plan 01. No scope creep.

## Issues Encountered
None - all verification steps passed cleanly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Search layer and PDF fetch/extract pipeline complete and verified
- ArxivSource can be used by the pipeline orchestrator in Plan 03 (AI analysis)
- PDF text (or abstract fallback) feeds into the AI analysis layer
- SearchSource ABC ready for additional adapters (PubMed, OpenAlex) in Phase 2

---
*Phase: 01-end-to-end-pipeline-proof*
*Completed: 2026-04-14*
