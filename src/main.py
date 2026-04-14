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

from src.config.loader import load_config
from src.config.models import AppConfig
from src.state.manager import StateManager
from src.search.models import Paper, AnalyzedPaper, RelevanceTier, SearchQuery
from src.search.arxiv_source import ArxivSource
from src.search.dedup import deduplicate_papers
from src.fetch.pdf_fetcher import fetch_and_enrich_paper
from src.analysis.keyword_extractor import extract_keywords
from src.analysis.analyzer import PaperAnalyzer
from src.delivery.feishu import FeishuNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("literature-push")


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
    logger.info("Step 1/7: Loading configuration...")
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Configuration error: {e}")
        stats["errors"].append(f"Config error: {e}")
        return stats

    logger.info(f"  Loaded {len(config.research_topics)} research topics")

    # 2. Initialize state manager
    logger.info("Step 2/7: Initializing state manager...")
    state = StateManager(state_dir=config.state_dir)
    logger.info(f"  Seen papers: {state.seen_count}")

    # 3. Extract keywords for each topic and search arXiv
    # CRITICAL: Track which topic produced each paper so analysis only scores
    # papers against the topic that found them (not all topics).
    logger.info("Step 3/7: Searching arXiv...")
    papers_by_topic: dict[str, list[Paper]] = defaultdict(list)

    from openai import OpenAI
    llm_client = OpenAI(
        api_key=os.environ.get(config.llm.api_key_env, ""),
        base_url=config.llm.base_url,
        timeout=60.0,
    )

    arxiv_source = ArxivSource()

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

        # Search arXiv
        if not config.sources.arxiv.enabled and (not topic.sources.arxiv.enabled):
            logger.info(f"    arXiv disabled for topic {topic.name}, skipping")
            continue

        try:
            query = SearchQuery(
                topic_name=topic.name,
                source="arxiv",
                keywords=keywords,
                timeframe_hours=config.search_timeframe_hours,
                max_results=topic.sources.arxiv.max_results or config.sources.arxiv.max_results,
            )
            papers = await arxiv_source.search(query)
            logger.info(f"    Found {len(papers)} papers from arXiv")
            papers_by_topic[topic.name].extend(papers)
        except Exception as e:
            error_msg = f"arXiv search failed for topic '{topic.name}': {e}"
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
    logger.info(f"Step 4/7: Deduplicating {len(all_papers)} papers...")
    all_papers = deduplicate_papers(all_papers)
    all_papers = state.filter_new(all_papers)
    logger.info(f"  After dedup + seen filter: {len(all_papers)} new papers")

    if not all_papers:
        logger.info("No new papers after filtering")
        return stats

    # Rebuild papers_by_topic with only the new papers that remain after dedup+filter.
    # A paper searched under Topic A stays associated with Topic A only.
    new_paper_ids = {p.paper_id for p in all_papers}
    filtered_by_topic: dict[str, list[Paper]] = defaultdict(list)
    for topic_name, topic_papers in papers_by_topic.items():
        for p in topic_papers:
            if p.paper_id in new_paper_ids:
                filtered_by_topic[topic_name].append(p)

    # 5. Fetch PDFs and extract text
    logger.info(f"Step 5/7: Fetching PDFs for {len(all_papers)} papers...")
    async with httpx.AsyncClient() as client:
        # Use semaphore to limit concurrent downloads
        sem = asyncio.Semaphore(5)
        async def fetch_with_sem(paper):
            async with sem:
                await fetch_and_enrich_paper(paper, client)

        await asyncio.gather(*[fetch_with_sem(p) for p in all_papers])

    full_text_count = sum(1 for p in all_papers if p.text_source == "full_text")
    logger.info(f"  {full_text_count} papers with full text, {len(all_papers) - full_text_count} with abstract only")

    # 6. AI Analysis (per topic -- only analyze papers found under that topic)
    # CRITICAL: Each paper is analyzed ONLY against the topic that found it.
    # This prevents duplicate entries and inflated stats from re-analyzing the
    # same paper against every topic.
    logger.info("Step 6/7: Running AI analysis...")
    all_analyzed: list[AnalyzedPaper] = []

    for topic in config.research_topics:
        topic_papers = filtered_by_topic.get(topic.name, [])
        if not topic_papers:
            continue

        try:
            analyzer = PaperAnalyzer(
                llm_config=config.llm,
                thresholds=topic.relevance_thresholds,
            )
            analyzed = analyzer.analyze_papers(topic_papers, topic.description)
            for ap in analyzed:
                ap.topic_name = topic.name
            all_analyzed.extend(analyzed)
        except Exception as e:
            error_msg = f"Analysis failed for topic '{topic.name}': {e}"
            logger.error(error_msg)
            stats["errors"].append(error_msg)
            continue  # Continue with other topics

    # 7. Send notification and save state
    logger.info("Step 7/7: Sending notification and saving state...")
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
