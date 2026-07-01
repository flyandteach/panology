"""Data models shared across the parcel lookup agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class GeocodeResult:
    found: bool
    input_address: str
    matched_address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    county_fips: Optional[str] = None
    county_name: Optional[str] = None
    state_fips: Optional[str] = None
    state_abbr: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Attempt:
    strategy: str
    detail: str
    success: bool


@dataclass
class PLSSDescription:
    raw_text: str
    section: int
    township_number: int
    township_dir: str  # "N" | "S"
    range_number: int
    range_dir: str  # "E" | "W"
    meridian: str = ""
    aliquot_parts: list[str] = field(default_factory=list)  # e.g. ["SW", "NE"], finest-first


@dataclass
class PLSSResult:
    found: bool
    description: PLSSDescription
    lat: Optional[float] = None
    lon: Optional[float] = None
    section_geometry: Optional[dict] = None
    confidence: Optional[str] = None
    source_service: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ExtractedLocation:
    """Best-effort location description pulled out of a document."""
    address: Optional[str] = None
    plss: Optional[PLSSDescription] = None
    apn: Optional[str] = None
    county_hint: Optional[str] = None
    state_hint: Optional[str] = None
    raw_text_excerpt: Optional[str] = None


@dataclass
class AirportDistance:
    ident: str
    name: str
    lat: float
    lon: float
    distance_nm: float
    distance_mi: float
    city: Optional[str] = None
    state: Optional[str] = None


@dataclass
class SiteReport:
    found: bool
    extracted: Optional[ExtractedLocation] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    location_source: Optional[str] = None  # "address" | "plss" | "apn"
    location_confidence: Optional[str] = None
    parcel: Optional["ParcelResult"] = None
    plss_result: Optional[PLSSResult] = None
    nearest_airports: list[AirportDistance] = field(default_factory=list)
    airport_data_is_public_use_verified: bool = False
    attempts: list[Attempt] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class ParcelResult:
    found: bool
    apn: Optional[str] = None
    owner_name: Optional[str] = None
    situs_address: Optional[str] = None
    legal_description: Optional[str] = None
    area_acres: Optional[float] = None
    area_sqft: Optional[float] = None
    geometry: Optional[dict] = None  # GeoJSON geometry
    county_name: Optional[str] = None
    state_abbr: Optional[str] = None
    source_service: Optional[str] = None
    source_layer_name: Optional[str] = None
    strategy_used: Optional[str] = None
    confidence: str = "none"  # "high" | "medium" | "low" | "none"
    raw_attributes: dict = field(default_factory=dict)
    geocode: Optional[GeocodeResult] = None
    attempts: list[Attempt] = field(default_factory=list)
    error: Optional[str] = None
