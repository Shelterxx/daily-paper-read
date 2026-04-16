"""Daily Literature Push - Pipeline Orchestrator

Complete pipeline: Config -> Keywords -> Search -> PDF Fetch -> AI Analysis -> Feishu Notify -> State Save
"""

import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

from src.config.loader import load_config
from src.config.models import AppConfig
from src.state.manager import StateManager
from src.search.models import Paper, AnalyzedPaper, RelevanceTier, SearchQuery
from src.search.arxiv_source import ArxivSource
from src.search.sci_search_source import SciSearchSource
from src.search.openalex_source import OpenAlexSource
from src.search.semantic_scholar_source import SemanticScholarSource
from src.search.doi_resolver import enrich_papers_batch
from src.search.dedup import deduplicate_papers
from src.fetch.multi_channel_fetcher import fetch_pdf_multi_channel
from src.analysis.keyword_extractor import extract_keywords
from src.analysis.analyzer import PaperAnalyzer
from src.delivery.feishu import FeishuNotifier
from src.integrations.zotero import ZoteroArchiver
from src.integrations.obsidian import ObsidianWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("literature-push")


def _get_source_instances() -> dict[str, "SearchSource"]:
    """Instantiate all enabled search sources.

    Returns a dict mapping source name to SearchSource instance.
    Sources that fail to instantiate (e.g. missing env vars) are skipped
    with a warning -- they won't be searched but won't block other sources.
    """
    from src.search.base import SearchSource

    sources: dict[str, SearchSource] = {}
    # ArxivSource always instantiated, controlled by enabled check in pipeline
    try:
        sources["arxiv"] = ArxivSource()
    except Exception:
        logger.warning("arXiv source not available")
    try:
        sources["sci_search"] = SciSearchSource()
    except Exception:
        logger.warning("sci_search source not available")
    try:
        sources["openalex"] = OpenAlexSource()
    except Exception:
        logger.warning("OpenAlex source not available")
    try:
        sources["semantic_scholar"] = SemanticScholarSource()
    except Exception:
        logger.warning("Semantic Scholar source not available")
    return sources


