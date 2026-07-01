"""Nearest-public-use-airport lookup.

Reads a bundled snapshot of US public-use airports
(`data/airports_public_use_snapshot.json`), produced by
`airports_refresh.py` from FAA's own published data (which carries an
explicit public-use vs. private-use flag).

Until that snapshot has been generated (it requires live internet access
to run -- see README), this falls back to the `airportsdata` PyPI package
for coordinates. That fallback is real, accurate, well-maintained data,
but it is **not** filtered to public-use facilities -- it includes every
landing area worldwide, private strips included. Every result carries a
flag saying which source produced it so callers/UI can show the caveat.
"""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache

from .models import AirportDistance

_SNAPSHOT_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "data", "airports_public_use_snapshot.json")
_EARTH_RADIUS_NM = 3440.065
_NM_TO_MI = 1.150779


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return _EARTH_RADIUS_NM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@lru_cache(maxsize=4)
def _load_snapshot(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("airports"):
        return None
    return data


@lru_cache(maxsize=1)
def _load_airportsdata_fallback() -> list[dict]:
    try:
        import airportsdata
    except ImportError:
        return []
    records = airportsdata.load("ICAO")
    airports = []
    for code, rec in records.items():
        if rec.get("country") != "US" or rec.get("lat") is None or rec.get("lon") is None:
            continue
        airports.append({
            "ident": code, "name": rec.get("name") or code,
            "lat": rec["lat"], "lon": rec["lon"],
            "city": rec.get("city"), "state": rec.get("subd"),
        })
    return airports


def load_airports(snapshot_path: str | None = None) -> tuple[list[dict], bool]:
    """Returns (airports, is_public_use_verified)."""
    path = snapshot_path or os.environ.get("PARCEL_AIRPORTS_SNAPSHOT_PATH", _SNAPSHOT_PATH_DEFAULT)
    snapshot = _load_snapshot(path)
    if snapshot:
        return snapshot["airports"], bool(snapshot.get("public_use_filtered"))
    return _load_airportsdata_fallback(), False


def nearest_airports(lat: float, lon: float, n: int = 5,
                      snapshot_path: str | None = None) -> tuple[list[AirportDistance], bool]:
    airports, verified = load_airports(snapshot_path)
    scored = []
    for airport in airports:
        try:
            a_lat, a_lon = float(airport["lat"]), float(airport["lon"])
        except (TypeError, KeyError, ValueError):
            continue
        dist_nm = _haversine_nm(lat, lon, a_lat, a_lon)
        scored.append(AirportDistance(
            ident=airport.get("ident") or "",
            name=airport.get("name") or "",
            lat=a_lat, lon=a_lon,
            distance_nm=round(dist_nm, 2),
            distance_mi=round(dist_nm * _NM_TO_MI, 2),
            city=airport.get("city"),
            state=airport.get("state"),
        ))
    scored.sort(key=lambda a: a.distance_nm)
    return scored[:n], verified
