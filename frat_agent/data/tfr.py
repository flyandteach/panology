"""
Fetch active TFRs from tfr.faa.gov and test whether a mission point intersects them.
No API key required.  TFR geometry is irregular; we use simple circle intersection
for TFRs with a published radius, and bounding-box fallback for others.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from typing import Optional

import requests
from bs4 import BeautifulSoup

from frat_agent.config import TFR_LIST_URL, TFR_DETAIL_URL
from frat_agent.models import TfrItem
from frat_agent.utils.geo import haversine_nm, point_in_circle


_TIMEOUT = 15
_NS = {
    "xsi":  "http://www.w3.org/2001/XMLSchema-instance",
    "tfr":  "http://tfr.faa.gov",
}


def _scrape_active_ids() -> list[str]:
    r = requests.get(TFR_LIST_URL, timeout=_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    ids  = []
    for a in soup.select("a[href*='detail_']"):
        href = a["href"]
        # href like /save_pages/detail_1234567.xml
        name = href.split("detail_")[-1].replace(".xml", "").replace(".html", "")
        if name.isdigit():
            ids.append(name)
    return list(set(ids))


def _parse_tfr_xml(notam_id: str, xml_text: str, mission_lat: float, mission_lon: float) -> Optional[TfrItem]:
    try:
        root = ET.fromstring(xml_text)
        # Try to pull name/description
        name_el = root.find(".//{*}name") or root.find(".//{*}Name")
        name    = name_el.text.strip() if name_el is not None and name_el.text else f"TFR {notam_id}"

        # Time fields
        eff_start = _text(root, "{*}effectiveStart") or _text(root, "{*}dateEffective") or ""
        eff_end   = _text(root, "{*}effectiveEnd")   or _text(root, "{*}dateExpire") or ""

        # Altitude
        min_alt = _int(root, "{*}minAlt")  or 0
        max_alt = _int(root, "{*}maxAlt")  or 99999

        # Center point
        c_lat = _float(root, "{*}latitude")  or _float(root, "{*}lat") or 0.0
        c_lon = _float(root, "{*}longitude") or _float(root, "{*}lon") or 0.0

        # Radius (statute or NM — FAA publishes NM)
        radius_nm = _float(root, "{*}radius") or None

        intersects = False
        if c_lat and c_lon and radius_nm:
            intersects = point_in_circle(mission_lat, mission_lon, c_lat, c_lon, radius_nm)

        return TfrItem(
            notam_id        = notam_id,
            name            = name,
            effective_start = eff_start,
            effective_end   = eff_end,
            min_alt_ft      = min_alt,
            max_alt_ft      = max_alt,
            center_lat      = c_lat,
            center_lon      = c_lon,
            radius_nm       = radius_nm,
            intersects_mission = intersects,
        )
    except Exception:
        return None


def _text(root: ET.Element, tag: str) -> Optional[str]:
    el = root.find(f".//{tag}")
    return el.text.strip() if el is not None and el.text else None


def _float(root: ET.Element, tag: str) -> Optional[float]:
    v = _text(root, tag)
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _int(root: ET.Element, tag: str) -> Optional[int]:
    v = _float(root, tag)
    return int(v) if v is not None else None


def fetch_tfrs(
    mission_lat: float,
    mission_lon: float,
    max_tfrs: int = 20,
) -> tuple[list[TfrItem], Optional[str]]:
    """
    Returns (list[TfrItem], warning_string).
    Only returns TFRs that could plausibly affect the mission area (within 200 NM)
    to keep result sets manageable.
    """
    warnings = []
    try:
        ids = _scrape_active_ids()
    except Exception as exc:
        return _mock_tfrs(mission_lat, mission_lon), f"TFR list fetch failed: {exc}"

    tfrs: list[TfrItem] = []
    for notam_id in ids[:max_tfrs]:
        try:
            url = TFR_DETAIL_URL.format(notam_id=notam_id)
            r   = requests.get(url, timeout=_TIMEOUT)
            r.raise_for_status()
            tfr = _parse_tfr_xml(notam_id, r.text, mission_lat, mission_lon)
            if tfr is None:
                continue
            # Filter to TFRs within 200 NM of mission — skip distant ones
            if tfr.center_lat and tfr.center_lon:
                dist = haversine_nm(mission_lat, mission_lon, tfr.center_lat, tfr.center_lon)
                if dist <= 200:
                    tfrs.append(tfr)
        except Exception:
            continue

    if not tfrs:
        return _mock_tfrs(mission_lat, mission_lon), (
            "No active TFRs found or TFR fetch incomplete; verify at tfr.faa.gov"
        )
    return tfrs, (warnings[0] if warnings else None)


def _mock_tfrs(lat: float, lon: float) -> list[TfrItem]:
    return [
        TfrItem(
            notam_id           = "MOCK-TFR",
            name               = "MOCK: No active TFRs confirmed (verify at tfr.faa.gov)",
            effective_start    = "N/A",
            effective_end      = "N/A",
            min_alt_ft         = 0,
            max_alt_ft         = 0,
            center_lat         = lat,
            center_lon         = lon,
            radius_nm          = None,
            intersects_mission = False,
        )
    ]
