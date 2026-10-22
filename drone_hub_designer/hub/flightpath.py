"""Departure / arrival corridor planning around the hub.

A corridor is a straight lane from the hub centre along one compass heading,
used for the climb out to cruise altitude (and the reverse for arrivals).
Beyond the end of the corridor aircraft turn direct to the customer.

For every candidate heading the planner checks:
- obstacles: inside the lane, the aircraft must be at least
  `obstacle_clearance_m` above each obstacle where it first reaches it;
- sensitive zones: length of lane flown below the zone's minimum overflight
  height (people in the parking lot, homes, schools).

Corridors are then chosen lexicographically: obstacle-clear headings only,
fewest metres of low overflight first, and among those the set that adds the
least mean extra distance to deliveries spread evenly over the service area.
The number of corridors is the larger of `min_corridors` and what the
movement rate needs at `movement_spacing_s` per aircraft per corridor.

The climb is modelled as a vertical lift to `vertical_climb_m` followed by a
constant-gradient climb (climb rate / climb ground speed) to cruise altitude.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from html import escape

from .models import AircraftProfile, AirspaceProfile
from .noise import level_at_distance

MIN_CORRIDOR_LENGTH_M = 150.0
SAMPLE_STEP_M = 5.0


def altitude_at(x_m: float, ac: AircraftProfile) -> float:
    gradient = ac.climb_rate_mps / max(ac.climb_ground_speed_mps, 0.1)
    return min(ac.cruise_altitude_m, ac.vertical_climb_m + gradient * max(x_m, 0.0))


def transition_distance_m(ac: AircraftProfile) -> float:
    gradient = ac.climb_rate_mps / max(ac.climb_ground_speed_mps, 0.1)
    return max(ac.cruise_altitude_m - ac.vertical_climb_m, 0.0) / gradient


def corridor_length_m(ac: AircraftProfile) -> float:
    return max(transition_distance_m(ac), MIN_CORRIDOR_LENGTH_M)


def _angle_diff(a: float, b: float) -> float:
    """Signed smallest difference a - b in degrees, in (-180, 180]."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def _in_sector(bearing: float, start: float, end: float) -> bool:
    span = (end - start) % 360.0
    return (bearing - start) % 360.0 <= span


def _xy(bearing_deg: float, dist: float) -> tuple[float, float]:
    """Compass bearing and distance to east/north metres."""
    t = math.radians(bearing_deg)
    return dist * math.sin(t), dist * math.cos(t)


@dataclass
class ObstacleConflict:
    obstacle: str
    along_m: float
    aircraft_alt_m: float
    required_alt_m: float


@dataclass
class HeadingAssessment:
    heading_deg: float
    conflicts: list[ObstacleConflict] = field(default_factory=list)
    low_overflight_m: dict[str, float] = field(default_factory=dict)  # zone name -> metres below minimum
    obstacles_in_lane: list[tuple[str, float, float]] = field(default_factory=list)  # name, along, height

    @property
    def clear(self) -> bool:
        return not self.conflicts

    @property
    def total_low_overflight_m(self) -> float:
        return sum(self.low_overflight_m.values())


def assess_heading(heading: float, ac: AircraftProfile, air: AirspaceProfile) -> HeadingAssessment:
    result = HeadingAssessment(heading)
    length = corridor_length_m(ac)
    for ob in air.obstacles:
        rel = math.radians(_angle_diff(ob.bearing_deg, heading))
        along = ob.distance_m * math.cos(rel)
        cross = abs(ob.distance_m * math.sin(rel))
        if along <= 0 or along - ob.width_m / 2 > length:
            continue
        if cross - ob.width_m / 2 > air.corridor_half_width_m:
            continue
        near = max(along - ob.width_m / 2, 0.0)
        result.obstacles_in_lane.append((ob.name, near, ob.height_m))
        need = ob.height_m + air.obstacle_clearance_m
        have = altitude_at(near, ac)
        if have < need:
            result.conflicts.append(ObstacleConflict(ob.name, near, have, need))

    x = SAMPLE_STEP_M / 2
    while x < length:
        h = altitude_at(x, ac)
        for z in air.zones:
            if z.inner_m <= x <= z.outer_m and _in_sector(heading, z.bearing_from_deg, z.bearing_to_deg):
                if h < z.min_overflight_m:
                    result.low_overflight_m[z.name] = result.low_overflight_m.get(z.name, 0.0) + SAMPLE_STEP_M
        x += SAMPLE_STEP_M
    return result


