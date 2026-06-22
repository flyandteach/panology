"""
FRAT-as-a-Service — Streamlit web UI
Run with: streamlit run frat_agent/streamlit_app.py
"""
from __future__ import annotations
import json
from datetime import datetime, date, time, timezone

import streamlit as st
import pandas as pd

from frat_agent.models import MissionRequest
from frat_agent.orchestrator import assess
from frat_agent.utils.audit_log import read_recent
from frat_agent.config import PAVE_RISK_LABELS, VERDICT_LABELS


st.set_page_config(
    page_title  = "FRAT-as-a-Service",
    page_icon   = "✈",
    layout      = "wide",
    initial_sidebar_state = "expanded",
)

PAGES = ["Assess Mission", "Audit Log", "About"]
page = st.sidebar.radio("Navigation", PAGES)

_VERDICT_COLOR = {
    "GO":                       "🟢",
    "PROCEED_WITH_MITIGATIONS": "🟡",
    "NO_GO":                    "🔴",
}


# ── Assess Mission ─────────────────────────────────────────────────────────────

if page == "Assess Mission":
    st.title("✈ FRAT-as-a-Service")
    st.caption("UAS Flight Risk Assessment · Part 107 / SORA 2.5 · Decision support only")

    with st.form("mission_form"):
        st.subheader("📍 Location & Time")
        col1, col2 = st.columns(2)
        with col1:
            lat           = st.number_input("Latitude (decimal °)", value=47.6097, format="%.6f")
            lon           = st.number_input("Longitude (decimal °)", value=-122.3331, format="%.6f")
            location_name = st.text_input("Location name", value="Downtown Seattle, WA")
        with col2:
            airport_icao  = st.text_input("Nearest airport ICAO", value="KSEA",
                                          help="Used for METAR/TAF fetch, e.g. KSEA, KORD, KJFK")
            plan_date     = st.date_input("Flight date", value=date.today())
            start_time    = st.time_input("Planned start", value=time(14, 0))
            end_time      = st.time_input("Planned end",   value=time(16, 0))

        st.subheader("✈ Operation")
        col3, col4 = st.columns(2)
        with col3:
            altitude      = st.slider("Max altitude AGL (ft)", 0, 400, 200, 10)
            operation     = st.selectbox("Operation type", ["VLOS", "EVLOS", "BVLOS"])
            density       = st.selectbox("Population density", ["sparse", "populated", "gathering"])
        with col4:
            over_people   = st.checkbox("Over people")
            over_vehicles = st.checkbox("Over moving vehicles")
            is_night      = st.checkbox("Night operation")

        st.subheader("🚁 Aircraft")
        col5, col6 = st.columns(2)
        with col5:
            aircraft_model = st.text_input("Make / model", value="DJI Mavic 3")
            weight_lbs     = st.number_input("Weight (lbs)", value=1.98, min_value=0.0, format="%.2f")
        with col6:
            dimension_m    = st.number_input("Characteristic dimension (m)", value=0.28, min_value=0.0, format="%.2f",
                                             help="Wingspan or rotor span")
            max_speed_ms   = st.number_input("Max speed (m/s)", value=19.0, min_value=0.0)

        st.subheader("👤 Pilot")
        col7, col8 = st.columns(2)
        with col7:
            pilot_name     = st.text_input("Pilot name", value="")
            pilot_cert     = st.selectbox("Certificate", ["Part 107", "Part 61", "student"])
            total_hours    = st.number_input("Total UAS hours", value=100.0, min_value=0.0)
        with col8:
            currency_days  = st.number_input("Days since last flight", value=10, min_value=0)
            night_current  = st.checkbox("Night current")

        st.subheader("⚠ External Pressures")
        col9, col10, col11 = st.columns(3)
        with col9:
            sched_pressure  = st.slider("Schedule pressure", 1, 5, 1)
        with col10:
            client_pressure = st.slider("Client pressure",   1, 5, 1)
        with col11:
            fin_pressure    = st.slider("Financial pressure", 1, 5, 1)

        notes = st.text_area("Operator notes (optional)")

        submitted = st.form_submit_button("🚀 Run Assessment", type="primary", use_container_width=True)

    if submitted:
        planned_start = datetime.combine(plan_date, start_time, tzinfo=timezone.utc)
        planned_end   = datetime.combine(plan_date, end_time,   tzinfo=timezone.utc)

        mission = MissionRequest(
            lat                  = lat,
            lon                  = lon,
            location_name        = location_name,
            nearest_airport_icao = airport_icao.strip().upper(),
            planned_start        = planned_start,
            planned_end          = planned_end,
            max_altitude_ft_agl  = altitude,
            operation_type       = operation,
            population_density   = density,
            over_people          = over_people,
            over_moving_vehicles = over_vehicles,
            is_night             = is_night,
            aircraft_make_model  = aircraft_model,
            aircraft_weight_lbs  = weight_lbs,
            aircraft_dimension_m = dimension_m,
            aircraft_max_speed_ms= max_speed_ms,
            pilot_name           = pilot_name,
            pilot_certificate    = pilot_cert,
            pilot_currency_days  = int(currency_days),
            pilot_total_hours    = total_hours,
            pilot_night_current  = night_current,
            schedule_pressure    = sched_pressure,
            client_pressure      = client_pressure,
            financial_pressure   = fin_pressure,
            notes                = notes,
        )

        with st.spinner("Fetching live data and computing risk scores…"):
            report = assess(mission, save=True)

        # ── Verdict banner ────────────────────────────────────────────────────
        emoji = _VERDICT_COLOR.get(report.verdict, "⬜")
        if report.verdict == "GO":
            st.success(f"{emoji} **{report.verdict_label}**")
        elif report.verdict == "PROCEED_WITH_MITIGATIONS":
            st.warning(f"{emoji} **{report.verdict_label}**")
        else:
            st.error(f"{emoji} **{report.verdict_label}**")

        st.caption(f"Report ID: `{report.report_id}`  |  Generated: {report.generated_at}")

        # ── Hard stops ────────────────────────────────────────────────────────
        if report.hard_stops:
            with st.expander("⛔ Hard Stops", expanded=True):
                for hs in report.hard_stops:
                    st.error(f"• {hs}")

        # ── Columns: Weather + LAANC ──────────────────────────────────────────
        col_w, col_l = st.columns(2)
        with col_w:
            st.subheader("🌤 Weather")
            if report.weather:
                w = report.weather
                cat_color = {"VFR": "green", "MVFR": "orange", "IFR": "red", "LIFR": "red"}
                st.metric("Flight Category", w.flight_category)
                st.metric("Wind", f"{w.wind_dir_deg or '?'}° / {w.wind_speed_kt} kt"
                          + (f" G{w.wind_gust_kt}kt" if w.wind_gust_kt else ""))
                st.metric("Visibility", f"{w.visibility_sm} SM")
                st.metric("Ceiling", f"{w.ceiling_ft or 'Clear'} ft")
                st.caption(f"METAR: `{w.raw_metar}`")
                st.caption(f"TAF: {w.taf_summary}")
            else:
                st.info("Weather unavailable")

        with col_l:
            st.subheader("🗺 LAANC / Airspace")
            if report.laanc:
                la = report.laanc
                st.metric("Facility", la.facility_name[:40])
                st.metric("Airspace Class", f"Class {la.airspace_class}")
                st.metric("LAANC Ceiling", f"{la.authorized_ceiling_ft} ft AGL")
                st.metric("Requested", f"{report.mission.get('max_altitude_ft_agl')} ft AGL",
                          delta=report.mission.get('max_altitude_ft_agl', 0) - la.authorized_ceiling_ft,
                          delta_color="inverse")
            else:
                st.info("LAANC data unavailable")

        # ── PAVE table ────────────────────────────────────────────────────────
        st.subheader("📊 PAVE Risk Scores")
        p = report.pave
        _PAVE_EMOJI = {1: "🟢", 2: "🟢", 3: "🟡", 4: "🟠", 5: "🔴"}
        pave_data = {
            "Dimension":   ["Pilot", "Aircraft", "Environment", "External", "**Average**"],
            "Score":       [p.pilot, p.aircraft, p.environment, p.external, round(p.average, 1)],
            "Risk Level":  [PAVE_RISK_LABELS.get(s, "?") for s in [p.pilot, p.aircraft, p.environment, p.external]] + [""],
            "Indicator":   [_PAVE_EMOJI.get(s, "⬜") for s in [p.pilot, p.aircraft, p.environment, p.external]] + [""],
        }
        st.dataframe(pd.DataFrame(pave_data), use_container_width=True, hide_index=True)

        # PAVE narrative
        if p.narrative:
            with st.expander("PAVE Narrative"):
                st.write(p.narrative)

        # PAVE factors per dimension
        for dim, factors in [
            ("Pilot", p.pilot_factors),
            ("Aircraft", p.aircraft_factors),
            ("Environment", p.environment_factors),
            ("External", p.external_factors),
        ]:
            if factors:
                with st.expander(f"{dim} risk factors"):
                    for f in factors:
                        st.write(f"• {f}")

        # ── SORA ─────────────────────────────────────────────────────────────
        st.subheader("📐 SORA 2.5")
        s = report.sora
        sail_roman = ["", "I", "II", "III", "IV", "V", "VI"]
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("iGRC", s.igrc, help=s.igrc_rationale)
        col_s2.metric("ARC", s.arc_label.upper(), help=s.arc_rationale)
        col_s3.metric("SAIL", sail_roman[s.sail] if 1 <= s.sail <= 6 else s.sail)

        # ── NOTAMs ───────────────────────────────────────────────────────────
        if report.notams:
            with st.expander(f"📋 NOTAMs ({len(report.notams)})"):
                for n in report.notams:
                    st.write(f"**[{n.classification}]** `{n.notam_id}` — {n.text[:200]}")

        # ── TFRs ─────────────────────────────────────────────────────────────
        if report.tfrs:
            with st.expander(f"🚫 TFRs ({len(report.tfrs)})"):
                for t in report.tfrs:
                    flag = "⚠️ **INTERSECTS MISSION AREA**" if t.intersects_mission else "Outside area"
                    st.write(f"`{t.notam_id}` {t.name} — {flag}")
                    st.caption(f"Alt: {t.min_alt_ft}–{t.max_alt_ft} ft | {t.effective_start} → {t.effective_end}")

        # ── Mitigations ───────────────────────────────────────────────────────
        if report.mitigations:
            st.subheader("🛡 Required Mitigations")
            for m in report.mitigations:
                icon = "⛔" if m.is_hard_stop else "⚠️"
                with st.expander(f"{icon} [{m.dimension.upper()}] {m.risk_factor}"):
                    st.write(f"**Action:** {m.action}")
                    if m.reduces_to:
                        st.write(f"**Residual risk after mitigation:** {m.reduces_to}")

        # ── Data warnings ─────────────────────────────────────────────────────
        if report.data_warnings:
            with st.expander("⚠ Data Quality Warnings"):
                for dw in report.data_warnings:
                    st.warning(dw)

        # ── Download ─────────────────────────────────────────────────────────
        st.divider()
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                "⬇ Download JSON report",
                data    = json.dumps(report.to_dict(), indent=2),
                file_name = f"{report.report_id}.json",
                mime    = "application/json",
            )
        from frat_agent.utils.export import _render
        with col_dl2:
            st.download_button(
                "⬇ Download text report",
                data      = _render(report),
                file_name = f"{report.report_id}.txt",
                mime      = "text/plain",
            )

        st.caption(
            "⚠ **Disclaimer**: This report is decision support only, not an FAA authorization. "
            "The pilot-in-command retains sole responsibility under 14 CFR 107.49."
        )


