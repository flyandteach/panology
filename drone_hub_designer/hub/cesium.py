"""Surface heights measured in the browser from Cesium ion (Cesium OSM Buildings + Cesium World
Terrain), turned into map obstacles.

The browser samples the 3D surface on a polar grid around the hub (every `step_deg` of bearing,
every `step_m` of distance) and sends back the points that stand at least `threshold_m` above the
hub's own ground. Each point becomes an obstacle as wide as the grid cell, so ground that rises
away from the hub counts as well as buildings.

Building heights in Cesium OSM Buildings come from OpenStreetMap: the height tag where mapped,
otherwise an estimate of 3 m per level (Cesium's documentation). Terrain comes from Cesium World
Terrain. Google Photorealistic 3D Tiles are never measured; see site_map/globe.js.
"""

from __future__ import annotations

import math

from .geo import from_local

CESIUM_JS_VERSION = "1.146.0"
CESIUM_BASE_URL = f"https://cdn.jsdelivr.net/npm/cesium@{CESIUM_JS_VERSION}/Build/Cesium/"
SOURCE = "Cesium OSM Buildings + World Terrain sample"


def measure_settings(corridor_length_m: float, heading_step_deg: float) -> dict:
    """Grid the browser should sample: out past the end of the climb, capped to keep it quick."""
    radius = min(max(math.ceil(corridor_length_m * 1.2 / 10) * 10, 150), 800)
    return {"step_deg": heading_step_deg, "step_m": 10, "radius_m": radius, "threshold_m": 1.0}


def samples_to_obstacles(payload: dict) -> tuple[list[dict], list[str]]:
    hub = tuple(payload["hub"])
    step_deg = float(payload["step_deg"])
    step_m = float(payload["step_m"])
    obstacles = []
    for bearing, dist, height in payload.get("points", []):
        t = math.radians(bearing)
        lat, lon = from_local(dist * math.sin(t), dist * math.cos(t), hub)
        width = max(step_m, dist * math.radians(step_deg))
        obstacles.append({
            "name": f"Surface {height:.0f} m",
            "lat": lat, "lon": lon,
            "height_m": round(float(height), 1),
            "width_m": round(width, 1),
            "source": f"{SOURCE}, {bearing:g}° {dist:g} m",
        })
    notes = [
        f"Measured {payload.get('sampled', 0)} points within {payload.get('radius_m', 0):g} m of the hub; "
        f"{len(obstacles)} stand at least {payload.get('threshold_m', 1):g} m above the hub's ground "
        f"({payload.get('hub_ground_m', 0):.1f} m ellipsoid height). They replace earlier measurements and "
        "OpenStreetMap building obstacles, which the 3D buildings already include.",
        "Cesium OSM Buildings take heights from OpenStreetMap, or 3 m per level where no height is mapped, so "
        "spot-check tall buildings. Trees, poles and wires are not in that tileset: add them by hand.",
    ]
    return obstacles, notes
