"""WSDOT Travel Form Agent – guided intake form."""

from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

import streamlit as st

from travel_agent import TravelFormAgent, TravelIntake
from travel_agent.geo import driving_miles, route_map_pdf, route_map_png
from travel_agent.profile import PROFILE_KEYS, load_profile, save_profile
from travel_agent.rates import (
    POV_ELECTIVE_RATE,
    POV_FULL_RATE,
    get_meal_amounts,
    meal_tier_for_city,
    mileage_object_code,
    mileage_rate,
    other_travel_object_code,
    registration_object_code,
    subsistence_object_code,
)

BASE = Path(__file__).resolve().parent


def _name_last_first(full_name: str) -> str:
    """'David Charles Ison' → 'Ison, David, C'   |   'David Ison' → 'Ison, David'"""
    parts = full_name.strip().split()
    if len(parts) >= 3:
        return f"{parts[-1]}, {parts[0]}, {parts[1][0]}"
    if len(parts) == 2:
        return f"{parts[1]}, {parts[0]}"
    return full_name

st.set_page_config(page_title="WSDOT Travel Form Agent", layout="wide", initial_sidebar_state="collapsed")
st.title("WSDOT Travel Form Agent")
st.caption("Fill in the trip details and click Generate. Meal tiers, object codes, days/nights, and mileage are all computed automatically.")

# ---------------------------------------------------------------------------
# Load saved profile into session state on first run.
# IMPORTANT: we set st.session_state[key] BEFORE the widgets render so that
# the key= parameter on each text_input picks up the saved value.
# ---------------------------------------------------------------------------
if "_profile_loaded" not in st.session_state:
    profile = load_profile()   # returns dict keyed p_name, p_employee_id, …
    for key in PROFILE_KEYS:
        st.session_state[key] = profile.get(key, "")
    if not st.session_state.get("p_state"):
        st.session_state["p_state"] = "WA"
    if not st.session_state.get("p_regular_hours"):
        st.session_state["p_regular_hours"] = "M-F 0800-1700"
    st.session_state["_profile_loaded"] = True

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_guided, tab_json = st.tabs(["Guided Form", "JSON Upload"])

