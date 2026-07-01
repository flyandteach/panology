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
