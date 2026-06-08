# Recursive Editorial Book Agent

A structured manuscript-production system that uses multiple specialized AI agents to draft, review, and refine book sections through a recursive quality gate loop.

This is **not a chatbot**. It is a production pipeline where each section passes through drafting, line editing, repetition checking, audience critique, and a final quality gate before being approved.

---

## Overview

The system works as follows:

1. **Architect Agent** generates a structured book outline from your project brief
2. **Drafter Agent** writes each section using project memory and prior approved summaries as context
3. **Line Editor Agent** reviews prose quality, sentence rhythm, transitions, and word choice
4. **Repetition Checker Agent** combines computational text metrics with LLM analysis to catch repeated phrases, ideas, and structural patterns
5. **Audience Critic Agent** simulates three distinct reader personas (professional editor, intelligent general reader, target-market reader)
6. **Quality Gate Agent** aggregates all scores against configured thresholds and determines pass/fail
7. If the gate fails, the system revises automatically (up to 5 cycles), targeting the specific failed dimensions each time
8. The user is presented with the best draft and a full scorecard, then chooses to Approve / Revise / Reject / Pause

---

## Installation

```bash
cd book_agent
pip install -r requirements.txt
```

### Optional: Connect to Claude API

```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

Without an API key, the system runs in **mock mode** — realistic fake outputs are generated so you can test the full pipeline end-to-end.

---

## Quick Start

```bash
# Create a new project
python app.py new-project

# Generate an outline
python app.py create-outline

# Write the next section (full pipeline)
python app.py write-next-section

# View project status
python app.py show-scorecard

# Export the completed manuscript
python app.py export-manuscript
```

---

## Command Reference

| Command | Description |
|---|---|
| `new-project` | Create a new book project interactively |
| `load-project <path>` | Load an existing project and show status |
| `create-outline` | Generate a book outline using the Architect Agent |
| `write-next-section` | Run the full pipeline on the next pending section |
| `review-current-section` | Run review agents on an existing draft without re-drafting |
| `approve-current-section` | Manually approve the current section draft |
| `show-scorecard` | Display section status and completion progress |
| `show-memory` | Display the full project memory state |
| `export-manuscript` | Export all approved sections as a single Markdown file |

### Project Directory

By default, commands operate on the current directory. Use `-p` or `--project-dir` to specify a different path:

```bash
python app.py -p /path/to/my/book write-next-section
```

---

## How to Connect to the Claude API

1. Get an API key from [console.anthropic.com](https://console.anthropic.com)
2. Set the environment variable:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
3. The system will automatically use Claude for all agent calls

The system uses `claude-sonnet-4-6` by default. You can change this in `config.py`.

---

## Project Memory Structure

The project state is stored in `memory/project_memory.json`:

```json
{
  "project": {
    "title": "Book title",
    "genre": "nonfiction",
    "audience": "Target readers",
    "tone": "analytical",
    "style_profile": "Malcolm Gladwell — story-first",
    "status": "in_progress"
  },
  "outline": [
    {
      "id": "intro",
      "title": "Introduction",
      "type": "introduction",
      "brief": "Hook the reader...",
      "target_word_count": 1500,
      "status": "approved"
    }
  ],
  "memory": {
    "approved_sections": [
      {
        "id": "intro",
        "title": "Introduction",
        "summary": "First two sentences...",
        "word_count": 1423,
        "approved_at": "2026-01-01T00:00:00"
      }
    ],
    "key_terms": {},
    "major_claims": [],
    "used_examples": [],
    "used_metaphors": [],
    "phrases_to_avoid": [],
    "style_notes": [],
    "continuity_notes": []
  },
  "revision_history": []
}
```

The `phrases_to_avoid` list accumulates across sessions. The Repetition Checker and Drafter agents both consult this list to ensure no phrase is reused across sections.

---

## How Scoring Thresholds Work

Each section must meet ALL of the following thresholds to be approved:

| Dimension | Minimum Score | Notes |
|---|---|---|
| Line Edit Quality | 8.0 | From LineEditorAgent |
| Repetition & Redundancy | 9.0 | Blended computational + LLM score |
| Continuity | 9.0 | Derived from repetition checker |
| Critical Audience | 8.5 | Average of 3 reader personas |
| **Overall Average** | **8.5** | Must meet even if all individuals pass |

If any threshold fails, the system automatically:
1. Records which dimensions failed
2. Launches a new revision cycle targeting those specific issues
3. Tracks the best draft seen across all cycles

After 5 failed cycles, the best draft is presented to the user with a full diagnosis. The user then decides whether to approve anyway, reject, or pause for manual editing.

---

## Directory Structure

```
book_agent/
  app.py              # CLI entry point
  config.py           # Thresholds and constants
  agents/             # Six specialized agents
  prompts/            # Prompt templates (Markdown)
  memory/             # project_memory.json
  drafts/
    current/          # Latest draft per section
    approved/         # Approved section drafts
    rejected/         # Rejected section drafts
  exports/            # Assembled manuscript files
  tests/              # Unit tests
  utils/              # Memory, metrics, export utilities
```