def _destinations(radius_m: float, rings: int = 12, spokes: int = 72) -> list[tuple[float, float]]:
    """Points spread evenly by area over a disc (equal-area rings)."""
    pts = []
    for i in range(rings):
        r = radius_m * math.sqrt((i + 0.5) / rings)
        for j in range(spokes):
            pts.append(_xy(360.0 * (j + 0.5) / spokes, r))
    return pts


def mean_detour_m(headings: list[float], length_m: float, service_radius_m: float) -> float:
    """Mean one-way extra distance from leaving along the nearest-useful corridor vs flying direct."""
    if not headings:
        return 0.0
    exits = [_xy(h, length_m) for h in headings]
    total = 0.0
    pts = _destinations(service_radius_m)
    for dx, dy in pts:
        direct = math.hypot(dx, dy)
        best = min(length_m + math.hypot(dx - ex, dy - ey) for ex, ey in exits)
        total += best - direct
    return total / len(pts)


@dataclass
class Corridor:
    heading_deg: float
    length_m: float
    low_overflight_m: dict[str, float]
    obstacles_in_lane: list[tuple[str, float, float]]


@dataclass
class FlightPathResult:
    corridors: list[Corridor]
    corridors_required: int
    movements_per_hour: float
    corridor_capacity_per_hour: float
    transition_distance_m: float
    corridor_length_m: float
    clear_headings: int
    candidate_headings: int
    mean_detour_m: float  # per sortie, outbound plus return
    extra_flight_s: float  # per sortie
    route_warnings: list[str]
    assessments: list[HeadingAssessment]

    @property
    def enough_corridors(self) -> bool:
        return len(self.corridors) >= self.corridors_required

    @property
    def low_overflight_m(self) -> float:
        return sum(sum(c.low_overflight_m.values()) for c in self.corridors)

    def to_map_svg(self, air: AirspaceProfile, ac: AircraftProfile) -> str:
        return render_map(self, air, ac)

    def to_profile_svg(self, air: AirspaceProfile, ac: AircraftProfile) -> str:
        return render_profile(self, air, ac)


def plan_flight_paths(
    ac: AircraftProfile,
    air: AirspaceProfile,
    sorties_per_hour: float,
    service_radius_km: float,
) -> FlightPathResult:
    step = max(air.heading_step_deg, 1.0)
    headings = [i * step for i in range(int(round(360.0 / step)))]
    assessments = [assess_heading(h, ac, air) for h in headings]
    clear = [a for a in assessments if a.clear]

    movements = 2 * sorties_per_hour
    per_corridor = 3600.0 / max(air.movement_spacing_s, 1.0) * air.max_corridor_utilization
    required = max(air.min_corridors, math.ceil(movements / per_corridor) if movements else 1)

    length = corridor_length_m(ac)
    radius_m = service_radius_km * 1000

    # Lexicographic choice: least low overflight first, then least added distance.
    pool = sorted(clear, key=lambda a: a.total_low_overflight_m)
    chosen: list[HeadingAssessment] = []
    while len(chosen) < required:
        spaced = [
            a for a in pool
            if a not in chosen
            and all(abs(_angle_diff(a.heading_deg, c.heading_deg)) >= air.min_corridor_separation_deg for c in chosen)
        ]
        if not spaced:
            break
        least = spaced[0].total_low_overflight_m
        tier = [a for a in spaced if a.total_low_overflight_m <= least + 1e-9]
        best = min(tier, key=lambda a: mean_detour_m([c.heading_deg for c in chosen] + [a.heading_deg],
                                                     length, radius_m))
        chosen.append(best)

    chosen.sort(key=lambda a: a.heading_deg)
    detour_one_way = mean_detour_m([c.heading_deg for c in chosen], length, radius_m)

    warnings = []
    for z in air.zones:
        if z.min_overflight_m > ac.cruise_altitude_m and z.outer_m > length:
            warnings.append(
                f"{z.name}: minimum overflight {z.min_overflight_m:.0f} m is above the aircraft's cruise altitude "
                f"({ac.cruise_altitude_m:.0f} m); en-route flights to or across it will be lower than intended."
            )

    return FlightPathResult(
        corridors=[Corridor(a.heading_deg, length, a.low_overflight_m, a.obstacles_in_lane) for a in chosen],
        corridors_required=required,
        movements_per_hour=movements,
        corridor_capacity_per_hour=per_corridor,
        transition_distance_m=transition_distance_m(ac),
        corridor_length_m=length,
        clear_headings=len(clear),
        candidate_headings=len(headings),
        mean_detour_m=2 * detour_one_way,
        extra_flight_s=2 * detour_one_way / max(ac.cruise_speed_mps, 0.1),
        route_warnings=warnings,
        assessments=assessments,
    )


