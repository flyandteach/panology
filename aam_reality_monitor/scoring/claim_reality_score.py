"""Claim reality scoring."""
from __future__ import annotations

from ..models import ClaimRecord, EvidenceRecord
from .common import claim_status_score


def score(evidence: list[EvidenceRecord], claims: list[ClaimRecord] | None = None) -> float:
    """Return a 0-100 claim reality score from claim verification status."""
    return claim_status_score(claims or [])
