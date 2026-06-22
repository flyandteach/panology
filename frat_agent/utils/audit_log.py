"""
Append-only JSON audit log.  Each completed assessment is a newline-delimited
JSON record in logs/audit_log.ndjson.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from frat_agent.models import RiskReport


_LOG_DIR  = Path(__file__).parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "audit_log.ndjson"


def _ensure_dir() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def write_record(report: RiskReport) -> Path:
    _ensure_dir()
    record = report.to_dict()
    record["_logged_at"] = datetime.now(timezone.utc).isoformat()
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return _LOG_FILE


def read_all() -> list[dict]:
    _ensure_dir()
    if not _LOG_FILE.exists():
        return []
    records = []
    with open(_LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def read_recent(n: int = 20) -> list[dict]:
    return read_all()[-n:]
