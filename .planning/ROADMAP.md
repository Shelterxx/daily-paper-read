# Roadmap: Daily Literature Push System (每日文献推送系统)

## Overview

This roadmap delivers a GitHub Actions-based daily academic literature push system across 4 phases. Phase 1 proves the entire pipeline end-to-end with a single search source (arXiv) and single notification channel (Feishu). Phase 2 expands to all five search sources with PDF fetching and deduplication at scale. Phase 3 deepens AI value with advanced analysis tiers. Phase 4 adds Zotero archiving and Obsidian knowledge base integrations for power users.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: End-to-End Pipeline Proof** - Config, arXiv search, basic AI analysis, Feishu notification, GitHub Actions workflow
- [ ] **Phase 2: Multi-Source Search and PDF Fetching** - All five search sources, PDF download pipeline, cross-source deduplication
- [ ] **Phase 3: Advanced AI Analysis** - Deep analysis, comparative analysis, pipeline hardening and error handling
- [ ] **Phase 4: Zotero and Obsidian Integrations** - Zotero archiving with PDFs and notes, Obsidian vault knowledge base generation

## Phase Details

### Phase 1: End-to-End Pipeline Proof
**Goal**: A researcher receives a daily Feishu message with AI-scored and summarized papers from arXiv, proving the full pipeline works
**Depends on**: Nothing (first phase)
**Requirements**: CONF-01, CONF-02, CONF-03, CONF-04, CONF-05, SRCH-01, SRCH-06, SRCH-07, SRCH-08, FETH-05, ANLY-01, ANLY-02, ANLY-05, NTFY-01, NTFY-02, NTFY-03, ZTR-06, OBS-05, PIPE-01, PIPE-02, PIPE-03, PIPE-04
**Success Criteria** (what must be TRUE):
  1. User can fork the repo, configure YAML with search queries and Feishu webhook, add GitHub Secrets, and trigger a workflow run that completes within 30 minutes
  2. User receives a Feishu rich message card listing arXiv papers scored by relevance to their configured research interests, with high-relevance papers showing full analysis, medium showing summary, and low showing title and link only
  3. Re-running the pipeline does not re-push papers already seen in previous runs
  4. If arXiv search or Claude API calls fail, the pipeline logs a clear error message and exits gracefully without a confusing partial notification
  5. User can enable or disable search sources and adjust relevance score thresholds via the YAML config file
**Plans**: 5 plans

Plans:
- [ ] 01-01-PLAN.md -- Config layer, data models, state management, example config
- [ ] 01-02-PLAN.md -- ArXiv search adapter, deduplication, PDF fetch and text extraction
- [ ] 01-03-PLAN.md -- AI analysis pipeline (two-stage scoring + deep analysis + keyword extraction)
- [ ] 01-04-PLAN.md -- Feishu notification with tiered rich message cards
- [ ] 01-05-PLAN.md -- Pipeline orchestrator and GitHub Actions workflow

### Phase 2: Multi-Source Search and PDF Fetching
**Goal**: Researchers get broad academic coverage from all five sources with full-text PDF support for AI analysis
**Depends on**: Phase 1
**Requirements**: SRCH-02, SRCH-03, SRCH-04, SRCH-05, FETH-01, FETH-02, FETH-03, FETH-04
**Success Criteria** (what must be TRUE):
  1. User can enable PubMed, OpenAlex, Semantic Scholar, and DOI resolution in config and receive papers from all enabled sources in a single daily run
  2. Papers appearing in multiple sources appear only once in the final digest (deduplicated by DOI and normalized title)
  3. For papers where an open-access PDF is available, the AI analysis incorporates extracted full text rather than relying solely on the abstract
  4. When a PDF download fails (timeout, 403, corrupt file), the system falls back to abstract-only processing and the paper still appears in the digest
  5. All source searches run in parallel and the pipeline completes within 30 minutes even with all sources enabled
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD
- [ ] 02-03: TBD

### Phase 3: Advanced AI Analysis
**Goal**: High-relevance papers receive deep methodology analysis and comparative analysis against related work, delivering genuine research insight
**Depends on**: Phase 2
**Requirements**: ANLY-03, ANLY-04
**Success Criteria** (what must be TRUE):
  1. Papers scoring above the high-relevance threshold include a deep analysis section covering methodology evaluation, limitations, and future research directions
  2. High-relevance papers include a comparative analysis section positioning the work relative to related papers found in the same run or recent runs
  3. The Feishu notification for high-relevance papers is clearly distinct from medium/low tier papers, showing the additional analysis depth
  4. Claude API costs remain bounded -- only papers above the high-relevance threshold consume tokens for deep and comparative analysis
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

### Phase 4: Zotero and Obsidian Integrations
**Goal**: Researchers can archive papers to Zotero with one click and accumulate a searchable knowledge base in Obsidian over time
**Depends on**: Phase 3
**Requirements**: ZTR-01, ZTR-02, ZTR-03, ZTR-04, ZTR-05, OBS-01, OBS-02, OBS-03, OBS-04
**Success Criteria** (what must be TRUE):
  1. User can configure Zotero API credentials and have high-relevance papers automatically archived as Zotero items with metadata, AI-generated tags, summary notes, and attached PDFs
  2. Running the pipeline multiple times does not create duplicate Zotero items for the same paper
  3. User can configure an Obsidian vault Git repository and find daily summary notes and per-paper literature cards pushed to the vault after each run
  4. Literature cards in Obsidian contain structured metadata, AI analysis, and backlinks to related papers by topic, enabling knowledge graph navigation
  5. Both Zotero and Obsidian integrations are fully optional -- the pipeline runs normally without them configured
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD
- [ ] 04-03: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. End-to-End Pipeline Proof | 0/5 | Planning complete | - |
| 2. Multi-Source Search and PDF Fetching | 0/? | Not started | - |
| 3. Advanced AI Analysis | 0/? | Not started | - |
| 4. Zotero and Obsidian Integrations | 0/? | Not started | - |
