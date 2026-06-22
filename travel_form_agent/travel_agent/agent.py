from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from .fill_excel import fill_expense_voucher_xlsx
from .fill_pdf import fill_travel_request_pdf
from .models import TravelIntake


@dataclass
class TravelFormAgent:
    travel_request_template: Path
    expense_voucher_template: Path
    output_dir: Path

    def run(self, intake: TravelIntake) -> Dict[str, Path]:
        missing = intake.validate()
        if missing:
            raise ValueError("Missing required travel intake fields: " + ", ".join(missing))

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in intake.event_title)[:60].strip("_")
        if not safe_name:
            safe_name = "travel"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        request_path = self.output_dir / f"travel_request_{safe_name}.pdf"
        expense_path = self.output_dir / f"travel_expense_{safe_name}.xlsx"

        fill_travel_request_pdf(intake, self.travel_request_template, request_path)
        fill_expense_voucher_xlsx(intake, self.expense_voucher_template, expense_path)
        return {"travel_request_pdf": request_path, "expense_voucher_xlsx": expense_path}
