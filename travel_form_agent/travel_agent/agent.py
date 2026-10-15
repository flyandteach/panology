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

        warnings: list[str] = []
        # The 133-103 account-coding block fits 5 lines (rows 34-38) and the
        # receipts block fits 6 lines (rows 34-39). Extra lines are dropped.
        if len(intake.account_codes) > 5:
            warnings.append(
                f"Only the first 5 of {len(intake.account_codes)} account-code lines fit "
                "on the 133-103 voucher; the rest were omitted."
            )
        if len(intake.other_expenses) > 6:
            warnings.append(
                f"Only the first 6 of {len(intake.other_expenses)} receipt lines fit "
                "on the 133-103 voucher; the rest were omitted."
            )

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in intake.event_title)[:60].strip("_")
        if not safe_name:
            safe_name = "travel"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        request_path = self.output_dir / f"travel_request_{safe_name}.pdf"
        expense_path = self.output_dir / f"travel_expense_{safe_name}.xlsx"

        fill_travel_request_pdf(intake, self.travel_request_template, request_path)
        fill_expense_voucher_xlsx(intake, self.expense_voucher_template, expense_path)
        result: Dict[str, Path] = {
            "travel_request_pdf": request_path,
            "expense_voucher_xlsx": expense_path,
        }
        if warnings:
            result["warnings"] = warnings  # type: ignore[assignment]
        return result
