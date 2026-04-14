---
phase: 01-end-to-end-pipeline-proof
plan: 04
subsystem: delivery
tags: [feishu, webhook, jinja2, httpx, rich-text, notification]

# Dependency graph
requires:
  - phase: 01-end-to-end-pipeline-proof/01-03
    provides: "AnalyzedPaper, AnalysisResult, RelevanceTier models from search/analysis"
provides:
  - "Notifier ABC abstract base class for delivery channels"
  - "FeishuNotifier with rich message cards and tiered display"
  - "Jinja2 template for Feishu webhook JSON envelope"
  - "Message splitting logic for large digests"
affects: [pipeline-orchestration, future-notification-channels]

# Tech tracking
tech-stack:
  added: [httpx, jinja2]
  patterns: [tiered-information-density, message-splitting, rich-text-tags]

key-files:
  created:
    - src/delivery/__init__.py
    - src/delivery/base.py
    - src/delivery/feishu.py
    - templates/feishu_card.json.j2
  modified: []

key-decisions:
  - "Feishu post format (not interactive cards) to avoid requiring app registration"
  - "Jinja2 template kept minimal (JSON envelope only); formatting logic in Python for Feishu's complex nested tag arrays"
  - "28KB conservative split threshold vs 30KB Feishu limit"
  - "Lazy import of FeishuNotifier in __init__.py to avoid circular dependency at module load"

patterns-established:
  - "Notifier ABC pattern: abstract send() with papers + topic_stats, allows future channels (email, etc.)"
  - "Tiered display pattern: HIGH=full, MEDIUM=compact, LOW=minimal, controlled by RelevanceTier enum"
  - "Message splitting by byte size with MAX_CONTENT_BYTES constant"

requirements-completed: [NTFY-01, NTFY-02, NTFY-03]

# Metrics
duration: 5min
completed: 2026-04-14
---

# Phase 1 Plan 4: Feishu Notification Delivery Summary

**Feishu rich message card delivery with tiered information density, topic-grouped sections, and automatic message splitting via Jinja2 template and httpx async POST**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-14T03:29:07Z
- **Completed:** 2026-04-14T03:34:45Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Notifier ABC with abstract async send() method, ready for future channel implementations
- FeishuNotifier with three-tier display: HIGH (score + summary + contributions + applications + link), MEDIUM (score + summary + contributions + link), LOW (title + link only)
- Topic-grouped sections with stats header (total, high, medium, low counts)
- Message splitting at 28KB threshold to stay under Feishu's 30KB webhook limit
- Jinja2 template for Feishu JSON envelope with language-aware locale selection

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Notifier ABC and Jinja2 Feishu card template** - `8cd1e7c` (feat)
2. **Task 2: Create FeishuNotifier with tiered formatting and message splitting** - `f2688b7` (feat)

## Files Created/Modified
- `src/delivery/__init__.py` - Package init with lazy FeishuNotifier import
- `src/delivery/base.py` - Notifier ABC with abstract async send() method
- `src/delivery/feishu.py` - FeishuNotifier with tiered formatting, topic grouping, message splitting
- `templates/feishu_card.json.j2` - Jinja2 template for Feishu post JSON envelope

## Decisions Made
- **Feishu post format (not interactive cards):** Webhook bots can send `msg_type: "post"` rich text without app registration; interactive cards require a Feishu app
- **Minimal Jinja2 template:** Feishu's rich text format (nested arrays of tag dicts) is fragile in Jinja2 JSON templates, so formatting logic lives in Python; template handles only the JSON envelope
- **28KB split threshold:** Conservative 28KB vs 30KB Feishu limit to account for JSON serialization overhead and UTF-8 encoding variance
- **Lazy import pattern:** `__init__.py` uses `__getattr__` for FeishuNotifier so importing the delivery package does not fail when feishu.py is not yet created

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed circular import in delivery/__init__.py**
- **Found during:** Task 1 (Notifier ABC creation)
- **Issue:** `__init__.py` eagerly imported FeishuNotifier from feishu.py, which did not exist yet, causing ModuleNotFoundError in verification
- **Fix:** Changed to lazy import via `__getattr__`, importing only Notifier ABC eagerly
- **Files modified:** src/delivery/__init__.py
- **Verification:** `from src.delivery.base import Notifier` succeeds without feishu.py
- **Committed in:** 8cd1e7c (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minor fix necessary for module loading order. No scope creep.

## Issues Encountered
None - all verifications passed on first or second attempt after the import fix.

## User Setup Required
None - no external service configuration required beyond the Feishu webhook URL (configured via environment variable).

## Next Phase Readiness
- Delivery layer complete, ready for pipeline orchestration (Plan 05)
- FeishuNotifier.send() interface matches Notifier ABC contract
- Message format validated against Feishu webhook JSON structure
- Topic stats dict interface aligned with upstream analysis output

---
*Phase: 01-end-to-end-pipeline-proof*
*Completed: 2026-04-14*

## Self-Check: PASSED
- src/delivery/__init__.py: FOUND
- src/delivery/base.py: FOUND
- src/delivery/feishu.py: FOUND
- templates/feishu_card.json.j2: FOUND
- Commit 8cd1e7c: FOUND
- Commit f2688b7: FOUND
