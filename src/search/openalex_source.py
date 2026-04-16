"""OpenAlex search adapter using the OpenAlex Works API.

Provides broad multi-disciplinary academic coverage. When OPENALEX_EMAIL
env var is set, uses the polite pool (10 req/s). Without it, uses the
standard pool (slower).

Rate limiting: 5 concurrent requests with 0.2s inter-request delay.
Uses tenacity for retry on transient failures (timeout, 5xx).
"""

import asyncio
import logging
import os
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
MAX_CONCURRENT_REQUESTS = 5
INTER_REQUEST_DELAY = 0.2  # seconds between requests

# API base URL
API_BASE_URL = "https://api.openalex.org/works"


def _reconstruct_abstract(inv_index: Optional[dict]) -> Optional[str]:
    """Reconstruct abstract text from OpenAlex inverted index format.

    OpenAlex stores abstracts as {"word": [pos1, pos2, ...]} mapping.
    This function rebuilds the original text by sorting words by position.

    Args:
        inv_index: OpenAlex abstract_inverted_index dict, or None.

    Returns:
        Reconstructed abstract string, or None if input is empty.
    """
    if not inv_index:
        return None
    positions: dict[int, str] = {}
    for word, pos_list in inv_index.items():
        for pos in pos_list:
            positions[pos] = word
    return " ".join(positions[k] for k in sorted(positions.keys()))


class OpenAlexSource(SearchSource):
    """OpenAlex search adapter for broad multi-disciplinary coverage.

    For each keyword in SearchQuery.keywords, sends a GET request to the
    OpenAlex Works API. Multiple keyword searches execute concurrently
    via asyncio.gather() with a semaphore limiting concurrent requests.

    Uses OPENALEX_EMAIL env var for polite pool access (10 req/s).
    """

    def __init__(self):
        self._email = os.environ.get("OPENALEX_EMAIL", "")
        if self._email:
            logger.info(f"OpenAlex using polite pool with email: {self._email}")
            self._concurrency = MAX_CONCURRENT_REQUESTS
        else:
            logger.info("OpenAlex using standard pool (set OPENALEX_EMAIL for faster access)")
            self._concurrency = 2  # Standard pool is heavily rate-limited

    @property
    def name(self) -> str:
        return "openalex"

    async def search(self, query: SearchQuery) -> list[Paper]:
        """Search OpenAlex for papers matching the query keywords.

        Runs one GET request per keyword in parallel, then deduplicates
        results by paper_id. Filters by publication_date within the query timeframe.

        Args:
            query: SearchQuery with keywords, timeframe_hours, and max_results.

        Returns:
            Deduplicated list of Paper objects from OpenAlex.
        """
        semaphore = asyncio.Semaphore(self._concurrency)
        all_papers: list[Paper] = []
        seen_ids: set[str] = set()

        async def _search_keyword(keyword: str) -> list[Paper]:
            async with semaphore:
                papers = await self._search_single_keyword(keyword, query)
                # Inter-request delay
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
                logger.error(f"OpenAlex keyword search failed: {result}")
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

        logger.info(
            f"OpenAlex returned {len(all_papers)} unique papers "
            f"for {len(query.keywords)} keywords"
        )
        return all_papers

    async def _search_single_keyword(self, keyword: str, query: SearchQuery) -> list[Paper]:
        """Execute a single keyword search against the OpenAlex Works API.

        Args:
            keyword: Single search keyword/phrase.
            query: Parent SearchQuery for max_results limit.

        Returns:
            List of Paper objects for this keyword.
        """
        today = datetime.now(timezone.utc)
        cutoff = today - timedelta(hours=query.timeframe_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")

        params = {
            "search": keyword,
            "per_page": min(query.max_results, 50),
            "sort": "publication_date:desc",
            "filter": f"from_publication_date:{cutoff_str},to_publication_date:{today_str},type:article|review",
        }

        # Polite pool: add mailto parameter for faster rate limits
        if self._email:
            params["mailto"] = self._email

        @retry(
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=2, min=4, max=60),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
        )
        async def _fetch():
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(API_BASE_URL, params=params)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.json()

        try:
            data = await _fetch()
        except Exception as e:
            logger.error(f"OpenAlex request failed for '{keyword}': {e}")
            return []

        results = data.get("results", [])
        if not isinstance(results, list):
            logger.warning(f"Unexpected OpenAlex response format for '{keyword}'")
            return []

        papers = []
        for work in results:
            if not isinstance(work, dict):
                continue
            paper = self._convert_work(work)
            if paper:
                papers.append(paper)

        logger.info(f"OpenAlex for '{keyword}' returned {len(papers)} results")
        return papers

    def _convert_work(self, work: dict) -> Optional[Paper]:
        """Convert an OpenAlex work object to our Paper model.

        Args:
            work: Raw dict from OpenAlex API response results.

        Returns:
            Paper object, or None if essential fields are missing.
        """
        try:
            # Title: OpenAlex uses "title" or "display_name"
            title = (work.get("title") or work.get("display_name") or "").strip()
            if not title:
                return None

            # paper_id: DOI (cleaned) > OpenAlex ID
            doi_raw = work.get("doi", "") or ""
            doi = doi_raw.replace("https://doi.org/", "").strip() if doi_raw else None

            if doi:
                paper_id = doi
            else:
                # Extract from OpenAlex ID like https://openalex.org/W12345
                oa_id = work.get("id", "")
                paper_id = oa_id.split("/")[-1] if oa_id else None
                if not paper_id:
                    return None

            # Abstract from inverted index
            abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

            # Authors from authorships
            authors: list[str] = []
            for authorship in work.get("authorships", []):
                try:
                    name = authorship.get("author", {}).get("display_name", "")
                    if name:
                        authors.append(name)
                except (AttributeError, TypeError):
                    continue

            # PDF URL from open_access
            pdf_url = None
            oa_info = work.get("open_access", {})
            if isinstance(oa_info, dict) and oa_info.get("oa_url"):
                pdf_url = oa_info["oa_url"]

            # Source URL: DOI URL or OpenAlex URL
            source_url = doi_raw if doi_raw else work.get("id")

            # Published date
            published_date = None
            pub_date_str = work.get("publication_date")
            if pub_date_str:
                try:
                    published_date = datetime.strptime(str(pub_date_str)[:10], "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    pass

            return Paper(
                paper_id=paper_id,
                title=title,
                abstract=abstract,
                authors=authors,
                doi=doi,
                source="openalex",
                source_url=source_url,
                pdf_url=pdf_url,
                published_date=published_date,
            )
        except Exception as e:
            logger.warning(f"Failed to parse OpenAlex work: {e}")
            return None
