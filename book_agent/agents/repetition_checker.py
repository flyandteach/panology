"""
Repetition and Redundancy Agent: Combines computational metrics with LLM analysis.
"""

import os
import re
import json


def call_llm(prompt: str, role: str = "repetition_checker") -> str:
    """Call LLM. Falls back to mock if no API key."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except ImportError:
            pass
        except Exception as e:
            print(f"[LLM warning] Anthropic call failed: {e}. Using mock.")

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
            return response.choices[0].message.content
        except ImportError:
            pass
        except Exception as e:
            print(f"[LLM warning] OpenAI call failed: {e}. Using mock.")

    return _mock_llm_response(role, prompt)


def _mock_llm_response(role: str, prompt: str) -> str:
    """Return realistic mock repetition check result."""
    draft_match = re.search(r"CURRENT DRAFT:\s*\n(.*?)(?:\n\n---|\Z)", prompt, re.DOTALL)
    draft_text = draft_match.group(1).strip() if draft_match else ""

    result = {
        "score": 8.7,
        "repeated_phrases": [
            "the prevailing explanation",
            "without interrogation",
        ],
        "repeated_ideas": [
            "The idea that frameworks shape perception appears in paragraphs 2 and 5 without sufficient development between instances",
            "The call for 'clarity' is mentioned twice but defined differently each time",
        ],
        "issues": [
            "The phrase 'the prevailing explanation' appears 3 times — vary with synonyms",
            "Paragraphs 3 and 6 make the same structural move: contrast then pivot — diversify the rhetorical pattern",
            "The word 'careful' and its variants appear 4 times across the draft",
        ],
        "revised_draft": draft_text if draft_text else "Revised draft with repetition addressed would appear here.",
    }
    return json.dumps(result)


def _build_repetition_prompt(draft: str, project_memory, metrics: dict) -> str:
    """Build the repetition checker prompt."""
    prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
    template_path = os.path.join(prompts_dir, "repetition_checker.md")

    try:
        with open(template_path, "r", encoding="utf-8") as fh:
            template = fh.read()
    except FileNotFoundError:
        template = """You are a repetition and redundancy specialist editor.

{PROJECT_MEMORY}

COMPUTATIONAL FLAGS (pre-computed):
{COMPUTATIONAL_FLAGS}

PHRASES TO AVOID FROM MEMORY:
{PHRASES_TO_AVOID}

CURRENT DRAFT:
{CURRENT_DRAFT}

Return JSON: score (float), repeated_phrases (list), repeated_ideas (list), issues (list), revised_draft (string)."""

    context = project_memory.get_context_for_agent()
    computational_flags = _format_computational_flags(metrics)
    phrases_to_avoid = project_memory.data["memory"].get("phrases_to_avoid", [])
    avoid_str = "\n".join(f"  - {p}" for p in phrases_to_avoid) if phrases_to_avoid else "  (none flagged)"

    prompt = template
    prompt = prompt.replace("{PROJECT_MEMORY}", context)
    prompt = prompt.replace("{CURRENT_DRAFT}", draft)
    prompt = prompt.replace("{COMPUTATIONAL_FLAGS}", computational_flags)
    prompt = prompt.replace("{PHRASES_TO_AVOID}", avoid_str)
    return prompt


def _format_computational_flags(metrics: dict) -> str:
    """Format computational metrics as actionable flags."""
    if not metrics:
        return "(No metrics computed)"

    lines = []

    repeated_3 = metrics.get("repeated_3grams", [])
    if repeated_3:
        lines.append("Repeated 3-grams (count > 2):")
        for phrase, cnt in repeated_3[:5]:
            lines.append(f"  - '{phrase}' ({cnt}x)")

    repeated_4 = metrics.get("repeated_4grams", [])
    if repeated_4:
        lines.append("Repeated 4-grams (count > 1):")
        for phrase, cnt in repeated_4[:5]:
            lines.append(f"  - '{phrase}' ({cnt}x)")

    openings = metrics.get("repeated_sentence_openings", [])
    if openings:
        lines.append(f"Repeated sentence openings: {', '.join(openings)}")

    top_words = metrics.get("top_repeated_words", [])
    if top_words:
        lines.append("Most frequent content words:")
        for word, cnt in top_words[:5]:
            lines.append(f"  - '{word}' ({cnt}x)")

    ttr = metrics.get("type_token_ratio", 0)
    if ttr < 0.6:
        lines.append(f"Low vocabulary diversity (TTR: {ttr:.3f}) — consider more varied word choices")

    return "\n".join(lines) if lines else "(No repetition flags from computational analysis)"


def _compute_computational_score(metrics: dict) -> float:
    """Derive a base score from computational metrics alone."""
    score = 10.0
    deductions = 0.0

    repeated_3 = metrics.get("repeated_3grams", [])
    deductions += min(len(repeated_3) * 0.3, 1.5)

    repeated_4 = metrics.get("repeated_4grams", [])
    deductions += min(len(repeated_4) * 0.4, 1.0)

    openings = metrics.get("repeated_sentence_openings", [])
    deductions += min(len(openings) * 0.2, 0.6)

    ttr = metrics.get("type_token_ratio", 1.0)
    if ttr < 0.5:
        deductions += 0.5
    elif ttr < 0.6:
        deductions += 0.2

    return max(5.0, round(score - deductions, 1))


def _parse_repetition_response(response: str, fallback_draft: str) -> dict:
    """Parse JSON from repetition checker response."""
    for extractor in [
        lambda r: json.loads(r),
        lambda r: json.loads(re.search(r"```(?:json)?\s*(\{.*?\})\s*```", r, re.DOTALL).group(1)),
        lambda r: json.loads(re.search(r"\{.*\}", r, re.DOTALL).group(0)),
    ]:
        try:
            data = extractor(response)
            score = max(1.0, min(10.0, float(data.get("score", 8.0))))
            return {
                "score": score,
                "repeated_phrases": list(data.get("repeated_phrases", [])),
                "repeated_ideas": list(data.get("repeated_ideas", [])),
                "issues": list(data.get("issues", [])),
                "revised_draft": str(data.get("revised_draft", fallback_draft)),
            }
        except Exception:
            continue

    return {
        "score": 7.5,
        "repeated_phrases": [],
        "repeated_ideas": [],
        "issues": ["Could not parse structured response from repetition checker"],
        "revised_draft": fallback_draft,
    }


class RepetitionCheckerAgent:
    """Combines computational metrics with LLM analysis to catch repetition."""

    def review(self, draft: str, project_memory, metrics: dict) -> dict:
        """
        Check for repetition, redundancy, and overused phrases.

        Returns:
            dict with keys: score, repeated_phrases, repeated_ideas, issues, revised_draft
        """
        # Compute a computational base score
        comp_score = _compute_computational_score(metrics)

        # Get LLM analysis
        prompt = _build_repetition_prompt(draft, project_memory, metrics)
        response = call_llm(prompt, role="repetition_checker")
        result = _parse_repetition_response(response, draft)

        # Blend computational and LLM scores (60/40 weighting toward LLM)
        blended_score = round(0.4 * comp_score + 0.6 * result["score"], 2)
        result["score"] = blended_score
        result["computational_score"] = comp_score

        if not result["revised_draft"].strip():
            result["revised_draft"] = draft

        return result
