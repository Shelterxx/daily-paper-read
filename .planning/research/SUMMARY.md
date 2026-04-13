# Project Research Summary

**Project:** Daily Academic Literature Push System
**Domain:** Developer tooling / academic workflow automation (GitHub Actions pipeline)
**Researched:** 2026-04-13
**Confidence:** HIGH

## Executive Summary

This project is a daily academic literature push system that runs as a GitHub Actions pipeline. It searches multiple academic databases (arXiv, PubMed, OpenAlex, Semantic Scholar), deduplicates results, uses Claude AI to score relevance and generate summaries, then delivers tiered notifications via Feishu, email, and optional Zotero/Obsidian integrations. Experts build this kind of system as a straightforward ETL pipeline with an AI analysis stage -- there are no novel architectural challenges, but execution quality in API integration, deduplication, and prompt engineering determines whether the tool is genuinely useful or just noisy.

The recommended approach is a six-stage pipeline architecture (Config -> Search -> Fetch -> Analyze -> Deliver -> State) built in Python with `httpx` for async HTTP, `pydantic` for data validation, and the `anthropic` SDK for Claude-powered analysis. The system should launch with arXiv as the sole search source and Feishu as the sole notification channel, then expand to additional sources and channels in later phases. This "narrow first, expand later" strategy directly addresses the top pitfall: API integration complexity compounds quickly when multiple sources are involved.

The key risks are Claude API cost explosion (mitigated by tiered analysis -- only high-relevance papers get full analysis), academic API rate limiting (mitigated by `tenacity` retry logic and per-source rate awareness), and PDF fetch brittleness (mitigated by always having an abstract-only fallback). The biggest non-technical risk is configuration complexity creating a barrier to adoption -- solved by shipping a well-documented `config.example.yaml` with sensible defaults and validating config on startup with clear error messages.

## Key Findings

### Recommended Stack

Python 3.10+ is the runtime, pinned to 3.12 in CI. The core stack is `anthropic` SDK (>=0.94.0) for Claude analysis, `httpx` (>=0.27) as the single HTTP client for all API calls, `pydantic` v2 (>=2.7) for data models and config validation, and `pydantic-settings` (>=2.2) for YAML config loading. The reference `paperRead` project uses the OpenAI SDK, but this system targets Claude and should use the native Anthropic SDK for first-class access to Claude-specific features.

**Core technologies:**
- `anthropic` >=0.94.0: Claude API for relevance scoring, summaries, deep analysis -- native SDK with streaming and structured output
- `pydantic` v2 >=2.7: All data models (Paper, SearchResult, AnalysisResult) and config validation with Rust-core performance
- `httpx` >=0.27: Single async HTTP client for arXiv, PubMed, OpenAlex, DOI resolution, Feishu webhooks -- replaces requests/aiohttp
- `arxiv` >=2.4.0: Purpose-built arXiv client with pagination and rate limiting -- primary search source for MVP
- `Jinja2` >=3.1: All output formatting (Feishu cards, email HTML, Obsidian markdown) via templates
- `tenacity` >=8.2: Retry logic with exponential backoff for all external API calls

### Expected Features

The system has clear feature tiers. Table-stakes features (multi-source search, configurable queries, deduplication, AI relevance scoring, tiered notifications, YAML config, GitHub Actions deployment) form the MVP. Differentiators (deep analysis, comparative analysis, Zotero integration, Obsidian vault generation, trend detection) are layered on after the core pipeline works reliably.

**Must have (table stakes):**
- Multi-source search with configurable queries in YAML -- users expect broad coverage
- Deduplication across sources by DOI/title hash -- prevents notification spam
- AI relevance scoring and summary generation -- the core value proposition
- Tiered content delivery (full analysis / summary / title-only based on score) -- respects attention
- Feishu rich message notification -- primary delivery channel
- YAML config + GitHub Secrets + quick fork-and-deploy -- adoption depends on easy setup

**Should have (competitive):**
- Deep analysis + comparative analysis for high-relevance papers -- differentiates from simple RSS feeds
- Zotero one-click archiving with auto-tagging -- integrates into existing researcher workflows
- Obsidian daily notes + per-paper literature cards -- builds a personal knowledge base over time
- Seen-paper tracking across runs -- prevents redundant notifications

**Defer (v2+):**
- Personalized relevance learning from Zotero library / Obsidian notes -- requires persistent ML state
- Trend detection across multiple search runs -- needs accumulated data over time
- Additional notification channels (Slack, Discord, Telegram) -- Feishu first, others by demand

### Architecture Approach

