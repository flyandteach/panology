"""CSV export helpers."""
from __future__ import annotations

import csv
from pathlib import Path

from ..models import ClaimRecord, EvidenceRecord, OEMProfile
from ..scoring.overall_score import score_all


def export_csv(path: Path, oems: list[OEMProfile], evidence: list[EvidenceRecord], claims: list[ClaimRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = score_all(oems, evidence, claims)
    fieldnames = ["oem_id", "name", "overall", "certification", "operational", "infrastructure", "production", "financial", "claim_reality"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
