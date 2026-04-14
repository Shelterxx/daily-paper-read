"""Search layer: source adapters, data models, and deduplication."""

from src.search.models import Paper, SearchQuery, AnalysisResult, AnalyzedPaper, RelevanceTier
from src.search.sci_search_source import SciSearchSource
from src.search.openalex_source import OpenAlexSource
from src.search.semantic_scholar_source import SemanticScholarSource

__all__ = [
    "Paper",
    "SearchQuery",
    "AnalysisResult",
    "AnalyzedPaper",
    "RelevanceTier",
    "SciSearchSource",
    "OpenAlexSource",
    "SemanticScholarSource",
]
