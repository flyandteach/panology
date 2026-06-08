"""Common scoring helpers."""
from __future__ import annotations

from datetime import date

from ..models import ClaimRecord, EvidenceRecord

CATEGORY_ALIASES = {
    "operations": "operational",
    "operational": "operational",
    "certification": "certification",
    "infrastructure": "infrastructure",
    "production": "production",
    "financial": "financial",
    "claim_reality": "claim_reality",
}

STATUS_MULTIPLIER = {
    "verified": 1.0,
    "sample": 0.0,
    "unverified": 0.35,
    "planned": 0.4,
    "announced": 0.45,
    "under_construction": 0.6,
    "tested": 0.75,
    "approved": 0.9,
    "operational": 1.0,
    "contradicted": 0.0,
}


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def category_evidence_score(evidence: list[EvidenceRecord], category: str) -> float:
    relevant = [e for e in evidence if e.category == category]
    if not relevant:
        return 0.0
    total = 0.0
    for item in relevant:
        multiplier = STATUS_MULTIPLIER.get(item.status, 0.5)
        primary_bonus = 1.15 if item.source_type in {"regulator", "company_filing", "flight_tracking", "aircraft_registry"} else 1.0
        total += item.weighted_value() * multiplier * primary_bonus
    # Saturating curve: multiple strong records approach 100 without requiring fabricated milestone flags.
    return round(clamp((total / (total + 3.0)) * 100), 2)


def claim_status_score(claims: list[ClaimRecord]) -> float:
    if not claims:
        return 0.0
    status_points = {
        "verified": 100,
        "partially_supported": 65,
        "unverified": 30,
        "outdated": 20,
        "promotional_only": 15,
        "contradicted": 0,
    }
    total = 0.0
    today = date.today()
    for claim in claims:
        base = claim.claim_reality_score if claim.claim_reality_score is not None else status_points[claim.claim_status]
        age_days = (today - date.fromisoformat(claim.claim_date)).days
        stale_penalty = 15 if claim.claim_status in {"unverified", "promotional_only"} and age_days > 180 else 0
        total += clamp(base - stale_penalty)
    return round(total / len(claims), 2)
