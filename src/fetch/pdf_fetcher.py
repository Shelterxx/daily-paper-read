"""Async PDF download with retry and graceful fallback.

Downloads PDFs from open-access sources (primarily arXiv) and validates
the response before returning bytes. On any failure, returns None so
the pipeline can fall back to abstract-only processing.

Key safety features per PITFALLS.md:
- PDF magic bytes validation prevents processing non-PDF responses
- 50MB size limit prevents memory issues in GitHub Actions
- 30-second timeout per download
- tenacity retry on transient HTTP failures
"""

import logging
from typing import Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)

PDF_TIMEOUT_SECONDS = 30
MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50MB
PDF_MAGIC_BYTES = b"%PDF"


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
)
async def fetch_pdf(url: str, client: httpx.AsyncClient) -> Optional[bytes]:
    """Download PDF from URL. Returns bytes if successful, None on failure.

    Validates response is actually a PDF by checking magic bytes.
    Respects size limits to avoid memory issues in GitHub Actions.

    Args:
        url: Direct URL to a PDF file.
        client: httpx AsyncClient for making the request.

    Returns:
        PDF bytes on success, None on any failure.
    """
    try:
        response = await client.get(url, timeout=PDF_TIMEOUT_SECONDS, follow_redirects=True)
        response.raise_for_status()

        content = response.content
        if len(content) > MAX_PDF_SIZE_BYTES:
            logger.warning(f"PDF too large ({len(content)} bytes): {url}")
            return None

        if not content[:4] == PDF_MAGIC_BYTES:
            logger.warning(f"Response is not a valid PDF: {url}")
            return None

        logger.info(f"Downloaded PDF ({len(content)} bytes): {url}")
        return content
    except httpx.TimeoutException:
        logger.warning(f"PDF download timeout: {url}")
        return None
    except httpx.HTTPStatusError as e:
        logger.warning(f"PDF download HTTP {e.response.status_code}: {url}")
        return None
    except Exception as e:
        logger.warning(f"PDF download failed: {url} - {e}")
        return None


async def fetch_and_enrich_paper(paper, client: httpx.AsyncClient) -> None:
    """Attempt to fetch PDF for a paper and enrich it with full_text.

    Mutates paper.full_text and paper.text_source in place.
    If PDF fetch or text extraction fails, paper.text_source remains 'abstract'.
    This is the core graceful fallback pattern: the pipeline always continues.

    Args:
        paper: Paper object with pdf_url field set.
        client: httpx AsyncClient for making HTTP requests.
    """
    if not paper.pdf_url:
        paper.text_source = "abstract"
        return

    pdf_bytes = await fetch_pdf(paper.pdf_url, client)
    if pdf_bytes:
        from src.fetch.text_extractor import extract_text_from_pdf
        text = extract_text_from_pdf(pdf_bytes)
        if text and len(text.strip()) > 100:  # Minimum meaningful text
            paper.full_text = text
            paper.text_source = "full_text"
            return

    paper.text_source = "abstract"
    logger.info(f"Using abstract fallback for: {paper.title[:50]}")
