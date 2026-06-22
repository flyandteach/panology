"""
Query the FAA UAS Facility Maps (UASFM) via the public ArcGIS REST API.
Returns the LAANC-authorized ceiling (ft AGL) for the grid cell containing
the mission launch point.  A ceiling of 0 means LAANC is NOT available in
that cell; the operator would need a standard Part 107 waiver / DrAW.
No API key required.
"""
from __future__ import annotations
from typing import Optional

import requests

from frat_agent.config import UASFM_QUERY_URL
from frat_agent.models import LaancData


_TIMEOUT = 15


def fetch_laanc(lat: float, lon: float) -> tuple[Optional[LaancData], Optional[str]]:
    """
    Returns (LaancData, warning_string).
    """
    params = {
        "geometry":      f"{lon},{lat}",
        "geometryType":  "esriGeometryPoint",
        "inSR":          "4326",
        "spatialRel":    "esriSpatialRelIntersects",
        "outFields":     "CEILING,FACILITY_NAME,AIRSPACE_CLASS,OBJECTID",
        "returnGeometry":"false",
        "f":             "json",
    }
    try:
        r = requests.get(UASFM_QUERY_URL, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        data     = r.json()
        features = data.get("features", [])

        if not features:
            return LaancData(
                grid_cell_id          = "NONE",
                authorized_ceiling_ft = 0,
                facility_name         = "Not in LAANC-enabled airspace",
                airspace_class        = "G",
            ), None

        attrs   = features[0].get("attributes", {})
        ceiling = attrs.get("CEILING", 0) or 0
        return LaancData(
            grid_cell_id          = str(attrs.get("OBJECTID", "?")),
            authorized_ceiling_ft = int(ceiling),
            facility_name         = attrs.get("FACILITY_NAME", "Unknown"),
            airspace_class        = attrs.get("AIRSPACE_CLASS", "?"),
        ), None

    except Exception as exc:
        return _mock_laanc(), f"UASFM/LAANC API error: {exc}"


def _mock_laanc() -> LaancData:
    return LaancData(
        grid_cell_id          = "MOCK",
        authorized_ceiling_ft = 400,
        facility_name         = "MOCK (verify at faa.gov/uas/programs_partnerships/data_exchange)",
        airspace_class        = "G",
    )
