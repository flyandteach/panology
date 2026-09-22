from __future__ import annotations

import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from evtol_fleet.faa_registry import (
    RegisteredAircraft,
    diff_aircraft,
    extract_master_csv,
    find_manufacturer_aircraft,
    parse_master_csv,
    parse_registry_zip,
)

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


def test_parse_registry_zip_end_to_end():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("MASTER.txt", HEADER + "".join(SAMPLE_ROWS))
    aircraft = parse_registry_zip(buffer.getvalue(), min_rows=0)

    assert {a.n_number for a in aircraft} == {"N12345", "N6789A", "N5551", "N9991"}


JOBY = RegisteredAircraft(
    n_number="N12345", icao24="a12345", manufacturer="Joby", owner_name="JOBY AERO INC",
    year_mfr="2023", status_code="V",
)
ARCHER = RegisteredAircraft(
    n_number="N6789A", icao24="a6789a", manufacturer="Archer", owner_name="ARCHER AVIATION INC",
    year_mfr="2024", status_code="V",
)
BETA = RegisteredAircraft(
    n_number="N5551", icao24="a5551", manufacturer="BETA", owner_name="BETA TECHNOLOGIES INC",
    year_mfr="2022", status_code="V",
)


def test_diff_aircraft_detects_additions_and_removals():
    diff = diff_aircraft(old=[JOBY, ARCHER], new=[JOBY, BETA])

    assert diff["added"] == ["N5551"]
    assert diff["removed"] == ["N6789A"]


def test_diff_aircraft_no_changes():
    diff = diff_aircraft(old=[JOBY, ARCHER], new=[JOBY, ARCHER])
    assert diff == {"added": [], "removed": []}


def test_diff_aircraft_against_empty_previous():
    diff = diff_aircraft(old=[], new=[JOBY, ARCHER])
    assert diff["added"] == ["N12345", "N6789A"]
    assert diff["removed"] == []


# --- Regression: the real MASTER.txt starts with a UTF-8 byte-order mark ---

import pytest


def _zip_of(master_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("MASTER.txt", master_bytes)
    return buffer.getvalue()


def test_byte_order_mark_does_not_hide_n_number_column():
    master = b"\xef\xbb\xbf" + sample_master_csv()
    aircraft = parse_registry_zip(_zip_of(master), min_rows=0)
    assert {a.n_number for a in aircraft} >= {"N12345", "N6789A", "N5551", "N9991"}


def test_faa_style_padded_headers_and_values_are_handled():
    master = (
        b"\xef\xbb\xbfN-NUMBER,SERIAL NUMBER,NAME                          ,MODE S CODE HEX,YEAR MFR,STATUS CODE,\r\n"
        b"314AB,SN1,JOBY AERO INC                  ,A3C1F2    ,2024,V ,\r\n"
    )
    aircraft = parse_registry_zip(_zip_of(master), min_rows=0)
    assert [(a.n_number, a.icao24, a.manufacturer) for a in aircraft] == [("N314AB", "a3c1f2", "Joby")]


def test_zero_matches_raises_instead_of_saving_empty_roster():
    master = b"N-NUMBER,NAME,MODE S CODE HEX,\n1111,DELTA AIR LINES INC,A1111,\n"
    with pytest.raises(ValueError, match="none matched"):
        parse_registry_zip(_zip_of(master), min_rows=0)


def test_truncated_registry_raises():
    with pytest.raises(ValueError, match="truncated"):
        parse_registry_zip(_zip_of(sample_master_csv()))


def test_missing_columns_raises():
    with pytest.raises(ValueError, match="missing expected column"):
        list(parse_master_csv(b"FOO,BAR\n1,2\n"))
