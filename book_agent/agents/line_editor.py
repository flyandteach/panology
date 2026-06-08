"""
Line Editor Agent: Reviews and revises drafts for prose quality.
"""

import os
import re
import json


def call_llm(prompt: str, role: str = "line_editor") -> str:
    """Call LLM with the given prompt. Falls back to mock if no API key."""
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
    """Return a realistic mock line-edit response as JSON."""
    # Estimate a score based on draft length in prompt
    draft_length = len(prompt)
    score = 8.3 if draft_length > 1000 else 7.6

    # Extract the draft from the prompt for the revised version
    draft_match = re.search(r"CURRENT DRAFT:\s*\n(.*?)(?:\n\n---|\Z)", prompt, re.DOTALL)
    draft_text = draft_match.group(1).strip() if draft_match else ""

    # Make light revisions to the draft
    revised = draft_text
    # Replace a few common weak constructions
    revised = re.sub(r"\bvery\s+(\w+)", r"deeply \1", revised, count=2)
    revised = re.sub(r"\bit is important to note that\b", "notably,", revised, flags=re.IGNORECASE, count=2)
    revised = re.sub(r"\bin order to\b", "to", revised, flags=re.IGNORECASE, count=3)

    if not revised:
        revised = "The revised draft would appear here with improved sentence rhythm, cleaner transitions, and tightened prose throughout."

    result = {
        "score": score,
        "critique": (
            "The draft shows a confident authorial voice and a clear argumentative structure. "
            "Sentence rhythm is generally good, though several mid-paragraph sequences run long "
            "before offering the reader a breath. Transitions between the second and third "
            "paragraphs feel slightly mechanical — consider varying the connective tissue. "
            "The opening is strong. The closing lands well but could be sharpened by removing "
            "the penultimate sentence, which partially deflates the impact of the final line."
        ),
        "issues": [
            "Two consecutive sentences begin with 'The' in paragraph three — vary sentence openings",
            "Passive voice in paragraph two weakens the causal claim being made",
            "Transition from abstract to concrete in paragraph four is abrupt — needs a bridge sentence",
            "Final paragraph slightly undercuts the confidence established earlier — trim or rewrite closing",
        ],
        "revised_draft": revised,
    }
    return json.dumps(result)


def _build_line_edit_prompt(draft: str, project_memory, metrics: dict) -> str:
    """Build the line editor prompt."""
    prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
    template_path = os.path.join(prompts_dir, "line_editor.md")

    try:
        with open(template_path, "r", encoding="utf-8") as fh:
            template = fh.read()
    except FileNotFoundError:
        template = """You are an expert line editor. Review and revise the following draft.

{PROJECT_MEMORY}

TEXT METRICS:
{METRICS_SUMMARY}

CURRENT DRAFT:
{CURRENT_DRAFT}

Return a JSON object with keys: score (float 6.0-9.5), critique (string), issues (list of strings), revised_draft (string)."""

    context = project_memory.get_context_for_agent()
    metrics_summary = _format_metrics(metrics)

    prompt = template
    prompt = prompt.replace("{PROJECT_MEMORY}", context)
    prompt = prompt.replace("{CURRENT_DRAFT}", draft)
    prompt = prompt.replace("{METRICS_SUMMARY}", metrics_summary)
    return prompt


def _format_metrics(metrics: dict) -> str:
    """Format metrics dict into readable summary."""
    if not metrics:
        return "(No metrics available)"
    lines = [
        f"Word count: {metrics.get('word_count', '?')}",
        f"Sentences: {metrics.get('sentence_count', '?')}",
        f"Avg sentence length: {metrics.get('avg_sentence_length', '?')} words",
        f"Sentence length std dev: {metrics.get('sentence_length_std', '?')}",
        f"Type-token ratio: {metrics.get('type_token_ratio', '?')}",
        f"Readability (Flesch): {metrics.get('readability_score', '?')}",
        f"Passive voice estimate: {metrics.get('passive_voice_estimate', '?')} sentences",
    ]
    repeated = metrics.get("repeated_sentence_openings", [])
    if repeated:
        lines.append(f"Repeated sentence openings: {', '.join(repeated)}")
    return "\n".join(lines)


def _parse_line_edit_response(response: str) -> dict:
    """Parse JSON response from line editor."""
    # Try direct parse
    try:
        data = json.loads(response)
        return _validate_line_edit_result(data)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            return _validate_line_edit_result(data)
        except json.JSONDecodeError:
            pass

    # Try finding JSON object
    match = re.search(r"\{.*\}", response, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return _validate_line_edit_result(data)
        except json.JSONDecodeError:
            pass

    # Fallback
    return {
        "score": 7.0,
        "critique": response[:500] if response else "No critique available.",
        "issues": ["Could not parse structured response from line editor"],
        "revised_draft": "",
    }


def _validate_line_edit_result(data: dict) -> dict:
    """Ensure the dict has required keys with correct types."""
    score = float(data.get("score", 7.0))
    score = max(1.0, min(10.0, score))
    return {
        "score": score,
        "critique": str(data.get("critique", "")),
        "issues": list(data.get("issues", [])),
        "revised_draft": str(data.get("revised_draft", "")),
    }


class LineEditorAgent:
    """Reviews draft prose for line-level quality and returns a revised draft with score."""

    def review(self, draft: str, project_memory, metrics: dict) -> dict:
        """
        Perform a line edit review.

        Returns:
            dict with keys: score (float), critique (str), issues (list), revised_draft (str)
        """
        prompt = _build_line_edit_prompt(draft, project_memory, metrics)
        response = call_llm(prompt, role="line_editor")
        result = _parse_line_edit_response(response)
        # If revised_draft is empty, return original draft
        if not result["revised_draft"].strip():
            result["revised_draft"] = draft
        return result
