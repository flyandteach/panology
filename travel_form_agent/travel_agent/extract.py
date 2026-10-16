"""Extract structured travel data from a filled WSDOT travel request PDF.

Uses pypdf to read AcroForm field values from a filled Form 700-006.
No external API required.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Field name → intake key mapping (verified from fill_pdf.py / Form 700-006)
# ---------------------------------------------------------------------------
_FIELD_MAP = {
    "NameOfEmployee":           ("traveler", "name"),
    "Text Field 168":           ("root",     "event_title"),
    "Text Field 176":           ("root",     "destination_city"),
    "Text Field 177":           ("root",     "departure_datetime"),
    "Text Field 178":           ("root",     "return_datetime"),
    "Text Field 179":           ("root",     "meeting_begin_datetime"),
    "Text Field 180":           ("root",     "meeting_end_datetime"),
    "RegistrationFee":          ("root",     "registration_fee"),
    "AirFare":                  ("root",     "airfare"),
    "dayssubsistence":          ("root",     "subsistence_days"),
    "dayssubsistenceamount":    ("root",     "subsistence_rate"),
    "dayslodging":              ("root",     "lodging_days"),
    "dayslodgingamount":        ("root",     "lodging_rate"),
    "vehiclemileage":           ("root",     "_mileage_total"),
    "Text Field 173":           ("root",     "comments"),
    "Text Field 129":           ("root",     "hotel_name"),
    "Text Field 130":           ("root",     "hotel_city"),
    "Text Field 166":           ("traveler", "org_code"),
    "Text Field 136":           ("root",     "signature_date"),
    "Text Field 234":           ("traveler", "supervisor_name"),
    "Text Field 235":           ("traveler", "approving_authority_name"),
}

_CURRENCY_FIELDS = {"registration_fee", "airfare", "subsistence_rate", "lodging_rate", "_mileage_total"}
_INT_FIELDS = {"subsistence_days", "lodging_days"}


def _parse_number(val: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def extract_travel_request(file_bytes: bytes, filename: str) -> dict:
    """Extract fields from a filled WSDOT Form 700-006 PDF.

    Returns a dict compatible with TravelIntake.from_dict().
    """
    from pypdf import PdfReader
    import io

    reader = PdfReader(io.BytesIO(file_bytes))
    fields = reader.get_fields() or {}

    traveler: dict = {}
    root: dict = {}

    for field_name, (target, key) in _FIELD_MAP.items():
        field = fields.get(field_name)
        if field is None:
            continue
        raw = field.get("/V", "")
        if raw in (None, "", "/Off"):
            continue
        # pypdf returns NameObject strings like '/Yes' for checkboxes
        if isinstance(raw, str) and raw.startswith("/"):
            raw = raw[1:]

        if key in _CURRENCY_FIELDS:
            val = _parse_number(raw)
        elif key in _INT_FIELDS:
            val = int(_parse_number(raw)) if raw else 0
        else:
            val = str(raw).strip()

        if target == "traveler":
            traveler[key] = val
        else:
            root[key] = val

    # Derive last_first from full name if not separately stored
    name = traveler.get("name", "")
    if name and "," not in name:
        parts = name.strip().split()
        if len(parts) >= 2:
            traveler["name_last_first_initial"] = (
                f"{parts[-1]}, {parts[0]}, {parts[1][0]}" if len(parts) >= 3
                else f"{parts[-1]}, {parts[0]}"
            )

    root["traveler"] = traveler
    root.setdefault("daily_expenses", [])
    root.setdefault("account_codes", [])
    root.setdefault("other_expenses", [])

    return root


def merge_receipts(intake: dict, receipts: list[dict]) -> dict:
    """Add manually-entered receipt rows into an intake dict."""
    result = dict(intake)
    oe = list(result.get("other_expenses", []))
    for r in receipts:
        if r.get("amount", 0):
            oe.append(r)
    result["other_expenses"] = oe
    return result
