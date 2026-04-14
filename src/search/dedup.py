"""Deduplication logic for papers from multiple search queries.

Per SRCH-06: deduplicate by DOI (primary) or title hash (fallback)
using the Paper.dedup_key property. Keeps first occurrence.
"""

from src.search.models import Paper


def deduplicate_papers(papers: list[Paper]) -> list[Paper]:
    """Remove duplicate papers by dedup_key, keeping first occurrence.

    Args:
        papers: List of Paper objects potentially containing duplicates
                from different search queries or sources.

    Returns:
        Deduplicated list preserving insertion order of first occurrences.
    """
    seen: set[str] = set()
    result: list[Paper] = []
    for paper in papers:
        key = paper.dedup_key
        if key not in seen:
            seen.add(key)
            result.append(paper)
    return result
