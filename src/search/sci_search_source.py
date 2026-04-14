"""sci_search adapter using the Supabase Edge Function API.

Calls the user's custom sci_search API (Supabase Edge Function) to find
relevant papers. Requires SCI_SEARCH_API_TOKEN environment variable.

Rate limiting: conservative 3 concurrent requests with 1.5s inter-request delay.
Uses tenacity for retry on transient failures (timeout, 5xx).
"""

import asyncio
import hashlib
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
MAX_CONCURRENT_REQUESTS = 3
INTER_REQUEST_DELAY = 1.5  # seconds between requests

# Default API URL (overridable via env var)
DEFAULT_API_URL = "https://qyyqlnwqwgvzxnccnbgm.supabase.co/functions/v1/sci_search"


class SciSearchSource(SearchSource):
    """sci_search adapter for the Supabase Edge Function API.

    For each keyword in SearchQuery.keywords, sends a POST request with
    the keyword and topK limit. Multiple keyword searches execute concurrently
    via asyncio.gather() with a semaphore limiting concurrent requests.

    If SCI_SEARCH_API_TOKEN is not set, search() returns an empty list
    (graceful degradation).
    """

    def __init__(self):
        self._api_token = os.environ.get("SCI_SEARCH_API_TOKEN", "")
        self._api_url = os.environ.get("SCI_SEARCH_API_URL", DEFAULT_API_URL)
        if not self._api_token:
            logger.warning(
                "SCI_SEARCH_API_TOKEN not set. SciSearchSource will return empty results."
            )

    @property
    def name(self) -> str:
        return "sci_search"

    async def search(self, query: SearchQuery) -> list[Paper]:
        """Search sci_search for papers matching the query keywords.

        Runs one POST request per keyword in parallel, then deduplicates
        results by paper_id. Filters by published_date within the query timeframe.

        Args:
            query: SearchQuery with keywords, timeframe_hours, and max_results.

        Returns:
            Deduplicated list of Paper objects from sci_search.
        """
        if not self._api_token:
            logger.warning("SCI_SEARCH_API_TOKEN not configured, returning empty results")
            return []

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        all_papers: list[Paper] = []
        seen_ids: set[str] = set()

        async def _search_keyword(keyword: str) -> list[Paper]:
            async with semaphore:
                papers = await self._search_single_keyword(keyword, query)
                # Inter-request delay to respect rate limits
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
                logger.error(f"sci_search keyword search failed: {result}")
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
            f"sci_search returned {len(all_papers)} unique papers "
            f"for {len(query.keywords)} keywords"
        )
        return all_papers

    async def _search_single_keyword(self, keyword: str, query: SearchQuery) -> list[Paper]:
        """Execute a single keyword search against the sci_search API.

        Args:
            keyword: Single search keyword/phrase.
            query: Parent SearchQuery for max_results limit.

        Returns:
            List of Paper objects for this keyword.
        """
        payload = {"query": keyword, "topK": query.max_results}
        headers = {
            "x-api-key": self._api_token,
            "Content-Type": "application/json",
        }

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
        )
        async def _fetch():
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self._api_url, json=payload, headers=headers)
                # Only raise for 5xx (server errors); 4xx are client errors, don't retry
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
            logger.error(f"sci_search request failed for '{keyword}': {e}")
            return []

        # Response can be a list directly or {"data": [...]}
        items = data if isinstance(data, list) else data.get("data", [])
        if not isinstance(items, list):
            logger.warning(f"Unexpected sci_search response format for '{keyword}'")
            return []

        papers = []
        for item in items:
            if not isinstance(item, dict):
                continue
            paper = self._convert_item(item)
            if paper:
                papers.append(paper)

        logger.info(f"sci_search for '{keyword}' returned {len(papers)} results")
        return papers

    def _convert_item(self, item: dict) -> Optional[Paper]:
        """Convert a sci_search API result item to our Paper model.

        Args:
            item: Raw dict from sci_search API response.

        Returns:
            Paper object, or None if essential fields are missing.
        """
        try:
            title = (item.get("title") or "").strip()
            if not title:
                return None

            # paper_id: DOI > S2 paperId > hash of title
            doi = item.get("doi") or item.get("externalIds", {}).get("DOI")
            paper_id: str
            if doi:
                paper_id = doi.strip()
            elif item.get("paperId"):
                paper_id = item["paperId"]
            else:
                paper_id = hashlib.sha256(title.lower().encode()).hexdigest()[:16]

            # Authors: may be list of strings or list of dicts with "name" key
            raw_authors = item.get("authors", [])
            authors: list[str] = []
            if isinstance(raw_authors, list):
                for a in raw_authors:
                    if isinstance(a, str):
                        authors.append(a)
                    elif isinstance(a, dict) and "name" in a:
                        authors.append(a["name"])

            # PDF URL from openAccessPdf if present
            pdf_url = None
            oa_pdf = item.get("openAccessPdf")
            if isinstance(oa_pdf, dict) and oa_pdf.get("url"):
                pdf_url = oa_pdf["url"]

            # Published date
            published_date = self._parse_date(item)

            # DOI cleanup
            clean_doi = None
            if doi:
                clean_doi = doi.replace("https://doi.org/", "").strip()

            return Paper(
                paper_id=paper_id,
                title=title,
                abstract=item.get("abstract"),
                authors=authors,
                doi=clean_doi,
                source="sci_search",
                source_url=item.get("url"),
                pdf_url=pdf_url,
                published_date=published_date,
            )
        except Exception as e:
            logger.warning(f"Failed to parse sci_search item: {e}")
            return None

    def _parse_date(self, item: dict) -> Optional[datetime]:
        """Parse publication date from sci_search item.

        Tries publicationDate first, then year field.
        """
        pub_date_str = item.get("publicationDate")
        if pub_date_str:
            try:
                return datetime.strptime(str(pub_date_str)[:10], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass

        year = item.get("year")
        if year:
            try:
                return datetime(int(year), 1, 1, tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        return None
