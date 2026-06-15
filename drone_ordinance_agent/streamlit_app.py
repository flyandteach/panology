"""
Streamlit UI — Drone Hub / Vertiport Ordinance Agent.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

st.set_page_config(
    page_title="Drone Ordinance Agent",
    page_icon="🚁",
    layout="wide",
    initial_sidebar_state="expanded",
)

from agents.orchestrator import OrdinanceOrchestrator
from utils.memory import OrdinanceSession
from utils.export import export_ordinance
import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def llm_badge() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "🟢 Claude API connected"
    if os.environ.get("OPENAI_API_KEY"):
        return "🟡 OpenAI API connected"
    return "🔴 Mock mode (set ANTHROPIC_API_KEY for live generation)"


DENSITY_OPTIONS = ["rural", "suburban", "urban", "dense_urban"]
AIRPORT_OPTIONS = ["class_b", "class_c", "class_d", "class_e", "class_g", "heliport", "vertiport", "none"]

US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
    "Wisconsin", "Wyoming",
]

TIER_COLORS = {1: "#4CAF50", 2: "#2196F3", 3: "#FF9800", 4: "#F44336"}
TIER_LABELS = {
    1: "Tier 1 — Micro-Hub",
    2: "Tier 2 — Community Vertiport",
    3: "Tier 3 — Regional Vertiport",
    4: "Tier 4 — Major Skyport",
}

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
DEFAULTS = {
    "ordinance_session": None,
    "generation_complete": False,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("Drone Ordinance Agent")
st.sidebar.caption(llm_badge())
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["Configure", "Generate", "Results", "Export"],
    index=0,
)

session: OrdinanceSession | None = st.session_state["ordinance_session"]
if session and session.inputs:
    st.sidebar.markdown("---")
    i = session.inputs
    st.sidebar.markdown(f"**State:** {i.get('state', '—')}")
    st.sidebar.markdown(f"**Airport:** {i.get('airport_type', '—')}")
    st.sidebar.markdown(f"**Density:** {i.get('density', '—')}")
    st.sidebar.markdown(f"**Scale:** {i.get('operational_scale', '—')} ops/day")
    if st.session_state["generation_complete"]:
        tier = session.get_output("tier_classification").get("tier", "?")
        color = TIER_COLORS.get(tier, "#999")
        label = TIER_LABELS.get(tier, f"Tier {tier}")
        st.sidebar.markdown(
            f'<div style="background:{color};color:white;padding:6px 10px;border-radius:4px;font-weight:bold;">{label}</div>',
            unsafe_allow_html=True,
        )


# ===========================================================================
# PAGE: Configure
# ===========================================================================
if page == "Configure":
    st.title("Configure Your Project")
    st.markdown("Enter parameters about the proposed drone hub or vertiport site. The agent will generate a complete draft ordinance package.")

    with st.form("configure_form"):
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Location & Context")
            state = st.selectbox("State *", US_STATES, index=US_STATES.index("California"))
            municipality = st.text_input("Municipality / City Name", placeholder="San Jose")
            density = st.selectbox(
                "Density Context *",
                DENSITY_OPTIONS,
                index=1,
                help="Character of the area surrounding the proposed site.",
            )
            airport_type = st.selectbox(
                "Nearest Airport / Airspace Class *",
                AIRPORT_OPTIONS,
                index=4,
                help="FAA airspace classification of the nearest airport.",
            )

        with col2:
            st.subheader("Facility Parameters")
            operational_scale = st.number_input(
                "Operational Scale (ops/day) *",
                min_value=1,
                max_value=5000,
                value=75,
                help="Maximum daily takeoff + landing cycles anticipated.",
            )
            site_acreage = st.number_input(
                "Site Acreage",
                min_value=0.0,
                max_value=500.0,
                value=1.5,
                step=0.1,
                help="Total project site area in acres.",
            )
            residential_proximity_ft = st.number_input(
                "Nearest Residential Structure (ft)",
                min_value=0,
                max_value=10000,
                value=600,
                help="Distance from proposed pad edge to nearest residential structure.",
            )

        st.subheader("Environmental Flags")
        env_col1, env_col2 = st.columns(2)
        with env_col1:
            wetland_nearby = st.checkbox("Wetland within 300 ft of site")
        with env_col2:
            floodplain_nearby = st.checkbox("Site within or adjacent to FEMA floodplain")

        notes = st.text_area(
            "Additional Context / Notes",
            placeholder="e.g. 'Site is on a brownfield adjacent to light rail.' or 'Intended for last-mile delivery only, no passenger service.'",
            height=80,
        )

        submitted = st.form_submit_button("Save Configuration", type="primary")

    if submitted:
        new_session = OrdinanceSession()
        new_session.set_inputs(
            state=state,
            airport_type=airport_type,
            density=density,
            operational_scale=int(operational_scale),
            municipality=municipality.strip(),
            site_acreage=float(site_acreage),
            wetland_nearby=wetland_nearby,
            floodplain_nearby=floodplain_nearby,
            residential_proximity_ft=int(residential_proximity_ft),
            notes=notes.strip(),
        )
        st.session_state["ordinance_session"] = new_session
        st.session_state["generation_complete"] = False
        st.success("Configuration saved. Go to Generate to run the agent.")
        st.rerun()

    if session and session.inputs:
        st.markdown("---")
        st.subheader("Current Configuration")
        st.code(session.get_inputs_summary(), language="yaml")


# ===========================================================================
# PAGE: Generate
# ===========================================================================
elif page == "Generate":
    st.title("Generate Ordinance Package")

    if not session or not session.inputs:
        st.warning("No configuration found. Go to Configure first.")
        st.stop()

    st.markdown("The agent will run 6 specialized modules in sequence:")
    st.markdown("""
