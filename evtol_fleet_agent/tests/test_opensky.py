from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from requests.exceptions import ConnectTimeout

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from evtol_fleet import config
from evtol_fleet.faa_registry import RegisteredAircraft
from evtol_fleet.opensky import (
    OpenSkyClient,
    OpenSkyCreditsExhausted,
    OpenSkyUnreachable,
    iter_windows,
)
from evtol_fleet.pipeline import refresh_flights, settled_sync_end
from evtol_fleet.store import FleetStore

DAY = config.DAY_SECONDS


# ---------- window chunking ----------

def test_iter_windows_single_window_when_under_limit():
    assert list(iter_windows(0, 1000, max_window_seconds=2000)) == [(0, 1000)]


def test_iter_windows_splits_on_aligned_boundaries():
    assert list(iter_windows(0, 100, max_window_seconds=30)) == [(0, 30), (30, 60), (60, 90), (90, 100)]
    # Unaligned start: first window runs only to the next boundary.
    assert list(iter_windows(10, 70, max_window_seconds=30)) == [(10, 30), (30, 60), (60, 70)]


def test_iter_windows_covers_full_range_without_gaps_or_overlap():
    windows = list(iter_windows(5, 1000, max_window_seconds=37))
    assert windows[0][0] == 5 and windows[-1][1] == 1000
    for (_, end_a), (start_b, _) in zip(windows, windows[1:]):
        assert end_a == start_b


def test_iter_windows_empty_range_yields_nothing():
    assert list(iter_windows(100, 100)) == []


def test_max_window_matches_opensky_two_day_limit():
    assert config.OPENSKY_MAX_WINDOW_SECONDS == 2 * DAY
    # A sync request (one day plus overlap) must fit in the limit and touch <= 2 UTC days.
    request_span = config.OPENSKY_SYNC_STEP_SECONDS + config.OPENSKY_WINDOW_OVERLAP_SECONDS
    assert request_span <= config.OPENSKY_MAX_WINDOW_SECONDS
    assert config.OPENSKY_WINDOW_OVERLAP_SECONDS < DAY


# ---------- fake HTTP ----------

class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def post(self, *a, **k):
        raise AssertionError("anonymous client should not request a token")


def flight_json(icao24, first, last):
    return {"icao24": icao24, "firstSeen": first, "lastSeen": last,
            "estDepartureAirport": "KXYZ", "estArrivalAirport": "KXYZ", "callsign": "JOBY1 "}


def make_client(responses):
    session = FakeSession(responses)
    client = OpenSkyClient(client_id=None, client_secret=None, session=session, sleep=lambda s: None)
    client.client_id = client.client_secret = None  # force anonymous regardless of env
    return client, session


# ---------- client behavior ----------

def test_404_means_no_flights():
    client, _ = make_client([FakeResponse(404)])
    assert client.get_flights_for_aircraft("abc123", 0, DAY) == []


def test_rejects_windows_over_two_days():
    client, _ = make_client([])
    with pytest.raises(ValueError):
        client.get_flights_for_aircraft("abc123", 0, 2 * DAY + 1)


def test_short_429_is_retried():
    client, session = make_client([
        FakeResponse(429, headers={"X-Rate-Limit-Retry-After-Seconds": "5"}),
        FakeResponse(200, [flight_json("abc123", 100, 200)]),
    ])
    flights = client.get_flights_for_aircraft("abc123", 0, DAY)
    assert len(flights) == 1 and flights[0].callsign == "JOBY1"
    assert len(session.calls) == 2


def test_long_429_raises_credits_exhausted_instead_of_sleeping():
    client, _ = make_client([FakeResponse(429, headers={"X-Rate-Limit-Retry-After-Seconds": "7200"})])
    with pytest.raises(OpenSkyCreditsExhausted) as exc:
        client.get_flights_for_aircraft("abc123", 0, DAY)
    assert exc.value.retry_after == 7200


