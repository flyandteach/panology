"""Address geocoding with a free-public-data fallback chain.

Strategy:
1. US Census Bureau geocoder (`onelineaddress`) - free, no key, returns
   coordinates *and* county FIPS in a single call. Best case.
2. If the Census geocoder can't match the address (common for rural
   routes, new construction, or slightly malformed input), fall back to
   OpenStreetMap Nominatim to get coordinates.
3. Whenever we only have coordinates (from Nominatim, or a caller-supplied
   lat/lon), resolve the county FIPS via the Census `coordinates`
   geography endpoint. This decouples "find coordinates" from "find the
   county", which is the piece the parcel registry/discovery needs.
"""

from __future__ import annotations

import requests

from .models import GeocodeResult

CENSUS_ONELINE_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
CENSUS_COORDINATES_URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "panology-parcel-lookup-agent/1.0 (contact: set NOMINATIM_CONTACT env var)"

DEFAULT_TIMEOUT = 15


def _census_county_from_geographies(geographies: dict) -> tuple[str | None, str | None, str | None, str | None]:
    counties = geographies.get("Counties") or []
    states = geographies.get("States") or []
    county_fips = county_name = state_fips = state_abbr = None
    if counties:
        c = counties[0]
        state_part = str(c.get("STATE", "")).zfill(2)
        county_part = str(c.get("COUNTY", "")).zfill(3)
        county_fips = c.get("GEOID") or (state_part + county_part)
        county_name = c.get("NAME")
        state_fips = state_part
    if states:
        state_abbr = states[0].get("STUSAB")
    return county_fips, county_name, state_fips, state_abbr


def geocode_census_oneline(address: str, timeout: int = DEFAULT_TIMEOUT) -> GeocodeResult:
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "layers": "Counties,States",
        "format": "json",
    }
    resp = requests.get(CENSUS_ONELINE_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    matches = data.get("result", {}).get("addressMatches") or []
    if not matches:
        return GeocodeResult(found=False, input_address=address, source="census_oneline",
                              error="No address match from Census geocoder")

    match = matches[0]
    coords = match.get("coordinates", {})
    lon, lat = coords.get("x"), coords.get("y")
    county_fips, county_name, state_fips, state_abbr = _census_county_from_geographies(
        match.get("geographies", {})
    )
    return GeocodeResult(
        found=True,
        input_address=address,
        matched_address=match.get("matchedAddress"),
        lat=lat,
        lon=lon,
        county_fips=county_fips,
        county_name=county_name,
        state_fips=state_fips,
        state_abbr=state_abbr,
        source="census_oneline",
    )


def geocode_census_coordinates(lat: float, lon: float, timeout: int = DEFAULT_TIMEOUT) -> GeocodeResult:
    params = {
        "x": lon,
        "y": lat,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "layers": "Counties,States",
        "format": "json",
    }
    resp = requests.get(CENSUS_COORDINATES_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    geographies = data.get("result", {}).get("geographies") or {}
    county_fips, county_name, state_fips, state_abbr = _census_county_from_geographies(geographies)
    if not county_fips:
        return GeocodeResult(found=False, input_address="", lat=lat, lon=lon, source="census_coordinates",
                              error="Census could not resolve a county for these coordinates")
    return GeocodeResult(
        found=True,
        input_address="",
        matched_address=None,
        lat=lat,
        lon=lon,
        county_fips=county_fips,
        county_name=county_name,
        state_fips=state_fips,
        state_abbr=state_abbr,
        source="census_coordinates",
    )


def geocode_nominatim(address: str, timeout: int = DEFAULT_TIMEOUT) -> GeocodeResult:
    params = {"q": address, "format": "jsonv2", "addressdetails": 1, "limit": 1, "countrycodes": "us"}
    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return GeocodeResult(found=False, input_address=address, source="nominatim",
                              error="No address match from Nominatim")
    top = results[0]
    return GeocodeResult(
        found=True,
        input_address=address,
        matched_address=top.get("display_name"),
        lat=float(top["lat"]),
        lon=float(top["lon"]),
        source="nominatim",
    )


def _address_variants(address: str) -> list[str]:
    """Cheap, deterministic rewrites to retry a geocode with before giving up."""
    variants = [address]
    stripped = address.strip()
    if stripped != address:
        variants.append(stripped)
    # Drop a trailing unit/apt/suite designator, which the Census geocoder
    # sometimes chokes on even though the base address matches fine.
    import re

    no_unit = re.sub(r",?\s*(apt|unit|ste|suite|#)\.?\s*\S+\s*(,|$)", ", ", address, flags=re.IGNORECASE)
    no_unit = re.sub(r"\s{2,}", " ", no_unit).strip(", ").strip()
    if no_unit and no_unit not in variants:
        variants.append(no_unit)
    return variants


def geocode(address: str, timeout: int = DEFAULT_TIMEOUT) -> GeocodeResult:
    """Resolve an address to coordinates + county, trying multiple strategies.

    Returns the first successful GeocodeResult, or a found=False result
    describing the last failure if every strategy was exhausted.
    """
    last_result: GeocodeResult | None = None

    for variant in _address_variants(address):
        try:
            result = geocode_census_oneline(variant, timeout=timeout)
        except requests.RequestException as exc:
            result = GeocodeResult(found=False, input_address=variant, source="census_oneline", error=str(exc))
        last_result = result
        if result.found:
            return result

    # Census couldn't match any variant of the address text. Fall back to
    # Nominatim for coordinates, then resolve the county from those
    # coordinates via Census (which is much more lenient about exact
    # coordinates than it is about address text).
    try:
        nominatim_result = geocode_nominatim(address, timeout=timeout)
    except requests.RequestException as exc:
        nominatim_result = GeocodeResult(found=False, input_address=address, source="nominatim", error=str(exc))

    if not nominatim_result.found:
        return last_result or nominatim_result

    try:
        county_result = geocode_census_coordinates(nominatim_result.lat, nominatim_result.lon, timeout=timeout)
    except requests.RequestException as exc:
        county_result = GeocodeResult(found=False, input_address=address, source="census_coordinates", error=str(exc))

    return GeocodeResult(
        found=True,
        input_address=address,
        matched_address=nominatim_result.matched_address,
        lat=nominatim_result.lat,
        lon=nominatim_result.lon,
        county_fips=county_result.county_fips,
        county_name=county_result.county_name,
        state_fips=county_result.state_fips,
        state_abbr=county_result.state_abbr,
        source="nominatim+census_coordinates",
    )
