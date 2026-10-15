#!/usr/bin/env python3
"""WSDOT Travel Form Agent — interactive terminal wizard.

No Streamlit, no browser. Walks through the trip intake question by question,
then generates the filled Travel Request PDF, the 133-103 Excel expense
voucher, and (for POV trips) a route map PDF — the complete pipeline.

Usage:
    python wizard.py [--out-dir outputs]

Requires: pypdf, openpyxl, requests, staticmap, Pillow
    pip install pypdf openpyxl requests staticmap Pillow
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from travel_agent.agent import TravelFormAgent
from travel_agent.geo import driving_miles, geocode_details, gsa_per_diem, route_map_pdf
from travel_agent.models import TravelIntake
from travel_agent.profile import PROFILE_KEYS, PROFILE_PATH, load_profile
from travel_agent.rates import (
    get_meal_amounts,
    gsa_meal_amounts,
    meal_tier_for_city,
    meal_tier_for_county,
    mileage_object_code,
    mileage_rate_on,
    other_travel_object_code,
    registration_object_code,
    subsistence_object_code,
)

import json

WA_COUNTIES = sorted({
    "adams", "asotin", "benton", "chelan", "clallam", "clark", "columbia",
    "cowlitz", "douglas", "ferry", "franklin", "garfield", "grant",
    "grays harbor", "island", "jefferson", "king", "kitsap", "kittitas",
    "klickitat", "lewis", "lincoln", "mason", "okanogan", "pacific",
    "pend oreille", "pierce", "san juan", "skagit", "skamania", "snohomish",
    "spokane", "stevens", "thurston", "wahkiakum", "walla walla", "whatcom",
    "whitman", "yakima",
})


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(1)
    return val if val else default


def ask_yn(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    val = ask(f"{prompt} ({hint})").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def ask_choice(prompt: str, options: list[tuple[str, str]], default_idx: int = 0) -> str:
    print(f"{prompt}")
    for i, (_, label) in enumerate(options, 1):
        print(f"  {i}. {label}")
    while True:
        val = ask(f"Choose [1-{len(options)}]", str(default_idx + 1))
        if val.isdigit() and 1 <= int(val) <= len(options):
            return options[int(val) - 1][0]
        print("  Enter a number from the list.")


def ask_float(prompt: str, default: float = 0.0) -> float:
    while True:
        val = ask(prompt, f"{default:g}" if default else "0")
        try:
            return round(float(val), 2)
        except ValueError:
            print("  Enter a number.")


def ask_date(prompt: str, default: date) -> date:
    while True:
        val = ask(prompt, default.isoformat())
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                pass
        print("  Use YYYY-MM-DD.")


def money_fmt(n: float) -> str:
    return f"${n:,.2f}"


def name_last_first(full_name: str) -> str:
    parts = full_name.strip().split()
    if len(parts) >= 3:
        return f"{parts[-1]}, {parts[0]}, {parts[1][0]}"
    if len(parts) == 2:
        return f"{parts[1]}, {parts[0]}"
    return full_name


# ---------------------------------------------------------------------------
# Section 1 – Traveler profile
# ---------------------------------------------------------------------------

PROFILE_LABELS = {
    "p_name": "Full name", "p_employee_id": "Employee ID",
    "p_class_title": "Class / title", "p_regular_hours": "Regular work hours",
    "p_official_station": "Official station (duty city)",
    "p_official_residence": "Official residence (home city)",
    "p_address": "Street address", "p_city": "City", "p_state": "State",
    "p_zip": "ZIP", "p_supervisor": "Supervisor name",
    "p_approver": "Approving authority",
}


def run_profile() -> dict:
    section("Section 1 – Traveler profile")
    profile = load_profile()
    if profile.get("p_name"):
        print(f"Loaded saved profile for {profile['p_name']}. Press Enter to keep each value.")
    else:
        print("No saved profile found. Your answers will be saved for next time.")
    if not profile.get("p_state"):
        profile["p_state"] = "WA"
    if not profile.get("p_regular_hours"):
        profile["p_regular_hours"] = "M-F 0800-1700"
    changed = False
    for key in PROFILE_KEYS:
        if key.startswith("p_p") or key in (
            "p_program", "p_work_order", "p_fund", "p_org_code", "p_unit",
            "p_subunit", "p_activity", "p_appr_unit", "p_function", "p_bal_sheet",
        ):
            continue  # charge codes are asked in Section 6
        label = PROFILE_LABELS.get(key, key)
        val = ask(f"  {label}", profile.get(key, ""))
        if val != profile.get(key, ""):
            changed = True
        profile[key] = val
    if changed or not PROFILE_PATH.exists():
        if ask_yn("Save profile for next time?", True):
            data = {k[2:]: profile.get(k, "") for k in PROFILE_KEYS}
            PROFILE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"  Saved to {PROFILE_PATH}")
    return profile


# ---------------------------------------------------------------------------
# Section 2 – Trip basics
# ---------------------------------------------------------------------------

def run_trip_basics() -> dict:
    section("Section 2 – Trip basics")
    scope = ask_choice("Where is the travel?", [
        ("in_state", "In-state (Washington)"),
        ("out_of_state", "Out-of-state (continental US)"),
        ("out_of_country", "Out-of-country (includes Canada)"),
    ])
    event_title = ask("Event / meeting name")
    while not event_title:
        print("  Event name is required.")
        event_title = ask("Event / meeting name")
    dest_city = ask("Destination city")
    while not dest_city:
        print("  Destination is required.")
        dest_city = ask("Destination city")

    tier_total, county, meal, rate_source, dest_state = 68, None, get_meal_amounts(68), "", "WA"
    if scope == "in_state":
        tier_total, county = meal_tier_for_city(dest_city)
        county = county or ""
        print(f"  Local lookup: {dest_city.title()} -> "
              f"{county.title() + ' County' if county else '(county unknown)'} -> ${tier_total} tier")
        if ask_yn("Confirm county via geocoding?", True):
            print("  Geocoding…")
            det = geocode_details(dest_city)
            if det and det.get("state_code") == "WA" and det.get("county"):
                c = det["county"].lower()
                if c in WA_COUNTIES:
                    county = c
                    tier_total = meal_tier_for_county(county)
                    print(f"  Confirmed: {county.title()} County -> ${tier_total} tier")
            else:
                print("  Geocoding failed or outside WA — keeping local lookup.")
        if not county or not ask_yn(f"Use {county.title()} County?", True):
            typed = ask("County name").strip().lower()
            if typed in WA_COUNTIES:
                county = typed
                tier_total = meal_tier_for_county(county)
            else:
                print(f"  Unknown county — defaulting to the ${68} base tier.")
                county, tier_total = typed, 68
        meal = get_meal_amounts(tier_total)
        rate_source = f"OFM rev. 10/1/2026 – {county.title()} County"
    else:
        print("  Looking up GSA per diem…")
        det = geocode_details(dest_city)
        gsa = None
        if det and det.get("state_code"):
            dest_state = det["state_code"]
            gsa = gsa_per_diem(det.get("city", dest_city), dest_state)
        if gsa:
            tier_total = gsa["mie"]
            meal = gsa_meal_amounts(tier_total)
            rate_source = gsa["source"]
            print(f"  GSA M&IE ${tier_total} (B ${meal.breakfast:g} / L ${meal.lunch:g} / D ${meal.dinner:g})")
            print(f"  Source: {rate_source}")
        else:
            print("  GSA lookup failed.")
            mie = ask_float("Enter the M&IE total manually")
            tier_total = int(round(mie))
            meal = gsa_meal_amounts(tier_total)
            rate_source = "Manual M&IE entry"
            print(f"  Split (TPPM 26/29/45): B ${meal.breakfast:g} / L ${meal.lunch:g} / D ${meal.dinner:g}")

    print(f"  Per diem: ${tier_total} — B ${meal.breakfast:g} / L ${meal.lunch:g} / D ${meal.dinner:g} ({rate_source})")

    today = date.today()
    dep = ask_date("Departure date", today)
    ret = ask_date("Return date", dep)
    if ret < dep:
        print("  Return before departure — using departure date.")
        ret = dep
    nights = (ret - dep).days
    days = nights + 1
    overnight = nights > 0
    print(f"  Trip: {days} day{'s' if days > 1 else ''}, {nights} night{'s' if nights != 1 else ''}"
          f" ({'overnight' if overnight else 'same day'})")

    depart_time = ask("Departure time (HHMM)", "0600")
    return_time = ask("Return time (HHMM)", "1800")
    meeting_start = ask("Meeting / event start (HHMM)", "0900")
    meeting_end = ask("Meeting / event end (HHMM)", "1700")
    signature_date = ask_date("Signature date", today)

    return {
        "scope": scope, "event_title": event_title, "dest_city": dest_city,
        "county": county, "tier_total": tier_total, "meal": meal,
        "rate_source": rate_source, "dest_state": dest_state,
        "dep": dep, "ret": ret, "nights": nights, "days": days,
        "overnight": overnight, "depart_time": depart_time,
        "return_time": return_time, "meeting_start": meeting_start,
        "meeting_end": meeting_end, "signature_date": signature_date,
    }


# ---------------------------------------------------------------------------
# Section 3 – Transportation
# ---------------------------------------------------------------------------

def run_transport(trip: dict, profile: dict) -> dict:
    section("Section 3 – Transportation")
    t = ask_choice("How are you getting there?", [
        ("pov", "Personal vehicle (POV)"),
        ("state", "WSDOT / motor pool vehicle"),
        ("rental", "Rental car"),
        ("airline", "Airline"),
        ("rail", "Train / rail / ferry"),
        ("multi", "Multiple / other"),
    ])
    out = {"mode": t, "pov_miles": 0.0, "pov_rate": 0.0, "pov_code": "",
           "pov_reason": "", "pov_from": "", "pov_to": "",
           "airfare": 0.0, "transport_desc": "", "want_map": False}

    if t == "pov":
        state_avail = ask_yn("Was a state / WSDOT vehicle available for this trip?", False)
        rate = mileage_rate_on(trip["dep"], state_avail)
        code = mileage_object_code(state_avail)
        print(f"  Rate: ${rate:.3f}/mi  |  Object code: {code}"
              + (" (elective — state vehicle was available)" if state_avail else " (full rate)"))
        origin = ask("Trip origin (home city / address)", profile.get("p_official_residence", ""))
        dest = ask("Trip destination", trip["dest_city"])
        miles = 0.0
        if ask_yn("Calculate driving miles automatically?", True):
            print("  Calculating route…")
            miles = driving_miles(origin, dest) or 0.0
            if miles:
                print(f"  Route: {miles:.1f} mi one-way")
            else:
                print("  Could not calculate — enter manually.")
        if not miles:
            miles = ask_float("One-way miles")
        rt = miles * 2
        print(f"  Mileage claim (round trip): {money_fmt(rt * rate)}"
              f"  ({miles:.1f} mi x 2 = {rt:.1f} mi x ${rate:.3f})")
        out.update({"pov_miles": miles, "pov_rate": rate, "pov_code": code,
                    "pov_from": origin, "pov_to": dest})
        if not state_avail:
            out["pov_reason"] = ask("Reason POV preferred over state vehicle",
                                    "No state vehicle available at duty station")
        out["want_map"] = ask_yn("Generate a route map PDF to attach?", True)
    elif t == "state":
        print("  No mileage line — vehicle cost runs through the equipment fund (GN01/GN02).")
    elif t == "rental":
        print("  Enter the rental cost in Section 5 as an Other expense (Rental car -> GD01).")
    elif t == "airline":
        out["airfare"] = ask_float("Airfare ($)")
        ac = {"in_state": "GB01", "out_of_state": "GG05", "out_of_country": "GG06"}[trip["scope"]]
        print(f"  Airfare codes to {ac}.")
        out["air_code"] = ac
    elif t == "rail":
        print("  Train / rail / ferry codes to GD01 — enter the fare in Section 5 as Other.")
    else:
        out["transport_desc"] = ask("Describe transportation")
    return out

# ---------------------------------------------------------------------------
# Section 4 – Meals and lodging
# ---------------------------------------------------------------------------

def run_meals_lodging(trip: dict) -> dict:
    section("Section 4 – Meals and lodging")
    meal = trip["meal"]
    sub_code = subsistence_object_code(trip["overnight"], trip["scope"])
    print(f"  Per diem ${trip['tier_total']} - B ${meal.breakfast:g} / L ${meal.lunch:g} / D ${meal.dinner:g}"
          f"  |  Object code: {sub_code}")
    print("  For each day: claim the meal? then was it provided at no cost (deduct)?")

    days = [trip["dep"] + timedelta(days=i) for i in range(trip["days"])]
    per_day = []
    for i, d in enumerate(days):
        tag = ""
        if trip["days"] > 1:
            tag = " (departure)" if i == 0 else (" (return)" if i == len(days) - 1 else "")
        print(f"\n  Day {i + 1} - {d.strftime('%a %m/%d')}{tag}")
        row = {}
        for key, label, amt, dflt in [
            ("b", "Breakfast", meal.breakfast, True),
            ("l", "Lunch", meal.lunch, True),
            ("d", "Dinner", meal.dinner, i < len(days) - 1),
        ]:
            claim = ask_yn(f"    {label} (${amt:g}) in travel status?", dflt)
            provided = ask_yn("      Provided at no cost (deduct)?", False) if claim else False
            row[key] = amt if (claim and not provided) else 0.0
        per_day.append((d, row))

    total = round(sum(r["b"] + r["l"] + r["d"] for _, r in per_day), 2)
    print(f"\n  Total meal reimbursement: {money_fmt(total)}")
    if not trip["overnight"] and total > 0:
        print("  !! Same-day reimbursement (GA02) is TAXABLE income.")
    trip["meals_total"] = total
    trip["meals_per_day"] = per_day
    trip["sub_code"] = sub_code

    lodging_amt, lodge_rate, hotel_name, hotel_city = 0.0, 0.0, "", ""
    if trip["overnight"]:
        print("\n  Lodging")
        hotel_name = ask("  Hotel name")
        hotel_city = ask("  Hotel city", trip["dest_city"])
        lodge_rate = ask_float("  Nightly lodging rate ($)")
        lodging_amt = round(lodge_rate * trip["nights"], 2)
        s = "s" if trip["nights"] != 1 else ""
        print(f"  Total lodging: {money_fmt(lodging_amt)} ({trip['nights']} night{s} x {money_fmt(lodge_rate)})")
    trip["lodging_amt"] = lodging_amt
    trip["lodge_rate"] = lodge_rate
    trip["hotel_name"] = hotel_name
    trip["hotel_city"] = hotel_city
    return trip


# ---------------------------------------------------------------------------
# Section 5 – Registration and other expenses
# ---------------------------------------------------------------------------

def run_other_expenses(trip: dict) -> dict:
    section("Section 5 – Registration and other expenses")
    reg_fee, reg_code = 0.0, "EG02"
    if ask_yn("Registration fee?", False):
        rtype = ask_choice("Registration type", [
            ("conference", "Conference / seminar"),
            ("training", "Training course"),
            ("out_of_state", "Out-of-state (non-bordering)"),
        ])
        reg_fee = ask_float("Registration amount ($)")
        reg_code = registration_object_code(rtype)
        print(f"  Object code: {reg_code}")

    park_amt = ask_float("Parking amount ($)") if ask_yn("Parking?", False) else 0.0

    other_amt, other_code, other_desc = 0.0, "GD01", ""
    if ask_yn("Other reimbursable expenses?", False):
        etype = ask_choice("Expense type", [
            ("taxi", "Taxi"), ("rideshare", "Rideshare"), ("ferry", "Ferry"),
            ("toll", "Toll"), ("bus", "Bus"), ("rail", "Rail"),
            ("rental_car", "Rental car"), ("official_meal", "Official meeting meal"),
            ("other", "Other"),
        ])
        other_desc = ask("Description") or etype.replace("_", " ").title()
        other_amt = ask_float("Amount ($)")
        other_code = other_travel_object_code(etype)
        print(f"  Object code: {other_code}")

    trip.update({"reg_fee": reg_fee, "reg_code": reg_code, "park_amt": park_amt,
                 "other_amt": other_amt, "other_code": other_code,
                 "other_desc": other_desc})
    return trip


# ---------------------------------------------------------------------------
# Section 6 – Charge codes
# ---------------------------------------------------------------------------

CHARGE_LABELS = [
    ("p_program", "Program"), ("p_work_order", "Task Order"), ("p_fund", "Fund"),
    ("p_org_code", "Dept"), ("p_unit", "Unit"), ("p_subunit", "Sub Unit"),
    ("p_activity", "Activity"), ("p_appr_unit", "Appr Unit"),
    ("p_function", "Function"), ("p_bal_sheet", "Bal Sheet"),
]


def run_charge_codes(profile: dict) -> dict:
    section("Section 6 - Charge codes")
    print("  Object code is filled automatically. Charge fields reuse your saved profile.")
    for key, label in CHARGE_LABELS:
        profile[key] = ask(f"  {label}", profile.get(key, ""))
    advance = ask_float("Travel advance received ($)")
    remarks = ask("Remarks (expense voucher)",
                  "Registration and mileage entered from approved travel request.")
    comments = ask("Comments (travel request - transport / hotel details)")
    profile["_travel_advance"] = advance
    profile["_remarks"] = remarks
    profile["_comments"] = comments
    return profile


# ---------------------------------------------------------------------------
# Payload builder (same shape as the Streamlit app build_payload)
# ---------------------------------------------------------------------------

def build_payload(profile: dict, trip: dict, trans: dict) -> dict:
    base = {
        "program": profile.get("p_program", ""), "work_order": profile.get("p_work_order", ""),
        "fund": profile.get("p_fund", ""), "org_code": profile.get("p_org_code", ""),
        "unit": profile.get("p_unit", ""), "subunit": profile.get("p_subunit", ""),
        "activity": profile.get("p_activity", ""), "appropriation": profile.get("p_appr_unit", ""),
        "function": profile.get("p_function", ""), "bal_sheet": profile.get("p_bal_sheet", ""),
    }
    days = trip["days"]
    per_day = trip["meals_per_day"]
    origin = trans["pov_from"] or profile.get("p_official_residence", "")
    dest_to = trans["pov_to"] or trip["dest_city"]
    one_way = trans["pov_miles"]

    def fdt(d: date, t: str) -> str:
        return f"{d.strftime('%m/%d/%y')} {t}".strip()

    daily = []
    for i, (d, row) in enumerate(per_day):
        first, last = i == 0, i == len(per_day) - 1
        daily.append({
            "date": d.isoformat(),
            "trip_from": origin if first else trip["dest_city"],
            "trip_to": dest_to if first else (origin if last else trip["dest_city"]),
            "depart": trip["depart_time"] if first else "",
            "return_time": trip["return_time"] if last else "",
            "breakfast": row["b"], "lunch": row["l"], "dinner": row["d"],
            "lodging": trip["lodge_rate"] if (trip["overnight"] and not last) else 0.0,
            "miles": (one_way * 2 if not trip["overnight"] else one_way)
                     if (trans["mode"] == "pov" and first) else 0.0,
            "mileage_rate": trans["pov_rate"] if (trans["mode"] == "pov" and first) else 0.0,
            "pov_reason": trans["pov_reason"] if (trans["mode"] == "pov" and first) else "",
            "purpose": trip["event_title"],
        })
    if trans["mode"] == "pov" and one_way > 0 and trip["overnight"]:
        daily.append({
            "date": trip["ret"].isoformat(), "trip_from": dest_to, "trip_to": origin,
            "depart": "", "return_time": trip["return_time"],
            "breakfast": 0.0, "lunch": 0.0, "dinner": 0.0, "lodging": 0.0,
            "miles": one_way, "mileage_rate": trans["pov_rate"],
            "pov_reason": trans["pov_reason"], "purpose": trip["event_title"],
        })

    accounts = []
    if trip["reg_fee"] > 0:
        accounts.append({**base, "object_code": trip["reg_code"], "amount": trip["reg_fee"]})
    if trip["meals_total"] > 0:
        accounts.append({**base, "object_code": trip["sub_code"], "amount": trip["meals_total"]})
    if trip["lodging_amt"] > 0:
        accounts.append({**base, "object_code": "GA01", "amount": trip["lodging_amt"]})
    if trans["mode"] == "pov" and one_way > 0:
        accounts.append({**base, "object_code": trans["pov_code"],
                         "amount": round(one_way * 2 * trans["pov_rate"], 2)})
    if trans.get("airfare", 0) > 0:
        accounts.append({**base, "object_code": trans.get("air_code", "GB01"),
                         "amount": trans["airfare"]})
    if trip["park_amt"] > 0:
        accounts.append({**base, "object_code": "GD01", "amount": trip["park_amt"]})
    if trip["other_amt"] > 0:
        accounts.append({**base, "object_code": trip["other_code"], "amount": trip["other_amt"]})

    others = []
    if trip["reg_fee"] > 0:
        others.append({"date": trip["dep"].isoformat(), "paid_to": trip["event_title"][:40],
                       "for_what": "Registration", "amount": trip["reg_fee"]})
    if trip["park_amt"] > 0:
        others.append({"date": trip["ret"].isoformat(), "paid_to": "Parking",
                       "for_what": "Parking", "amount": trip["park_amt"]})
    if trip["other_amt"] > 0:
        others.append({"date": trip["dep"].isoformat(), "paid_to": trip["other_desc"],
                       "for_what": trip["other_desc"], "amount": trip["other_amt"]})

    t = profile
    pm = trans["mode"]
    return {
        "traveler": {
            "name": t.get("p_name", ""),
            "name_last_first_initial": name_last_first(t.get("p_name", "")),
            "employee_id": t.get("p_employee_id", ""), "class_title": t.get("p_class_title", ""),
            "address": t.get("p_address", ""), "city": t.get("p_city", ""),
            "state": t.get("p_state", "WA") or "WA", "zip_code": t.get("p_zip", ""),
            "official_station": t.get("p_official_station", ""),
            "official_residence": t.get("p_official_residence", ""),
            "regular_work_hours": t.get("p_regular_hours", ""),
            "supervisor_name": t.get("p_supervisor", ""),
            "approving_authority_name": t.get("p_approver", ""),
        },
        "event_title": trip["event_title"], "destination_city": trip["dest_city"],
        "departure_datetime": fdt(trip["dep"], trip["depart_time"]),
        "return_datetime": fdt(trip["ret"], trip["return_time"]),
        "meeting_begin_datetime": fdt(trip["dep"], trip["meeting_start"]),
        "meeting_end_datetime": fdt(trip["ret"], trip["meeting_end"]),
        "payment_methods": (
            ["Other"] if pm == "pov" else
            ["Car Rental"] if pm == "rental" else
            ["Airline travel"] if pm == "airline" else
            ["TrainRailFerry"] if pm == "rail" else ["Other"]),
        "other_payment_method_description": "Mileage" if pm == "pov" else trans.get("transport_desc", ""),
        "registration_fee": trip["reg_fee"], "airfare": trans.get("airfare", 0.0),
        "subsistence_days": days if trip["meals_total"] > 0 else None,
        "subsistence_rate": round(trip["meals_total"] / days, 2) if (trip["meals_total"] > 0 and days) else None,
        "lodging_days": trip["nights"] if trip["overnight"] else 0,
        "lodging_rate": trip["lodge_rate"] if trip["overnight"] else 0.0,
        "hotel_name": trip["hotel_name"], "hotel_city": trip["hotel_city"],
        "comments": t.get("_comments", ""), "remarks": t.get("_remarks", ""),
        "signature_date": trip["signature_date"].isoformat(),
        "travel_advance": t.get("_travel_advance", 0.0), "request_other_fees": 0.0,
        "daily_expenses": daily, "account_codes": accounts, "other_expenses": others,
    }


# ---------------------------------------------------------------------------
# Section 7 – Review and generate
# ---------------------------------------------------------------------------

def summary_lines(trip: dict, trans: dict):
    lines = []
    if trip["meals_total"] > 0:
        lines.append(("Meals", trip["sub_code"], trip["meals_total"]))
    if trip["lodging_amt"] > 0:
        lines.append((f"Lodging ({trip['nights']}n)", "GA01", trip["lodging_amt"]))
    if trans["mode"] == "pov" and trans["pov_miles"] > 0:
        rt = trans["pov_miles"] * 2
        lines.append((f"Mileage ({rt:.1f} mi)", trans["pov_code"], round(rt * trans["pov_rate"], 2)))
    if trip["reg_fee"] > 0:
        lines.append(("Registration", trip["reg_code"], trip["reg_fee"]))
    if trans.get("airfare", 0) > 0:
        lines.append(("Airfare", trans.get("air_code", "GB01"), trans["airfare"]))
    if trip["park_amt"] > 0:
        lines.append(("Parking", "GD01", trip["park_amt"]))
    if trip["other_amt"] > 0:
        lines.append((trip["other_desc"], trip["other_code"], trip["other_amt"]))
    return lines


def run_review(profile: dict, trip: dict, trans: dict, out_dir: Path) -> None:
    section("Section 7 – Review and generate")
    county_bit = f" - {trip['county'].title()} County" if trip["scope"] == "in_state" and trip["county"] else ""
    print(f"  Event: {trip['event_title']}")
    print(f"  Destination: {trip['dest_city'].title()}{county_bit}")
    print(f"  Dates: {trip['dep']} -> {trip['ret']} ({trip['days']}d/{trip['nights']}n)")
    print("  Forms: Travel Request (PDF) + Expense Voucher (XLSX)")
    print("\n  Expense lines:")
    lines = summary_lines(trip, trans)
    for label, code, amt in lines:
        print(f"    - {label}: {money_fmt(amt)} [{code}]")
    grand = round(sum(a for _, _, a in lines), 2)
    print(f"\n  Estimated total: {money_fmt(grand)}")
    if not trip["overnight"] and trip["meals_total"] > 0:
        print("  !! Same-day meals are taxable (GA02).")

    if not ask_yn("Generate the forms?", True):
        print("  Discarded - nothing was written.")
        return

    payload = build_payload(profile, trip, trans)
    intake = TravelIntake.from_dict(payload)
    missing = intake.validate()
    if missing:
        print("  Missing required fields: " + ", ".join(missing))
        return

    agent = TravelFormAgent(
        travel_request_template=BASE / "templates" / "travel_request_template.pdf",
        expense_voucher_template=BASE / "templates" / "133-103_template.xlsx",
        output_dir=out_dir,
    )
    outputs = agent.run(intake)
    print("\n  Generated:")
    for label, path in outputs.items():
        if label == "warnings":
            continue
        print(f"    {label}: {path}")
    for w in outputs.get("warnings", []):
        print(f"  !! {w}")

    if trans["mode"] == "pov" and trans["want_map"] and trans["pov_from"] and trans["pov_to"]:
        print("  Generating route map...")
        pdf_bytes = route_map_pdf(trans["pov_from"], trans["pov_to"])
        if pdf_bytes:
            safe = "".join(c if c.isalnum() else "_" for c in trip["event_title"])[:40]
            map_path = out_dir / f"route_map_{safe}.pdf"
            map_path.write_bytes(pdf_bytes)
            print(f"    route_map_pdf: {map_path}")
        else:
            print("    Route map failed (offline?) - attach a map manually.")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="WSDOT travel form wizard - guided intake, generates the filled PDF + XLSX.")
    parser.add_argument("--out-dir", default=str(BASE / "outputs"),
                        help="Directory for generated forms (default: ./outputs)")
    args = parser.parse_args()

    print("\n  WSDOT Travel Form Agent - guided intake (no Streamlit needed)")
    profile = run_profile()
    trip = run_trip_basics()
    trans = run_transport(trip, profile)
    trip = run_meals_lodging(trip)
    trip = run_other_expenses(trip)
    profile = run_charge_codes(profile)
    run_review(profile, trip, trans, Path(args.out_dir))


if __name__ == "__main__":
    main()
