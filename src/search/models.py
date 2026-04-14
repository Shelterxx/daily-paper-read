"""Unified data models for the literature search pipeline.

This module defines the core data structures used across all pipeline stages:
- Paper: normalized paper representation from any search source
- SearchQuery: a search query for one topic + source combination
- AnalysisResult: AI analysis output for a single paper
- AnalyzedPaper: paper combined with its analysis result
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class RelevanceTier(str, Enum):
    """Relevance tier classification based on score thresholds."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Paper(BaseModel):
    """Unified paper model from any search source.

    All fields except paper_id, title, and source are optional to handle
    varying metadata quality across sources. Each source adapter normalizes
    its raw results into this common schema.
    """
    paper_id: str = Field(description="Unique ID: arXiv ID, DOI, or generated hash")
    title: str
    abstract: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    doi: Optional[str] = None
    source: str = Field(description="Source name: arxiv, pubmed, openalex, etc.")
    source_url: Optional[str] = None
    pdf_url: Optional[str] = None
    published_date: Optional[datetime] = None
    full_text: Optional[str] = None
    text_source: str = Field(default="abstract", description="Where text came from: abstract or full_text")

    @property
    def dedup_key(self) -> str:
        """Deterministic key for deduplication: DOI if present, else normalized title hash.

        Per SRCH-06: dedup by DOI first (most reliable), fallback to SHA256
        of normalized title when DOI is missing.
        """
        import hashlib
        if self.doi:
            return f"doi:{self.doi.lower().strip()}"
        normalized = self.title.lower().strip().replace(" ", "")
        h = hashlib.sha256(normalized.encode()).hexdigest()[:16]
        return f"title:{h}"


class SearchQuery(BaseModel):
    """A search query for one topic + source combination.

    Created from ResearchTopic config, one SearchQuery per topic-source pair.
    """
    topic_name: str
    source: str
    keywords: list[str]
    timeframe_hours: int = 24
    max_results: int = 50


class AnalysisResult(BaseModel):
    """AI analysis result for a single paper.

    Tiered output based on relevance score:
    - High (7-10): full analysis with contributions and applications
    - Medium (4-6): summary + key contributions
    - Low (1-3): score + title + link only
    """
    relevance_score: int = Field(ge=1, le=10)
    tier: RelevanceTier
    summary: Optional[str] = None
    key_contributions: Optional[list[str]] = None
    potential_applications: Optional[list[str]] = None
    extracted_keywords: list[str] = Field(default_factory=list)
    scoring_reason: Optional[str] = None


class AnalyzedPaper(BaseModel):
    """Paper combined with its analysis result."""
    paper: Paper
    analysis: AnalysisResult
    topic_name: str
