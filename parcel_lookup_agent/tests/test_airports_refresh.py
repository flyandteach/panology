from unittest.mock import MagicMock, patch

from parcel_agent import airports_refresh


def _mock_response(json_data):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


SERVICE_META = {
    "layers": [
        {
            "id": 0,
            "name": "Airports",
            "fields": [
                {"name": "IDENT"}, {"name": "NAME"}, {"name": "FACILITY_USE"},
                {"name": "LATITUDE"}, {"name": "LONGITUDE"}, {"name": "CITY"}, {"name": "STATE"},
            ],
        }
    ]
}

AIRPORT_FEATURES = {
    "features": [
        {
            "type": "Feature",
            "geometry": None,
            "properties": {
                "IDENT": "KSEA", "NAME": "Sea-Tac", "FACILITY_USE": "PU",
                "LATITUDE": 47.4489, "LONGITUDE": -122.3094, "CITY": "Seattle", "STATE": "WA",
            },
        }
    ]
}


def test_refresh_writes_snapshot(tmp_path):
    # `airports_refresh.requests` and `arcgis_client.requests` are the same
    # module object, so this must be a single dispatching patch rather than
    # two separate ones (the second would just clobber the first).
    def fake_get(url, params=None, timeout=None):
        if params and "where" in params:
            return _mock_response(AIRPORT_FEATURES)
        return _mock_response(SERVICE_META)

    output_path = str(tmp_path / "snapshot.json")
    with patch.object(airports_refresh.requests, "get", side_effect=fake_get):
        snapshot = airports_refresh.refresh(service_url="https://example.com/Airports/FeatureServer",
                                             output_path=output_path)

    assert snapshot["public_use_filtered"] is True
    assert len(snapshot["airports"]) == 1
    assert snapshot["airports"][0]["ident"] == "KSEA"

    import json
    with open(output_path) as f:
        on_disk = json.load(f)
    assert on_disk["airports"][0]["name"] == "Sea-Tac"


def test_refresh_raises_when_no_service_found():
    with patch.object(airports_refresh, "find_faa_airport_service_candidates", return_value=[]):
        try:
            airports_refresh.refresh()
            assert False, "expected SystemExit"
        except SystemExit:
            pass
