"""
Fetch NOTAMs from the FAA NOTAM Search API (notamapi.faa.gov).
Requires env vars: FAA_NOTAM_CLIENT_ID, FAA_NOTAM_CLIENT_SECRET
Falls back to empty list with a warning when credentials are absent.
"""
from __future__ import annotations
import os
from typing import Optional

import requests

from frat_agent.config import NOTAM_API_BASE, NOTAM_TOKEN_URL, NOTAM_RADIUS_NM
from frat_agent.models import NotamItem


_TIMEOUT = 15
_CLASSIFICATION_KEYWORDS = {
    "TFR":       ["temporary flight restriction", "tfr"],
    "AIRSPACE":  ["airspace", "class b", "class c", "class d", "moa", "restricted"],
    "OBSTACLE":  ["obstacle", "crane", "tower", "wind turbine"],
    "NAV":       ["vor", "ils", "gps", "rnav", "notam nav"],
}


def _classify(text: str) -> str:
    low = text.lower()
    for cls, kws in _CLASSIFICATION_KEYWORDS.items():
        if any(kw in low for kw in kws):
            return cls
    return "OTHER"


def _get_token(client_id: str, client_secret: str) -> str:
    r = requests.post(
        NOTAM_TOKEN_URL,
        data={
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _parse_notam(item: dict) -> NotamItem:
    props  = item.get("properties", item)
    text   = (
        props.get("coreNOTAMData", {}).get("notam", {}).get("fullText", "")
        or props.get("text", "")
    )
    notam_id = (
        props.get("coreNOTAMData", {}).get("notam", {}).get("id", "")
        or props.get("id", "UNKNOWN")
    )
    eff_start = props.get("effectiveStart", "")
    eff_end   = props.get("effectiveEnd", "")

    geometry  = item.get("geometry", {})
    coords    = geometry.get("coordinates", [])
    lat = lon = None
    if coords and geometry.get("type") == "Point":
        lon, lat = coords[0], coords[1]

    return NotamItem(
        notam_id        = notam_id,
        classification  = _classify(text),
        effective_start = eff_start,
        effective_end   = eff_end,
        text            = text[:500],
        lat             = lat,
        lon             = lon,
        radius_nm       = None,
    )


def fetch_notams(
    lat: float,
    lon: float,
    radius_nm: int = NOTAM_RADIUS_NM,
) -> tuple[list[NotamItem], Optional[str]]:
    """
    Returns (list[NotamItem], warning_string).
    """
    client_id     = os.getenv("FAA_NOTAM_CLIENT_ID", "")
    client_secret = os.getenv("FAA_NOTAM_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        return _mock_notams(), (
            "FAA_NOTAM_CLIENT_ID / FAA_NOTAM_CLIENT_SECRET not set; "
            "NOTAM data is mocked — obtain credentials at https://api.faa.gov"
        )

    try:
        token = _get_token(client_id, client_secret)
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "locationLongitude": lon,
            "locationLatitude":  lat,
            "locationRadius":    radius_nm,
            "pageSize":          50,
            "pageNum":           1,
            "sortBy":            "effectiveStart",
            "sortOrder":         "Asc",
        }
        r = requests.get(NOTAM_API_BASE, headers=headers, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        items = r.json().get("items", [])
        return [_parse_notam(i) for i in items], None

    except Exception as exc:
        return _mock_notams(), f"NOTAM API error: {exc}"


def _mock_notams() -> list[NotamItem]:
    return [
        NotamItem(
            notam_id        = "MOCK-0001",
            classification  = "NAV",
            effective_start = "2026-06-22T00:00:00Z",
            effective_end   = "2026-06-29T23:59:00Z",
            text            = "MOCK: GPS satellite maintenance may cause unreliable GPS signals within 30nm.",
            lat             = None,
            lon             = None,
            radius_nm       = 30.0,
        )
    ]
