"""Refresh the bundled public-use airport snapshot from FAA's own data.

Run this from an environment with general internet access -- it queries a
live ArcGIS service, so it will NOT work from a network-restricted sandbox.
Usage:

    python -m parcel_agent.airports_refresh
    python -m parcel_agent.airports_refresh --service-url https://.../Airports/FeatureServer

It searches ArcGIS Online for FAA's published Airports feature service
(rather than hardcoding an item URL, since those can change), verifies it
live, discovers -- by field-name pattern matching against the service's
actual schema -- which field distinguishes public-use vs. private-use
facilities, and writes only public-use records to
`data/airports_public_use_snapshot.json`.

If discovery doesn't find a usable service, pass --service-url once you've
found the right one (e.g. via https://gis-faa.opendata.arcgis.com).
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone

import requests

from . import arcgis_client, discovery

DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "data", "airports_public_use_snapshot.json")

_USE_FIELD_PATTERNS = [r"facility.?use", r"^use$", r"use.?code", r"site.?use"]
_IDENT_FIELD_PATTERNS = [r"^ident$", r"faa.?id", r"^lid$", r"site.?no", r"^icao"]
_NAME_FIELD_PATTERNS = [r"^name$", r"facility.?name", r"apt.?name"]
_CITY_FIELD_PATTERNS = [r"^city$", r"municipality"]
_STATE_FIELD_PATTERNS = [r"^state$", r"^st$", r"state.?code"]
_LAT_FIELD_PATTERNS = [r"^lat", r"latitude"]
_LON_FIELD_PATTERNS = [r"^lon", r"longitude"]


def _find_field(names: list[str], patterns: list[str]) -> str | None:
    for pattern in patterns:
        for name in names:
            if re.search(pattern, name, re.IGNORECASE):
                return name
    return None


def find_faa_airport_service_candidates(timeout: int = 30) -> list[str]:
    queries = ['title:"Airports" AND owner:FAA', "FAA public use airports ownership facility"]
    seen: set[str] = set()
    urls: list[str] = []
    for query in queries:
        try:
            results = discovery.search_arcgis_online(query, num=10, timeout=timeout)
        except requests.RequestException:
            continue
        for item in results:
            if item.get("type") != "Feature Service":
                continue
            url = item.get("url")
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def query_all_features(service_url: str, layer_id, where: str, timeout: int = 30,
                        page_size: int = 1000) -> list[dict]:
    features: list[dict] = []
    offset = 0
    while True:
        url = f"{arcgis_client.layer_url(service_url, layer_id)}/query"
        params = {
            "where": where, "outFields": "*", "returnGeometry": "false",
            "resultOffset": offset, "resultRecordCount": page_size, "f": "geojson",
        }
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise arcgis_client.ArcGISError(str(data["error"]))
        batch = data.get("features", [])
        features.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return features


def _try_layer(service_url: str, layer: dict, timeout: int) -> dict | None:
    fields = [f.get("name", "") for f in layer.get("fields", []) or []]
    ident_field = _find_field(fields, _IDENT_FIELD_PATTERNS)
    name_field = _find_field(fields, _NAME_FIELD_PATTERNS)
    if not (ident_field and name_field):
        return None

    use_field = _find_field(fields, _USE_FIELD_PATTERNS)
    lat_field = _find_field(fields, _LAT_FIELD_PATTERNS)
    lon_field = _find_field(fields, _LON_FIELD_PATTERNS)
    city_field = _find_field(fields, _CITY_FIELD_PATTERNS)
    state_field = _find_field(fields, _STATE_FIELD_PATTERNS)
    layer_id = layer.get("id", 0)
    where = f"UPPER({use_field}) = 'PU'" if use_field else "1=1"

    print(f"  querying layer {layer_id} where {where} ...")
    try:
        raw_features = query_all_features(service_url, layer_id, where, timeout=timeout)
    except (requests.RequestException, arcgis_client.ArcGISError, ValueError) as exc:
        print(f"  query failed: {exc}")
        return None
    if not raw_features:
        return None

    airports = []
    for feat in raw_features:
        props = feat.get("properties", {}) or {}
        geom = feat.get("geometry") or {}
        lat = props.get(lat_field) if lat_field else None
        lon = props.get(lon_field) if lon_field else None
        if lat is None or lon is None:
            coords = geom.get("coordinates")
            if coords and len(coords) == 2:
                lon, lat = coords
        if lat is None or lon is None:
            continue
        airports.append({
            "ident": props.get(ident_field),
            "name": props.get(name_field),
            "lat": float(lat),
            "lon": float(lon),
            "city": props.get(city_field) if city_field else None,
            "state": props.get(state_field) if state_field else None,
        })

    if not airports:
        return None

    return {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "source": f"{service_url} (layer {layer_id})",
        "public_use_filtered": use_field is not None,
        "airports": airports,
    }


def refresh(service_url: str | None = None, output_path: str = DEFAULT_OUTPUT, timeout: int = 30) -> dict:
    urls_to_try = [service_url] if service_url else find_faa_airport_service_candidates(timeout=timeout)
    tried = []

    for url in urls_to_try:
        tried.append(url)
        print(f"Trying {url} ...")
        try:
            meta = arcgis_client.describe_service(url, timeout=timeout)
        except (requests.RequestException, arcgis_client.ArcGISError, ValueError) as exc:
            print(f"  unreachable: {exc}")
            continue

        layer_list = meta.get("layers") or ([meta] if "fields" in meta else [])
        for layer in layer_list:
            snapshot = _try_layer(url, layer, timeout)
            if snapshot:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, indent=2)
                print(f"Wrote {len(snapshot['airports'])} airports to {output_path} "
                      f"(public_use_filtered={snapshot['public_use_filtered']})")
                return snapshot

    raise SystemExit(
        f"Could not find/query a usable FAA airports service. Tried: {tried}\n"
        "Pass --service-url explicitly if you know the correct ArcGIS FeatureServer URL "
        "(e.g. found via https://gis-faa.opendata.arcgis.com)."
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-url", default=None, help="Known FAA Airports FeatureServer URL, skips discovery")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)
    refresh(service_url=args.service_url, output_path=args.output, timeout=args.timeout)


if __name__ == "__main__":
    main()
