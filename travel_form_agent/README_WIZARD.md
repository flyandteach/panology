# WSDOT Travel Form Wizard (no Streamlit)

`wizard.py` is an interactive terminal questionnaire that runs the complete
travel-form pipeline: it asks the same 7 sections as the Streamlit guided
form, then generates the filled **Travel Request PDF**, the **133-103 Excel
expense voucher**, and — for POV trips — a **route map PDF**.

## Install (one time)

```bash
cd travel_form_agent
python3 -m venv .venv
.venv/bin/pip install pypdf openpyxl requests staticmap Pillow
```

## Run

```bash
.venv/bin/python wizard.py
# forms land in ./outputs/  (override with --out-dir)
```

Walk through the prompts; most have sensible defaults (press Enter to accept).
Your traveler profile and charge codes are saved to
`~/.wsdot_travel_profile.json` and reused next time.

What the wizard does automatically:
- Resolves destination city → county → OFM meal tier (with optional
  geocoding confirmation); GSA per-diem lookup for out-of-state travel
- Computes days/nights from dates; assigns object codes (GA01/GA02,
  GF05/GF02, GC01/GC02, EG01/EG02/EG94, GD01/GD03, GB01/GG05/GG06)
- Calculates driving miles via OSRM (or enter manually) and applies the
  date-aware POV rate ($0.725 before 7/1/2026, $0.76 on/after)
- Per-day meal claiming with provided-meal deductions; same-day taxable warning
- Generates the route map PDF for POV trips

## Updating rates each January

Edit the rate block at the top of `travel_agent/rates.py`
(POV rates, meal-tier B/L/D splits). Nothing else needs to change.

## Files changed vs. the Streamlit repo (Oct 2026)

- `travel_agent/rates.py` — meal splits updated to OFM rev. 10/1/2026
  ($68→17/20/31, $80→20/24/36, $86→22/25/39); added date-aware
  `pov_full_rate_on()` / `mileage_rate_on()`
- `travel_agent/fill_excel.py` — account-code block corrected to rows 34–38
  and receipts block to rows 34–39 with the right columns (the old mapping
  wrote rows 38–45 and collided on merged cells)
- `travel_agent/agent.py` — warns instead of silently dropping account/receipt
  lines beyond what the form fits
- `wizard.py` — new: the interactive intake
