---
phase: 02-multi-source-search
plan: 02
subsystem: search
tags: [doi, unpaywall, pmc, pdf, httpx, tenacity, content-negotiation]

# Dependency graph
requires:
  - phase: 01-end-to-end-pipeline-proof
    provides: Paper model, fetch_pdf, extract_text_from_pdf, fetch_and_enrich_paper
provides:
  - DOI metadata enrichment via content negotiation (citeproc+json)
  - Multi-channel PDF fetcher with Unpaywall/PMC priority fallback
  - resolve_unpaywall_pdf_url for open-access PDF URL resolution
  - resolve_pmc_pdf_url for PMC direct PDF links
affects: [02-03, multi-source-search, pdf-fetching, dedup]

# Tech tracking
tech-stack:
  added: []
  patterns: [multi-channel-fallback-chain, doi-content-negotiation, unpaywall-oa-resolution]

key-files:
  created:
    - src/search/doi_resolver.py
    - src/fetch/multi_channel_fetcher.py
  modified:
    - src/fetch/__init__.py

key-decisions:
  - "DOI enrichment only fills missing fields, never overwrites existing data"
  - "Unpaywall requires UNPAYWALL_EMAIL env var; channel skipped silently if not set"
  - "PMC ID detection via paper.source in (pubmed, pmc) and paper.paper_id"
  - "All download validation delegated to existing fetch_pdf (no duplication)"

patterns-established:
  - "Multi-channel fallback: try channels in priority order, log each attempt, fall back gracefully"
  - "In-place Paper mutation: enrich functions mutate Paper directly (same as fetch_and_enrich_paper)"

requirements-completed: [SRCH-05, FETH-02, FETH-03]

# Metrics
duration: 4min
completed: 2026-04-14
---

# Phase 2 Plan 2: DOI Resolver and Multi-Channel PDF Fetcher Summary

**DOI content negotiation enriches missing paper metadata (title/authors/abstract) via citeproc+json, and multi-channel PDF fetcher tries paper.pdf_url -> Unpaywall -> PMC before falling back to abstract**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-14T12:28:58Z
- **Completed:** 2026-04-14T12:33:22Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- DOI metadata resolver fills gaps in paper data via CrossRef content negotiation, improving dedup accuracy
- Unpaywall API integration resolves open-access PDF URLs from DOIs (requires UNPAYWALL_EMAIL env var)
- Multi-channel PDF fetcher implements 3-channel priority chain: direct URL -> Unpaywall -> PMC
- All download validation reused from existing fetch_pdf (magic bytes, 50MB limit, retry logic)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create DOI metadata resolver** - `4a5b20c` (feat)
2. **Task 2: Create multi-channel PDF fetcher with Unpaywall and PMC** - `b31980f` (feat)

## Files Created/Modified
- `src/search/doi_resolver.py` - DOI content negotiation enrichment (enrich_paper_from_doi, enrich_papers_batch)
- `src/fetch/multi_channel_fetcher.py` - Multi-channel PDF fetching with Unpaywall/PMC fallback chain
- `src/fetch/__init__.py` - Added fetch_pdf_multi_channel export

## Decisions Made
- DOI enrichment is additive-only: fills missing fields, never overwrites existing data
- Unpaywall channel is silently skipped when UNPAYWALL_EMAIL env var is not set (no warnings for users who don't use it)
- PMC ID detection uses paper.source == "pubmed"/"pmc" with paper.paper_id as the PMC ID
- Extracted _try_download_and_extract helper to avoid code duplication across channels
- _parse_date helper handles partial dates (year-only, year-month) from citeproc format

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

To enable Unpaywall PDF resolution, set the `UNPAYWALL_EMAIL` environment variable to a valid email address. Without it, the Unpaywall channel is skipped silently.

## Next Phase Readiness
- DOI resolver ready for integration into multi-source search pipeline (Plan 02-03)
- Multi-channel fetcher ready to replace fetch_and_enrich_paper for non-arXiv papers
- All imports verified; existing pdf_fetcher.py unmodified

## Self-Check: PASSED

All files exist:
- src/search/doi_resolver.py
- src/fetch/multi_channel_fetcher.py
- src/fetch/__init__.py
- .planning/phases/02-multi-source-search/02-02-SUMMARY.md

All commits found:
- 4a5b20c (Task 1)
- b31980f (Task 2)

---
*Phase: 02-multi-source-search*
*Completed: 2026-04-14*
