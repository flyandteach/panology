"""Generic client for querying Esri ArcGIS REST feature/map services.

County and city GIS departments overwhelmingly run their public parcel
layers on ArcGIS Server (either self-hosted, or as a hosted Feature
Service on ArcGIS Online). The REST contract is the same regardless of
who's hosting it, so one client works against any of them:

    <service_url>?f=json                         -> service + layer metadata
    <service_url>/<layer_id>/query?geometry=...   -> spatial query

Field names for the parcel attributes (APN, owner, situs address, ...)
are not standardized across jurisdictions, so this module also does
best-effort heuristic normalization based on common naming patterns.
"""

from __future__ import annotations

import re
from typing import Any

import requests

DEFAULT_TIMEOUT = 20


class ArcGISError(Exception):
    pass


def _get_json(url: str, params: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        raise ArcGISError(str(data["error"]))
    return data


def describe_service(service_url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Fetch service metadata for a FeatureServer/MapServer root URL."""
    return _get_json(service_url.rstrip("/"), {"f": "json"}, timeout=timeout)


def list_polygon_layers(service_url: str, timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    """Return layer metadata entries whose geometry type is polygon.

    If `service_url` already points at a specific layer (its metadata has
    a top-level "geometryType" rather than a "layers" list), return that
    single layer wrapped in a list when it's a polygon layer.
    """
    meta = describe_service(service_url, timeout=timeout)
    if "layers" in meta:
        return [
            {**layer, "_service_url": service_url}
            for layer in meta["layers"]
            if layer.get("geometryType") == "esriGeometryPolygon"
        ]
    if meta.get("geometryType") == "esriGeometryPolygon":
        return [{**meta, "_service_url": service_url, "id": meta.get("id", "")}]
    return []


_CATALOG_NAME_PATTERN = r"parcel|assessor|cadastr|tax.?lot|propert"


def list_catalog(root_url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Fetch an ArcGIS Server services-directory listing (folders + services)."""
    return _get_json(root_url.rstrip("/"), {"f": "json"}, timeout=timeout)


def find_parcel_services_in_catalog(root_url: str, max_folders: int = 8,
                                     timeout: int = DEFAULT_TIMEOUT) -> list[str]:
    """Best-effort crawl of an ArcGIS Server catalog for parcel-like services.

    Scans the root's service list, then descends one level into any
    folders whose name itself looks parcel/assessor-related (bounded, so
    this can't turn into an unbounded crawl of a large GIS server).
    Returns full service URLs (e.g. ".../Parcels/FeatureServer").
    """
    root_url = root_url.rstrip("/")
    found: list[str] = []

    def scan(base_url: str, catalog: dict) -> None:
        for svc in catalog.get("services", []) or []:
            name = svc.get("name", "")
            svc_type = svc.get("type", "")
            if svc_type in ("FeatureServer", "MapServer") and re.search(_CATALOG_NAME_PATTERN, name, re.IGNORECASE):
                found.append(f"{base_url}/{name.rsplit('/', 1)[-1]}/{svc_type}")

    try:
        root_catalog = list_catalog(root_url, timeout=timeout)
    except (requests.RequestException, ArcGISError, ValueError):
        return found

    scan(root_url, root_catalog)

    for folder in (root_catalog.get("folders") or [])[:max_folders]:
        if not re.search(_CATALOG_NAME_PATTERN, folder, re.IGNORECASE):
            continue
        try:
            sub_url = f"{root_url}/{folder}"
            sub_catalog = list_catalog(sub_url, timeout=timeout)
        except (requests.RequestException, ArcGISError, ValueError):
            continue
        scan(sub_url, sub_catalog)

    return found


def layer_url(service_url: str, layer_id: Any) -> str:
    base = service_url.rstrip("/")
    if re.search(r"/\d+$", base):
        return base
    return f"{base}/{layer_id}"


def query_where(service_url: str, layer_id: Any, where: str,
                 timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    """Attribute-only spatial query. Returns a list of GeoJSON features."""
    url = f"{layer_url(service_url, layer_id)}/query"
    params = {
        "where": where,
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "geojson",
    }
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        raise ArcGISError(str(data["error"]))
    return data.get("features", [])


def query_point(service_url: str, layer_id: Any, lon: float, lat: float,
                 timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    """Spatial point-in-polygon query. Returns a list of GeoJSON features."""
    url = f"{layer_url(service_url, layer_id)}/query"
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "geojson",
    }
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("error"):
        raise ArcGISError(str(data["error"]))
    return data.get("features", [])


# --- Field normalization -------------------------------------------------

_APN_PATTERNS = [r"^apn$", r"parcel.?id", r"parcel.?num", r"^pin$", r"tax.?id", r"^folio", r"parcelkey"]
_OWNER_PATTERNS = [r"owner.?name", r"^owner$", r"owner1", r"taxpayer"]
_SITUS_PATTERNS = [r"situs", r"site.?addr", r"prop.?addr", r"full.?addr", r"^address$"]
_LEGAL_PATTERNS = [r"legal.?desc"]
_ACRES_PATTERNS = [r"acre"]
_SQFT_PATTERNS = [r"sq.?ft", r"shape.*area", r"^area$"]


def _find_field(fields: dict[str, Any], patterns: list[str]) -> tuple[str | None, Any]:
    for pattern in patterns:
        for key in fields:
            if re.search(pattern, key, re.IGNORECASE):
                return key, fields[key]
    return None, None


def normalize_attributes(properties: dict[str, Any]) -> dict[str, Any]:
    """Best-effort mapping of a parcel feature's raw fields to a common shape."""
    apn_field, apn = _find_field(properties, _APN_PATTERNS)
    owner_field, owner = _find_field(properties, _OWNER_PATTERNS)
    situs_field, situs = _find_field(properties, _SITUS_PATTERNS)
    legal_field, legal = _find_field(properties, _LEGAL_PATTERNS)
    acres_field, acres = _find_field(properties, _ACRES_PATTERNS)
    sqft_field, sqft = _find_field(properties, _SQFT_PATTERNS)

    matched_fields = [f for f in (apn_field, owner_field, situs_field) if f]

    return {
        "apn": apn,
        "owner_name": owner,
        "situs_address": situs,
        "legal_description": legal,
        "area_acres": acres,
        "area_sqft": sqft,
        "matched_field_count": len(matched_fields),
    }
