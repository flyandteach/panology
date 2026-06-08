"""
Book Architect Agent: Generates and refines book outlines.
"""

import os
import json
import re


def call_llm(prompt: str, role: str = "architect") -> str:
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
    """Return realistic mock architect output."""
    # Extract project info from prompt if possible
    title_match = re.search(r"Title:\s*(.+)", prompt)
    genre_match = re.search(r"Genre:\s*(.+)", prompt)
    title = title_match.group(1).strip() if title_match else "The Book"
    genre = genre_match.group(1).strip() if genre_match else "nonfiction"

    outline = {
        "title": title,
        "genre": genre,
        "premise": f"A comprehensive exploration of the core ideas that define {title}.",
        "sections": [
            {
                "id": "intro",
                "title": "Introduction: Setting the Stage",
                "type": "introduction",
                "brief": "Establish the core problem, hook the reader, and preview the journey ahead. Introduce the central argument without revealing the full resolution.",
                "target_word_count": 1500,
                "status": "pending",
            },
            {
                "id": "ch01",
                "title": "Chapter 1: The Foundation",
                "type": "chapter",
                "brief": "Lay the intellectual groundwork. Define key terms, present the historical context, and introduce the primary framework the book will use.",
                "target_word_count": 3000,
                "status": "pending",
            },
            {
                "id": "ch02",
                "title": "Chapter 2: The Problem in Depth",
                "type": "chapter",
                "brief": "Examine the central problem from multiple angles. Use case studies and concrete examples to make abstract concepts tangible.",
                "target_word_count": 3500,
                "status": "pending",
            },
            {
                "id": "ch03",
                "title": "Chapter 3: A New Perspective",
                "type": "chapter",
                "brief": "Introduce the book's central insight or solution. Show why prior approaches fall short and what's genuinely different here.",
                "target_word_count": 3500,
                "status": "pending",
            },
            {
                "id": "ch04",
                "title": "Chapter 4: Putting It Into Practice",
                "type": "chapter",
                "brief": "Move from theory to application. Provide actionable frameworks, detailed examples, and practical guidance.",
                "target_word_count": 4000,
                "status": "pending",
            },
            {
                "id": "conclusion",
                "title": "Conclusion: The Path Forward",
                "type": "conclusion",
                "brief": "Synthesise the journey, reinforce the central argument, and leave the reader with a compelling vision of what's possible.",
                "target_word_count": 1500,
                "status": "pending",
            },
        ],
        "notes": "Maintain a consistent analytical tone throughout. Each chapter should end with a transition that creates forward momentum.",
    }
    return json.dumps(outline, indent=2)


def _build_outline_prompt(project_memory, user_input: str) -> str:
    """Construct the architect prompt from template + memory."""
    prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
    template_path = os.path.join(prompts_dir, "architect.md")

    try:
        with open(template_path, "r", encoding="utf-8") as fh:
            template = fh.read()
    except FileNotFoundError:
        template = "You are a book architect. Create a detailed outline.\n\n{PROJECT_MEMORY}\n\nUser request: {USER_INPUT}\n\nReturn a JSON outline."

    context = project_memory.get_context_for_agent()
    prompt = template.replace("{PROJECT_MEMORY}", context)
    prompt = prompt.replace("{USER_INPUT}", user_input)
    return prompt


def _build_refine_prompt(project_memory, feedback: str) -> str:
    """Construct the refinement prompt."""
    prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
    template_path = os.path.join(prompts_dir, "architect.md")

    try:
        with open(template_path, "r", encoding="utf-8") as fh:
            template = fh.read()
    except FileNotFoundError:
        template = "You are a book architect. Refine the existing outline based on feedback.\n\n{PROJECT_MEMORY}\n\nFeedback: {FEEDBACK}\n\nReturn a revised JSON outline."

    context = project_memory.get_context_for_agent()
    current_outline = project_memory.get_outline()
    prompt = template.replace("{PROJECT_MEMORY}", context)
    prompt = prompt.replace("{USER_INPUT}", f"Refine based on feedback: {feedback}")
    prompt += f"\n\nCURRENT OUTLINE:\n{json.dumps(current_outline, indent=2)}"
    prompt += f"\n\nFEEDBACK TO ADDRESS:\n{feedback}"
    prompt += "\n\nReturn the complete revised outline as JSON."
    return prompt


def _parse_outline_response(response: str) -> dict:
    """Extract JSON dict from LLM response."""
    # Try direct JSON parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find any JSON-like structure
    match = re.search(r"\{.*\}", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Return minimal structure
    return {
        "title": "Unknown",
        "sections": [],
        "error": "Could not parse outline from LLM response",
        "raw": response[:500],
    }


class ArchitectAgent:
    """Generates and refines book structure outlines."""

    def create_outline(self, project_memory, user_input: str) -> dict:
        """Generate a new book outline based on project memory and user input."""
        prompt = _build_outline_prompt(project_memory, user_input)
        response = call_llm(prompt, role="architect")
        outline = _parse_outline_response(response)
        return outline

    def refine_outline(self, project_memory, feedback: str) -> dict:
        """Refine the existing outline based on feedback."""
        prompt = _build_refine_prompt(project_memory, feedback)
        response = call_llm(prompt, role="architect")
        outline = _parse_outline_response(response)
        return outline
