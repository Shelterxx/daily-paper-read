"""Pydantic configuration models for the literature push system."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class LLMConfig(BaseModel):
    """LLM API configuration."""

    scoring_model: str = Field(
        default="claude-3-5-haiku-20241022",
        description="Model for batch relevance scoring",
    )
    analysis_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Model for deep analysis of high-relevance papers",
    )
    base_url: str = Field(
        default="https://api.anthropic.com/v1/",
        description="OpenAI-compatible API base URL",
    )
    api_key_env: str = Field(
        default="LLM_API_KEY",
        description="Environment variable name holding the API key",
    )
    max_tokens_per_call: int = Field(default=4096)


class SourceConfig(BaseModel):
    """Toggle and settings for a search source."""

    enabled: bool = True
    max_results: int = 50


class SourcesConfig(BaseModel):
    """All search source toggles."""

    arxiv: SourceConfig = Field(
        default_factory=lambda: SourceConfig(enabled=True, max_results=50)
    )


class NotificationConfig(BaseModel):
    """Notification channel settings."""

    feishu_webhook_env: str = Field(
        default="FEISHU_WEBHOOK_URL",
        description="Env var name for Feishu webhook URL",
    )
    language: str = Field(
        default="zh",
        description="Output language: zh, en, or mixed",
    )

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        allowed = {"zh", "en", "mixed"}
        if v not in allowed:
            raise ValueError(f"language must be one of {allowed}, got '{v}'")
        return v


class RelevanceThresholds(BaseModel):
    """Score cutoffs for tiered analysis."""

    high: int = Field(default=7, ge=1, le=10, description="Score >= this is high relevance")
    medium: int = Field(default=4, ge=1, le=10, description="Score >= this is medium relevance")


class ResearchTopic(BaseModel):
    """A single research topic with search configuration."""

    name: str = Field(description="Short name for this topic, e.g. 'LLM Reasoning'")
    description: str = Field(description="Natural language description of research direction")
    keywords: Optional[list[str]] = Field(
        default=None,
        description="Manual keywords override. If set, skip LLM extraction and use these directly.",
    )
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    max_push: int = Field(default=20, description="Max papers to push per topic per run")
    relevance_thresholds: RelevanceThresholds = Field(default_factory=RelevanceThresholds)


class AppConfig(BaseModel):
    """Root application configuration."""

    research_topics: list[ResearchTopic] = Field(
        min_length=1,
        description="At least one research topic required",
    )
    sources: SourcesConfig = Field(
        default_factory=SourcesConfig,
        description="Global source toggles (topic-level can override)",
    )
    llm: LLMConfig = Field(default_factory=LLMConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
    search_timeframe_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="How far back to search",
    )
    state_dir: str = Field(
        default="state",
        description="Directory for persistent state files",
    )
