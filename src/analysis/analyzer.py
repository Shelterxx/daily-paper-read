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

from src.analysis.prompts import SCORING_PROMPT, ANALYSIS_PROMPT, DEEP_METHODOLOGY_PROMPT, COMPARATIVE_ANALYSIS_PROMPT, get_language_instruction
from src.config.models import LLMConfig, RelevanceThresholds
from src.search.models import Paper, AnalysisResult, AnalyzedPaper, RelevanceTier

logger = logging.getLogger(__name__)


class PaperAnalyzer:
    """Two-stage paper analysis pipeline.

    Stage 1: Score all papers for relevance using a fast/cheap model.
    Stage 2: Deep-analyze high-relevance papers with a capable model.
    """

    def __init__(self, llm_config: LLMConfig, thresholds: RelevanceThresholds, language: str = "en"):
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
        self.language = language
        self._language_instruction = get_language_instruction(language)

    def _get_text_for_analysis(self, paper: Paper, abstract_only: bool = False) -> str:
        """Get the best available text for analysis.

        Args:
            abstract_only: If True, skip full_text and use abstract only.
                Used for scoring stage — abstracts are more concise and sufficient
                for relevance scoring, avoiding unnecessary PDF downloads.
        """
        if not abstract_only and paper.full_text and len(paper.full_text.strip()) > 100:
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
        """Stage 1: Score a single paper for relevance using abstract only.

        Scoring with abstracts is sufficient for relevance assessment and avoids
        the cost of downloading PDFs for papers that will be filtered out.
        """
        text = self._get_text_for_analysis(paper, abstract_only=True)
        prompt = SCORING_PROMPT.format(
            research_interests=research_interests,
            title=paper.title,
            text=text[:2000],
            language_instruction=self._language_instruction,
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
            language_instruction=self._language_instruction,
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

    def deep_analyze_methodology(self, paper: Paper, stage2a_result: AnalysisResult) -> AnalysisResult:
        """Stage 2b: Deep methodology analysis for high-relevance papers.

        Evaluates methodology soundness, identifies limitations, and suggests
        future research directions. Enriches the Stage 2a result with new fields.

        On failure: returns stage2a_result unchanged (independent fault tolerance).
        """
        text = self._get_text_for_analysis(paper)
        prompt = DEEP_METHODOLOGY_PROMPT.format(
            title=paper.title,
            text=text,
            summary=stage2a_result.summary or "",
            key_contributions=json.dumps(stage2a_result.key_contributions or [], ensure_ascii=False),
            language_instruction=self._language_instruction,
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

            usage = getattr(response, "usage", None)
            if usage:
                logger.info(
                    f"Stage 2b tokens for '{paper.title[:30]}': "
                    f"input={usage.prompt_tokens}, output={usage.completion_tokens}"
                )

            return AnalysisResult(
                relevance_score=stage2a_result.relevance_score,
                tier=stage2a_result.tier,
                summary=stage2a_result.summary,
                key_contributions=stage2a_result.key_contributions,
                potential_applications=stage2a_result.potential_applications,
                extracted_keywords=stage2a_result.extracted_keywords,
                scoring_reason=stage2a_result.scoring_reason,
                methodology_evaluation=parsed.get("methodology_evaluation"),
                limitations=parsed.get("limitations"),
                future_directions=parsed.get("future_directions"),
            )
        except Exception as e:
            logger.warning(f"Stage 2b methodology analysis failed for '{paper.title[:40]}': {e}")
            return stage2a_result

    def compare_with_history(self, paper: Paper, stage2b_result: AnalysisResult, historical_papers: list[dict]) -> AnalysisResult:
        """Stage 3: Comparative analysis against historical papers.

        Compares the target paper against previously analyzed papers from the
        same research area. Enriches the Stage 2b result with comparative fields.

        On failure or insufficient history: returns stage2b_result unchanged.
        """
        if not historical_papers or len(historical_papers) < 1:
            logger.warning("Not enough historical papers for comparison, skipping Stage 3")
            return stage2b_result

        # Format historical papers for the prompt
        formatted_parts = []
        for hp in historical_papers:
            abstract = (hp.get("abstract") or "")[:300]
            summary = (hp.get("summary") or "")[:200]
            formatted_parts.append(
                f"Title: {hp.get('title', 'Unknown')}\n"
                f"Abstract: {abstract}\n"
                f"Summary: {summary}\n---"
            )
        formatted_history = "\n".join(formatted_parts)

        prompt = COMPARATIVE_ANALYSIS_PROMPT.format(
            title=paper.title,
            abstract=(paper.abstract or "")[:1000],
            summary=stage2b_result.summary or "",
            historical_papers=formatted_history,
            language_instruction=self._language_instruction,
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

            usage = getattr(response, "usage", None)
            if usage:
                logger.info(
                    f"Stage 3 tokens for '{paper.title[:30]}': "
                    f"input={usage.prompt_tokens}, output={usage.completion_tokens}"
                )

            return AnalysisResult(
                relevance_score=stage2b_result.relevance_score,
                tier=stage2b_result.tier,
                summary=stage2b_result.summary,
                key_contributions=stage2b_result.key_contributions,
                potential_applications=stage2b_result.potential_applications,
                extracted_keywords=stage2b_result.extracted_keywords,
                scoring_reason=stage2b_result.scoring_reason,
                methodology_evaluation=stage2b_result.methodology_evaluation,
                limitations=stage2b_result.limitations,
                future_directions=stage2b_result.future_directions,
                comparative_analysis=parsed.get("comparative_analysis"),
                compared_with=[hp.get("title", "") for hp in historical_papers[:5]],
            )
        except Exception as e:
            logger.warning(f"Stage 3 comparative analysis failed for '{paper.title[:40]}': {e}")
            return stage2b_result

    def analyze_papers(self, papers: list[Paper], research_interests: str) -> list[AnalyzedPaper]:
        """Stage 1 only: Score all papers with fast model (abstract-based).

        Deep analysis for high-relevance papers is handled separately by the caller
        after PDF fetching, using analyze_paper().
        """
        results = []

        logger.info(f"Stage 1: Scoring {len(papers)} papers (abstracts only)...")
        for paper in papers:
            score_result = self.score_paper(paper, research_interests)
            results.append(AnalyzedPaper(
                paper=paper,
                analysis=score_result,
                topic_name="",  # Set by caller
            ))
            logger.info(
                f"  [{score_result.tier.value}] Score {score_result.relevance_score}: "
                f"{paper.title[:50]}..."
            )

        tier_counts = {t.value: sum(1 for r in results if r.analysis.tier == t) for t in RelevanceTier}
        logger.info(f"Scoring complete: {tier_counts}")
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
