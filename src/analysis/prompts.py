"""Prompt templates for AI analysis pipeline.

All prompts use {placeholder} syntax for str.format() and instruct the LLM
to return strict JSON for reliable parsing.
"""


def get_language_instruction(language: str) -> str:
    """Return language instruction to append to prompts.

    For "zh" and "mixed": instruct LLM to output analysis text in Chinese.
    For "en": no extra instruction (default English behavior).
    """
    if language in ("zh", "mixed"):
        return "Respond entirely in Chinese (中文). The 'summary', 'key_contributions', 'potential_applications', 'reason', 'methodology_evaluation', 'limitations', 'future_directions', and 'comparative_analysis' fields must all be written in Chinese. Paper titles mentioned within those fields should remain in their original English."
    return ""


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

IMPORTANT — Score LOW (1-3) for papers that are:
- Traditional CMAQ/WRF-Chem simulation studies WITHOUT AI or novel methodology
- Pure air quality monitoring, policy evaluation, or health impact studies WITHOUT methodological innovation
- Indoor air quality or occupational health studies
- Pure climate change or carbon footprint studies unrelated to atmospheric pollution
- Traditional bottom-up emission inventory compilation (emission factors, activity data) WITHOUT inverse modeling or AI

Only score HIGH (8-10) for papers that demonstrate clear methodological innovation using AI, machine learning, deep learning, data assimilation, or novel computational approaches.

Also extract 3-5 key technical terms/concepts from the paper.

{language_instruction}

Return strict JSON: {{"score": 7, "reason": "one sentence explanation", "keywords": ["term1", "term2"]}}"""

ANALYSIS_PROMPT = """Provide a detailed analysis of this paper's relevance to the research area.

Research area: {research_interests}

Paper title: {title}
Paper text: {text}

Provide:
1. A concise summary (2-3 paragraphs) of the paper's content and contributions
2. Exactly 3 key contributions as a list
3. 2-3 potential application scenarios for this research

{language_instruction}

Return strict JSON:
{{
  "summary": "2-3 paragraph summary...",
  "key_contributions": ["contribution 1", "contribution 2", "contribution 3"],
  "potential_applications": ["application 1", "application 2"]
}}"""

DEEP_METHODOLOGY_PROMPT = """Perform a deep methodology analysis of this research paper.

Paper title: {title}
Paper text: {text}
Prior summary: {summary}
Prior key contributions: {key_contributions}

Analyze the following aspects:

1. **Methodology Evaluation**: Evaluate the experimental design soundness, dataset scale and representativeness, baseline comparison choices, and reproducibility. Note any methodological strengths or novel approaches.

2. **Limitations**: Identify both explicitly acknowledged limitations (stated by the authors) and implicit limitations you observe. Be specific about what is limited and why it matters.

3. **Future Research Directions**: Suggest specific, actionable future research directions based on the paper's contributions and limitations. Avoid generic suggestions like "need more data" or "larger scale experiments" — focus on concrete next steps.

{language_instruction}

Return strict JSON:
{{
  "methodology_evaluation": "A paragraph evaluating the methodology...",
  "limitations": ["limitation 1", "limitation 2", "limitation 3"],
  "future_directions": ["direction 1", "direction 2", "direction 3"]
}}"""

COMPARATIVE_ANALYSIS_PROMPT = """Compare this paper against previously analyzed papers in the same research area.

Target paper title: {title}
Target paper abstract: {abstract}
Target paper summary: {summary}

Historical papers for comparison:
{historical_papers}

Compare the target paper against the historical papers above. Focus on:
1. Key similarities and differences in research approach and methodology
2. How the target paper's contributions relate to or extend prior work
3. Unique aspects of the target paper not seen in the historical papers

{language_instruction}

Return strict JSON:
{{
  "comparative_analysis": "2-3 sentence comparison summarizing key similarities and differences...",
  "key_differences": ["difference 1", "difference 2"]
}}"""
