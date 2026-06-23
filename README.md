# AAM Reality Monitor

AAM Reality Monitor is a local Python 3.11+ CLI for tracking public evidence about AAM/eVTOL OEMs and comparing company claims against observable certification, operations, infrastructure, production, financial, and source-backed evidence.

The MVP is intentionally **not** a live scraper and **not** a generic news summarizer. It persists local JSON records, separates claims from evidence, scores OEMs transparently, and generates Markdown/CSV/JSON outputs.

## Critical Operating Rules

- Never treat company claims as verified evidence by default.
- Prefer primary sources over media reports.
- Preserve both observation dates and event dates.
- Never fabricate sources, flight activity, or certification status.
- Distinguish announced, planned, under construction, tested, approved, and operational status.
- Missing data scores as zero rather than inferred progress.
- Placeholder sample records are clearly marked and do not represent real-world evidence.

## Quick Start

```bash
python -m aam_reality_monitor.app init-project --overwrite
python -m aam_reality_monitor.app list-oems
python -m aam_reality_monitor.app score-all
python -m aam_reality_monitor.app generate-report --output aam_reality_monitor/generated_reports/report.md
python -m aam_reality_monitor.app export-json --output exports/aam_export.json
python -m aam_reality_monitor.app export-csv --output exports/aam_scores.csv
```

## CLI Commands

- `init-project`
- `add-oem`
- `list-oems`
- `add-evidence`
- `add-claim`
- `link-evidence-to-claim`
- `score-oem`
- `score-all`
- `generate-report`
- `export-json`
- `export-csv`
- `show-claims`
- `show-evidence`
- `import-evidence-csv`
- `import-claims-csv`

Run command help with:

```bash
python -m aam_reality_monitor.app <command> --help
```

## Example Manual Evidence Entry

```bash
python -m aam_reality_monitor.app add-evidence \
  --oem-id joby \
  --event-date 2026-06-01 \
  --category certification \
  --source-type regulator \
  --source-name FAA \
  --source-url "https://example.invalid/replace-with-real-primary-source" \
  --title "Replace with verified title" \
  --summary "Replace with verified summary" \
  --evidence-strength 5 \
  --reliability 5 \
  --status verified
```

## Data Files

- `aam_reality_monitor/data/oems.json` contains OEM profiles.
- `aam_reality_monitor/data/evidence.json` contains factual evidence records.
- `aam_reality_monitor/data/claims.json` contains claim records.
- `aam_reality_monitor/data/scoring_weights.json` contains overall score weights.

## Scoring

Each OEM receives 0-100 scores for:

- Certification reality
- Operational evidence
- Infrastructure readiness
- Production readiness
- Financial endurance
- Claim reality

The overall score is a weighted average using default weights: certification 30%, operational 20%, infrastructure 15%, production 15%, financial 10%, claim reality 10%.

Evidence scores use evidence strength, reliability, source type, and status. Sample records are given no scoring value. Claims are scored separately by verification status and staleness.

## Tests

```bash
python -m pytest
```
