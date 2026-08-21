"""
Assembles the final AMRG summary document: the LLM-written What/Who/Where/
Summary/Keywords sections (per prompts/amrg_template.md), plus the
deterministically-computed writing score and fact-check sections appended
by the pipeline (not the LLM, so those numbers can't drift from what
agents/scoring.py and agents/fact_check.py actually calculated).
"""

import os

import config
from utils.llm import call_llm

RECOMMENDATION_LIBRARY = {
    "cohesion": "Strengthen transitions between paragraphs so the argument's throughline is easier to follow.",
    "lexical_diversity": "Improve lexical diversity by avoiding repetitive phrasing and word choice.",
    "semantic_complexity": "Strengthen conceptual depth by integrating more nuanced arguments and connecting ideas explicitly.",
    "syntactic_complexity": "Vary sentence structure -- mix clause types instead of relying on one pattern throughout.",
    "grammar": "Copy-edit for grammar and mechanics before final publication.",
    "topic_relevance": "Trim digressions that drift from the article's stated subject.",
    "readability": "Reduce sentence length and simplify wording for better readability.",
}


def _build_prompt(article_text: str, figures: list, topic_area: str, scholar_meta: dict) -> str:
    template_path = os.path.join(config.PROMPTS_DIR, "amrg_template.md")
    with open(template_path, "r", encoding="utf-8") as fh:
        template = fh.read()

    figure_list = "\n".join(
        f"- Figure {i + 1}: {os.path.basename(f['path'])} (page {f['page']}"
        f"{', caption: ' + f['caption'] if f.get('caption') else ''})"
        for i, f in enumerate(figures)
    ) or "(no extractable figures found in this PDF)"

    scholar_block = (
        f"- Scholar-listed title: {scholar_meta.get('title', 'n/a')}\n"
        f"- Scholar-listed authors: {', '.join(scholar_meta.get('authors', [])) or 'n/a'}\n"
        f"- Scholar-listed venue: {scholar_meta.get('venue', 'n/a')}\n"
        f"- Scholar-listed year: {scholar_meta.get('pub_year', 'n/a')}\n"
        f"- Scholar URL: {scholar_meta.get('scholar_url', 'n/a')}\n"
        f"- Full-text URL: {scholar_meta.get('eprint_url', 'n/a')}"
    )

    prompt = template
    prompt = prompt.replace("{TOPIC_AREA}", topic_area)
    # Keep the excerpt within a reasonable context budget; long PDFs get
    # truncated rather than dropped.
    prompt = prompt.replace("{ARTICLE_TEXT}", article_text[:60000])
    prompt = prompt.replace("{FIGURE_LIST}", figure_list)
    prompt = prompt.replace("{SCHOLAR_METADATA}", scholar_block)
    return prompt


def generate_recommendations(score_result: dict, top_n: int = 3) -> list:
    """Deterministic recommendations from the lowest-scoring dimensions,
    so recommendations always match the numbers actually computed."""
    all_scores = dict(score_result["components"])
    all_scores["readability"] = score_result["readability_score"]
    weakest = sorted(all_scores.items(), key=lambda kv: kv[1])[:top_n]
    return [RECOMMENDATION_LIBRARY[dim] for dim, _ in weakest if dim in RECOMMENDATION_LIBRARY]


def _format_score_section(score_result: dict) -> str:
    c = score_result["components"]
    lines = [
        "## Writing Quality Score",
        "",
        f"**Final Writing Score: {score_result['final_writing_score']:.2f}** / 10",
        "",
        f"- Readability Score: {score_result['readability_score']:.2f}",
        f"- Comprehensive Writing Quality Score: {score_result['comprehensive_writing_quality_score']:.2f}",
        "  - Cohesion: " + f"{c['cohesion']:.2f}",
        "  - Lexical Diversity: " + f"{c['lexical_diversity']:.2f}",
        "  - Semantic Complexity: " + f"{c['semantic_complexity']:.2f}",
        "  - Syntactic Complexity: " + f"{c['syntactic_complexity']:.2f}",
        "  - Grammar: " + f"{c['grammar']:.2f}",
        "  - Topic Relevance: " + f"{c['topic_relevance']:.2f}",
        "",
        "**Recommendations:**",
    ]
    for rec in generate_recommendations(score_result):
        lines.append(f"- {rec}")
    return "\n".join(lines)


def _format_fact_check_section(fact_check_result: dict) -> str:
    lines = [
        "## Fact Check (heuristic)",
        "",
        f"- References detected: {fact_check_result['references_detected']}",
        f"- References checked against Crossref: {fact_check_result['references_checked']}",
        f"- References verified (matching record found): {fact_check_result['references_verified']}",
        f"- References NOT found in Crossref: {fact_check_result['references_not_found']}",
        "",
    ]
    not_found = [r for r in fact_check_result["reference_details"] if r.get("found") is False]
    if not_found:
        lines.append("**References that did not resolve to a Crossref record** (may still be "
                      "legitimate -- some sources, e.g. government/industry reports, aren't indexed "
                      "by Crossref -- but warrant a manual look):")
        for r in not_found[:10]:
            lines.append(f"- {r['entry'][:200]}")
        lines.append("")

    flagged = fact_check_result.get("flagged_claims", [])
    if flagged:
        lines.append(f"**Claims flagged for plausibility review** "
                      f"(of {fact_check_result['claims_reviewed']} reviewed):")
        for f in flagged:
            lines.append(f"- \"{f.get('claim', '')}\" -- {f.get('concern', '')}")
    else:
        lines.append(f"No numeric claims flagged (of {fact_check_result['claims_reviewed']} reviewed).")

    lines.append("")
    lines.append(f"_{fact_check_result['scope_note']}_")
    return "\n".join(lines)


def summarize_article(article_text: str, figures: list, topic_area: str,
                       scholar_meta: dict, score_result: dict, fact_check_result: dict) -> str:
    """Produce the complete AMRG markdown document for one article."""
    prompt = _build_prompt(article_text, figures, topic_area, scholar_meta)
    mock = (
        "## What?\n(mock -- no LLM configured)\n\n"
        "## Who?\n(mock)\n\n## Where?\n*(mock)*\n\n## Summary\n(mock)\n\n"
        "**Key Takeaways**\n- (mock)\n\n## Keywords\n#mock"
    )
    body = call_llm(prompt, mock_response=mock, max_tokens=config.MAX_TOKENS)

    sections = [
        body.strip(),
        "",
        "---",
        "",
        _format_score_section(score_result),
        "",
        "---",
        "",
        _format_fact_check_section(fact_check_result),
    ]
    return "\n".join(sections)
