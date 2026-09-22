from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evtol_fleet import config
from evtol_fleet.faa_registry import diff_aircraft, fetch_manufacturer_aircraft, read_snapshot, write_snapshot
from evtol_fleet.pipeline import sync_aircraft_list
from evtol_fleet.store import FleetStore



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

    store.close()

    # Flights are synced in a separate step (scripts/sync_flights.py) so a blocked or
    # rate-limited OpenSky can never stop the roster from being committed.
    print("Roster step done. Run scripts/sync_flights.py for OpenSky flight history.")


if __name__ == "__main__":
    main()
