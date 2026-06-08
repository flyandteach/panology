"""JSON export helpers."""
from __future__ import annotations

from pathlib import Path

from ..models import ClaimRecord, EvidenceRecord, OEMProfile
from ..scoring.overall_score import score_all
from ..storage import write_json


def export_json(path: Path, oems: list[OEMProfile], evidence: list[EvidenceRecord], claims: list[ClaimRecord]) -> None:
    write_json(path, {
        "oems": [o.to_dict() for o in oems],
        "evidence": [e.to_dict() for e in evidence],
        "claims": [c.to_dict() for c in claims],
        "scores": score_all(oems, evidence, claims),
    })
