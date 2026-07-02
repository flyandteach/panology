# eVTOL Fleet Tracker

Tracks aircraft registered to Joby, Archer, and BETA Technologies using the FAA
aircraft registry, cross-references flight activity from OpenSky Network, and
shows total flights and total flight time per aircraft (or per manufacturer) in
a Streamlit dashboard.

Unlike a single web app that fetches everything live on each page load, this
splits the work into two steps so failures are isolated and cheap to retry:

1. **Refresh** (`scripts/refresh.py`) pulls fresh data from the FAA and OpenSky
   into a local SQLite cache (`data/evtol_fleet.db`). This is the step that can
   hit network/rate-limit issues, so it's run separately and can be re-run
   safely — flight inserts are deduplicated and each aircraft resumes from its
   last synced timestamp.
2. **Dashboard** (`app.py`) only reads from the local cache, so it loads
   instantly and never depends on FAA/OpenSky being reachable at view time.

## How it works

- `evtol_fleet/faa_registry.py` downloads the FAA's `ReleasableAircraft.zip`
  (the public aircraft registry), parses `MASTER.txt`, and matches the
  registrant `NAME` field against configurable name patterns per manufacturer
  (`evtol_fleet/config.py: MANUFACTURER_NAME_PATTERNS`). It extracts each
  matching aircraft's N-Number and Mode S hex code (ICAO24), which OpenSky
  needs to identify the aircraft.
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

Without these, `scripts/refresh.py` still runs but will likely hit rate
limits quickly.

## Usage

Pull the FAA registry and the last 30 days of flights for all tracked
manufacturers:

```bash
python scripts/refresh.py
```

Useful flags:

```bash
python scripts/refresh.py --days 90                # backfill further for first-time sync
python scripts/refresh.py --manufacturer Joby       # only sync one manufacturer's flights
python scripts/refresh.py --skip-registry           # only refresh flights
python scripts/refresh.py --skip-flights            # only refresh the FAA roster
```

Then launch the dashboard:

```bash
streamlit run app.py
```

Use the sidebar to filter by manufacturer or specific N-numbers. The
dashboard shows total aircraft selected, total flights, total flight hours,
a per-aircraft table, a flights-per-aircraft chart, and a raw flight log.

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
  this tool's.** Large fleets or long backfills may need multiple
  `scripts/refresh.py` runs across separate days.
- The FAA registry and OpenSky must both be reachable from wherever you run
  `scripts/refresh.py`. If you're running this from a network-restricted
  sandbox, run the refresh step from a host with normal outbound internet
  access, then copy `data/evtol_fleet.db` to wherever the dashboard runs.

## Tests

```bash
pip install pytest
pytest tests/
```

Tests cover FAA registry parsing/matching, OpenSky window chunking, the
SQLite cache, and flight-time aggregation using fixture data — they don't
hit the FAA or OpenSky network.
