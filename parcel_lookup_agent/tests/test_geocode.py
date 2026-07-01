from unittest.mock import MagicMock, patch

from parcel_agent import geocode as geocode_mod


def _mock_response(json_data, status_ok=True):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if not status_ok:
        resp.raise_for_status.side_effect = Exception("HTTP error")
    return resp


CENSUS_MATCH = {
    "result": {
        "addressMatches": [
            {
                "matchedAddress": "400 BROAD ST, SEATTLE, WA, 98109",
                "coordinates": {"x": -122.3493, "y": 47.6205},
                "geographies": {
                    "Counties": [{"GEOID": "53033", "NAME": "King", "STATE": "53", "COUNTY": "033"}],
                    "States": [{"STUSAB": "WA"}],
                },
            }
        ]
    }
}

CENSUS_NO_MATCH = {"result": {"addressMatches": []}}


def test_geocode_census_oneline_success():
    with patch.object(geocode_mod.requests, "get", return_value=_mock_response(CENSUS_MATCH)):
        result = geocode_mod.geocode_census_oneline("400 Broad St, Seattle, WA")
    assert result.found
    assert result.lat == 47.6205
    assert result.lon == -122.3493
    assert result.county_fips == "53033"
    assert result.county_name == "King"
    assert result.state_abbr == "WA"


def test_geocode_prefers_census_when_it_matches():
    with patch.object(geocode_mod.requests, "get", return_value=_mock_response(CENSUS_MATCH)) as mock_get:
        result = geocode_mod.geocode("400 Broad St, Seattle, WA")
    assert result.found
    assert result.source == "census_oneline"
    assert mock_get.call_count == 1


NOMINATIM_MATCH = [{"display_name": "400 Broad St, Seattle, WA", "lat": "47.6205", "lon": "-122.3493"}]

CENSUS_COORDS_MATCH = {
    "result": {
        "geographies": {
            "Counties": [{"GEOID": "53033", "NAME": "King", "STATE": "53", "COUNTY": "033"}],
            "States": [{"STUSAB": "WA"}],
        }
    }
}


def test_geocode_falls_back_to_nominatim_then_census_coordinates():
    responses = [
        _mock_response(CENSUS_NO_MATCH),  # census oneline, original address
        _mock_response(NOMINATIM_MATCH),  # nominatim
        _mock_response(CENSUS_COORDS_MATCH),  # census coordinates lookup
    ]

    def fake_get(url, params=None, headers=None, timeout=None):
        return responses.pop(0)

    with patch.object(geocode_mod.requests, "get", side_effect=fake_get):
        result = geocode_mod.geocode("123 Rural Route, Nowhere, WA")

    assert result.found
    assert result.source == "nominatim+census_coordinates"
    assert result.county_fips == "53033"
    assert result.lat == 47.6205


def test_geocode_returns_not_found_when_everything_fails():
    with patch.object(geocode_mod.requests, "get", return_value=_mock_response(CENSUS_NO_MATCH)):
        # Nominatim also returns empty via the same mock (empty list truthy check)
        with patch.object(geocode_mod, "geocode_nominatim",
                           return_value=geocode_mod.GeocodeResult(found=False, input_address="x", source="nominatim")):
            result = geocode_mod.geocode("not a real address")
    assert not result.found
