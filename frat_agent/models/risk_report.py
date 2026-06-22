from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional


@dataclass
class WeatherSnapshot:
    station: str
    flight_category: str          # VFR | MVFR | IFR | LIFR
    wind_dir_deg: Optional[int]
    wind_speed_kt: int
    wind_gust_kt: Optional[int]
    visibility_sm: Optional[float]
    ceiling_ft: Optional[int]     # lowest BKN or OVC layer, None if clear
    temp_c: Optional[float]
    raw_metar: str
    taf_summary: str


@dataclass
class NotamItem:
    notam_id: str
    classification: str           # "TFR" | "AIRSPACE" | "OBSTACLE" | "NAV" | "OTHER"
    effective_start: str
    effective_end: str
    text: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    radius_nm: Optional[float] = None


@dataclass
class TfrItem:
    notam_id: str
    name: str
    effective_start: str
    effective_end: str
    min_alt_ft: int
    max_alt_ft: int
    center_lat: float
    center_lon: float
    radius_nm: Optional[float]
    intersects_mission: bool


@dataclass
class LaancData:
    grid_cell_id: str
    authorized_ceiling_ft: int    # 0 means no LAANC authorization available
    facility_name: str
    airspace_class: str           # "B" | "C" | "D" | "E" | "G"


@dataclass
class PaveScore:
    pilot: int         # 1–5
    aircraft: int
    environment: int
    external: int
    average: float
    pilot_factors: list[str]      = field(default_factory=list)
    aircraft_factors: list[str]   = field(default_factory=list)
    environment_factors: list[str]= field(default_factory=list)
    external_factors: list[str]   = field(default_factory=list)
    narrative: str = ""


@dataclass
class SoraScore:
    igrc: int                     # 1–9
    arc: int                      # 1–4 (a=1, b=2, c=3, d=4)
    arc_label: str                # "a" | "b" | "c" | "d"
    sail: int                     # I–VI (stored as 1–6)
    igrc_rationale: str = ""
    arc_rationale: str = ""


@dataclass
class Mitigation:
    dimension: str                # "pilot" | "aircraft" | "environment" | "external" | "sora"
    risk_factor: str
    action: str
    reduces_to: Optional[str]     # risk level after mitigation
    is_hard_stop: bool = False


@dataclass
class RiskReport:
    report_id: str
    generated_at: str
    verdict: str                  # "GO" | "PROCEED_WITH_MITIGATIONS" | "NO_GO"
    verdict_label: str

    mission: dict                 # MissionRequest.to_dict()
    weather: Optional[WeatherSnapshot]
    notams: list[NotamItem]
    tfrs: list[TfrItem]
    laanc: Optional[LaancData]

    pave: PaveScore
    sora: SoraScore
    mitigations: list[Mitigation]

    hard_stops: list[str]         # plain-English hard stop descriptions
    data_warnings: list[str]      # API fetch issues that may affect completeness

    def to_dict(self) -> dict:
        def _clean(obj: Any) -> Any:
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _clean(v) for k, v in asdict(obj).items()}
            if isinstance(obj, list):
                return [_clean(i) for i in obj]
            return obj

        return {
            "report_id":     self.report_id,
            "generated_at":  self.generated_at,
            "verdict":       self.verdict,
            "verdict_label": self.verdict_label,
            "mission":       self.mission,
            "weather":       _clean(self.weather) if self.weather else None,
            "notams":        [_clean(n) for n in self.notams],
            "tfrs":          [_clean(t) for t in self.tfrs],
            "laanc":         _clean(self.laanc) if self.laanc else None,
            "pave":          _clean(self.pave),
            "sora":          _clean(self.sora),
            "mitigations":   [_clean(m) for m in self.mitigations],
            "hard_stops":    self.hard_stops,
            "data_warnings": self.data_warnings,
        }
