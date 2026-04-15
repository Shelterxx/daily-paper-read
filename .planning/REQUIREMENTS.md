# Requirements: Daily Literature Push System (每日文献推送系统)

**Defined:** 2026-04-13
**Core Value:** Every morning, a researcher sees a prioritized, AI-analyzed digest of the most relevant new papers in their field — with one click to archive to Zotero or add to their Obsidian knowledge base.

## v1 Requirements

### Configuration

- [x] **CONF-01**: User can define search queries, research interests, and preferences via a validated YAML config file
- [x] **CONF-02**: System provides a well-documented config.example.yaml with sensible defaults for quick setup
- [x] **CONF-03**: System loads API credentials from environment variables (GitHub Secrets) with clear error messages for missing keys
- [x] **CONF-04**: User can enable/disable individual search sources via config toggles
- [x] **CONF-05**: User can configure relevance score thresholds for tiered analysis (high/medium/low cutoffs)

### Literature Search

- [x] **SRCH-01**: System searches arXiv for papers matching configured queries with date filtering
- [x] **SRCH-02**: System searches PubMed via E-utilities for papers matching configured queries
- [x] **SRCH-03**: System searches OpenAlex for papers matching configured queries
- [x] **SRCH-04**: System searches Semantic Scholar for papers matching configured queries
- [x] **SRCH-05**: System resolves DOIs to paper metadata via content negotiation
- [x] **SRCH-06**: System deduplicates results across all sources by DOI and normalized title hash
- [x] **SRCH-07**: System tracks seen papers in persistent state file to avoid re-pushing across daily runs
- [x] **SRCH-08**: System runs search queries in parallel across enabled sources via asyncio

### Content Fetching

- [x] **FETH-01**: System downloads open-access PDFs from arXiv using direct HTTP
- [x] **FETH-02**: System downloads open-access PDFs from PubMed Central
- [x] **FETH-03**: System resolves open-access PDF URLs via Unpaywall API for DOI-resolved papers
- [x] **FETH-04**: System extracts full text from downloaded PDFs via PyMuPDF for AI analysis
- [x] **FETH-05**: System gracefully falls back to abstract-only processing when PDF is unavailable

### AI Analysis

- [x] **ANLY-01**: System scores each paper's relevance (1-10) to user's configured research interests via Claude API
- [x] **ANLY-02**: System generates concise summaries (2-3 paragraphs) for medium-and-above relevance papers via Claude API
- [x] **ANLY-03**: System produces deep analysis (methodology, limitations, future directions) for high-relevance papers via Claude API
- [x] **ANLY-04**: System produces comparative analysis with related work for high-relevance papers via Claude API
- [x] **ANLY-05**: System delivers tiered output: high-relevance → full analysis, medium → score + summary, low → title + link only

### Notification

- [x] **NTFY-01**: System pushes tiered literature digest to Feishu/Lark via webhook as rich message cards
- [x] **NTFY-02**: Feishu messages include paper title, authors, relevance score, AI analysis (tiered), and direct links
- [x] **NTFY-03**: System splits large digests into multiple messages if content exceeds Feishu message size limits

### Zotero Integration

- [ ] **ZTR-01**: System can auto-create Zotero items with paper metadata (title, authors, DOI, abstract, date)
- [ ] **ZTR-02**: System adds AI-generated tags to Zotero items based on analysis results
- [ ] **ZTR-03**: System attaches AI summary as a note to each Zotero item
- [ ] **ZTR-04**: System attaches downloaded PDFs to corresponding Zotero items
- [ ] **ZTR-05**: System checks for existing items before creating to avoid duplicates
- [x] **ZTR-06**: Zotero integration is fully optional — system works without Zotero credentials

### Obsidian Integration

- [ ] **OBS-01**: System generates per-paper markdown literature cards with structured metadata and AI analysis
- [ ] **OBS-02**: System generates daily summary notes listing all pushed papers with relevance tiers
- [ ] **OBS-03**: System organizes papers by topic/theme with Obsidian backlinks for knowledge graph building
- [ ] **OBS-04**: System pushes generated notes to an independent Git vault repository via authenticated git push
- [x] **OBS-05**: Obsidian integration is fully optional — system works without vault repo configuration