def test_repeated_connect_timeouts_raise_unreachable():
    client, _ = make_client([ConnectTimeout("t")] * 3)
    with pytest.raises(OpenSkyUnreachable) as exc:
        client.get_flights_for_aircraft("abc123", 0, DAY)
    assert "home" in str(exc.value)


def test_day_windows_overlap_to_catch_flights_crossing_midnight():
    client, session = make_client([FakeResponse(404), FakeResponse(404)])
    list(client.iter_flight_windows("abc123", 10 * DAY, 12 * DAY, pause_between_requests=0))
    overlap = config.OPENSKY_WINDOW_OVERLAP_SECONDS
    assert [(c["begin"], c["end"]) for c in session.calls] == [
        (10 * DAY - overlap, 11 * DAY),
        (11 * DAY - overlap, 12 * DAY),
    ]


# ---------- pipeline ----------

def make_store_with(*aircraft):
    store = FleetStore(Path(tempfile.mkdtemp()) / "t.db")
    for a in aircraft:
        store.upsert_aircraft(a)
    return store


A1 = RegisteredAircraft("N1AA", "aaa111", "Archer", "ARCHER AVIATION INC", "2024", "V")
A2 = RegisteredAircraft("N2BB", "bbb222", "Joby", "JOBY AERO INC", "2024", "V")


def test_settled_end_excludes_today_and_yesterday():
    now = 100 * DAY + 5 * 3600  # 05:00 UTC on day 100
    assert settled_sync_end(now) == 99 * DAY


def test_refresh_saves_progress_and_stops_cleanly_when_credits_run_out(monkeypatch):
    monkeypatch.setattr("evtol_fleet.pipeline.settled_sync_end", lambda now=None: 13 * DAY)
    store = make_store_with(A1, A2)
    client, _ = make_client([
        FakeResponse(200, [flight_json("aaa111", 10 * DAY + 100, 10 * DAY + 900)]),
        FakeResponse(429, headers={"X-Rate-Limit-Retry-After-Seconds": "9999"}),
    ])
    report = refresh_flights(store, client, begin=10 * DAY, pause_between_requests=0)
    assert report.stopped_reason and "credits" in report.stopped_reason
    assert report.new_flights["N1AA"] == 1
    assert store.get_sync_state("aaa111") == 11 * DAY  # first day kept
    assert store.get_sync_state("bbb222") is None      # never reached

    # Resume: continues from day 11 for A1, then does A2 from scratch.
    client2, session2 = make_client([FakeResponse(404)] * 2 + [FakeResponse(404)] * 3)
    report2 = refresh_flights(store, client2, begin=10 * DAY, pause_between_requests=0)
    assert report2.ok
    assert session2.calls[0]["end"] == 12 * DAY
    assert store.get_sync_state("aaa111") == 13 * DAY
    assert store.get_sync_state("bbb222") == 13 * DAY


def test_refresh_continues_past_single_aircraft_error(monkeypatch):
    monkeypatch.setattr("evtol_fleet.pipeline.settled_sync_end", lambda now=None: 11 * DAY)
    store = make_store_with(A1, A2)
    client, _ = make_client([FakeResponse(500), FakeResponse(404)])
    report = refresh_flights(store, client, begin=10 * DAY, pause_between_requests=0)
    assert "N1AA" in report.errors
    assert report.stopped_reason is None
    assert store.get_sync_state("bbb222") == 11 * DAY


def test_refresh_never_marks_unsettled_days_as_synced(monkeypatch):
    monkeypatch.setattr("evtol_fleet.pipeline.settled_sync_end", lambda now=None: 11 * DAY)
    store = make_store_with(A1)
    client, session = make_client([FakeResponse(404)])
    report = refresh_flights(store, client, begin=10 * DAY, end=50 * DAY, pause_between_requests=0)
    assert report.synced_through == 11 * DAY
    assert store.get_sync_state("aaa111") == 11 * DAY
    assert len(session.calls) == 1
