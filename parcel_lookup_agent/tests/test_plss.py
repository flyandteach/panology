from unittest.mock import MagicMock, patch

from parcel_agent import plss


def _mock_response(json_data):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def test_parse_plss_basic():
    d = plss.parse_plss("SW 1/4 Section 12, T 33 N, R 21 E, WM")
    assert d.section == 12
    assert d.township_number == 33 and d.township_dir == "N"
    assert d.range_number == 21 and d.range_dir == "E"
    assert d.meridian == "WM"
    assert d.aliquot_parts == ["SW"]


def test_parse_plss_no_match_returns_none():
    assert plss.parse_plss("no legal description here") is None


SECTION_LAYER_META = {
    "layers": [
        {
            "id": 2,
            "name": "PLSSFirstDivision",
            "fields": [
                {"name": "PRINMER"}, {"name": "TWNSHPNO"}, {"name": "TWNSHPDIR"},
                {"name": "RANGENO"}, {"name": "RANGEDIR"}, {"name": "FRSTDIVNO"},
            ],
        }
    ]
}

SECTION_FEATURE = {
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[-122.36, 47.60], [-122.36, 47.6145],
                                                               [-122.3455, 47.6145], [-122.3455, 47.60],
                                                               [-122.36, 47.60]]]},
            "properties": {"FRSTDIVNO": "012"},
        }
    ]
}


def test_resolve_plss_success():
    desc = plss.parse_plss("SW 1/4 Section 12, T 33 N, R 21 E, WM")
    responses = [_mock_response(SECTION_LAYER_META), _mock_response(SECTION_FEATURE)]

    def fake_get(url, params=None, timeout=None):
        return responses.pop(0)

    with patch.object(plss.arcgis_client.requests, "get", side_effect=fake_get):
        result = plss.resolve_plss(desc)

    assert result.found
    assert result.lat is not None and result.lon is not None
    assert "aliquot_approx" in result.confidence


def test_resolve_plss_no_section_layer():
    desc = plss.parse_plss("Section 12, T 33 N, R 21 E, WM")
    with patch.object(plss.arcgis_client.requests, "get", return_value=_mock_response({"layers": []})):
        result = plss.resolve_plss(desc)
    assert not result.found
    assert "No Section" in result.error
