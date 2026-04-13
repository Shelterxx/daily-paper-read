# Stack Research

**Domain:** Daily academic literature push system (GitHub Actions, multi-source search, AI analysis, multi-channel notifications)
**Researched:** 2026-04-13
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | >=3.10 | Runtime language | GitHub Actions runners ship Python 3.10+. Using 3.10 as floor gives access to match statements, better type unions, and modern stdlib features. The `anthropic` SDK requires >=3.9; 3.10+ avoids edge-case compatibility issues with type hints and pydantic v2. |
| `anthropic` | >=0.94.0 | Claude API SDK for AI analysis pipeline | Official Anthropic Python SDK. Version 0.94.0 (2026-04-10) is current. Supports streaming, tool use, structured output, and message batching. Replaces the reference project's use of OpenAI SDK -- the new system targets Claude, not OpenAI. Use `anthropic.Anthropic()` client with `messages.create()` for relevance scoring, summary generation, deep analysis, and comparative analysis. |
| `pydantic` | >=2.7 | Data validation and serialization | v2 is a ground-up rewrite with Rust core, 5-50x faster than v1. Use for all data models: Paper, SearchResult, AnalysisResult, NotificationPayload. BaseModel for schema definition, model_validator for cross-field logic. Pydantic v2 is the current stable line (v2.12.x as of 2026-04). |
| `pydantic-settings` | >=2.2 | YAML config loading with validation | Extends pydantic with settings management. v2.0+ has native YAML support via `yaml_file` source. Define a `Settings` model with typed fields, defaults, and env-variable overrides. Maps directly to the project's YAML config + GitHub Secrets pattern: YAML file for user preferences, env vars for API keys. |
| `httpx` | >=0.27 | Async HTTP client for all API calls | Supports both sync and async, HTTP/1.1 and HTTP/2. One client handles arXiv API, OpenAlex, Semantic Scholar, PubMed, DOI resolution, and Feishu webhooks. Prefer over `aiohttp` because: simpler API surface, sync+async in one package, HTTP/2 for better multiplexing with multiple academic APIs. Use `httpx.AsyncClient` for all pipeline HTTP calls. |
| `PyYAML` | >=6.0 | Parse user YAML configuration files | Standard YAML parser for Python. Reads the user's `config.yaml` defining search queries, research interests, notification preferences. Works with pydantic-settings for validated config loading. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `arxiv` | >=2.4.0 | arXiv API client | For arXiv search. Version 2.4.0 (2026-01-05) is the official Python client wrapping arXiv's REST API. Supports paginated search, category filtering, and PDF URL extraction. Use as primary arXiv interface instead of raw feedparser -- the library handles rate limiting and pagination internally. |
| `feedparser` | >=6.0.11 | Atom/RSS feed parsing | Fallback for arXiv RSS feeds and any source that exposes Atom/RSS. The reference paperRead project uses it for arXiv category feeds. Keep as fallback even when using the `arxiv` library, since some arXiv edge cases (e.g., bulk category feeds) work better via RSS. |
| `pyalex` | >=0.5 | OpenAlex API client | For OpenAlex search. Thin wrapper around OpenAlex REST API. OpenAlex is free, no API key required (just polite pool with email). Covers papers, authors, institutions, concepts. Use as primary broad-search source because it aggregates from arXiv, PubMed, Crossref, MAG, and more. |
| `pyzotero` | >=1.6.11 | Zotero API client | For optional Zotero archiving. Version 1.6.11 (2025-03-20). Handles item creation, tagging, note attachment, PDF upload, and collection management. The reference paperRead project already uses it successfully. Wrap behind a ZoteroInterface so users without Zotero can skip it. |
| `PyMuPDF` (aka `fitz`) | >=1.24 | PDF text extraction | For extracting text from fetched PDFs when AI analysis needs full-text content beyond abstracts. Fast, C-based, works well in GitHub Actions runners. Only needed when the analysis pipeline processes PDF content, not just metadata/abstracts. |
| `beautifulsoup4` | >=4.12 | HTML parsing for web scraping | For scraping paper metadata from publisher pages when APIs return incomplete data. Also useful for parsing ScienceDirect article pages and DOI resolution redirects. The reference projects use it for this purpose. |
| `Jinja2` | >=3.1 | Template engine for notification formatting | For generating Feishu rich message cards, email HTML bodies, and Obsidian markdown files. Template-based formatting is cleaner than string concatenation for complex notification payloads. Use for all output formatting. |
| `semantic-scholar` | >=0.8.0 | Semantic Scholar API client | Optional secondary search source. Semantic Scholar provides paper search, citation data, and relevance ranking via their free API. Useful for citation-graph-based discovery (papers citing or cited by known relevant work). |
| `bibtexparser` | >=1.4 | BibTeX parsing | For importing BibTeX reference lists that users may provide as seed corpora. Also handles BibTeX output for Zotero integration. Only needed if users want to import existing reference lists. |
| `tenacity` | >=8.2 | Retry logic with exponential backoff | For all external API calls. The reference paperRead project implements custom retry logic -- use `tenacity` instead for cleaner code. Configurable stop conditions, wait strategies, and retry predicates (e.g., retry on HTTP 429, 500, 502, 503). |

