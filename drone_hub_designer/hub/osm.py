"""OpenStreetMap (Overpass API) features around the hub, as map obstacles and zones.

The browser runs the query (this server never calls Overpass) and hands the raw
JSON to `features_from_overpass`. OSM coverage varies by place: buildings
without a mapped height get an estimate, and every estimate says so in its
"source" field, so review the obstacle list before trusting the corridors.

Map data © OpenStreetMap contributors, available under the Open Database License.
"""

from __future__ import annotations

import math
import re

from .geo import point_in_polygon, to_local

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OBSTACLE_RADIUS_M = 400
ZONE_RADIUS_M = 1000
MAX_OBSTACLES = 150
MAX_RESIDENTIAL_BUILDINGS = 40
# Assumptions, flagged on every obstacle that uses them.
METRES_PER_LEVEL = 3.0
ASSUMED_BUILDING_HEIGHT_M = 10.0
# Starting minimum overflight heights per zone kind. These repeat the example
# site's placeholders; they are design choices, not regulations.
DEFAULT_MIN_OVERFLIGHT_M = {"residential": 45.0, "school": 45.0, "hospital": 45.0, "people": 30.0}

RESIDENTIAL_BUILDINGS = {"house", "residential", "apartments", "detached", "semidetached_house", "terrace",
                         "bungalow", "dormitory"}


def overpass_query(lat: float, lon: float) -> str:
    a_ob = f"(around:{OBSTACLE_RADIUS_M},{lat:.6f},{lon:.6f})"
    a_zn = f"(around:{ZONE_RADIUS_M},{lat:.6f},{lon:.6f})"
    return (
        "[out:json][timeout:25];("
        f'way["building"]{a_ob};'
        f'way["landuse"="residential"]{a_zn};'
        f'relation["landuse"="residential"]{a_zn};'
        f'way["amenity"~"^(school|kindergarten|hospital|parking)$"]{a_zn};'
        f'node["man_made"~"^(mast|tower|chimney)$"]{a_ob};'
        f'way["man_made"~"^(mast|tower|chimney)$"]{a_ob};'
        f'node["power"="tower"]{a_ob};'
        ");out geom;"
    )


def parse_height_m(value: str | None) -> float | None:
    """OSM height tags: '12', '12 m', '12.5m', '40 ft', "40'"; returns metres or None."""
    if not value:
        return None
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(m|ft|')?\s*$", str(value).replace(",", "."))
    if not m:
        return None
    number = float(m.group(1))
    return number * 0.3048 if m.group(2) in ("ft", "'") else number


def _rings(el: dict) -> list[list[list[float]]]:
    if el.get("type") == "way" and el.get("geometry"):
        return [[[p["lat"], p["lon"]] for p in el["geometry"]]]
    if el.get("type") == "relation":
        return [[[p["lat"], p["lon"]] for p in m.get("geometry", [])]
                for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
    return []


def _height(tags: dict) -> tuple[float, str]:
    h = parse_height_m(tags.get("height"))
    if h is not None:
        return h, "OSM height tag"
    levels = parse_height_m(tags.get("building:levels"))
    if levels:
        return levels * METRES_PER_LEVEL, f"estimated: {levels:g} levels x {METRES_PER_LEVEL:g} m"
    return ASSUMED_BUILDING_HEIGHT_M, f"assumed {ASSUMED_BUILDING_HEIGHT_M:g} m (no height in OSM)"


def features_from_overpass(data: dict, hub: tuple[float, float]) -> tuple[list[dict], list[dict], list[str]]:
    """Returns (obstacles, zones, notes) in the map geometry format of hub.geo."""
    obstacles, zones, residential_buildings, notes = [], [], [], []
    skipped_towers = 0
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        osm_ref = f"OSM {el.get('type')} {el.get('id')}"

        if el.get("type") == "node":
            h = parse_height_m(tags.get("height"))
            if h is None:
                skipped_towers += 1
                continue
            kind = tags.get("man_made") or ("power tower" if tags.get("power") == "tower" else "structure")
            obstacles.append({"name": tags.get("name") or kind.capitalize(), "lat": el["lat"], "lon": el["lon"],
                              "height_m": round(h, 1), "width_m": 2.0, "source": f"{osm_ref}, OSM height tag"})
            continue

        for ring in _rings(el):
            if len(ring) < 3:
                continue
            local = [to_local(lat, lon, hub) for lat, lon in ring]
            if "building" in tags or "man_made" in tags:
                if "man_made" in tags and parse_height_m(tags.get("height")) is None:
                    skipped_towers += 1
                    continue
                height, basis = _height(tags)
                cx = sum(p[0] for p in local) / len(local)
                cy = sum(p[1] for p in local) / len(local)
                lat = sum(p[0] for p in ring) / len(ring)
                lon = sum(p[1] for p in ring) / len(ring)
                width = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a in local for b in local)
                name = tags.get("name") or f"Building ({tags.get('building', tags.get('man_made'))})"
                obstacles.append({"name": name, "lat": lat, "lon": lon, "height_m": round(height, 1),
                                  "width_m": round(width, 1), "source": f"{osm_ref}, {basis}",
                                  "_dist": math.hypot(cx, cy)})
                if tags.get("building") in RESIDENTIAL_BUILDINGS:
                    residential_buildings.append((math.hypot(cx, cy), ring, osm_ref))
                continue

            amenity, landuse = tags.get("amenity"), tags.get("landuse")
            if landuse == "residential":
                kind, label = "residential", "Residential area"
            elif amenity in ("school", "kindergarten"):
                kind, label = "school", "School"
            elif amenity == "hospital":
                kind, label = "hospital", "Hospital"
            elif amenity == "parking":
                if point_in_polygon(0.0, 0.0, local):
                    notes.append("The hub sits inside a mapped parking area. It is kept as a people zone; only "
                                 "the part outside your lot outline counts as overflight of cars and shoppers.")
                kind, label = "people", "Parking"
            else:
                continue
            zones.append({"name": tags.get("name") or label, "kind": kind,
                          "min_overflight_m": DEFAULT_MIN_OVERFLIGHT_M[kind],
                          "polygon": ring, "source": osm_ref})

    # Houses are noise receptors even where no residential land use is mapped.
    for _, ring, ref in sorted(residential_buildings)[:MAX_RESIDENTIAL_BUILDINGS]:
        zones.append({"name": "Home", "kind": "residential",
                      "min_overflight_m": DEFAULT_MIN_OVERFLIGHT_M["residential"], "polygon": ring, "source": ref})

    obstacles.sort(key=lambda o: o.get("_dist", 0.0))
    if len(obstacles) > MAX_OBSTACLES:
        notes.append(f"Kept the {MAX_OBSTACLES} nearest of {len(obstacles)} OSM obstacles.")
        obstacles = obstacles[:MAX_OBSTACLES]
    for o in obstacles:
        o.pop("_dist", None)
    estimated = sum(1 for o in obstacles if "OSM height tag" not in o["source"])
    if estimated:
        notes.append(f"{estimated} of {len(obstacles)} obstacle heights are estimated or assumed, not mapped. "
                     "Check them on the map.")
    if skipped_towers:
        notes.append(f"Skipped {skipped_towers} towers/masts with no mapped height; add them by hand if they matter.")
    return obstacles, zones, notes
