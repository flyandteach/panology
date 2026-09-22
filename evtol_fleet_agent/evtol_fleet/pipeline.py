from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from . import config
from .faa_registry import RegisteredAircraft, fetch_manufacturer_aircraft, parse_registry_zip, read_snapshot
from .opensky import OpenSkyClient, OpenSkyError
from .store import FleetStore

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]


def sync_aircraft_list(store: FleetStore, aircraft: list[RegisteredAircraft]) -> dict[str, int]:
    """Sync an already-fetched aircraft list into the store, grouped by manufacturer."""
    by_manufacturer: dict[str, list[RegisteredAircraft]] = {}
    for a in aircraft:
        by_manufacturer.setdefault(a.manufacturer, []).append(a)
    for manufacturer, group in by_manufacturer.items():
        store.replace_manufacturer_aircraft(manufacturer, group)
    return {manufacturer: len(group) for manufacturer, group in by_manufacturer.items()}


def refresh_registry(store: FleetStore) -> dict[str, int]:
    """Pull the FAA registry and sync tracked manufacturers' rosters into the store."""
    return sync_aircraft_list(store, fetch_manufacturer_aircraft())


def refresh_registry_from_zip_bytes(store: FleetStore, zip_bytes: bytes) -> dict[str, int]:
    """Sync tracked manufacturers' rosters from an already-downloaded ReleasableAircraft.zip.

    Fallback for when this host can't download the FAA registry itself (e.g. the
    FAA blocking this host's IP range).
    """
    return sync_aircraft_list(store, parse_registry_zip(zip_bytes))


def sync_registry_from_snapshot(
    store: FleetStore, snapshot_path: str | None = None
) -> tuple[dict[str, int], str | None]:
    """Load the CI-generated registry snapshot (data/tracked_aircraft.json) into the store.

    This is the primary, no-network way the deployed app gets its aircraft roster —
    see scripts/monthly_refresh.py and the "eVTOL fleet monthly refresh" GitHub
    Actions workflow, which keep the snapshot current. Returns (counts per
    manufacturer, snapshot generation timestamp).
    """
    aircraft, generated_at = read_snapshot(snapshot_path or config.DEFAULT_REGISTRY_SNAPSHOT_PATH)
    return sync_aircraft_list(store, aircraft), generated_at


def settled_sync_end(now: int | None = None) -> int:
    """Latest timestamp whose OpenSky flight data is final.

    OpenSky builds /flights data in a nightly batch, so only "the previous day or
    earlier" is available. Syncing (and marking as synced) anything newer would
    permanently skip flights that land in a later batch.
    """
    now = int(time.time()) if now is None else now
    today_midnight = now // config.DAY_SECONDS * config.DAY_SECONDS
    return today_midnight - (config.OPENSKY_SETTLE_DAYS - 1) * config.DAY_SECONDS


@dataclass
class SyncReport:
    new_flights: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    stopped_reason: str | None = None
    stop_error: Exception | None = None
    synced_through: int | None = None

    @property
    def ok(self) -> bool:
        return not self.errors and self.stopped_reason is None


def refresh_flights(
    store: FleetStore,
    client: OpenSkyClient,
    begin: int,
    end: int | None = None,
    manufacturer: str | None = None,
    progress_callback: ProgressCallback | None = None,
    pause_between_requests: float = 1.0,
) -> SyncReport:
    """Fetch new OpenSky flight history for cached aircraft.

    Resumes from each aircraft's saved watermark, saves progress after every
    day-window so an interrupted run loses nothing, never syncs past the settled
    point (see settled_sync_end), and keeps going past a single aircraft's error.
    Run-wide problems (host blocked, credits exhausted, bad credentials) stop the
    run with a clear `stopped_reason` instead of burning retries on every aircraft.
    """
    settled = settled_sync_end()
    end = settled if end is None else min(end, settled)
    begin = begin // config.DAY_SECONDS * config.DAY_SECONDS
    report = SyncReport(synced_through=end)
    aircraft_rows = store.list_aircraft(manufacturer)
    for index, aircraft in enumerate(aircraft_rows):
        icao24, n_number = aircraft["icao24"], aircraft["n_number"]
        window_begin = max(begin, store.get_sync_state(icao24) or begin)
        inserted = 0
        try:
            if window_begin < end:
                for synced_through, flights in client.iter_flight_windows(
                    icao24, window_begin, end, pause_between_requests
                ):
                    inserted += store.insert_flights(flights)
                    store.set_sync_state(icao24, synced_through)
        except OpenSkyError as e:
            report.new_flights[n_number] = inserted
            report.stopped_reason = str(e)
            report.stop_error = e
            logger.error("Stopping flight sync: %s", e)
            break
        except Exception as e:  # one aircraft's bad response shouldn't sink the fleet
            report.errors[n_number] = f"{type(e).__name__}: {e}"
            logger.exception("Flight sync failed for %s", n_number)
        report.new_flights[n_number] = inserted
        if progress_callback:
            progress_callback(index + 1, len(aircraft_rows), n_number)
    return report
