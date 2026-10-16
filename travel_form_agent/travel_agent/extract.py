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
    Parse the charge code table using positional double-newline-separated values.

    Form 700-006 columns (Task Order, Location, Bal Sheet are typically blank
    for conference travel and are absent from the extracted text stream):
      Program | Fund | Dept | Unit | Sub Unit | Object | Activity | Appr Unit | Function

    Expected pattern (e.g.): AVOPS\n\n039\n\n405\n\n6910\n\n10\n\nGA01\n\nF501\n\n310\n\n0605
    Object code is captured but overridden per expense type at voucher-build time.
    """
    # Match: Program(alpha) Fund(3d) Dept(3d) Unit(3-5d) SubUnit(1-4d)
    #        Object(2alpha+2d) Activity(1alpha+3d) ApprUnit(3d) Function(4d)
    m = re.search(
        r'([A-Z]{2,8})\n\n(\d{3})\n\n(\d{3})\n\n(\d{3,5})\n\n(\d{1,4})\n\n'
        r'([A-Z]{2}\d{2})\n\n([A-Z]\d{3})\n\n(\d{3})\n\n(\d{4})',
        text,
    )
    if m:
        return [{
            "program":       m.group(1),
            "work_order":    "",
            "fund":          m.group(2),
            "org_code":      m.group(3),   # Dept column → org_code field → XLSX col U
            "unit":          m.group(4),
            "subunit":       m.group(5),
            "object_code":   "",           # assigned per expense type at voucher-build time
            "activity":      m.group(7),
            "appropriation": m.group(8),
            "function":      m.group(9),
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
    """Parse labeled fields from PDF text. Returns (traveler, root).

    Label patterns are tuned to WSDOT Form 700-006 printed text.
    """
    traveler = {
        # "Name of Employee" label on line, value follows on same or next line
        "name": _after(
            r"Name\s*of\s*Employee|Employee\s*Name", text, 60),
        # "Approving Authority Printed Name"
        "approving_authority_name": _after(
            r"Approving\s*Authority\s*(?:Printed\s*)?Name|Approv(?:ing)?\s*Authority", text, 60),
        # "Employee No." / "Employee ID" / "Empl No" / "Employee Number"
        "employee_id": _after(
            r"Employee\s*(?:No\.?|ID|#|Number|Num\.?)|Empl\.?\s*(?:No\.?|ID|#)", text, 20),
        # "Official Station" (Vancouver, Olympia, etc.)
        "official_station": _after(
            r"Official\s*(?:Work\s*)?Station|Duty\s*Station|Home\s*Station", text, 40),
        # "Class Title" / "Position Title" / "Classification"
        "class_title": _after(
            r"Class(?:ification)?(?:\s*Title)?|Position\s*Title|Job\s*Class", text, 30),
    }

    # Supervisor name: blank if the form is unsigned (field shows only "Date" label)
    raw_sup = _after(r"Supervisor(?:'s)?\s*(?:Printed\s*)?Name|Traveler.s\s*Supervisor", text, 60)
    if raw_sup and not re.fullmatch(r'Date|Time|Signature|N/?A', raw_sup, re.I):
        traveler["supervisor_name"] = raw_sup

    root = {
        # Full label from form: "Meeting/Training/Conference Event Title"
        "event_title": _after(
            r"(?:Meeting|Training|Conference)\s*/\s*(?:Training|Conference)\s*/?\s*(?:Conference\s*)?Event\s*Title"
            r"|Event\s*Title|Conference\s*(?:Name|Title)|Meeting\s*Title|Training\s*Title",
            text, 120),
        "destination_city": _after(
            r"Destination\s*(?:City)?(?:/State)?|Destination\s*Location", text, 60),
        # "Departure Date/Time"
        "departure_datetime": _after(
            r"Departure\s*Date(?:/Time)?|Depart(?:ure)?\s*Date", text, 35),
        # "Return Date/Time"
        "return_datetime": _after(
            r"Return\s*Date(?:/Time)?", text, 35),
        # "Conference/Meeting begins Date/Time"
        "meeting_begin_datetime": _after(
            r"(?:Conference|Meeting|Event)\s*[Bb]egins?\s*(?:Date(?:/Time)?)?|Begin(?:s)?\s*Date", text, 35),
        # "Conference/Meeting ends Date/Time"
        "meeting_end_datetime": _after(
            r"(?:Conference|Meeting|Event)\s*[Ee]nds?\s*(?:Date(?:/Time)?)?|End(?:s)?\s*Date", text, 35),
        # "Name of Hotel/Motel"
        "hotel_name": _after(
            r"Name\s*of\s*Hotel(?:/Motel)?|Hotel(?:/Motel)?\s*Name|Hotel\s*Name", text, 60),
        # "City" in lodging section — look in a narrow window after hotel name if possible
        "hotel_city": _after(
            r"Hotel\s*City|City\s*(?:of\s*)?Hotel|(?:Hotel[^:]{0,40})City", text, 40),
        # "Justification and benefit to WSDOT:"
        "comments": _after(
            r"Justification\s*(?:and\s*[Bb]enefit\s*to\s*WSDOT)?|Benefit\s*to\s*WSDOT|Purpose\s*of\s*Travel",
            text, 500),
        "registration_fee": _dollar(r"Registration\s*Fee", text),
    }

    # ---------------------------------------------------------------------------
    # Airfare, subsistence, lodging — Form 700-006 Section A has two columns.
    # pdftotext interleaves them: adjacent-column values bleed across label lines.
    #
    # Layout in extracted text:
    #   "Air Fare $\n<subsistence_days>\n\nper day = $\n\n<sub_total>\n\nper day = $\n\n$ <lodging_rate>"
    #   "Days subsistence at\n\n<lodging_days>\n\nDays lodging at\n\n$\n\n<meal_rate>"
    #
    # Reliable sources:
    #   - Airfare: only if double-\n\n separates it from "Air Fare $"
    #   - Subsistence days: single-\n digit after "Air Fare $" (adjacent column)
    #   - Subsistence rate: 150% section "Per diem meal rate $ 68"
    #   - Lodging days: digit after "Days subsistence at\n\n" (adjacent column)
    #   - Lodging rate: 150% section "is (rate) $ 198.75"
    # ---------------------------------------------------------------------------

    # Airfare: value only present if preceded by double newline
    m_air_val = re.search(r"Air\s*[Ff]are\s*\$\s*\n\n\s*([\d,]+\.?\d*)", text)
    root["airfare"] = float(m_air_val.group(1).replace(",", "")) if m_air_val else 0.0

    # Subsistence days: digit on line immediately following "Air Fare $" (single \n)
    m_subdays = re.search(r"Air\s*[Ff]are\s*\$\s*\n(\d+)", text)
    if m_subdays:
        root["subsistence_days"] = int(m_subdays.group(1))

    # Lodging days: digit after "Days subsistence at\n\n" (garbled adjacent column)
    m_lodgdays = re.search(r"Days\s+subsistence\s+at\s*\n\n(\d+)", text, re.I)
    if m_lodgdays:
        root["lodging_days"] = int(m_lodgdays.group(1))

    # Subsistence rate: from the 150% section's explicit "Per diem meal rate $ XX"
    m_subrate = re.search(r"[Pp]er\s*diem\s*meal\s*rate\s*\$\s*([\d.]+)", text)
    if m_subrate:
        root["subsistence_rate"] = float(m_subrate.group(1))

    # Lodging rate: from 150% section's explicit "is (rate) $ 198.75"
    m_lodgrate = re.search(r"is\s*\(rate\)\s*\$\s*([\d.]+)", text, re.I)
    if m_lodgrate:
        root["lodging_rate"] = float(m_lodgrate.group(1))

    # Fallback subsistence rate from standard label patterns (non-150% forms)
    if not root.get("subsistence_rate"):
        root["subsistence_rate"] = _dollar(
            r"Subsistence\s*(?:@|at|per\s*day|rate|amount)|@\s*\$[\d.]+\s*per\s*day", text) or None

    # Fallback lodging rate from standard label patterns (non-150% forms)
    if not root.get("lodging_rate"):
        root["lodging_rate"] = _dollar(
            r"Lodging\s*(?:@|at|per\s*night|rate|nightly|amount)|@\s*\$[\d.]+\s*per\s*night", text) or None

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
