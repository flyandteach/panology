# AMRG Weekly Literature Watch Agent

A weekly agent that searches [OpenAlex](https://openalex.org) for new
research on Advanced Air Mobility (AAM), Urban Air Mobility (UAM), eVTOLs,
electric aircraft, vertiports, and AI in aviation; keeps only articles with
a public full-text link; downloads and reads them; and produces an
AMRG-template summary (with extracted figures, a writing-quality score, and
a heuristic fact check) delivered as a Google Doc, with a weekly digest
emailed out summarizing what ran.

**Read the Limitations section before relying on this for anything
time-sensitive.** Full-text availability is OpenAlex's own open-access
flag (not a scraped link), but its fact-checking is still a sanity check,
not a source-verified audit.

This originally scraped Google Scholar, which has no public API and
CAPTCHA-blocks cloud/CI IP ranges. It was switched to OpenAlex -- a free,
documented REST API with no anti-bot wall and a first-class open-access
field -- after that proved unreliable in practice.

---

## What it does, end to end

1. **Search** — queries the OpenAlex Works API for each topic in
   `config.SEARCH_TOPICS`, sorted newest-first and limited to the last
   `config.LOOKBACK_DAYS` days (`agents/article_search.py`).
2. **Filter** — keeps only results where OpenAlex's own open-access data
   points at a real PDF (surfaced as `pdf_url`), and that haven't been
   processed in a previous run (`state/seen_articles.json`).
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
8. **Email** — sends a digest (new articles + links, search coverage by
   topic, any blocked/errored topics) via SMTP (`agents/email_notify.py`).
   Sent every run, including "nothing new this week," so a silently
   blocked run is still visible.
9. **Record** — marks the article as seen so it isn't reprocessed next week.

Any single article failing (bad download, unparsable PDF, rate-limited
search) is logged in the run report and does not stop the rest of the run.

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
| `EMAIL_SMTP_USER` + `EMAIL_SMTP_PASSWORD` | Weekly digest email | A Gmail address and a Gmail **App Password** for it (not your normal password) — requires 2FA enabled on that account, then generate one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). Without these, the pipeline still runs; it just skips the email and says so in the run report. |
| `EMAIL_TO` | Weekly digest email | Recipient(s), comma-separated. Defaults to `flyandteach@gmail.com`. |
| `OPENALEX_MAILTO` | Search reliability (optional) | A contact address identifying requests for OpenAlex's "polite pool" (better reliability under load). This is sent to OpenAlex on every request, so it's opt-in — leave unset to use the default shared pool. |
| `OPENALEX_API_KEY` | Search reliability (optional) | A free personal key ([docs](https://docs.openalex.org/how-to-use-the-api/api-overview#api-key)) for a dedicated rate budget instead of sharing the lowest-priority anonymous tier with every other caller. Not required; the pipeline works without it. |

### Run it once

```bash
python app.py show-config
python app.py run-weekly --dry-run          # search + score, skip upload/email/dedupe
python app.py run-weekly --no-email         # everything except the email
python app.py run-weekly --report-json out.json
```

---

## Running it weekly

`.github/workflows/amrg_weekly.yml` runs `run-weekly` every Monday via
GitHub Actions and commits the updated `state/seen_articles.json` back to
the branch so dedupe persists across runs (Actions runners are ephemeral).
Configure `ANTHROPIC_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON`,
`GOOGLE_DRIVE_FOLDER_ID`, `EMAIL_SMTP_USER`, and `EMAIL_SMTP_PASSWORD` as
repository secrets (Settings → Secrets and variables → Actions) for it to
actually deliver anything — without them it will still run (mock summaries,
local `.docx` only, no email) but won't reach Drive or your inbox.
`EMAIL_TO` is optional there too (defaults to `flyandteach@gmail.com`), and
so are `OPENALEX_MAILTO`/`OPENALEX_API_KEY` if OpenAlex's anonymous tier
turns out to need more headroom than a single GitHub Actions runner's IP
gets by default.

If you'd rather trigger it from a scheduled Claude Code session/Routine
instead of GitHub Actions, point that Routine's prompt at
`python amrg_agent/app.py run-weekly` in this repo on a weekly cron.

---

## Limitations (read before trusting the output)

- **OpenAlex's anonymous tier shares a rate budget with everyone else
  hitting the API unauthenticated.** Under load (e.g. many sessions on the
  same IP range, like a shared CI/sandbox pool) a topic can come back
  `blocked: true` in the run report for the rest of that day — that's
  rate-limiting, not a bug. `OPENALEX_MAILTO` and especially
  `OPENALEX_API_KEY` (free, instant via email verification) give a
  dedicated budget and should make this rare in production. There's no
  CAPTCHA/anti-bot wall to fight, unlike the Google-Scholar-scraping
  approach this replaced.
- **"Public full text" means OpenAlex's own open-access field, nothing
  more.** `best_oa_location`/`open_access.oa_url` can occasionally point
  at an HTML landing page instead of a direct PDF; those are skipped
  rather than mis-parsed (`agents/pdf_extract.py` checks Content-Type
  before trusting it).
- **OpenAlex's index, like any aggregator, isn't exhaustive or
  instantaneous.** New papers can take time to appear, and very
  recent/niche venues may be under-indexed relative to Scholar's broader
  (if unreliable) crawl.
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
    article_search.py     # OpenAlex search + open-access full-text detection
    pdf_extract.py         # PDF download + text/figure extraction
    fact_check.py           # reference verification + claim plausibility
    scoring.py               # readability + writing-quality formula
    summarizer.py             # AMRG template summary assembly
    drive_upload.py            # docx build + Google Drive upload
    email_notify.py              # weekly digest email (SMTP)
  prompts/
    amrg_template.md      # the AMRG summary prompt/template
  state/
    seen_articles.json    # dedupe across weekly runs
  output/                  # local .docx + extracted figures (gitignored)
  tests/                    # unit tests for pure-function pieces
```
