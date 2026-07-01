from unittest.mock import patch

from parcel_agent import agent as agent_mod
from parcel_agent.models import GeocodeResult


def _geo_found():
    return GeocodeResult(
        found=True, input_address="400 Broad St, Seattle, WA", matched_address="400 BROAD ST, SEATTLE, WA",
        lat=47.6205, lon=-122.3493, county_fips="53033", county_name="King", state_fips="53",
        state_abbr="WA", source="census_oneline",
    )


def _geo_not_found():
    return GeocodeResult(found=False, input_address="garbage", source="census_oneline", error="no match")


FEATURE = {
    "type": "Feature",
    "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]},
    "properties": {"APN": "123-456", "OWNER_NAME": "Jane Doe", "SITUS_ADDRESS": "400 Broad St"},
}


def test_lookup_returns_not_found_when_geocode_fails():
    with patch.object(agent_mod, "geocode", return_value=_geo_not_found()):
        result = agent_mod.ParcelLookupAgent().lookup("garbage")
    assert not result.found
    assert "geocode" in result.error.lower() or "Could not geocode" in result.error


def test_lookup_succeeds_via_discovery():
    candidates = [{"title": "King County Parcels", "url": "https://x/FeatureServer", "owner": "kc", "id": "1", "score": 4}]
    with patch.object(agent_mod, "geocode", return_value=_geo_found()), \
         patch.object(agent_mod.discovery, "find_parcel_service_candidates", return_value=candidates), \
         patch.object(agent_mod.arcgis_client, "list_polygon_layers",
                       return_value=[{"id": 0, "name": "Parcels", "_service_url": "https://x/FeatureServer"}]), \
         patch.object(agent_mod.arcgis_client, "query_point", return_value=[FEATURE]):
        result = agent_mod.ParcelLookupAgent().lookup("400 Broad St, Seattle, WA")

    assert result.found
    assert result.apn == "123-456"
    assert result.owner_name == "Jane Doe"
    assert result.strategy_used == "arcgis_online_discovery"
    assert result.confidence == "high"
    assert result.county_name == "King"


def test_lookup_falls_back_to_registry_when_discovery_empty():
    registry_entry = {"name": "King County, WA", "service_url": "https://registry-x/FeatureServer", "layer_id": 0}
    with patch.object(agent_mod, "geocode", return_value=_geo_found()), \
         patch.object(agent_mod.discovery, "find_parcel_service_candidates", return_value=[]), \
         patch.object(agent_mod.registry, "lookup_by_fips", return_value=registry_entry), \
         patch.object(agent_mod.arcgis_client, "list_polygon_layers",
                       return_value=[{"id": 0, "name": "Parcels", "_service_url": "https://registry-x/FeatureServer"}]), \
         patch.object(agent_mod.arcgis_client, "query_point", return_value=[FEATURE]):
        result = agent_mod.ParcelLookupAgent().lookup("400 Broad St, Seattle, WA")

    assert result.found
    assert result.strategy_used == "curated_registry"


def test_lookup_reports_not_found_with_attempt_log_when_all_strategies_fail():
    with patch.object(agent_mod, "geocode", return_value=_geo_found()), \
         patch.object(agent_mod.discovery, "find_parcel_service_candidates", return_value=[]), \
         patch.object(agent_mod.registry, "lookup_by_fips", return_value=None), \
         patch.object(agent_mod, "_llm_suggest_catalog_roots", return_value=[]):
        result = agent_mod.ParcelLookupAgent().lookup("400 Broad St, Seattle, WA")

    assert not result.found
    assert len(result.attempts) >= 3
    assert any(a.strategy == "discovery" for a in result.attempts)
    assert any(a.strategy == "curated_registry" for a in result.attempts)
