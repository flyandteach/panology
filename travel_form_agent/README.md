# Travel Form Agent

This is a small, local Python agent for WSDOT Aviation travel paperwork. It intakes structured trip data and generates:

1. a completed Aviation Travel Request PDF; and
2. a completed 133-103 Travel Expense Voucher XLSX.

It does not approve travel, apply signatures, or make reimbursement eligibility decisions. Meals, mileage rates, lodging, registration, and charge-code splits should be entered or reviewed by the traveler/travel coordinator.

## Files included

- `templates/travel_request_template.pdf` - blank Aviation Travel Request template.
- `templates/133-103_template.xlsx` - blank 133-103 Travel Expense Voucher template.
- `examples/bfi_travel_intake.json` - sample trip intake.
- `travel_agent/` - core code.
- `app.py` - Streamlit intake interface.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run from the command line

```bash
python -m travel_agent.cli \
  --input examples/bfi_travel_intake.json \
  --out-dir outputs
```

The generated files will be written to `outputs/`.

## Run the web app

```bash
streamlit run app.py
```

Then upload or paste a travel-intake JSON file. The app will return downloadable PDF and XLSX files.

## Intake JSON notes

The agent is intentionally conservative. It does not infer meal eligibility from travel times. It uses the daily expenses, other expenses, and account-code amounts provided in the JSON.

Important fields:

- `traveler`: name, employee ID, address, official station, official residence, and optional supervisor/approving authority.
- `event_title`, `destination_city`, `departure_datetime`, `return_datetime`, `meeting_begin_datetime`, `meeting_end_datetime`.
- `payment_methods`: e.g., `Other`, `Parking`, `Car Rental`, `Airline travel`.
- `daily_expenses`: one row per voucher line. Use multiple rows when mileage must be split by rate or charge code.
- `other_expenses`: detail section for registration or other receipts.
- `account_codes`: up to five rows for the 133-103 account-code section, and up to six rows for the travel request charge-code section.

## Template mapping

The PDF filler supports the field names observed in the current uploaded blank travel request template and the older signed example. The XLSX filler targets the `133-103` sheet and writes to the visible form cells while preserving the workbook structure.

## Review checklist before routing

- Verify travel dates, meeting times, and destination.
- Confirm meal eligibility and any provided meals.
- Confirm mileage rates and POV reason codes.
- Confirm registration or other receipt amounts.
- Confirm charge codes and account-code split amounts.
- Attach supporting documentation before routing for signature.