### Standard Library (No Install Needed)

| Module | Purpose | Notes |
|--------|---------|-------|
| `smtplib` + `email.mime` | Email notification via SMTP | Standard library, zero dependencies. Use `email.mime.multipart.MIMEMultipart` for HTML+plain email digests. SMTP credentials come from GitHub Secrets. |
| `json` | State persistence between runs | Track seen papers, last-run timestamps, deduplication state. Write to `state/` directory in the repo. |
| `pathlib` | File path handling | Modern path API. Use throughout for file I/O. |
| `logging` | Structured logging | Configure for GitHub Actions console output. Use `structlog` only if richer structured logging is needed. |
| `hashlib` | Paper deduplication via DOI/title hashing | Generate deterministic hashes for dedup across sources. |
| `asyncio` | Async pipeline orchestration | Use `asyncio.gather()` for parallel API calls to multiple sources. The httpx AsyncClient integrates natively. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` + `pytest-asyncio` | Testing | Test async pipeline components. Mock external APIs with `pytest-httpx` or `respx`. |
| `ruff` | Linting + formatting | Single tool replacing flake8, isort, black. Fast, opinionated. Run in CI. |
| `mypy` | Type checking | Valuable with pydantic models. Use `--strict` for core data models. |
| `pre-commit` | Git hook management | Run ruff, mypy, and YAML validation before commits. |
| `act` | Local GitHub Actions testing | Run workflows locally before pushing. Essential for developing GitHub Actions workflows without burning CI minutes. |

## Installation

```bash
# Core (always needed)
pip install anthropic>=0.94.0 pydantic>=2.7 pydantic-settings>=2.2 httpx>=0.27 PyYAML>=6.0

# Academic search sources (install all, graceful degradation if any missing)
pip install arxiv>=2.4.0 feedparser>=6.0.11 pyalex>=0.5 semantic-scholar>=0.8.0

# Notification and output
pip install Jinja2>=3.1

# Optional integrations
pip install pyzotero>=1.6.11    # Zotero archiving
pip install PyMuPDF>=1.24       # PDF text extraction
pip install beautifulsoup4>=4.12  # Web scraping fallback
pip install bibtexparser>=1.4   # BibTeX import
pip install tenacity>=8.2       # Retry logic

