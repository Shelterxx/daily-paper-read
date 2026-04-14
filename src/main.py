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
    logger.info("Step 1/8: Loading configuration...")
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Configuration error: {e}")
        stats["errors"].append(f"Config error: {e}")
        return stats

    logger.info(f"  Loaded {len(config.research_topics)} research topics")

    # 2. Initialize state manager
    logger.info("Step 2/8: Initializing state manager...")
    state = StateManager(state_dir=config.state_dir)
    logger.info(f"  Seen papers: {state.seen_count}")

    # 3. Extract keywords for each topic and search ALL enabled sources
    # CRITICAL: Track which topic produced each paper so analysis only scores
    # papers against the topic that found them (not all topics).
    logger.info("Step 3/8: Searching all enabled sources...")
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
            # Check enabled: topic-level overrides global
            enabled = topic_cfg.enabled if topic_cfg is not None else global_cfg.enabled
            if not enabled:
                logger.info(f"    {source_name} disabled for topic {topic.name}, skipping")
                continue

            if source_name not in source_instances:
                logger.warning(f"    {source_name} adapter not available, skipping")
                continue

            try:
                max_results = (topic_cfg.max_results if topic_cfg is not None else None) or global_cfg.max_results
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
    logger.info(f"Step 4/8: Deduplicating {len(all_papers)} papers...")
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
    MAX_PAPERS_PER_TOPIC_MULTIPLIER = 3
    for topic in config.research_topics:
        topic_papers = filtered_by_topic.get(topic.name, [])
        cap = topic.max_push * MAX_PAPERS_PER_TOPIC_MULTIPLIER
        if len(topic_papers) > cap:
            logger.info(
                f"  Capping '{topic.name}': {len(topic_papers)} → {cap} papers"
            )
            filtered_by_topic[topic.name] = topic_papers[:cap]

    # 5. AI Scoring (abstract-only, no PDF needed)
    # Score ALL papers using abstracts to determine relevance tiers.
    # This avoids downloading PDFs for papers that will be filtered out.
    logger.info("Step 5/8: Scoring papers (abstracts only)...")
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
        logger.info(f"Step 6/8: Fetching PDFs for {len(high_analyzed)} high-relevance papers (multi-channel)...")
        async with httpx.AsyncClient() as client:
            sem = asyncio.Semaphore(5)

            async def fetch_with_sem(ap):
                async with sem:
                    await fetch_pdf_multi_channel(ap.paper, client)

            await asyncio.gather(*[fetch_with_sem(ap) for ap in high_analyzed])

        full_text_count = sum(1 for ap in high_analyzed if ap.paper.text_source == "full_text")
        logger.info(f"  {full_text_count}/{len(high_analyzed)} papers with full text (multi-channel)")
    else:
        logger.info("Step 6/8: No high-relevance papers, skipping PDF download")

    # 7. Deep analysis for HIGH-relevance papers (with full text)
    if high_analyzed:
        logger.info(f"Step 7/8: Deep-analyzing {len(high_analyzed)} high-relevance papers...")
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
        logger.info("Step 7/8: No papers to deep-analyze")

    # 8. Send notification and save state
    logger.info("Step 8/8: Sending notification and saving state...")
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
        # Send Feishu notification
        webhook_url = os.environ.get(config.notification.feishu_webhook_env)
        notifier = FeishuNotifier(
            webhook_url=webhook_url,
            language=config.notification.language,
        )
        try:
            notify_ok = await notifier.send(all_analyzed, topic_stats)
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
        notifier = FeishuNotifier(webhook_url=webhook_url, language=config.notification.language)
        try:
            await notifier.send([], topic_stats)
        except Exception:
            pass

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
