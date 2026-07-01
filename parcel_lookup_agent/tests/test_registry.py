import json
import os

from parcel_agent import registry


def test_lookup_by_fips_returns_none_when_missing(tmp_path, monkeypatch):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"_readme": "ignored"}))
    monkeypatch.setenv("PARCEL_REGISTRY_PATH", str(path))
    registry._load.cache_clear()
    assert registry.lookup_by_fips("99999") is None


def test_lookup_by_fips_returns_entry(tmp_path, monkeypatch):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"53033": {"name": "King County, WA", "service_url": "https://x/FeatureServer"}}))
    monkeypatch.setenv("PARCEL_REGISTRY_PATH", str(path))
    registry._load.cache_clear()
    entry = registry.lookup_by_fips("53033")
    assert entry["name"] == "King County, WA"


def test_lookup_by_fips_none_when_no_fips():
    assert registry.lookup_by_fips(None) is None
