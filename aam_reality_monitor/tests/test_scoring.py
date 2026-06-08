from __future__ import annotations

from aam_reality_monitor.models import ClaimRecord, EvidenceRecord, OEMProfile
from aam_reality_monitor.scoring.overall_score import score_oem


def test_scoring_calculations_and_weighting():
    oem = OEMProfile("joby", "Joby Aviation", "United States")
    evidence = [
        EvidenceRecord("ev_1", "joby", "2026-06-08", "2026-06-01", "certification", "regulator", "FAA", evidence_strength=5, reliability=5, status="verified"),
        EvidenceRecord("ev_2", "joby", "2026-06-08", "2026-06-01", "operational", "flight_tracking", "Manual", evidence_strength=4, reliability=4, status="verified"),
    ]
    claims = [ClaimRecord("cl_1", "joby", "2026-06-01", "Manual", "Specific claim", "certification", claim_status="verified")]
    scores = score_oem(oem, evidence, claims)
    assert scores["certification"] > scores["infrastructure"]
    assert scores["operational"] > 0
    assert scores["claim_reality"] == 100
    assert 0 < scores["overall"] < 100


def test_missing_data_handling_scores_zero():
    oem = OEMProfile("wisk", "Wisk Aero", "United States")
    scores = score_oem(oem, [], [])
    assert scores == {
        "overall": 0.0,
        "certification": 0.0,
        "operational": 0.0,
        "infrastructure": 0.0,
        "production": 0.0,
        "financial": 0.0,
        "claim_reality": 0.0,
    }
