"""Command-line interface for the AAM Reality Monitor."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .config import CLAIMS_FILE, EVIDENCE_FILE, OEMS_FILE
from .models import ClaimRecord, EvidenceRecord, OEMProfile
from .reports.csv_export import export_csv as export_scores_csv
from .reports.json_export import export_json as export_bundle_json
from .reports.markdown_report import generate_markdown_report
from .scoring.overall_score import score_all, score_oem
from .storage import import_csv, init_data, load_claims, load_evidence, load_oems, next_id, save_claims, save_evidence, save_oems


def _print_table(rows: list[dict]) -> None:
    for row in rows:
        print(row)


def cmd_init_project(args: argparse.Namespace) -> None:
    init_data(overwrite=args.overwrite)
    print(f"Initialized data files in {OEMS_FILE.parent}")


def cmd_add_oem(args: argparse.Namespace) -> None:
    oems = load_oems()
    oem_id = args.oem_id or args.name.lower().replace(" ", "_")
    if any(o.oem_id == oem_id for o in oems):
        raise SystemExit(f"OEM already exists: {oem_id}")
    profile = OEMProfile(oem_id, args.name, args.country, args.aircraft or [], args.company_type, args.ticker, args.regulators or [], args.website, args.notes)
    profile.validate()
    oems.append(profile)
    save_oems(oems)
    print(f"Added OEM {profile.oem_id}")


def cmd_list_oems(args: argparse.Namespace) -> None:
    for oem in load_oems():
        ticker = f" ({oem.ticker})" if oem.ticker else ""
        print(f"{oem.oem_id}: {oem.name}{ticker} - {', '.join(oem.regulators)}")


def cmd_add_evidence(args: argparse.Namespace) -> None:
    evidence = load_evidence()
    evidence_id = args.evidence_id or next_id("ev_", [e.evidence_id for e in evidence])
    record = EvidenceRecord(
        evidence_id=evidence_id,
        oem_id=args.oem_id,
        date_observed=args.date_observed or date.today().isoformat(),
        event_date=args.event_date,
        category=args.category,
        source_type=args.source_type,
        source_name=args.source_name,
        source_url=args.source_url,
        title=args.title,
        summary=args.summary,
        evidence_strength=args.evidence_strength,
        reliability=args.reliability,
        status=args.status,
        notes=args.notes,
    )
    record.validate()
    evidence.append(record)
    save_evidence(evidence)
    print(f"Added evidence {record.evidence_id}")


def cmd_add_claim(args: argparse.Namespace) -> None:
    claims = load_claims()
    claim_id = args.claim_id or next_id("cl_", [c.claim_id for c in claims])
    record = ClaimRecord(
        claim_id=claim_id,
        oem_id=args.oem_id,
        claim_date=args.claim_date,
        claim_source=args.claim_source,
        claim_text=args.claim_text,
        claim_category=args.claim_category,
        specificity=args.specificity,
        verifiability=args.verifiability,
        claim_status=args.claim_status,
        notes=args.notes,
    )
    record.validate()
    claims.append(record)
    save_claims(claims)
    print(f"Added claim {record.claim_id}")


def cmd_link_evidence_to_claim(args: argparse.Namespace) -> None:
    claims = load_claims()
    evidence_ids = {e.evidence_id for e in load_evidence()}
    if args.evidence_id not in evidence_ids:
        raise SystemExit(f"Evidence not found: {args.evidence_id}")
    for claim in claims:
        if claim.claim_id == args.claim_id:
            target = claim.contradicting_evidence_ids if args.contradicts else claim.supporting_evidence_ids
            if args.evidence_id not in target:
                target.append(args.evidence_id)
            save_claims(claims)
            print(f"Linked {args.evidence_id} to {args.claim_id}")
            return
    raise SystemExit(f"Claim not found: {args.claim_id}")


def cmd_score_oem(args: argparse.Namespace) -> None:
    oems = load_oems()
    oem = next((item for item in oems if item.oem_id == args.oem_id), None)
    if oem is None:
        raise SystemExit(f"OEM not found: {args.oem_id}")
    print(score_oem(oem, load_evidence(), load_claims()))


def cmd_score_all(args: argparse.Namespace) -> None:
    _print_table(score_all(load_oems(), load_evidence(), load_claims()))


def cmd_generate_report(args: argparse.Namespace) -> None:
    report = generate_markdown_report(load_oems(), load_evidence(), load_claims())
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    print(f"Wrote report to {path}")


def cmd_export_json(args: argparse.Namespace) -> None:
    export_bundle_json(Path(args.output), load_oems(), load_evidence(), load_claims())
    print(f"Wrote JSON export to {args.output}")


def cmd_export_csv(args: argparse.Namespace) -> None:
    export_scores_csv(Path(args.output), load_oems(), load_evidence(), load_claims())
    print(f"Wrote CSV export to {args.output}")


def cmd_show_claims(args: argparse.Namespace) -> None:
    for claim in load_claims():
        if args.oem_id is None or claim.oem_id == args.oem_id:
            print(claim.to_dict())


def cmd_show_evidence(args: argparse.Namespace) -> None:
    for record in load_evidence():
        if args.oem_id is None or record.oem_id == args.oem_id:
            print(record.to_dict())


def cmd_import_evidence_csv(args: argparse.Namespace) -> None:
    records = load_evidence() + import_csv(Path(args.path), EvidenceRecord)
    save_evidence(records)
    print(f"Imported evidence from {args.path}")


def cmd_import_claims_csv(args: argparse.Namespace) -> None:
    records = load_claims() + import_csv(Path(args.path), ClaimRecord)
    save_claims(records)
    print(f"Imported claims from {args.path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AAM/eVTOL evidence reality monitoring CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-project")
    init.add_argument("--overwrite", action="store_true")
    init.set_defaults(func=cmd_init_project)

    add_oem = sub.add_parser("add-oem")
    add_oem.add_argument("--oem-id")
    add_oem.add_argument("--name", required=True)
    add_oem.add_argument("--country", required=True)
    add_oem.add_argument("--aircraft", nargs="*")
    add_oem.add_argument("--company-type", default="private")
    add_oem.add_argument("--ticker")
    add_oem.add_argument("--regulators", nargs="*")
    add_oem.add_argument("--website", default="")
    add_oem.add_argument("--notes", default="")
    add_oem.set_defaults(func=cmd_add_oem)

    sub.add_parser("list-oems").set_defaults(func=cmd_list_oems)

    add_ev = sub.add_parser("add-evidence")
    add_ev.add_argument("--evidence-id")
    add_ev.add_argument("--oem-id", required=True)
    add_ev.add_argument("--date-observed")
    add_ev.add_argument("--event-date", required=True)
    add_ev.add_argument("--category", required=True)
    add_ev.add_argument("--source-type", required=True)
    add_ev.add_argument("--source-name", required=True)
    add_ev.add_argument("--source-url", default="")
    add_ev.add_argument("--title", default="")
    add_ev.add_argument("--summary", default="")
    add_ev.add_argument("--evidence-strength", type=int, default=1)
    add_ev.add_argument("--reliability", type=int, default=1)
    add_ev.add_argument("--status", default="unverified")
    add_ev.add_argument("--notes", default="")
    add_ev.set_defaults(func=cmd_add_evidence)

    add_claim = sub.add_parser("add-claim")
    add_claim.add_argument("--claim-id")
    add_claim.add_argument("--oem-id", required=True)
    add_claim.add_argument("--claim-date", required=True)
    add_claim.add_argument("--claim-source", required=True)
    add_claim.add_argument("--claim-text", required=True)
    add_claim.add_argument("--claim-category", required=True)
    add_claim.add_argument("--specificity", default="medium")
    add_claim.add_argument("--verifiability", default="medium")
    add_claim.add_argument("--claim-status", default="unverified")
    add_claim.add_argument("--notes", default="")
    add_claim.set_defaults(func=cmd_add_claim)

    link = sub.add_parser("link-evidence-to-claim")
    link.add_argument("--claim-id", required=True)
    link.add_argument("--evidence-id", required=True)
    link.add_argument("--contradicts", action="store_true")
    link.set_defaults(func=cmd_link_evidence_to_claim)

    score_one = sub.add_parser("score-oem")
    score_one.add_argument("--oem-id", required=True)
    score_one.set_defaults(func=cmd_score_oem)
    sub.add_parser("score-all").set_defaults(func=cmd_score_all)

    report = sub.add_parser("generate-report")
    report.add_argument("--output", default="aam_reality_monitor/generated_reports/report.md")
    report.set_defaults(func=cmd_generate_report)

    json_export = sub.add_parser("export-json")
    json_export.add_argument("--output", required=True)
    json_export.set_defaults(func=cmd_export_json)

    csv_export = sub.add_parser("export-csv")
    csv_export.add_argument("--output", required=True)
    csv_export.set_defaults(func=cmd_export_csv)

    show_claims = sub.add_parser("show-claims")
    show_claims.add_argument("--oem-id")
    show_claims.set_defaults(func=cmd_show_claims)

    show_evidence = sub.add_parser("show-evidence")
    show_evidence.add_argument("--oem-id")
    show_evidence.set_defaults(func=cmd_show_evidence)

    import_ev = sub.add_parser("import-evidence-csv")
    import_ev.add_argument("path")
    import_ev.set_defaults(func=cmd_import_evidence_csv)

    import_claims = sub.add_parser("import-claims-csv")
    import_claims.add_argument("path")
    import_claims.set_defaults(func=cmd_import_claims_csv)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