async def run_pipeline(config_path: str = "config.yaml") -> dict:
    """Execute the complete literature push pipeline.

    Returns a dict with stats: {total_papers, topics: {name: {high, medium, low, total}}, errors: [str]}
    """
    start_time = time.time()
    stats = {
        "total_papers": 0,
        "topics": {},
        "errors": [],
    }

    # 1. Load and validate config
    logger.info("Step 1/12: Loading configuration...")
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Configuration error: {e}")
        stats["errors"].append(f"Config error: {e}")
        return stats

    logger.info(f"  Loaded {len(config.research_topics)} research topics")

    # 2. Initialize state manager
    logger.info("Step 2/12: Initializing state manager...")
    state = StateManager(state_dir=config.state_dir)
    logger.info(f"  Seen papers: {state.seen_count}")

    # 3. Extract keywords for each topic and search ALL enabled sources
    # CRITICAL: Track which topic produced each paper so analysis only scores
    # papers against the topic that found them (not all topics).
    logger.info("Step 3/12: Searching all enabled sources...")
    papers_by_topic: dict[str, list[Paper]] = defaultdict(list)

    from openai import OpenAI
    llm_client = OpenAI(
        api_key=os.environ.get(config.llm.api_key_env, ""),
        base_url=config.llm.base_url,
        timeout=60.0,
    )

    source_instances = _get_source_instances()

    for topic in config.research_topics:
        logger.info(f"  Processing topic: {topic.name}")

        # Extract keywords (manual override or LLM extraction)
        if topic.keywords:
            keywords = topic.keywords
            logger.info(f"    Using manual keywords: {keywords}")
        else:
            keywords = extract_keywords(
                description=topic.description,
                client=llm_client,
                model=config.llm.scoring_model,
            )
            logger.info(f"    Extracted keywords: {keywords}")

        # Search each enabled source
        source_configs = {
            "arxiv": (config.sources.arxiv, topic.sources.arxiv),
            "sci_search": (config.sources.sci_search, getattr(topic.sources, 'sci_search', None)),
            "openalex": (config.sources.openalex, getattr(topic.sources, 'openalex', None)),
            "semantic_scholar": (config.sources.semantic_scholar, getattr(topic.sources, 'semantic_scholar', None)),
        }

        for source_name, (global_cfg, topic_cfg) in source_configs.items():
            # Check enabled: topic-level explicit override wins, else inherit from global config
            # Topic-level SourcesConfig defaults are ignored — only explicit topic config overrides global.
            enabled = global_cfg.enabled
            if not enabled:
                logger.info(f"    {source_name} disabled for topic {topic.name}, skipping")
                continue

            if source_name not in source_instances:
                logger.warning(f"    {source_name} adapter not available, skipping")
                continue

            try:
                max_results = global_cfg.max_results
                query = SearchQuery(
                    topic_name=topic.name,
                    source=source_name,
                    keywords=keywords,
                    timeframe_hours=config.search_timeframe_hours,
                    max_results=max_results,
                )
                papers = await source_instances[source_name].search(query)
                logger.info(f"    Found {len(papers)} papers from {source_name}")
                papers_by_topic[topic.name].extend(papers)
            except Exception as e:
                error_msg = f"{source_name} search failed for topic '{topic.name}': {e}"
                logger.error(f"    {error_msg}")
                stats["errors"].append(error_msg)
                continue  # PIPE-04: one source failure does not block others

    all_papers: list[Paper] = []
    for topic_papers in papers_by_topic.values():
        all_papers.extend(topic_papers)

    if not all_papers:
        logger.info("No papers found from any source")
        return stats

    # 4. Deduplicate and filter seen papers (SRCH-07)
    logger.info(f"Step 4/12: Deduplicating {len(all_papers)} papers...")
    all_papers = deduplicate_papers(all_papers)
    all_papers = state.filter_new(all_papers)
    logger.info(f"  After dedup + seen filter: {len(all_papers)} new papers")

    if not all_papers:
        logger.info("No new papers after filtering")
        return stats

    # 4b. Enrich papers with missing metadata via DOI content negotiation
    logger.info(f"Step 4b: Enriching {len(all_papers)} papers via DOI resolution...")
    async with httpx.AsyncClient() as client:
        await enrich_papers_batch(all_papers, client)
    enriched_count = sum(1 for p in all_papers if p.doi and p.abstract)
    logger.info(f"  {enriched_count} papers have DOI + abstract after enrichment")

    # Rebuild papers_by_topic with only the new papers that remain after dedup+filter.
    # A paper searched under Topic A stays associated with Topic A only.
    new_paper_ids = {p.paper_id for p in all_papers}
    filtered_by_topic: dict[str, list[Paper]] = defaultdict(list)
    for topic_name, topic_papers in papers_by_topic.items():
        for p in topic_papers:
            if p.paper_id in new_paper_ids:
                filtered_by_topic[topic_name].append(p)

    # Cap papers per topic to control scoring cost.
    # After dedup, keep at most max_push * 3 per topic (score excess papers wastes API calls).
    # Prioritize papers with DOI and abstract (likely from academic DBs like OpenAlex/sci_search)
    # over arXiv-only papers which may lack relevance for environmental science topics.
    SOURCE_PRIORITY = {"openalex": 0, "sci_search": 1, "semantic_scholar": 2, "arxiv": 3}
    MAX_PAPERS_PER_TOPIC_MULTIPLIER = 3
    for topic in config.research_topics:
        topic_papers = filtered_by_topic.get(topic.name, [])
        cap = topic.max_push * MAX_PAPERS_PER_TOPIC_MULTIPLIER
        if len(topic_papers) > cap:
            topic_papers.sort(key=lambda p: (
                SOURCE_PRIORITY.get(p.source, 99),
                0 if p.doi else 1,
                0 if p.abstract else 1,
            ))
            logger.info(
                f"  Capping '{topic.name}': {len(topic_papers)} → {cap} papers "
                f"(prioritizing academic DB sources)"
            )
            filtered_by_topic[topic.name] = topic_papers[:cap]

    # 5. AI Scoring (abstract-only, no PDF needed)
    # Score ALL papers using abstracts to determine relevance tiers.
    # This avoids downloading PDFs for papers that will be filtered out.
    logger.info("Step 5/12: Scoring papers (abstracts only)...")
    all_analyzed: list[AnalyzedPaper] = []

    for topic in config.research_topics:
        topic_papers = filtered_by_topic.get(topic.name, [])
        if not topic_papers:
            continue

        try:
            analyzer = PaperAnalyzer(
                llm_config=config.llm,
                thresholds=topic.relevance_thresholds,
                language=config.notification.language,
            )
            analyzed = analyzer.analyze_papers(topic_papers, topic.description)
            for ap in analyzed:
                ap.topic_name = topic.name
            all_analyzed.extend(analyzed)
        except Exception as e:
            error_msg = f"Analysis failed for topic '{topic.name}': {e}"
            logger.error(error_msg)
            stats["errors"].append(error_msg)
            continue

    # 6. Fetch PDFs only for HIGH-relevance papers (multi-channel)
    high_analyzed = [ap for ap in all_analyzed if ap.analysis.tier == RelevanceTier.HIGH]
    if high_analyzed:
        logger.info(f"Step 6/12: Fetching PDFs for {len(high_analyzed)} high-relevance papers (multi-channel)...")
        async with httpx.AsyncClient() as client:
            sem = asyncio.Semaphore(5)

            async def fetch_with_sem(ap):
                async with sem:
                    await fetch_pdf_multi_channel(ap.paper, client)

            await asyncio.gather(*[fetch_with_sem(ap) for ap in high_analyzed])

        full_text_count = sum(1 for ap in high_analyzed if ap.paper.text_source == "full_text")
        logger.info(f"  {full_text_count}/{len(high_analyzed)} papers with full text (multi-channel)")
    else:
        logger.info("Step 6/12: No high-relevance papers, skipping PDF download")

    # 7. Deep analysis for HIGH-relevance papers (with full text) — Stage 2a
    if high_analyzed:
        logger.info(f"Step 7/12: Deep-analyzing {len(high_analyzed)} high-relevance papers...")
        for topic in config.research_topics:
            topic_high = [ap for ap in high_analyzed if ap.topic_name == topic.name]
            if not topic_high:
                continue
            try:
                analyzer = PaperAnalyzer(
                    llm_config=config.llm,
                    thresholds=topic.relevance_thresholds,
                    language=config.notification.language,
                )
                for ap in topic_high:
                    ap.analysis = analyzer.analyze_paper(
                        ap.paper, topic.description, ap.analysis
                    )
            except Exception as e:
                logger.error(f"Deep analysis failed for topic '{topic.name}': {e}")
    else:
        logger.info("Step 7/12: No papers to deep-analyze")

    # 8. Stage 2b: Methodology deep analysis for HIGH-relevance papers
    if high_analyzed:
        logger.info(f"Step 8/12: Methodology deep analysis for {len(high_analyzed)} high-relevance papers...")
        for topic in config.research_topics:
            topic_high = [ap for ap in high_analyzed if ap.topic_name == topic.name]
            if not topic_high:
                continue
            try:
                analyzer = PaperAnalyzer(
                    llm_config=config.llm,
                    thresholds=topic.relevance_thresholds,
                    language=config.notification.language,
                )
                for ap in topic_high:
                    ap.analysis = analyzer.deep_analyze_methodology(ap.paper, ap.analysis)
            except Exception as e:
                logger.error(f"Methodology analysis failed for topic '{topic.name}': {e}")
    else:
        logger.info("Step 8/12: No high-relevance papers, skipping methodology analysis")

    # 9. Stage 3: Comparative analysis for top-scoring papers (9-10 only)
    top_papers = [ap for ap in high_analyzed if ap.analysis.relevance_score >= 9]
    if top_papers:
        logger.info(f"Step 9/12: Comparative analysis for {len(top_papers)} top-scoring papers (score >= 9)...")
        for topic in config.research_topics:
            topic_top = [ap for ap in top_papers if ap.topic_name == topic.name]
            if not topic_top:
                continue
            try:
                analyzer = PaperAnalyzer(
                    llm_config=config.llm,
                    thresholds=topic.relevance_thresholds,
                    language=config.notification.language,
                )
                for ap in topic_top:
                    historical = state.get_history_for_comparison(
                        topic_name=topic.name,
                        keywords=ap.analysis.extracted_keywords,
                        limit=5,
                    )
                    if historical:
                        ap.analysis = analyzer.compare_with_history(ap.paper, ap.analysis, historical)
                    else:
                        logger.warning(f"No historical papers for comparison with '{ap.paper.title[:40]}'")
            except Exception as e:
                logger.error(f"Comparative analysis failed for topic '{topic.name}': {e}")
    else:
        logger.info("Step 9/12: No papers scoring 9+, skipping comparative analysis")

    # Save HIGH papers to history for future comparative analysis
    if high_analyzed:
        for ap in high_analyzed:
            try:
                state.add_to_history(ap)
            except Exception as e:
                logger.warning(f"Failed to add paper to history: {e}")
        logger.info(f"Saved {len(high_analyzed)} papers to analysis history")

    # 10. Send notification and save state
    logger.info("Step 10/12: Sending notification and saving state...")
    topic_stats = {}
    for ap in all_analyzed:
        if ap.topic_name not in topic_stats:
            topic_stats[ap.topic_name] = {"high": 0, "medium": 0, "low": 0, "total": 0}
        tier = ap.analysis.tier.value
        topic_stats[ap.topic_name][tier] += 1
        topic_stats[ap.topic_name]["total"] += 1

    stats["topics"] = topic_stats
    stats["total_papers"] = len(all_analyzed)

    if all_analyzed:
        # Cap HIGH papers per topic to max_push for notification
        notify_analyzed = []
        max_push_by_topic = {t.name: t.max_push for t in config.research_topics}
        for topic in config.research_topics:
            topic_papers = [ap for ap in all_analyzed if ap.topic_name == topic.name]
            high_topic = [ap for ap in topic_papers if ap.analysis.tier == RelevanceTier.HIGH]
            high_topic.sort(key=lambda ap: ap.analysis.relevance_score, reverse=True)
            cap = max_push_by_topic.get(topic.name, 20)
            if len(high_topic) > cap:
                logger.info(
                    f"  Capping '{topic.name}' push: {len(high_topic)} HIGH → {cap} "
                    f"(top {cap} by score)"
                )
                # Keep capped HIGH + all non-HIGH (for stats)
                capped_high = set(ap.paper.paper_id for ap in high_topic[:cap])
                notify_analyzed.extend(
                    ap for ap in topic_papers
                    if ap.paper.paper_id in capped_high or ap.analysis.tier != RelevanceTier.HIGH
                )
            else:
                notify_analyzed.extend(topic_papers)

        # Send Feishu notification
        webhook_url = os.environ.get(config.notification.feishu_webhook_env)
        notifier = FeishuNotifier(
            webhook_url=webhook_url,
            language=config.notification.language,
            compact_cards=config.notification.compact_cards,
            feishu_app_config=config.feishu_app,
        )
        try:
            notify_ok = await notifier.send(notify_analyzed, topic_stats)
            if notify_ok:
                logger.info("  Notification sent successfully")
            else:
                logger.error("  Notification sending failed")
                stats["errors"].append("Feishu notification failed")
        except Exception as e:
            logger.error(f"  Notification error: {e}")
            stats["errors"].append(f"Notification error: {e}")

        # Save seen papers only after successful pipeline run
        state.mark_seen_batch([ap.paper.dedup_key for ap in all_analyzed])
        logger.info(f"  Saved {len(all_analyzed)} papers to seen state")
    else:
        # No papers worth notifying about -- still notify "no new papers"
        webhook_url = os.environ.get(config.notification.feishu_webhook_env)
        notifier = FeishuNotifier(
            webhook_url=webhook_url,
            language=config.notification.language,
            compact_cards=config.notification.compact_cards,
            feishu_app_config=config.feishu_app,
        )
        try:
            await notifier.send([], topic_stats)
        except Exception:
            pass

    # 11. Zotero archiving (optional, independent fault tolerance)
    if config.zotero and config.zotero.enabled:
        if config.feishu_app and config.feishu_app.enabled:
            # Interactive mode: save paper data for archive service, skip auto-archive
            logger.info("Step 11: Interactive button enabled — saving papers for on-demand archiving")
            try:
                papers_data = []
                for ap in high_analyzed:
                    papers_data.append({
                        "paper": ap.paper.model_dump(mode="json"),
                        "analysis": ap.analysis.model_dump(mode="json"),
                        "topic_name": ap.topic_name,
                    })
                state.save_papers_for_callback(papers_data)
                logger.info(f"  Saved {len(papers_data)} papers for archive service")
            except Exception as e:
                logger.warning(f"  Failed to save papers for callback: {e}")
        else:
            # Auto-archive mode: archive papers above archive_threshold
            threshold = config.zotero.archive_threshold
            to_archive = [ap for ap in high_analyzed if ap.analysis.relevance_score >= threshold]
            skipped_auto = len(high_analyzed) - len(to_archive)
            logger.info(
                f"Step 11: Archiving {len(to_archive)}/{len(high_analyzed)} HIGH papers "
                f"(score >= {threshold}) to Zotero, {skipped_auto} below archive threshold"
            )
            if to_archive:
                try:
                    zotero_archiver = ZoteroArchiver(config.zotero)
                    zotero_result = await zotero_archiver.archive_papers(to_archive)
                    logger.info(
                        f"  Zotero: {zotero_result.get('archived', 0)} archived, "
                        f"{zotero_result.get('skipped_existing', 0)} duplicates skipped, "
                        f"{len(zotero_result.get('errors', []))} errors"
                    )
                    if zotero_result.get('errors'):
                        for err in zotero_result['errors']:
                            logger.warning(f"  Zotero error: {err}")
                except Exception as e:
                    logger.error(f"  Zotero archiving failed: {e}")
                    stats["errors"].append(f"Zotero error: {e}")
            else:
                logger.info("  No papers above archive threshold, skipping")
    elif config.feishu_app and config.feishu_app.enabled:
        # Interactive mode enabled but Zotero not configured — still save papers
        # (archive service handles Zotero connection independently)
        logger.info("Step 11: Saving papers for archive service (Zotero not in pipeline config)")
        try:
            papers_data = []
            for ap in high_analyzed:
                papers_data.append({
                    "paper": ap.paper.model_dump(mode="json"),
                    "analysis": ap.analysis.model_dump(mode="json"),
                    "topic_name": ap.topic_name,
                })
            state.save_papers_for_callback(papers_data)
            logger.info(f"  Saved {len(papers_data)} papers for archive service")
        except Exception as e:
            logger.warning(f"  Failed to save papers for callback: {e}")
    else:
        logger.info("Step 11: Zotero integration not configured, skipping")

    # 12. Obsidian vault generation (optional, independent fault tolerance)
    if config.obsidian and config.obsidian.enabled:
        logger.info("Step 12: Generating Obsidian vault notes and pushing...")
        try:
            obsidian_writer = ObsidianWriter(config.obsidian)
            obsidian_result = await obsidian_writer.write_and_push(all_analyzed, topic_stats)
            logger.info(
                f"  Obsidian: {obsidian_result.get('cards_written', 0)} cards, "
                f"daily={obsidian_result.get('daily_written', False)}, "
                f"pushed={obsidian_result.get('pushed', False)}"
            )
            if obsidian_result.get('errors'):
                for err in obsidian_result['errors']:
                    logger.warning(f"  Obsidian error: {err}")
        except Exception as e:
            logger.error(f"  Obsidian generation failed: {e}")
            stats["errors"].append(f"Obsidian error: {e}")
    else:
        logger.info("Step 12: Obsidian integration not configured, skipping")

    elapsed = time.time() - start_time
    logger.info(f"Pipeline complete in {elapsed:.1f}s: {stats['total_papers']} papers, {len(stats['errors'])} errors")
    return stats


def main():
    """Entry point for the pipeline."""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    result = asyncio.run(run_pipeline(config_path))

    # Exit with error code if there were critical failures
    if result["errors"] and result["total_papers"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
