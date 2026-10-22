"""Throughput sizing: sortie timing, fleet, pads, batteries, chargers, power.

Pads are sized with an M/M/c (Erlang C) queue. That treats pad requests as
random arrivals with exponentially distributed occupancy, which is pessimistic
for a dispatcher that schedules departures but reasonable for arrivals, which
the hub does not control.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import AircraftProfile, DemandProfile, DesignRequirements


def mean_trip_distance_km(service_radius_km: float) -> float:
    """Mean distance from the centre of a disc to a point spread uniformly over it is 2R/3."""
    return 2.0 * service_radius_km / 3.0


def erlang_c(servers: int, offered_load: float) -> float:
    """Probability an arrival has to wait in an M/M/c queue. offered_load = lambda / mu (Erlangs)."""
    if servers <= 0:
        return 1.0
    if offered_load >= servers:
        return 1.0
    term = 1.0
    total = 1.0
    for k in range(1, servers):
        term *= offered_load / k
        total += term
    term *= offered_load / servers
    top = term * servers / (servers - offered_load)
    return top / (total + top)


def mean_wait_s(servers: int, arrivals_per_s: float, service_s: float) -> float:
    if arrivals_per_s <= 0:
        return 0.0
    load = arrivals_per_s * service_s
    if load >= servers:
        return math.inf
    return erlang_c(servers, load) * service_s / (servers - load)


def pads_required(arrivals_per_s: float, service_s: float, target_wait_s: float, max_util: float) -> int:
    if arrivals_per_s <= 0:
        return 1
    load = arrivals_per_s * service_s
    c = max(1, math.ceil(load / max_util))
    while mean_wait_s(c, arrivals_per_s, service_s) > target_wait_s:
        c += 1
    return c


@dataclass
class CapacityResult:
    sorties_per_hour: float
    mean_trip_km: float
    flight_time_s: float
    ground_turnaround_s: float
    cycle_time_s: float
    range_ok: bool
    aircraft_required: int
    pad_events_per_hour: float
    pad_service_s: float
    pads_required: int
    pad_utilization: float
    pad_mean_wait_s: float
    batteries_required: int
    charging_slots: int
    stored_energy_kwh: float
    charging_kw: float


def size_capacity(ac: AircraftProfile, demand: DemandProfile, design: DesignRequirements) -> CapacityResult:
    sorties_h = demand.peak_orders_per_hour / max(ac.packages_per_sortie, 1)
    trip_km = mean_trip_distance_km(demand.service_radius_km)
    flight_s = 2 * trip_km * 1000 / ac.cruise_speed_mps + ac.delivery_dwell_s + ac.climb_descent_s
    range_ok = 2 * demand.service_radius_km <= ac.max_range_km

    charge_s = ac.charge_time_min * 60
    if ac.battery_mode == "swap":
        ground_s = design.load_time_s + design.swap_time_s
    elif ac.battery_mode == "onboard":
        ground_s = design.load_time_s + charge_s
    else:
        raise ValueError(f"battery_mode must be 'swap' or 'onboard', got {ac.battery_mode!r}")

    cycle_s = flight_s + ground_s + ac.takeoff_pad_time_s + ac.landing_pad_time_s
    sorties_s = sorties_h / 3600
    # Little's law: aircraft busy = arrival rate x time in system.
    aircraft = math.ceil(sorties_s * cycle_s * (1 + design.fleet_spare_frac))

    if design.turnaround_on_pad:
        # Land, load / swap / charge, and take off without leaving the pad.
        events_s = sorties_s
        service_s = ac.landing_pad_time_s + ground_s + ac.takeoff_pad_time_s
    else:
        # Separate launch and recovery events; aircraft taxis or is carried to a loading bay.
        events_s = 2 * sorties_s
        service_s = (ac.takeoff_pad_time_s + ac.landing_pad_time_s) / 2
    pads = pads_required(events_s, service_s, design.target_pad_wait_s, design.max_pad_utilization)
    util = events_s * service_s / pads

    if ac.battery_mode == "swap":
        # Each pack cycles: on the aircraft for a sortie, then on a charger.
        pack_cycle_s = cycle_s + charge_s
        batteries = math.ceil(sorties_s * pack_cycle_s * (1 + design.battery_spare_frac))
        slots = math.ceil(sorties_s * charge_s * (1 + design.battery_spare_frac))
    else:
        batteries = aircraft
        slots = pads if design.turnaround_on_pad else math.ceil(sorties_s * charge_s * (1 + design.fleet_spare_frac))

    return CapacityResult(
        sorties_per_hour=sorties_h,
        mean_trip_km=trip_km,
        flight_time_s=flight_s,
        ground_turnaround_s=ground_s,
        cycle_time_s=cycle_s,
        range_ok=range_ok,
        aircraft_required=aircraft,
        pad_events_per_hour=events_s * 3600,
        pad_service_s=service_s,
        pads_required=pads,
        pad_utilization=util,
        pad_mean_wait_s=mean_wait_s(pads, events_s, service_s),
        batteries_required=batteries,
        charging_slots=slots,
        stored_energy_kwh=batteries * ac.pack_energy_wh / 1000,
        charging_kw=slots * ac.charger_power_kw,
    )
