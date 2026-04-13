# Pitfalls Research

**Domain:** Daily academic literature push system
**Researched:** 2026-04-13
**Confidence:** HIGH

## Critical Pitfalls

### 1. Academic API Rate Limits
**Warning signs:** HTTP 429 responses, truncated results, inconsistent daily output
**Prevention:**
- Implement exponential backoff with `tenacity` for all API calls
- Respect per-source rate limits: arXiv (1 req/s), PubMed (3 req/s without key, 10/s with), OpenAlex (10 req/s polite pool), Semantic Scholar (1 req/s unauthenticated)
- Add configurable delays between source queries
- Batch API calls where possible
**Phase:** Search layer implementation (Phase 1)

### 2. Deduplication Failures
**Warning signs:** Same paper pushed multiple times, user frustration, notification spam
**Prevention:**
- Primary dedup by DOI (most reliable identifier)
- Fallback dedup by normalized title hash when DOI missing
- Normalize DOIs (lowercase, strip prefixes like "https://doi.org/")
- Track seen papers in persistent state file across runs
**Phase:** Search layer + State management (Phase 1)

### 3. PDF Fetch Brittleness
**Warning signs:** Frequent download failures, timeout errors, corrupted PDFs
**Prevention:**
- Never assume PDF is available — always have abstract fallback
- Set reasonable timeouts (30s per PDF)
- Validate downloaded content (check PDF magic bytes, not just HTTP 200)
- Don't use Selenium/browser automation — too brittle for CI environment
- Only fetch from known open-access sources
**Phase:** Fetch layer implementation (Phase 2)

### 4. Claude API Cost Explosion
**Warning signs:** Unexpectedly high API bills, analysis taking too long
**Prevention:**
- Use tiered analysis: only send high-relevance papers for full analysis
- Set max paper count per run (configurable, e.g., top 50)
- Use prompt caching where possible
- Monitor token usage and set budgets
- Consider using Haiku for relevance scoring, Sonnet/Opus for deep analysis only
- Send batched requests where possible
**Phase:** Analysis layer implementation (Phase 2)

### 5. GitHub Actions Resource Limits
**Warning signs:** Workflow timeout (>6h), out-of-memory errors
**Prevention:**
- Keep total pipeline under 30 minutes for typical runs
- Limit concurrent downloads (max 5-10 parallel)
- Don't store large files in the repo — use artifacts or external storage for PDFs
- Stream API responses instead of buffering everything in memory
**Phase:** All phases (architecture constraint)

### 6. Configuration Complexity Barrier
**Warning signs:** Users give up during setup, misconfigured searches, support requests
**Prevention:**
- Provide a well-documented `config.example.yaml` with sensible defaults
- Validate config on startup with clear error messages
- Minimize required configuration: search keywords + at least one notification channel
- Make everything else optional with sensible defaults
- Provide setup guide in README with step-by-step instructions
**Phase:** Config layer + README (Phase 1)

### 7. Feishu Webhook Message Format Errors
**Warning signs:** Messages not rendering, rejected by API, rate limited
**Prevention:**
- Test Feishu card format against actual API before deploying
- Feishu has strict message size limits (~30KB per message)
- Split large digests into multiple messages if needed
- Use interactive card elements for "Save to Zotero" buttons
- Test with Feishu test bot before production
**Phase:** Feishu notifier implementation (Phase 3)

### 8. SMTP Email Deliverability
**Warning signs:** Emails land in spam, rejected by recipient servers
**Prevention:**
- Recommend using established SMTP services (Gmail with app password, SendGrid, etc.)
- Include plain-text alternative alongside HTML
- Set proper From/Reply-To headers
- Don't include too many links (spam trigger)
**Phase:** Email notifier implementation (Phase 3)

### 9. Zotero API Rate Limiting and Conflicts
**Warning signs:** Duplicate items in Zotero, API errors, sync conflicts
**Prevention:**
- Check for existing items before creating (search by DOI/title)
- Use Zotero's built-in duplicate detection
- Respect API rate limits (ziur.org/docs/dev/api)
- Handle version conflicts gracefully
**Phase:** Zotero integration (Phase 4)

### 10. Obsidian Vault Git Push Conflicts
**Warning signs:** Merge conflicts in vault repo, overwritten notes, failed pushes
**Prevention:**
- Use a dedicated branch for automated commits (e.g., `auto/inbox`)
- Never modify existing notes — only add new ones
- Include timestamps in filenames to avoid collisions
- Force-push only to the automation branch, never to user's main branch
**Phase:** Obsidian integration (Phase 4)

### 11. State File Corruption
**Warning signs:** Duplicate papers after state reset, missing state file on first run
**Prevention:**
- Initialize state file if missing (first run detection)
- Write state atomically (write to temp file, then rename)
- Keep state file small (prune entries older than 90 days)
- Consider committing state to repo for persistence across workflow runs
**Phase:** State management (Phase 1)

### 12. Cross-Source Data Model Inconsistencies
**Warning signs:** Missing fields in normalized Paper model, None errors downstream
**Prevention:**
- Make most Paper fields Optional with defaults
- Validate at normalization boundary (each source adapter)
- Don't assume any field exists beyond title + at least one identifier
- Log warnings for papers with missing critical fields
**Phase:** Data models + Search adapters (Phase 1)

---
*Pitfalls research for: Daily Literature Push System*
*Researched: 2026-04-13*
