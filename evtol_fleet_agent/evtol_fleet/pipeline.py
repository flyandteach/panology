from __future__ import annotations

import logging
from typing import Callable

from .faa_registry import RegisteredAircraft, fetch_manufacturer_aircraft, parse_registry_zip
from .opensky import OpenSkyClient
from .store import FleetStore

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]


def _sync_aircraft_to_store(store: FleetStore, aircraft: list[RegisteredAircraft]) -> dict[str, int]:
    by_manufacturer: dict[str, list[RegisteredAircraft]] = {}
    for a in aircraft:
        by_manufacturer.setdefault(a.manufacturer, []).append(a)
    for manufacturer, group in by_manufacturer.items():
        store.replace_manufacturer_aircraft(manufacturer, group)
    return {manufacturer: len(group) for manufacturer, group in by_manufacturer.items()}


def refresh_registry(store: FleetStore) -> dict[str, int]:
    """Pull the FAA registry and sync tracked manufacturers' rosters into the store."""
    return _sync_aircraft_to_store(store, fetch_manufacturer_aircraft())


def refresh_registry_from_zip_bytes(store: FleetStore, zip_bytes: bytes) -> dict[str, int]:
    """Sync tracked manufacturers' rosters from an already-downloaded ReleasableAircraft.zip.

    Fallback for when this host can't download the FAA registry itself (e.g. the
    FAA blocking this host's IP range).
    """
    return _sync_aircraft_to_store(store, parse_registry_zip(zip_bytes))


def refresh_flights(
    store: FleetStore,
    client: OpenSkyClient,
    begin: int,
    end: int,
    manufacturer: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    """Fetch new OpenSky flight history for cached aircraft, resuming from each
    aircraft's last synced timestamp so re-runs only pull new data."""
    aircraft_rows = store.list_aircraft(manufacturer)
    results: dict[str, int] = {}
    for index, aircraft in enumerate(aircraft_rows):
        icao24 = aircraft["icao24"]
        window_begin = max(begin, store.get_sync_state(icao24) or begin)
        if window_begin >= end:
            results[aircraft["n_number"]] = 0
        else:
            flights = client.get_flights_in_range(icao24, window_begin, end)
            results[aircraft["n_number"]] = store.insert_flights(flights)
            store.set_sync_state(icao24, end)
        if progress_callback:
            progress_callback(index + 1, len(aircraft_rows), aircraft["n_number"])
    return results
