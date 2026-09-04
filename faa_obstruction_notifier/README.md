# FAA 7460 Obstruction Case Notifier

Watches a list of FAA OE/AAA Aeronautical Study Numbers (ASNs, format
`YYYY-REG-####-OE`) and notifies you when a case's status changes —
especially when it reaches a final determination.

## Watchlist

`watchlist.json` is seeded with the 4 distinct ASNs found in the submitted
Form 7460-1 PDFs, all sponsored by Tahoma Capital Partners near airport 8W5:

- `2026-ANM-456-OE`
- `2026-ANM-457-OE`
- `2026-ANM-1840-OE`
- `2026-ANM-1841-OE`

(Note: of the 5 PDFs originally provided, two — the ones named `...456OE.pdf`
and `...1840OE.pdf` — contained identical data for case `1840-OE`, and no PDF
actually contained case `458-OE`. If you get its real case number, add it by
editing `watchlist.json` as described below.)

`state.json` is seeded with each case's status as of 2026-09-04 (read
directly off the PDFs), so the first real run only reports genuine changes
from that point forward, not the initial baseline.

Add or remove cases by editing `watchlist.json`:

```json
{"asn": "2026-ANM-XXXX-OE", "label": "short description", "sponsor": "...", "nearest_airport": "..."}
```

## How it checks status

FAA publishes a public, no-login case lookup at
`https://oeaaa.faa.gov/oeaaa/services/case/{asn}`. This tool calls that
endpoint and scans the response for one of FAA's fixed status words
(`Pending`, `Evaluating`, `Circularized`, `Interim`, `Determined`, `Denied`,
`Withdrawn`, `Terminated`) rather than depending on an exact response
schema — so it keeps working even if the response format changes shape,
as long as one of those words appears.

**This endpoint could not be verified from within this sandboxed session**
(outbound network access to `oeaaa.faa.gov` is blocked here). Before relying
on this tool, verify it against the live FAA site from an environment with
normal internet access:

```bash
pip install -r requirements.txt
python -m faa_notifier.cli selftest 2026-ANM-457-OE
```

This prints the raw parsed result for one ASN without touching state or
sending notifications. If it reports `ok=False`, open
`faa_notifier/checker.py` and check `CASE_URL_TEMPLATE` / `_extract_status`
against whatever the live endpoint actually returns, and adjust — the
targeted logic to fix is isolated to that one function.

If a check ever fails 3 times in a row for a given ASN, the tool notifies
you that the checker itself needs attention (distinct from a status
change), so a broken endpoint doesn't fail silently.

## Running it

```bash
cd faa_obstruction_notifier
pip install -r requirements.txt
python -m faa_notifier.cli check
```

This checks every ASN in `watchlist.json`, updates `state.json`, and
notifies on any status change (always prints to the console; other
channels are opt-in via environment variables — see below).

### Option A: cron (your own machine/server)

```cron
0 */4 * * * cd /path/to/faa_obstruction_notifier && /usr/bin/python3 -m faa_notifier.cli check >> check.log 2>&1
```

### Option B: GitHub Actions (no server needed)

`.github/workflows/faa-7460-check.yml` runs the check every 4 hours,
commits the updated `state.json` back to the repo, and (with
`permissions: issues: write`, already set) opens or updates a GitHub issue
labeled `faa-7460-tracker` whenever a status changes — you'll get GitHub's
normal notification for that issue. No secrets are required for this path.

## Notification channels

All are optional and additive; console output always happens.

| Channel | Env vars |
|---|---|
| Email (SMTP) | `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_USER`, `SMTP_PASS`, `NOTIFY_EMAIL_TO`, `NOTIFY_EMAIL_FROM` |
| Webhook (Slack/Discord/generic) | `NOTIFY_WEBHOOK_URL`, `NOTIFY_WEBHOOK_FORMAT` (`slack`, `discord`, or `plain`) |
| GitHub issue | `GITHUB_TOKEN`, `GITHUB_REPOSITORY` (both auto-set in GitHub Actions) |

For GitHub Actions, set the email/webhook variables as repository secrets
if you want those channels too; otherwise the GitHub-issue channel alone
is enough to get notified.

## Tests

```bash
pip install pytest
python -m pytest tests/ -q
```
