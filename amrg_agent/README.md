# AMRG Weekly Literature Watch Agent

A weekly agent that searches Google Scholar for new research on Advanced Air
Mobility (AAM), Urban Air Mobility (UAM), eVTOLs, electric aircraft,
vertiports, and AI in aviation; keeps only articles with a public full-text
link; downloads and reads them; and produces an AMRG-template summary
(with extracted figures, a writing-quality score, and a heuristic fact
check) delivered as a Google Doc.

**Read the Limitations section before relying on this for anything
time-sensitive.** This is a best-effort scraper against a service with no
public API, and its fact-checking is a sanity check, not a source-verified
audit.

---

## What it does, end to end

1. **Search** — queries Google Scholar (via the unofficial `scholarly`
   package) for each topic in `config.SEARCH_TOPICS`, sorted by date.
2. **Filter** — keeps only results where Scholar shows a free full-text
   link (the "[PDF]"-style link to the right of a result — surfaced as
   `eprint_url`), and that haven't been processed in a previous run
   (`state/seen_articles.json`).
3. **Download & extract** — fetches the PDF and pulls out the full text and
   embedded figures (`agents/pdf_extract.py`, via PyMuPDF).
4. **Fact-check (heuristic)** — extracts the reference list and checks each
   entry against Crossref's free API, and runs an LLM plausibility pass over
   numeric claims (`agents/fact_check.py`). See Limitations.
5. **Score writing quality** — computes Readability, the six weighted
   Comprehensive Writing Quality components, and the blended Final Writing
   Score exactly per the AMRG formula (`agents/scoring.py`).
6. **Summarize** — has Claude write the What / Who / Where / Summary /
   Keywords sections per `prompts/amrg_template.md`, referencing extracted
   figures by number (`agents/summarizer.py`).
7. **Deliver** — renders the summary + figures to a `.docx` and uploads it
   to a Google Drive folder as a Google Doc (`agents/drive_upload.py`).
8. **Record** — marks the article as seen so it isn't reprocessed next week.

Any single article failing (bad download, unparsable PDF, blocked search)
is logged in the run report and does not stop the rest of the run.

---

## Setup

```bash
cd amrg_agent
pip install -r requirements.txt
python -m nltk.downloader cmudict   # one-time; textstat's readability scorer needs this
```

### Required/optional configuration (environment variables)

| Variable | Required for | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Summaries + LLM-rated scores | Without it, those steps fall back to mock/placeholder output so the pipeline still runs end-to-end. |
| `GOOGLE_DRIVE_FOLDER_ID` | Drive delivery | Folder must already exist and be shared (Editor) with the service account's email. Without it, summaries are still built as local `.docx` files under `output/`. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` or `GOOGLE_SERVICE_ACCOUNT_FILE` | Drive delivery | Service-account key JSON (inline or path). Create one in Google Cloud Console with the Drive API enabled, then share the target folder with `<name>@<project>.iam.gserviceaccount.com`. |

### Run it once

```bash
python app.py show-config
python app.py run-weekly --dry-run          # search + score, skip upload/dedupe
python app.py run-weekly --report-json out.json
```

---

## Running it weekly

`.github/workflows/amrg_weekly.yml` runs `run-weekly` every Monday via
GitHub Actions and commits the updated `state/seen_articles.json` back to
the branch so dedupe persists across runs (Actions runners are ephemeral).
Configure `ANTHROPIC_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON`, and
`GOOGLE_DRIVE_FOLDER_ID` as repository secrets for it to actually deliver
anything — without them it will still run (mock summaries, local `.docx`
only) but won't reach Drive.

If you'd rather trigger it from a scheduled Claude Code session/Routine
instead of GitHub Actions, point that Routine's prompt at
`python amrg_agent/app.py run-weekly` in this repo on a weekly cron.

---

## Limitations (read before trusting the output)

- **Google Scholar has no public API.** This uses the unofficial
  `scholarly` package to scrape the public results page, which is against
  Google's Terms of Service and gets CAPTCHA-blocked on cloud/CI IP ranges
  fairly often. Expect some weeks (or some topics within a week) to come
  back empty with `blocked: true` in the run report — that's Scholar
  rate-limiting the run, not a bug. There is no key-based fix for this
  short of a paid search API (e.g. SerpApi's Scholar endpoint), which
  wasn't part of this build.
- **"Public full text" means Scholar's own eprint link, nothing more.**
  Some of those links land on an HTML page instead of a direct PDF (e.g. a
  publisher landing page); those are skipped rather than mis-parsed.
- **Fact-check is a heuristic sanity check, not verification.** Reference
  "not found in Crossref" does not mean fabricated — plenty of legitimate
  sources (government/industry reports, some conference proceedings)
  aren't Crossref-indexed. The claim-plausibility pass is an LLM read of
  internal consistency, not a check against primary data.
- **No plagiarism-overlap or AI-authorship detection.** Neither has a
  reliable free/unsupervised tool, and a fabricated-looking percentage or
  likelihood score would be more misleading than useful. If you have a
  licensed tool for either (Turnitin, Copyleaks, Originality.ai, etc.),
  wire its API into `agents/fact_check.py` — `run_fact_check()`'s return
  dict is where a `plagiarism` / `ai_detection` key would slot in, and
  `agents/summarizer.py::_format_fact_check_section` is where it would
  render.
- **Writing-quality scores mix formula and judgment.** Readability, Lexical
  Diversity, and Syntactic Complexity are computed directly from the text.
  Cohesion, Semantic Complexity, Grammar, and Topic Relevance are LLM-rated
  (same pattern as `book_agent`'s audience-critique scores) because those
  are genuinely judgment calls a formula can't make well — treat them as a
  consistent second opinion, not ground truth.

---

## Directory structure

```
amrg_agent/
  app.py                 # CLI entry point
  pipeline.py             # orchestrates the full weekly run
  config.py               # topics, thresholds, paths, formula weights
  agents/
    scholar_search.py     # Google Scholar search + full-text detection
    pdf_extract.py         # PDF download + text/figure extraction
    fact_check.py           # reference verification + claim plausibility
    scoring.py               # readability + writing-quality formula
    summarizer.py             # AMRG template summary assembly
    drive_upload.py            # docx build + Google Drive upload
  prompts/
    amrg_template.md      # the AMRG summary prompt/template
  state/
    seen_articles.json    # dedupe across weekly runs
  output/                  # local .docx + extracted figures (gitignored)
  tests/                    # unit tests for pure-function pieces
```
