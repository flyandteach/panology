from __future__ import annotations

from pathlib import Path
from typing import Dict, Set

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

from .models import TravelIntake


# ---------------------------------------------------------------------------
# Field names verified from travel_request_template.pdf (Form 700-006)
# Fields were identified by tooltip (Alt text) from the PDF's AcroForm.
# ---------------------------------------------------------------------------

def _currency(value: float) -> str:
    return f"{value:.2f}" if value else ""


def _plain(value) -> str:
    if value is None:
        return ""
    return str(value)


def _set_need_appearances(writer: PdfWriter) -> None:
    root = writer._root_object
    acroform = root.get("/AcroForm")
    if acroform is not None:
        acroform_obj = acroform.get_object()
        acroform_obj.update({NameObject("/NeedAppearances"): BooleanObject(True)})


def _set_checkbox(writer: PdfWriter, field_name: str, checked: bool) -> None:
    value = NameObject("/Yes" if checked else "/Off")
    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        for ref in (annots.get_object() if hasattr(annots, "get_object") else annots):
            annot = ref.get_object()
            if annot.get("/T") == field_name:
                annot.update({NameObject("/V"): value, NameObject("/AS"): value})


def build_travel_request_field_values(intake: TravelIntake, fields: Set[str]) -> Dict[str, str]:
    """Map TravelIntake to verified Form 700-006 field names."""
    fv: Dict[str, str] = {}

    def put(name: str, value) -> None:
        if name in fields:
            fv[name] = _plain(value)

    # ---------- Traveler / header ----------
    put("NameOfEmployee", intake.traveler.name)

    # ---------- Trip basics (page 1) ----------
    # tooltip='Meeting/Training/Conference Event Title'
    put("Text Field 168", intake.event_title)
    # tooltip='Destination City/State'
    put("Text Field 176", intake.destination_city)
    # tooltip='Departure Date/Time'
    put("Text Field 177", intake.departure_datetime)
    # tooltip='Return Date/Time'
    put("Text Field 178", intake.return_datetime)
    # tooltip='Conference/Meeting begins Date/Time'
    put("Text Field 179", intake.meeting_begin_datetime)
    # tooltip='Conference/Meeting ends Date/Time'
    put("Text Field 180", intake.meeting_end_datetime)

    # ---------- Estimated costs ----------
    put("RegistrationFee", _currency(intake.registration_fee))
    put("AirFare", _currency(intake.airfare))

    # Subsistence: days | per-day rate | total
    if intake.subsistence_days is not None:
        put("dayssubsistence", str(intake.subsistence_days))
    if intake.subsistence_rate is not None:
        put("dayssubsistenceamount", _currency(intake.subsistence_rate))
    put("dayssubsistenceperday", _currency(intake.subsistence_total))

    # Lodging: days | per-night rate | total
    if intake.lodging_days:
        put("dayslodging", str(intake.lodging_days))
    if intake.lodging_rate:
        put("dayslodgingamount", _currency(intake.lodging_rate))
    put("dayslodgingperday", _currency(intake.lodging_total))

    # Mileage dollar total (vehiclemileage field holds the $ amount, not the mile count)
    put("vehiclemileage", _currency(intake.mileage_total))

    put("totalestimatedcost", _currency(intake.estimated_total))

    # ---------- Justification / comments ----------
    # tooltip='Justification and benefit to WSDOT:'
    put("Text Field 173", intake.comments)
    # tooltip='Flight and/or Rail Details…'
    put("Text Field 128", intake.comments)

    # ---------- Hotel (page 2 lodging exception section) ----------
    # tooltip='Name of Hotel/Motel'
    put("Text Field 129", intake.hotel_name)
    # tooltip='City'
    put("Text Field 130", intake.hotel_city)

    # ---------- Org / trip id ----------
    # tooltip='Org Code'
    put("Text Field 166", "")   # org_code from first account line if present
    if intake.account_codes:
        put("Text Field 166", intake.account_codes[0].org_code)

    # ---------- Signatures / dates (page 2) ----------
    if intake.signature_date:
        date_str = intake.signature_date.strftime("%m/%d/%y")
        put("Text Field 136", date_str)   # traveler date
        put("Text Field 137", date_str)   # supervisor date
        put("Text Field 138", date_str)   # approving authority date

    # tooltip='Traveler's Supervisor Printed Name'
    put("Text Field 234", intake.traveler.supervisor_name)
    # tooltip='Approving Authority Printed Name'
    put("Text Field 235", intake.traveler.approving_authority_name)

    return fv


def fill_travel_request_pdf(
    intake: TravelIntake,
    template_path: str | Path,
    output_path: str | Path,
) -> Path:
    template_path = Path(template_path)
    output_path = Path(output_path)

    reader = PdfReader(str(template_path))
    writer = PdfWriter()
    writer.append(reader)
    _set_need_appearances(writer)

    fields = set((reader.get_fields() or {}).keys())
    values = build_travel_request_field_values(intake, fields)
    for page in writer.pages:
        writer.update_page_form_field_values(page, values)

    # Transport method checkboxes (verified field names and tooltips)
    requested = {str(x).strip().lower() for x in intake.payment_methods}
    checkbox_map = {
        "Check Box 82": any(k in requested for k in ("airline", "airline travel")),
        "Check Box 83": any(k in requested for k in ("car rental", "rental_car")),
        "Check Box 86": any(k in requested for k in ("train", "rail", "ferry", "trainrailferry")),
        "Check Box 87": any(k in requested for k in ("other", "mileage")),
        # Always mark WSDOT Funded (standard for WSDOT employee travel)
        "Check Box 96": True,
    }
    for field_name, checked in checkbox_map.items():
        if field_name in fields:
            _set_checkbox(writer, field_name, checked)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)
    return output_path
