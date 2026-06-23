from __future__ import annotations

import csv

from aam_reality_monitor.models import ClaimRecord, EvidenceRecord, OEMProfile
from aam_reality_monitor.reports.csv_export import export_csv
from aam_reality_monitor.reports.markdown_report import generate_markdown_report


def test_markdown_report_generation():
    oems = [OEMProfile("joby", "Joby Aviation", "United States")]
    evidence = [EvidenceRecord("ev_1", "joby", "2026-06-08", "2026-06-01", "general", "manual_note", "Tester", title="Placeholder", summary="Sample only")]
    claims = [ClaimRecord("cl_1", "joby", "2026-06-01", "Manual", "Placeholder claim", "general")]
    report = generate_markdown_report(oems, evidence, claims)
    assert "# AAM Reality Monitor Report" in report
    assert "## OEM Ranking Table" in report
    assert "### Joby Aviation" in report
    assert "Company claims are not treated as verified evidence" in report


def test_csv_export(tmp_path):
    output = tmp_path / "scores.csv"
    export_csv(output, [OEMProfile("joby", "Joby Aviation", "United States")], [], [])
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["oem_id"] == "joby"
    assert rows[0]["overall"] == "0.0"


def test_claim_evidence_linking_logic():
    claim = ClaimRecord("cl_1", "joby", "2026-06-01", "Manual", "Specific claim", "certification")
    claim.supporting_evidence_ids.append("ev_1")
    assert "ev_1" in claim.supporting_evidence_ids
