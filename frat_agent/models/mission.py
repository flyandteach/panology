from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class MissionRequest:
    # ── Location ──────────────────────────────────────────────────────────────
    lat: float
    lon: float
    location_name: str
    nearest_airport_icao: str   # e.g. "KSEA" — used for weather station lookup

    # ── Time window ───────────────────────────────────────────────────────────
    planned_start: datetime
    planned_end: datetime

    # ── Operation parameters ──────────────────────────────────────────────────
    max_altitude_ft_agl: int
    operation_type: str            # "VLOS" | "EVLOS" | "BVLOS"
    population_density: str        # "sparse" | "populated" | "gathering"
    over_people: bool = False
    over_moving_vehicles: bool = False
    is_night: bool = False

    # ── Aircraft ──────────────────────────────────────────────────────────────
    aircraft_make_model: str = ""
    aircraft_weight_lbs: float = 0.0
    aircraft_dimension_m: float = 1.0   # characteristic dimension (wingspan / rotor span)
    aircraft_max_speed_ms: float = 15.0

    # ── Pilot ─────────────────────────────────────────────────────────────────
    pilot_name: str = ""
    pilot_certificate: str = "Part 107"  # "Part 107" | "Part 61" | "student"
    pilot_currency_days: int = 0         # days since last flight of this type
    pilot_night_current: bool = False
    pilot_total_hours: float = 0.0

    # ── External pressures (1 = none, 5 = extreme) ───────────────────────────
    schedule_pressure: int = 1
    client_pressure: int = 1
    financial_pressure: int = 1

    # ── Optional free-text notes ──────────────────────────────────────────────
    notes: str = ""

    # ── Derived ───────────────────────────────────────────────────────────────
    is_bvlos: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_bvlos = self.operation_type == "BVLOS"
        if isinstance(self.planned_start, str):
            self.planned_start = datetime.fromisoformat(self.planned_start)
        if isinstance(self.planned_end, str):
            self.planned_end = datetime.fromisoformat(self.planned_end)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["planned_start"] = self.planned_start.isoformat()
        d["planned_end"]   = self.planned_end.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MissionRequest":
        d = dict(d)
        d["planned_start"] = datetime.fromisoformat(d["planned_start"])
        d["planned_end"]   = datetime.fromisoformat(d["planned_end"])
        d.pop("is_bvlos", None)
        return cls(**d)
