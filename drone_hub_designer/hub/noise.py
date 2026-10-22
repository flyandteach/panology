"""Screening-level noise estimate at the nearest noise-sensitive receptor.

Uses spherical spreading from a point source (-6 dB per doubling of distance),
energy addition for pads operating at once, and the Maekawa / Kurze-Anderson
thin-barrier approximation. Ground effect, air absorption, reflections and
tonal penalties are ignored. This is for comparing layouts, not for permitting:
an acoustic consultant's model with the aircraft's measured spectrum is needed
for that.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SPEED_OF_SOUND_MPS = 343.0
BARRIER_CAP_DB = 20.0  # practical upper limit for a single thin barrier
PAD_HOVER_HEIGHT_M = 3.0  # aircraft height while lifting off / landing


def level_at_distance(level_ref_db: float, ref_m: float, distance_m: float) -> float:
    return level_ref_db - 20 * math.log10(max(distance_m, 0.1) / ref_m)


def distance_to_level(level_ref_db: float, ref_m: float, target_db: float) -> float:
    return ref_m * 10 ** ((level_ref_db - target_db) / 20)


def combine_sources(level_db: float, count: int) -> float:
    return level_db + 10 * math.log10(max(count, 1))


def barrier_attenuation_db(
    source_to_barrier_m: float,
    barrier_to_receiver_m: float,
    barrier_height_m: float,
    source_height_m: float,
    receiver_height_m: float,
    frequency_hz: float,
) -> float:
    a, b = source_to_barrier_m, barrier_to_receiver_m
    line_of_sight_height = source_height_m + (receiver_height_m - source_height_m) * a / (a + b)
    if barrier_height_m <= line_of_sight_height:
        # Barrier does not break line of sight; take no credit (conservative).
        return 0.0
    over = math.hypot(a, barrier_height_m - source_height_m) + math.hypot(b, barrier_height_m - receiver_height_m)
    direct = math.hypot(a + b, source_height_m - receiver_height_m)
    fresnel = 2 * (over - direct) * frequency_hz / SPEED_OF_SOUND_MPS
    return min(10 * math.log10(3 + 20 * fresnel), BARRIER_CAP_DB)


@dataclass
class NoiseResult:
    simultaneous_pads: int
    source_level_ref_db: float
    level_at_receptor_db: float
    barrier_attenuation_db: float
    level_with_barrier_db: float
    limit_db: float
    meets_limit: bool
    distance_to_limit_m: float  # unshielded distance at which the limit is met
    events_per_hour_at_pads: float


def assess_noise(
    hover_noise_dba: float,
    ref_m: float,
    receptor_m: float,
    limit_db: float,
    simultaneous_pads: int,
    pad_events_per_hour: float,
    barrier: bool,
    barrier_height_m: float,
    barrier_distance_m: float,
    receiver_height_m: float,
    frequency_hz: float,
) -> NoiseResult:
    source = combine_sources(hover_noise_dba, simultaneous_pads)
    at_receptor = level_at_distance(source, ref_m, receptor_m)
    atten = 0.0
    if barrier and barrier_distance_m < receptor_m:
        atten = barrier_attenuation_db(
            barrier_distance_m,
            receptor_m - barrier_distance_m,
            barrier_height_m,
            PAD_HOVER_HEIGHT_M,
            receiver_height_m,
            frequency_hz,
        )
    shielded = at_receptor - atten
    return NoiseResult(
        simultaneous_pads=simultaneous_pads,
        source_level_ref_db=source,
        level_at_receptor_db=at_receptor,
        barrier_attenuation_db=atten,
        level_with_barrier_db=shielded,
        limit_db=limit_db,
        meets_limit=shielded <= limit_db,
        distance_to_limit_m=distance_to_level(source, ref_m, limit_db),
        events_per_hour_at_pads=pad_events_per_hour,
    )