def overflight_level_db(ac: AircraftProfile, altitude_m: float) -> float:
    """Screening level on the ground directly under the aircraft, from the hover reference level."""
    return level_at_distance(ac.hover_noise_dba, ac.noise_ref_distance_m, altitude_m)


# --- drawing -----------------------------------------------------------------

# Reference palette (dataviz skill, light mode): slot 1 blue for corridors,
# slot 2 orange for sensitive zones; critical red reserved for conflicts.
CORRIDOR = "#2a78d6"
ZONE = "#eb6834"
CRITICAL = "#d03b3b"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"


def render_map(fp: FlightPathResult, air: AirspaceProfile, ac: AircraftProfile, size: int = 560) -> str:
    """Plan view, north up, hub at the centre."""
    extent = max(
        [fp.corridor_length_m * 1.4, 200.0]
        + [o.distance_m + o.width_m for o in air.obstacles]
        + [z.inner_m + 60 for z in air.zones]
    )
    extent = min(extent, 1500.0)
    pad = 40
    c = size / 2
    k = (size / 2 - pad) / extent

    def pt(bearing, dist):
        x, y = _xy(bearing, min(dist, extent))
        return c + x * k, c - y * k

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size + 24}" '
        f'font-family="sans-serif" font-size="11" role="img" aria-label="Corridor plan view">',
        f'<rect width="{size}" height="{size + 24}" fill="{SURFACE}"/>',
    ]
    for r in (0.25, 0.5, 0.75, 1.0):
        out.append(f'<circle cx="{c}" cy="{c}" r="{r * extent * k:.1f}" fill="none" stroke="{GRID}"/>')
        out.append(f'<text x="{c + 3}" y="{c - r * extent * k - 3:.1f}" fill="{INK_2}">{r * extent:.0f} m</text>')

    for z in air.zones:
        inner, outer = z.inner_m, min(z.outer_m, extent)
        if inner >= extent:
            continue
        span = (z.bearing_to_deg - z.bearing_from_deg) % 360.0
        steps = max(2, int(span / 3))
        arc = [pt(z.bearing_from_deg + span * i / steps, outer) for i in range(steps + 1)]
        back = [pt(z.bearing_from_deg + span * i / steps, inner) for i in range(steps, -1, -1)]
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in arc + back)
        out.append(
            f'<polygon points="{d}" fill="{ZONE}" fill-opacity="0.16" stroke="{ZONE}" stroke-width="1">'
            f"<title>{escape(z.name)} ({escape(z.kind)}): keep above {z.min_overflight_m:.0f} m</title></polygon>"
        )
        lx, ly = pt(z.bearing_from_deg + span / 2, inner + (outer - inner) * 0.75)
        out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" fill="{INK}" text-anchor="middle">{escape(z.name)}</text>')

    for o in air.obstacles:
        x, y = pt(o.bearing_deg, o.distance_m)
        r = max(o.width_m / 2 * k, 3)
        out.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{INK_2}" fill-opacity="0.35" stroke="{INK_2}">'
            f"<title>{escape(o.name)}: {o.height_m:.0f} m tall</title></circle>"
        )
        out.append(f'<text x="{x:.1f}" y="{y + r + 12:.1f}" fill="{INK}" text-anchor="middle">'
                   f'{escape(o.name)} ({o.height_m:.0f} m)</text>')

    blocked = {a.heading_deg for a in fp.assessments if not a.clear}
    for h in sorted(blocked):
        x, y = pt(h, extent)
        out.append(f'<line x1="{c}" y1="{c}" x2="{x:.1f}" y2="{y:.1f}" stroke="{CRITICAL}" '
                   f'stroke-opacity="0.18" stroke-width="1"/>')

    w = air.corridor_half_width_m
    for cor in fp.corridors:
        h = cor.heading_deg
        ex, ey = _xy(h, cor.length_m)
        px, py = _xy(h + 90, w)
        quad = [(px, py), (ex + px, ey + py), (ex - px, ey - py), (-px, -py)]
        d = " ".join(f"{c + qx * k:.1f},{c - qy * k:.1f}" for qx, qy in quad)
        out.append(
            f'<polygon points="{d}" fill="{CORRIDOR}" fill-opacity="0.25" stroke="{CORRIDOR}" stroke-width="2">'
            f"<title>Corridor {h:03.0f}°: {cor.length_m:.0f} m to cruise altitude</title></polygon>"
        )
        lx, ly = pt(h, cor.length_m + 18 / k)
        out.append(f'<text x="{lx:.1f}" y="{ly + 4:.1f}" fill="{INK}" text-anchor="middle" '
                   f'font-weight="bold">{h:03.0f}°</text>')

    sx, sy = pt(air.store_bearing_deg, extent * 0.97)
    out.append(f'<text x="{sx:.1f}" y="{sy:.1f}" fill="{INK_2}" text-anchor="middle">store side</text>')
    out.append(f'<circle cx="{c}" cy="{c}" r="5" fill="{INK}"><title>Hub</title></circle>')
    out.append(f'<text x="{size - 20}" y="22" fill="{INK}" text-anchor="middle" font-weight="bold">N ↑</text>')
    out.append(
        f'<text x="8" y="{size + 16}" fill="{INK_2}">Blue: chosen corridors. Orange: sensitive zones. '
        f'Faint red rays: headings blocked by obstacles. Grey: obstacles.</text>'
    )
    out.append("</svg>")
    return "\n".join(out)


