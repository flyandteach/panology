"""Extract structured travel data from a filled WSDOT Form 700-006 PDF.

Strategy:
1. AcroForm field extraction (pypdf get_fields) — captures digitally-filled values.
2. Text extraction + regex — captures all labeled fields including charge codes
   and the 150% lodging exception.
Both are attempted and merged; whichever finds more data wins per field.
No external API required.
"""

from __future__ import annotations

import io
import re
from typing import Optional


# ---------------------------------------------------------------------------
# Known AcroForm field names (Form 700-006, verified from fill_pdf.py tooltips).
# A filled PDF may use these names; the debug dump on Streamlit Cloud will
# confirm the actual names and allow mapping updates.
# ---------------------------------------------------------------------------
_ACRO_FIELD_MAP = {
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

_CURRENCY_KEYS = {"registration_fee", "airfare", "subsistence_rate", "lodging_rate", "_mileage_total"}
_INT_KEYS = {"subsistence_days", "lodging_days"}


def _clean_num(val: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Debug helper
# ---------------------------------------------------------------------------

def dump_raw_fields(file_bytes: bytes) -> dict:
    """Return ALL AcroForm field names → current values for debugging."""
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


# ---------------------------------------------------------------------------
# AcroForm extraction
# ---------------------------------------------------------------------------

def _acroform_extract(file_bytes: bytes) -> tuple[dict, dict]:
    """Return (traveler_dict, root_dict) from AcroForm fields."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    fields = reader.get_fields() or {}

    traveler: dict = {}
    root: dict = {}

    for field_name, (target, key) in _ACRO_FIELD_MAP.items():
        field = fields.get(field_name)
        if field is None:
            continue
        raw = field.get("/V", "")
        if raw in (None, "", "/Off"):
            continue
        if isinstance(raw, str) and raw.startswith("/"):
            raw = raw[1:]
        val_str = str(raw).strip()
        if not val_str:
            continue

        if key in _CURRENCY_KEYS:
            val = _clean_num(val_str)
        elif key in _INT_KEYS:
            val = int(_clean_num(val_str))
        else:
            val = val_str

        if target == "traveler":
            traveler[key] = val
        else:
            root[key] = val

    return traveler, root


# ---------------------------------------------------------------------------
# Text extraction + regex parsing
# ---------------------------------------------------------------------------

def _pdf_text(file_bytes: bytes) -> str:
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def _after(label: str, text: str, width: int = 80) -> str:
    """Return the value after a label (colon or whitespace separator)."""
    m = re.search(label + r"[:\s]+([^\n]{1," + str(width) + r"})", text, re.I)
    return m.group(1).strip().rstrip(".,") if m else ""


def _dollar(label: str, text: str) -> float:
    m = re.search(label + r"[:\s]*\$?\s*([\d,]+\.?\d*)", text, re.I)
    return float(m.group(1).replace(",", "")) if m else 0.0


def _parse_charge_codes(text: str) -> list[dict]:
    """
    Parse the charge code table from the Form 700-006 (WSDOT).

    Form 700-006 column headers (Chart of Accounts M 13-02):
      Program | Task Order | Fund | Dept | Unit | Sub Unit |
      Object | Activity | Location | Appr Unit | Function | Bal Sheet

    Object codes are NOT extracted here — they are auto-assigned per
    expense type when building the expense voucher.  We extract the
    base fields that are constant across all charge code rows.
    """
    # Narrow to the Charge Codes section if possible
    m = re.search(r"Charge\s*Codes?(.*)", text, re.I | re.S)
    section = m.group(1)[:800] if m else text

    # --- helpers to pull the first non-header token after a label ---
    def _val(label: str, src: str, width: int = 20) -> str:
        mv = re.search(label + r"[:\s]+([A-Za-z0-9]+)", src, re.I)
        return mv.group(1).strip() if mv else ""

    # Program (e.g. AVOPS)
    program = _val(r"Program", section) or _after(r"Program", text, 15)

    # Task Order / Work Order — often blank for conference travel
    work_order = _val(r"Task\s*Order|Work\s*Order", section) or _after(r"Task\s*Order|Work\s*Order", text, 20)

    # Fund (3-digit, e.g. 039)
    fund = _val(r"\bFund\b", section) or _after(r"\bFund\b", text, 10)

    # Dept (column U in 133-103 XLSX, maps to org_code field, e.g. 405)
    dept = _val(r"\bDept\b", section) or _after(r"\bDept\b", text, 10)

    # Unit (column AA in XLSX, e.g. 6910)
    unit = _val(r"\bUnit\b(?!\s*[Ss]ub|\s*[Aa]ppr)", section) or ""
    if not unit:
        # fallback: look for 4-digit number after Fund/Dept but before Object code
        mu = re.search(r"\b(\d{4})\b", section[section.find(fund or ""):] if fund else section)
        unit = mu.group(1) if mu else ""

    # Sub Unit (e.g. 10)
    subunit = _val(r"Sub\s*[Uu]nit", section) or _after(r"Sub\s*[Uu]nit", text, 10)

    # Activity (e.g. F501)
    activity = _val(r"\bActivity\b", section) or _after(r"\bActivity\b", text, 15)

    # Appr Unit / Appropriation (e.g. 310)
    appr = _val(r"Appr(?:opriation)?\s*(?:Unit)?", section) or _after(r"Appr(?:opriation)?\s*(?:Unit)?", text, 15)

    # Function (e.g. 0605)
    function = _val(r"\bFunction\b", section) or _after(r"\bFunction\b", text, 10)

    if any([program, fund, dept, unit, activity]):
        return [{
            "program":       program,
            "work_order":    work_order,
            "fund":          fund,
            "org_code":      dept,   # Dept column → org_code field → XLSX column U
            "unit":          unit,
            "subunit":       subunit,
            "object_code":   "",     # assigned per expense type at voucher-build time
            "activity":      activity,
            "appropriation": appr,
            "function":      function,
            "bal_sheet":     "",
        }]
    return []


def _parse_150_rule(text: str) -> dict:
    """
    Detect 150% lodging exception info.
    Returns dict with keys: applies (bool), hotel_rate, gsa_rate, percent, approved_rate.
    """
    result = {"applies": False}

    if re.search(r"150\s*%|one\s*and\s*a\s*half|lodging\s*exception", text, re.I):
        result["applies"] = True
        # Try to extract the actual rate approved
        m = re.search(r"150\s*%.*?\$?\s*([\d,]+\.?\d*)", text, re.I)
        if m:
            result["approved_rate"] = float(m.group(1).replace(",", ""))
        # Look for hotel rate in the 150% section
        m2 = re.search(r"(?:hotel|lodging|rate)[^$\n]*\$?\s*([\d,]+\.?\d*)", text, re.I)
        if m2:
            result["hotel_rate"] = float(m2.group(1).replace(",", ""))

    return result


def _text_extract(text: str) -> tuple[dict, dict]:
    """Parse labeled fields from PDF text. Returns (traveler, root)."""
    traveler = {
        "name":                   _after(r"Name\s*of\s*Employee|Employee\s*Name", text, 60),
        "supervisor_name":        _after(r"Supervisor(?:'s)?\s*(?:Name)?|Supervisor\s*Printed", text, 60),
        "approving_authority_name": _after(r"Approv(?:ing)?\s*Authority|Approving\s*Official", text, 60),
        "employee_id":            _after(r"Employee\s*(?:ID|#|Number)", text, 20),
        "official_station":       _after(r"Official\s*Station|Duty\s*Station", text, 40),
        "class_title":            _after(r"Class(?:\s*Title)?|Position\s*Title", text, 30),
    }

    root = {
        "event_title":          _after(r"Event\s*Title|Conference.*?Title|Meeting.*?Title|Training.*?Title", text, 100),
        "destination_city":     _after(r"Destination\s*(?:City)?(?:/State)?", text, 60),
        "departure_datetime":   _after(r"Departure\s*Date(?:/Time)?", text, 30),
        "return_datetime":      _after(r"Return\s*Date(?:/Time)?", text, 30),
        "meeting_begin_datetime": _after(r"(?:Conference|Meeting|Event)\s*[Bb]egins?|Begin\s*Date", text, 30),
        "meeting_end_datetime": _after(r"(?:Conference|Meeting|Event)\s*[Ee]nds?|End\s*Date", text, 30),
        "hotel_name":           _after(r"(?:Name\s*of\s*)?Hotel(?:/Motel)?(?:\s*Name)?", text, 60),
        "hotel_city":           _after(r"Hotel\s*City|City\s*(?:of\s*)?Hotel", text, 40),
        "comments":             _after(r"Justification|Benefit\s*to\s*WSDOT", text, 300),
        "registration_fee":     _dollar(r"Registration\s*Fee", text),
        "airfare":              _dollar(r"Air\s*[Ff]are|Airfare", text),
        "subsistence_rate":     _dollar(r"Subsistence\s*(?:per\s*day|rate)", text),
        "lodging_rate":         _dollar(r"Lodging\s*(?:per\s*night|rate|nightly)", text),
    }

    # Subsistence/lodging day counts
    m = re.search(r"(\d+)\s*[Dd]ay[s]?\s*(?:subsistence|meal)", text)
    if m:
        root["subsistence_days"] = int(m.group(1))
    m = re.search(r"(\d+)\s*[Nn]ight[s]?\s*(?:lodging)?|(?:lodging)\s*(\d+)\s*[Nn]ight", text)
    if m:
        root["lodging_days"] = int(m.group(1) or m.group(2))

    # 150% rule
    rule = _parse_150_rule(text)
    if rule["applies"]:
        root["_150pct_rule"] = rule
        if rule.get("hotel_rate") and not root.get("lodging_rate"):
            root["lodging_rate"] = rule["hotel_rate"]

    # Charge codes
    charge_codes = _parse_charge_codes(text)
    if charge_codes:
        root["account_codes"] = charge_codes

    return traveler, root


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def _merge_dicts(base: dict, overlay: dict) -> dict:
    """Fill empty/missing keys in base from overlay."""
    result = dict(base)
    for k, v in overlay.items():
        if v and not result.get(k):
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_travel_request(file_bytes: bytes, filename: str) -> dict:
    """Extract fields from a filled WSDOT Form 700-006 PDF.

    Tries AcroForm field extraction first, then text parsing.
    Returns a dict compatible with TravelIntake.from_dict().
    """
    traveler: dict = {}
    root: dict = {}

    # 1. AcroForm extraction
    try:
        t_acro, r_acro = _acroform_extract(file_bytes)
        traveler = _merge_dicts(traveler, t_acro)
        root = _merge_dicts(root, r_acro)
    except Exception:
        pass

    # 2. Text extraction (fills gaps and picks up charge codes)
    try:
        text = _pdf_text(file_bytes)
        t_text, r_text = _text_extract(text)
        traveler = _merge_dicts(traveler, t_text)
        # Merge root but don't overwrite non-empty charge codes from AcroForm
        for k, v in r_text.items():
            if k == "account_codes":
                if not root.get("account_codes") and v:
                    root["account_codes"] = v
            elif v and not root.get(k):
                root[k] = v
    except Exception:
        pass

    # Derive name_last_first_initial
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
    root.setdefault("account_codes", root.pop("account_codes", []))
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