# Dev dependencies
pip install -D pytest pytest-asyncio pytest-httpx ruff mypy pre-commit
```

Consolidated `requirements.txt` for GitHub Actions:

```
anthropic>=0.94.0
pydantic>=2.7
pydantic-settings>=2.2
httpx>=0.27
PyYAML>=6.0
arxiv>=2.4.0
feedparser>=6.0.11
pyalex>=0.5
semantic-scholar>=0.8.0
Jinja2>=3.1
pyzotero>=1.6.11
PyMuPDF>=1.24
beautifulsoup4>=4.12
tenacity>=8.2
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `httpx` | `aiohttp` | If the pipeline needs extreme concurrency (100+ simultaneous connections) or websocket support. aiohttp has slightly better raw throughput for pure async workloads. But httpx is simpler, supports sync+async, and has HTTP/2 -- better for this project's ~5-20 concurrent API calls. |
| `anthropic` SDK | `openai` SDK (with base_url) | Only if you need a single codebase that switches between Claude and OpenAI models. The reference paperRead project uses OpenAI SDK with configurable base_url. But for a Claude-first system, the native SDK is cleaner and has first-class support for Claude-specific features (extended thinking, tool use). |
| `pydantic` v2 | `dataclasses` + manual validation | Only for trivial scripts. Pydantic v2's Rust core is fast enough that overhead is negligible, and the validation + serialization + settings management are critical for a config-driven system. |
| `arxiv` library | Raw arXiv API via `httpx` | If you need search features the library doesn't expose. The `arxiv` library wraps the REST API cleanly and handles pagination/rate-limiting -- use it unless you hit a specific limitation. |
| `pyalex` | Raw OpenAlex API via `httpx` | If pyalex lacks a feature you need. pyalex is very thin (minimal abstraction), so the overhead is negligible. Use it for the convenience of constructed filter queries. |
| `Jinja2` | Python f-strings | Only for trivial single-line formatting. Any notification template with conditionals, loops, or reusable components benefits from Jinja2's template inheritance and filters. |
| `tenacity` | Custom retry decorator | Only if you want zero dependencies. tenacity is battle-tested, handles edge cases (jitter, retry-only-specific-exceptions), and is cleaner than hand-rolling retry logic. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `openai` SDK | The project targets Claude API, not OpenAI. The reference paperRead project uses OpenAI SDK, but this system should use the native Anthropic SDK. Mixing OpenAI SDK to call Claude via a proxy adds unnecessary complexity and loses access to Claude-specific features (extended thinking, tool use, message batching). | `anthropic` >=0.94.0 |
| `aiohttp` as primary HTTP client | Adds a second async HTTP library for no clear benefit. aiohttp is more complex to use correctly (session lifecycle, connector management) and provides no meaningful performance advantage at this project's scale (~5-20 concurrent calls). | `httpx` with `AsyncClient` |
| `requests` library | Synchronous only, no HTTP/2, blocks the event loop. The reference projects use requests, but this system should use httpx for both sync and async needs. httpx's sync API is a drop-in replacement for requests. | `httpx` (sync or async) |
| `selenium` / `playwright` for PDF fetching | The reference sciencedirect-live-session-fetcher uses Selenium, but browser automation is heavy, slow, and brittle in GitHub Actions. It also raises ethical/legal concerns about bypassing publisher access controls. The system should only fetch legally accessible PDFs via direct HTTP. | `httpx` direct download for open-access PDFs |
| `feedparser` as primary arXiv interface | feedparser is a generic RSS/Atom parser. The `arxiv` library provides a purpose-built client with proper pagination, rate limiting, and structured results. Keep feedparser as a fallback, not the primary interface. | `arxiv` library >=2.4.0 |
| `pydantic` v1 | v1 is deprecated. v2 is a complete rewrite with Rust core, different API, and better performance. New projects must use v2. Migration guides exist for the reference code. | `pydantic` v2 >=2.7 |
| `xml.etree` / `lxml` for API parsing | Most modern academic APIs (arXiv REST, OpenAlex, Semantic Scholar) return JSON. Only PubMed E-utilities uses XML. If PubMed XML parsing is needed, use `xml.etree.ElementTree` from stdlib rather than adding `lxml` as a dependency. | `httpx` JSON responses; stdlib `xml.etree` for PubMed only |
| Custom notification SDKs (e.g., `feishu-sdk`) | Feishu bot webhooks are simple HTTP POST with JSON payloads. The reference notifier.py proves this works with plain `requests.post()`. Using httpx avoids an extra dependency and gives more control over the payload format. | `httpx` POST to webhook URLs |
| `structlog` | Adds complexity for minimal benefit in a GitHub Actions context where logs go to console. stdlib `logging` with formatted output is sufficient. | stdlib `logging` |
| `celery` / `dramatiq` task queues | The pipeline runs as a single GitHub Actions workflow, not as a long-running service. Task queues add infrastructure overhead for no benefit. Use simple `asyncio.gather()` for parallelism. | `asyncio` for parallel execution |

