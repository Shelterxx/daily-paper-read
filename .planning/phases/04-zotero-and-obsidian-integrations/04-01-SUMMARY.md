---
phase: 04-zotero-and-obsidian-integrations
plan: 01
subsystem: integrations
tags: [zotero, pyzotero, pydantic, config, obsidian, archiving]

# Dependency graph
requires:
  - phase: 01-end-to-end-pipeline-proof
    provides: "AppConfig, Paper, AnalyzedPaper, AnalysisResult models"
  - phase: 03-advanced-ai-analysis
    provides: "Deep analysis fields (methodology, limitations, future_directions)"
provides:
  - "ZoteroConfig and ObsidianConfig config models"
  - "ZoteroArchiver class with full ZTR-01~05 archiving pipeline"
  - "src/integrations package with lazy import pattern"
affects: [04-02, 04-03, main-pipeline]

# Tech tracking
tech-stack:
  added: [pyzotero>=1.5]
  patterns: [lazy-client-init, exponential-backoff-retry, linked-url-pdf-attachment]

key-files:
  created:
    - src/integrations/__init__.py
    - src/integrations/zotero.py
  modified:
    - src/config/models.py
    - requirements.txt

key-decisions:
  - "Lazy pyzotero client init via property to defer credential validation until first use"
  - "PDF attached as linked_url (not uploaded file) since pipeline runs in CI without local PDFs"
  - "Tags added by fetching item and updating via update_item rather than create_tags for robustness"
  - "Dedup searches Zotero items API with q= parameter, not collection-specific iteration"

patterns-established:
  - "Lazy client property with env-var credential resolution"
  - "Retry helper with exponential backoff for Zotero API calls"

requirements-completed: [ZTR-01, ZTR-02, ZTR-03, ZTR-04, ZTR-05]

# Metrics
duration: 6min
completed: 2026-04-15
---

# Phase 4 Plan 1: Zotero Integration Module Summary

**ZoteroConfig and ObsidianConfig config models added; ZoteroArchiver implemented with pyzotero for archiving HIGH-relevance papers with metadata, AI tags, structured HTML notes, and linked PDF attachments**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-15T09:06:01Z
- **Completed:** 2026-04-15T09:12:31Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- ZoteroConfig (enabled, user_id_env, api_key_env, collection_root) and ObsidianConfig (enabled, vault_repo_url, vault_pat_env) added to AppConfig as optional fields
- Full ZoteroArchiver class (379 lines) with all ZTR-01 through ZTR-05 requirements implemented
- Retry with exponential backoff for all Zotero API calls, matching reference pattern from zotero_indexer.py
- pyzotero>=1.5 added to project dependencies

## Task Commits

Each task was committed atomically:

1. **Task 1: Add ZoteroConfig and ObsidianConfig to config models** - `146ff03` (feat)
2. **Task 2: Implement ZoteroArchiver module** - `7414ac0` (feat)

## Files Created/Modified
- `src/config/models.py` - Added ZoteroConfig and ObsidianConfig classes, both as optional fields on AppConfig
- `src/integrations/__init__.py` - Package init with lazy __getattr__ for ZoteroArchiver and ObsidianWriter
- `src/integrations/zotero.py` - Complete ZoteroArchiver: archive_papers, collection management, item creation, tags, notes, PDF attachment, dedup
- `requirements.txt` - Added pyzotero>=1.5

## Decisions Made
- Lazy pyzotero client initialization via @property defers credential validation until first API call, allowing import without env vars set
- PDF attached as linked_url rather than file upload because the pipeline runs in GitHub Actions without local PDF files
- Tags added via fetch-item-then-update pattern rather than create_tags for better compatibility across pyzotero versions
- Dedup uses Zotero items API search (q= parameter) for DOI and title matching rather than iterating collection items

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

**External services require manual configuration for Zotero archiving:**
- Set `ZOTERO_USER_ID` environment variable (from Zotero Settings -> Your User ID)
- Set `ZOTERO_API_KEY` environment variable (from Zotero Settings -> Feeds/API -> Create new private key)
- Add `zotero: { enabled: true }` to config.yaml to enable archiving

## Next Phase Readiness
- ZoteroArchiver is ready to be wired into the main pipeline (src/main.py) in a future plan
- ObsidianConfig model is in place for Plan 04-02 (Obsidian vault generation)
- The integrations package is established with lazy import pattern for both ZoteroArchiver and ObsidianWriter

## Self-Check: PASSED

All files verified present:
- src/config/models.py - FOUND
- src/integrations/__init__.py - FOUND
- src/integrations/zotero.py - FOUND
- requirements.txt - FOUND
- 04-01-SUMMARY.md - FOUND

All commits verified:
- 146ff03 (Task 1) - FOUND
- 7414ac0 (Task 2) - FOUND

---
*Phase: 04-zotero-and-obsidian-integrations*
*Completed: 2026-04-15*