A six-stage pipeline running in a single GitHub Actions workflow. Each stage transforms data and passes it downstream: Config loads YAML + secrets, Search queries sources in parallel via `asyncio.gather()`, Fetch downloads open-access PDFs with abstract fallback, Analyze calls Claude API with tiered prompts, Deliver pushes to notification channels in parallel, and State tracks seen papers across runs. Source adapters implement a common `SearchSource` ABC so adding a new source requires only a new adapter class. All output uses Jinja2 templates so users can customize formatting without touching Python code.

**Major components:**
1. Config Layer -- pydantic-settings models loading `config.yaml` + environment variables
2. Search Layer -- parallel source adapters (arXiv, PubMed, OpenAlex, DOI) behind `SearchSource` ABC, with deduplication
3. Fetch Layer -- PDF download with graceful degradation to abstract-only
4. Analysis Layer -- Claude API with tiered prompts (relevance score, summary, deep analysis, comparative)
5. Delivery Layer -- parallel notifiers (Feishu webhook, SMTP email, optional Zotero API, optional Obsidian git push)
6. State Management -- flat JSON file tracking seen papers by DOI/title hash

### Critical Pitfalls

1. **Academic API rate limits** -- Use `tenacity` for exponential backoff; respect per-source limits (arXiv 1 req/s, PubMed 3 req/s, OpenAlex 10 req/s polite pool). This is the most likely cause of production failures.
2. **Deduplication failures causing notification spam** -- Primary dedup by DOI, fallback by normalized title hash. Normalize DOIs aggressively (lowercase, strip prefixes). Track seen papers in persistent state file.
3. **Claude API cost explosion** -- Tiered analysis is mandatory: only papers scoring >=7 get full deep + comparative analysis. Set configurable max paper count per run (suggest 50). Consider Haiku for scoring, Sonnet for deep analysis.
4. **PDF fetch brittleness** -- Always have abstract fallback. Validate PDF magic bytes, not just HTTP 200. Set 30s timeouts. Never use browser automation. Only fetch from known open-access sources.
5. **GitHub Actions resource limits** -- Keep pipeline under 30 minutes. Limit concurrent downloads to 5-10. Stream API responses instead of buffering everything. Don't store large files in the repo.
6. **Configuration complexity barrier** -- Ship `config.example.yaml` with sensible defaults. Validate on startup with clear error messages. Minimum required config: search keywords + one notification channel.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation + Single Source + Single Channel
**Rationale:** Get the full pipeline working end-to-end with the simplest possible configuration before adding complexity. One source (arXiv) and one channel (Feishu) prove the entire architecture works.
**Delivers:** A deployable system that searches arXiv daily, scores relevance with Claude, and pushes Feishu notifications.
**Addresses:** Config layer, data models, state management, arXiv source adapter, analysis pipeline (scoring + summary), Feishu notifier, GitHub Actions workflow.
**Avoids:** API rate limit issues (single source is easy to manage), configuration complexity (minimal config needed), cost explosion (single source produces manageable paper count).

### Phase 2: Multi-Source Search + PDF Fetch
**Rationale:** With the pipeline proven, expand to multiple sources. PDF fetch is added here because it requires per-source URL patterns and error handling that benefits from having multiple sources already working.
**Delivers:** Broad academic coverage from arXiv, PubMed, OpenAlex, Semantic Scholar. Open-access PDF download with abstract fallback. Deduplication across sources.
**Uses:** `pyalex`, `httpx` for PubMed E-utilities, `semantic-scholar` library, `PyMuPDF` for text extraction, `tenacity` for retry logic.
**Implements:** Search layer source adapters, deduplication logic, fetch layer with PDF download.
**Avoids:** Rate limiting (implement `tenacity` from the start), deduplication failures (DOI + title hash from day one).

### Phase 3: Advanced Analysis + Email Notifications
**Rationale:** Deep and comparative analysis are high-value features that depend on a working pipeline. Email is the second notification channel and requires SMTP configuration.
**Delivers:** Deep methodology analysis and comparative analysis for high-relevance papers. HTML email digest as alternative/supplement to Feishu.
**Uses:** Claude API with advanced prompts, `Jinja2` for email templates, `smtplib` for email delivery.
**Implements:** Tiered analysis pipeline, email notifier with HTML + plain-text.
**Avoids:** Claude API cost explosion (tiered analysis limits token usage per run).

