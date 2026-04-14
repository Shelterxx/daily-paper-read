"""Prompt templates for AI analysis pipeline.

All prompts use {placeholder} syntax for str.format() and instruct the LLM
to return strict JSON for reliable parsing.
"""

KEYWORD_EXTRACTION_PROMPT = """You are a research librarian. Extract search keywords from the following research description for use in academic paper search (e.g., arXiv).

Research description: {description}

Requirements:
- Return 3-8 keywords/phrases suitable for arXiv search queries
- Use both English terms and field-specific terminology
- Include abbreviations where common (e.g., "LLM" for "large language model")
- Order by importance

Return strict JSON: {{"keywords": ["keyword1", "keyword2", ...]}}"""

SCORING_PROMPT = """Score the relevance of this paper to the following research interests.

Research interests: {research_interests}

Paper title: {title}
Paper text (first 2000 chars): {text}

Score from 1-10:
- 1-3: Not relevant to the research area
- 4-6: Tangentially related, worth knowing about
- 7-10: Directly relevant, significant contribution to the research area

Also extract 3-5 key technical terms/concepts from the paper.

Return strict JSON: {{"score": 7, "reason": "one sentence explanation", "keywords": ["term1", "term2"]}}"""

ANALYSIS_PROMPT = """Provide a detailed analysis of this paper's relevance to the research area.

Research area: {research_interests}

Paper title: {title}
Paper text: {text}

Provide:
1. A concise summary (2-3 paragraphs) of the paper's content and contributions
2. Exactly 3 key contributions as a list
3. 2-3 potential application scenarios for this research

Return strict JSON:
{{
  "summary": "2-3 paragraph summary...",
  "key_contributions": ["contribution 1", "contribution 2", "contribution 3"],
  "potential_applications": ["application 1", "application 2"]
}}"""
