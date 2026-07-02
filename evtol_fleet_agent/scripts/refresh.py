from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evtol_fleet import config
from evtol_fleet.opensky import OpenSkyClient
from evtol_fleet.pipeline import refresh_flights, refresh_registry
from evtol_fleet.store import FleetStore


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Refresh the FAA registry roster and OpenSky flight history for tracked eVTOL manufacturers."
    )
    parser.add_argument("--db", default=config.DEFAULT_DB_PATH, help="Path to the SQLite cache file.")
    parser.add_argument("--skip-registry", action="store_true", help="Skip the FAA registry pull.")
    parser.add_argument("--skip-flights", action="store_true", help="Skip the OpenSky flight sync.")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="How many days back to sync for aircraft with no prior sync state.",
    )
    parser.add_argument(
        "--manufacturer",
        default=None,
        choices=sorted(config.MANUFACTURER_NAME_PATTERNS),
        help="Only sync flights for one manufacturer (default: all).",
    )
    args = parser.parse_args()

    with FleetStore(args.db) as store:
        if not args.skip_registry:
            counts = refresh_registry(store)
            print(f"Registry refreshed: {counts or 'no tracked aircraft found'}")

        if not args.skip_flights:
            end = int(datetime.now(tz=timezone.utc).timestamp())
            begin = end - args.days * 24 * 3600
            client = OpenSkyClient()
            if not client.is_authenticated():
                print(
                    "Warning: OPENSKY_CLIENT_ID/OPENSKY_CLIENT_SECRET not set; "
                    "using anonymous OpenSky access, which is heavily rate-limited."
                )

            def progress(done: int, total: int, n_number: str) -> None:
                print(f"[{done}/{total}] synced flights for {n_number}")

            results = refresh_flights(
                store, client, begin, end, manufacturer=args.manufacturer, progress_callback=progress
            )
            print(f"New flight rows inserted: {results}")


if __name__ == "__main__":
    main()
