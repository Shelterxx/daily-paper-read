# Architecture Research

**Domain:** Daily academic literature push system
**Researched:** 2026-04-13
**Confidence:** HIGH

## System Overview

The system is a **pipeline architecture** running in GitHub Actions. Each stage transforms data and passes it to the next. The pipeline is orchestrated by a main runner script triggered by cron or manual dispatch.

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│   Config     │───→│   Search      │───→│   Fetch      │───→│   Analyze    │───→│   Deliver     │
│   Loader     │    │   (parallel)  │    │   (parallel)  │    │   (AI/LLM)   │    │   (parallel)  │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────────┘    └──────────────┘
     YAML              ↑                    ↑                    ↑                   ↑
   + Secrets      Source adapters       PDF fetchers        Claude API        Notifiers +
                   (arXiv, PubMed,     (per source)        analysis chain     Zotero + Obsidian
                   OpenAlex, DOI)
```

## Component Boundaries

### 1. Config Layer
**Responsibility:** Load and validate all user configuration
- Reads `config.yaml` (search queries, preferences, notification settings)
- Reads environment variables / GitHub Secrets (API keys, tokens)
- Validates via pydantic-settings models
- Outputs a typed `Config` object consumed by all other components

**Interfaces:**
- Input: `config.yaml` file + environment variables
- Output: `Config` pydantic model

### 2. Search Layer (Source Adapters)
**Responsibility:** Query multiple academic sources, normalize results
- Each source (arXiv, PubMed, OpenAlex, DOI, Semantic Scholar) has an adapter
- All adapters implement a common `SearchSource` interface
- Search runs in parallel via `asyncio.gather()`
- Results normalized to a unified `Paper` model

**Interfaces:**
- Input: `SearchQuery` (from Config)
- Output: `list[Paper]` (deduplicated, normalized)

**Abstract interface:**
```python
class SearchSource(ABC):
    async def search(self, query: SearchQuery) -> list[Paper]: ...
    def normalize(self, raw_result) -> Paper: ...
```

**Source adapters:**
| Adapter | Library/API | Output |
|---------|-------------|--------|
| ArxivSource | `arxiv` library | Paper with arXiv ID, PDF URL |
| PubMedSource | PubMed E-utilities via `httpx` | Paper with PMID, PMCID |
| OpenAlexSource | `pyalex` | Paper with DOI, OpenAlex ID |
| SemanticScholarSource | `semantic-scholar` or httpx | Paper with S2 ID, citations |
| DOIResolver | httpx + content negotiation | Paper with DOI, redirect URL |

### 3. Fetch Layer
**Responsibility:** Download PDFs and extract text for analysis
- Attempts PDF download for each paper (open access only)
- Falls back gracefully to abstract-only if PDF unavailable
- Text extraction via PyMuPDF for downloaded PDFs

**Interfaces:**
- Input: `list[Paper]` (with source URLs)
- Output: `list[Paper]` (enriched with `full_text` or `abstract_only` flag)

**Fetch strategy per source:**
| Source | PDF URL Pattern | Method |
|--------|----------------|--------|
| arXiv | `arxiv.org/pdf/{id}` | Direct HTTP download |
| PubMed Central | `ncbi.nlm.nih.gov/pmc/articles/{id}/pdf/` | Direct HTTP download |
| DOI-resolved OA | Unpaywall API → OA URL | Conditional download |
| Others | N/A | Abstract only |

### 4. Analysis Layer
**Responsibility:** AI-powered paper analysis using Claude API
- Receives papers with text content
- Produces tiered analysis based on relevance score
- Uses structured prompts for consistent output

**Interfaces:**
- Input: `list[Paper]` (with text content) + `Config` (research interests)
- Output: `list[AnalyzedPaper]` (with score, summary, deep analysis, comparisons)

**Analysis pipeline per paper:**
1. **Relevance scoring** (all papers): Score 1-10 based on research interests
2. **Summary generation** (score >= threshold): Key contributions in 2-3 paragraphs
3. **Deep analysis** (high relevance only): Methodology, limitations, future directions
4. **Comparative analysis** (high relevance only): Related work comparison

**Tiered output:**
| Relevance Score | Content Generated |
|----------------|-------------------|
| 7-10 (High) | Full analysis: score + summary + deep + comparative |
| 4-6 (Medium) | Score + summary |
| 1-3 (Low) | Score + title + link only |

### 5. Delivery Layer
**Responsibility:** Push results to configured channels
- Runs in parallel for all enabled channels
- Each channel is a notifier implementing a common interface
- Zotero and Obsidian are optional, controlled by config

**Interfaces:**
- Input: `list[AnalyzedPaper]` + `Config`
- Output: Delivery confirmations

**Notifiers:**
| Channel | Method | Format |
|---------|--------|--------|
| Feishu/Lark | Webhook POST (httpx) | Rich message card (JSON) |
| Email | SMTP (stdlib) | HTML email via Jinja2 template |
| Zotero | pyzotero API | Create item + tags + attach PDF |
| Obsidian | Git push to vault repo | Markdown files (Jinja2 templates) |

### 6. State Management
**Responsibility:** Track seen papers and run history across executions
- Maintains `state/seen_papers.json` with DOI/title hashes
- Ensures no duplicate notifications across runs
- Tracks last successful run timestamp

**Interfaces:**
- Input: `list[Paper]` (to check/filter)
- Output: Updated state file

## Data Flow

```
Config.yaml ──→ Settings model
                    │
                    ↓
