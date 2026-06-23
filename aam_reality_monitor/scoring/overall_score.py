"""Overall scoring orchestration."""
from __future__ import annotations

from ..models import ClaimRecord, EvidenceRecord, OEMProfile
from ..storage import load_weights
from . import certification_score, claim_reality_score, financial_score, infrastructure_score, operational_score, production_score


def score_oem(oem: OEMProfile, evidence: list[EvidenceRecord], claims: list[ClaimRecord], weights: dict[str, float] | None = None) -> dict[str, float]:
    oem_evidence = [item for item in evidence if item.oem_id == oem.oem_id]
    oem_claims = [item for item in claims if item.oem_id == oem.oem_id]
    category_scores = {
        "certification": certification_score.score(oem_evidence, oem_claims),
        "operational": operational_score.score(oem_evidence, oem_claims),
        "infrastructure": infrastructure_score.score(oem_evidence, oem_claims),
        "production": production_score.score(oem_evidence, oem_claims),
        "financial": financial_score.score(oem_evidence, oem_claims),
        "claim_reality": claim_reality_score.score(oem_evidence, oem_claims),
    }
    active_weights = weights or load_weights()
    weight_total = sum(active_weights.values()) or 1
    overall = sum(category_scores[key] * active_weights.get(key, 0) for key in category_scores) / weight_total
    return {"overall": round(overall, 2), **category_scores}


def score_all(oems: list[OEMProfile], evidence: list[EvidenceRecord], claims: list[ClaimRecord], weights: dict[str, float] | None = None) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for oem in oems:
        rows.append({"oem_id": oem.oem_id, "name": oem.name, **score_oem(oem, evidence, claims, weights)})
    return sorted(rows, key=lambda row: float(row["overall"]), reverse=True)
