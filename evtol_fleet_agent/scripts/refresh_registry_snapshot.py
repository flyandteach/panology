from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evtol_fleet import config
from evtol_fleet.faa_registry import fetch_manufacturer_aircraft, write_snapshot


def main() -> None:
    aircraft = fetch_manufacturer_aircraft()
    write_snapshot(aircraft, config.DEFAULT_REGISTRY_SNAPSHOT_PATH)
    by_manufacturer: dict[str, int] = {}
    for a in aircraft:
        by_manufacturer[a.manufacturer] = by_manufacturer.get(a.manufacturer, 0) + 1
    print(f"Wrote {len(aircraft)} aircraft to {config.DEFAULT_REGISTRY_SNAPSHOT_PATH}: {by_manufacturer}")


if __name__ == "__main__":
    main()
