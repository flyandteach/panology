"""Certification scoring."""
from __future__ import annotations

from ..models import ClaimRecord, EvidenceRecord
from .common import category_evidence_score


def score(evidence: list[EvidenceRecord], claims: list[ClaimRecord] | None = None) -> float:
    """Return a 0-100 certification score from certification evidence only."""
    return category_evidence_score(evidence, "certification")
