# Daily Literature Push System (每日文献推送系统)

## What This Is

A GitHub Actions-based daily academic literature push system that automatically searches, fetches, analyzes, and notifies users about relevant new papers in their research areas. Users can fork the repo, configure their research interests via YAML, and receive daily push notifications via Feishu (Lark) and/or email. The system also supports optional Zotero archiving and Obsidian knowledge base accumulation.

Designed for individual researchers but architected for easy fork-and-deploy reuse by others.

## Core Value

Every morning, a researcher sees a prioritized, AI-analyzed digest of the most relevant new papers in their field — with one click to archive to Zotero or add to their Obsidian knowledge base.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Multi-source literature search (sci_search, arXiv, PubMed, OpenAlex, DOI resolution)
- [ ] PDF fetching from multiple sources (ScienceDirect, arXiv, PubMed Central, DOI-resolved open access)
- [ ] AI-powered analysis pipeline: relevance scoring, summary generation, deep analysis, comparative analysis
- [ ] Tiered push notifications: high-relevance papers get full analysis, medium get summary, low get title-only listing
- [ ] Feishu/Lark notification integration (rich message cards)
- [ ] Email notification integration (formatted digest email)
- [ ] Optional Zotero archiving: auto-add items, tags/notes, attach PDFs, click-to-trigger mode
- [ ] Obsidian knowledge base: independent Git repo vault with daily summaries, topic-based categorization, per-paper literature cards
- [ ] YAML configuration file for search queries, research interests, notification preferences
- [ ] GitHub Actions workflow with mixed trigger mode (scheduled cron + manual dispatch)
- [ ] Unified, well-structured codebase referencing existing tools (literature-search, sciencedirect-live-session-fetcher, paperRead) but rebuilt with consistent architecture

### Out of Scope

- Real-time collaboration or team features — designed for individual use, fork-based sharing
- Web UI or dashboard — GitHub repo is the interface, notifications are the output
- Mobile app — notifications via existing platforms (Feishu, email)
- Full-text search indexing — focus on daily push, not retrospective search
- Closed-access PDF bypass — only fetch legally accessible papers (open access, arXiv preprints)

## Context

### Existing Tools to Reference

The user has access to several existing skills/tools that inform this project:

1. **literature-search**: Search tool primarily using sci_search source. Returns sorted literature results. Likely uses DOI URLs for linking. Should be studied for search query construction and result normalization.

2. **sciencedirect-live-session-fetcher**: Can fetch PDFs from ScienceDirect URLs using session-based access. Should be studied for PDF fetching patterns and session management.

3. **paperRead**: Complete arXiv-based literature reading pipeline. Has search → fetch → analyze flow but lacks Obsidian integration. Should be studied as a reference for the overall pipeline architecture.

4. **literature-annotator**: Creates dual-column HTML files with color-coded analysis. May inform the AI analysis output format.

### Key Design Principles

- **Configuration-driven**: Users define everything via YAML files committed to their fork
- **Source-agnostic**: Abstract search/fetch interfaces so adding new sources (e.g., Semantic Scholar, DBLP) is straightforward
- **Graceful degradation**: If one source fails, others continue; if PDF fetch fails, still push with abstract
- **Fork-friendly**: New users should be able to fork, configure secrets, edit YAML, and have a working system in < 10 minutes

### Deployment Model

- **Primary**: GitHub Actions (cron schedule + workflow_dispatch)
- **Configuration**: YAML files in repo + GitHub Secrets for API keys
- **Output channels**: Feishu bot webhook, SMTP email, Zotero API, Git push to Obsidian vault repo

## Constraints

- **Platform**: Must run in GitHub Actions environment (Ubuntu runner, limited resources)
- **Budget**: Minimize API costs — prefer free tiers (Semantic Scholar API, arXiv API, PubMed E-utilities, OpenAlex API)
- **AI Model**: Claude API for analysis (user provides their own API key via GitHub Secrets)
- **Time**: GitHub Actions has 6-hour timeout; daily run should complete within 30 minutes
- **Access**: Only fetch legally accessible content (open access papers, arXiv preprints, publisher-provided abstracts)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Reference existing tools, rebuild with unified architecture | User wants clean, standardized code rather than gluing existing skills together | — Pending |
| Independent Git repo for Obsidian vault | Works with GitHub Actions, no local filesystem access needed, clean separation | — Pending |
| YAML config files + GitHub Secrets for credentials | Fork-friendly: config in repo, secrets protected | — Pending |
| Tiered notification (high/medium/low relevance) | Manages information overload — researchers can focus on what matters | — Pending |

---
*Last updated: 2026-04-13 after initialization*
