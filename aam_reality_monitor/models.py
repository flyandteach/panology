"""Dataclass schemas and validation helpers for persisted records."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from .config import VALID_CLAIM_STATUS, VALID_EVIDENCE_CATEGORIES, VALID_SOURCE_TYPES


def _require(value: Any, field_name: str) -> None:
    if value is None or value == "":
        raise ValueError(f"{field_name} is required")


def _validate_date(value: str, field_name: str) -> None:
    _require(value, field_name)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _validate_score(value: int, field_name: str) -> None:
    if not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError(f"{field_name} must be an integer from 1 to 5")


@dataclass(slots=True)
class OEMProfile:
    oem_id: str
    name: str
    country: str
    aircraft: list[str] = field(default_factory=list)
    company_type: str = "private"
    ticker: str | None = None
    regulators: list[str] = field(default_factory=list)
    website: str = ""
    notes: str = ""

    def validate(self) -> None:
        _require(self.oem_id, "oem_id")
        _require(self.name, "name")
        _require(self.country, "country")
        if not isinstance(self.aircraft, list):
            raise ValueError("aircraft must be a list")
        if not isinstance(self.regulators, list):
            raise ValueError("regulators must be a list")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OEMProfile":
        obj = cls(**data)
        obj.validate()
        return obj


@dataclass(slots=True)
class EvidenceRecord:
    evidence_id: str
    oem_id: str
    date_observed: str
    event_date: str
    category: str
    source_type: str
    source_name: str
    source_url: str = ""
    title: str = ""
    summary: str = ""
    evidence_strength: int = 1
    reliability: int = 1
    status: str = "unverified"
    notes: str = ""

    def validate(self) -> None:
        _require(self.evidence_id, "evidence_id")
        _require(self.oem_id, "oem_id")
        _validate_date(self.date_observed, "date_observed")
        _validate_date(self.event_date, "event_date")
        if self.category not in VALID_EVIDENCE_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(VALID_EVIDENCE_CATEGORIES)}")
        if self.source_type not in VALID_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}")
        _require(self.source_name, "source_name")
        _validate_score(self.evidence_strength, "evidence_strength")
        _validate_score(self.reliability, "reliability")

    def weighted_value(self) -> float:
        return (self.evidence_strength + self.reliability) / 10

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRecord":
        obj = cls(**data)
        obj.validate()
        return obj


@dataclass(slots=True)
class ClaimRecord:
    claim_id: str
    oem_id: str
    claim_date: str
    claim_source: str
    claim_text: str
    claim_category: str
    specificity: str = "medium"
    verifiability: str = "medium"
    supporting_evidence_ids: list[str] = field(default_factory=list)
    contradicting_evidence_ids: list[str] = field(default_factory=list)
    claim_status: str = "unverified"
    claim_reality_score: float | None = None
    notes: str = ""

    def validate(self) -> None:
        _require(self.claim_id, "claim_id")
        _require(self.oem_id, "oem_id")
        _validate_date(self.claim_date, "claim_date")
        _require(self.claim_text, "claim_text")
        if self.claim_category not in VALID_EVIDENCE_CATEGORIES:
            raise ValueError(f"claim_category must be one of {sorted(VALID_EVIDENCE_CATEGORIES)}")
        if self.claim_status not in VALID_CLAIM_STATUS:
            raise ValueError(f"claim_status must be one of {sorted(VALID_CLAIM_STATUS)}")
        if self.claim_reality_score is not None and not 0 <= self.claim_reality_score <= 100:
            raise ValueError("claim_reality_score must be between 0 and 100")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClaimRecord":
        obj = cls(**data)
        obj.validate()
        return obj
