"""Input data model for a drone delivery hub design.

Every numeric default in this file is a placeholder chosen so the tool runs out
of the box. None of them describe a specific vendor's aircraft or come from a
regulation. Replace them with OEM data, site measurements and the requirements
of the authority having jurisdiction (AHJ) before relying on any output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields


@dataclass
class AircraftProfile:
    name: str = "Generic small multirotor (placeholder)"
    span_m: float = 1.5  # largest horizontal dimension, rotor tip to rotor tip
    cruise_speed_mps: float = 25.0
    max_range_km: float = 20.0  # round-trip range on one pack, with reserve already removed
    packages_per_sortie: int = 1
    takeoff_pad_time_s: float = 30.0  # pad occupied from lift-off until clear of the pad area
    landing_pad_time_s: float = 45.0  # pad occupied from final approach until on the ground
    delivery_dwell_s: float = 60.0  # hover / lower / release at the customer
    climb_descent_s: float = 60.0  # extra time vs pure cruise for climb, descent and transitions
    battery_mode: str = "swap"  # "swap" (packs swapped and charged off-aircraft) or "onboard"
    pack_energy_wh: float = 500.0
    charge_time_min: float = 45.0  # one pack, empty to flight-ready
    charger_power_kw: float = 1.0  # per charging slot at the plug
    hover_noise_dba: float = 65.0  # measured A-weighted level at reference distance (placeholder)
    noise_ref_distance_m: float = 30.0
    max_wind_mps: float = 12.0  # operating limit, informational
    precip_capable: bool = False  # can the aircraft fly in rain / snow
    night_capable: bool = True


@dataclass
class DemandProfile:
    peak_orders_per_hour: float = 30.0
    daily_orders: float = 250.0
    service_radius_km: float = 8.0
    operating_hours_per_day: float = 14.0
    night_hours_in_window: float = 3.0  # hours of the operating window that are after civil dusk (annual mean)


@dataclass
class SiteProfile:
    width_m: float = 60.0  # along the store frontage
    depth_m: float = 50.0  # away from the store
    nearest_receptor_m: float = 120.0  # distance from hub centre to nearest noise-sensitive property line
    receptor_noise_limit_dba: float = 55.0  # local ordinance or design target at that property line
    receptor_height_m: float = 1.5
    # Climatology: fraction of operating hours in each condition (from local weather records).
    wind_exceedance_frac: float = 0.05  # hours with wind above aircraft limit
    precip_frac: float = 0.08  # hours with measurable precipitation
    snow_ice_frac: float = 0.02  # hours with snow / ice accumulation on surfaces
    extreme_heat_frac: float = 0.03  # hours hot enough to derate charging without conditioning


@dataclass
class DesignRequirements:
    target_pad_wait_s: float = 30.0  # mean wait for a pad that the design should not exceed
    max_pad_utilization: float = 0.7
    fleet_spare_frac: float = 0.15  # extra aircraft for maintenance / AOG
    battery_spare_frac: float = 0.25
    turnaround_on_pad: bool = False  # True = loading/swap happens on the launch pad (baseline nests)
    load_time_s: float = 60.0
    swap_time_s: float = 30.0
    pad_size_factor: float = 2.0  # pad side = factor x aircraft span
    pad_separation_factor: float = 1.0  # clear gap between pad edges = factor x aircraft span
    fence_buffer_factor: float = 3.0  # pad edge to fence = factor x aircraft span
    public_setback_m: float = 10.0  # fence to nearest parking aisle / walkway
    ops_building_depth_m: float = 10.0
    battery_room_separation_m: float = 10.0  # clear distance from battery room to ops building and pads
    battery_room_side_m: float = 6.0
    # Long-term hub features. The parking-lot baseline turns these off.
    covered_loading: bool = True
    heated_pads: bool = True
    heated_pad_w_per_m2: float = 300.0  # placeholder; size with a snow-melt designer
    night_lighting: bool = True
    noise_barrier: bool = True
    barrier_height_m: float = 4.0  # barrier sits on the airside fence
    noise_frequency_hz: float = 500.0  # representative frequency for barrier attenuation
    conditioned_battery_room: bool = True
    battery_fire_suppression: bool = True
    perimeter_fence: bool = True
    hvac_lighting_base_kw: float = 15.0


@dataclass
class HubInputs:
    aircraft: AircraftProfile = field(default_factory=AircraftProfile)
    demand: DemandProfile = field(default_factory=DemandProfile)
    site: SiteProfile = field(default_factory=SiteProfile)
    design: DesignRequirements = field(default_factory=DesignRequirements)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "HubInputs":
        def build(dc, values):
            names = {f.name for f in fields(dc)}
            unknown = set(values) - names
            if unknown:
                raise ValueError(f"Unknown {dc.__name__} fields: {sorted(unknown)}")
            return dc(**values)

        return cls(
            aircraft=build(AircraftProfile, data.get("aircraft", {})),
            demand=build(DemandProfile, data.get("demand", {})),
            site=build(SiteProfile, data.get("site", {})),
            design=build(DesignRequirements, data.get("design", {})),
        )


def parking_lot_baseline(design: DesignRequirements) -> DesignRequirements:
    """The interim parking-lot nest: fence, container, pads, nothing else.

    Pad geometry and sizing targets are kept so the comparison isolates the
    long-term features rather than the pad count.
    """
    values = asdict(design)
    values.update(
        turnaround_on_pad=True,
        covered_loading=False,
        heated_pads=False,
        night_lighting=False,
        noise_barrier=False,
        conditioned_battery_room=False,
        battery_fire_suppression=False,
        battery_room_separation_m=0.0,
        public_setback_m=2.0,
        fence_buffer_factor=1.0,
        ops_building_depth_m=2.5,  # one shipping container
    )
    return DesignRequirements(**values)