# ── Audit Log ─────────────────────────────────────────────────────────────────

elif page == "Audit Log":
    st.title("📋 Assessment Audit Log")
    records = read_recent(50)
    if not records:
        st.info("No assessments recorded yet.")
    else:
        rows = []
        for r in reversed(records):
            verdict = r.get("verdict", "")
            emoji   = _VERDICT_COLOR.get(verdict, "⬜")
            rows.append({
                "Generated":    r.get("generated_at", "")[:19],
                "Report ID":    r.get("report_id", "")[:24],
                "Location":     r.get("mission", {}).get("location_name", "?")[:30],
                "Pilot":        r.get("mission", {}).get("pilot_name", "?"),
                "Alt (ft)":     r.get("mission", {}).get("max_altitude_ft_agl", "?"),
                "Verdict":      f"{emoji} {verdict}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.subheader("Record detail")
        report_ids = [r.get("report_id", "") for r in reversed(records)]
        selected = st.selectbox("Select report ID", report_ids)
        if selected:
            sel = next((r for r in records if r.get("report_id") == selected), None)
            if sel:
                st.json(sel)


# ── About ─────────────────────────────────────────────────────────────────────

elif page == "About":
    st.title("About FRAT-as-a-Service")
    st.markdown("""
## What this is

FRAT-as-a-Service is an agentic flight risk assessment tool for UAS (drone) operators.
It ingests a planned mission (location, time window, altitude, aircraft, pilot), pulls live
weather, NOTAMs, TFRs, and LAANC ceiling data from official FAA feeds, and computes a
structured **PAVE / SORA 2.5** risk score — returning a timestamped go / no-go decision
with named mitigations as an exportable, auditable record.

## Regulatory framework

| Framework | Coverage |
|-----------|----------|
| **14 CFR Part 107** | Standard remote pilot certification; pre-flight assessment obligation under §107.49 |
| **SORA 2.5** (JARUS) | iGRC, ARC, SAIL scoring for specific-category operations; anticipated ORA structure for Part 108 BVLOS |
| **Part 108 (NPRM)** | BVLOS authorization anticipated; final rule pending as of June 2026 |

## Data sources

| Data | Source | Notes |
|------|--------|-------|
| METAR / TAF | aviationweather.gov REST API | Open, no key required |
| NOTAMs | FAA NOTAM Search API | Requires OAuth2 credentials (api.faa.gov) |
| TFRs | tfr.faa.gov XML | Open, parsed at runtime |
| LAANC / UASFM | FAA ArcGIS REST service | Open, no key required |

## Disclaimer

This tool provides **decision support only**.  It is not an FAA authorization.
The remote pilot-in-command retains sole legal responsibility for pre-flight assessment
under **14 CFR 107.49** and for compliance with all applicable regulations.
Verify all data independently before flight.
    """)
