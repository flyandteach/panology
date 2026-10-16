"""Extract structured travel data from a filled WSDOT travel request PDF.

Strategy:
1. Try pypdf AcroForm field extraction (works for digitally filled PDFs).
2. Fall back to text extraction + regex parsing (works for printed/scanned PDFs).
No external API required.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# AcroForm field name → intake key mapping.
# These names were verified from fill_pdf.py (Form 700-006 / travel_request_template.pdf).
# pypdf.get_fields() returns them as dict keys on a filled PDF.
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
    "Text Field 128":           ("root",     "comments"),
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


def dump_raw_fields(file_bytes: bytes) -> dict:
    """Return all AcroForm field names and their current values — for debugging."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    fields = reader.get_fields() or {}
    out = {}
    for k, v in fields.items():
        raw = v.get("/V", "")
        if isinstance(raw, str) and raw.startswith("/"):
            raw = raw[1:]
        out[k] = str(raw).strip() if raw not in (None, "", "/Off") else ""
    return out


def _acroform_extract(file_bytes: bytes) -> dict:
    """Extract values from AcroForm fields. Returns {} if none found."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    fields = reader.get_fields() or {}
    if not fields:
        return {}

    traveler: dict = {}
    root: dict = {}

    for field_name, (target, key) in _FIELD_MAP.items():
        field = fields.get(field_name)
        if field is None:
            continue
        raw = field.get("/V", "")
        if raw in (None, "", "/Off"):
            continue
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

    root["traveler"] = traveler
    return root


def _text_extract(file_bytes: bytes) -> dict:
    """Extract text from PDF pages and parse key fields with regex."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    text = "\n".join(p.extract_text() or "" for p in reader.pages)

    def _after(label: str, text: str, width: int = 80) -> str:
        m = re.search(re.escape(label) + r"[:\s]*([^\n]{1," + str(width) + r"})", text, re.I)
        return m.group(1).strip() if m else ""

    def _currency(label: str) -> float:
        m = re.search(re.escape(label) + r"[:\s]*\$?([\d,]+\.?\d*)", text, re.I)
        return float(m.group(1).replace(",", "")) if m else 0.0

    traveler = {
        "name": _after("Name of Employee", text) or _after("Employee Name", text),
        "supervisor_name": _after("Supervisor", text),
    }

    root = {
        "event_title":          _after("Event Title", text) or _after("Meeting.*Title", text),
        "destination_city":     _after("Destination", text),
        "departure_datetime":   _after("Departure Date", text),
        "return_datetime":      _after("Return Date", text),
        "registration_fee":     _currency("Registration Fee"),
        "airfare":              _currency("Air Fare"),
        "hotel_name":           _after("Hotel", text) or _after("Motel", text),
        "hotel_city":           _after("Hotel.*City", text),
        "comments":             _after("Justification", text, 200),
        "traveler":             traveler,
    }
    return root


def _merge(base: dict, overlay: dict) -> dict:
    """Fill in missing keys in base from overlay."""
    result = dict(base)
    for k, v in overlay.items():
        if k == "traveler":
            t = dict(result.get("traveler") or {})
            for tk, tv in (v or {}).items():
                if tv and not t.get(tk):
                    t[tk] = tv
            result["traveler"] = t
        elif v and not result.get(k):
            result[k] = v
    return result


def extract_travel_request(file_bytes: bytes, filename: str) -> dict:
    """Extract fields from a filled WSDOT Form 700-006 PDF.

    Tries AcroForm field extraction first; falls back to text parsing.
    Returns a dict compatible with TravelIntake.from_dict().
    """
    result: dict = {}

    # Try AcroForm extraction
    try:
        acro = _acroform_extract(file_bytes)
        if acro:
            result = acro
    except Exception:
        pass

    # Try text extraction and merge any missing fields
    try:
        text_data = _text_extract(file_bytes)
        result = _merge(result, text_data)
    except Exception:
        pass

    # Derive last_first from full name
    name = (result.get("traveler") or {}).get("name", "")
    if name and "," not in name:
        parts = name.strip().split()
        if len(parts) >= 2:
            lfi = (
                f"{parts[-1]}, {parts[0]}, {parts[1][0]}" if len(parts) >= 3
                else f"{parts[-1]}, {parts[0]}"
            )
            result.setdefault("traveler", {})["name_last_first_initial"] = lfi

    result.setdefault("traveler", {})
    result.setdefault("daily_expenses", [])
    result.setdefault("account_codes", [])
    result.setdefault("other_expenses", [])

    return result


def merge_receipts(intake: dict, receipts: list[dict]) -> dict:
    """Add manually-entered receipt rows into an intake dict."""
    result = dict(intake)
    oe = list(result.get("other_expenses", []))
    for r in receipts:
        if r.get("amount", 0):
            oe.append(r)
    result["other_expenses"] = oe
    return result
