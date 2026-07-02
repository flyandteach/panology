from __future__ import annotations

import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from evtol_fleet.faa_registry import extract_master_csv, find_manufacturer_aircraft, parse_master_csv

HEADER = "N-NUMBER,NAME,MODE S CODE HEX,YEAR MFR,STATUS CODE,\n"

SAMPLE_ROWS = [
    "12345,JOBY AERO INC,A12345,2023,V,\n",
    "6789A,ARCHER AVIATION INC,A6789A,2024,V,\n",
    "5551,BETA TECHNOLOGIES INC,A5551,2022,V,\n",
    "9991,BETA AIR LLC,A9991,2021,V,\n",
    "1111,DELTA AIR LINES INC,A1111,2019,V,\n",
    "2222,JOBY AERO INC,,2023,V,\n",  # no Mode S hex -> should be skipped
]


def sample_master_csv() -> bytes:
    return (HEADER + "".join(SAMPLE_ROWS)).encode("utf-8")


def test_parse_master_csv_strips_whitespace():
    rows = list(parse_master_csv(sample_master_csv()))
    assert rows[0]["NAME"] == "JOBY AERO INC"
    assert rows[0]["N-NUMBER"] == "12345"


def test_find_manufacturer_aircraft_matches_known_manufacturers():
    rows = list(parse_master_csv(sample_master_csv()))
    aircraft = find_manufacturer_aircraft(rows)
    manufacturers = {a.n_number: a.manufacturer for a in aircraft}

    assert manufacturers["N12345"] == "Joby"
    assert manufacturers["N6789A"] == "Archer"
    assert manufacturers["N5551"] == "BETA"
    assert manufacturers["N9991"] == "BETA"


def test_find_manufacturer_aircraft_excludes_unmatched_and_missing_icao24():
    rows = list(parse_master_csv(sample_master_csv()))
    aircraft = find_manufacturer_aircraft(rows)
    n_numbers = {a.n_number for a in aircraft}

    assert "N1111" not in n_numbers  # unrelated owner
    assert "N2222" not in n_numbers  # missing Mode S hex


def test_find_manufacturer_aircraft_lowercases_icao24_and_prefixes_n_number():
    rows = list(parse_master_csv(sample_master_csv()))
    aircraft = find_manufacturer_aircraft(rows)
    joby = next(a for a in aircraft if a.n_number == "N12345")

    assert joby.icao24 == "a12345"
    assert joby.n_number.startswith("N")


def test_extract_master_csv_reads_master_txt_from_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("MASTER.txt", "header\nrow\n")
        zf.writestr("ACFTREF.txt", "unrelated\n")
    extracted = extract_master_csv(buffer.getvalue())

    assert extracted == b"header\nrow\n"


def test_extract_master_csv_raises_without_master_file():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("OTHER.txt", "data\n")

    try:
        extract_master_csv(buffer.getvalue())
        assert False, "expected ValueError"
    except ValueError:
        pass
