from unittest.mock import MagicMock, patch

from parcel_agent import discovery


def _mock_response(json_data):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


SEARCH_RESULTS = {
    "results": [
        {"type": "Feature Service", "title": "King County Parcels", "url": "https://services.arcgis.com/x/Parcels/FeatureServer", "owner": "kingcounty", "id": "abc"},
        {"type": "Feature Service", "title": "King County Zoning", "url": "https://services.arcgis.com/x/Zoning/FeatureServer", "owner": "kingcounty", "id": "def"},
        {"type": "Map Service", "title": "King County Parcels (map only)", "url": "https://services.arcgis.com/x/Parcels/MapServer", "owner": "kingcounty", "id": "ghi"},
    ]
}


def test_find_parcel_service_candidates_filters_and_ranks():
    with patch.object(discovery.requests, "get", return_value=_mock_response(SEARCH_RESULTS)):
        candidates = discovery.find_parcel_service_candidates(
            county_name="King", state_abbr="WA", lat=47.62, lon=-122.35,
        )
    urls = [c["url"] for c in candidates]
    assert "https://services.arcgis.com/x/Parcels/FeatureServer" in urls
    assert "https://services.arcgis.com/x/Zoning/FeatureServer" not in urls
    assert "https://services.arcgis.com/x/Parcels/MapServer" not in urls  # not a Feature Service


def test_find_parcel_service_candidates_dedupes_across_queries():
    with patch.object(discovery.requests, "get", return_value=_mock_response(SEARCH_RESULTS)) as mock_get:
        candidates = discovery.find_parcel_service_candidates(county_name="King County", state_abbr="WA")
    urls = [c["url"] for c in candidates]
    assert len(urls) == len(set(urls))
    assert mock_get.call_count >= 1
