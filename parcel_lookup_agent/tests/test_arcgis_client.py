from unittest.mock import MagicMock, patch

from parcel_agent import arcgis_client


def _mock_response(json_data):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


SERVICE_META = {
    "layers": [
        {"id": 0, "name": "Parcels", "geometryType": "esriGeometryPolygon"},
        {"id": 1, "name": "Zoning Points", "geometryType": "esriGeometryPoint"},
    ]
}


def test_list_polygon_layers_filters_to_polygons():
    with patch.object(arcgis_client.requests, "get", return_value=_mock_response(SERVICE_META)):
        layers = arcgis_client.list_polygon_layers("https://example.com/FeatureServer")
    assert len(layers) == 1
    assert layers[0]["name"] == "Parcels"


GEOJSON_FEATURE = {
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]},
            "properties": {
                "APN": "123-456-789",
                "OWNER_NAME": "Jane Doe",
                "SITUS_ADDRESS": "400 Broad St",
                "GIS_ACRES": 0.25,
            },
        }
    ]
}


def test_query_point_returns_features():
    with patch.object(arcgis_client.requests, "get", return_value=_mock_response(GEOJSON_FEATURE)):
        features = arcgis_client.query_point("https://example.com/FeatureServer", 0, -122.35, 47.62)
    assert len(features) == 1
    assert features[0]["properties"]["APN"] == "123-456-789"


def test_normalize_attributes_matches_common_field_names():
    props = GEOJSON_FEATURE["features"][0]["properties"]
    normalized = arcgis_client.normalize_attributes(props)
    assert normalized["apn"] == "123-456-789"
    assert normalized["owner_name"] == "Jane Doe"
    assert normalized["situs_address"] == "400 Broad St"
    assert normalized["area_acres"] == 0.25
    assert normalized["matched_field_count"] == 3


def test_normalize_attributes_handles_unknown_schema():
    normalized = arcgis_client.normalize_attributes({"OBJECTID": 1, "SHAPE_Length": 100})
    assert normalized["apn"] is None
    assert normalized["matched_field_count"] == 0


CATALOG_ROOT = {
    "folders": ["Property", "Zoning"],
    "services": [{"name": "Basemap", "type": "MapServer"}],
}

CATALOG_PROPERTY_FOLDER = {
    "folders": [],
    "services": [{"name": "Property/Parcels", "type": "FeatureServer"}],
}


def test_find_parcel_services_in_catalog_descends_into_promising_folders():
    def fake_get(url, params=None, timeout=None):
        if url.endswith("/Property"):
            return _mock_response(CATALOG_PROPERTY_FOLDER)
        return _mock_response(CATALOG_ROOT)

    with patch.object(arcgis_client.requests, "get", side_effect=fake_get):
        found = arcgis_client.find_parcel_services_in_catalog("https://gis.example.gov/arcgis/rest/services")

    assert found == ["https://gis.example.gov/arcgis/rest/services/Property/Parcels/FeatureServer"]
