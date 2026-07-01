"""Small curated fallback registry of known county parcel GIS endpoints.

This is only consulted after dynamic ArcGIS Online discovery
(`discovery.py`) comes up empty. It exists for jurisdictions that don't
publish through ArcGIS Online (or aren't indexed there yet). See
`data/county_gis_registry.json` for the format and how to add entries.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "county_gis_registry.json")


@lru_cache(maxsize=1)
def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_registry() -> dict:
    path = os.environ.get("PARCEL_REGISTRY_PATH", _DEFAULT_PATH)
    return _load(path)


def lookup_by_fips(county_fips: str | None) -> dict | None:
    if not county_fips:
        return None
    return load_registry().get(county_fips)
