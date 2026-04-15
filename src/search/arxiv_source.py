"""ArXiv search adapter using the arxiv library with feedparser fallback.

Primary interface: arxiv library (>=2.4.0) for structured search.
Fallback: feedparser + httpx for raw Atom feed parsing when the library
encounters unexpected errors.

Rate limiting: arXiv allows ~1 request/second. This adapter uses a semaphore
to limit concurrent requests to 2 and includes inter-request delays.
"""

import asyncio
import logging
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.search.base import SearchSource
from src.search.models import Paper, SearchQuery

logger = logging.getLogger(__name__)

# Rate limiting constants
MAX_CONCURRENT_REQUESTS = 2
INTER_REQUEST_DELAY = 1.0  # seconds between requests to respect arXiv rate limit


class ArxivSource(SearchSource):
    """ArXiv search adapter.

    Uses the arxiv library as primary search interface. Falls back to
    feedparser + httpx for raw Atom feed parsing on library errors.

    For each keyword in the SearchQuery.keywords list, runs a separate
    search. Multiple keyword searches execute concurrently via asyncio.gather()
    with a semaphore limiting to MAX_CONCURRENT_REQUESTS.
    """

    def __init__(self):
        import arxiv
        self._client = arxiv.Client()

    @property
    def name(self) -> str:
        return "arxiv"

    async def search(self, query: SearchQuery) -> list[Paper]:
        """Search arXiv for papers matching the query keywords.

        Runs one search per keyword in parallel, then deduplicates results
        by paper_id. Filters by published_date within the query timeframe.

        Args:
            query: SearchQuery with keywords, timeframe_hours, and max_results.

        Returns:
            Deduplicated list of Paper objects from arXiv.
        """
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        all_papers: list[Paper] = []
        seen_ids: set[str] = set()

        async def _search_keyword(keyword: str) -> list[Paper]:
            async with semaphore:
                papers = await self._search_single_keyword(keyword, query)
                # Inter-request delay to respect arXiv rate limit
                await asyncio.sleep(INTER_REQUEST_DELAY)
                return papers

        # Run all keyword searches concurrently
        results = await asyncio.gather(
            *[_search_keyword(kw) for kw in query.keywords],
            return_exceptions=True,
        )

        cutoff_date = datetime.now(timezone.utc) - timedelta(hours=query.timeframe_hours)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Keyword search failed: {result}")
                continue
            for paper in result:
                if paper.paper_id not in seen_ids:
                    # Filter by timeframe
                    if paper.published_date and paper.published_date.tzinfo is None:
                        paper.published_date = paper.published_date.replace(tzinfo=timezone.utc)
                    if paper.published_date and paper.published_date < cutoff_date:
                        continue
                    seen_ids.add(paper.paper_id)
                    all_papers.append(paper)

        logger.info(f"ArXiv search returned {len(all_papers)} unique papers for {len(query.keywords)} keywords")
        return all_papers

    async def _search_single_keyword(self, keyword: str, query: SearchQuery) -> list[Paper]:
        """Execute a single keyword search against arXiv.

        Tries the arxiv library first, falls back to feedparser on failure.

        Args:
            keyword: Single search keyword/phrase.
            query: Parent SearchQuery for max_results limit.

        Returns:
            List of Paper objects for this keyword.
        """
        try:
            return await self._search_with_library(keyword, query)
        except Exception as e:
            logger.warning(f"arxiv library search failed for '{keyword}': {e}. Trying feedparser fallback.")
            return await self._search_with_feedparser(keyword, query)

    async def _search_with_library(self, keyword: str, query: SearchQuery) -> list[Paper]:
        """Search using the arxiv library (primary method).

        Compatible with arxiv>=2.4 (Query API) and arxiv>=3.0 (Search API).
        """
        import arxiv

        # arxiv 3.0+ uses Search; arxiv 2.x uses Query
        SearchClass = getattr(arxiv, "Search", None) or getattr(arxiv, "Query", None)
        if SearchClass is None:
            raise AttributeError("Neither arxiv.Search nor arxiv.Query found")

        search = SearchClass(
            query=keyword,
            max_results=query.max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        # Run the synchronous arxiv client in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        raw_results = await loop.run_in_executor(
            None,
            lambda: list(self._client.results(search)),
        )

        papers = []
        for result in raw_results:
            paper = self._convert_library_result(result)
            papers.append(paper)

        logger.info(f"ArXiv library search for '{keyword}' returned {len(papers)} results")
        return papers

    def _convert_library_result(self, result) -> Paper:
        """Convert an arxiv library result to our Paper model."""
        arxiv_id = result.entry_id.split("/")[-1]
        # Handle versioned IDs like 2301.00001v1
        if "v" in arxiv_id:
            base_id = arxiv_id.rsplit("v", 1)[0]
        else:
            base_id = arxiv_id

        return Paper(
            paper_id=base_id,
            title=result.title.replace("\n", " "),
            abstract=result.summary.replace("\n", " ") if result.summary else None,
            authors=[a.name for a in result.authors] if result.authors else [],
            doi=result.doi,
            source="arxiv",
            source_url=f"https://arxiv.org/abs/{base_id}",
            pdf_url=f"https://arxiv.org/pdf/{base_id}",
            published_date=result.published,
        )

    async def _search_with_feedparser(self, keyword: str, query: SearchQuery) -> list[Paper]:
        """Fallback search using feedparser + httpx for raw Atom feed parsing.

        Used when the arxiv library encounters unexpected errors.
        """
        import feedparser

        encoded_kw = urllib.parse.quote(keyword)
        url = (
            f"https://export.arxiv.org/api/query?search_query={encoded_kw}"
            f"&sortBy=submittedDate&sortOrder=descending&max_results={query.max_results}"
        )

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
        )
        async def _fetch():
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                return response.text

        try:
            xml_text = await _fetch()
        except Exception as e:
            logger.error(f"Feedparser fallback also failed for '{keyword}': {e}")
            return []

        feed = feedparser.parse(xml_text)
        papers = []
        for entry in feed.entries:
            paper = self._convert_feed_entry(entry)
            if paper:
                papers.append(paper)

        logger.info(f"ArXiv feedparser fallback for '{keyword}' returned {len(papers)} results")
        return papers

    def _convert_feed_entry(self, entry) -> Optional[Paper]:
        """Convert a feedparser entry to our Paper model."""
        try:
            entry_id = entry.get("id", "")
            # Extract arXiv ID from entry URL
            arxiv_id = entry_id.split("/")[-1]
            if not arxiv_id or arxiv_id == "":
                return None
            # Handle versioned IDs
            if "v" in arxiv_id:
                base_id = arxiv_id.rsplit("v", 1)[0]
            else:
                base_id = arxiv_id

            title = entry.get("title", "").replace("\n", " ").strip()
            if not title:
                return None

            summary = entry.get("summary", "").replace("\n", " ").strip() or None

            # Extract authors
            authors = []
            for author in (entry.get("authors") or []):
                name = (author.get("name") or "").strip()
                if name:
                    authors.append(name)

            # Extract DOI if present
            doi = None
            for link in (entry.get("links") or []):
                if link.get("title") == "doi":
                    doi = link.get("href", "").replace("https://doi.org/", "")
                    break

            # Parse published date
            published_str = entry.get("published", "")
            published_date = None
            if published_str:
                try:
                    published_date = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                except ValueError:
                    try:
                        published_date = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%S%z")
                    except ValueError:
                        pass

            return Paper(
                paper_id=base_id,
                title=title,
                abstract=summary,
                authors=authors,
                doi=doi,
                source="arxiv",
                source_url=f"https://arxiv.org/abs/{base_id}",
                pdf_url=f"https://arxiv.org/pdf/{base_id}",
                published_date=published_date,
            )
        except Exception as e:
            logger.warning(f"Failed to parse feed entry: {e}")
            return None
