from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evtol_fleet import config
from evtol_fleet.faa_registry import diff_aircraft, fetch_manufacturer_aircraft, read_snapshot, write_snapshot
from evtol_fleet.opensky import OpenSkyClient
from evtol_fleet.pipeline import refresh_flights, sync_aircraft_list
from evtol_fleet.store import FleetStore

# CI runs monthly (see .github/workflows/evtol-fleet-monthly-refresh.yml), so pull a
# window comfortably wider than a month in case a run is delayed — sync_state means
# re-covering a few extra days costs nothing, it just returns already-seen flights as
# zero new inserts.
FLIGHT_SYNC_DAYS = 45


def main() -> None:
    print(f"Downloading FAA registry from {config.FAA_REGISTRY_URL}")
    print(f"(human-facing page: {config.FAA_REGISTRY_PAGE_URL})")
    previous_aircraft, previous_generated_at = read_snapshot(config.DEFAULT_REGISTRY_SNAPSHOT_PATH)
    new_aircraft = fetch_manufacturer_aircraft()
    write_snapshot(new_aircraft, config.DEFAULT_REGISTRY_SNAPSHOT_PATH)

    diff = diff_aircraft(previous_aircraft, new_aircraft)
    print(f"Previous snapshot: {len(previous_aircraft)} aircraft (generated {previous_generated_at})")
    print(f"New snapshot: {len(new_aircraft)} aircraft")
    if diff["added"]:
        print(f"  Added: {', '.join(diff['added'])}")
    if diff["removed"]:
        print(f"  Removed (deregistered or changed owner): {', '.join(diff['removed'])}")
    if not diff["added"] and not diff["removed"]:
        print("  No roster changes since last run.")

    store = FleetStore(config.DEFAULT_DB_PATH)
    registry_counts = sync_aircraft_list(store, new_aircraft)
    print(f"Aircraft by manufacturer: {registry_counts or 'none tracked'}")

    client = OpenSkyClient()
    if not client.is_authenticated():
        print(
            "WARNING: OPENSKY_CLIENT_ID/OPENSKY_CLIENT_SECRET not set — flight sync will use "
            "anonymous access, which is heavily rate-limited and may fail."
        )

    end = int(datetime.now(tz=timezone.utc).timestamp())
    begin = end - FLIGHT_SYNC_DAYS * 24 * 3600

    def on_progress(done: int, total: int, n_number: str) -> None:
        print(f"  [{done}/{total}] synced flights for {n_number}")

    flight_results = refresh_flights(store, client, begin, end, progress_callback=on_progress)
    print(f"New flight rows inserted: {flight_results}")
    store.close()


if __name__ == "__main__":
    main()