### Phase 4: Zotero + Obsidian Integrations
**Rationale:** These are optional integrations that add significant value for power users but are not required for the core workflow. Both require additional user setup (Zotero account, Obsidian vault repo).
**Delivers:** One-click Zotero archiving with auto-tagging and PDF attachment. Daily Obsidian notes and per-paper literature cards pushed to a separate vault repo.
**Uses:** `pyzotero` for Zotero API, `git` commands for Obsidian vault push, `Jinja2` for markdown templates.
**Implements:** Zotero notifier, Obsidian notifier.
**Avoids:** Zotero API conflicts (check existing items before creating), Obsidian git push conflicts (use dedicated `auto/inbox` branch, never modify existing notes).

### Phase Ordering Rationale

- Phase 1 proves the full pipeline works end-to-end before any complexity is added. This avoids the common failure mode of building all source adapters before the analysis/delivery pipeline works.
- Phase 2 expands horizontally (more sources) while the core pipeline is already proven. Deduplication and rate limiting are solved here because they only matter with multiple sources.
- Phase 3 deepens the AI value proposition (advanced analysis) and adds the second notification channel. This order ensures the basic scoring and summary pipeline is solid before adding more complex prompts.
- Phase 4 adds optional integrations last because they require additional user setup and are not needed for the core value proposition.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Multi-Source Search):** Each source API (PubMed E-utilities, OpenAlex, Semantic Scholar) has unique query syntax, pagination, and rate limit behavior. Research specific query patterns during planning.
- **Phase 3 (Advanced Analysis):** Prompt engineering for deep analysis and comparative analysis needs iteration. The prompt templates significantly affect output quality.
- **Phase 4 (Obsidian Integration):** Git automation within GitHub Actions (pushing to a separate repo) requires specific token configuration and branch management patterns.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** arXiv library, Feishu webhook, pydantic config, GitHub Actions cron -- all well-documented with reference implementations in the existing `paperRead` project.
- **Phase 4 (Zotero Integration):** `pyzotero` is well-documented and the reference project already demonstrates the pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All packages verified against PyPI with current versions. Core stack (anthropic, pydantic, httpx) is battle-tested. Reference project validates feasibility. |
| Features | HIGH | Feature set is clearly defined with reference implementations. Complexity assessments are based on known API surfaces. Anti-features prevent scope creep. |
| Architecture | HIGH | Pipeline pattern is straightforward. Six-stage decomposition is clean with clear interfaces. Reference paperRead project validates the approach. |
| Pitfalls | HIGH | All pitfalls identified from known API behaviors and reference project experience. Prevention strategies are concrete and implementable. |

**Overall confidence:** HIGH

### Gaps to Address

- **PubMed E-utilities XML parsing:** PubMed returns XML while most other sources return JSON. The exact parsing approach needs validation during Phase 2 planning -- whether stdlib `xml.etree` is sufficient or if additional handling is needed.
- **Claude prompt quality:** The analysis pipeline's value depends heavily on prompt engineering. Research identified the architecture but not specific prompts. Plan prompt iteration cycles during Phase 1 and Phase 3.
- **Feishu card format specifics:** The reference project demonstrates basic webhook usage, but rich interactive cards with "Save to Zotero" buttons need testing against actual Feishu API during Phase 1.
- **OpenAlex "polite pool" configuration:** OpenAlex recommends providing an email for faster rate limits. The exact configuration approach (email in config vs. hardcoded) needs a decision during Phase 2.
- **Obsidian vault repo authentication:** Pushing to a separate repository from within GitHub Actions requires a PAT or deploy key. The specific authentication pattern and token management need resolution during Phase 4.

## Sources

### Primary (HIGH confidence)
- PyPI package pages -- verified versions and dependencies for anthropic, arxiv, pydantic, pydantic-settings, httpx, pyzotero, pyalex, tenacity
- Reference project `paperRead/paperRead-main/` -- baseline implementation for Feishu notifications, Zotero integration, arXiv search, and OpenAI SDK usage pattern
- OpenAlex documentation (docs.openalex.org) -- free API, polite pool, no key required
- Anthropic SDK documentation -- Claude API patterns for analysis pipeline
- Feishu Open Platform docs -- webhook message format verified against reference implementation

### Secondary (MEDIUM confidence)
- `semantic-scholar` library documentation -- less actively maintained than other stack libraries; version compatibility verified on PyPI
- PubMed E-utilities documentation -- API behavior validated, XML parsing approach inferred
- GitHub Actions documentation -- resource limits, cron scheduling, secrets management

### Tertiary (LOW confidence)
- PyMuPDF text extraction quality for academic PDFs -- inferred from library capabilities, needs validation with actual papers
- Claude API token usage estimates for analysis pipeline -- depends on prompt design and paper count, not precisely predictable

---
*Research completed: 2026-04-13*
*Ready for roadmap: yes*
