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

`state.json` is seeded with each case's real status as of 2026-09-04,
confirmed live against FAA's API (see below), so the first real run only
reports genuine changes from that point forward, not the initial baseline.

Add or remove cases by editing `watchlist.json`:

```json
{"asn": "2026-ANM-XXXX-OE", "label": "short description", "sponsor": "...", "nearest_airport": "..."}
```

## How it checks status

FAA publishes a public, no-login case lookup at
`https://oeaaa.faa.gov/oeaaa/services/case/{asn}` (confirmed against FAA's
own published WADL for the service, and live against these 4 real ASNs on
2026-09-04 via a GitHub Actions run — not just assumed). It returns XML
like:

```xml
<caseData><OECase>
  <asn>2026-ANM-456-OE</asn>
  <statusCode>NPF</statusCode>
  ...
</OECase></caseData>
```

`statusCode` is FAA's raw internal case code — it's *not* the plain-English
word ("Pending", "Evaluating", ...) shown on the OE/AAA web UI or a printed
Form 7460-1; that label is computed client-side and isn't in this API
response. Two mappings are confirmed live, cross-checked against the status
printed on the originally submitted PDFs for the same ASNs:

| statusCode | confirmed meaning |
|---|---|
| `NPF` | Pending |
| `HLD-Eval` | Evaluating |

Beyond those two, FAA's documented final-determination outcomes are
"Determination of No Hazard" (`DNH`) and "Determination of Hazard" (`DOH`)
per the FAA Air Traffic Program Handbook — but the exact `statusCode`
string FAA uses for a finished case hasn't been observed directly, so
**the tool does not rely on guessing that list to decide whether to notify
you.** It notifies on *any* change to `statusCode`, full stop; a
"DETERMINATION ISSUED" banner is a best-effort bonus (see
`LIKELY_TERMINAL_SUBSTRINGS` in `faa_notifier/checker.py`) that may not
fire for an unanticipated code, but the notification itself always will.

To check this yourself against the live site:

```bash
pip install -r requirements.txt
python -m faa_notifier.cli selftest 2026-ANM-457-OE
```

This prints the parsed status code/label for one ASN (plus a raw body
snippet on failure) without touching state or sending notifications.

Any failed check is printed to the console immediately (not hidden behind
a threshold); it only escalates to the configured notification channels
(email/webhook/GitHub issue) after 3 consecutive failures, to avoid noise
from a single transient blip.

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
