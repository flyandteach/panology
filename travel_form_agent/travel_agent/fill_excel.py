from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import openpyxl
from openpyxl.utils import column_index_from_string

from .models import DailyExpenseLine, OtherExpense, TravelIntake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cv(value) -> float:
    return round(float(value or 0), 2)


def _excel_time(value) -> Optional[float]:
    """Convert a time string like '0600' or '06:00' to an Excel time fraction."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().upper().replace(".", "")
    normalized = re.sub(r"\s+", " ", text)
    for candidate in [normalized, normalized.replace(" ", "")]:
        for fmt in ("%I:%M%p", "%I%M%p", "%H:%M", "%H%M"):
            try:
                dt = datetime.strptime(candidate, fmt)
                return round((dt.hour * 60 + dt.minute) / 1440, 10)
            except ValueError:
                pass
    return None


def _set(ws, cell_ref: str, value) -> None:
    """Write a value to a cell, skipping None and empty string."""
    if value is None or value == "":
        return
    ws[cell_ref] = value


# ---------------------------------------------------------------------------
# Row writers
# ---------------------------------------------------------------------------

def _write_daily_line(ws, row: int, line: DailyExpenseLine) -> None:
    _set(ws, f"A{row}", line.date)
    _set(ws, f"B{row}", line.date.strftime("%a")[:2])
    _set(ws, f"C{row}", line.trip_from)
    _set(ws, f"D{row}", line.trip_to)
    t_dep = _excel_time(line.depart)
    t_ret = _excel_time(line.return_time)
    if t_dep is not None:
        _set(ws, f"E{row}", t_dep)
    if t_ret is not None:
        _set(ws, f"F{row}", t_ret)
    if line.breakfast:
        _set(ws, f"G{row}", _cv(line.breakfast))
    if line.lunch:
        _set(ws, f"H{row}", _cv(line.lunch))
    if line.dinner:
        _set(ws, f"I{row}", _cv(line.dinner))
    if line.lodging:
        _set(ws, f"J{row}", _cv(line.lodging))
    if line.miles:
        _set(ws, f"K{row}", _cv(line.miles))
    if line.mileage_rate:
        _set(ws, f"L{row}", _cv(line.mileage_rate))
    _set(ws, f"M{row}", line.pov_reason)
    if line.mileage_total:
        _set(ws, f"N{row}", _cv(line.mileage_total))
    if line.other:
        _set(ws, f"O{row}", _cv(line.other))
    if line.total:
        _set(ws, f"P{row}", _cv(line.total))
    _set(ws, f"Q{row}", line.purpose)


def _page_totals(lines: List[DailyExpenseLine]) -> Dict[str, float]:
    return {
        "meals":   _cv(sum(x.breakfast + x.lunch + x.dinner for x in lines)),
        "lodging": _cv(sum(x.lodging for x in lines)),
        "mileage": _cv(sum(x.mileage_total for x in lines)),
        "other":   _cv(sum(x.other for x in lines)),
        "total":   _cv(sum(x.total for x in lines)),
    }


def _write_page_totals(ws, lines: List[DailyExpenseLine], row: int) -> None:
    t = _page_totals(lines)
    _set(ws, f"G{row}", t["meals"])
    _set(ws, f"J{row}", t["lodging"])
    _set(ws, f"N{row}", t["mileage"])
    _set(ws, f"O{row}", t["other"])
    _set(ws, f"P{row}", t["total"])


def _write_accounts(ws, intake: TravelIntake) -> None:
    for row, account in zip(range(35, 40), intake.account_codes[:5]):
        _set(ws, f"A{row}", account.work_order)
        _set(ws, f"B{row}", account.group)
        _set(ws, f"C{row}", account.work_op)
        _set(ws, f"D{row}", account.object_code)
        _set(ws, f"E{row}", account.org_code)
        _set(ws, f"F{row}", account.cont_sec)
        _set(ws, f"G{row}", account.bal_sheet)
        _set(ws, f"J{row}", account.non_participating)
        if account.amount:
            _set(ws, f"K{row}", _cv(account.amount))
    if intake.travel_advance:
        _set(ws, "K40", _cv(intake.travel_advance))
    total_coded = sum(x.amount for x in intake.account_codes[:5])
    _set(ws, "K41", _cv(total_coded - intake.travel_advance))


def _write_other_expenses(ws, items: List[OtherExpense]) -> None:
    for row, item in zip(range(35, 41), items[:6]):
        _set(ws, f"L{row}", item.date)
        _set(ws, f"M{row}", item.paid_to)
        _set(ws, f"N{row}", item.for_what)
        if item.amount:
            _set(ws, f"Q{row}", _cv(item.amount))
    total = _cv(sum(x.amount for x in items[:6]))
    if total:
        _set(ws, "Q41", total)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def fill_expense_voucher_xlsx(
    intake: TravelIntake,
    template_path: str | Path,
    output_path: str | Path,
) -> Path:
    template_path = Path(template_path)
    output_path = Path(output_path)

    wb = openpyxl.load_workbook(str(template_path))

    # Find the 133-103 sheet by name, fall back to the first sheet
    ws = wb["133-103"] if "133-103" in wb.sheetnames else wb.active

    # Traveler header
    t = intake.traveler
    _set(ws, "A5", t.name_last_first_initial or t.name)
    _set(ws, "H5", t.employee_id)
    _set(ws, "L5", t.class_title)
    _set(ws, "O5", t.official_station)
    _set(ws, "A7", t.address)
    _set(ws, "H7", t.city)
    _set(ws, "L7", t.state)
    _set(ws, "M7", t.zip_code)
    _set(ws, "O7", t.official_residence)
    _set(ws, "E28", t.regular_work_hours)

    if intake.daily_expenses:
        _set(ws, "A28", max(x.date for x in intake.daily_expenses))
    _set(ws, "A30", intake.remarks)

    # Daily expense rows
    first_page_rows = list(range(10, 22))   # rows 10–21
    second_page_rows = list(range(51, 84))  # rows 51–83

    page1_lines = intake.daily_expenses[: len(first_page_rows)]
    page2_lines = intake.daily_expenses[len(first_page_rows) : len(first_page_rows) + len(second_page_rows)]

    for row, line in zip(first_page_rows, page1_lines):
        _write_daily_line(ws, row, line)
    for row, line in zip(second_page_rows, page2_lines):
        _write_daily_line(ws, row, line)

    # Page totals
    _write_page_totals(ws, page1_lines, 22)
    _write_page_totals(ws, page2_lines, 84)

    # Cross-page carry-forward (page 2 subtotals carried into page 1 summary)
    t2 = _page_totals(page2_lines)
    _set(ws, "G23", t2["meals"])
    _set(ws, "J23", t2["lodging"])
    _set(ws, "N23", t2["mileage"])
    _set(ws, "O23", t2["other"])
    _set(ws, "P23", t2["total"])

    all_t = _page_totals(intake.daily_expenses)
    _set(ws, "G25", all_t["meals"])
    _set(ws, "J25", all_t["lodging"])
    _set(ws, "N25", all_t["mileage"])
    _set(ws, "O25", all_t["other"])
    _set(ws, "P25", all_t["total"])

    if intake.travel_advance:
        _set(ws, "M27", _cv(intake.travel_advance))
    _set(ws, "P27", _cv(all_t["total"] + intake.other_expenses_total - intake.travel_advance))

    # Charge codes and receipts
    _write_accounts(ws, intake)
    _write_other_expenses(ws, intake.other_expenses)

    _set(ws, "E44", intake.signature_date)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))
    return output_path
