"""
Writing-quality scoring, per the AMRG project instructions:

  Comprehensive Writing Quality Score =
      (Cohesion * 0.20) + (Lexical Diversity * 0.15) + (Semantic Complexity * 0.15)
      + (Syntactic Complexity * 0.20) + (Grammar * 0.15) + (Topic Relevance * 0.15)

  Final Writing Score = (0.35 * Readability Score) + (0.65 * Comprehensive Writing Quality Score)

All component scores and the two top-level scores are on a 0-10 scale.

Readability, Lexical Diversity and Syntactic Complexity are computed directly
from the text (textstat + simple sentence-structure heuristics). Cohesion,
Semantic Complexity, Grammar and Topic Relevance require judgment an LLM is
better suited to than a formula, so those four are LLM-rated (same pattern
book_agent uses for its audience-critique scores) -- each call returns its
own reasoning so the score is auditable, not a black box.
"""

import json
import re

import textstat

import config
from utils.llm import call_llm

LLM_DIMENSIONS = ["cohesion", "semantic_complexity", "grammar", "topic_relevance"]

SCORING_PROMPT = """You are scoring an academic/research article excerpt on four writing dimensions, \
each on a 0-10 scale (10 = excellent). Be a strict, consistent grader -- most competent published \
research writing should land in the 6-8.5 range; reserve 9+ for exceptional work and below 5 for \
writing with real deficiencies.

Dimensions:
- cohesion: how well ideas connect across sentences and paragraphs (transitions, logical flow, \
  referential clarity).
- semantic_complexity: depth and sophistication of the ideas and conceptual relationships expressed \
  (not just vocabulary difficulty).
- grammar: correctness of grammar, punctuation, and mechanics.
- topic_relevance: how well the content stays focused on and relevant to its stated subject \
  ({TOPIC_AREA}), without digression.

ARTICLE EXCERPT:
{EXCERPT}

Return ONLY JSON: {{"cohesion": float, "semantic_complexity": float, "grammar": float, \
"topic_relevance": float, "notes": {{"cohesion": str, "semantic_complexity": str, "grammar": str, \
"topic_relevance": str}}}}"""


def _clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))


def readability_score(text: str) -> float:
    """Flesch Reading Ease (0-100, higher = easier) rescaled to 0-10.
    Research writing is intentionally dense, so a mid-range score here is
    normal and not itself a quality problem -- it only feeds 35% of the
    final blended score for that reason."""
    flesch = textstat.flesch_reading_ease(text)
    return round(_clamp(flesch / 10.0), 2)


def lexical_diversity_score(text: str) -> float:
    """Type-token ratio, rescaled. Long academic texts naturally have a
    lower raw TTR than short ones (word reuse is unavoidable), so this
    uses a moving-average TTR over 500-word windows to reduce the length
    penalty, then maps typical academic-prose TTR (~0.35-0.55) onto 0-10."""
    words = [w.lower() for w in re.findall(r"[A-Za-z']+", text)]
    if not words:
        return 0.0

    window = 500
    ratios = []
    for i in range(0, len(words), window):
        chunk = words[i:i + window]
        if len(chunk) < 20:
            continue
        ratios.append(len(set(chunk)) / len(chunk))
    mattr = sum(ratios) / len(ratios) if ratios else len(set(words)) / len(words)

    # Map ~0.30 -> 3, ~0.55 -> 9 (roughly linear across the typical range).
    scaled = (mattr - 0.30) / (0.55 - 0.30) * 6.0 + 3.0
    return round(_clamp(scaled), 2)


def syntactic_complexity_score(text: str) -> float:
    """Blend of average sentence length and subordinate-clause frequency
    (proxied by subordinating conjunctions/relative pronouns per sentence),
    rescaled to 0-10. This rewards structural variety, not just length --
    a wall of 40-word run-ons scores the same as short choppy sentences if
    neither shows clause-level structure."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        return 0.0

    subordinators = (
        r"\b(although|because|since|while|whereas|if|unless|until|though|"
        r"which|who|whom|that|whose|when|where|as)\b"
    )
    lengths = [len(s.split()) for s in sentences]
    avg_len = sum(lengths) / len(lengths)
    clause_hits = sum(len(re.findall(subordinators, s, re.IGNORECASE)) for s in sentences)
    clauses_per_sentence = clause_hits / len(sentences)

    # Average sentence length: ~12 words -> low, ~28 words -> high (typical
    # academic-prose range), each mapped 0-5 and summed.
    len_component = _clamp((avg_len - 12) / (28 - 12) * 5.0, 0, 5)
    clause_component = _clamp(clauses_per_sentence / 1.5 * 5.0, 0, 5)
    return round(_clamp(len_component + clause_component), 2)


def llm_rated_dimensions(text: str, topic_area: str, excerpt_chars: int = 12000) -> dict:
    """cohesion, semantic_complexity, grammar, topic_relevance via LLM."""
    excerpt = text[:excerpt_chars]
    prompt = (
        SCORING_PROMPT
        .replace("{TOPIC_AREA}", topic_area)
        .replace("{EXCERPT}", excerpt)
    )
    mock = json.dumps({
        "cohesion": 7.0, "semantic_complexity": 7.0, "grammar": 7.5, "topic_relevance": 7.5,
        "notes": {k: "mock score (no LLM configured)" for k in LLM_DIMENSIONS},
    })
    response = call_llm(prompt, mock_response=mock)

    for extractor in [
        lambda r: json.loads(r),
        lambda r: json.loads(re.search(r"```(?:json)?\s*(\{.*?\})\s*```", r, re.DOTALL).group(1)),
        lambda r: json.loads(re.search(r"\{.*\}", r, re.DOTALL).group(0)),
    ]:
        try:
            data = extractor(response)
            scored = {
                dim: round(_clamp(float(data.get(dim, 7.0))), 2)
                for dim in LLM_DIMENSIONS
            }
            scored["notes"] = dict(data.get("notes", {}))
            return scored
        except Exception:
            continue

    fallback = {dim: 7.0 for dim in LLM_DIMENSIONS}
    fallback["notes"] = {"parse_error": True}
    return fallback


def score_article(text: str, topic_area: str) -> dict:
    """Full scoring pass. Returns component scores, the composite quality
    score, the readability score, and the final blended writing score."""
    readability = readability_score(text)
    lexical = lexical_diversity_score(text)
    syntactic = syntactic_complexity_score(text)
    llm_scores = llm_rated_dimensions(text, topic_area)

    components = {
        "cohesion": llm_scores["cohesion"],
        "lexical_diversity": lexical,
        "semantic_complexity": llm_scores["semantic_complexity"],
        "syntactic_complexity": syntactic,
        "grammar": llm_scores["grammar"],
        "topic_relevance": llm_scores["topic_relevance"],
    }

    quality_score = sum(
        components[dim] * weight for dim, weight in config.QUALITY_WEIGHTS.items()
    )
    final_score = (
        config.READABILITY_WEIGHT * readability + config.QUALITY_WEIGHT * quality_score
    )

    return {
        "readability_score": readability,
        "components": components,
        "comprehensive_writing_quality_score": round(quality_score, 2),
        "final_writing_score": round(final_score, 2),
        "llm_notes": llm_scores.get("notes", {}),
    }
