# Draft Wringer

A personal editorial and evidence-audit agent: it critiques a draft, revises it in your voice, fact-checks its claims, and validates its references, while keeping every substantive change behind your approval.

The agent itself is a Claude Code subagent defined in [`.claude/agents/draft-wringer.md`](../.claude/agents/draft-wringer.md). That file holds the full specification (priorities, workflow, status vocabulary, evidence-ledger schema, approval rules, output package) plus notes on how it uses the tools available in Claude Code.

## Using it

In any Claude Code session opened in this repository, ask for it by name:

> Use the draft-wringer agent on `drafts/vertiport-memo.md`. Genre: policy report. Intensity: rigorous. Reference style: preserve existing. Substantive corrections: propose for approval.

Claude Code also picks it automatically when you ask to critique, revise, or fact-check a draft. Fill in whatever parts of the starter template apply:

```
Draft: [path or paste]
Genre/audience: [academic article, policy report, correspondence, etc.]
Voice samples/profile: [paths, or "unavailable"]
Intensity: [light, substantial, rigorous]
Reference style: [preserve existing, APA, other]
Evidence scope/as-of date: [specify if relevant]
Protected material: [specify]
Word limit: [specify]
Sources/full text: [paths to PDFs or documents]
Substantive corrections: [propose for approval; or specify authorized scope]
Requested output: [full package or specified components]
```

Revisions and reports are written to a new `<draft-stem>.wringer/` folder next to the draft; the original file is never modified. Because the agent runs as a subagent, proposed substantive changes come back to the main conversation as an approvals list for you to accept or reject.

## Voice profiles

Approved profiles go in `profiles/` as `academic.md`, `policy-report.md`, or `correspondence.md`. The agent proposes a profile from your samples and only writes it here after you approve it, so it persists across sessions through the repository rather than through any memory feature.

## Descriptive diagnostics

`diagnostics.py` (standard library only) assigns paragraph and sentence IDs and reports sentence-length distribution, runs of short sentences, repeated openings, recurring four-word phrases, paragraph-length patterns, and similar paragraph pairs:

```bash
python3 -I draft_wringer/diagnostics.py path/to/draft.md          # Markdown report
python3 -I draft_wringer/diagnostics.py path/to/draft.md --json   # JSON
```

The output lists its methods and limitations. These are surface signals for review, not an authorship test, and they do not decide rewrites.

## Tests

```bash
cd draft_wringer && python -m pytest tests
```
