"""Search layer: source adapters, data models, and deduplication."""

from src.search.models import Paper, SearchQuery, AnalysisResult, AnalyzedPaper, RelevanceTier
from src.search.sci_search_source import SciSearchSource

__all__ = [
    "Paper",
    "SearchQuery",
    "AnalysisResult",
    "AnalyzedPaper",
    "RelevanceTier",
    "SciSearchSource",
]
