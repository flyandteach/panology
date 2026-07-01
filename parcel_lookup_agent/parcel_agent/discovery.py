"""Dynamic discovery of a county/city's parcel FeatureServer.

Instead of relying only on a hand-maintained list of GIS endpoints (which
inevitably goes stale and can't cover every jurisdiction), this queries
Esri's public ArcGIS Online item-search API, which indexes the feature
services published by the huge majority of US county and city GIS
departments -- whether they're self-hosted and federated through ArcGIS
Hub, or hosted directly on ArcGIS Online.

This is the piece that generalizes: it doesn't need a jurisdiction to be
pre-registered anywhere. It ranks candidate services by title relevance
and, when we already have coordinates, by proximity (bbox filter), then
lets the caller (agent.py) verify each candidate by actually querying it.
"""

from __future__ import annotations

import requests

ARCGIS_SEARCH_URL = "https://www.arcgis.com/sharing/rest/search"
DEFAULT_TIMEOUT = 20

_PARCEL_KEYWORDS = ("parcel", "assessor", "cadastr", "tax lot", "taxlot", "property")


def search_arcgis_online(query: str, bbox: tuple[float, float, float, float] | None = None,
                          num: int = 10, timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    params = {
        "q": query,
        "f": "json",
        "num": num,
        "sortField": "relevance",
    }
    if bbox:
        params["bbox"] = ",".join(str(round(v, 6)) for v in bbox)
    resp = requests.get(ARCGIS_SEARCH_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", []) or []


def _candidate_queries(county_name: str | None, state_abbr: str | None, city: str | None) -> list[str]:
    queries = []
    if county_name:
        name = county_name if any(w in county_name.lower() for w in ("county", "parish", "borough")) \
            else f"{county_name} County"
        suffix = f" {state_abbr}" if state_abbr else ""
        queries.append(f"parcels {name}{suffix}")
        queries.append(f"assessor parcels {name}{suffix}")
    if city:
        suffix = f" {state_abbr}" if state_abbr else ""
        queries.append(f"parcels {city}{suffix}")
    return queries


def _looks_like_parcels(title: str) -> bool:
    lowered = title.lower()
    return any(kw in lowered for kw in _PARCEL_KEYWORDS)


def _relevance_rank(title: str, county_name: str | None) -> int:
    lowered = title.lower()
    score = 0
    if "parcel" in lowered:
        score += 2
    if county_name and county_name.lower().replace(" county", "") in lowered:
        score += 2
    if "assessor" in lowered or "tax" in lowered:
        score += 1
    return score


def find_parcel_service_candidates(county_name: str | None, state_abbr: str | None,
                                    lat: float | None = None, lon: float | None = None,
                                    city: str | None = None, num: int = 10,
                                    timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    """Return a ranked, de-duplicated list of candidate Feature Service dicts.

    Each candidate: {"title", "url", "owner", "id", "score"}.
    """
    bbox = None
    if lat is not None and lon is not None:
        pad = 0.35  # degrees; wide enough to keep the whole county in view
        bbox = (lon - pad, lat - pad, lon + pad, lat + pad)

    seen_urls: set[str] = set()
    candidates: list[dict] = []

    for query in _candidate_queries(county_name, state_abbr, city):
        try:
            results = search_arcgis_online(query, bbox=bbox, num=num, timeout=timeout)
        except requests.RequestException:
            continue
        for item in results:
            if item.get("type") != "Feature Service":
                continue
            url = item.get("url")
            title = item.get("title") or ""
            if not url or url in seen_urls:
                continue
            if not _looks_like_parcels(title):
                continue
            seen_urls.add(url)
            candidates.append({
                "title": title,
                "url": url,
                "owner": item.get("owner"),
                "id": item.get("id"),
                "score": _relevance_rank(title, county_name),
            })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates
