"""Two-stage paper analysis pipeline.

Stage 1: Batch relevance scoring using fast model (Haiku).
Stage 2: Deep analysis of high-relevance papers using capable model (Sonnet).

Uses OpenAI-compatible API (openai SDK + custom base_url) for multi-model
support per CONTEXT.md decisions. Cost control: only high-relevance papers
consume tokens for deep analysis (PITFALLS.md #4).
"""

import json
import logging
import os
import re
from typing import Optional

from openai import OpenAI

from src.analysis.prompts import SCORING_PROMPT, ANALYSIS_PROMPT
from src.config.models import LLMConfig, RelevanceThresholds
from src.search.models import Paper, AnalysisResult, AnalyzedPaper, RelevanceTier

logger = logging.getLogger(__name__)


class PaperAnalyzer:
    """Two-stage paper analysis pipeline.

    Stage 1: Score all papers for relevance using a fast/cheap model.
    Stage 2: Deep-analyze high-relevance papers with a capable model.
    """

    def __init__(self, llm_config: LLMConfig, thresholds: RelevanceThresholds):
        api_key = os.environ.get(llm_config.api_key_env, "")
        if not api_key:
            raise ValueError(f"Missing API key: environment variable {llm_config.api_key_env} is not set")

        self.client = OpenAI(
            api_key=api_key,
            base_url=llm_config.base_url,
            timeout=90.0,
            max_retries=2,
        )
        self.scoring_model = llm_config.scoring_model
        self.analysis_model = llm_config.analysis_model
        self.thresholds = thresholds
        self.max_tokens = llm_config.max_tokens_per_call

    def _get_text_for_analysis(self, paper: Paper) -> str:
        """Get the best available text for analysis: full_text if available, else abstract.

        Returns up to 8000 chars from full_text to manage token cost.
        """
        if paper.full_text and len(paper.full_text.strip()) > 100:
            return paper.full_text[:8000]
        if paper.abstract:
            return paper.abstract[:2000]
        return paper.title

    def _determine_tier(self, score: int) -> RelevanceTier:
        """Map score to relevance tier based on configurable thresholds."""
        if score >= self.thresholds.high:
            return RelevanceTier.HIGH
        elif score >= self.thresholds.medium:
            return RelevanceTier.MEDIUM
        return RelevanceTier.LOW

    def score_paper(self, paper: Paper, research_interests: str) -> AnalysisResult:
        """Stage 1: Score a single paper for relevance. Used for all papers."""
        text = self._get_text_for_analysis(paper)
        prompt = SCORING_PROMPT.format(
            research_interests=research_interests,
            title=paper.title,
            text=text[:2000],
        )

        try:
            response = self.client.chat.completions.create(
                model=self.scoring_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=500,
                temperature=0.3,
            )
            content = response.choices[0].message.content or "{}"
            parsed = _safe_json_parse(content)

            score = max(1, min(10, int(parsed.get("score", 1))))
            tier = self._determine_tier(score)

            return AnalysisResult(
                relevance_score=score,
                tier=tier,
                scoring_reason=parsed.get("reason", ""),
                extracted_keywords=parsed.get("keywords", []),
            )
        except Exception as e:
            logger.warning(f"Scoring failed for '{paper.title[:40]}': {e}")
            return AnalysisResult(
                relevance_score=1,
                tier=RelevanceTier.LOW,
                scoring_reason=f"Scoring error: {e}",
            )

    def analyze_paper(self, paper: Paper, research_interests: str, score_result: AnalysisResult) -> AnalysisResult:
        """Stage 2: Deep analysis for high-relevance papers only."""
        text = self._get_text_for_analysis(paper)
        prompt = ANALYSIS_PROMPT.format(
            research_interests=research_interests,
            title=paper.title,
            text=text,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.analysis_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=self.max_tokens,
                temperature=0.4,
            )
            content = response.choices[0].message.content or "{}"
            parsed = _safe_json_parse(content)

            return AnalysisResult(
                relevance_score=score_result.relevance_score,
                tier=score_result.tier,
                summary=parsed.get("summary"),
                key_contributions=parsed.get("key_contributions"),
                potential_applications=parsed.get("potential_applications"),
                extracted_keywords=score_result.extracted_keywords,
                scoring_reason=score_result.scoring_reason,
            )
        except Exception as e:
            logger.warning(f"Deep analysis failed for '{paper.title[:40]}': {e}")
            # Return score result without deep analysis
            return score_result

    def analyze_papers(self, papers: list[Paper], research_interests: str) -> list[AnalyzedPaper]:
        """Full two-stage pipeline for a list of papers.

        Stage 1: Score all papers with fast model.
        Stage 2: Deep-analyze high-relevance papers with capable model.
        Returns tiered results for all papers.
        """
        results = []

        # Stage 1: Score all papers
        logger.info(f"Stage 1: Scoring {len(papers)} papers...")
        scored = []
        for paper in papers:
            score_result = self.score_paper(paper, research_interests)
            scored.append((paper, score_result))
            logger.info(
                f"  [{score_result.tier.value}] Score {score_result.relevance_score}: "
                f"{paper.title[:50]}..."
            )

        # Stage 2: Deep analysis for high-relevance only
        high_relevance = [(p, s) for p, s in scored if s.tier == RelevanceTier.HIGH]
        if high_relevance:
            logger.info(f"Stage 2: Deep-analyzing {len(high_relevance)} high-relevance papers...")
            for paper, score_result in high_relevance:
                deep_result = self.analyze_paper(paper, research_interests, score_result)
                # Replace score_result with deep_result
                idx = next(i for i, (p, _) in enumerate(scored) if p.paper_id == paper.paper_id)
                scored[idx] = (paper, deep_result)

        # Build AnalyzedPaper list
        for paper, analysis in scored:
            results.append(AnalyzedPaper(
                paper=paper,
                analysis=analysis,
                topic_name="",  # Set by caller
            ))

        tier_counts = {t.value: sum(1 for _, a in scored if a.tier == t) for t in RelevanceTier}
        logger.info(f"Analysis complete: {tier_counts}")
        return results


def _safe_json_parse(text: str) -> dict:
    """Parse JSON from LLM response, handling formatting issues."""
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
