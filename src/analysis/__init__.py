"""Analysis layer: AI-powered paper scoring, analysis, and keyword extraction."""

from src.analysis.keyword_extractor import extract_keywords

__all__ = ["extract_keywords"]

# PaperAnalyzer added in analyzer.py -- re-exported once available
try:
    from src.analysis.analyzer import PaperAnalyzer
    __all__.append("PaperAnalyzer")
except ImportError:
    pass
