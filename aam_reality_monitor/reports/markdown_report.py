"""Markdown report generation."""
from __future__ import annotations

from datetime import datetime, timezone

from ..models import ClaimRecord, EvidenceRecord, OEMProfile
from ..scoring.overall_score import score_all, score_oem


def _records_for_oem(oem_id: str, records):
    return [record for record in records if record.oem_id == oem_id]


def generate_markdown_report(oems: list[OEMProfile], evidence: list[EvidenceRecord], claims: list[ClaimRecord]) -> str:
    generated = datetime.now(timezone.utc).date().isoformat()
    rankings = score_all(oems, evidence, claims)
    lines = [
        "# AAM Reality Monitor Report",
        "",
        f"Date generated: {generated}",
        "",
        "## Executive Summary",
        "",
        "This report scores AAM/eVTOL OEMs using local evidence records and separately tracks claims. Company claims are not treated as verified evidence unless linked to supporting evidence.",
        "",
        "## OEM Ranking Table",
        "",
        "| Rank | OEM | Overall | Certification | Operations | Infrastructure | Production | Financial | Claim Reality |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rank, row in enumerate(rankings, start=1):
        lines.append(
            f"| {rank} | {row['name']} | {row['overall']} | {row['certification']} | {row['operational']} | {row['infrastructure']} | {row['production']} | {row['financial']} | {row['claim_reality']} |"
        )
    lines.extend(["", "## OEM Profiles", ""])
    for oem in oems:
        scores = score_oem(oem, evidence, claims)
        oem_evidence = _records_for_oem(oem.oem_id, evidence)
        oem_claims = _records_for_oem(oem.oem_id, claims)
        lines.extend([
            f"### {oem.name}",
            "",
            "#### Current Assessment",
            "",
            f"Overall score: {scores['overall']} / 100. This score reflects only stored evidence; missing data scores as zero rather than inferred progress.",
            "",
            "#### Evidence Summary",
            "",
            f"Stored evidence records: {len(oem_evidence)}. Verified or operational records are scored more heavily than announcements, planned items, or weak sources.",
            "",
            "#### Certification Status",
            "",
            f"Score: {scores['certification']} / 100. No certification milestone is inferred without a matching evidence record.",
            "",
            "#### Operational Evidence",
            "",
            f"Score: {scores['operational']} / 100. Test flights and demonstrations require direct evidence records.",
            "",
            "#### Infrastructure Readiness",
            "",
            f"Score: {scores['infrastructure']} / 100. Announced, approved, under construction, tested, and operational infrastructure should be recorded distinctly.",
            "",
            "#### Production Readiness",
            "",
            f"Score: {scores['production']} / 100.",
            "",
            "#### Financial Endurance",
            "",
            f"Score: {scores['financial']} / 100.",
            "",
            "#### Claim Reality Review",
            "",
            f"Score: {scores['claim_reality']} / 100 across {len(oem_claims)} stored claims.",
            "",
            "#### Recent Claims",
            "",
        ])
        if oem_claims:
            for claim in sorted(oem_claims, key=lambda c: c.claim_date, reverse=True)[:5]:
                lines.append(f"- {claim.claim_date}: {claim.claim_text} ({claim.claim_status})")
        else:
            lines.append("- No claims recorded.")
        lines.extend(["", "#### Key Evidence Records", ""])
        if oem_evidence:
            for item in sorted(oem_evidence, key=lambda e: e.event_date, reverse=True)[:8]:
                lines.append(f"- {item.event_date}: {item.title or item.category} — {item.summary} [{item.source_type}; strength {item.evidence_strength}, reliability {item.reliability}, status {item.status}]")
        else:
            lines.append("- No evidence recorded.")
        lines.extend([
            "",
            "#### Watch Items",
            "",
            "- Add primary-source evidence before relying on company timing claims.",
            "- Review unsupported claims older than 180 days for staleness.",
            "",
        ])
    lines.extend([
        "## Limitations",
        "",
        "- MVP uses local JSON data only and does not perform live scraping.",
        "- Placeholder sample records are marked as sample and do not contribute to real-world scores.",
        "- Scores are directional monitoring aids, not investment, safety, or regulatory advice.",
        "",
        "## Data Sources",
        "",
        "- Local OEM profiles, evidence records, claim records, and scoring weights stored as JSON files.",
    ])
    return "\n".join(lines) + "\n"
