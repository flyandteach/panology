# eVTOL Fleet Tracker

Tracks aircraft registered to Joby, Archer, and BETA Technologies using the FAA
aircraft registry, cross-references flight activity from OpenSky Network, and
shows total flights and total flight time per aircraft (or per manufacturer) in
a Streamlit dashboard.

## Architecture

Both upstream sources block cloud hosting. `registry.faa.gov` returns 403 to
hosting-platform IP ranges, and OpenSky drops connections from many hosting
ranges (it shows up as a connection timeout). OpenSky has said publicly that it
filters hosting ranges and won't allowlist them. So the deployed app never
depends on a live call to either one:

1. **Roster**: the scheduled GitHub Actions workflow runs
   `scripts/monthly_refresh.py`, which downloads the FAA `ReleasableAircraft.zip`,
   matches Joby/Archer/BETA aircraft, logs added/removed N-numbers, and commits
   `data/tracked_aircraft.json`.
2. **Flights**: `scripts/sync_flights.py` pulls OpenSky history for every
   aircraft in the roster into `data/evtol_fleet.db`. The workflow tries this
   too, as a separate step, so a blocked OpenSky can't stop the roster commit.
   If that step fails with "could not be reached", GitHub's runners are being
   filtered as well, and the reliable option is to run it from a home or office
   network and commit the DB:

   ```bash
   cd evtol_fleet_agent
   export OPENSKY_CLIENT_ID=...  OPENSKY_CLIENT_SECRET=...
   python scripts/sync_flights.py --days 90
   git add data/evtol_fleet.db && git commit -m "Update flight history" && git push
   ```
3. `app.py` only reads those two committed files, so it always loads. The
   sidebar's **Sync flights from OpenSky now** expander is still there but is
   best-effort on Streamlit Cloud.

### OpenSky limits the sync is built around

From OpenSky's REST API documentation for `/flights/aircraft`:

- **Maximum interval is 2 days.** (Earlier versions of this tool used 29-day
  windows, which OpenSky rejects.) The sync uses one-UTC-day steps.
- **Only flights that departed and arrived inside the interval are returned.**
  Each request reaches 3 hours back into the previous day so flights crossing
  00:00 UTC (5 pm Pacific) aren't lost. Overlap duplicates are dropped by the
  database's primary key.
- **Data is published nightly, for the previous day or earlier.** The sync never
  marks the last ~2 days as done, so late-arriving flights are picked up next run.
- **Requests cost credits by calendar days touched** (1-2 days = 30 credits).
  Every request stays within 2 days. When credits run out (a 429 with a long
  retry-after) the run stops cleanly and saves progress per aircraft per day, so
  the next run resumes where it left off.

## How it works

- `evtol_fleet/faa_registry.py` parses the FAA's `MASTER.txt` (from
  `ReleasableAircraft.zip`) — the fixed-width-in-CSV layout is exactly as
  documented in the FAA's own `ardata.pdf` schema (N-Number at position 1-5,
  Registrant's Name at 59-108, Mode S Code Hex at 602-611, etc.) — and matches
  the registrant `NAME` field against configurable name patterns per
  manufacturer (`evtol_fleet/config.py: MANUFACTURER_NAME_PATTERNS`),
  extracting each matching aircraft's N-Number and Mode S hex code (ICAO24),
  which OpenSky needs to identify the aircraft. `write_snapshot`/`read_snapshot`
  save/load that result as JSON; `diff_aircraft` compares two snapshots by
  N-number to report additions/removals.
- `scripts/monthly_refresh.py` is the CI roster step (registry pull + diff).
- `scripts/sync_flights.py` is the flight step, runnable in CI or at home.
- `scripts/refresh_registry_snapshot.py` is a lighter-weight, registry-only
  version of the same pull, for local/manual use.
- `evtol_fleet/opensky.py` queries OpenSky's `/flights/aircraft` REST endpoint
  per aircraft in one-day steps (see limits above), retries short 429s, and
  raises distinct errors for blocked hosts, exhausted credits, and bad
  credentials so the pipeline can stop with a clear message.
- `evtol_fleet/store.py` caches aircraft and flights in SQLite, deduplicating
  flight rows and tracking a per-aircraft sync watermark so both scheduled
  CI job and on-demand syncs only fetch what's new since the last run.
- `evtol_fleet/metrics.py` aggregates cached flights into per-aircraft flight
  counts and total flight hours.

## Setup

