"""Profile persistence – saves traveler standing info to ~/.wsdot_travel_profile.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

PROFILE_PATH = Path.home() / ".wsdot_travel_profile.json"

# Keys use a "p_" prefix so they never collide with Streamlit widget auto-keys.
PROFILE_KEYS = [
    "p_name", "p_employee_id", "p_class_title", "p_regular_hours",
    "p_official_station", "p_official_residence",
    "p_address", "p_city", "p_state", "p_zip",
    "p_supervisor", "p_approver",
    "p_work_order", "p_group_code", "p_work_op", "p_org_code",
]

# Maps session-state key → JSON file key
PROFILE_KEY_MAP = {k: k[2:] for k in PROFILE_KEYS}   # strip "p_"


def load_profile() -> Dict[str, str]:
    """Return dict keyed by session-state key (p_name, p_employee_id, …)."""
    if PROFILE_PATH.exists():
        try:
            raw = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            return {f"p_{k}": v for k, v in raw.items()}
        except Exception:
            return {}
    return {}


def save_profile(session_state) -> None:
    """Write profile to disk from Streamlit session_state."""
    data = {k[2:]: session_state.get(k, "") for k in PROFILE_KEYS}
    PROFILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
