from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from evtol_fleet.metrics import summarize

AIRCRAFT_ROWS = [
    {"n_number": "N12345", "manufacturer": "Joby", "icao24": "a12345"},
    {"n_number": "N6789A", "manufacturer": "Archer", "icao24": "a6789a"},
]


def test_summarize_counts_flights_and_sums_duration():
    flight_rows = [
        {"n_number": "N12345", "first_seen": 1000, "last_seen": 4600},  # 1 hr
        {"n_number": "N12345", "first_seen": 5000, "last_seen": 6800},  # 0.5 hr
    ]
    summaries = {s.n_number: s for s in summarize(AIRCRAFT_ROWS, flight_rows)}

    assert summaries["N12345"].total_flights == 2
    assert summaries["N12345"].total_flight_hours == 1.5
    assert summaries["N6789A"].total_flights == 0
    assert summaries["N6789A"].total_flight_hours == 0.0


def test_summarize_handles_no_flights():
    summaries = summarize(AIRCRAFT_ROWS, [])
    assert all(s.total_flights == 0 for s in summaries)
    assert all(s.total_flight_seconds == 0 for s in summaries)


def test_summarize_ignores_negative_duration():
    flight_rows = [{"n_number": "N12345", "first_seen": 5000, "last_seen": 4000}]
    summaries = {s.n_number: s for s in summarize(AIRCRAFT_ROWS, flight_rows)}
    assert summaries["N12345"].total_flight_seconds == 0
