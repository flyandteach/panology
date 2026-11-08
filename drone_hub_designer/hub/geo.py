"""Turns a site drawn on a map into the engine's inputs, and the results back into map shapes.

The map sends a "site geometry" dict (latitudes/longitudes, WGS 84):

    {
      "version": int,              # bumped by Python when it replaces the drawing (import, OSM fill)
      "hub": [lat, lon] | None,    # hub centre (the apron centre)
      "store": [lat, lon] | None,  # any point on the store; sets which way the layout faces
      "lot": [[lat, lon], ...] | None,  # available lot outline
      "obstacles": [{"name", "lat", "lon", "height_m", "width_m", "source"}],
      "zones": [{"name", "kind", "min_overflight_m", "polygon": [[lat, lon], ...], "source"}],
    }

Distances use a local flat projection centred on the hub (equirectangular,
spherical Earth of radius 6,371,008.8 m, the IUGG mean radius). Over the
1-2 km this tool looks at, the error is far below the accuracy of a hand-drawn
outline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

EARTH_RADIUS_M = 6_371_008.8
NOISE_SENSITIVE_KINDS = {"residential", "school", "hospital"}


def empty_geometry() -> dict:
    return {"version": 0, "hub": None, "store": None, "lot": None, "obstacles": [], "zones": []}


# --- projection ----------------------------------------------------------------

def to_local(lat: float, lon: float, origin: tuple[float, float]) -> tuple[float, float]:
    """(east, north) metres from origin."""
    lat0, lon0 = origin
    x = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_RADIUS_M
    return x, y


def from_local(x: float, y: float, origin: tuple[float, float]) -> tuple[float, float]:
    lat0, lon0 = origin
    lat = lat0 + math.degrees(y / EARTH_RADIUS_M)
    lon = lon0 + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(lat0))))
    return lat, lon


def bearing_of(x: float, y: float) -> float:
    return math.degrees(math.atan2(x, y)) % 360.0


# --- planar polygon helpers ------------------------------------------------------

def point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _segment_distance(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def distance_to_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> float:
    if point_in_polygon(x, y, poly):
        return 0.0
    n = len(poly)
    return min(_segment_distance(x, y, *poly[i], *poly[(i + 1) % n]) for i in range(n))


def _edge_distance(poly: list[tuple[float, float]]) -> float:
    """Distance from the origin to the nearest edge of a polygon, whether or not the origin is inside."""
    n = len(poly)
    return min(_segment_distance(0.0, 0.0, *poly[i], *poly[(i + 1) % n]) for i in range(n))


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


@dataclass
class Rectangle:
    angle_deg: float  # compass bearing of side "a"
    a_m: float
    b_m: float  # side at angle_deg + 90
    centre: tuple[float, float]


def min_area_rectangle(points: list[tuple[float, float]]) -> Rectangle:
    """Smallest-area enclosing rectangle; one side is always collinear with a hull edge."""
    hull = convex_hull(points)
    best = None
    for i in range(len(hull)):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % len(hull)]
        theta = math.atan2(y2 - y1, x2 - x1)
        c, s = math.cos(theta), math.sin(theta)
        us = [x * c + y * s for x, y in hull]
        vs = [-x * s + y * c for x, y in hull]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0]:
            umid, vmid = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            centre = (umid * c - vmid * s, umid * s + vmid * c)
            best = (area, theta, max(us) - min(us), max(vs) - min(vs), centre)
    _, theta, a, b, centre = best
    # theta is measured from east, counter-clockwise; convert to a compass bearing.
    return Rectangle((90.0 - math.degrees(theta)) % 360.0, a, b, centre)


def _angle_gap(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def polygon_sector(poly: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """(bearing_from, bearing_to, inner_m, outer_m) of the sector from the origin that covers the polygon.

    The sector is a conservative cover: it can include ground the polygon does not.
    """
    outer = max(math.hypot(x, y) for x, y in poly)
    if point_in_polygon(0.0, 0.0, poly):
        return 0.0, 359.99, 0.0, outer
    inner = distance_to_polygon(0.0, 0.0, poly)
    # Densify edges so long edges don't hide the angular extent between vertices.
    bearings = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        for k in range(8):
            t = k / 8
            bearings.append(bearing_of(x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
    bearings.sort()
    # The sector is the complement of the largest empty gap between bearings.
    gaps = [((bearings[(i + 1) % len(bearings)] - bearings[i]) % 360.0, i) for i in range(len(bearings))]
    _, i = max(gaps)
    start = bearings[(i + 1) % len(bearings)]
    end = bearings[i]
    return start, end, inner, outer


# --- site derivation -------------------------------------------------------------

@dataclass
class DerivedSite:
    site: dict = field(default_factory=dict)  # SiteProfile overrides
    airspace: dict = field(default_factory=dict)  # store_bearing_deg, obstacles, zones
    notes: list[str] = field(default_factory=list)
    frontage_bearing_deg: float | None = None  # direction of the lot's width axis


def derive_site(geo: dict) -> DerivedSite:
    out = DerivedSite()
    hub = geo.get("hub")
    if not hub:
        return out
    origin = (hub[0], hub[1])

    store_bearing = None
    if geo.get("store"):
        sx, sy = to_local(*geo["store"], origin)
        store_bearing = bearing_of(sx, sy)
        out.airspace["store_bearing_deg"] = round(store_bearing, 1)
    else:
        out.notes.append("No store marked: the layout keeps its default orientation (store to the south).")

    lot = geo.get("lot")
    lot_local = None
    if lot and len(lot) >= 3:
        pts = [to_local(lat, lon, origin) for lat, lon in lot]
        lot_local = pts
        rect = min_area_rectangle(pts)
        if not point_in_polygon(0.0, 0.0, pts):
            out.notes.append("The hub pin is outside the lot outline.")
        if store_bearing is None:
            # Without a store, call the longer side the frontage.
            width, depth, frontage = (rect.a_m, rect.b_m, rect.angle_deg) if rect.a_m >= rect.b_m else (
                rect.b_m, rect.a_m, (rect.angle_deg + 90) % 360)
        elif not 45 <= _angle_gap(rect.angle_deg, store_bearing) <= 135:
            # Side a points towards the store, so it is the depth.
            width, depth, frontage = rect.b_m, rect.a_m, (rect.angle_deg + 90) % 360
        else:
            width, depth, frontage = rect.a_m, rect.b_m, rect.angle_deg
        out.site["width_m"] = round(width, 1)
        out.site["depth_m"] = round(depth, 1)
        out.frontage_bearing_deg = frontage
        area = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2
        if area < 0.85 * rect.a_m * rect.b_m:
            out.notes.append(
                f"The lot is not rectangular ({area:.0f} m² inside a {rect.a_m * rect.b_m:.0f} m² bounding "
                "rectangle); the layout check uses the bounding rectangle, so confirm the fit on the map."
            )

    obstacles = []
    for ob in geo.get("obstacles", []):
        x, y = to_local(ob["lat"], ob["lon"], origin)
        obstacles.append({
            "name": ob.get("name") or "Obstacle",
            "bearing_deg": round(bearing_of(x, y), 1),
            "distance_m": round(max(math.hypot(x, y), 0.1), 1),
            "height_m": float(ob.get("height_m") or 0.0),
            "width_m": float(ob.get("width_m") or 1.0),
        })
    out.airspace["obstacles"] = obstacles

    zones = []
    receptor = None
    for z in geo.get("zones", []):
        poly = [to_local(lat, lon, origin) for lat, lon in z.get("polygon", [])]
        if len(poly) < 3:
            continue
        b_from, b_to, inner, outer = polygon_sector(poly)
        if inner == 0.0 and lot_local:
            # The hub is inside this zone (e.g. the store's parking lot). Flight over the hub's own
            # lot doesn't count, so the zone starts at the nearest edge of the lot.
            inner = _edge_distance(lot_local)
        zones.append({
            "name": z.get("name") or z.get("kind", "zone"),
            "kind": z.get("kind", "people"),
            "bearing_from_deg": round(b_from, 1),
            "bearing_to_deg": round(b_to, 1),
            "inner_m": round(inner, 1),
            "outer_m": round(outer, 1),
            "min_overflight_m": float(z.get("min_overflight_m") or 0.0),
        })
        if z.get("kind") in NOISE_SENSITIVE_KINDS:
            receptor = inner if receptor is None else min(receptor, inner)
    out.airspace["zones"] = zones
    if receptor is not None:
        out.site["nearest_receptor_m"] = round(max(receptor, 1.0), 1)
    else:
        out.notes.append("No residential, school or hospital area drawn: nearest receptor distance stays manual.")
    return out


# --- results back onto the map -------------------------------------------------------

def _rotate(x: float, y: float, bearing_deg: float) -> tuple[float, float]:
    """Rotate a local point whose +y axis should point along bearing_deg."""
    t = math.radians(bearing_deg)
    return x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)


def layout_shapes(layout, hub: tuple[float, float], up_bearing_deg: float) -> list[dict]:
    """Layout rectangles as lat/lon polygons, with the apron centre on the hub pin.

    Layout coordinates have +y pointing away from the store; that axis is laid
    along up_bearing_deg.
    """
    apron = layout.get("Airside apron (fenced)")
    cx, cy = apron.x + apron.w / 2, apron.y + apron.h / 2
    shapes = []
    for r in layout.rects:
        corners = [(r.x, r.y), (r.x2, r.y), (r.x2, r.y2), (r.x, r.y2)]
        ring = []
        for x, y in corners:
            ex, ny = _rotate(x - cx, y - cy, up_bearing_deg)
            ring.append(list(from_local(ex, ny, hub)))
        shapes.append({"name": r.name, "kind": r.kind, "polygon": ring})
    return shapes


def corridor_shapes(flight_paths, hub: tuple[float, float], half_width_m: float) -> list[dict]:
    shapes = []
    for c in flight_paths.corridors:
        t = math.radians(c.heading_deg)
        ex, ey = c.length_m * math.sin(t), c.length_m * math.cos(t)
        px, py = half_width_m * math.cos(t), -half_width_m * math.sin(t)
        quad = [(px, py), (ex + px, ey + py), (ex - px, ey - py), (-px, -py)]
        shapes.append({
            "heading_deg": c.heading_deg,
            "length_m": c.length_m,
            "centreline": [list(hub), list(from_local(ex, ey, hub))],
            "polygon": [list(from_local(x, y, hub)) for x, y in quad],
        })
    return shapes
