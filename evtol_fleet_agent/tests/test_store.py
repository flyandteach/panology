from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from evtol_fleet.faa_registry import RegisteredAircraft
from evtol_fleet.opensky import Flight
from evtol_fleet.store import FleetStore

JOBY = RegisteredAircraft(
    n_number="N12345", icao24="a12345", manufacturer="Joby", owner_name="JOBY AERO INC",
    year_mfr="2023", status_code="V",
)
ARCHER = RegisteredAircraft(
    n_number="N6789A", icao24="a6789a", manufacturer="Archer", owner_name="ARCHER AVIATION INC",
    year_mfr="2024", status_code="V",
)


def make_store() -> tuple[FleetStore, Path]:
    tmp_dir = Path(tempfile.mkdtemp())
    return FleetStore(tmp_dir / "test.db"), tmp_dir


def test_upsert_and_list_aircraft():
    store, _ = make_store()
    store.upsert_aircraft(JOBY)
    store.upsert_aircraft(ARCHER)

    all_aircraft = store.list_aircraft()
    assert {a["n_number"] for a in all_aircraft} == {"N12345", "N6789A"}

    joby_only = store.list_aircraft(manufacturer="Joby")
    assert [a["n_number"] for a in joby_only] == ["N12345"]
    store.close()


def test_replace_manufacturer_aircraft_drops_stale_rows():
    store, _ = make_store()
    store.replace_manufacturer_aircraft("Joby", [JOBY])
    assert {a["n_number"] for a in store.list_aircraft("Joby")} == {"N12345"}

    renamed = RegisteredAircraft(
        n_number="N99999", icao24="a99999", manufacturer="Joby", owner_name="JOBY AERO INC",
        year_mfr="2023", status_code="V",
    )
    store.replace_manufacturer_aircraft("Joby", [renamed])
    assert {a["n_number"] for a in store.list_aircraft("Joby")} == {"N99999"}
    store.close()


def test_insert_flights_deduplicates():
    store, _ = make_store()
    store.upsert_aircraft(JOBY)
    flight = Flight(
        icao24="a12345", first_seen=1000, last_seen=4600,
        est_departure_airport="KBFI", est_arrival_airport="KSEA", callsign="JOBY01",
    )
    inserted_first = store.insert_flights([flight])
    inserted_again = store.insert_flights([flight])

    assert inserted_first == 1
    assert inserted_again == 0
    assert len(store.flights_for_n_numbers(["N12345"])) == 1
    store.close()


def test_sync_state_roundtrip():
    store, _ = make_store()
    assert store.get_sync_state("a12345") is None
    store.set_sync_state("a12345", 123456)
    assert store.get_sync_state("a12345") == 123456
    store.set_sync_state("a12345", 999999)
    assert store.get_sync_state("a12345") == 999999
    store.close()


def test_flights_for_n_numbers_joins_manufacturer():
    store, _ = make_store()
    store.upsert_aircraft(JOBY)
    store.upsert_aircraft(ARCHER)
    store.insert_flights(
        [
            Flight("a12345", 1000, 2000, "KBFI", "KSEA", "JOBY01"),
            Flight("a6789a", 3000, 5000, "KSJC", "KOAK", "ARCH01"),
        ]
    )

    rows = store.flights_for_n_numbers(["N12345"])
    assert len(rows) == 1
    assert rows[0]["manufacturer"] == "Joby"
    store.close()
