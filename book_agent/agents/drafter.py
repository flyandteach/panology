"""
Drafting Agent: Writes section drafts based on project memory and section brief.
"""

import os
import re


def call_llm(prompt: str, role: str = "drafter") -> str:
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
    """Return realistic mock draft text."""
    title_match = re.search(r"Section Brief:\s*(.+?)(?:\n|$)", prompt)
    section_title = title_match.group(1).strip() if title_match else "This Section"

    return f"""The question that opens this chapter is not a simple one. It arrives wrapped in layers of assumption, each one requiring careful examination before we can move forward with confidence.

Consider the world as it exists before the argument takes hold. Most people accept the prevailing explanation without interrogation — not because they are incurious, but because the prevailing explanation has been built to resist interrogation. It fits neatly into the grooves of common sense. It explains enough to satisfy without explaining so much that it invites scrutiny.

But neatness is not the same as truth.

What we find, when we press against the edges of the conventional account, is that the structure begins to give way. Small inconsistencies appear. Anomalies accumulate. The explanation that seemed airtight in summary begins to breathe strangely when examined at length.

This is not a counsel of despair. It is, in fact, an opening.

The argument at the heart of {section_title} is this: the frameworks we inherit are not neutral containers for facts — they are active shapers of what facts we notice, how we interpret them, and what conclusions feel available to us. Once you see the frame, you cannot unsee it. And once you cannot unsee it, the obligation to think more carefully becomes unavoidable.

We will move through this territory methodically. First, we will examine what the inherited framework actually claims — stated plainly, without the softening that usually accompanies it. Then we will look at three cases where it fails in instructive ways. Finally, we will sketch the outlines of a better approach, one that preserves what is genuinely useful while discarding what has become an obstacle.

The goal is not demolition. The goal is clarity. And clarity, as we will see, demands more courage than we typically expect of ourselves.

There is a famous observation — attributed to various thinkers, which itself tells you something — that the hardest problems to solve are the ones we have forgotten are problems. We stopped asking because the answer seemed obvious. We stopped looking because we thought we had already seen.

The work of this chapter is to start asking again."""


def _build_draft_prompt(project_memory, section_brief: dict, metrics: dict) -> str:
    """Build the drafting prompt from template + context."""
    prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
    template_path = os.path.join(prompts_dir, "drafter.md")

    try:
        with open(template_path, "r", encoding="utf-8") as fh:
            template = fh.read()
    except FileNotFoundError:
        template = """You are an expert author. Write the following section.

{PROJECT_MEMORY}

Section Brief: {SECTION_BRIEF}

Prior Summaries:
{PRIOR_SUMMARIES}

Write the full section text now. Aim for {TARGET_WORD_COUNT} words."""

    context = project_memory.get_context_for_agent()
    approved = project_memory.get_approved_sections()

    prior_summaries = ""
    if approved:
        lines = []
        for s in approved:
            lines.append(f"- [{s['id']}] {s['title']}: {s.get('summary', 'No summary available.')}")
        prior_summaries = "\n".join(lines)
    else:
        prior_summaries = "(This is the first section — no prior content yet.)"

    phrases_to_avoid = project_memory.data["memory"].get("phrases_to_avoid", [])
    avoid_str = ", ".join(phrases_to_avoid) if phrases_to_avoid else "none flagged"

    target_wc = section_brief.get("target_word_count", 2000)
    brief_text = section_brief.get("brief", "Write this section.")
    section_title = section_brief.get("title", "Section")

    prompt = template
    prompt = prompt.replace("{PROJECT_MEMORY}", context)
    prompt = prompt.replace("{PRIOR_SUMMARIES}", prior_summaries)
    prompt = prompt.replace("{SECTION_BRIEF}", f"{section_title}: {brief_text}")
    prompt = prompt.replace("{TARGET_WORD_COUNT}", str(target_wc))
    prompt = prompt.replace("{PHRASES_TO_AVOID}", avoid_str)

    return prompt


class DrafterAgent:
    """Writes section drafts using project memory and prior context."""

    def draft_section(self, project_memory, section_brief: dict, metrics: dict = None) -> str:
        """
        Draft a section based on the project memory and section brief.

        Args:
            project_memory: ProjectMemory instance
            section_brief: dict with keys: id, title, brief, target_word_count
            metrics: optional dict of prior metrics (unused in base draft, available for revision)

        Returns:
            Draft text as a string.
        """
        if metrics is None:
            metrics = {}
        prompt = _build_draft_prompt(project_memory, section_brief, metrics)
        draft = call_llm(prompt, role="drafter")
        return draft
