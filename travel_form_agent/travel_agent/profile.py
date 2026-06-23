"""Profile persistence – saves traveler standing info to ~/.wsdot_travel_profile.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

PROFILE_PATH = Path.home() / ".wsdot_travel_profile.json"

PROFILE_KEYS = [
    "name", "name_lfi", "employee_id", "class_title", "regular_hours",
    "official_station", "official_residence",
    "address", "city", "state", "zip",
    "supervisor", "approver",
    "work_order", "group_code", "work_op", "org_code",
]


def load_profile() -> Dict[str, Any]:
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_profile(data: Dict[str, Any]) -> None:
    PROFILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
