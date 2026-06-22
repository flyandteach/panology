"""
Pure-computation SORA 2.5 scorer.  No LLM call.
Computes iGRC, ARC, and SAIL from mission parameters and airspace data.
"""
from __future__ import annotations

from frat_agent.config import (
    DIM_CLASSES, IGRC_TABLE, SAIL_TABLE, ARC_LABEL,
)
from frat_agent.models import MissionRequest, LaancData, SoraScore


def _dim_index(dim_m: float) -> int:
    for i, upper in enumerate(DIM_CLASSES):
        if dim_m < upper:
            return i
    return len(DIM_CLASSES) - 1


def _compute_igrc(mission: MissionRequest) -> tuple[int, str]:
    density = mission.population_density
    if density not in IGRC_TABLE:
        density = "populated"

    idx  = _dim_index(mission.aircraft_dimension_m)
    igrc = IGRC_TABLE[density][idx]

    # Gatherings of people raise iGRC by +1 if not already maxed
    if mission.over_people and density != "gathering":
        igrc = min(igrc + 1, 9)

    # BVLOS adds +1 (reduced detectability / reaction time)
    if mission.is_bvlos:
        igrc = min(igrc + 1, 9)

    rationale = (
        f"UA char. dim {mission.aircraft_dimension_m} m → size class index {idx}; "
        f"population '{density}'"
        + (" + over people" if mission.over_people else "")
        + (" + BVLOS" if mission.is_bvlos else "")
    )
    return igrc, rationale


def _compute_arc(mission: MissionRequest, laanc: LaancData | None) -> tuple[int, str]:
    """
    Simplified ARC mapping based on airspace class and altitude.
    ARC-a=1, ARC-b=2, ARC-c=3, ARC-d=4
    """
    alt      = mission.max_altitude_ft_agl
    cls      = (laanc.airspace_class if laanc else "G").upper()

    if cls == "G" and alt <= 400:
        arc, note = 1, "Class G ≤ 400 ft AGL → ARC-a"
    elif cls == "G":
        arc, note = 2, "Class G > 400 ft AGL → ARC-b"
    elif cls == "E" and alt <= 400:
        arc, note = 2, "Class E ≤ 400 ft AGL → ARC-b"
    elif cls == "E":
        arc, note = 3, "Class E > 400 ft AGL → ARC-c"
    elif cls in ("D",):
        arc, note = 3, f"Class {cls} airspace → ARC-c"
    elif cls in ("C", "B"):
        arc, note = 4, f"Class {cls} airspace → ARC-d"
    else:
        arc, note = 2, f"Unknown class '{cls}' → defaulting to ARC-b"

    # Night operations in non-Class-G add one ARC level
    if mission.is_night and cls != "G":
        arc = min(arc + 1, 4)
        note += " + night → +1 ARC"

    return arc, note


def _compute_sail(igrc: int, arc: int) -> int:
    igrc_clamped = max(1, min(igrc, 9))
    arc_clamped  = max(1, min(arc, 4))
    row = SAIL_TABLE.get(igrc_clamped, SAIL_TABLE[9])
    return row[arc_clamped - 1]


def score(mission: MissionRequest, laanc: LaancData | None) -> SoraScore:
    igrc, igrc_rationale = _compute_igrc(mission)
    arc,  arc_rationale  = _compute_arc(mission, laanc)
    sail                 = _compute_sail(igrc, arc)

    return SoraScore(
        igrc          = igrc,
        arc           = arc,
        arc_label     = ARC_LABEL.get(arc, "?"),
        sail          = sail,
        igrc_rationale= igrc_rationale,
        arc_rationale = arc_rationale,
    )
