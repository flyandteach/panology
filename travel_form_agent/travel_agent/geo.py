"""Driving distance lookup using free OpenStreetMap APIs (no API key required).

Geocoding: Nominatim (nominatim.openstreetmap.org)
Routing:   OSRM public instance (router.project-osrm.org)
"""

from __future__ import annotations

from typing import Optional, Tuple
import requests

_HEADERS = {"User-Agent": "WSDOT-TravelFormAgent/1.0 (flyandteach@gmail.com)"}
_TIMEOUT = 8


def geocode(place: str) -> Optional[Tuple[float, float]]:
    """Return (lat, lon) for a place name, biased to Washington State."""
    queries = [f"{place}, Washington, USA", f"{place}, USA"]
    for q in queries:
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "json", "limit": 1, "countrycodes": "us"},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            data = resp.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception:
            continue
    return None


def driving_miles(origin: str, destination: str) -> Optional[float]:
    """Return one-way driving miles between two place names, or None on failure."""
    orig = geocode(origin)
    dest = geocode(destination)
    if orig is None or dest is None:
        return None
    try:
        url = (
            f"http://router.project-osrm.org/route/v1/driving/"
            f"{orig[1]},{orig[0]};{dest[1]},{dest[0]}"
        )
        resp = requests.get(url, params={"overview": "false"}, headers=_HEADERS, timeout=_TIMEOUT)
        data = resp.json()
        if data.get("code") == "Ok":
            meters = data["routes"][0]["distance"]
            return round(meters / 1609.344, 1)
    except Exception:
        pass
    return None
