"""Semantic Scholar search adapter using the S2 Graph API.

Provides strong CS research coverage. When S2_API_KEY env var is set,
uses authenticated access (1 req/sec). Without it, uses anonymous access
(100 req/5min).

Rate limiting: 2 concurrent requests with 3.0s delay (anonymous) or
1.0s delay (authenticated). Uses tenacity for retry with 3 attempts
(S2 is flakier than other sources).
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
MAX_CONCURRENT_REQUESTS = 2
INTER_REQUEST_DELAY_ANON = 3.0  # seconds, conservative without API key
INTER_REQUEST_DELAY_AUTH = 1.0  # seconds, with API key

# API base URL
API_BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

# Fields to request from the API
FIELDS = (
    "paperId,title,abstract,authors,year,citationCount,"
    "url,externalIds,publicationDate,openAccessPdf"
)


class SemanticScholarSource(SearchSource):
    """Semantic Scholar search adapter for strong CS research coverage.

    For each keyword in SearchQuery.keywords, sends a GET request to the
    S2 Graph API. Multiple keyword searches execute concurrently via
    asyncio.gather() with a semaphore limiting concurrent requests.

    Uses S2_API_KEY env var for higher rate limits if available.
    """

    def __init__(self):
        self._api_key = os.environ.get("S2_API_KEY", "")
        self._has_key = bool(self._api_key)
        self._delay = INTER_REQUEST_DELAY_AUTH if self._has_key else INTER_REQUEST_DELAY_ANON
        if self._has_key:
            logger.info("Semantic Scholar using authenticated access (1 req/sec)")
        else:
            logger.info(
                "Semantic Scholar using anonymous access "
                "(100 req/5min). Set S2_API_KEY for higher limits."
            )

    @property
    def name(self) -> str:
        return "semantic_scholar"

    async def search(self, query: SearchQuery) -> list[Paper]:
        """Search Semantic Scholar for papers matching the query keywords.

        Runs one GET request per keyword in parallel, then deduplicates
        results by paper_id. Filters by publicationDate within the query timeframe.

        Args:
            query: SearchQuery with keywords, timeframe_hours, and max_results.

        Returns:
            Deduplicated list of Paper objects from Semantic Scholar.
        """
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        all_papers: list[Paper] = []
        seen_ids: set[str] = set()

        async def _search_keyword(keyword: str) -> list[Paper]:
            async with semaphore:
                papers = await self._search_single_keyword(keyword, query)
                # Inter-request delay
                await asyncio.sleep(self._delay)
                return papers

        # Run all keyword searches concurrently
        results = await asyncio.gather(
            *[_search_keyword(kw) for kw in query.keywords],
            return_exceptions=True,
        )

        cutoff_date = datetime.now(timezone.utc) - timedelta(hours=query.timeframe_hours)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Semantic Scholar keyword search failed: {result}")
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
            f"Semantic Scholar returned {len(all_papers)} unique papers "
            f"for {len(query.keywords)} keywords"
        )
        return all_papers

    async def _search_single_keyword(self, keyword: str, query: SearchQuery) -> list[Paper]:
        """Execute a single keyword search against the Semantic Scholar API.

        Args:
            keyword: Single search keyword/phrase.
            query: Parent SearchQuery for max_results limit.

        Returns:
            List of Paper objects for this keyword.
        """
        # S2 uses year range, not date range
        current_year = datetime.now().year
        cutoff_year = current_year - max(1, query.timeframe_hours // (365 * 24))

        params = {
            "query": keyword,
            "limit": min(query.max_results, 100),
            "fields": FIELDS,
            "year": f"{cutoff_year}-{current_year}",
        }

        headers: dict[str, str] = {}
        if self._api_key:
            headers["x-api-key"] = self._api_key

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
        )
        async def _fetch():
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(
                    API_BASE_URL, params=params, headers=headers
                )
                # Handle 429 rate limit with longer wait
                if response.status_code == 429:
                    raise httpx.HTTPStatusError(
                        f"Rate limited (429)",
                        request=response.request,
                        response=response,
                    )
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
            logger.error(f"Semantic Scholar request failed for '{keyword}': {e}")
            return []

        items = data.get("data", [])
        if not isinstance(items, list):
            logger.warning(f"Unexpected Semantic Scholar response format for '{keyword}'")
            return []

        papers = []
        for paper_data in items:
            if not isinstance(paper_data, dict):
                continue
            paper = self._convert_paper(paper_data)
            if paper:
                papers.append(paper)

        logger.info(f"Semantic Scholar for '{keyword}' returned {len(papers)} results")
        return papers

    def _convert_paper(self, paper_data: dict) -> Optional[Paper]:
        """Convert a Semantic Scholar paper object to our Paper model.

        Args:
            paper_data: Raw dict from Semantic Scholar API response data.

        Returns:
            Paper object, or None if essential fields are missing.
        """
        try:
            title = (paper_data.get("title") or "").strip()
            if not title:
                return None

            # paper_id: DOI (from externalIds) > S2 paperId
            external_ids = paper_data.get("externalIds", {}) or {}
            doi = external_ids.get("DOI")
            if doi:
                # Clean DOI (remove URL prefix if present)
                clean_doi = doi.replace("https://doi.org/", "").strip()
                paper_id = clean_doi
            else:
                paper_id = paper_data.get("paperId", "")
                clean_doi = None
                if not paper_id:
                    return None

            # Authors
            authors: list[str] = []
            for author in paper_data.get("authors", []):
                name = author.get("name", "")
                if name:
                    authors.append(name)

            # PDF URL from openAccessPdf
            pdf_url = None
            oa_pdf = paper_data.get("openAccessPdf")
            if isinstance(oa_pdf, dict) and oa_pdf.get("url"):
                pdf_url = oa_pdf["url"]

            # Published date
            published_date = None
            pub_date_str = paper_data.get("publicationDate")
            if pub_date_str:
                try:
                    published_date = datetime.strptime(
                        str(pub_date_str)[:10], "%Y-%m-%d"
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            return Paper(
                paper_id=paper_id,
                title=title,
                abstract=paper_data.get("abstract"),
                authors=authors,
                doi=clean_doi,
                source="semantic_scholar",
                source_url=paper_data.get("url"),
                pdf_url=pdf_url,
                published_date=published_date,
            )
        except Exception as e:
            logger.warning(f"Failed to parse Semantic Scholar paper: {e}")
            return None
