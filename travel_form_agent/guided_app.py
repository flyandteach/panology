"""Guided intake form for WSDOT Travel Request and Expense Voucher generation."""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

import streamlit as st

from travel_agent import TravelFormAgent, TravelIntake
from travel_agent.rates import (
    get_meal_amounts,
    meal_tier_for_city,
    mileage_object_code,
    mileage_rate,
    other_travel_object_code,
    registration_object_code,
    subsistence_object_code,
    POV_FULL_RATE,
    POV_ELECTIVE_RATE,
)

BASE = Path(__file__).resolve().parent

st.set_page_config(page_title="WSDOT Travel Form Agent", layout="wide", initial_sidebar_state="collapsed")
st.title("WSDOT Travel Form Agent")
st.caption("Fill out the form below. The agent resolves meal tiers, object codes, and mileage, then produces your completed WSDOT forms.")

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def ss(key, default=None):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_guided, tab_json = st.tabs(["Guided Form", "JSON Upload"])

# ===========================================================================
# GUIDED FORM TAB
# ===========================================================================
with tab_guided:
    # -----------------------------------------------------------------------
    # Section 1 – Traveler (standing info, reused across trips)
    # -----------------------------------------------------------------------
    with st.expander("Section 1 – Traveler (saved between trips)", expanded=True):
        c1, c2 = st.columns(2)
        traveler_name = c1.text_input("Full name", value=ss("t_name", ""), key="t_name")
        traveler_name_lfi = c2.text_input("Last, First, M.I.", value=ss("t_name_lfi", ""), key="t_name_lfi",
                                           placeholder="Smith, Jane, A")
        c1b, c2b, c3b = st.columns(3)
        employee_id = c1b.text_input("Employee ID", value=ss("t_emp_id", ""), key="t_emp_id")
        class_title = c2b.text_input("Class / title", value=ss("t_class", ""), key="t_class", placeholder="TPS-4")
        regular_hours = c3b.text_input("Regular work hours", value=ss("t_hours", "M-F 0800-1700"), key="t_hours")
        c1c, c2c = st.columns(2)
        official_station = c1c.text_input("Official station (duty city)", value=ss("t_station", ""), key="t_station",
                                           placeholder="OLYMPIA")
        official_residence = c2c.text_input("Official residence (home city)", value=ss("t_residence", ""),
                                             key="t_residence", placeholder="CAMAS")
        address = c1.text_input("Street address", value=ss("t_address", ""), key="t_address")
        c1d, c2d, c3d = st.columns([3, 1, 1])
        addr_city = c1d.text_input("City", value=ss("t_city", ""), key="t_city")
        addr_state = c2d.text_input("State", value=ss("t_state", "WA"), key="t_state", max_chars=2)
        addr_zip = c3d.text_input("ZIP", value=ss("t_zip", ""), key="t_zip")
        c1e, c2e = st.columns(2)
        supervisor = c1e.text_input("Supervisor name", value=ss("t_supervisor", ""), key="t_supervisor")
        approver = c2e.text_input("Approving authority", value=ss("t_approver", ""), key="t_approver")

    # -----------------------------------------------------------------------
    # Section 2 – Trip basics
    # -----------------------------------------------------------------------
    with st.expander("Section 2 – Trip basics", expanded=True):
        form_type = st.radio(
            "What are you filling out?",
            ["Before the trip (Travel Request)", "After the trip (Expense Voucher / 133-103)"],
            horizontal=True,
        )
        is_before_trip = form_type.startswith("Before")

        scope = st.radio(
            "Where is the travel?",
            ["In-state (Washington)", "Out-of-state (continental US)", "Out-of-country (includes Canada)"],
            horizontal=True,
        )
        scope_key = "in_state" if scope.startswith("In") else ("out_of_state" if scope.startswith("Out-of-s") else "out_of_country")

        overnight = st.radio("Does the trip include an overnight stay?", ["No – same day", "Yes – overnight"],
                             horizontal=True)
        is_overnight = overnight.startswith("Yes")

        event_title = st.text_input("Event / meeting name", placeholder="AAAE ACT/BFI Innovation Event")
        destination_city = st.text_input("Destination city (or ZIP)", placeholder="Seattle")

        # Auto-resolve county and meal tier
        tier_total = 68
        county_resolved = None
        if destination_city:
            tier_total, county_resolved = meal_tier_for_city(destination_city)
            meal = get_meal_amounts(tier_total)
            county_label = county_resolved.title() if county_resolved else "unknown"
            st.info(
                f"**Destination:** {county_label} County → **meal tier ${tier_total}** "
                f"(B ${meal.breakfast:.0f} / L ${meal.lunch:.0f} / D ${meal.dinner:.0f})"
                + ("" if county_resolved else "  \n⚠️ County not recognized – defaulting to base $68 tier. Verify manually.")
            )

        col_d1, col_d2 = st.columns(2)
        travel_date = col_d1.date_input("Travel date (first day)", value=date.today())
        return_date = col_d2.date_input("Return date", value=date.today())

        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        depart_time = col_t1.text_input("Departure time", value="0600", placeholder="0600")
        return_time = col_t2.text_input("Return time", value="1800", placeholder="1800")
        meeting_start = col_t3.text_input("Meeting start", value="0900", placeholder="0900")
        meeting_end = col_t4.text_input("Meeting end", value="1700", placeholder="1700")

        travel_date_str = travel_date.strftime("%m/%d/%y")
        return_date_str = return_date.strftime("%m/%d/%y")
        departure_datetime = f"{travel_date_str} {depart_time}"
        return_datetime = f"{return_date_str} {return_time}"
        meeting_begin_datetime = f"{travel_date_str} {meeting_start}"
        meeting_end_datetime = f"{return_date_str} {meeting_end}"

        signature_date = st.date_input("Signature date", value=date.today())

    # -----------------------------------------------------------------------
    # Section 3 – Transportation
    # -----------------------------------------------------------------------
    with st.expander("Section 3 – Transportation", expanded=True):
        transport = st.radio(
            "How are you getting there?",
            ["Personal vehicle (POV)", "WSDOT / motor pool vehicle", "Rental car", "Airline", "Train / rail / ferry",
             "Multiple / other"],
            horizontal=False,
        )

        state_vehicle_available = False
        pov_miles = 0.0
        pov_from = ""
        pov_to = ""
        pov_rate_used = POV_FULL_RATE
        pov_code = "GC01"
        pov_reason = ""
        transport_payment_methods: List[str] = []
        transport_other_desc = ""

        if transport == "Personal vehicle (POV)":
            state_vehicle_available = st.checkbox("Was a state / WSDOT vehicle available for this trip?",
                                                  help="If yes, you claim the elective rate GC02 ($0.205/mi) instead of the full rate GC01 ($0.725/mi).")
            pov_rate_used = POV_ELECTIVE_RATE if state_vehicle_available else POV_FULL_RATE
            pov_code = mileage_object_code(state_vehicle_available)
            rate_label = f"${pov_rate_used:.3f}/mi ({'elective GC02' if state_vehicle_available else 'full GC01'})"
            st.caption(f"Mileage rate: {rate_label}")

            mc1, mc2 = st.columns(2)
            pov_from = mc1.text_input("Trip origin", placeholder="Camas")
            pov_to = mc2.text_input("Trip destination", placeholder="Seattle/BFI")
            pov_miles = st.number_input("One-way miles (verify with odometer or Google Maps)", min_value=0.0, step=0.1)
            st.caption(f"Mileage claim: {pov_miles:.1f} mi × ${pov_rate_used:.3f} = **${pov_miles * pov_rate_used:.2f}**")
            if state_vehicle_available:
                pov_reason = ""
            else:
                pov_reason = st.text_input("Reason POV preferred over state vehicle", placeholder="No state vehicle available at duty station")
            transport_payment_methods = ["Other"]
            transport_other_desc = "Mileage"

        elif transport in ("WSDOT / motor pool vehicle",):
            st.info("No mileage claimed on your Travel Request – vehicle cost rides through the equipment fund (GN01/GN02) on a journal voucher.")
            transport_payment_methods = []

        elif transport == "Rental car":
            transport_payment_methods = ["Car Rental"]

        elif transport == "Airline":
            transport_payment_methods = ["Airline travel"]

        elif transport == "Train / rail / ferry":
            transport_payment_methods = ["TrainRailFerry"]

        else:
            transport_payment_methods = ["Other"]
            transport_other_desc = st.text_input("Describe other transportation")

    # -----------------------------------------------------------------------
    # Section 4 – Meals
    # -----------------------------------------------------------------------
    with st.expander("Section 4 – Meals", expanded=True):
        meal = get_meal_amounts(tier_total)
        st.caption(f"Meal tier: ${tier_total} | B ${meal.breakfast:.0f} / L ${meal.lunch:.0f} / D ${meal.dinner:.0f}")

        col_m1, col_m2, col_m3 = st.columns(3)
        claim_breakfast = col_m1.checkbox(f"Breakfast (${meal.breakfast:.0f}) – in travel status?")
        claim_lunch = col_m2.checkbox(f"Lunch (${meal.lunch:.0f}) – in travel status?")
        claim_dinner = col_m3.checkbox(f"Dinner (${meal.dinner:.0f}) – in travel status?")

        col_p1, col_p2, col_p3 = st.columns(3)
        prov_breakfast = col_p1.checkbox("Breakfast provided (deduct)", disabled=not claim_breakfast)
        prov_lunch = col_p2.checkbox("Lunch provided (deduct)", disabled=not claim_lunch)
        prov_dinner = col_p3.checkbox("Dinner provided (deduct)", disabled=not claim_dinner)

        breakfast_amt = meal.breakfast if (claim_breakfast and not prov_breakfast) else 0.0
        lunch_amt = meal.lunch if (claim_lunch and not prov_lunch) else 0.0
        dinner_amt = meal.dinner if (claim_dinner and not prov_dinner) else 0.0
        meal_total = round(breakfast_amt + lunch_amt + dinner_amt, 2)
        st.metric("Meal reimbursement", f"${meal_total:.2f}")

        if not is_overnight and meal_total > 0:
            st.warning("Same-day meal reimbursement (GA02) is **taxable income**. Confirm you were in travel status for each claimed meal period.")

        subsistence_code = subsistence_object_code(is_overnight, scope_key)
        st.caption(f"Object code: **{subsistence_code}**")

        # Lodging (overnight only)
        lodging_amt = 0.0
        lodging_rate_val = 0.0
        hotel_name = ""
        hotel_city = ""
        if is_overnight:
            st.markdown("**Lodging**")
            lc1, lc2 = st.columns(2)
            hotel_name = lc1.text_input("Hotel name")
            hotel_city = lc2.text_input("Hotel city")
            lodging_rate_val = st.number_input("Nightly lodging rate ($)", min_value=0.0, step=1.0)
            num_nights = st.number_input("Number of nights", min_value=1, step=1, value=1)
            lodging_amt = lodging_rate_val * num_nights

    # -----------------------------------------------------------------------
    # Section 5 – Registration / other expenses
    # -----------------------------------------------------------------------
    with st.expander("Section 5 – Registration and other expenses", expanded=True):
        has_registration = st.checkbox("Registration fee?")
        registration_fee = 0.0
        reg_code = "EG02"
        if has_registration:
            reg_type = st.selectbox("Registration type", ["conference", "training", "out_of_state"])
            registration_fee = st.number_input("Registration amount ($)", min_value=0.0, step=1.0)
            reg_code = registration_object_code(reg_type)
            st.caption(f"Object code: **{reg_code}**")
            reg_event_url = st.text_input("Event URL (optional – paste for recordkeeping)")

        has_parking = st.checkbox("Parking?")
        parking_amt = 0.0
        if has_parking:
            parking_amt = st.number_input("Parking amount ($)", min_value=0.0, step=1.0)

        has_other = st.checkbox("Other reimbursable expenses?")
        other_desc = ""
        other_amt = 0.0
        other_code = "GD01"
        if has_other:
            other_exp_type = st.selectbox("Expense type",
                                          ["taxi", "ferry", "toll", "bus", "rail", "rental_car", "official_meal", "other"])
            other_desc = st.text_input("Description")
            other_amt = st.number_input("Amount ($)", min_value=0.0, step=1.0)
            other_code = other_travel_object_code(other_exp_type)
            st.caption(f"Object code: **{other_code}**")

        airfare_amt = 0.0
        if transport == "Airline":
            airfare_amt = st.number_input("Airfare ($)", min_value=0.0, step=1.0)

    # -----------------------------------------------------------------------
    # Section 6 – Account / charge codes
    # -----------------------------------------------------------------------
    with st.expander("Section 6 – Charge codes (work order, org code, etc.)", expanded=True):
        st.caption("Enter your primary work order and org code. The agent fills the object code column automatically.")
        acc1, acc2, acc3 = st.columns(3)
        work_order = acc1.text_input("Work order", value=ss("acc_wo", ""), key="acc_wo")
        group_code = acc2.text_input("Group", value=ss("acc_group", ""), key="acc_group", placeholder="02")
        work_op = acc3.text_input("Work op", value=ss("acc_wop", ""), key="acc_wop", placeholder="0605")
        org_code = st.text_input("Org code", value=ss("acc_org", ""), key="acc_org", placeholder="691010")
        travel_advance = st.number_input("Travel advance received ($)", min_value=0.0, step=1.0)
        remarks = st.text_area("Remarks (expense voucher)", placeholder="Registration and mileage entered from approved travel request.")
        comments = st.text_area("Comments (travel request – transport / hotel details)",
                                placeholder="Drive personal vehicle to avoid delays. Home to/from HQ at GC01 (XX miles × $0.725 = $XX).")

    # -----------------------------------------------------------------------
    # Build payload
    # -----------------------------------------------------------------------
    def build_payload():
        traveler = {
            "name": traveler_name,
            "name_last_first_initial": traveler_name_lfi,
            "employee_id": employee_id,
            "class_title": class_title,
            "address": address,
            "city": addr_city,
            "state": addr_state,
            "zip_code": addr_zip,
            "official_station": official_station,
            "official_residence": official_residence,
            "regular_work_hours": regular_hours,
            "supervisor_name": supervisor,
            "approving_authority_name": approver,
        }

        daily_expenses = []
        if transport == "Personal vehicle (POV)" and pov_miles > 0:
            daily_expenses.append({
                "date": travel_date.strftime("%Y-%m-%d"),
                "trip_from": pov_from or official_residence,
                "trip_to": pov_to or destination_city,
                "depart": depart_time,
                "return_time": return_time if travel_date == return_date else "",
                "breakfast": breakfast_amt,
                "lunch": lunch_amt,
                "dinner": dinner_amt,
                "lodging": lodging_amt if is_overnight else 0.0,
                "miles": pov_miles,
                "mileage_rate": pov_rate_used,
                "pov_reason": pov_reason,
                "purpose": event_title,
            })
        else:
            daily_expenses.append({
                "date": travel_date.strftime("%Y-%m-%d"),
                "trip_from": official_residence or official_station,
                "trip_to": destination_city,
                "depart": depart_time,
                "return_time": return_time if travel_date == return_date else "",
                "breakfast": breakfast_amt,
                "lunch": lunch_amt,
                "dinner": dinner_amt,
                "lodging": lodging_amt if is_overnight else 0.0,
                "miles": 0.0,
                "mileage_rate": 0.0,
                "pov_reason": "",
                "purpose": event_title,
            })

        # Build account code lines in object-code order
        account_codes = []
        base_acct = {"work_order": work_order, "group": group_code, "work_op": work_op, "org_code": org_code}

        if registration_fee > 0:
            account_codes.append({**base_acct, "object_code": reg_code, "amount": registration_fee})
        if meal_total > 0:
            account_codes.append({**base_acct, "object_code": subsistence_code, "amount": meal_total})
        if transport == "Personal vehicle (POV)" and pov_miles > 0:
            mileage_amt = round(pov_miles * pov_rate_used, 2)
            account_codes.append({**base_acct, "object_code": pov_code, "amount": mileage_amt})
        if parking_amt > 0:
            account_codes.append({**base_acct, "object_code": "GD01", "amount": parking_amt})
        if other_amt > 0:
            account_codes.append({**base_acct, "object_code": other_code, "amount": other_amt})

        other_expenses = []
        if registration_fee > 0:
            other_expenses.append({
                "date": travel_date.strftime("%Y-%m-%d"),
                "paid_to": event_title[:40],
                "for_what": "Registration",
                "amount": registration_fee,
            })
        if parking_amt > 0:
            other_expenses.append({
                "date": travel_date.strftime("%Y-%m-%d"),
                "paid_to": "Parking",
                "for_what": "Parking",
                "amount": parking_amt,
            })
        if other_amt > 0:
            other_expenses.append({
                "date": travel_date.strftime("%Y-%m-%d"),
                "paid_to": other_desc or other_exp_type,
                "for_what": other_desc or other_exp_type,
                "amount": other_amt,
            })

        # Subsistence days/rate for travel request summary
        num_days = (return_date - travel_date).days + 1
        sub_days = num_days if meal_total > 0 else 0
        sub_rate = meal_total / num_days if (meal_total > 0 and num_days > 0) else 0

        return {
            "traveler": traveler,
            "event_title": event_title,
            "destination_city": destination_city,
            "departure_datetime": departure_datetime,
            "return_datetime": return_datetime,
            "meeting_begin_datetime": meeting_begin_datetime,
            "meeting_end_datetime": meeting_end_datetime,
            "payment_methods": transport_payment_methods,
            "other_payment_method_description": transport_other_desc,
            "registration_fee": registration_fee,
            "airfare": airfare_amt,
            "subsistence_days": sub_days if meal_total > 0 else None,
            "subsistence_rate": round(meal_total / sub_days, 2) if sub_days > 0 else None,
            "lodging_days": (return_date - travel_date).days if is_overnight else 0,
            "lodging_rate": lodging_rate_val if is_overnight else 0,
            "hotel_name": hotel_name,
            "hotel_city": hotel_city,
            "comments": comments,
            "remarks": remarks,
            "signature_date": signature_date.strftime("%Y-%m-%d"),
            "travel_advance": travel_advance,
            "daily_expenses": daily_expenses,
            "account_codes": account_codes,
            "other_expenses": other_expenses,
            "request_other_fees": 0.0,
        }

    # -----------------------------------------------------------------------
    # Section 7 – Review and generate
    # -----------------------------------------------------------------------
    with st.expander("Section 7 – Review and generate", expanded=True):
        if st.button("Review trip summary", use_container_width=True):
            if not traveler_name:
                st.error("Enter your name in Section 1.")
            elif not event_title:
                st.error("Enter the event name in Section 2.")
            elif not destination_city:
                st.error("Enter the destination in Section 2.")
            else:
                payload = build_payload()
                mileage_display = ""
                if transport == "Personal vehicle (POV)" and pov_miles > 0:
                    mileage_display = f"\n- **Mileage:** {pov_miles:.1f} mi × ${pov_rate_used:.3f} = **${pov_miles * pov_rate_used:.2f}** ({pov_code})"

                reg_display = f"\n- **Registration:** ${registration_fee:.2f} ({reg_code})" if registration_fee > 0 else ""
                park_display = f"\n- **Parking:** ${parking_amt:.2f} (GD01)" if parking_amt > 0 else ""
                other_display = f"\n- **{other_desc or 'Other'}:** ${other_amt:.2f} ({other_code})" if other_amt > 0 else ""

                st.markdown(f"""
**Event:** {event_title}
**Destination:** {destination_city}{f' — {county_resolved.title()} County' if county_resolved else ''}
**Dates:** {travel_date_str} → {return_date_str}
**Form:** {'Travel Request' if is_before_trip else 'Expense Voucher'}

---
**Expense lines:**
- **Meals:** ${meal_total:.2f} ({subsistence_code}){'  ⚠️ taxable (same-day)' if not is_overnight and meal_total > 0 else ''}{mileage_display}{reg_display}{park_display}{other_display}

**Total estimated:** ${sum(a.get('amount', 0) for a in payload['account_codes']):.2f}
""")
                st.json(payload, expanded=False)
                st.session_state["_payload"] = payload

        if st.button("Generate forms", type="primary", use_container_width=True):
            if not traveler_name or not event_title or not destination_city:
                st.error("Complete Sections 1–2 before generating.")
            else:
                payload = build_payload()
                try:
                    intake = TravelIntake.from_dict(payload)
                    missing = intake.validate()
                    if missing:
                        st.error("Missing required fields: " + ", ".join(missing))
                    else:
                        with tempfile.TemporaryDirectory() as td:
                            td_path = Path(td)
                            req_tpl = td_path / "travel_request_template.pdf"
                            exp_tpl = td_path / "133-103_template.xlsx"
                            req_tpl.write_bytes((BASE / "templates" / "travel_request_template.pdf").read_bytes())
                            exp_tpl.write_bytes((BASE / "templates" / "133-103_template.xlsx").read_bytes())

                            agent = TravelFormAgent(req_tpl, exp_tpl, td_path / "outputs")
                            outputs = agent.run(intake)
                            pdf_bytes = outputs["travel_request_pdf"].read_bytes()
                            xlsx_bytes = outputs["expense_voucher_xlsx"].read_bytes()

                        safe = "".join(c if c.isalnum() else "_" for c in event_title)[:40]
                        st.success("Forms generated.")
                        dl1, dl2 = st.columns(2)
                        dl1.download_button(
                            "Download Travel Request PDF",
                            pdf_bytes,
                            f"travel_request_{safe}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                        dl2.download_button(
                            "Download Expense Voucher XLSX",
                            xlsx_bytes,
                            f"expense_voucher_{safe}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )
                        with st.expander("View intake JSON"):
                            st.json(payload)
                except Exception as e:
                    st.error(str(e))
                    raise

# ===========================================================================
# JSON UPLOAD TAB (original flow, unchanged)
# ===========================================================================
with tab_json:
    st.subheader("JSON Upload")
    st.write("Upload or paste a travel-intake JSON file to generate forms directly.")

    with st.expander("Expected JSON shape", expanded=False):
        example_path = BASE / "examples" / "bfi_travel_intake.json"
        if example_path.exists():
            st.code(example_path.read_text(encoding="utf-8"), language="json")

    uploaded = st.file_uploader("Travel intake JSON", type=["json"], key="json_upload")
    text = st.text_area("Or paste travel intake JSON", height=260, key="json_text")
    travel_request_template_json = st.file_uploader("Travel request PDF template (override)", type=["pdf"],
                                                     key="pdf_tpl")
    expense_template_json = st.file_uploader("133-103 XLSX template (override)", type=["xlsx"], key="xlsx_tpl")

    if st.button("Generate forms from JSON", key="json_gen"):
        try:
            if uploaded is not None:
                payload_json = json.loads(uploaded.read().decode("utf-8"))
            elif text.strip():
                payload_json = json.loads(text)
            else:
                st.error("Provide a travel-intake JSON file or paste JSON.")
                st.stop()

            with tempfile.TemporaryDirectory() as td:
                td_path = Path(td)
                req_tpl = td_path / "travel_request_template.pdf"
                exp_tpl = td_path / "133-103_template.xlsx"
                if travel_request_template_json:
                    req_tpl.write_bytes(travel_request_template_json.read())
                else:
                    req_tpl.write_bytes((BASE / "templates" / "travel_request_template.pdf").read_bytes())
                if expense_template_json:
                    exp_tpl.write_bytes(expense_template_json.read())
                else:
                    exp_tpl.write_bytes((BASE / "templates" / "133-103_template.xlsx").read_bytes())

                intake = TravelIntake.from_dict(payload_json)
                agent = TravelFormAgent(req_tpl, exp_tpl, td_path / "outputs")
                outputs = agent.run(intake)
                pdf_bytes = outputs["travel_request_pdf"].read_bytes()
                xlsx_bytes = outputs["expense_voucher_xlsx"].read_bytes()

            st.success("Forms generated.")
            st.download_button("Download travel request PDF", pdf_bytes, "travel_request.pdf",
                               mime="application/pdf")
            st.download_button("Download travel expense voucher XLSX", xlsx_bytes,
                               "travel_expense_voucher.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.error(str(e))
