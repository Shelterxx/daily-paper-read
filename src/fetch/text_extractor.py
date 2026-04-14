"""PyMuPDF text extraction wrapper.

Extracts text content from PDF bytes using PyMuPDF (fitz). Handles multi-page
PDFs by concatenating all pages. Returns None on any failure so the pipeline
can fall back to abstract-only processing.
"""

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes) -> Optional[str]:
    """Extract text content from PDF bytes using PyMuPDF.

    Returns extracted text string, or None if extraction fails.
    Handles multi-page PDFs by concatenating all pages.

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        Extracted text string, or None if extraction fails or produces
        empty output.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not installed, cannot extract PDF text")
        return None

    try:
        doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
        text_parts = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if text.strip():
                text_parts.append(text.strip())

        doc.close()
        full_text = "\n\n".join(text_parts)

        if not full_text.strip():
            logger.warning("PDF text extraction produced empty output")
            return None

        return full_text
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return None
