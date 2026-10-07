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
    """Fetch recent fleet activity first, then fairly backfill historical gaps.

    Resumes from each aircraft's saved watermark, saves progress after every
    day-window so an interrupted run loses nothing, never syncs past the settled
    point (see settled_sync_end), and keeps going past a single aircraft's error.
    Run-wide problems (host blocked, credits exhausted, bad credentials) stop the
    run with a clear `stopped_reason` instead of burning retries on every aircraft.
    """
    settled = settled_sync_end()
    end = settled if end is None else min(end, settled)
    begin = begin // config.DAY_SECONDS * config.DAY_SECONDS
    report = SyncReport()
    aircraft_rows = store.list_aircraft(manufacturer)
    if not aircraft_rows or begin >= end:
        return report
    # Rotate first aircraft daily so a quota smaller than one fleet sweep cannot
    # indefinitely starve aircraft at the end of the roster.
    rotation = (end // config.DAY_SECONDS) % len(aircraft_rows)
    aircraft_rows = aircraft_rows[rotation:] + aircraft_rows[:rotation]
    recent_begin = max(begin, end - 2 * config.DAY_SECONDS)
    failed = set()

    def stop(error):
        report.stopped_reason = str(error)
        report.stop_error = error
        logger.error("Stopping flight sync: %s", error)

    # Spend the first requests on recent activity across the fleet. Do not move
    # a historical watermark over unqueried gaps merely because recent records
    # were received. The following backfill pass closes those gaps separately.
    for index, aircraft in enumerate(aircraft_rows):
        icao24, n_number = aircraft["icao24"], aircraft["n_number"]
        report.new_flights[n_number] = 0
        try:
            flights = client.get_flights_for_aircraft(icao24, recent_begin, end)
            report.new_flights[n_number] += store.insert_flights(flights)
            watermark = store.get_sync_state(icao24)
            if (watermark is not None and watermark >= recent_begin) or begin == recent_begin:
                store.set_sync_state(icao24, end)
            if pause_between_requests:
                time.sleep(pause_between_requests)
        except OpenSkyError as error:
            stop(error)
            break
        except Exception as error:
            failed.add(icao24)
            report.errors[n_number] = f"{type(error).__name__}: {error}"
        if progress_callback:
            progress_callback(index + 1, len(aircraft_rows), n_number)

    # Backfill one day per aircraft per pass, preserving progress after each
    # successful request instead of consuming all credits on the first aircraft.
    while report.stop_error is None:
        progressed = False
        for aircraft in aircraft_rows:
            icao24, n_number = aircraft["icao24"], aircraft["n_number"]
            if icao24 in failed:
                continue
            cursor = max(begin, store.get_sync_state(icao24) or begin)
            if cursor >= end:
                continue
            try:
                for synced_through, flights in client.iter_flight_windows(
                    icao24, cursor, min(cursor + config.DAY_SECONDS, end), pause_between_requests
                ):
                    report.new_flights[n_number] += store.insert_flights(flights)
                    store.set_sync_state(icao24, synced_through)
                    progressed = True
            except OpenSkyError as error:
                stop(error)
                break
            except Exception as error:
                failed.add(icao24)
                report.errors[n_number] = f"{type(error).__name__}: {error}"
        if not progressed:
            break
    watermarks = [store.get_sync_state(a["icao24"]) for a in aircraft_rows]
    report.synced_through = min(watermarks) if all(w is not None for w in watermarks) else None
    return report
