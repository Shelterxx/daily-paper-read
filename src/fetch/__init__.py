"""Fetch layer: PDF download, multi-channel fetching, and text extraction."""

from src.fetch.pdf_fetcher import fetch_pdf, fetch_and_enrich_paper
from src.fetch.text_extractor import extract_text_from_pdf
from src.fetch.multi_channel_fetcher import fetch_pdf_multi_channel

__all__ = [
    "fetch_pdf",
    "fetch_and_enrich_paper",
    "extract_text_from_pdf",
    "fetch_pdf_multi_channel",
]
