# Features Research

**Domain:** Daily academic literature push system
**Researched:** 2026-04-13
**Confidence:** HIGH

## Table Stakes (Must Have)

### Literature Search
- **Multi-source search**: Query arXiv, PubMed, OpenAlex, Semantic Scholar simultaneously — users expect broad coverage
- **Configurable search queries**: Users define keywords, topics, authors, date ranges in YAML config
- **Deduplication across sources**: Same paper appears in multiple databases; must merge/dedup by DOI or title
- **Relevance sorting**: Results ranked by relevance to user's configured research interests
- **Date filtering**: Only return papers published within configurable time window (default: last 24h)

### PDF / Full-text Access
- **Open access PDF download**: Fetch legally available PDFs from arXiv, PubMed Central, publisher open access
- **Graceful degradation**: If PDF unavailable, still deliver paper with abstract and metadata
- **DOI-based resolution**: Accept DOI and resolve to paper metadata + PDF if available

### AI Analysis
- **Relevance scoring**: Rate each paper's relevance to user's research on a scale (e.g., 1-10)
- **Summary generation**: Produce concise summary highlighting key contributions and methods
- **Chinese/English support**: Generate summaries in user's preferred language

### Notifications
- **Tiered content delivery**: High-relevance → full analysis; medium → summary; low → title + link only
- **Feishu/Lark rich message**: Card-style messages with paper details, links, and action buttons
- **Email digest**: Formatted HTML email with all papers organized by relevance tier

### Configuration & Deployment
- **YAML config file**: All user preferences in one readable file
- **GitHub Secrets for credentials**: API keys, tokens stored securely
- **GitHub Actions workflow**: Scheduled cron + manual dispatch trigger
- **Quick fork-and-deploy**: New users get running in < 10 minutes

## Differentiators (Competitive Advantage)

### Advanced AI Analysis
- **Deep analysis**: Detailed breakdown of methodology, experimental design, limitations, future directions
- **Comparative analysis**: Compare new paper with related work, highlight novel contributions
- **Personalized relevance**: AI learns from user's Zotero library / Obsidian notes to improve relevance scoring over time

### Zotero Integration
- **One-click archiving**: Push notification includes "Save to Zotero" action
- **Auto-tagging**: AI-generated tags applied to Zotero entries
- **PDF attachment**: Downloaded PDFs automatically attached to Zotero items
- **Collection management**: Papers auto-sorted into user-defined Zotero collections

### Obsidian Knowledge Base
- **Daily summary notes**: Each day's papers generate a dated summary note
- **Per-paper literature cards**: Individual markdown files with structured metadata + AI analysis
- **Topic-based organization**: Papers organized by research topic/theme with backlinks
- **Timeline view**: Daily accumulation of literature knowledge over time
- **Independent Git vault**: Notes pushed to a separate repo, opened as Obsidian vault

### System Intelligence
- **Seen-paper tracking**: Never push the same paper twice across runs
- **Trend detection**: Identify emerging topics or hot papers across multiple searches
- **Configurable alert thresholds**: User sets minimum relevance score for notification

## Anti-Features (Deliberately NOT Building)

| Anti-Feature | Why Not |
|-------------|---------|
| Web UI / Dashboard | GitHub repo IS the interface; notifications are the output. Adding a web UI doubles the scope |
| Full-text indexing / retrospective search | Focus on daily push, not building a search engine |
| Browser extension | Outside the GitHub Actions paradigm; adds significant frontend scope |
| Closed-access PDF bypass | Legal and ethical concerns; only fetch legally accessible content |
| Real-time collaboration / team features | Designed for individual researchers; fork-based sharing is sufficient |
| Mobile app | Notifications delivered via existing platforms (Feishu, email) |
| Complex user authentication | No user accounts; configuration is per-fork |
| Plugin/marketplace system | Over-engineered for the current scope; add new sources via code contribution |

## Complexity Assessment

| Feature | Complexity | Dependencies |
|---------|-----------|--------------|
| Multi-source search | MEDIUM | Requires source adapters for each API |
| Deduplication | LOW | DOI hashing + title fuzzy matching |
| PDF download (open access) | MEDIUM | Different URL patterns per source |
| Relevance scoring (AI) | MEDIUM | Claude API prompt engineering |
| Summary generation (AI) | MEDIUM | Claude API prompt engineering |
| Deep + comparative analysis (AI) | HIGH | Requires understanding of research context |
| Feishu notification | LOW | Simple webhook POST |
| Email notification | LOW | SMTP + HTML template |
| Tiered content delivery | LOW | Conditional formatting based on score |
| Zotero integration | MEDIUM | pyzotero API, user must have Zotero account |
| Obsidian vault generation | MEDIUM | Markdown templates + git push |
| YAML config system | LOW | pydantic-settings |
| GitHub Actions workflow | LOW | Standard YAML workflow definition |
| Seen-paper tracking | LOW | JSON state file with DOI/title hashes |

## Feature Dependencies

```
YAML Config ──→ Multi-source Search ──→ Deduplication ──→ Relevance Scoring (AI)
                                            │                    │
                                            ↓                    ↓
                                      PDF Download          Summary / Deep Analysis
                                            │                    │
                                            ↓                    ↓
                                      Tiered Content Delivery ←──┘
                                            │
                                    ┌───────┼───────┐
                                    ↓       ↓       ↓
                                 Feishu   Email   (Zotero + Obsidian)
```

---
*Features research for: Daily Literature Push System*
*Researched: 2026-04-13*
