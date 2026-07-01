import json

from parcel_agent import airports


def test_nearest_airports_from_snapshot(tmp_path, monkeypatch):
    snapshot = {
        "refreshed_at": "2026-01-01T00:00:00Z",
        "source": "test",
        "public_use_filtered": True,
        "airports": [
            {"ident": "KSEA", "name": "Sea-Tac", "lat": 47.4489, "lon": -122.3094, "city": "Seattle", "state": "WA"},
            {"ident": "KPDX", "name": "Portland Intl", "lat": 45.5887, "lon": -122.5969, "city": "Portland", "state": "OR"},
        ],
    }
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(snapshot))
    airports._load_snapshot.cache_clear()

    results, verified = airports.nearest_airports(47.45, -122.30, n=5, snapshot_path=str(path))

    assert verified is True
    assert len(results) == 2
    assert results[0].ident == "KSEA"
    assert results[0].distance_nm < results[1].distance_nm


def test_nearest_airports_falls_back_when_snapshot_empty(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"airports": []}))
    airports._load_snapshot.cache_clear()

    airports_list, verified = airports.load_airports(snapshot_path=str(path))
    assert verified is False


def test_haversine_known_distance():
    # Seattle to Portland is roughly 129 nm / 148 statute miles as the crow flies.
    dist = airports._haversine_nm(47.6062, -122.3321, 45.5152, -122.6784)
    assert 120 < dist < 140