## Stack Patterns by Variant

**If PDF full-text analysis is not needed (abstract-only pipeline):**
- Drop `PyMuPDF` and `beautifulsoup4`
- Analysis uses only title + abstract from API responses
- Simpler, faster, fewer failure points

**If Zotero integration is not needed:**
- Drop `pyzotero`
- All notification and Obsidian features work independently
- Users can add Zotero later by installing the library and configuring credentials

**If only arXiv is needed as a source:**
- Keep `arxiv` library, drop `pyalex` and `semantic-scholar`
- Reduces API surface and configuration complexity
- Good for MVP / initial deployment

**If running locally instead of GitHub Actions:**
- Same stack works; just change the entry point from GitHub Actions workflow to a local script
- Config can use `.env` file instead of GitHub Secrets
- Consider `schedule` library for local cron-like behavior, or just use system cron

**If adding new academic sources later (e.g., DBLP, Scopus):**
- Implement a `SearchSource` abstract base class with `search()`, `normalize()` methods
- Each source is a thin adapter: source API -> normalized `Paper` model
- Add the source-specific library to requirements only if a good client exists; otherwise use raw httpx

## Version Compatibility

| Package | Requires | Notes |
|---------|----------|-------|
| `anthropic` >=0.94.0 | Python >=3.9 | Will not work on Python 3.8. This is why the floor is Python 3.10. |
| `pydantic` v2 | Python >=3.8 | v2.7+ recommended for bug fixes and YAML settings support |
| `pydantic-settings` >=2.2 | pydantic v2 | Strictly requires pydantic v2, not compatible with v1 |
| `arxiv` >=2.4.0 | Python >=3.9 | Uses modern type hints internally |
| `httpx` >=0.27 | Python >=3.8 | HTTP/2 requires `h2` package (auto-installed) |
| `PyMuPDF` >=1.24 | Python >=3.8 | C extension, ships pre-built wheels for most platforms |
| `pyzotero` >=1.6.11 | Python >=3.7 | No known conflicts with other stack libraries |
| `pyalex` >=0.5 | Python >=3.8 | Thin wrapper, minimal dependencies |

**GitHub Actions runner compatibility:** Ubuntu runners include Python 3.10, 3.11, 3.12, 3.13. Pin to 3.12 in the workflow for stability.

**Python 3.13 note:** All listed packages work on 3.13 as of 2026-04. However, pin to 3.12 in CI for predictability.

## Sources

- PyPI (`pypi.org/project/anthropic`) -- verified anthropic 0.94.0 release date and Python requirement
- PyPI (`pypi.org/project/arxiv`) -- verified arxiv 2.4.0 release date 2026-01-05
- PyPI (`pypi.org/project/pyzotero`) -- verified pyzotero 1.6.11 as latest (not 1.11.0 which is the docs site version)
- PyPI (`pypi.org/project/pydantic`) -- verified pydantic v2 stable line
- `pypi.org/project/pydantic-settings` -- verified v2.0+ has native YAML support
- Reference project `paperRead/paperRead-main/requirements.txt` -- baseline dependency list
- Reference project `paperRead/paperRead-main/notifier.py` -- Feishu webhook implementation pattern
- Reference project `paperRead/paperRead-main/main.py` -- OpenAI SDK usage pattern (superseded by Anthropic SDK)
- OpenAlex documentation (`docs.openalex.org`) -- free API, no key required, polite pool with email
- Feishu Open Platform docs -- webhook message format verified against reference implementation
- Confidence: HIGH for all core stack items (verified against PyPI + official docs); MEDIUM for semantic-scholar library version (less actively maintained)

---
*Stack research for: Daily Literature Push System*
*Researched: 2026-04-13*
