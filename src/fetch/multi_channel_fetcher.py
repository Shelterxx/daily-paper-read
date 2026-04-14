"""Multi-channel PDF fetching with priority fallback chain.

For papers from multiple sources (not just arXiv), this module tries
several channels to obtain a full-text PDF before falling back to abstract:

Priority chain:
1. paper.pdf_url -- already set by search adapter (S2 openAccessPdf, OpenAlex oa_url)
2. Unpaywall API -- resolves open-access PDF URL from DOI
3. PMC (PubMed Central) -- direct download via PMC ID

Each channel failure is logged and the next channel is attempted.
Actual download+validation is delegated to fetch_pdf (magic bytes, size limit, retry).

Key design:
- Reuses fetch_pdf for all downloads (no duplicated validation logic)
- Minimum 100 chars extracted text threshold (same as pdf_fetcher)
- Graceful: all channel failures result in abstract fallback, never crashes
"""

import logging
import os
from typing import Optional

import httpx

from src.fetch.pdf_fetcher import fetch_pdf
from src.fetch.text_extractor import extract_text_from_pdf
from src.search.models import Paper

logger = logging.getLogger(__name__)

UNPAYWALL_TIMEOUT_SECONDS = 15
MIN_TEXT_LENGTH = 100


async def resolve_unpaywall_pdf_url(
    doi: str, client: httpx.AsyncClient
) -> Optional[str]:
    """Resolve open-access PDF URL via Unpaywall API.

    Unpaywall requires an email for API access. If UNPAYWALL_EMAIL env var
    is not set, returns None immediately.

    Args:
        doi: DOI string to look up.
        client: httpx AsyncClient for making the request.

    Returns:
        PDF URL string if found, None otherwise.
    """
    email = os.environ.get("UNPAYWALL_EMAIL")
    if not email:
        logger.debug("UNPAYWALL_EMAIL not set, skipping Unpaywall channel")
        return None

    try:
        response = await client.get(
            f"https://api.unpaywall.org/v2/{doi}?email={email}",
            timeout=UNPAYWALL_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
        data = response.json()

        best_oa = data.get("best_oa_location")
        if best_oa:
            pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")
            if pdf_url:
                logger.debug(f"Unpaywall resolved PDF URL for {doi}")
                return pdf_url

        logger.debug(f"Unpaywall found no OA PDF for {doi}")
        return None
    except Exception as e:
        logger.warning(f"Unpaywall lookup failed for {doi}: {e}")
        return None


async def resolve_pmc_pdf_url(pmid: str) -> Optional[str]:
    """Construct PMC PDF URL from a PubMed Central ID.

    The URL follows the pattern:
    https://www.ncbi.nlm.nih.gov/pmc/articles/{PMC_ID}/pdf/

    The actual download will validate via fetch_pdf (magic bytes check).

    Args:
        pmid: PMC ID, with or without "PMC" prefix.

    Returns:
        Constructed PDF URL string.
    """
    if not pmid:
        return None

    # Ensure PMC prefix
    pmc_id = pmid if pmid.startswith("PMC") else f"PMC{pmid}"
    return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"


async def _try_download_and_extract(
    url: str,
    paper: Paper,
    client: httpx.AsyncClient,
    channel_name: str,
) -> bool:
    """Attempt to download PDF from URL and extract text.

    Args:
        url: URL to download from.
        paper: Paper object to enrich.
        client: httpx AsyncClient.
        channel_name: Name of the channel for logging.

    Returns:
        True if full text was successfully extracted, False otherwise.
    """
    pdf_bytes = await fetch_pdf(url, client)
    if pdf_bytes:
        text = extract_text_from_pdf(pdf_bytes)
        if text and len(text.strip()) > MIN_TEXT_LENGTH:
            paper.full_text = text
            paper.text_source = "full_text"
            logger.info(f"Channel {channel_name} succeeded for {paper.title[:40]}")
            return True
        else:
            logger.info(
                f"Channel {channel_name} downloaded PDF but text extraction failed for {paper.title[:40]}"
            )
    else:
        logger.info(f"Channel {channel_name} failed for {paper.title[:40]}")
    return False


async def fetch_pdf_multi_channel(
    paper: Paper, client: httpx.AsyncClient
) -> None:
    """Fetch PDF for a paper using multiple channels with priority fallback.

    Tries channels in order:
    1. paper.pdf_url (already set by search adapter)
    2. Unpaywall API (if DOI available and UNPAYWALL_EMAIL set)
    3. PMC direct link (if PMC ID available)

    On first successful download with meaningful text extraction, sets
    paper.full_text and paper.text_source = "full_text" and returns.

    If all channels fail, sets paper.text_source = "abstract".

    Mutates the Paper object in place (same pattern as fetch_and_enrich_paper).

    Args:
        paper: Paper object to fetch PDF for.
        client: httpx AsyncClient for making HTTP requests.
    """
    # Channel 1: paper.pdf_url (set by search adapter from S2/OpenAlex/etc.)
    if paper.pdf_url:
        logger.info(f"Trying pdf_url channel for {paper.title[:40]}...")
        if await _try_download_and_extract(paper.pdf_url, paper, client, "pdf_url"):
            return

    # Channel 2: Unpaywall (DOI-based OA resolution)
    if paper.doi:
        logger.info(f"Trying Unpaywall channel for {paper.title[:40]}...")
        oa_url = await resolve_unpaywall_pdf_url(paper.doi, client)
        if oa_url:
            if await _try_download_and_extract(oa_url, paper, client, "unpaywall"):
                return

    # Channel 3: PMC (PubMed Central)
    # Papers from PubMed/PMC sources store PMC ID as paper_id
    pmc_id = None
    if paper.source in ("pubmed", "pmc") and paper.paper_id:
        pmc_id = paper.paper_id
    if pmc_id:
        logger.info(f"Trying PMC channel for {paper.title[:40]}...")
        pmc_url = await resolve_pmc_pdf_url(pmc_id)
        if pmc_url:
            if await _try_download_and_extract(pmc_url, paper, client, "pmc"):
                return

    # All channels failed -- fall back to abstract
    paper.text_source = "abstract"
    logger.info(f"All PDF channels failed, using abstract fallback for: {paper.title[:50]}")
