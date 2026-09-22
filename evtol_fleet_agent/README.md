# eVTOL Fleet Tracker

Tracks aircraft registered to Joby, Archer, and BETA Technologies using the FAA
aircraft registry, cross-references flight activity from OpenSky Network, and
shows total flights and total flight time per aircraft (or per manufacturer) in
a Streamlit dashboard.

## Architecture

`registry.faa.gov` blocks requests from cloud-hosting platforms (including
Streamlit Community Cloud) outright — browser-like headers don't help, it's an
IP-range block. So the FAA registry is **not** fetched live by the deployed
app. Instead:

1. A scheduled GitHub Actions workflow (`.github/workflows/evtol-fleet-registry-refresh.yml`,
   weekly) runs `scripts/refresh_registry_snapshot.py` from CI, which *does*
   have unrestricted FAA egress, and commits the result to
   `data/tracked_aircraft.json` — a small JSON list of Joby/Archer/BETA
   aircraft (N-number, ICAO24, owner name, etc.).
2. `app.py` reads that committed file on every page load (`sync_registry_from_snapshot`)
   — a local file read, no network call, so it always works regardless of the
   FAA's blocking. This means **you never have to do anything to get the
   aircraft roster** — it's already in the repo, kept fresh automatically.
3. Only OpenSky flight history is fetched live, on demand, via the sidebar's
   **Sync latest OpenSky flights** button — OpenSky hasn't shown the same
   blocking behavior, and flight data is time-sensitive so it makes sense to
   pull on demand rather than bake into the weekly snapshot.

Flight data itself is cached in a local SQLite file so the dashboard doesn't
re-hit OpenSky on every view; see the ephemeral-storage note below for how
that interacts with Streamlit Community Cloud specifically.

## How it works

- `evtol_fleet/faa_registry.py` parses the FAA's `MASTER.txt` (from
  `ReleasableAircraft.zip`) and matches the registrant `NAME` field against
  configurable name patterns per manufacturer
  (`evtol_fleet/config.py: MANUFACTURER_NAME_PATTERNS`), extracting each
  matching aircraft's N-Number and Mode S hex code (ICAO24), which OpenSky
  needs to identify the aircraft. `write_snapshot`/`read_snapshot` save/load
  that result as JSON.
- `scripts/refresh_registry_snapshot.py` is the CI entry point: downloads the
  registry, matches manufacturers, writes `data/tracked_aircraft.json`.
- `evtol_fleet/opensky.py` queries OpenSky's `/flights/aircraft` REST endpoint
  per aircraft. OpenSky caps each request to a 30-day window, so longer ranges
  are automatically chunked (`iter_windows`) and 429 responses are retried with
  backoff.
- `evtol_fleet/store.py` caches aircraft and flights in SQLite, deduplicating
  flight rows and tracking a per-aircraft sync watermark for incremental
  refreshes.
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
quickly.

## Usage

```bash
streamlit run app.py
```

The aircraft roster (`data/tracked_aircraft.json`) loads automatically — no
setup step needed. Use the sidebar's **Sync latest OpenSky flights** button
to pull flight history for those aircraft, then filter by manufacturer or
N-number. The dashboard shows total aircraft selected, total flights, total
flight hours, a per-aircraft table, a flights-per-aircraft chart, and a raw
flight log.

There's also a CLI equivalent for local/manual use (`scripts/refresh.py`),
which does a live FAA pull + OpenSky sync in one shot — useful outside of CI
if you're on a network the FAA doesn't block:

```bash
python scripts/refresh.py --days 90
```

## Keeping the roster fresh

Normally you don't need to do anything — the GitHub Actions workflow refreshes
`data/tracked_aircraft.json` weekly and commits it automatically. To run it
early (e.g. right after adding a manufacturer name pattern), trigger it
manually from the repo's **Actions** tab → "eVTOL fleet registry refresh" →
**Run workflow**. Note: the `schedule` trigger only fires for workflow files
on the repo's default branch, so the weekly cadence won't kick in until this
is merged — `workflow_dispatch` (the manual "Run workflow" button) works on
any branch, though.

If you need a one-off refresh without CI at all, the app's sidebar has an
**Advanced: refresh the FAA aircraft roster now** expander with a live-pull
button and a manual-zip-upload fallback (download
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
4. Deploy — the roster shows up immediately from the committed snapshot.
   Click **Sync latest OpenSky flights** in the sidebar to populate flight
   data.

**Storage is ephemeral on Community Cloud.** The SQLite flight cache lives on
the container's local disk, which is wiped whenever the app restarts — on
every redeploy, and whenever the app wakes up after going to sleep from
inactivity. The aircraft roster reloads itself automatically either way
(it's read from the repo, not the wiped disk); only flight history needs a
re-sync after a restart.

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
- **The registry roster is only as fresh as the last CI run** (weekly by
  default). A brand-new aircraft registration could take up to a week to
  appear; trigger the workflow manually if you need it sooner.

## Tests

```bash
pip install pytest
pytest tests/
```

Tests cover FAA registry parsing/matching, the JSON snapshot round trip,
OpenSky window chunking, the SQLite cache, and flight-time aggregation using
fixture data — they don't hit the FAA or OpenSky network.
