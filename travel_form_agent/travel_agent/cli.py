from __future__ import annotations

import argparse
from pathlib import Path

from .agent import TravelFormAgent
from .models import TravelIntake


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Fill WSDOT travel request and travel expense voucher forms.")
    parser.add_argument("--input", required=True, help="Path to travel intake JSON file.")
    parser.add_argument("--travel-request-template", default=str(base / "templates" / "travel_request_template.pdf"))
    parser.add_argument("--expense-voucher-template", default=str(base / "templates" / "133-103_template.xlsx"))
    parser.add_argument("--out-dir", default=str(base / "outputs"))
    args = parser.parse_args()

    intake = TravelIntake.from_json_file(args.input)
    agent = TravelFormAgent(
        travel_request_template=Path(args.travel_request_template),
        expense_voucher_template=Path(args.expense_voucher_template),
        output_dir=Path(args.out_dir),
    )
    outputs = agent.run(intake)
    print("Generated:")
    for label, path in outputs.items():
        print(f"  {label}: {path}")


if __name__ == "__main__":
    main()