SearchQuery ──→ [ArxivSource, PubMedSource, OpenAlexSource, ...]
                    │                         (parallel via asyncio.gather)
                    ↓
              Raw results from each source
                    │
                    ↓
              Normalization → Paper models
                    │
                    ↓
              Deduplication (by DOI / title hash)
                    │
                    ↓
              Seen-paper filtering (compare with state/)
                    │
                    ↓
              New unseen papers
                    │
                    ↓
              PDF fetch (parallel, graceful degradation)
                    │
                    ↓
              Papers with text content
                    │
                    ↓
              AI Analysis (batched Claude API calls)
                    │         ┌─ High:   full analysis
                    │         ├─ Medium: summary only
                    │         └─ Low:    metadata only
                    ↓
              AnalyzedPaper list
                    │
            ┌───────┼──────────┬──────────┐
            ↓       ↓          ↓          ↓
         Feishu   Email     Zotero     Obsidian
       (webhook)  (SMTP)   (API opt)  (git opt)
```

## Directory Structure

```
literature-push/
├── .github/
│   └── workflows/
│       └── daily-push.yml          # GitHub Actions workflow
├── src/
│   ├── __init__.py
│   ├── main.py                     # Pipeline orchestrator
│   ├── config/
│   │   ├── __init__.py
│   │   ├── models.py               # Pydantic config models
│   │   └── loader.py               # YAML + env config loader
│   ├── search/
│   │   ├── __init__.py
│   │   ├── base.py                 # SearchSource ABC
│   │   ├── arxiv_source.py
│   │   ├── pubmed_source.py
│   │   ├── openalex_source.py
│   │   ├── doi_resolver.py
│   │   └── dedup.py                # Deduplication logic
│   ├── fetch/
│   │   ├── __init__.py
│   │   ├── pdf_fetcher.py
│   │   └── text_extractor.py       # PyMuPDF wrapper
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── analyzer.py             # Claude API integration
│   │   └── prompts.py              # Prompt templates
│   ├── delivery/
│   │   ├── __init__.py
│   │   ├── base.py                 # Notifier ABC
│   │   ├── feishu.py               # Feishu webhook
│   │   ├── email_notify.py         # SMTP email
│   │   ├── zotero.py               # Zotero integration
│   │   └── obsidian.py             # Obsidian vault push
│   └── state/
│       ├── __init__.py
│       └── manager.py              # Seen-paper tracking
├── templates/
│   ├── feishu_card.json.j2         # Feishu message template
│   ├── email_digest.html.j2        # Email HTML template
│   ├── obsidian_daily.md.j2        # Obsidian daily summary template
│   └── obsidian_paper.md.j2        # Obsidian per-paper card template
├── config.yaml                     # User configuration (search queries, preferences)
├── config.example.yaml             # Example configuration for new users
├── requirements.txt                # Python dependencies
├── state/                          # Runtime state (gitignored)
│   └── seen_papers.json
└── README.md                       # Setup instructions
```

## Build Order (Dependency-Aware)

| Order | Component | Depends On | Reason |
|-------|-----------|-----------|--------|
| 1 | Config layer | Nothing | Foundation — everything reads config |
| 2 | Data models (Paper, SearchResult) | Config | Shared types used by all layers |
| 3 | State management | Data models | Needed before search to filter seen papers |
| 4 | Search layer (source adapters) | Config + Data models | Core functionality |
| 5 | Fetch layer | Search layer | Needs paper URLs from search |
| 6 | Analysis layer | Fetch layer | Needs paper text content |
| 7 | Delivery: Feishu + Email | Analysis layer | Core notification channels |
| 8 | Delivery: Zotero | Analysis layer + Fetch | Optional, needs PDFs |
| 9 | Delivery: Obsidian | Analysis layer | Optional, needs analysis output |
| 10 | GitHub Actions workflow | All components | Orchestrates the pipeline |

## Key Architecture Decisions

1. **Pipeline, not microservices**: Single GitHub Actions workflow, sequential stages, parallel within stages. No service mesh, no database, no message queue.

2. **Source adapters behind ABC**: Adding a new source = implement `SearchSource` + add to config. No changes to pipeline logic.

3. **Graceful degradation at every stage**: If search fails for one source, others continue. If PDF fetch fails, use abstract. If analysis API errors, deliver raw metadata.

4. **State in flat JSON files**: No database. JSON files in `state/` directory, committed to repo or gitignored based on preference. Simple, inspectable, debuggable.

5. **Templates for all output**: Feishu, email, Obsidian all use Jinja2 templates. Users can customize output format without touching Python code.

---
*Architecture research for: Daily Literature Push System*
*Researched: 2026-04-13*
