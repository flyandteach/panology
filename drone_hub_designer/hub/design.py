"""Runs every model for one set of inputs and grades the result.

The pass/fail criteria in CRITERIA are this tool's defaults, not regulations.
They exist so two designs can be compared on the same terms; edit them to
match the operator's and the AHJ's requirements.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace

from .capacity import CapacityResult, size_capacity
from .fire import FireResult, assess_fire
from .layout import Layout, plan_layout
from .models import HubInputs, parking_lot_baseline
from .noise import NoiseResult, assess_noise
from .weather import AvailabilityResult, assess_availability

CRITERIA = {
    "min_public_setback_m": 10.0,
    "min_fence_buffer_spans": 2.0,
    "min_battery_separation_m": 3.0,
    "min_availability": 0.85,
    "max_hub_downtime_frac": 0.02,
}


@dataclass
class Check:
    category: str
    name: str
    passed: bool
    detail: str


@dataclass
class HubDesign:
    inputs: HubInputs
    capacity: CapacityResult
    layout: Layout
    noise: NoiseResult
    fire: FireResult
    availability: AvailabilityResult
    peak_power_kw: float
    checks: list[Check]

    def scores(self) -> dict[str, float]:
        cats: dict[str, list[bool]] = {}
        for c in self.checks:
            cats.setdefault(c.category, []).append(c.passed)
        return {k: sum(v) / len(v) for k, v in cats.items()}

    def summary(self) -> dict:
        return {
            "capacity": asdict(self.capacity),
            "layout": {
                "fits": self.layout.fits,
                "required_w_m": round(self.layout.required_w, 1),
                "required_d_m": round(self.layout.required_d, 1),
                "pad_side_m": self.layout.pad_side_m,
                "grid": f"{self.layout.cols} x {self.layout.rows}",
            },
            "noise": asdict(self.noise),
            "fire": asdict(self.fire),
            "availability": asdict(self.availability),
            "peak_power_kw": round(self.peak_power_kw, 1),
            "scores": self.scores(),
            "checks": [asdict(c) for c in self.checks],
        }


def evaluate(inputs: HubInputs) -> HubDesign:
    ac, demand, site, d = inputs.aircraft, inputs.demand, inputs.site, inputs.design
    cap = size_capacity(ac, demand, d)

    layout = plan_layout(
        site.width_m,
        site.depth_m,
        cap.pads_required,
        ac.span_m,
        d.pad_size_factor,
        d.pad_separation_factor,
        d.fence_buffer_factor,
        d.public_setback_m,
        d.ops_building_depth_m,
        d.battery_room_side_m,
        d.battery_room_separation_m,
        d.noise_barrier,
        "Operations building (covered loading)" if d.covered_loading else "Storage container (open-air loading)",
    )

    busy_pads = max(1, math.ceil(cap.pad_events_per_hour * cap.pad_service_s / 3600))
    noise = assess_noise(
        ac.hover_noise_dba,
        ac.noise_ref_distance_m,
        site.nearest_receptor_m,
        site.receptor_noise_limit_dba,
        busy_pads,
        cap.pad_events_per_hour,
        d.noise_barrier,
        d.barrier_height_m,
        layout.barrier_to_pad_m,
        site.receptor_height_m,
        d.noise_frequency_hz,
    )

    fire = assess_fire(
        cap.stored_energy_kwh,
        d.battery_room_separation_m,
        d.battery_fire_suppression,
        d.conditioned_battery_room,
        CRITERIA["min_battery_separation_m"],
    )

    avail = assess_availability(
        demand.operating_hours_per_day,
        demand.night_hours_in_window,
        site.wind_exceedance_frac,
        site.precip_frac,
        site.snow_ice_frac,
        site.extreme_heat_frac,
        ac.precip_capable,
        ac.night_capable,
        d.covered_loading,
        d.heated_pads,
        d.night_lighting,
        d.conditioned_battery_room,
    )

    pad_heat_kw = 0.0
    if d.heated_pads:
        pad_heat_kw = cap.pads_required * layout.pad_side_m**2 * d.heated_pad_w_per_m2 / 1000
    peak_kw = cap.charging_kw + d.hvac_lighting_base_kw + pad_heat_kw

    checks = _checks(inputs, cap, layout, noise, fire, avail)
    return HubDesign(inputs, cap, layout, noise, fire, avail, peak_kw, checks)


def _checks(inputs, cap, layout, noise, fire, avail) -> list[Check]:
    ac, demand, d = inputs.aircraft, inputs.demand, inputs.design
    c = CRITERIA
    return [
        Check("Throughput", "Service radius within aircraft range", cap.range_ok,
              f"Round trip to the edge is {2 * demand.service_radius_km:.1f} km; usable range {ac.max_range_km:.1f} km."),
        Check("Throughput", "Pad wait within target", cap.pad_mean_wait_s <= d.target_pad_wait_s,
              f"{cap.pads_required} pads at {cap.pad_utilization:.0%} utilisation, mean wait {cap.pad_mean_wait_s:.0f} s."),
        Check("Throughput", "Layout fits the site", layout.fits,
              f"Needs {layout.required_w:.0f} x {layout.required_d:.0f} m; site is "
              f"{layout.site_w:.0f} x {layout.site_d:.0f} m."),
        Check("Throughput", "Loading off the launch pads", not d.turnaround_on_pad,
              "Loading and battery swaps on the pad tie up a pad for the whole turnaround."),
        Check("Safety", "Public setback from cars and pedestrians", d.public_setback_m >= c["min_public_setback_m"],
              f"{d.public_setback_m:.0f} m from fence to parking/walkways (criterion {c['min_public_setback_m']:.0f} m)."),
        Check("Safety", "Pad-to-fence buffer", d.fence_buffer_factor >= c["min_fence_buffer_spans"],
              f"{d.fence_buffer_factor * ac.span_m:.1f} m ({d.fence_buffer_factor:g} aircraft spans; "
              f"criterion {c['min_fence_buffer_spans']:g})."),
        Check("Safety", "Perimeter fence", d.perimeter_fence, "Keeps the public out of the rotor area."),
        Check("Safety", "Staff work away from active pads", not d.turnaround_on_pad,
              "Staff loading on a pad work next to aircraft landing on adjacent pads."),
        Check("Weather", "Covered loading and swaps", d.covered_loading, "Ground crew and packages under cover."),
        Check("Weather", "Snow/ice-free pads", d.heated_pads, "Heated pads remove manual clearing downtime."),
        Check("Weather", "Hub-caused downtime", avail.hub_limited_frac <= c["max_hub_downtime_frac"],
              f"Facility causes {avail.hub_limited_frac:.1%} of operating hours lost "
              f"({avail.annual_hours_lost_to_hub:.0f} h/yr)."),
        Check("Weather", "Overall availability", avail.availability >= c["min_availability"],
              f"{avail.availability:.1%} of operating hours flyable (criterion {c['min_availability']:.0%})."),
        Check("Night", "Ground lighting", d.night_lighting, "Apron, pad and loading lighting for after-dark ops."),
        Check("Night", "Aircraft night capable", ac.night_capable, "Aircraft limitation, not the hub's."),
        Check("Noise", "Meets receptor limit", noise.meets_limit,
              f"{noise.level_with_barrier_db:.1f} dBA at the receptor vs {noise.limit_db:.0f} dBA limit "
              f"({noise.simultaneous_pads} pad(s) active, barrier {noise.barrier_attenuation_db:.1f} dB)."),
        Check("Noise", "Noise barrier", d.noise_barrier, "Shields lift-off and landing, not overflight."),
        Check("Fire", "Battery area separated", fire.separated,
              f"{d.battery_room_separation_m:.0f} m clear (criterion {c['min_battery_separation_m']:.0f} m)."),
        Check("Fire", "Detection / suppression", fire.suppression, "Battery area protection."),
        Check("Fire", "Conditioned battery area", fire.conditioned, "Temperature-controlled charging."),
    ]


def compare_with_baseline(inputs: HubInputs) -> tuple[HubDesign, HubDesign]:
    """Returns (proposed, parking-lot baseline) for the same aircraft, demand and site."""
    baseline_inputs = replace(inputs, design=parking_lot_baseline(inputs.design))
    return evaluate(inputs), evaluate(baseline_inputs)