```bash
cd evtol_fleet_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### OpenSky account (strongly recommended)

Anonymous OpenSky access is heavily rate-limited and often blocked for the
historical `/flights/aircraft` endpoint. Register a free account at
https://opensky-network.org, create an API client under your account
settings, and set:

```bash
export OPENSKY_CLIENT_ID=your-client-id
export OPENSKY_CLIENT_SECRET=your-client-secret
```

Without these, flight sync still runs but will likely hit rate limits
quickly. For the CI job to authenticate too, add the same two values as
**repository secrets** (Settings → Secrets and variables → Actions → New
repository secret) named `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET`.

## Usage

```bash
streamlit run app.py
```

Both the aircraft roster (`data/tracked_aircraft.json`) and a month's worth of
flight history (`data/evtol_fleet.db`) load automatically — no setup step
needed. Filter by manufacturer or N-number; use the sidebar's **Sync latest
OpenSky flights** button for anything more recent than the last scheduled
run. The dashboard shows total aircraft selected, total flights, total flight
hours, a per-aircraft table, a flights-per-aircraft chart, and a raw flight
log.

There's also a CLI equivalent for local/manual use (`scripts/refresh.py`),
which does a live FAA pull + OpenSky sync in one shot — useful outside of CI
if you're on a network the FAA doesn't block:

```bash
python scripts/refresh.py --days 90
```

## Keeping the roster and flight history fresh

Normally you don't need to do anything — the GitHub Actions workflow runs
weekly and commits the updated roster + flight history automatically,
logging any added/removed aircraft along the way. To run it early (e.g.
right after adding a manufacturer name pattern, or to get more-recent flight
data baked into the committed baseline), trigger it manually from the repo's
**Actions** tab → "eVTOL fleet scheduled refresh" → **Run workflow**. Note: the
`schedule` trigger only fires for workflow files on the repo's default
branch, so the weekly cadence won't kick in until this is merged —
`workflow_dispatch` (the manual "Run workflow" button) works on any branch,
though.

If you need a one-off registry refresh without CI at all, the app's sidebar
has an **Advanced: refresh the FAA aircraft roster now** expander with a
live-pull button and a manual-zip-upload fallback (download
`ReleasableAircraft.zip` yourself from a normal network, upload it there).

## Deploying to Streamlit Community Cloud

1. Push this branch (or merge it) so the code is on GitHub.
2. Go to https://share.streamlit.io → **New app**, pick the `panology` repo
   and the branch, and set the main file path to `evtol_fleet_agent/app.py`.
3. In the app's **Settings → Secrets**, add:
   ```toml
   OPENSKY_CLIENT_ID = "your-client-id"
   OPENSKY_CLIENT_SECRET = "your-client-secret"
   ```
   (`app.py` reads `st.secrets` first, falling back to environment variables
   for local runs.)
4. Deploy — the roster and a month of flight history show up immediately
   from the committed files. Click **Sync latest OpenSky flights** in the
   sidebar for anything more recent.

**Storage is ephemeral on Community Cloud** — the app's local disk is wiped
on every restart (redeploys, or waking from sleep). That no longer matters
for the baseline data: both the roster and the flight-history
snapshot are read from files committed to the repo, so a restart just falls
back to whatever the last CI run committed. Only *live* syncs done via the
sidebar button are session-only and get reset by a restart.

## Reliability notes / known limitations

- **Owner-name matching only catches aircraft registered directly under a
  manufacturer's name.** Aircraft delivered to customers, or registered under
  a leasing/trust entity, won't match. Add explicit mappings to
  `MANUAL_N_NUMBER_OVERRIDES` in `evtol_fleet/config.py` for those cases.
- **Aircraft without an assigned Mode S hex code are skipped** — the FAA
  assigns this only once an aircraft is registered, so brand-new aircraft may
  not appear until the FAA registry catches up.
- **Flight time is a track-based estimate, not official flight hours.** It's
  computed from OpenSky's ADS-B `firstSeen`/`lastSeen` timestamps per flight,
  which reflect when the aircraft was observable on ADS-B, not engine/Hobbs
  time. Test aircraft that don't broadcast ADS-B, or fly outside OpenSky's
  ground-station/satellite coverage, won't show up.
- **OpenSky's free-tier history depth and rate limits are OpenSky's, not
  this tool's.** Large fleets or long backfills may need multiple sync runs.
- **The roster and flight baseline are only as fresh as the last CI run**
  (weekly by default). Trigger the workflow manually if you need either
  sooner than that.
- **A "no roster changes" or empty diff doesn't guarantee nothing changed at
  the FAA** — if a CI run itself fails (e.g. hits a bot-protection
  interstitial instead of the real file), `download_registry()` now raises
  instead of silently committing an empty/stale result, so check the
  workflow run's status rather than assuming a quiet job means "no changes."

## Tests

```bash
pip install pytest
pytest tests/
```

Tests cover FAA registry parsing/matching, the JSON snapshot round trip and
diffing, OpenSky window chunking, the SQLite cache, and flight-time
aggregation using fixture data — they don't hit the FAA or OpenSky network.
