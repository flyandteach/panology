from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Set

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

from .models import TravelIntake


def _currency(value: float) -> str:
    return f"{value:.2f}" if value else "0"


def _plain(value) -> str:
    if value is None:
        return ""
    return str(value)


def _field_names(reader: PdfReader) -> Set[str]:
    fields = reader.get_fields() or {}
    return set(fields.keys())


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
        for ref in annots.get_object() if hasattr(annots, "get_object") else annots:
            annot = ref.get_object()
            if annot.get("/T") == field_name:
                annot.update({NameObject("/V"): value, NameObject("/AS"): value})


def build_travel_request_field_values(intake: TravelIntake, fields: Set[str]) -> Dict[str, str]:
    """Build field values that support both the current and older WSDOT Aviation travel request templates."""
    field_values: Dict[str, str] = {}

    def put(name: str, value) -> None:
        if name in fields:
            field_values[name] = _plain(value)

    put("Employee Traveling", intake.traveler.name)
    put("Meeting/Training/Conf. event title:", intake.event_title)
    put("MeetingTrainingConf event title", intake.event_title)
    put("Destination City", intake.destination_city)

    # Current template names
    put("Departure Date/Time", intake.departure_datetime)
    put("return date and time", intake.return_datetime)
    put("conference/meeting date and time", intake.meeting_begin_datetime)
    put("conference meeting end date and time", intake.meeting_end_datetime)

    # Older template names observed in signed examples. The labels are ambiguous in that file, so this maps by visual label.
    put("Return DateTime", intake.departure_datetime)
    put("undefined_2", intake.return_datetime)
    put("ConferenceMeeting ends DateTime", intake.meeting_begin_datetime)
    put("undefined_3", intake.meeting_end_datetime)

    put("Registration fee", _currency(intake.registration_fee))
    put("reg. fee", _currency(intake.registration_fee))
    put("Airfare", _currency(intake.airfare))
    put("air fare rates", _currency(intake.airfare))

    put("Days subsistence", "" if intake.subsistence_days is None else intake.subsistence_days)
    put("sub days", "" if intake.subsistence_days is None else intake.subsistence_days)
    put("Days subsistence at", "" if intake.subsistence_rate is None else intake.subsistence_rate)
    put("sub rates", "" if intake.subsistence_rate is None else intake.subsistence_rate)
    put("subsistaence total", _currency(intake.subsistence_total))
    put("sub total", _currency(intake.subsistence_total))

    put("Days Lodging", "" if intake.lodging_days is None else intake.lodging_days)
    put("lodging days", "" if intake.lodging_days is None else intake.lodging_days)
    put("Days lodging at", "" if intake.lodging_rate is None else intake.lodging_rate)
    put("lodging rates", "" if intake.lodging_rate is None else intake.lodging_rate)
    put("lodging total", _currency(intake.lodging_total))

    put("other fees", _currency(intake.other_fees_total_for_request))
    put("estimated cost", _currency(intake.estimated_total))
    put("estimated total", _currency(intake.estimated_total))

    put("Details Comments", intake.comments)
    put("Section B Airline Train or Ferry details CommentsAccommodationsother relevant informationRow1", intake.comments)
    put("other", intake.other_payment_method_description)
    put("undefined", intake.other_payment_method_description)

    put("name of hotel", intake.hotel_name)
    put("undefined_4", intake.hotel_name)
    put("Name of Hotel City", intake.hotel_city)
    put("City", intake.hotel_city)

    put("Traveler’s name", intake.traveler.name)
    put("Print name", intake.traveler.name)
    put("supervisor's name", intake.traveler.supervisor_name)
    put("approving authority name", intake.traveler.approving_authority_name)
    if intake.signature_date:
        put("Date 1", intake.signature_date.strftime("%m/%d/%y"))
        put("Date", intake.signature_date.strftime("%m/%d/%y"))

    # Charge codes. Supports both the current long-coded version and older work-order layout.
    for idx, account in enumerate(intake.account_codes[:6], start=1):
        put(f"Cited Authority Fund Appropriation Object Unit Subunit Activity Function Work Op ProgramRow{idx}", account.cited_authority)
        put(f"Fund {idx}", account.fund)
        put(f"Appropriation {idx}", account.appropriation)
        put(f"Object {idx}", account.object_code)
        put(f"Unit {idx}", account.unit or account.org_code)
        put(f"subunit {idx}", account.subunit)
        put(f"activity {idx}", account.activity)
        put(f"function {idx}", account.function or account.work_op)
        put(f"program {idx}", account.program)

        put(f"Work OrderRow{idx}", account.work_order)
        put(f"GroupRow{idx}", account.group)
        put(f"Work OpRow{idx}", account.work_op)
        put(f"Object CodeRow{idx}", account.object_code)
        put(f"Org CodeRow{idx}", account.org_code)

    return field_values


def fill_travel_request_pdf(intake: TravelIntake, template_path: str | Path, output_path: str | Path) -> Path:
    template_path = Path(template_path)
    output_path = Path(output_path)
    reader = PdfReader(str(template_path))
    writer = PdfWriter()
    writer.append(reader)
    _set_need_appearances(writer)

    fields = _field_names(reader)
    values = build_travel_request_field_values(intake, fields)
    for page in writer.pages:
        writer.update_page_form_field_values(page, values)

    method_map = {
        "airline": ["Check Box2", "Airline travel"],
        "airline travel": ["Check Box2", "Airline travel"],
        "train": ["Check Box3", "TrainRailFerry"],
        "rail": ["Check Box3", "TrainRailFerry"],
        "ferry": ["Check Box3", "TrainRailFerry"],
        "car rental": ["Check Box4", "Car Rental"],
        "parking": ["Check Box5", "Parking"],
        "other": ["Check Box6", "Other"],
    }
    requested = {str(x).strip().lower() for x in intake.payment_methods}
    for method, candidates in method_map.items():
        checked = method in requested
        for field_name in candidates:
            if field_name in fields:
                _set_checkbox(writer, field_name, checked)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)
    return output_path