1. **Classification** — Assign facility tier
2. **Definitions** — Legal use definitions
3. **Zoning Language** — Full ordinance text
4. **Setbacks** — Calculated distances
5. **Approval Pathways** — Entitlement process
6. **Environmental Review** — Triggered studies & mitigations
""")

    col_a, col_b = st.columns([1, 3])
    with col_a:
        run_btn = st.button("Run Agent", type="primary", use_container_width=True)

    if run_btn:
        progress = st.progress(0, text="Starting...")
        status_msgs = []

        def on_progress(step, total, label):
            pct = int(step / total * 100)
            progress.progress(pct, text=f"Step {step}/{total}: {label}")
            status_msgs.append(f"✓ {label}")

        try:
            orchestrator = OrdinanceOrchestrator()
            orchestrator.run(session, progress_callback=on_progress)
            progress.progress(100, text="Complete!")
            st.session_state["generation_complete"] = True

            for msg in status_msgs:
                st.markdown(msg)

            st.success("Ordinance package generated. Go to Results to review.")
        except Exception as exc:
            st.error(f"Generation failed: {exc}")
            raise

    if st.session_state["generation_complete"]:
        st.info("Generation already complete. Go to Results or re-run to regenerate.")


# ===========================================================================
# PAGE: Results
# ===========================================================================
elif page == "Results":
    st.title("Ordinance Results")

    if not session or not st.session_state["generation_complete"]:
        st.warning("No results yet. Go to Generate first.")
        st.stop()

    # ---- Tier Banner ----
    tier_data = session.get_output("tier_classification")
    tier = tier_data.get("tier", "?")
    tier_label = tier_data.get("label", "")
    color = TIER_COLORS.get(tier, "#999")

    st.markdown(
        f'<div style="background:{color};color:white;padding:12px 16px;border-radius:6px;font-size:1.2rem;font-weight:bold;margin-bottom:1rem;">'
        f'Tier {tier} — {tier_label}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(tier_data.get("description", ""))

    col1, col2, col3 = st.columns(3)
    col1.metric("Operational Class", tier_data.get("operational_class", "—"))
    col2.metric("FAA Coordination", "Required" if tier_data.get("faa_coordination_required") else "Recommended")
    col3.metric("Density Context", tier_data.get("density_modifier", "—").replace("_", " ").title())

    if tier_data.get("faa_coordination_note"):
        st.info(tier_data["faa_coordination_note"])

    st.markdown("---")

    # ---- Tabs for each output ----
    tabs = st.tabs(["Definitions", "Zoning Language", "Setbacks", "Approval Pathways", "Environmental Review"])

    # --- Definitions ---
    with tabs[0]:
        st.subheader("Use Definitions")
        defs_data = session.get_output("use_definitions")
        defs = defs_data.get("definitions", [])
        if defs:
            for d in defs:
                term = d.get("term", "")
                defn = d.get("definition", "")
                st.markdown(f"**{term}**")
                st.markdown(f"> {defn}")
                st.markdown("")
        if defs_data.get("notes"):
            st.caption(defs_data["notes"])

    # --- Zoning Language ---
    with tabs[1]:
        st.subheader("Draft Zoning Ordinance")
        zoning_data = session.get_output("zoning_language")
        if zoning_data.get("text"):
            st.text_area("Ordinance Text", value=zoning_data["text"], height=500, disabled=True)

        col_z1, col_z2, col_z3 = st.columns(3)
        with col_z1:
            st.markdown("**Permitted By-Right Zones**")
            for z in zoning_data.get("permitted_zones", []):
                st.markdown(f"- {z}")
        with col_z2:
            st.markdown("**CUP Required Zones**")
            for z in zoning_data.get("conditional_zones", []):
                st.markdown(f"- {z}")
        with col_z3:
            st.markdown("**Prohibited Zones**")
            for z in zoning_data.get("prohibited_zones", []):
                st.markdown(f"- {z}")

        if zoning_data.get("overlay_district"):
            st.info(f"Overlay District: **{zoning_data['overlay_district']}**")

        col_n1, col_n2 = st.columns(2)
        col_n1.metric("Operating Hours", zoning_data.get("operating_hours", "—"))
        col_n2.metric("Noise Limit", f"{zoning_data.get('noise_limit_dba', '—')} dB(A) Leq")

        if zoning_data.get("notes"):
            st.caption(zoning_data["notes"])

    # --- Setbacks ---
    with tabs[2]:
        st.subheader("Setback Requirements")
        setback_data = session.get_output("setback_recommendations")

        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("Density Multiplier", f"{setback_data.get('density_multiplier', '—')}×")
        col_s2.metric("Tier Factor", f"{setback_data.get('tier_factor', '—')}×")
        col_s3.metric("Airport Proximity", f"{setback_data.get('airport_proximity_miles', '—')} miles")

        items = setback_data.get("items", [])
        if items:
            import pandas as pd
            rows = [{"Land Use / Context": i["label"], "Setback (ft)": i["feet"]} for i in items]
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.markdown("**Detailed Requirements**")
            for item in items:
                with st.expander(f"{item['label']} — {item['feet']} ft"):
                    st.markdown(item["detail"])

        if setback_data.get("airport_note"):
            st.warning(setback_data["airport_note"])
        if setback_data.get("notes"):
            st.caption(setback_data["notes"])

    # --- Approval Pathways ---
    with tabs[3]:
        st.subheader("Approval Pathways")
        path_data = session.get_output("approval_pathways")

        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("Primary Entitlement", path_data.get("primary_entitlement", "—"))
        col_p2.metric("Est. Timeline", path_data.get("estimated_timeline_weeks", "—") + " wks")
        col_p3.metric("Est. Fees", path_data.get("estimated_fees", "—"))

        hearing = path_data.get("public_hearing_required", False)
        if hearing:
            st.warning("Public hearing required before the Planning Commission.")
        else:
            st.success("Administrative review — no public hearing required (unless appealed).")

        st.markdown(f"**CEQA/NEPA Track:** {path_data.get('ceqa_track', '—')}")
        st.markdown(f"**FAA Coordination:** {'Required' if path_data.get('faa_coordination_required') else 'Recommended'}")

        st.markdown("---")
        for i, step in enumerate(path_data.get("pathways", []), 1):
            with st.expander(f"{step.get('label', f'Step {i}')}"):
                st.markdown(step.get("detail", ""))
                if step.get("agency"):
                    st.caption(f"Agency: {step['agency']}")
                if step.get("timeline"):
                    st.caption(f"Timeline: {step['timeline']}")
                if step.get("estimated_fees"):
                    st.caption(f"Estimated Fees: {step['estimated_fees']}")

        if path_data.get("appeal_path"):
            st.info(f"**Appeal Path:** {path_data['appeal_path']}")
        if path_data.get("notes"):
            st.caption(path_data["notes"])

    # --- Environmental ---
    with tabs[4]:
        st.subheader("Environmental Review Triggers")
        env_data = session.get_output("environmental_triggers")

        col_e1, col_e2 = st.columns(2)
        col_e1.metric("Triggers Identified", env_data.get("trigger_count", 0))
        col_e2.metric("Recommended CEQA Document", env_data.get("ceqa_document", "—"))

        triggers = env_data.get("triggers", [])
        if triggers:
            for t in triggers:
                triggered = t.get("triggered", True)
                icon = "⚠️" if triggered else "✅"
                with st.expander(f"{icon} {t.get('trigger', 'Trigger')} — {t.get('actual', '')}"):
                    st.markdown(t.get("detail", ""))
                    st.caption(f"Threshold: {t.get('threshold', '—')}")
        else:
            st.success("No environmental review triggers identified.")

        studies = env_data.get("studies_required", [])
        if studies:
            st.markdown("**Studies Required**")
            for s in studies:
                st.markdown(f"- {s}")

        mitigations = env_data.get("mitigation_measures", [])
        if mitigations:
            st.markdown("**Mitigation Measures**")
            for m in mitigations:
                st.markdown(f"- {m}")

        if env_data.get("notes"):
            st.caption(env_data["notes"])


# ===========================================================================
# PAGE: Export
# ===========================================================================
elif page == "Export":
    st.title("Export Ordinance Package")

    if not session or not st.session_state["generation_complete"]:
        st.warning("No completed ordinance to export. Go to Generate first.")
        st.stop()

    st.info("Export a complete Markdown document suitable for legal review and council adoption proceedings.")

    export_dir = os.path.join(os.path.dirname(__file__), config.EXPORTS_DIR)

    if st.button("Generate Export", type="primary"):
        with st.spinner("Assembling ordinance document..."):
            try:
                filepath = export_ordinance(session, export_dir)
                with open(filepath, "r", encoding="utf-8") as fh:
                    content = fh.read()
                st.session_state["_export_content"] = content
                st.session_state["_export_filename"] = os.path.basename(filepath)
                st.success(f"Exported: {filepath}")
            except Exception as exc:
                st.error(f"Export failed: {exc}")

    content = st.session_state.get("_export_content", "")
    filename = st.session_state.get("_export_filename", "ordinance.md")

    if content:
        st.download_button(
            label="Download Ordinance (.md)",
            data=content,
            file_name=filename,
            mime="text/markdown",
            type="primary",
        )
        st.markdown("---")
        st.subheader("Preview")
        st.text_area("Ordinance Document", value=content, height=600, disabled=True)

    # Also offer raw JSON
    if st.button("Download Raw JSON"):
        json_str = json.dumps(session.to_dict(), indent=2)
        st.download_button(
            label="Download JSON",
            data=json_str,
            file_name=filename.replace(".md", ".json"),
            mime="application/json",
        )
