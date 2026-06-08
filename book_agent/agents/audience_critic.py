"""
Critical Audience Agent: Simulates reader reactions from multiple perspectives.
"""

import os
import re
import json


def call_llm(prompt: str, role: str = "audience_critic") -> str:
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
    """Return realistic mock audience critique."""
    result = {
        "score": 8.2,
        "reactions": {
            "professional_editor": {
                "verdict": "Publishable with minor revisions",
                "strengths": [
                    "Strong conceptual scaffolding — the reader always knows where they are in the argument",
                    "The closing paragraph creates genuine forward momentum",
                ],
                "concerns": [
                    "The transition at the end of paragraph three is too abrupt for a general trade audience",
                    "The abstract-to-concrete ratio skews too abstract in the middle section",
                ],
                "score": 8.4,
            },
            "intelligent_general_reader": {
                "verdict": "Engaging but occasionally loses me",
                "strengths": [
                    "The opening question is genuinely arresting — I wanted to keep reading",
                    "The prose is clean and not condescending",
                ],
                "concerns": [
                    "I struggled in paragraph four — felt like I missed a step in the logic",
                    "Could use one concrete example earlier to anchor the abstract argument",
                ],
                "score": 7.9,
            },
            "target_market_reader": {
                "verdict": "This is exactly what I was hoping for",
                "strengths": [
                    "Speaks directly to the frustration I have felt about conventional explanations",
                    "The framing around inherited frameworks is going to resonate with this audience",
                ],
                "concerns": [
                    "The call for 'courage' in the final paragraph might feel slightly high-minded to some readers",
                    "A brief preview of what comes next would be welcome here",
                ],
                "score": 8.3,
            },
        },
        "weaknesses": [
            "The argumentative leap in paragraph four is not adequately bridged",
            "Abstract-to-concrete ratio is imbalanced — too much abstraction in the midsection",
            "Closing is strong but slightly deflated by the penultimate sentence",
        ],
        "issues": [
            "Add a concrete example in paragraphs 2-3 to anchor the abstract framing",
            "Bridge the logic gap between paragraphs 3 and 4",
            "Consider cutting or rewriting the penultimate sentence in the closing paragraph",
        ],
    }
    return json.dumps(result)


def _build_audience_critique_prompt(draft: str, project_memory, section_brief: str) -> str:
    """Build the audience critic prompt."""
    prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
    template_path = os.path.join(prompts_dir, "audience_critic.md")

    try:
        with open(template_path, "r", encoding="utf-8") as fh:
            template = fh.read()
    except FileNotFoundError:
        template = """You are a panel of three critical readers evaluating a book draft.

{PROJECT_MEMORY}

Section Brief: {SECTION_BRIEF}

CURRENT DRAFT:
{CURRENT_DRAFT}

Evaluate as:
1. Professional Editor (publication standards, structural integrity)
2. Intelligent General Reader (clarity, engagement, logical flow)
3. Target-Market Reader (relevance, resonance, value delivered)

Return JSON with keys: score (float), reactions (dict), weaknesses (list), issues (list)."""

    context = project_memory.get_context_for_agent()
    prompt = template
    prompt = prompt.replace("{PROJECT_MEMORY}", context)
    prompt = prompt.replace("{CURRENT_DRAFT}", draft)
    prompt = prompt.replace("{SECTION_BRIEF}", section_brief)
    return prompt


def _parse_audience_response(response: str) -> dict:
    """Parse audience critique JSON response."""
    for extractor in [
        lambda r: json.loads(r),
        lambda r: json.loads(re.search(r"```(?:json)?\s*(\{.*?\})\s*```", r, re.DOTALL).group(1)),
        lambda r: json.loads(re.search(r"\{.*\}", r, re.DOTALL).group(0)),
    ]:
        try:
            data = extractor(response)
            score = max(1.0, min(10.0, float(data.get("score", 7.5))))
            return {
                "score": score,
                "reactions": dict(data.get("reactions", {})),
                "weaknesses": list(data.get("weaknesses", [])),
                "issues": list(data.get("issues", [])),
            }
        except Exception:
            continue

    return {
        "score": 7.0,
        "reactions": {
            "professional_editor": {"verdict": "Unable to parse", "score": 7.0},
            "intelligent_general_reader": {"verdict": "Unable to parse", "score": 7.0},
            "target_market_reader": {"verdict": "Unable to parse", "score": 7.0},
        },
        "weaknesses": ["Could not parse structured response from audience critic"],
        "issues": ["Re-run audience critique — parse error occurred"],
    }


class AudienceCriticAgent:
    """Simulates three distinct reader personas to critique a draft."""

    def review(self, draft: str, project_memory, section_brief: str) -> dict:
        """
        Run audience critique from three perspectives.

        Args:
            draft: The draft text to evaluate
            project_memory: ProjectMemory instance
            section_brief: string description of the section's purpose

        Returns:
            dict with keys: score, reactions, weaknesses, issues
        """
        if isinstance(section_brief, dict):
            section_brief = section_brief.get("brief", str(section_brief))

        prompt = _build_audience_critique_prompt(draft, project_memory, section_brief)
        response = call_llm(prompt, role="audience_critic")
        return _parse_audience_response(response)
