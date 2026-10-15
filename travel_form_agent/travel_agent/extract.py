"""Extract structured travel data from documents using Claude vision API."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional

import anthropic

_SYSTEM = """You are a WSDOT travel expense expert. Extract structured data from travel documents.
Return ONLY valid JSON, no prose, no markdown code blocks."""

_TRAVEL_REQUEST_PROMPT = """Extract all available fields from this approved WSDOT travel request document.
Return a JSON object with these fields (omit fields not found):
{
  "traveler": {
    "name": "",
    "employee_id": "",
    "class_title": "",
    "official_station": "",
    "official_residence": "",
    "address": "",
    "city": "",
    "state": "",
    "zip_code": "",
    "regular_work_hours": "",
    "supervisor_name": ""
  },
  "event_title": "",
  "destination_city": "",
  "departure_datetime": "",
  "return_datetime": "",
  "meeting_begin_datetime": "",
  "meeting_end_datetime": "",
  "registration_fee": 0,
  "airfare": 0,
  "lodging_days": 0,
  "lodging_rate": 0,
  "hotel_name": "",
  "hotel_city": "",
  "comments": "",
  "remarks": "",
  "signature_date": "",
  "travel_advance": 0,
  "account_codes": [
    {
      "program": "", "work_order": "", "fund": "", "org_code": "",
      "unit": "", "subunit": "", "object_code": "", "activity": "",
      "appropriation": "", "function": "", "bal_sheet": "", "amount": 0
    }
  ]
}
For dates use format YYYY-MM-DD. For datetimes use "MM/DD/YY HHMM"."""

_RECEIPT_PROMPT = """Extract expense information from this receipt/invoice/folio.
Return a JSON object:
{
  "vendor": "",
  "date": "",
  "amount": 0.0,
  "description": "",
  "expense_type": ""
}
For date use YYYY-MM-DD format.
For expense_type use one of: lodging, airfare, registration, parking, taxi, rideshare, ferry, toll, other."""

_HOTEL_PROMPT = """Extract hotel stay information from this hotel folio/receipt.
Return a JSON object:
{
  "hotel_name": "",
  "hotel_city": "",
  "check_in": "",
  "check_out": "",
  "nightly_rate": 0.0,
  "num_nights": 0,
  "total_amount": 0.0,
  "lodging_entries": [
    {"date": "", "amount": 0.0}
  ]
}
For dates use YYYY-MM-DD format."""


def _encode_file(file_bytes: bytes, media_type: str) -> dict:
    data = base64.standard_b64encode(file_bytes).decode("utf-8")
    return {"type": "base64", "media_type": media_type, "data": data}


def _media_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "application/pdf")


def _call_claude(content: list) -> dict:
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=4096,
        system=_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    text = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


def extract_travel_request(file_bytes: bytes, filename: str) -> dict:
    """Extract structured data from an approved travel request PDF."""
    media_type = _media_type(filename)
    content = [
        {
            "type": "document" if media_type == "application/pdf" else "image",
            "source": _encode_file(file_bytes, media_type),
        },
        {"type": "text", "text": _TRAVEL_REQUEST_PROMPT},
    ]
    return _call_claude(content)


def extract_hotel_folio(file_bytes: bytes, filename: str) -> dict:
    """Extract hotel stay details from a hotel folio/receipt."""
    media_type = _media_type(filename)
    content = [
        {
            "type": "document" if media_type == "application/pdf" else "image",
            "source": _encode_file(file_bytes, media_type),
        },
        {"type": "text", "text": _HOTEL_PROMPT},
    ]
    return _call_claude(content)


def extract_receipt(file_bytes: bytes, filename: str) -> dict:
    """Extract expense info from a generic receipt."""
    media_type = _media_type(filename)
    content = [
        {
            "type": "document" if media_type == "application/pdf" else "image",
            "source": _encode_file(file_bytes, media_type),
        },
        {"type": "text", "text": _RECEIPT_PROMPT},
    ]
    return _call_claude(content)


def merge_into_intake(
    travel_request: dict,
    hotel_data: Optional[dict] = None,
    receipts: Optional[list[dict]] = None,
) -> dict:
    """Merge extracted document data into a TravelIntake-compatible dict."""
    intake = dict(travel_request)

    other_expenses = list(intake.get("other_expenses", []))
    account_codes = list(intake.get("account_codes", []))

    if hotel_data:
        if not intake.get("hotel_name") and hotel_data.get("hotel_name"):
            intake["hotel_name"] = hotel_data["hotel_name"]
        if not intake.get("hotel_city") and hotel_data.get("hotel_city"):
            intake["hotel_city"] = hotel_data["hotel_city"]
        if not intake.get("lodging_rate") and hotel_data.get("nightly_rate"):
            intake["lodging_rate"] = hotel_data["nightly_rate"]
        if not intake.get("lodging_days") and hotel_data.get("num_nights"):
            intake["lodging_days"] = hotel_data["num_nights"]

        for entry in hotel_data.get("lodging_entries", []):
            other_expenses.append({
                "date": entry.get("date", ""),
                "paid_to": hotel_data.get("hotel_name", "Hotel"),
                "for_what": "Lodging",
                "amount": entry.get("amount", hotel_data.get("nightly_rate", 0)),
            })

    for r in (receipts or []):
        other_expenses.append({
            "date": r.get("date", ""),
            "paid_to": r.get("vendor", ""),
            "for_what": r.get("description", r.get("expense_type", "")),
            "amount": r.get("amount", 0),
        })

    intake["other_expenses"] = other_expenses
    intake["account_codes"] = account_codes
    return intake
