"""Operational availability from site climatology and hub features.

Splits downtime into what the aircraft cannot fly through (wind, and
precipitation for aircraft not rated for it) and what the hub itself causes
(snow on pads, heat-limited charging, no lighting at night, uncovered loading
in rain). Conditions are treated as independent, so the result is an estimate,
not a forecast.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AvailabilityResult:
    aircraft_limited_frac: float  # share of operating hours lost to aircraft limits
    hub_limited_frac: float  # extra share lost to the ground facility
    availability: float
    annual_hours_available: float
    annual_hours_lost_to_hub: float
    causes: dict[str, float]


def assess_availability(
    operating_hours_per_day: float,
    night_hours: float,
    wind_frac: float,
    precip_frac: float,
    snow_frac: float,
    heat_frac: float,
    precip_capable: bool,
    night_capable: bool,
    covered_loading: bool,
    heated_pads: bool,
    night_lighting: bool,
    conditioned_battery_room: bool,
) -> AvailabilityResult:
    night_frac = min(night_hours / operating_hours_per_day, 1.0) if operating_hours_per_day else 0.0

    aircraft_up = 1 - wind_frac
    if not precip_capable:
        aircraft_up *= 1 - precip_frac
    if not night_capable:
        aircraft_up *= 1 - night_frac

    causes = {}
    if precip_capable and not covered_loading:
        # Aircraft can fly but staff cannot load packages or swap packs in the open.
        causes["uncovered loading in precipitation"] = precip_frac
    if not heated_pads:
        causes["snow / ice on pads"] = snow_frac
    if not conditioned_battery_room:
        causes["heat-limited charging"] = heat_frac
    if night_capable and not night_lighting:
        causes["no ground lighting after dark"] = night_frac

    hub_up = 1.0
    for frac in causes.values():
        hub_up *= 1 - frac
    availability = aircraft_up * hub_up
    annual = operating_hours_per_day * 365
    return AvailabilityResult(
        aircraft_limited_frac=1 - aircraft_up,
        hub_limited_frac=aircraft_up - availability,
        availability=availability,
        annual_hours_available=annual * availability,
        annual_hours_lost_to_hub=annual * (aircraft_up - availability),
        causes=causes,
    )
