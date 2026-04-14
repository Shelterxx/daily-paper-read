"""LLM-based keyword extraction from natural language research descriptions.

Extracts search keywords from a user's natural language description of their
research direction. Falls back to simple word extraction if LLM is unavailable.
"""

import json
import logging
import re
from typing import Optional

from openai import OpenAI

from src.analysis.prompts import KEYWORD_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


def extract_keywords(
    description: str,
    client: OpenAI,
    model: str = "claude-3-5-haiku-20241022",
) -> list[str]:
    """Extract search keywords from a natural language research description.

    If extraction fails, returns a fallback list derived from the description.

    Args:
        description: Natural language description of research direction.
        client: OpenAI-compatible client instance.
        model: Model name to use for extraction.

    Returns:
        List of keyword strings suitable for academic search queries.
    """
    prompt = KEYWORD_EXTRACTION_PROMPT.format(description=description)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.3,
        )
        content = response.choices[0].message.content or "{}"
        parsed = _safe_json_parse(content)
        keywords = parsed.get("keywords", [])
        if keywords and isinstance(keywords, list):
            logger.info(f"Extracted {len(keywords)} keywords: {keywords}")
            return keywords
    except Exception as e:
        logger.warning(f"Keyword extraction failed: {e}")

    # Fallback: split description into words, take longest meaningful ones
    words = re.findall(r'[A-Za-z][A-Za-z-]+[A-Za-z]', description)
    fallback = list(dict.fromkeys(words[:5]))  # deduplicate, take first 5
    logger.info(f"Using fallback keywords: {fallback}")
    return fallback


def _safe_json_parse(text: str) -> dict:
    """Parse JSON from LLM response, handling potential formatting issues.

    Tries direct JSON parse first, then extracts the first {...} block
    if the response contains extra text around the JSON.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}
