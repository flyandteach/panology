from __future__ import annotations

import pytest

from aam_reality_monitor.models import ClaimRecord, EvidenceRecord, OEMProfile


def test_valid_oem_schema():
    oem = OEMProfile("joby", "Joby Aviation", "United States", ["S4"], "public", "JOBY", ["FAA"])
    oem.validate()
    assert oem.to_dict()["oem_id"] == "joby"


def test_valid_evidence_schema():
    record = EvidenceRecord("ev_000001", "joby", "2026-06-08", "2026-06-01", "certification", "regulator", "FAA", evidence_strength=5, reliability=5)
    record.validate()
    assert record.weighted_value() == 1.0


def test_invalid_evidence_strength_rejected():
    with pytest.raises(ValueError):
        EvidenceRecord("ev_000001", "joby", "2026-06-08", "2026-06-01", "certification", "regulator", "FAA", evidence_strength=6, reliability=5).validate()


def test_valid_claim_schema():
    claim = ClaimRecord("cl_000001", "archer", "2026-06-01", "Manual", "A specific claim", "certification")
    claim.validate()
    assert claim.claim_status == "unverified"
