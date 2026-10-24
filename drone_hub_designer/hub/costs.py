"""Bill of quantities, capital and operating cost, and cost per delivery.

Quantities come from the design (pads, aircraft, packs, building and apron
areas, fence and barrier lengths, peak power). Unit costs come from the user:
the tool ships with no prices except the electricity rate, because no
verifiable price could be found for the rest. A line with a zero unit cost
is reported as "not entered", so a missing price is never mistaken for a
free item.

Capital is annualised with the capital recovery factor
r(1+r)^n / ((1+r)^n - 1), using separate lives for aircraft and for fixed
infrastructure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .models import CostInputs


@dataclass
class CostLine:
    group: str  # "capital" or "operating"
    item: str
    quantity: float
    unit: str
    unit_cost: float
    life: str = ""  # "aircraft" or "infrastructure" for capital lines

    @property
    def total(self) -> float:
        return self.quantity * self.unit_cost

    @property
    def entered(self) -> bool:
        return self.unit_cost > 0 or self.quantity == 0


@dataclass
class CostResult:
    lines: list[CostLine]
    capital_total: float
    annualised_capital: float
    operating_annual: float
    annual_deliveries: float
    cost_per_delivery: float
    missing: list[str] = field(default_factory=list)


def capital_recovery_factor(rate: float, years: float) -> float:
    if years <= 0:
        return 0.0
    if rate <= 0:
        return 1.0 / years
    g = (1 + rate) ** years
    return rate * g / (g - 1)


def estimate_costs(design, uc: CostInputs) -> CostResult:
    """design is a HubDesign; imported loosely to avoid a circular import."""
    inp = design.inputs
    ac, d, demand, site = inp.aircraft, inp.design, inp.demand, inp.site
    cap, lay, avail = design.capacity, design.layout, design.availability

    apron = lay.get("Airside apron (fenced)")
    building = next(r for r in lay.rects if r.kind == "building")
    battery_room = lay.get("Battery charging / storage room")
    pads = cap.pads_required
    pad_area = pads * lay.pad_side_m**2
    barrier_len = 2 * apron.h + apron.w  # three sides; the building closes the fourth
    swap = ac.battery_mode == "swap"

    lines = [
        CostLine("capital", "Aircraft", cap.aircraft_required, "each", uc.aircraft_unit_cost, "aircraft"),
        CostLine("capital", "Spare battery packs", cap.batteries_required if swap else 0, "each",
                 uc.battery_pack_cost, "aircraft"),
        CostLine("capital", "Charging slots", cap.charging_slots, "each", uc.charger_cost_per_slot, "infrastructure"),
        CostLine("capital", "Pads / docks", pads, "each", uc.pad_or_dock_cost, "infrastructure"),
        CostLine("capital", "Apron paving and site work", apron.area, "m²", uc.site_work_cost_per_m2,
                 "infrastructure"),
    ]
    if d.covered_loading:
        lines.append(CostLine("capital", "Operations building", building.area, "m²", uc.building_cost_per_m2,
                              "infrastructure"))
    else:
        lines.append(CostLine("capital", "Storage container", 1, "lump", uc.container_cost, "infrastructure"))
    lines.append(CostLine("capital", "Battery room", battery_room.area, "m²", uc.battery_room_cost_per_m2,
                          "infrastructure"))
    if d.perimeter_fence:
        lines.append(CostLine("capital", "Perimeter fence", 2 * (apron.w + apron.h), "m", uc.fence_cost_per_m,
                              "infrastructure"))
    if d.noise_barrier:
        lines.append(CostLine("capital", "Noise barrier", barrier_len * d.barrier_height_m, "m²",
                              uc.barrier_cost_per_m2, "infrastructure"))
    if d.heated_pads:
        lines.append(CostLine("capital", "Heated pads", pad_area, "m²", uc.heated_pad_cost_per_m2, "infrastructure"))
    if d.night_lighting:
        lines.append(CostLine("capital", "Apron and loading lighting", 1, "lump", uc.lighting_cost, "infrastructure"))
    if d.battery_fire_suppression:
        lines.append(CostLine("capital", "Battery-room detection / suppression", 1, "lump", uc.fire_suppression_cost,
                              "infrastructure"))
    if d.conditioned_battery_room:
        lines.append(CostLine("capital", "Battery-room HVAC", 1, "lump", uc.battery_hvac_cost, "infrastructure"))
    lines.append(CostLine("capital", "Electrical service", design.peak_power_kw, "kW", uc.electrical_service_cost_per_kw,
                          "infrastructure"))

    # Operating
    op_hours = demand.operating_hours_per_day * 365
    annual_deliveries = demand.daily_orders * 365 * avail.availability
    annual_sorties = annual_deliveries / max(ac.packages_per_sortie, 1)
    # Conservative: every sortie is charged as one full pack, through the charger losses.
    sortie_kwh = ac.pack_energy_wh / 1000 / max(uc.charger_efficiency, 0.01)
    heat_kw = pads * lay.pad_side_m**2 * d.heated_pad_w_per_m2 / 1000 if d.heated_pads else 0.0
    energy_kwh = (annual_sorties * sortie_kwh
                  + d.hvac_lighting_base_kw * op_hours
                  + heat_kw * site.snow_ice_frac * op_hours)
    sorties_peak_s = cap.sorties_per_hour / 3600
    handler_load = sorties_peak_s * d.load_time_s + (sorties_peak_s * d.swap_time_s if swap else 0.0)
    ground_crew = math.ceil(handler_load / max(uc.crew_utilization, 0.05)) if handler_load else 0
    staff = ground_crew + uc.other_staff_per_shift
    pack_count = cap.batteries_required if swap else cap.aircraft_required

    lines += [
        CostLine("operating", "Electricity", energy_kwh, "kWh/yr", uc.electricity_price_per_kwh),
        CostLine("operating", "Demand charges", design.peak_power_kw * 12, "kW-month/yr", uc.demand_charge_per_kw_month),
        CostLine("operating", f"Staff ({ground_crew} ground crew + {uc.other_staff_per_shift} other per shift)",
                 staff * op_hours, "staff-h/yr", uc.staff_cost_per_hour),
        CostLine("operating", "Aircraft maintenance", cap.aircraft_required * uc.aircraft_unit_cost,
                 "$ of fleet value", uc.aircraft_maintenance_frac_per_year),
        CostLine("operating", "Battery pack replacement",
                 annual_sorties / max(uc.battery_cycle_life, 1) if pack_count else 0, "packs/yr",
                 uc.battery_pack_cost),
        CostLine("operating", "Site lease", (apron.area + building.area), "m²·yr", uc.site_lease_per_m2_year),
    ]

    capital_total = sum(line.total for line in lines if line.group == "capital")
    crf_ac = capital_recovery_factor(uc.discount_rate, uc.aircraft_life_years)
    crf_inf = capital_recovery_factor(uc.discount_rate, uc.infrastructure_life_years)
    annualised = sum(line.total * (crf_ac if line.life == "aircraft" else crf_inf)
                     for line in lines if line.group == "capital")
    operating = sum(line.total for line in lines if line.group == "operating")
    missing = [line.item for line in lines if not line.entered]

    return CostResult(
        lines=lines,
        capital_total=capital_total,
        annualised_capital=annualised,
        operating_annual=operating,
        annual_deliveries=annual_deliveries,
        cost_per_delivery=(annualised + operating) / annual_deliveries if annual_deliveries else math.inf,
        missing=missing,
    )