def render_profile(fp: FlightPathResult, air: AirspaceProfile, ac: AircraftProfile,
                   width: int = 560, height: int = 260) -> str:
    """Climb profile (altitude vs distance along the corridor) with obstacles in any chosen corridor."""
    left, right, top, bottom = 48, 16, 16, 40
    x_max = fp.corridor_length_m * 1.15
    obstacles = {}
    for cor in fp.corridors:
        for name, along, hgt in cor.obstacles_in_lane:
            obstacles.setdefault(name, (along, hgt, []))[2].append(cor.heading_deg)
    y_max = max([ac.cruise_altitude_m * 1.15]
                + [h + air.obstacle_clearance_m + 5 for _, h, _ in obstacles.values()]
                + [z.min_overflight_m + 5 for z in air.zones])
    pw, ph = width - left - right, height - top - bottom

    def sx(x):
        return left + x / x_max * pw

    def sy(y):
        return top + ph - y / y_max * ph

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="sans-serif" '
        f'font-size="11" role="img" aria-label="Climb profile">',
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
    ]
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = y_max * frac
        out.append(f'<line x1="{left}" x2="{width - right}" y1="{sy(y):.1f}" y2="{sy(y):.1f}" stroke="{GRID}"/>')
        out.append(f'<text x="{left - 6}" y="{sy(y) + 4:.1f}" fill="{INK_2}" text-anchor="end">{y:.0f}</text>')
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        x = x_max * frac
        out.append(f'<text x="{sx(x):.1f}" y="{height - bottom + 16}" fill="{INK_2}" '
                   f'text-anchor="middle">{x:.0f}</text>')
    out.append(f'<text x="{left + pw / 2}" y="{height - 6}" fill="{INK_2}" text-anchor="middle">'
               f'distance along corridor (m); altitude above hub (m)</text>')

    for z in air.zones:
        if z.min_overflight_m <= y_max:
            out.append(f'<line x1="{left}" x2="{width - right}" y1="{sy(z.min_overflight_m):.1f}" '
                       f'y2="{sy(z.min_overflight_m):.1f}" stroke="{ZONE}" stroke-dasharray="4 3"/>')
            out.append(f'<text x="{width - right - 2}" y="{sy(z.min_overflight_m) - 3:.1f}" fill="{INK_2}" '
                       f'text-anchor="end">min over {escape(z.name)}</text>')

    for name, (along, hgt, heads) in obstacles.items():
        need = hgt + air.obstacle_clearance_m
        conflict = altitude_at(along, ac) < need
        colour = CRITICAL if conflict else INK_2
        bw = max(pw * 0.012, 4)
        out.append(
            f'<rect x="{sx(along) - bw / 2:.1f}" y="{sy(hgt):.1f}" width="{bw:.1f}" height="{sy(0) - sy(hgt):.1f}" '
            f'rx="2" fill="{colour}" fill-opacity="0.6"><title>{escape(name)}: {hgt:.0f} m at {along:.0f} m '
            f'(needs {need:.0f} m){" CONFLICT" if conflict else ""}</title></rect>'
        )
        label = f"{name}{' (conflict)' if conflict else ''}"
        out.append(f'<text x="{sx(along) + 6:.1f}" y="{sy(hgt) - 4:.1f}" fill="{INK}">{escape(label)}</text>')

    n = 60
    pts = " ".join(f"{sx(x_max * i / n):.1f},{sy(altitude_at(x_max * i / n, ac)):.1f}" for i in range(n + 1))
    out.append(f'<polyline points="{sx(0):.1f},{sy(0):.1f} {pts}" fill="none" '
               f'stroke="{CORRIDOR}" stroke-width="2"/>')
    out.append(f'<text x="{sx(fp.corridor_length_m):.1f}" y="{sy(ac.cruise_altitude_m) - 6:.1f}" '
               f'fill="{INK}" text-anchor="middle">cruise {ac.cruise_altitude_m:.0f} m</text>')
    out.append("</svg>")
    return "\n".join(out)
