from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .faa_registry import RegisteredAircraft
from .opensky import Flight

SCHEMA = """
CREATE TABLE IF NOT EXISTS aircraft (
    n_number TEXT PRIMARY KEY,
    icao24 TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    owner_name TEXT,
    year_mfr TEXT,
    status_code TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS flights (
    icao24 TEXT NOT NULL,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    est_departure_airport TEXT,
    est_arrival_airport TEXT,
    callsign TEXT,
    fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (icao24, first_seen, last_seen)
);

CREATE TABLE IF NOT EXISTS sync_state (
    icao24 TEXT PRIMARY KEY,
    synced_through INTEGER NOT NULL
);
"""


class FleetStore:
    """SQLite-backed cache of FAA registry aircraft and OpenSky flight history.

    Caching locally means the dashboard loads instantly and refreshes (which hit
    slow, rate-limited external APIs) are a separate, explicit step run via the
    CLI script rather than on every page load.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "FleetStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def upsert_aircraft(self, aircraft: RegisteredAircraft) -> None:
        self._conn.execute(
            """
            INSERT INTO aircraft (n_number, icao24, manufacturer, owner_name, year_mfr, status_code, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(n_number) DO UPDATE SET
                icao24=excluded.icao24,
                manufacturer=excluded.manufacturer,
                owner_name=excluded.owner_name,
                year_mfr=excluded.year_mfr,
                status_code=excluded.status_code,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                aircraft.n_number,
                aircraft.icao24,
                aircraft.manufacturer,
                aircraft.owner_name,
                aircraft.year_mfr,
                aircraft.status_code,
            ),
        )
        self._conn.commit()

    def replace_manufacturer_aircraft(
        self, manufacturer: str, aircraft_list: Iterable[RegisteredAircraft]
    ) -> None:
        """Sync one manufacturer's roster: upsert current aircraft, drop ones no longer registered."""
        aircraft_list = list(aircraft_list)
        keep = {a.n_number for a in aircraft_list}
        existing = {
            row["n_number"]
            for row in self._conn.execute(
                "SELECT n_number FROM aircraft WHERE manufacturer = ?", (manufacturer,)
            )
        }
        stale = existing - keep
        if stale:
            self._conn.executemany(
                "DELETE FROM aircraft WHERE n_number = ?", [(n,) for n in stale]
            )
        for aircraft in aircraft_list:
            self.upsert_aircraft(aircraft)
        self._conn.commit()

    def list_aircraft(self, manufacturer: str | None = None) -> list[dict]:
        if manufacturer:
            cur = self._conn.execute(
                "SELECT * FROM aircraft WHERE manufacturer = ? ORDER BY n_number", (manufacturer,)
            )
        else:
            cur = self._conn.execute("SELECT * FROM aircraft ORDER BY manufacturer, n_number")
        return [dict(row) for row in cur.fetchall()]

    def insert_flights(self, flights: Iterable[Flight]) -> int:
        rows = [
            (f.icao24, f.first_seen, f.last_seen, f.est_departure_airport, f.est_arrival_airport, f.callsign)
            for f in flights
        ]
        if not rows:
            return 0
        cur = self._conn.executemany(
            """
            INSERT OR IGNORE INTO flights
                (icao24, first_seen, last_seen, est_departure_airport, est_arrival_airport, callsign)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._conn.commit()
        return cur.rowcount

    def get_sync_state(self, icao24: str) -> int | None:
        row = self._conn.execute(
            "SELECT synced_through FROM sync_state WHERE icao24 = ?", (icao24,)
        ).fetchone()
        return row["synced_through"] if row else None

    def set_sync_state(self, icao24: str, synced_through: int) -> None:
        self._conn.execute(
            """
            INSERT INTO sync_state (icao24, synced_through) VALUES (?, ?)
            ON CONFLICT(icao24) DO UPDATE SET synced_through=excluded.synced_through
            """,
            (icao24, synced_through),
        )
        self._conn.commit()

    def flights_for_n_numbers(self, n_numbers: Iterable[str]) -> list[dict]:
        n_numbers = list(n_numbers)
        if not n_numbers:
            return []
        placeholders = ",".join("?" for _ in n_numbers)
        cur = self._conn.execute(
            f"""
            SELECT f.*, a.n_number, a.manufacturer
            FROM flights f
            JOIN aircraft a ON a.icao24 = f.icao24
            WHERE a.n_number IN ({placeholders})
            ORDER BY f.first_seen
            """,
            n_numbers,
        )
        return [dict(row) for row in cur.fetchall()]
