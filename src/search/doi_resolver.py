"""DOI metadata enrichment via content negotiation.

Resolves a DOI to enriched metadata (title, authors, abstract, published date)
using CrossRef's content negotiation API (doi.org with citeproc+json).

This fills gaps for papers that come from search sources with incomplete metadata,
improving deduplication accuracy (DOI-based) and analysis quality.

Key design:
- Graceful: never crashes, only fills missing fields
- Retry: 2 attempts with exponential backoff on transient failures
- Batch: concurrent enrichment with semaphore-limited parallelism
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.search.models import Paper

logger = logging.getLogger(__name__)

DOI_TIMEOUT_SECONDS = 15
DOI_BASE_URL = "https://doi.org"


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
)
async def _fetch_citeproc(doi: str, client: httpx.AsyncClient) -> dict:
    """Fetch citeproc+json metadata for a DOI.

    Args:
        doi: DOI string (e.g. "10.1234/abcd").
        client: httpx AsyncClient for making the request.

    Returns:
        Parsed JSON dict from CrossRef content negotiation.

    Raises:
        httpx.TimeoutException or httpx.HTTPStatusError for retry to catch.
    """
    response = await client.get(
        f"{DOI_BASE_URL}/{doi}",
        headers={"Accept": "application/citeproc+json"},
        timeout=DOI_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.json()


def _parse_authors(author_list: list[dict]) -> list[str]:
    """Parse citeproc author list into 'Given Family' strings."""
    result = []
    for author in author_list:
        given = author.get("given", "")
        family = author.get("family", "")
        name = f"{given} {family}".strip()
        if name:
            result.append(name)
    return result


def _parse_date(date_parts: Optional[dict]) -> Optional[datetime]:
    """Parse citeproc date-parts into datetime.

    citeproc format: {"date-parts": [[YYYY, MM, DD]]}
    Month and day may be missing.
    """
    if not date_parts:
        return None
    parts = date_parts.get("date-parts", [[None]])[0]
    if not parts or parts[0] is None:
        return None
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 and parts[1] is not None else 1
    day = int(parts[2]) if len(parts) > 2 and parts[2] is not None else 1
    try:
        return datetime(year, month, day)
    except (ValueError, OverflowError):
        return None


async def enrich_paper_from_doi(paper: Paper, client: httpx.AsyncClient) -> None:
    """Enrich a paper's missing metadata fields via DOI content negotiation.

    Mutates the Paper object in place, only filling fields that are currently
    empty/missing. If paper.doi is None or all fields are already populated,
    returns immediately without making any HTTP request.

    Args:
        paper: Paper object to enrich. Must have paper.doi set for enrichment.
        client: httpx AsyncClient for making HTTP requests.
    """
    if paper.doi is None:
        return

    # Check if enrichment is needed
    has_title = bool(paper.title and paper.title.strip())
    has_abstract = bool(paper.abstract and paper.abstract.strip())
    has_authors = bool(paper.authors)
    if has_title and has_abstract and has_authors:
        return

    try:
        data = await _fetch_citeproc(paper.doi, client)
    except Exception as e:
        logger.warning(f"DOI content negotiation failed for {paper.doi}: {e}")
        return

    enriched_count = 0

    if not has_title:
        title = data.get("title")
        if title and title.strip():
            paper.title = title.strip()
            enriched_count += 1

    if not has_abstract:
        abstract = data.get("abstract")
        if abstract and abstract.strip():
            paper.abstract = abstract.strip()
            enriched_count += 1

    if not has_authors:
        author_list = data.get("author", [])
        parsed = _parse_authors(author_list)
        if parsed:
            paper.authors = parsed
            enriched_count += 1

    if not paper.published_date:
        pub_date = _parse_date(data.get("published-print")) or _parse_date(
            data.get("published-online")
        )
        if pub_date:
            paper.published_date = pub_date
            enriched_count += 1

    if not paper.source_url:
        url = data.get("URL")
        if url:
            paper.source_url = url
            enriched_count += 1

    if enriched_count > 0:
        logger.info(f"Enriched paper {paper.doi} with {enriched_count} fields from DOI content negotiation")


async def enrich_papers_batch(papers: list[Paper], client: httpx.AsyncClient) -> None:
    """Enrich all papers that need DOI resolution, concurrently.

    Uses a semaphore to limit concurrent requests to 5, preventing rate-limiting.
    Individual failures are logged but do not affect other papers.

    Args:
        papers: List of Paper objects to potentially enrich.
        client: httpx AsyncClient for making HTTP requests.
    """
    semaphore = asyncio.Semaphore(5)

    async def _enrich_with_semaphore(paper: Paper) -> None:
        async with semaphore:
            try:
                await enrich_paper_from_doi(paper, client)
            except Exception as e:
                logger.warning(f"Unexpected error enriching paper {paper.paper_id}: {e}")

    results = await asyncio.gather(
        *[_enrich_with_semaphore(p) for p in papers],
        return_exceptions=True,
    )

    enriched = sum(
        1
        for r, p in zip(results, papers)
        if not isinstance(r, Exception) and p.doi is not None
        and (bool(p.title and p.title.strip()) and bool(p.abstract and p.abstract.strip()))
    )
    total_with_doi = sum(1 for p in papers if p.doi is not None)
    logger.info(f"Enriched {enriched}/{total_with_doi} papers from DOI content negotiation")