# ===========================================================================
# GUIDED FORM TAB
# ===========================================================================
with tab_guided:

    # -----------------------------------------------------------------------
    # Section 1 – Traveler profile
    # -----------------------------------------------------------------------
    with st.expander("Section 1 – Traveler profile", expanded=True):
        if load_profile():
            st.success("Profile loaded from your saved file.")
        else:
            st.info("Fill in your details and click **Save profile**. They will load automatically every time you open the app.")

        # Use key= so Streamlit reads/writes directly from session_state.
        # The values pre-set above (from load_profile) appear automatically.
        st.text_input("Full name", key="p_name",
                      help="Agent derives 'Last, First, M.I.' format automatically for the expense voucher.")
        c1b, c2b, c3b = st.columns(3)
        c1b.text_input("Employee ID", key="p_employee_id")
        c2b.text_input("Class / title", key="p_class_title", placeholder="TPS-4")
        c3b.text_input("Regular work hours", key="p_regular_hours")
        c1c, c2c = st.columns(2)
        c1c.text_input("Official station (duty city)", key="p_official_station", placeholder="OLYMPIA")
        c2c.text_input("Official residence (home city)", key="p_official_residence", placeholder="CAMAS")
        st.text_input("Street address", key="p_address")
        c1d, c2d, c3d = st.columns([3, 1, 1])
        c1d.text_input("City", key="p_city")
        c2d.text_input("State", key="p_state", max_chars=2)
        c3d.text_input("ZIP", key="p_zip")
        c1e, c2e = st.columns(2)
        c1e.text_input("Supervisor name", key="p_supervisor")
        c2e.text_input("Approving authority", key="p_approver")

        if st.button("Save profile", help="Saves to ~/.wsdot_travel_profile.json – loads automatically next time"):
            save_profile(st.session_state)
            st.success("Profile saved. It will load automatically next time you open the app.")

    # -----------------------------------------------------------------------
    # Section 2 – Trip basics
    # -----------------------------------------------------------------------
    with st.expander("Section 2 – Trip basics", expanded=True):
        st.caption("Both the Travel Request (PDF) and Expense Voucher (XLSX) are always generated together.")

        scope = st.radio(
            "Where is the travel?",
            ["In-state (Washington)", "Out-of-state (continental US)", "Out-of-country (includes Canada)"],
            horizontal=True,
        )
        scope_key = (
            "in_state" if scope.startswith("In")
            else "out_of_state" if scope.startswith("Out-of-s")
            else "out_of_country"
        )

        event_title = st.text_input("Event / meeting name", placeholder="AAAE ACT/BFI Innovation Event")
        destination_city = st.text_input("Destination city", placeholder="Seattle")

        # Auto-resolve county and meal tier
        tier_total = 68
        county_resolved = None
        if destination_city:
            tier_total, county_resolved = meal_tier_for_city(destination_city)
            meal_obj = get_meal_amounts(tier_total)
            county_label = county_resolved.title() if county_resolved else "unknown county"
            st.info(
                f"**{destination_city.title()}** → {county_label} County → "
                f"**meal tier ${tier_total}** "
                f"(B ${meal_obj.breakfast:.0f} / L ${meal_obj.lunch:.0f} / D ${meal_obj.dinner:.0f})"
                + ("" if county_resolved else
                   "\n\n⚠️ County not recognized – using base $68 tier. Verify against OFM map.")
            )

        # Dates
        col_d1, col_d2 = st.columns(2)
        travel_date = col_d1.date_input("Departure date", value=date.today())
        return_date = col_d2.date_input("Return date", value=date.today())

        if return_date < travel_date:
            st.error("Return date cannot be before departure date.")
            return_date = travel_date

        # Auto-compute days/nights
        num_nights = (return_date - travel_date).days
        num_days = num_nights + 1
        is_overnight = num_nights > 0

        if is_overnight:
            st.success(f"Trip duration: **{num_days} day{'s' if num_days > 1 else ''}**, **{num_nights} night{'s' if num_nights > 1 else ''}** (overnight)")
        else:
            st.info("Trip duration: **same day** (no overnight) — subsistence is taxable (GA02)")

        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        depart_time = col_t1.text_input("Departure time", value="0600", placeholder="0600")
        return_time_str = col_t2.text_input("Return time", value="1800", placeholder="1800")
        meeting_start = col_t3.text_input("Meeting / event start", value="0900")
        meeting_end = col_t4.text_input("Meeting / event end", value="1700")

        travel_date_str = travel_date.strftime("%m/%d/%y")
        return_date_str = return_date.strftime("%m/%d/%y")
        departure_datetime = f"{travel_date_str} {depart_time}"
        return_datetime = f"{return_date_str} {return_time_str}"
        meeting_begin_datetime = f"{travel_date_str} {meeting_start}"
        meeting_end_datetime = f"{return_date_str} {meeting_end}"

        signature_date = st.date_input("Signature date", value=date.today())

    # -----------------------------------------------------------------------
    # Section 3 – Transportation
    # -----------------------------------------------------------------------
    with st.expander("Section 3 – Transportation", expanded=True):
        transport = st.radio(
            "How are you getting there?",
            ["Personal vehicle (POV)", "WSDOT / motor pool vehicle", "Rental car",
             "Airline", "Train / rail / ferry", "Multiple / other"],
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
        airfare_amt = 0.0

        if transport == "Personal vehicle (POV)":
            state_vehicle_available = st.checkbox(
                "Was a state / WSDOT vehicle available for this trip?",
                help="Yes → elective rate GC02 ($0.205/mi). No → full rate GC01 ($0.725/mi).",
            )
            pov_rate_used = POV_ELECTIVE_RATE if state_vehicle_available else POV_FULL_RATE
            pov_code = mileage_object_code(state_vehicle_available)
            st.caption(f"Rate: ${pov_rate_used:.3f}/mi  |  Object code: **{pov_code}**")

            mc1, mc2 = st.columns(2)
            # Origin defaults to saved home city/address so user rarely has to type it
            default_origin = (
                st.session_state.get("p_official_residence", "")
                or st.session_state.get("p_city", "")
            )
            pov_from = mc1.text_input("Trip origin (home city / address)", value=default_origin,
                                       placeholder="Camas")
            pov_to = mc2.text_input("Trip destination", value=destination_city, placeholder="Seattle")

            # Auto-calculate driving distance + route map
            dist_col, btn_col = st.columns([3, 1])
            pov_miles = dist_col.number_input(
                "One-way miles", min_value=0.0, step=0.1,
                value=st.session_state.get("_pov_miles", 0.0),
                help="Click 'Calculate & Map' to auto-fill, or enter manually.",
            )
            with btn_col:
                st.write("")
                st.write("")
                if st.button("Calculate & Map"):
                    if pov_from and pov_to:
                        with st.spinner("Calculating route and generating map…"):
                            result = driving_miles(pov_from, pov_to)
                            map_pdf = route_map_pdf(pov_from, pov_to)
                            map_png = route_map_png(pov_from, pov_to)
                        if result is not None:
                            st.session_state["_pov_miles"] = result
                            st.session_state["_route_map_png"] = map_png
                            st.session_state["_route_map_pdf"] = map_pdf
                            st.session_state["_route_from"] = pov_from
                            st.session_state["_route_to"] = pov_to
                            st.rerun()
                        else:
                            st.error("Could not calculate distance. Enter miles manually.")
                    else:
                        st.warning("Enter origin and destination first.")

            if pov_miles > 0:
                rt_miles = pov_miles * 2
                st.metric(
                    "Mileage claim (round trip)",
                    f"${rt_miles * pov_rate_used:.2f}",
                    delta=f"{pov_miles:.1f} mi × 2 legs = {rt_miles:.1f} mi × ${pov_rate_used:.3f}",
                )

            # Show route map and PDF download button
            if st.session_state.get("_route_map_png"):
                st.image(st.session_state["_route_map_png"], use_container_width=True,
                         caption=f"Route: {st.session_state.get('_route_from','')} → {st.session_state.get('_route_to','')}")
                safe_from = "".join(c if c.isalnum() else "_" for c in st.session_state.get("_route_from", "origin"))
                safe_to   = "".join(c if c.isalnum() else "_" for c in st.session_state.get("_route_to", "dest"))
                if st.session_state.get("_route_map_pdf"):
                    st.download_button(
                        "⬇ Download route map PDF (attach to travel request)",
                        data=st.session_state["_route_map_pdf"],
                        file_name=f"route_{safe_from}_to_{safe_to}.pdf",
                        mime="application/pdf",
                    )

            if not state_vehicle_available:
                pov_reason = st.text_input("Reason POV preferred over state vehicle",
                                           placeholder="No state vehicle available at duty station")
            transport_payment_methods = ["Other"]
            transport_other_desc = "Mileage"

        elif transport == "WSDOT / motor pool vehicle":
            st.info("No mileage line on your request — vehicle cost runs through the equipment fund (GN01/GN02) on a separate journal voucher.")

        elif transport == "Rental car":
            transport_payment_methods = ["Car Rental"]

        elif transport == "Airline":
            transport_payment_methods = ["Airline travel"]
            airfare_amt = st.number_input("Airfare ($)", min_value=0.0, step=1.0)

        elif transport == "Train / rail / ferry":
            transport_payment_methods = ["TrainRailFerry"]

        else:
            transport_payment_methods = ["Other"]
            transport_other_desc = st.text_input("Describe transportation")

    # -----------------------------------------------------------------------
    # Section 4 – Meals and lodging
    # -----------------------------------------------------------------------
    with st.expander("Section 4 – Meals and lodging", expanded=True):
        meal_obj = get_meal_amounts(tier_total)
        subsistence_code = subsistence_object_code(is_overnight, scope_key)
        st.caption(f"Meal tier: ${tier_total} (B ${meal_obj.breakfast:.0f} / L ${meal_obj.lunch:.0f} / D ${meal_obj.dinner:.0f})  |  Object code: **{subsistence_code}**")

        st.markdown("**Which meals are you in travel status for?** (uncheck meals provided at no cost to you)")

        # Per-day meal grid for multi-day trips
        all_days = [travel_date + timedelta(days=i) for i in range(num_days)]
        meal_totals_by_day = []

        if num_days == 1:
            col_m1, col_m2, col_m3 = st.columns(3)
            b = col_m1.checkbox(f"Breakfast (${meal_obj.breakfast:.0f})", value=True)
            l = col_m2.checkbox(f"Lunch (${meal_obj.lunch:.0f})", value=True)
            d = col_m3.checkbox(f"Dinner (${meal_obj.dinner:.0f})", value=True)
            col_p1, col_p2, col_p3 = st.columns(3)
            pb = col_p1.checkbox("Breakfast provided (deduct)", disabled=not b)
            pl = col_p2.checkbox("Lunch provided (deduct)", disabled=not l)
            pd_ = col_p3.checkbox("Dinner provided (deduct)", disabled=not d)
            day_b = meal_obj.breakfast if (b and not pb) else 0.0
            day_l = meal_obj.lunch if (l and not pl) else 0.0
            day_d = meal_obj.dinner if (d and not pd_) else 0.0
            meal_totals_by_day = [(all_days[0], day_b, day_l, day_d)]
        else:
            st.markdown("*Check meals you will claim; uncheck if provided at the event or not in travel status.*")
            day_labels = []
            for i, d_ in enumerate(all_days):
                if i == 0:
                    label = f"Day 1 – {d_.strftime('%a %m/%d')} (departure)"
                elif i == num_days - 1:
                    label = f"Day {i+1} – {d_.strftime('%a %m/%d')} (return)"
                else:
                    label = f"Day {i+1} – {d_.strftime('%a %m/%d')}"
                day_labels.append(label)

            for i, (d_, label) in enumerate(zip(all_days, day_labels)):
                st.markdown(f"**{label}**")
                col_m1, col_m2, col_m3 = st.columns(3)
                # Default: departure day no breakfast (leave before eligible), return day no dinner
                default_b = True
                default_d = True if i < num_days - 1 else False
                b = col_m1.checkbox(f"Breakfast (${meal_obj.breakfast:.0f})", value=default_b, key=f"b_{i}")
                l = col_m2.checkbox(f"Lunch (${meal_obj.lunch:.0f})", value=True, key=f"l_{i}")
                dv = col_m3.checkbox(f"Dinner (${meal_obj.dinner:.0f})", value=default_d, key=f"d_{i}")
                col_p1, col_p2, col_p3 = st.columns(3)
                pb = col_p1.checkbox("Provided", disabled=not b, key=f"pb_{i}")
                pl = col_p2.checkbox("Provided", disabled=not l, key=f"pl_{i}")
                pd_ = col_p3.checkbox("Provided", disabled=not dv, key=f"pd_{i}")
                day_b = meal_obj.breakfast if (b and not pb) else 0.0
                day_l = meal_obj.lunch if (l and not pl) else 0.0
                day_d = meal_obj.dinner if (dv and not pd_) else 0.0
                meal_totals_by_day.append((d_, day_b, day_l, day_d))
                st.divider()

        total_subsistence = round(sum(b + l + d for _, b, l, d in meal_totals_by_day), 2)
        st.metric("Total meal reimbursement", f"${total_subsistence:.2f}")
        if not is_overnight and total_subsistence > 0:
            st.warning("Same-day reimbursement (GA02) is **taxable income**.")

        # Lodging
        lodging_amt = 0.0
        lodging_rate_val = 0.0
        hotel_name = ""
        hotel_city = ""
        if is_overnight:
            st.markdown("---\n**Lodging**")
            lc1, lc2 = st.columns(2)
            hotel_name = lc1.text_input("Hotel name")
            hotel_city = lc2.text_input("Hotel city")
            lodging_rate_val = st.number_input("Nightly lodging rate ($)", min_value=0.0, step=1.0)
            st.metric("Total lodging", f"${lodging_rate_val * num_nights:.2f}",
                      delta=f"{num_nights} night{'s' if num_nights > 1 else ''} × ${lodging_rate_val:.2f}")
            lodging_amt = lodging_rate_val * num_nights

    # -----------------------------------------------------------------------
    # Section 5 – Registration and other expenses
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

        has_parking = st.checkbox("Parking?")
        parking_amt = 0.0
        if has_parking:
            parking_amt = st.number_input("Parking amount ($)", min_value=0.0, step=1.0)

        has_other = st.checkbox("Other reimbursable expenses?")
        other_desc = ""
        other_amt = 0.0
        other_code = "GD01"
        other_exp_type = "other"
        if has_other:
            other_exp_type = st.selectbox("Expense type",
                                          ["taxi", "rideshare", "ferry", "toll", "bus", "rail",
                                           "rental_car", "official_meal", "other"])
            other_desc = st.text_input("Description")
            other_amt = st.number_input("Amount ($)", min_value=0.0, step=1.0)
            other_code = other_travel_object_code(other_exp_type)
            st.caption(f"Object code: **{other_code}**")

    # -----------------------------------------------------------------------
    # Section 6 – Charge codes
    # -----------------------------------------------------------------------
    with st.expander("Section 6 – Charge codes", expanded=True):
        st.caption("Object code column is filled automatically. Enter your work order and org code.")
        acc1, acc2, acc3 = st.columns(3)
        acc1.text_input("Work order", key="p_work_order")
        acc2.text_input("Group", key="p_group_code", placeholder="02")
        acc3.text_input("Work op", key="p_work_op", placeholder="0605")
        st.text_input("Org code", key="p_org_code", placeholder="691010")
        travel_advance = st.number_input("Travel advance received ($)", min_value=0.0, step=1.0)
        remarks = st.text_area("Remarks (expense voucher)",
                               placeholder="Registration and mileage entered from approved travel request.")
        comments = st.text_area("Comments (travel request – transport / hotel details)",
                                placeholder="Drive personal vehicle to avoid delays. Home to/from HQ at GC01 (XX mi × $0.725 = $XX).")

    # -----------------------------------------------------------------------
    # Build payload
    # -----------------------------------------------------------------------
    def build_payload():
        work_order = st.session_state["p_work_order"]
        group_code = st.session_state["p_group_code"]
        work_op = st.session_state["p_work_op"]
        org_code = st.session_state["p_org_code"]
        base_acct = {"work_order": work_order, "group": group_code, "work_op": work_op, "org_code": org_code}

        # Build per-day expense lines
        daily_expenses = []
        for i, (day, day_b, day_l, day_d) in enumerate(meal_totals_by_day):
            is_first = i == 0
            is_last = i == len(meal_totals_by_day) - 1
            entry = {
                "date": day.strftime("%Y-%m-%d"),
                "trip_from": (pov_from or st.session_state.get("p_official_residence", "")) if is_first else destination_city,
                "trip_to": (pov_to or destination_city) if is_first else (
                    (pov_from or st.session_state.get("p_official_residence", "")) if is_last else destination_city
                ),
                "depart": depart_time if is_first else "",
                "return_time": return_time_str if is_last else "",
                "breakfast": day_b,
                "lunch": day_l,
                "dinner": day_d,
                "lodging": lodging_rate_val if (is_overnight and not is_last) else 0.0,
                "miles": (pov_miles * 2 if not is_overnight else pov_miles) if (transport == "Personal vehicle (POV)" and is_first) else 0.0,
                "mileage_rate": pov_rate_used if (transport == "Personal vehicle (POV)" and is_first) else 0.0,
                "pov_reason": pov_reason if (transport == "Personal vehicle (POV)" and is_first) else "",
                "purpose": event_title,
            }
            daily_expenses.append(entry)

        # Return trip mileage line (same day = already round-trip in miles entry above; multi-day = add return leg)
        if transport == "Personal vehicle (POV)" and pov_miles > 0 and is_overnight:
            daily_expenses.append({
                "date": return_date.strftime("%Y-%m-%d"),
                "trip_from": pov_to or destination_city,
                "trip_to": pov_from or st.session_state.get("p_official_residence", ""),
                "depart": "",
                "return_time": return_time_str,
                "breakfast": 0.0, "lunch": 0.0, "dinner": 0.0, "lodging": 0.0,
                "miles": pov_miles,
                "mileage_rate": pov_rate_used,
                "pov_reason": pov_reason,
                "purpose": event_title,
            })

        # Account codes
        account_codes = []
        if registration_fee > 0:
            account_codes.append({**base_acct, "object_code": reg_code, "amount": registration_fee})
        if total_subsistence > 0:
            account_codes.append({**base_acct, "object_code": subsistence_code, "amount": total_subsistence})
        if transport == "Personal vehicle (POV)" and pov_miles > 0:
            trips = 2
            mileage_total = round(pov_miles * trips * pov_rate_used, 2)
            account_codes.append({**base_acct, "object_code": pov_code, "amount": mileage_total})
        if parking_amt > 0:
            account_codes.append({**base_acct, "object_code": "GD01", "amount": parking_amt})
        if other_amt > 0:
            account_codes.append({**base_acct, "object_code": other_code, "amount": other_amt})

        # Other expenses (receipts section of 133-103)
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
                "date": return_date.strftime("%Y-%m-%d"),
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

        ss = st.session_state
        return {
            "traveler": {
                "name": ss["p_name"],
                "name_last_first_initial": _name_last_first(ss["p_name"]),
                "employee_id": ss["p_employee_id"],
                "class_title": ss["p_class_title"],
                "address": ss["p_address"],
                "city": ss["p_city"],
                "state": ss["p_state"],
                "zip_code": ss["p_zip"],
                "official_station": ss["p_official_station"],
                "official_residence": ss["p_official_residence"],
                "regular_work_hours": ss["p_regular_hours"],
                "supervisor_name": ss["p_supervisor"],
                "approving_authority_name": ss["p_approver"],
            },
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
            "subsistence_days": num_days if total_subsistence > 0 else None,
            "subsistence_rate": round(total_subsistence / num_days, 2) if (total_subsistence > 0 and num_days) else None,
            "lodging_days": num_nights if is_overnight else 0,
            "lodging_rate": lodging_rate_val if is_overnight else 0.0,
            "hotel_name": hotel_name,
            "hotel_city": hotel_city,
            "comments": comments,
            "remarks": remarks,
            "signature_date": signature_date.strftime("%Y-%m-%d"),
            "travel_advance": travel_advance,
            "request_other_fees": 0.0,
            "daily_expenses": daily_expenses,
            "account_codes": account_codes,
            "other_expenses": other_expenses,
        }

    # -----------------------------------------------------------------------
    # Section 7 – Review and generate
    # -----------------------------------------------------------------------
    with st.expander("Section 7 – Review and generate", expanded=True):
        col_rv, col_gen = st.columns(2)

        if col_rv.button("Review summary", use_container_width=True):
            if not st.session_state["p_name"]:
                st.error("Enter your name in Section 1 and click Save Profile.")
            elif not event_title or not destination_city:
                st.error("Complete the event name and destination in Section 2.")
            else:
                payload = build_payload()
                mileage_display = ""
                if transport == "Personal vehicle (POV)" and pov_miles > 0:
                    trips = 2
                    total_mi = pov_miles * trips
                    mileage_display = (
                        f"\n- **Mileage:** {pov_miles:.1f} mi × {trips} "
                        f"= {total_mi:.1f} mi × ${pov_rate_used:.3f} = "
                        f"**${total_mi * pov_rate_used:.2f}** ({pov_code})"
                    )
                lines = [
                    f"**Event:** {event_title}",
                    f"**Destination:** {destination_city.title()}" + (f" – {county_resolved.title()} County" if county_resolved else ""),
                    f"**Dates:** {travel_date_str} → {return_date_str}  ({num_days} day{'s' if num_days > 1 else ''}, {num_nights} night{'s' if num_nights > 1 else ''})",
                    "**Forms:** Travel Request (PDF) + Expense Voucher (XLSX)",
                    "---",
                    "**Expense lines:**",
                    f"- **Meals:** ${total_subsistence:.2f} ({subsistence_code})" + (" ⚠️ taxable" if not is_overnight else ""),
                ]
                if registration_fee:
                    lines.append(f"- **Registration:** ${registration_fee:.2f} ({reg_code})")
                if is_overnight and lodging_amt:
                    lines.append(f"- **Lodging:** ${lodging_amt:.2f} (GA01, {num_nights} night{'s' if num_nights > 1 else ''})")
                if mileage_display:
                    lines.append(mileage_display.strip("- "))
                if parking_amt:
                    lines.append(f"- **Parking:** ${parking_amt:.2f} (GD01)")
                if other_amt:
                    lines.append(f"- **{other_desc or other_exp_type}:** ${other_amt:.2f} ({other_code})")
                grand = sum(a.get("amount", 0) for a in payload["account_codes"])
                lines.append(f"\n**Estimated total: ${grand:.2f}**")
                st.markdown("\n".join(lines))
                with st.expander("View full intake JSON"):
                    st.json(payload)

        if col_gen.button("Generate forms", type="primary", use_container_width=True):
            if not st.session_state["p_name"] or not event_title or not destination_city:
                st.error("Name (Section 1), event name, and destination (Section 2) are required.")
            else:
                try:
                    payload = build_payload()
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
                        st.success(f"Forms generated for **{event_title}**.")
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
                except Exception as e:
                    st.error(str(e))
                    raise

# ===========================================================================
# JSON UPLOAD TAB
# ===========================================================================
with tab_json:
    st.subheader("JSON Upload")
    st.write("Upload or paste a travel-intake JSON to generate forms directly.")
    with st.expander("Example JSON", expanded=False):
        example_path = BASE / "examples" / "bfi_travel_intake.json"
        if example_path.exists():
            st.code(example_path.read_text(encoding="utf-8"), language="json")

    uploaded = st.file_uploader("Travel intake JSON", type=["json"], key="json_upload")
    text = st.text_area("Or paste JSON", height=260, key="json_text")
    travel_request_template_json = st.file_uploader("Travel request PDF template (override)", type=["pdf"], key="pdf_tpl")
    expense_template_json = st.file_uploader("133-103 XLSX template (override)", type=["xlsx"], key="xlsx_tpl")

    if st.button("Generate forms from JSON", key="json_gen"):
        try:
            if uploaded is not None:
                payload_json = json.loads(uploaded.read().decode("utf-8"))
            elif text.strip():
                payload_json = json.loads(text)
            else:
                st.error("Provide a JSON file or paste JSON.")
                st.stop()
            with tempfile.TemporaryDirectory() as td:
                td_path = Path(td)
                req_tpl = td_path / "travel_request_template.pdf"
                exp_tpl = td_path / "133-103_template.xlsx"
                req_tpl.write_bytes(travel_request_template_json.read() if travel_request_template_json
                                    else (BASE / "templates" / "travel_request_template.pdf").read_bytes())
                exp_tpl.write_bytes(expense_template_json.read() if expense_template_json
                                    else (BASE / "templates" / "133-103_template.xlsx").read_bytes())
                intake = TravelIntake.from_dict(payload_json)
                agent = TravelFormAgent(req_tpl, exp_tpl, td_path / "outputs")
                outputs = agent.run(intake)
                pdf_bytes = outputs["travel_request_pdf"].read_bytes()
                xlsx_bytes = outputs["expense_voucher_xlsx"].read_bytes()
            st.success("Forms generated.")
            st.download_button("Download Travel Request PDF", pdf_bytes, "travel_request.pdf", mime="application/pdf")
            st.download_button("Download Expense Voucher XLSX", xlsx_bytes, "travel_expense_voucher.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.error(str(e))
