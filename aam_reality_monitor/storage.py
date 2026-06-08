"""JSON persistence and import helpers."""
from __future__ import annotations

import csv
import json
from dataclasses import fields
from pathlib import Path
from typing import Any, TypeVar

from .config import CLAIMS_FILE, DATA_DIR, EVIDENCE_FILE, OEMS_FILE, SCORING_WEIGHTS_FILE
from .models import ClaimRecord, EvidenceRecord, OEMProfile

T = TypeVar("T", OEMProfile, EvidenceRecord, ClaimRecord)

DEFAULT_WEIGHTS = {
    "certification": 0.30,
    "operational": 0.20,
    "infrastructure": 0.15,
    "production": 0.15,
    "financial": 0.10,
    "claim_reality": 0.10,
}

SAMPLE_OEMS = [
    OEMProfile("joby", "Joby Aviation", "United States", ["S4"], "public", "JOBY", ["FAA"], "https://www.jobyaviation.com", "Sample OEM profile; evidence must be manually verified."),
    OEMProfile("archer", "Archer Aviation", "United States", ["Midnight"], "public", "ACHR", ["FAA"], "https://www.archer.com", "Sample OEM profile; evidence must be manually verified."),
    OEMProfile("beta", "Beta Technologies", "United States", ["ALIA CX300", "ALIA A250"], "private", None, ["FAA"], "https://www.beta.team", "Sample OEM profile; evidence must be manually verified."),
    OEMProfile("wisk", "Wisk Aero", "United States", ["Generation 6"], "private", None, ["FAA"], "https://wisk.aero", "Sample OEM profile; evidence must be manually verified."),
    OEMProfile("eve", "Eve Air Mobility", "Brazil", ["Eve eVTOL"], "public", "EVEX", ["ANAC", "FAA", "EASA"], "https://www.eveairmobility.com", "Starter profile; add evidence manually."),
    OEMProfile("vertical", "Vertical Aerospace", "United Kingdom", ["VX4"], "public", "EVTL", ["CAA", "EASA"], "https://vertical-aerospace.com", "Starter profile; add evidence manually."),
    OEMProfile("lilium", "Lilium", "Germany", ["Lilium Jet"], "public", "LILM", ["EASA", "FAA"], "https://lilium.com", "Track only if relevant; verify current status before scoring."),
    OEMProfile("supernal", "Supernal", "United States", ["S-A2"], "subsidiary", None, ["FAA"], "https://www.supernal.aero", "Starter profile; add evidence manually."),
    OEMProfile("volocopter", "Volocopter", "Germany", ["VoloCity"], "private", None, ["EASA"], "https://www.volocopter.com", "Starter profile; add evidence manually."),
    OEMProfile("electra", "Electra.aero", "United States", ["EL9"], "private", None, ["FAA"], "https://www.electra.aero", "Starter profile; add evidence manually."),
]

SAMPLE_EVIDENCE = [
    EvidenceRecord("ev_sample_0001", "joby", "2026-06-08", "2026-06-08", "general", "manual_note", "Sample Data", title="Placeholder only", summary="Clearly marked placeholder evidence for testing workflows; not a real-world source.", evidence_strength=1, reliability=1, status="sample", notes="Do not use for real assessment."),
    EvidenceRecord("ev_sample_0002", "archer", "2026-06-08", "2026-06-08", "general", "manual_note", "Sample Data", title="Placeholder only", summary="Clearly marked placeholder evidence for testing workflows; not a real-world source.", evidence_strength=1, reliability=1, status="sample", notes="Do not use for real assessment."),
]

SAMPLE_CLAIMS = [
    ClaimRecord("cl_sample_0001", "joby", "2026-06-08", "Sample Data", "Placeholder claim for testing; not a company claim.", "general", "low", "low", claim_status="promotional_only", claim_reality_score=0, notes="Do not use for real assessment."),
]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def init_data(overwrite: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        OEMS_FILE: [o.to_dict() for o in SAMPLE_OEMS],
        EVIDENCE_FILE: [e.to_dict() for e in SAMPLE_EVIDENCE],
        CLAIMS_FILE: [c.to_dict() for c in SAMPLE_CLAIMS],
        SCORING_WEIGHTS_FILE: DEFAULT_WEIGHTS,
    }
    for path, data in files.items():
        if overwrite or not path.exists():
            write_json(path, data)


def _load_records(path: Path, cls: type[T]) -> list[T]:
    return [cls.from_dict(item) for item in read_json(path, [])]


def load_oems() -> list[OEMProfile]:
    return _load_records(OEMS_FILE, OEMProfile)


def load_evidence() -> list[EvidenceRecord]:
    return _load_records(EVIDENCE_FILE, EvidenceRecord)


def load_claims() -> list[ClaimRecord]:
    return _load_records(CLAIMS_FILE, ClaimRecord)


def save_oems(records: list[OEMProfile]) -> None:
    write_json(OEMS_FILE, [r.to_dict() for r in records])


def save_evidence(records: list[EvidenceRecord]) -> None:
    write_json(EVIDENCE_FILE, [r.to_dict() for r in records])


def save_claims(records: list[ClaimRecord]) -> None:
    write_json(CLAIMS_FILE, [r.to_dict() for r in records])


def load_weights() -> dict[str, float]:
    return read_json(SCORING_WEIGHTS_FILE, DEFAULT_WEIGHTS)


def next_id(prefix: str, existing_ids: list[str]) -> str:
    numbers = []
    for item in existing_ids:
        if item.startswith(prefix):
            suffix = item.removeprefix(prefix)
            if suffix.isdigit():
                numbers.append(int(suffix))
    return f"{prefix}{max(numbers, default=0) + 1:06d}"


def import_csv(path: Path, cls: type[T]) -> list[T]:
    list_fields = {"aircraft", "regulators", "supporting_evidence_ids", "contradicting_evidence_ids"}
    records: list[T] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            clean: dict[str, Any] = {k: v for k, v in row.items() if k}
            for key in list_fields:
                if key in clean and isinstance(clean[key], str):
                    clean[key] = [x.strip() for x in clean[key].split(";") if x.strip()]
            for numeric in ("evidence_strength", "reliability"):
                if numeric in clean and clean[numeric] != "":
                    clean[numeric] = int(clean[numeric])
            if "claim_reality_score" in clean and clean["claim_reality_score"] == "":
                clean["claim_reality_score"] = None
            elif "claim_reality_score" in clean:
                clean["claim_reality_score"] = float(clean["claim_reality_score"])
            records.append(cls.from_dict(clean))
    return records
