"""Google Earth KML/KMZ import, and KML / GeoJSON export of a design.

Import reads placemarks drawn in Google Earth and sorts them by name:

- a point named like "store" marks the store; one named like "hub", "pad" or
  "site" places the hub (otherwise the first other point does);
- a point with a height in its name or description ("Light pole 12 m",
  "tree 40 ft", "h=15") becomes an obstacle;
- a polygon named like "lot", "site", "parcel" or "boundary" is the lot
  (otherwise the first polygon without a zone keyword is);
- polygons named like "home", "house", "residential", "school", "hospital",
  "parking" or "people" become sensitive zones of that kind.

Export writes the hub, lot, layout, corridors (as 3D lines that follow the
climb profile), obstacles and zones, so the design can be checked in Google
Earth or a GIS.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from html import escape

from .flightpath import altitude_at
from .geo import corridor_shapes, empty_geometry, layout_shapes
from .osm import DEFAULT_MIN_OVERFLIGHT_M

MAX_KML_BYTES = 20 * 1024 * 1024

ZONE_KEYWORDS = [
    ("residential", ("home", "house", "residential", "neighbourhood", "neighborhood", "apartment")),
    ("school", ("school", "kindergarten", "daycare")),
    ("hospital", ("hospital", "clinic")),
    ("people", ("parking", "people", "entrance", "walkway", "plaza", "park")),
]
LOT_KEYWORDS = ("lot", "site", "parcel", "boundary")
HUB_KEYWORDS = ("hub", "pad", "site", "nest")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_all(el, name):
    return [e for e in el.iter() if _local(e.tag) == name]


def _text(el, name) -> str:
    found = _find_all(el, name)
    return (found[0].text or "").strip() if found else ""


def _coords(text: str) -> list[list[float]]:
    pts = []
    for tup in text.split():
        parts = tup.split(",")
        if len(parts) >= 2:
            lon, lat = float(parts[0]), float(parts[1])
            pts.append([lat, lon])
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]  # KML rings repeat the first point
    return pts


def _height_from(text: str) -> float | None:
    explicit = re.search(r"h\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(m|ft|feet|')?", text, re.I)
    m = explicit or re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(m|meters?|metres?|ft|feet|foot|')(?![a-z])", text, re.I)
    if not m:
        return None
    value = float(m.group(1))
    unit = (m.group(2) or "m").lower()
    return value * 0.3048 if unit in ("ft", "feet", "foot", "'") else value


def _zone_kind(name: str) -> str | None:
    low = name.lower()
    for kind, words in ZONE_KEYWORDS:
        if any(w in low for w in words):
            return kind
    return None


def read_kml(data: bytes) -> bytes:
    if len(data) > MAX_KML_BYTES:
        raise ValueError("File is larger than 20 MB.")
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise ValueError("The KMZ file has no .kml inside.")
            info = z.getinfo("doc.kml" if "doc.kml" in names else names[0])
            if info.file_size > MAX_KML_BYTES:
                raise ValueError("The KML inside the KMZ is larger than 20 MB.")
            return z.read(info)
    return data


def import_kml(data: bytes) -> tuple[dict, list[str]]:
    """Returns (site geometry, notes)."""
    root = ET.fromstring(read_kml(data))
    geo, notes = empty_geometry(), []
    points, polygons = [], []
    for pm in _find_all(root, "Placemark"):
        name = _text(pm, "name")
        desc = _text(pm, "description")
        for poly in _find_all(pm, "Polygon"):
            outer = _find_all(poly, "outerBoundaryIs") or [poly]
            ring = _coords(_text(outer[0], "coordinates"))
            if len(ring) >= 3:
                polygons.append((name, desc, ring))
        for pt in _find_all(pm, "Point"):
            c = _coords(_text(pt, "coordinates"))
            if c:
                points.append((name, desc, c[0]))

    unused_points = []
    for name, desc, (lat, lon) in points:
        low = name.lower()
        height = _height_from(f"{name} {desc}")
        if "store" in low and geo["store"] is None:
            geo["store"] = [lat, lon]
        elif any(w in low for w in HUB_KEYWORDS) and geo["hub"] is None:
            geo["hub"] = [lat, lon]
        elif height is not None:
            geo["obstacles"].append({"name": name or "Obstacle", "lat": lat, "lon": lon,
                                     "height_m": round(height, 1), "width_m": 5.0, "source": "KML import"})
        else:
            unused_points.append((name, lat, lon))
    if geo["hub"] is None and unused_points:
        name, lat, lon = unused_points.pop(0)
        geo["hub"] = [lat, lon]
        notes.append(f'Used the point "{name or "(unnamed)"}" as the hub.')
    for name, _, _ in unused_points:
        notes.append(f'Ignored the point "{name or "(unnamed)"}": no height given and not named hub or store.')

    lot_candidates = []
    for name, desc, ring in polygons:
        kind = _zone_kind(name)
        if any(w in name.lower() for w in LOT_KEYWORDS) and geo["lot"] is None and kind is None:
            geo["lot"] = ring
        elif kind:
            geo["zones"].append({"name": name, "kind": kind, "min_overflight_m": DEFAULT_MIN_OVERFLIGHT_M[kind],
                                 "polygon": ring, "source": "KML import"})
        else:
            lot_candidates.append((name, ring))
    if geo["lot"] is None and lot_candidates:
        name, ring = lot_candidates.pop(0)
        geo["lot"] = ring
        notes.append(f'Used the polygon "{name or "(unnamed)"}" as the lot.')
    for name, ring in lot_candidates:
        geo["zones"].append({"name": name or "Area", "kind": "people",
                             "min_overflight_m": DEFAULT_MIN_OVERFLIGHT_M["people"], "polygon": ring,
                             "source": "KML import"})
        notes.append(f'Treated the polygon "{name or "(unnamed)"}" as a "people" zone; rename it to set its kind.')
    if geo["hub"] is None:
        notes.append("No hub point found. Place the hub on the map.")
    return geo, notes


# --- export ------------------------------------------------------------------------

# KML colours are aabbggrr.
_KML_STYLE = {
    "lot": ("ff00ff00", "1a00ff00"),
    "setback": ("ff999999", "33f5eee8"),
    "building": ("ff3a5a7a", "aa9ab9c9"),
    "apron": ("ff555555", "66e2ddd9"),
    "pad": ("ffb57f4a", "ddb57f4a"),
    "battery": ("ff3a57d0", "dd3a57d0"),
    "corridor": ("ffd6782a", "552a78d6"),
    "zone": ("ff3468eb", "333468eb"),
    "obstacle": ("ff4e5152", "ff4e5152"),
}


def _kml_ring(ring: list[list[float]], alt: float | None = None) -> str:
    pts = ring + [ring[0]]
    return " ".join(f"{lon:.7f},{lat:.7f},{alt or 0:.1f}" for lat, lon in pts)


def _placemark_polygon(name: str, style: str, ring, desc: str = "") -> str:
    return (f"<Placemark><name>{escape(name)}</name><description>{escape(desc)}</description>"
            f"<styleUrl>#{style}</styleUrl><Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing>"
            f"<coordinates>{_kml_ring(ring)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>")


def _placemark_point(name: str, style: str, lat: float, lon: float, desc: str = "") -> str:
    return (f"<Placemark><name>{escape(name)}</name><description>{escape(desc)}</description>"
            f"<styleUrl>#{style}</styleUrl><Point><coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point>"
            "</Placemark>")


def export_kml(design, geo: dict, title: str = "Drone delivery hub") -> str:
    hub = tuple(geo["hub"])
    air, ac = design.inputs.airspace, design.inputs.aircraft
    up = air.store_bearing_deg + 180.0
    styles = "".join(
        f'<Style id="{k}"><LineStyle><color>{line}</color><width>2</width></LineStyle>'
        f"<PolyStyle><color>{fill}</color></PolyStyle></Style>" for k, (line, fill) in _KML_STYLE.items()
    )
    parts = [f'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
             f"<name>{escape(title)}</name>{styles}"]
    parts.append(_placemark_point("Hub", "pad", *hub, "Hub centre (apron centre)"))
    if geo.get("store"):
        parts.append(_placemark_point("Store", "building", *geo["store"]))
    if geo.get("lot"):
        parts.append(_placemark_polygon("Lot", "lot", geo["lot"]))

    parts.append("<Folder><name>Layout</name>")
    for s in layout_shapes(design.layout, hub, up):
        parts.append(_placemark_polygon(s["name"], s["kind"] if s["kind"] in _KML_STYLE else "apron", s["polygon"]))
    parts.append("</Folder><Folder><name>Corridors</name>")
    for c in corridor_shapes(design.flight_paths, hub, air.corridor_half_width_m):
        label = f"Corridor {c['heading_deg']:03.0f}°"
        parts.append(_placemark_polygon(label, "corridor", c["polygon"],
                                        f"{c['length_m']:.0f} m to cruise altitude {ac.cruise_altitude_m:.0f} m AGL"))
        # 3D centreline following the climb profile, heights relative to ground.
        (lat0, lon0), (lat1, lon1) = c["centreline"]
        n = 12
        coords = " ".join(
            f"{lon0 + (lon1 - lon0) * i / n:.7f},{lat0 + (lat1 - lat0) * i / n:.7f},"
            f"{altitude_at(c['length_m'] * i / n, ac):.1f}" for i in range(n + 1)
        )
        parts.append(f"<Placemark><name>{escape(label)} climb</name><styleUrl>#corridor</styleUrl><LineString>"
                     f"<altitudeMode>relativeToGround</altitudeMode><coordinates>{coords}</coordinates>"
                     "</LineString></Placemark>")
    parts.append("</Folder><Folder><name>Obstacles</name>")
    for o in geo.get("obstacles", []):
        parts.append(_placemark_point(o.get("name", "Obstacle"), "obstacle", o["lat"], o["lon"],
                                      f"{o.get('height_m', 0):.1f} m tall; {o.get('source', '')}"))
    parts.append("</Folder><Folder><name>Sensitive zones</name>")
    for z in geo.get("zones", []):
        parts.append(_placemark_polygon(z.get("name", "Zone"), "zone", z["polygon"],
                                        f"{z.get('kind')}; keep above {z.get('min_overflight_m', 0):.0f} m"))
    parts.append("</Folder></Document></kml>")
    return "".join(parts)


def export_geojson(design, geo: dict) -> str:
    hub = tuple(geo["hub"])
    air, ac = design.inputs.airspace, design.inputs.aircraft
    up = air.store_bearing_deg + 180.0

    def ring(r):
        return [[[lon, lat] for lat, lon in r + [r[0]]]]

    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [hub[1], hub[0]]},
              "properties": {"layer": "hub", "name": "Hub"}}]
    if geo.get("store"):
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": geo["store"][::-1]},
                      "properties": {"layer": "store", "name": "Store"}})
    if geo.get("lot"):
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": ring(geo["lot"])},
                      "properties": {"layer": "lot", "name": "Lot"}})
    for s in layout_shapes(design.layout, hub, up):
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": ring(s["polygon"])},
                      "properties": {"layer": "layout", "name": s["name"], "kind": s["kind"]}})
    for c in corridor_shapes(design.flight_paths, hub, air.corridor_half_width_m):
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": ring(c["polygon"])},
                      "properties": {"layer": "corridor", "heading_deg": c["heading_deg"],
                                     "length_m": round(c["length_m"], 1),
                                     "cruise_altitude_m_agl": ac.cruise_altitude_m}})
    for o in geo.get("obstacles", []):
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [o["lon"], o["lat"]]},
                      "properties": {"layer": "obstacle", **{k: v for k, v in o.items() if k not in ("lat", "lon")}}})
    for z in geo.get("zones", []):
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": ring(z["polygon"])},
                      "properties": {"layer": "zone", **{k: v for k, v in z.items() if k != "polygon"}}})
    return json.dumps({"type": "FeatureCollection", "features": feats}, indent=1)