### GitHub Actions Pipeline

- [x] **PIPE-01**: System runs as a GitHub Actions workflow with daily scheduled cron trigger
- [x] **PIPE-02**: System supports manual workflow_dispatch trigger for on-demand execution
- [x] **PIPE-03**: Pipeline completes within 30 minutes for typical runs (under 100 new papers)
- [x] **PIPE-04**: Pipeline handles partial failures gracefully — one source failure does not block others

## v2 Requirements

### Email Notification

- **NTFY-E01**: System sends HTML email digest via SMTP with all papers organized by relevance tier
- **NTFY-E02**: Email includes both HTML and plain-text alternatives for deliverability
- **NTFY-E03**: User can configure SMTP credentials and recipient address via config

### Advanced Features

- **ADV-01**: System detects emerging research trends across multiple daily runs
- **ADV-02**: System supports importing BibTeX reference lists as seed corpus for relevance calibration
- **ADV-03**: System provides interactive Feishu card buttons for one-click Zotero archiving

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web UI / Dashboard | GitHub repo is the interface; notifications are the output |
| Full-text search indexing | Focus on daily push, not retrospective search engine |
| Browser extension | Outside the GitHub Actions paradigm |
| Closed-access PDF bypass | Legal and ethical concerns; only legally accessible content |
| Real-time collaboration / team features | Designed for individual researchers; fork-based sharing |
| Mobile app | Notifications delivered via existing platforms |
| User authentication system | No user accounts; configuration is per-fork |
| Plugin/marketplace system | Over-engineered; add sources via code contribution |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONF-01 | Phase 1 | Complete |
| CONF-02 | Phase 1 | Complete |
| CONF-03 | Phase 1 | Complete |
| CONF-04 | Phase 1 | Complete |
| CONF-05 | Phase 1 | Complete |
| SRCH-01 | Phase 1 | Complete |
| SRCH-02 | Phase 2 | Complete |
| SRCH-03 | Phase 2 | Complete |
| SRCH-04 | Phase 2 | Complete |
| SRCH-05 | Phase 2 | Complete |
| SRCH-06 | Phase 1 | Complete |
| SRCH-07 | Phase 1 | Complete |
| SRCH-08 | Phase 1 | Complete |
| FETH-01 | Phase 2 | Complete |
| FETH-02 | Phase 2 | Complete |
| FETH-03 | Phase 2 | Complete |
| FETH-04 | Phase 2 | Complete |
| FETH-05 | Phase 1 | Complete |
| ANLY-01 | Phase 1 | Complete |
| ANLY-02 | Phase 1 | Complete |
| ANLY-03 | Phase 3 | Complete |
| ANLY-04 | Phase 3 | Complete |
| ANLY-05 | Phase 1 | Complete |
| NTFY-01 | Phase 1 | Complete |
| NTFY-02 | Phase 1 | Complete |
| NTFY-03 | Phase 1 | Complete |
| ZTR-01 | Phase 4 | Pending |
| ZTR-02 | Phase 4 | Pending |
| ZTR-03 | Phase 4 | Pending |
| ZTR-04 | Phase 4 | Pending |
| ZTR-05 | Phase 4 | Pending |
| ZTR-06 | Phase 1 | Complete |
| OBS-01 | Phase 4 | Pending |
| OBS-02 | Phase 4 | Pending |
| OBS-03 | Phase 4 | Pending |
| OBS-04 | Phase 4 | Pending |
| OBS-05 | Phase 1 | Complete |
| PIPE-01 | Phase 1 | Complete |
| PIPE-02 | Phase 1 | Complete |
| PIPE-03 | Phase 1 | Complete |
| PIPE-04 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 41 total
- Mapped to phases: 41
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-13*
*Last updated: 2026-04-13 after roadmap creation*
