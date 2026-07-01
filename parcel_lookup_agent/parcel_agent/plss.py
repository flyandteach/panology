"""Parse and resolve Public Land Survey System (PLSS) legal descriptions.

Handles descriptions of the form:

    SW 1/4 Section 12, T 33 N, R 21 E, WM
    NE1/4 SW1/4 Sec. 4, T2S, R3E, B.M.
    Section 9, Township 15 North, Range 30 East, Willamette Meridian

Resolution strategy: query the BLM's public PLSS Cadastral Survey ArcGIS
service (the standard federal source for Township/Range/Section geometry)
directly against its Section-level ("First Division") layer, matching on
meridian + township + range + section. Field names in that service are
discovered at runtime (regex-matched against the live schema, the same
approach used in arcgis_client.normalize_attributes) rather than hardcoded,
since this code can't be live-tested against the real service from an
environment without general internet access.

The national BLM layer only carries geometry down to the Section level, not
individual aliquot parts (quarter-sections, quarter-quarters). When a
description includes those (e.g. "SW 1/4"), this module approximates the
sub-parcel by geometrically subdividing the Section's bounding box -- a
reasonable approximation for "how far is this from the nearest airport"
purposes, but NOT a substitute for a surveyed legal boundary.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from . import arcgis_client
from .models import PLSSDescription, PLSSResult

BLM_PLSS_SERVICE_URL = "https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer"

# Best-effort abbreviation -> full name, used only as a fallback query value
# if the field's raw abbreviation doesn't match. Not exhaustive.
_MERIDIAN_NAMES = {
    "WM": "Willamette", "BM": "Boise", "MDM": "Mount Diablo", "HM": "Humboldt",
    "SBM": "San Bernardino", "GSRM": "Gila and Salt River", "NMPM": "New Mexico Principal",
    "SLM": "Salt Lake", "6PM": "Sixth Principal", "5PM": "Fifth Principal",
    "4PM": "Fourth Principal", "3PM": "Third Principal", "2PM": "Second Principal",
    "IM": "Indian", "CM": "Choctaw", "STM": "St Stephens", "CHM": "Chickasaw",
    "BHM": "Black Hills", "CIM": "Cimarron", "WRM": "Wind River", "UM": "Ute",
}

_AQ_TOKEN = r"(?:NE|NW|SE|SW|N|S|E|W)\s*1\s*/\s*2?4?"
_AQ_SEP = r"(?:\s*,?\s*(?:of\s+(?:the\s+)?)?)"
_ALIQUOT = rf"(?:{_AQ_TOKEN}{_AQ_SEP})+"

# Meridian: either a short code (WM, B.M., MDM, ...) or a full name followed
# by the literal word "Meridian" (e.g. "Willamette Meridian"). Matched as two
# alternatives rather than one generic pattern, since a generic "stop at the
# first M" pattern false-matches inside names like "Willamette".
_MERIDIAN_PATTERN = r"(?:[A-Za-z]{1,3}\.?M\.?\b|[A-Za-z][A-Za-z\s]{1,25}?\s+Merid(?:ian)?\.?)"

_PLSS_PATTERN = re.compile(
    r"(?P<aliquot>" + _ALIQUOT + r")?"
    r"Sec(?:tion|t)?\.?\s*(?P<section>\d{1,2})\s*,?\s*"
    r"T(?:ownship)?\.?\s*(?P<twp_num>\d{1,3})\s*(?P<twp_dir>N(?:orth)?|S(?:outh)?)\.?\s*,?\s*"
    r"R(?:ange)?\.?\s*(?P<rng_num>\d{1,3})\s*(?P<rng_dir>E(?:ast)?|W(?:est)?)\.?"
    rf"(?:\s*,?\s*(?P<meridian>{_MERIDIAN_PATTERN}))?",
    re.IGNORECASE,
)


def _parse_aliquot(raw: str | None) -> list[str]:
    if not raw:
        return []
    tokens = re.findall(r"(NE|NW|SE|SW|N|S|E|W)\s*1\s*/\s*2?4?", raw, re.IGNORECASE)
    return [t.upper() for t in tokens]


def _normalize_meridian(raw: str | None) -> str:
    if not raw:
        return ""
    compact = re.sub(r"[.\s]", "", raw).upper()
    compact = re.sub(r"MERIDIAN$", "M", compact)
    return compact


def parse_plss(text: str) -> PLSSDescription | None:
    """Find and parse the first PLSS legal description in free text."""
    match = _PLSS_PATTERN.search(text)
    if not match:
        return None
    return PLSSDescription(
        raw_text=match.group(0).strip(),
        aliquot_parts=_parse_aliquot(match.group("aliquot")),
        section=int(match.group("section")),
        township_number=int(match.group("twp_num")),
        township_dir=match.group("twp_dir")[0].upper(),
        range_number=int(match.group("rng_num")),
        range_dir=match.group("rng_dir")[0].upper(),
        meridian=_normalize_meridian(match.group("meridian")),
    )


# --- Geometric aliquot subdivision (approximation) ------------------------

def _bbox_of_geometry(geometry: dict) -> tuple[float, float, float, float]:
    coords = geometry.get("coordinates", [])

    def flatten(node):
        if isinstance(node, (int, float)):
            return
        if len(node) and isinstance(node[0], (int, float)):
            yield node
        else:
            for child in node:
                yield from flatten(child)

    points = list(flatten(coords))
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _subdivide(bbox: tuple[float, float, float, float], code: str) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bbox
    midx, midy = (minx + maxx) / 2, (miny + maxy) / 2
    return {
        "NE": (midx, midy, maxx, maxy),
        "NW": (minx, midy, midx, maxy),
        "SE": (midx, miny, maxx, midy),
        "SW": (minx, miny, midx, midy),
        "N": (minx, midy, maxx, maxy),
        "S": (minx, miny, maxx, midy),
        "E": (midx, miny, maxx, maxy),
        "W": (minx, miny, midx, maxy),
    }[code]


def resolve_aliquot_centroid(section_geometry: dict, aliquot_parts: list[str]) -> tuple[float, float]:
    """Approximate lat/lon centroid of an aliquot sub-parcel within a Section.

    `aliquot_parts` should be in the order they appear in the written
    description (finest subdivision first, e.g. ["SW", "NE"] for
    "SW 1/4 of the NE 1/4"). Subdivisions are applied from the outermost
    (last-written) inward, matching standard PLSS description grammar.
    """
    bbox = _bbox_of_geometry(section_geometry)
    for code in reversed(aliquot_parts):
        bbox = _subdivide(bbox, code)
    minx, miny, maxx, maxy = bbox
    return (miny + maxy) / 2, (minx + maxx) / 2  # (lat, lon)


# --- BLM service query -----------------------------------------------------

_SECTION_NAME_PATTERN = r"first.?division|section"
_FIELD_PATTERNS = {
    "meridian": [r"prinmer", r"^meridian$", r"merid"],
    "twp_num": [r"twnshpno", r"township.?no", r"town.?num"],
    "twp_dir": [r"twnshpdir", r"township.?dir", r"town.?dir"],
    "rng_num": [r"rangeno", r"range.?no", r"rng.?num"],
    "rng_dir": [r"rangedir", r"range.?dir", r"rng.?dir"],
    "section_no": [r"frstdivno", r"section.?no", r"sec.?num"],
}


def _find_field(field_names: list[str], patterns: list[str]) -> str | None:
    for pattern in patterns:
        for name in field_names:
            if re.search(pattern, name, re.IGNORECASE):
                return name
    return None


def _find_section_layer(service_url: str, timeout: int) -> dict | None:
    meta = arcgis_client.describe_service(service_url, timeout=timeout)
    for layer in meta.get("layers", []) or []:
        if re.search(_SECTION_NAME_PATTERN, layer.get("name", ""), re.IGNORECASE):
            return layer
    return None


def _quote(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def resolve_plss(desc: PLSSDescription, service_url: str = BLM_PLSS_SERVICE_URL,
                  timeout: int = 20) -> PLSSResult:
    try:
        layer = _find_section_layer(service_url, timeout)
    except (requests.RequestException, arcgis_client.ArcGISError, ValueError) as exc:
        return PLSSResult(found=False, description=desc, error=f"Could not reach BLM PLSS service: {exc}")

    if layer is None:
        return PLSSResult(found=False, description=desc, error="No Section/First-Division layer found in BLM service")

    field_names = [f.get("name", "") for f in layer.get("fields", []) or []]
    fmap = {key: _find_field(field_names, patterns) for key, patterns in _FIELD_PATTERNS.items()}
    if not fmap["twp_num"] or not fmap["rng_num"] or not fmap["section_no"]:
        return PLSSResult(found=False, description=desc,
                           error=f"Could not identify township/range/section fields in BLM schema {field_names}")

    layer_id = layer.get("id", 0)

    def query(where: str) -> list[dict]:
        return arcgis_client.query_where(service_url, layer_id, where, timeout=timeout)

    base_where = (
        f"{fmap['twp_num']}={desc.township_number} AND {fmap['section_no']}={desc.section} "
        f"AND {fmap['rng_num']}={desc.range_number}"
    )
    if fmap["twp_dir"]:
        base_where += f" AND {fmap['twp_dir']}={_quote(desc.township_dir)}"
    if fmap["rng_dir"]:
        base_where += f" AND {fmap['rng_dir']}={_quote(desc.range_dir)}"

    attempts_tried = []
    features: list[dict] = []
    confidence = "section"

    for meridian_value in filter(None, [desc.meridian, _MERIDIAN_NAMES.get(desc.meridian)]):
        if not fmap["meridian"]:
            break
        where = base_where + f" AND {fmap['meridian']} LIKE {_quote(meridian_value + '%')}"
        attempts_tried.append(where)
        try:
            features = query(where)
        except (requests.RequestException, arcgis_client.ArcGISError, ValueError) as exc:
            return PLSSResult(found=False, description=desc, error=f"BLM query failed: {exc}")
        if features:
            break

    if not features:
        # Meridian filter may be wrong/missing from the schema entirely; retry without it.
        attempts_tried.append(base_where)
        try:
            features = query(base_where)
        except (requests.RequestException, arcgis_client.ArcGISError, ValueError) as exc:
            return PLSSResult(found=False, description=desc, error=f"BLM query failed: {exc}")
        confidence = "section_no_meridian_filter"

    if not features:
        return PLSSResult(found=False, description=desc,
                           error=f"No matching Section found in BLM PLSS data. Tried: {attempts_tried}")

    section_geometry = features[0].get("geometry")
    if not section_geometry:
        return PLSSResult(found=False, description=desc, error="BLM feature had no geometry")

    if desc.aliquot_parts:
        lat, lon = resolve_aliquot_centroid(section_geometry, desc.aliquot_parts)
        confidence = f"aliquot_approx_within_{confidence}"
    else:
        minx, miny, maxx, maxy = _bbox_of_geometry(section_geometry)
        lat, lon = (miny + maxy) / 2, (minx + maxx) / 2

    return PLSSResult(
        found=True,
        description=desc,
        lat=lat,
        lon=lon,
        section_geometry=section_geometry,
        confidence=confidence,
        source_service=f"{service_url} (layer {layer_id})",
    )
