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
    reference_id: str = "generic"  # key into hub.aircraft_library.LIBRARY
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
    cruise_altitude_m: float = 50.0
    vertical_climb_m: float = 15.0  # straight-up climb before moving off the pad
    climb_rate_mps: float = 3.0
    climb_ground_speed_mps: float = 8.0  # horizontal speed while climbing to cruise
    launch_infrastructure: str = "ground pad"  # informational: "charging pad", "dock", ...
    delivery_method: str = "unspecified"  # informational
    receptor_setback_m: float = 0.0  # minimum distance to noise-sensitive areas from FAA EAs; 0 = none known


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
class Obstacle:
    name: str
    bearing_deg: float  # compass bearing from the hub centre
    distance_m: float
    height_m: float  # above hub ground level
    width_m: float = 10.0


@dataclass
class SensitiveZone:
    name: str
    kind: str  # "people", "residential", "school", "road", ...
    bearing_from_deg: float  # sector, clockwise from this bearing...
    bearing_to_deg: float  # ...to this one
    inner_m: float
    outer_m: float
    min_overflight_m: float  # aircraft should be at least this high over the zone


def _default_obstacles() -> list[Obstacle]:
    return [
        Obstacle("Store building", 180.0, 80.0, 10.0, 100.0),
        Obstacle("Parking-lot light poles", 240.0, 50.0, 12.0, 30.0),
        Obstacle("Tree line", 90.0, 90.0, 18.0, 60.0),
    ]


def _default_zones() -> list[SensitiveZone]:
    return [
        SensitiveZone("Parking lot and store entrance", "people", 120.0, 250.0, 0.0, 150.0, 30.0),
        SensitiveZone("Residential neighbourhood", "residential", 20.0, 110.0, 120.0, 2000.0, 45.0),
    ]


@dataclass
class AirspaceProfile:
    """The hub's surroundings, for laying out departure and arrival corridors.

    Bearings are compass degrees from the hub centre (0 = north, 90 = east).
    All defaults are an invented example site, not real data.
    """

    store_bearing_deg: float = 180.0  # direction from the hub to the store
    obstacles: list[Obstacle] = field(default_factory=_default_obstacles)
    zones: list[SensitiveZone] = field(default_factory=_default_zones)
    obstacle_clearance_m: float = 10.0  # vertical margin over obstacles (design choice)
    corridor_half_width_m: float = 15.0
    min_corridor_separation_deg: float = 30.0
    min_corridors: int = 2
    movement_spacing_s: float = 30.0  # minimum time between aircraft in the same corridor
    max_corridor_utilization: float = 0.6
    heading_step_deg: float = 5.0

    def __post_init__(self):
        self.obstacles = [o if isinstance(o, Obstacle) else Obstacle(**o) for o in self.obstacles]
        self.zones = [z if isinstance(z, SensitiveZone) else SensitiveZone(**z) for z in self.zones]


@dataclass
class CostInputs:
    """Unit costs. Zero means "not entered", not free; only the electricity rate has a default.

    The electricity default is the US commercial-sector average for January-June 2026,
    13.86 cents/kWh, from EIA Electric Power Monthly Table 5.6.B as reported by a secondary
    source (startbusinessbystate.com); use your utility tariff instead.
    """

    aircraft_unit_cost: float = 0.0
    battery_pack_cost: float = 0.0
    charger_cost_per_slot: float = 0.0
    pad_or_dock_cost: float = 0.0
    site_work_cost_per_m2: float = 0.0
    building_cost_per_m2: float = 0.0
    container_cost: float = 0.0
    battery_room_cost_per_m2: float = 0.0
    fence_cost_per_m: float = 0.0
    barrier_cost_per_m2: float = 0.0
    heated_pad_cost_per_m2: float = 0.0
    lighting_cost: float = 0.0
    fire_suppression_cost: float = 0.0
    battery_hvac_cost: float = 0.0
    electrical_service_cost_per_kw: float = 0.0
    electricity_price_per_kwh: float = 0.1386
    demand_charge_per_kw_month: float = 0.0
    staff_cost_per_hour: float = 0.0
    other_staff_per_shift: int = 1  # supervisor / remote pilot on site, beyond ground crew
    crew_utilization: float = 0.6  # share of a crew member's time spent loading / swapping
    aircraft_maintenance_frac_per_year: float = 0.0
    battery_cycle_life: float = 500.0  # placeholder; use the pack supplier's rating
    charger_efficiency: float = 0.9  # placeholder
    site_lease_per_m2_year: float = 0.0
    discount_rate: float = 0.08  # placeholder; use your cost of capital
    aircraft_life_years: float = 5.0  # placeholder
    infrastructure_life_years: float = 20.0  # placeholder


@dataclass
class HubInputs:
    aircraft: AircraftProfile = field(default_factory=AircraftProfile)
    demand: DemandProfile = field(default_factory=DemandProfile)
    site: SiteProfile = field(default_factory=SiteProfile)
    design: DesignRequirements = field(default_factory=DesignRequirements)
    airspace: AirspaceProfile = field(default_factory=AirspaceProfile)
    costs: CostInputs = field(default_factory=CostInputs)

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

        aircraft = dict(data.get("aircraft", {}))
        ref = aircraft.get("reference_id")
        if ref:
            # Fields not given explicitly come from the reference aircraft.
            from .aircraft_library import LIBRARY, profile_for

            if ref not in LIBRARY:
                raise ValueError(f"Unknown reference aircraft {ref!r}; choose from {sorted(LIBRARY)}")
            build(AircraftProfile, aircraft)  # validate field names
            aircraft = asdict(profile_for(ref, **{k: v for k, v in aircraft.items() if k != "reference_id"}))

        return cls(
            aircraft=build(AircraftProfile, aircraft),
            demand=build(DemandProfile, data.get("demand", {})),
            site=build(SiteProfile, data.get("site", {})),
            design=build(DesignRequirements, data.get("design", {})),
            airspace=build(AirspaceProfile, data.get("airspace", {})),
            costs=build(CostInputs, data.get("costs", {})),
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
