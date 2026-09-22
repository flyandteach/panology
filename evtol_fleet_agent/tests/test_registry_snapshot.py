from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from evtol_fleet.faa_registry import RegisteredAircraft, read_snapshot, write_snapshot
from evtol_fleet.pipeline import sync_registry_from_snapshot
from evtol_fleet.store import FleetStore

JOBY = RegisteredAircraft(
    n_number="N12345", icao24="a12345", manufacturer="Joby", owner_name="JOBY AERO INC",
    year_mfr="2023", status_code="V",
)
ARCHER = RegisteredAircraft(
    n_number="N6789A", icao24="a6789a", manufacturer="Archer", owner_name="ARCHER AVIATION INC",
    year_mfr="2024", status_code="V",
)


def test_write_then_read_snapshot_round_trips():
    tmp_path = Path(tempfile.mkdtemp()) / "tracked_aircraft.json"
    write_snapshot([JOBY, ARCHER], tmp_path)

    aircraft, generated_at = read_snapshot(tmp_path)

    assert generated_at is not None
    assert {a.n_number for a in aircraft} == {"N12345", "N6789A"}


def test_read_snapshot_missing_file_returns_empty():
    aircraft, generated_at = read_snapshot(Path(tempfile.mkdtemp()) / "does_not_exist.json")
    assert aircraft == []
    assert generated_at is None


def test_sync_registry_from_snapshot_populates_store():
    snapshot_path = Path(tempfile.mkdtemp()) / "tracked_aircraft.json"
    write_snapshot([JOBY, ARCHER], snapshot_path)
    store = FleetStore(Path(tempfile.mkdtemp()) / "test.db")

    counts, generated_at = sync_registry_from_snapshot(store, str(snapshot_path))

    assert counts == {"Joby": 1, "Archer": 1}
    assert generated_at is not None
    assert {a["n_number"] for a in store.list_aircraft()} == {"N12345", "N6789A"}
    store.close()


def test_sync_registry_from_snapshot_missing_file_is_a_noop():
    store = FleetStore(Path(tempfile.mkdtemp()) / "test.db")
    counts, generated_at = sync_registry_from_snapshot(
        store, str(Path(tempfile.mkdtemp()) / "missing.json")
    )
    assert counts == {}
    assert generated_at is None
    assert store.list_aircraft() == []
    store.close()
