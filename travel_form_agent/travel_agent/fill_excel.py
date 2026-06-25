from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import copy
import re
import zipfile
import xml.etree.ElementTree as ET

from .models import DailyExpenseLine, OtherExpense, TravelIntake

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)
ET.register_namespace("xml", XML_NS)


def _q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def _currency(value: float) -> float:
    return round(float(value or 0), 2)


def _excel_date(value: date | datetime) -> int:
    if isinstance(value, datetime):
        value = value.date()
    return (value - date(1899, 12, 30)).days


def _col_to_num(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n




def _excel_time(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().upper().replace(".", "")
    normalized = re.sub(r"\s+", " ", text)
    candidates = [normalized, normalized.replace(" ", "")]
    for candidate in candidates:
        for fmt in ("%I:%M%p", "%I%M%p", "%H:%M", "%H%M"):
            try:
                dt = datetime.strptime(candidate, fmt)
                return round((dt.hour * 60 + dt.minute) / 1440, 10)
            except ValueError:
                pass
    return value

def _split_cell(cell_ref: str) -> Tuple[str, int]:
    m = re.match(r"^([A-Za-z]+)(\d+)$", cell_ref)
    if not m:
        raise ValueError(f"Invalid cell reference: {cell_ref}")
    return m.group(1).upper(), int(m.group(2))


def _cell_sort_key(cell_ref: str) -> Tuple[int, int]:
    col, row = _split_cell(cell_ref)
    return row, _col_to_num(col)


class OOXMLWorksheetEditor:
    """Tiny XLSX sheet editor that preserves workbook parts that openpyxl may drop."""

    def __init__(self, root: ET.Element):
        self.root = root
        self.sheet_data = root.find(_q(MAIN_NS, "sheetData"))
        if self.sheet_data is None:
            self.sheet_data = ET.SubElement(root, _q(MAIN_NS, "sheetData"))
        self.rows: Dict[int, ET.Element] = {}
        for row in self.sheet_data.findall(_q(MAIN_NS, "row")):
            r = int(row.attrib.get("r", "0"))
            if r:
                self.rows[r] = row

    def _get_row(self, row_num: int) -> ET.Element:
        row = self.rows.get(row_num)
        if row is not None:
            return row
        row = ET.Element(_q(MAIN_NS, "row"), {"r": str(row_num)})
        inserted = False
        for idx, existing in enumerate(list(self.sheet_data)):
            existing_r = int(existing.attrib.get("r", "0"))
            if existing_r > row_num:
                self.sheet_data.insert(idx, row)
                inserted = True
                break
        if not inserted:
            self.sheet_data.append(row)
        self.rows[row_num] = row
        return row

    def _get_cell(self, cell_ref: str) -> ET.Element:
        col, row_num = _split_cell(cell_ref)
        row = self._get_row(row_num)
        for cell in row.findall(_q(MAIN_NS, "c")):
            if cell.attrib.get("r") == cell_ref:
                return cell
        cell = ET.Element(_q(MAIN_NS, "c"), {"r": cell_ref})
        new_key = _cell_sort_key(cell_ref)
        inserted = False
        for idx, existing in enumerate(list(row)):
            existing_ref = existing.attrib.get("r")
            if existing_ref and _cell_sort_key(existing_ref) > new_key:
                row.insert(idx, cell)
                inserted = True
                break
        if not inserted:
            row.append(cell)
        return cell

    def set_cell(self, cell_ref: str, value) -> None:
        cell = self._get_cell(cell_ref)
        # Preserve style, merge behavior, and row/column formatting, but remove previous value/formula payload.
        for child in list(cell):
            if child.tag in {_q(MAIN_NS, "v"), _q(MAIN_NS, "f"), _q(MAIN_NS, "is")}:
                cell.remove(child)
        cell.attrib.pop("t", None)
        cell.attrib.pop("cm", None)
        cell.attrib.pop("vm", None)

        if value is None or value == "":
            return
        if isinstance(value, (date, datetime)):
            ET.SubElement(cell, _q(MAIN_NS, "v")).text = str(_excel_date(value))
            return
        if isinstance(value, bool):
            cell.attrib["t"] = "b"
            ET.SubElement(cell, _q(MAIN_NS, "v")).text = "1" if value else "0"
            return
        if isinstance(value, (int, float)):
            ET.SubElement(cell, _q(MAIN_NS, "v")).text = str(value)
            return
        cell.attrib["t"] = "inlineStr"
        is_el = ET.SubElement(cell, _q(MAIN_NS, "is"))
        t_el = ET.SubElement(is_el, _q(MAIN_NS, "t"))
        text = str(value)
        if text != text.strip():
            t_el.attrib[_q(XML_NS, "space")] = "preserve"
        t_el.text = text


def _find_worksheet_path(xlsx: zipfile.ZipFile, sheet_name: str) -> str:
    workbook_xml = ET.fromstring(xlsx.read("xl/workbook.xml"))
    rels_xml = ET.fromstring(xlsx.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_xml.findall(_q(PKG_REL_NS, "Relationship"))}
    for sheet in workbook_xml.findall(f".//{_q(MAIN_NS, 'sheet')}"):
        if sheet.attrib.get("name") == sheet_name:
            rid = sheet.attrib.get(_q(REL_NS, "id"))
            target = rel_map[rid]
            return "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
    # Fallback for this WSDOT template.
    return "xl/worksheets/sheet1.xml"


def _write_daily_line(ws: OOXMLWorksheetEditor, row: int, line: DailyExpenseLine) -> None:
    ws.set_cell(f"A{row}", line.date)
    ws.set_cell(f"B{row}", line.date.strftime("%a")[:2])
    ws.set_cell(f"C{row}", line.trip_from)
    ws.set_cell(f"D{row}", line.trip_to)
    ws.set_cell(f"E{row}", _excel_time(line.depart))
    ws.set_cell(f"F{row}", _excel_time(line.return_time))
    ws.set_cell(f"G{row}", _currency(line.breakfast) or None)
    ws.set_cell(f"H{row}", _currency(line.lunch) or None)
    ws.set_cell(f"I{row}", _currency(line.dinner) or None)
    ws.set_cell(f"J{row}", _currency(line.lodging) or None)
    ws.set_cell(f"K{row}", _currency(line.miles) or None)
    ws.set_cell(f"L{row}", _currency(line.mileage_rate) or None)
    ws.set_cell(f"M{row}", line.pov_reason)
    ws.set_cell(f"N{row}", _currency(line.mileage_total) or None)
    ws.set_cell(f"O{row}", _currency(line.other) or None)
    ws.set_cell(f"P{row}", _currency(line.total) or None)
    ws.set_cell(f"Q{row}", line.purpose)


def _clear_rows(ws: OOXMLWorksheetEditor, rows: Sequence[int]) -> None:
    for r in rows:
        for col in list("ABCDEFGHIJKLMNOPQ"):
            ws.set_cell(f"{col}{r}", None)


def _page_totals(lines: List[DailyExpenseLine]) -> Dict[str, float]:
    return {
        "meals": _currency(sum(x.breakfast + x.lunch + x.dinner for x in lines)),
        "lodging": _currency(sum(x.lodging for x in lines)),
        "mileage": _currency(sum(x.mileage_total for x in lines)),
        "other": _currency(sum(x.other for x in lines)),
        "total": _currency(sum(x.total for x in lines)),
    }


def _write_page_totals(ws: OOXMLWorksheetEditor, lines: List[DailyExpenseLine], row: int) -> None:
    totals = _page_totals(lines)
    ws.set_cell(f"G{row}", totals["meals"])
    ws.set_cell(f"J{row}", totals["lodging"])
    ws.set_cell(f"N{row}", totals["mileage"])
    ws.set_cell(f"O{row}", totals["other"])
    ws.set_cell(f"P{row}", totals["total"])


def _write_accounts(ws: OOXMLWorksheetEditor, intake: TravelIntake) -> None:
    for row in range(35, 40):
        for col in ["A", "B", "C", "D", "E", "F", "G", "J", "K"]:
            ws.set_cell(f"{col}{row}", None)
    for row, account in zip(range(35, 40), intake.account_codes[:5]):
        ws.set_cell(f"A{row}", account.work_order)
        ws.set_cell(f"B{row}", account.group)
        ws.set_cell(f"C{row}", account.work_op)
        ws.set_cell(f"D{row}", account.object_code)
        ws.set_cell(f"E{row}", account.org_code)
        ws.set_cell(f"F{row}", account.cont_sec)
        ws.set_cell(f"G{row}", account.bal_sheet)
        ws.set_cell(f"J{row}", account.non_participating)
        ws.set_cell(f"K{row}", _currency(account.amount) or None)
    ws.set_cell("K40", _currency(intake.travel_advance) or None)
    ws.set_cell("K41", _currency(sum(x.amount for x in intake.account_codes[:5]) - intake.travel_advance))


def _write_other_expenses(ws: OOXMLWorksheetEditor, items: List[OtherExpense]) -> None:
    for row in range(35, 41):
        for col in ["L", "M", "N", "Q"]:
            ws.set_cell(f"{col}{row}", None)
    for row, item in zip(range(35, 41), items[:6]):
        ws.set_cell(f"L{row}", item.date)
        ws.set_cell(f"M{row}", item.paid_to)
        ws.set_cell(f"N{row}", item.for_what)
        ws.set_cell(f"Q{row}", _currency(item.amount) or None)
    ws.set_cell("Q41", _currency(sum(x.amount for x in items[:6])))


def fill_expense_voucher_xlsx(intake: TravelIntake, template_path: str | Path, output_path: str | Path) -> Path:
    template_path = Path(template_path)
    output_path = Path(output_path)

    with zipfile.ZipFile(template_path, "r") as zin:
        sheet_path = _find_worksheet_path(zin, "133-103")
        sheet_root = ET.fromstring(zin.read(sheet_path))
        ws = OOXMLWorksheetEditor(sheet_root)

        t = intake.traveler
        ws.set_cell("A5", t.name_last_first_initial or t.name)
        ws.set_cell("H5", t.employee_id)
        ws.set_cell("L5", t.class_title)
        ws.set_cell("O5", t.official_station)
        ws.set_cell("A7", t.address)
        ws.set_cell("H7", t.city)
        ws.set_cell("L7", t.state)
        ws.set_cell("M7", t.zip_code)
        ws.set_cell("O7", t.official_residence)
        ws.set_cell("E28", t.regular_work_hours)

        if intake.daily_expenses:
            ws.set_cell("A28", max(x.date for x in intake.daily_expenses))
        ws.set_cell("A30", intake.remarks)

        first_page_rows = list(range(10, 22))
        second_page_rows = list(range(51, 84))
        _clear_rows(ws, first_page_rows + second_page_rows)

        page1_lines = intake.daily_expenses[: len(first_page_rows)]
        page2_lines = intake.daily_expenses[len(first_page_rows) : len(first_page_rows) + len(second_page_rows)]
        for row, line in zip(first_page_rows, page1_lines):
            _write_daily_line(ws, row, line)
        for row, line in zip(second_page_rows, page2_lines):
            _write_daily_line(ws, row, line)

        _write_page_totals(ws, page1_lines, 22)
        _write_page_totals(ws, page2_lines, 84)
        totals1 = _page_totals(page1_lines)
        totals2 = _page_totals(page2_lines)
        all_totals = _page_totals(intake.daily_expenses)

        ws.set_cell("G23", totals2["meals"])
        ws.set_cell("J23", totals2["lodging"])
        ws.set_cell("N23", totals2["mileage"])
        ws.set_cell("O23", totals2["other"])
        ws.set_cell("P23", totals2["total"])
        ws.set_cell("G25", all_totals["meals"])
        ws.set_cell("J25", all_totals["lodging"])
        ws.set_cell("N25", all_totals["mileage"])
        ws.set_cell("O25", all_totals["other"])
        ws.set_cell("P25", all_totals["total"])
        ws.set_cell("M27", _currency(intake.travel_advance) or None)
        ws.set_cell("P27", _currency(all_totals["total"] + intake.other_expenses_total - intake.travel_advance))

        _write_accounts(ws, intake)
        _write_other_expenses(ws, intake.other_expenses)
        ws.set_cell("E44", intake.signature_date)

        sheet_bytes = ET.tostring(sheet_root, encoding="utf-8", xml_declaration=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Skip calcChain.xml — after rewriting cells the cached chain is stale
        # and causes Excel to refuse to open the file.
        _SKIP = {"xl/calcChain.xml"}
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in _SKIP:
                    continue
                data = sheet_bytes if item.filename == sheet_path else zin.read(item.filename)
                zi = zipfile.ZipInfo(item.filename, date_time=item.date_time)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = item.external_attr
                zout.writestr(zi, data)
    return output_path
