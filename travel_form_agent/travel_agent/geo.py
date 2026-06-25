"""Driving distance and route map using free OpenStreetMap APIs (no API key required).

Geocoding: Nominatim (nominatim.openstreetmap.org)
Routing:   OSRM public instance (router.project-osrm.org)
Map tiles: OpenStreetMap via staticmap
"""

from __future__ import annotations

import io
import struct
import zlib
from typing import List, Optional, Tuple

import requests

_HEADERS = {"User-Agent": "WSDOT-TravelFormAgent/1.0 (flyandteach@gmail.com)"}
_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

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


def geocode_details(place: str) -> Optional[dict]:
    """
    Return a dict with lat, lon, city, county, state_code for a place name.
    Uses Nominatim reverse-address lookup.
    """
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{place}, USA", "format": "json", "limit": 1,
                    "countrycodes": "us", "addressdetails": 1},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if data:
            addr = data[0].get("address", {})
            state_code = addr.get("ISO3166-2-lvl4", "").replace("US-", "")
            return {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"]),
                "city": addr.get("city") or addr.get("town") or addr.get("village") or place,
                "county": addr.get("county", "").replace(" County", "").strip(),
                "state_code": state_code,
                "state_name": addr.get("state", ""),
            }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# GSA federal per diem lookup (out-of-state travel)
# ---------------------------------------------------------------------------

def gsa_per_diem(city: str, state_code: str, year: int = 2026) -> Optional[dict]:
    """
    Query the GSA per diem API and return {'mie': 68, 'lodging': 107, 'source': '...'}.
    Falls back to state standard rate if city not found.
    No API key required for personal/low-volume use.
    """
    # Normalize city: remove common suffixes, encode for URL
    city_clean = city.strip().title()
    state_up = state_code.upper()

    def _parse(data: dict) -> Optional[dict]:
        rates = data.get("rates", [])
        if not rates:
            return None
        # Prefer non-standard (city-specific) rates over the state standard
        best = None
        for entry in rates:
            for rate in entry.get("rate", []):
                months = rate.get("months", {}).get("month", [])
                if not months:
                    continue
                # Use the highest month value as the representative (or month 1)
                mie_vals = [m.get("value", 0) for m in months if m.get("value")]
                mie = max(mie_vals) if mie_vals else 0
                if mie and (best is None or mie > best["mie"]):
                    lodging_months = rate.get("months", {}).get("month", [])
                    # lodging is separate in some versions
                    best = {
                        "mie": int(mie),
                        "lodging": int(entry.get("rate", [{}])[0].get("value", 0) or 0),
                        "source": f"GSA FY{year} {city_clean}, {state_up}",
                    }
        return best

    # Try city-specific rate first
    try:
        url = f"https://api.gsa.gov/travel/perdiem/v2/rates/city/{city_clean}/state/{state_up}/year/{year}"
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code == 200:
            result = _parse(resp.json())
            if result and result["mie"]:
                return result
    except Exception:
        pass

    # Fall back to state standard rate
    try:
        url = f"https://api.gsa.gov/travel/perdiem/v2/rates/state/{state_up}/year/{year}"
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            meals = data.get("meals")
            if meals:
                return {
                    "mie": int(meals),
                    "lodging": 0,
                    "source": f"GSA FY{year} {state_up} standard rate",
                }
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Polyline decoder (Google/OSRM encoded polyline format)
# ---------------------------------------------------------------------------

def _decode_polyline(encoded: str) -> List[Tuple[float, float]]:
    """Decode a Google-encoded polyline string into a list of (lat, lon) pairs."""
    coords: List[Tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0
    while index < len(encoded):
        for is_lng in (False, True):
            result = 0
            shift = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            value = ~(result >> 1) if (result & 1) else (result >> 1)
            if is_lng:
                lng += value
            else:
                lat += value
        coords.append((lat / 1e5, lng / 1e5))
    return coords


# ---------------------------------------------------------------------------
# Routing + distance
# ---------------------------------------------------------------------------

def _osrm_route(orig: Tuple[float, float], dest: Tuple[float, float]):
    """Call OSRM and return (distance_meters, encoded_polyline) or (None, None)."""
    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{orig[1]},{orig[0]};{dest[1]},{dest[0]}"
    )
    try:
        resp = requests.get(
            url,
            params={"overview": "full", "geometries": "polyline"},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if data.get("code") == "Ok":
            route = data["routes"][0]
            return route["distance"], route["geometry"]
    except Exception:
        pass
    return None, None


def driving_miles(origin: str, destination: str) -> Optional[float]:
    """Return one-way driving miles between two place names, or None on failure."""
    orig = geocode(origin)
    dest = geocode(destination)
    if orig is None or dest is None:
        return None
    meters, _ = _osrm_route(orig, dest)
    if meters is None:
        return None
    return round(meters / 1609.344, 1)


# ---------------------------------------------------------------------------
# Route map image
# ---------------------------------------------------------------------------

def route_map_png(origin: str, destination: str, width: int = 900, height: int = 500) -> Optional[bytes]:
    """
    Return a PNG image (bytes) showing the driving route between two places,
    rendered on OpenStreetMap tiles.  Returns None if routing fails.
    """
    try:
        from staticmap import StaticMap, Line, CircleMarker
    except ImportError:
        return _fallback_map_png(origin, destination)

    orig_coords = geocode(origin)
    dest_coords = geocode(destination)
    if orig_coords is None or dest_coords is None:
        return None

    meters, polyline_enc = _osrm_route(orig_coords, dest_coords)
    if polyline_enc is None:
        return None

    route_latlon = _decode_polyline(polyline_enc)
    # staticmap uses (lon, lat) tuples
    route_lonlat = [(lon, lat) for lat, lon in route_latlon]

    m = StaticMap(width, height, url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                  headers=_HEADERS)
    m.add_line(Line(route_lonlat, "#1a73e8", 4))
    m.add_marker(CircleMarker((orig_coords[1], orig_coords[0]), "#16a34a", 14))  # green = origin
    m.add_marker(CircleMarker((dest_coords[1], dest_coords[0]), "#dc2626", 14))  # red = destination

    img = m.render()

    # Annotate with origin, destination, and mileage
    miles = round(meters / 1609.344, 1)
    img = _annotate(img, origin, destination, miles)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _annotate(img, origin: str, destination: str, miles: float):
    """Add a mileage label banner to the bottom of the map image."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return img

    draw = ImageDraw.Draw(img)
    w, h = img.size
    banner_h = 36
    draw.rectangle([(0, h - banner_h), (w, h)], fill=(15, 23, 42, 220))

    label = (
        f"  {origin.title()}  →  {destination.title()}  |  "
        f"One-way: {miles:.1f} mi   Round-trip: {miles * 2:.1f} mi   "
        f"@ $0.725/mi = ${miles * 2 * 0.725:.2f}"
    )
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except Exception:
        font = ImageFont.load_default()

    draw.text((8, h - banner_h + 8), label, fill=(255, 255, 255), font=font)
    return img


def _fallback_map_png(origin: str, destination: str) -> Optional[bytes]:
    """Return None – staticmap not installed; caller shows install instructions."""
    return None


def route_map_pdf(origin: str, destination: str, width: int = 900, height: int = 500) -> Optional[bytes]:
    """Return a PDF (bytes) of the route map, suitable for attaching to a travel request."""
    png = route_map_png(origin, destination, width, height)
    if png is None:
        return None
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(png)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PDF", resolution=150)
        return buf.getvalue()
    except Exception:
        return None
