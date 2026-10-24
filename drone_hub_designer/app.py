from __future__ import annotations

import json
from dataclasses import asdict, fields

import pandas as pd
import streamlit as st

from hub import CRITERIA, HubInputs, compare_with_baseline
from hub.aircraft_library import LIBRARY, facts, profile_for, provenance, reference_names
from hub.models import AirspaceProfile, CostInputs, DemandProfile, DesignRequirements, Obstacle, SensitiveZone, SiteProfile

st.set_page_config(page_title="Drone Delivery Hub Designer", layout="wide")
st.title("Drone Delivery Hub Designer")
st.caption(
    "Sizes a permanent drone delivery hub for a peak order rate, plans its departure and arrival corridors, "
    "and grades it against an interim parking-lot nest. Values marked as placeholders are not data: "
    "replace them with OEM figures, site measurements and your AHJ's requirements."
)

uploaded = st.sidebar.file_uploader("Load inputs (JSON)", type="json")
base = HubInputs.from_dict(json.load(uploaded)) if uploaded else HubInputs()
upload_key = uploaded.file_id if uploaded else "default"

names = reference_names()
ref_ids = list(names)
ref_id = st.sidebar.selectbox(
    "Reference aircraft",
    ref_ids,
    index=ref_ids.index(base.aircraft.reference_id) if base.aircraft.reference_id in names else 0,
    format_func=names.get,
    key=f"{upload_key}.ref",
    help="Fills the aircraft inputs from published figures. See the Aircraft reference tab for sources.",
)
if uploaded and ref_id == base.aircraft.reference_id:
    aircraft_start = base.aircraft
else:
    aircraft_start = profile_for(ref_id)
key_prefix = f"{upload_key}.{ref_id}"


def widget(section: str, name: str, value, suffix: str = ""):
    label = name.replace("_", " ") + suffix
    key = f"{key_prefix}.{section}.{name}"
    if isinstance(value, bool):
        return st.checkbox(label, value=value, key=key)
    if isinstance(value, int):
        return int(st.number_input(label, value=value, min_value=0, step=1, key=key))
    if isinstance(value, float):
        return float(st.number_input(label, value=value, min_value=0.0, key=key, format="%.4g"))
    if name == "battery_mode":
        return st.selectbox(label, ["swap", "onboard"], index=["swap", "onboard"].index(value), key=key)
    return st.text_input(label, value=value, key=key)


values = {}
with st.sidebar.expander("Aircraft", expanded=False):
    placeholder_fields = {r["field"] for r in provenance(ref_id) if r["basis"] == "placeholder"}
    st.caption("Fields marked * are placeholders, not published data.")
    values["aircraft"] = {"reference_id": ref_id, "name": aircraft_start.name}
    for f in fields(aircraft_start):
        if f.name in ("name", "reference_id"):
            continue
        suffix = " *" if f.name in placeholder_fields else ""
        values["aircraft"][f.name] = widget("aircraft", f.name, getattr(aircraft_start, f.name), suffix)

for section, title, dc in [
    ("demand", "Demand", DemandProfile),
    ("site", "Site and climate", SiteProfile),
    ("design", "Design choices", DesignRequirements),
]:
    current = getattr(base, section)
    with st.sidebar.expander(title, expanded=section == "demand"):
        values[section] = {f.name: widget(section, f.name, getattr(current, f.name)) for f in fields(dc)}

with st.sidebar.expander("Unit costs"):
    st.caption("Enter your own prices. Zero means not entered. Only electricity has a default "
               "(US commercial average, Jan-Jun 2026, per EIA via a secondary source).")
    values["costs"] = {f.name: widget("costs", f.name, getattr(base.costs, f.name)) for f in fields(CostInputs)}

with st.sidebar.expander("Flight path settings"):
    air_scalars = {
        f.name: widget("airspace", f.name, getattr(base.airspace, f.name))
        for f in fields(AirspaceProfile)
        if f.name not in ("obstacles", "zones")
    }

metrics_box = st.container()
tabs = st.tabs(["Layout and scorecard", "Flight paths", "Costs", "Throughput", "Noise", "Weather and night",
                "Aircraft reference", "All checks"])

with tabs[1]:
    st.markdown("**Site surroundings.** Bearings are compass degrees from the hub centre; heights are above "
                "hub ground level. The starting rows are an invented example site.")
    obstacles_df = st.data_editor(
        pd.DataFrame([asdict(o) for o in base.airspace.obstacles], columns=[f.name for f in fields(Obstacle)]),
        num_rows="dynamic", key=f"{upload_key}.obstacles", use_container_width=True,
    )
    zones_df = st.data_editor(
        pd.DataFrame([asdict(z) for z in base.airspace.zones], columns=[f.name for f in fields(SensitiveZone)]),
        num_rows="dynamic", key=f"{upload_key}.zones", use_container_width=True,
    )


def rows(df: pd.DataFrame) -> list[dict]:
    clean = df.dropna(how="any")
    out = []
    for rec in clean.to_dict("records"):
        out.append({k: (str(v) if k in ("name", "kind") else float(v)) for k, v in rec.items()})
    return out


values["airspace"] = {**air_scalars, "obstacles": rows(obstacles_df), "zones": rows(zones_df)}
try:
    inputs = HubInputs.from_dict(values)
except (TypeError, ValueError) as exc:
    st.error(f"Could not read the inputs: {exc}")
    st.stop()

proposed, baseline = compare_with_baseline(inputs)
cap = proposed.capacity
fp = proposed.flight_paths

with metrics_box:
    cols = st.columns(7)
    cols[0].metric("Pads" if inputs.aircraft.launch_infrastructure != "dock" else "Docks", cap.pads_required,
                   delta=cap.pads_required - baseline.capacity.pads_required, delta_color="inverse",
                   help="Change vs the parking-lot baseline")
    cols[1].metric("Aircraft", cap.aircraft_required)
    cols[2].metric("Battery packs", cap.batteries_required)
    cols[3].metric("Charging slots", cap.charging_slots)
    cols[4].metric("Corridors", f"{len(fp.corridors)} / {fp.corridors_required}")
    cols[5].metric("Peak power", f"{proposed.peak_power_kw:.0f} kW")
    cols[6].metric("Availability", f"{proposed.availability.availability:.0%}",
                   delta=f"{proposed.availability.availability - baseline.availability.availability:+.0%}")

with tabs[0]:
    left, right = st.columns([3, 2])
    with left:
        if not proposed.layout.fits:
            st.error(
                f"Hub needs {proposed.layout.required_w:.0f} x {proposed.layout.required_d:.0f} m but the site is "
                f"{proposed.layout.site_w:.0f} x {proposed.layout.site_d:.0f} m."
            )
        show = st.radio("Show", ["Proposed hub", "Parking-lot baseline"], horizontal=True)
        svg = (proposed if show == "Proposed hub" else baseline).layout.to_svg()
        st.markdown(f'<div style="max-width:100%">{svg}</div>', unsafe_allow_html=True)
    with right:
        st.subheader("Scorecard")
        st.dataframe(
            pd.DataFrame({"Proposed": proposed.scores(), "Parking-lot baseline": baseline.scores()}
                         ).map(lambda v: f"{v:.0%}"),
            use_container_width=True,
        )
        st.caption("Share of checks passed per category. Criteria are tool defaults: " +
                   ", ".join(f"{k} = {v:g}" for k, v in CRITERIA.items()))
        st.subheader("Open items")
        open_items = [c for c in proposed.checks if not c.passed]
        for c in open_items:
            st.warning(f"**{c.category}: {c.name}.** {c.detail}")
        for flag in proposed.fire.flags:
            st.warning(f"**Fire:** {flag}")
        if not open_items and not proposed.fire.flags:
            st.success("Every check passes for these inputs.")

with tabs[1]:
    m, p = st.columns(2)
    with m:
        st.markdown(fp.to_map_svg(inputs.airspace, inputs.aircraft), unsafe_allow_html=True)
    with p:
        st.markdown(fp.to_profile_svg(inputs.airspace, inputs.aircraft), unsafe_allow_html=True)
        st.write(
            f"Climb to {inputs.aircraft.cruise_altitude_m:.0f} m takes {fp.transition_distance_m:.0f} m of "
            f"ground distance; corridors are {fp.corridor_length_m:.0f} m long. "
            f"{fp.clear_headings} of {fp.candidate_headings} headings are clear of obstacles."
        )
        st.write(
            f"{fp.movements_per_hour:.0f} movements/h at peak; one corridor handles "
            f"{fp.corridor_capacity_per_hour:.0f}/h, so {fp.corridors_required} are needed. Using fixed "
            f"corridors adds {fp.mean_detour_m:.0f} m ({fp.extra_flight_s:.0f} s) to the average sortie, "
            "already included in fleet sizing."
        )
    st.dataframe(pd.DataFrame([{
        "Heading": f"{c.heading_deg:03.0f}°",
        "Length (m)": round(c.length_m),
        "Low overflight (m)": round(sum(c.low_overflight_m.values())),
        "Obstacles in lane": ", ".join(n for n, _, _ in c.obstacles_in_lane) or "none",
    } for c in fp.corridors]), hide_index=True, use_container_width=True)
    for w in fp.route_warnings:
        st.warning(w)
    st.caption("Corridor planning is a screening model: straight lanes, a constant-gradient climb and the "
               "obstacles and zones you enter. It does not check airspace classes, airport proximity, "
               "terrain, or the operator's own route approvals.")

with tabs[2]:
    pc, bc = proposed.costs, baseline.costs
    if pc.missing:
        st.info("Unit costs not entered for: " + ", ".join(pc.missing) + ". Those lines count as zero, so the "
                "totals below are incomplete. Enter prices under Unit costs in the sidebar.")

    def money(v: float) -> str:
        return f"${v:,.0f}" if v < 1e6 else f"${v / 1e6:,.2f}M"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capital", money(pc.capital_total), delta=money(pc.capital_total - bc.capital_total)
              if pc.capital_total != bc.capital_total else None, delta_color="inverse", help="vs baseline")
    c2.metric("Operating / yr", money(pc.operating_annual))
    c3.metric("Deliveries / yr", f"{pc.annual_deliveries:,.0f}",
              delta=f"{pc.annual_deliveries - bc.annual_deliveries:+,.0f}", help="Demand x availability")
    c4.metric("Cost per delivery", f"${pc.cost_per_delivery:,.2f}",
              delta=f"{pc.cost_per_delivery - bc.cost_per_delivery:+,.2f}", delta_color="inverse")
    st.dataframe(pd.DataFrame([{
        "Group": line.group, "Item": line.item, "Quantity": round(line.quantity, 1), "Unit": line.unit,
        "Unit cost": line.unit_cost, "Total": round(line.total),
        "Status": "" if line.entered else "not entered",
    } for line in pc.lines]), hide_index=True, use_container_width=True)
    st.caption(
        "Capital is annualised with the capital recovery factor at the discount rate and asset lives entered. "
        "Deliveries per year = daily orders x 365 x availability, so hub downtime raises cost per delivery. "
        "Energy assumes one full pack charge per sortie. The baseline uses the same unit costs."
    )

with tabs[3]:
    st.write(
        f"{cap.sorties_per_hour:.0f} sorties/h at peak. Mean trip {cap.mean_trip_km:.1f} km each way; "
        f"flight {cap.flight_time_s / 60:.1f} min, ground turnaround {cap.ground_turnaround_s / 60:.1f} min, "
        f"full cycle {cap.cycle_time_s / 60:.1f} min."
    )
    st.write(
        f"Pads: {cap.pad_events_per_hour:.0f} pad events/h, {cap.pad_service_s:.0f} s each, "
        f"{cap.pad_utilization:.0%} utilisation, mean wait {cap.pad_mean_wait_s:.0f} s. "
        f"The baseline (turnaround on the pad) needs {baseline.capacity.pads_required} pads at "
        f"{baseline.capacity.pad_utilization:.0%}."
    )
    st.write(f"Lithium-ion energy on site: {cap.stored_energy_kwh:.1f} kWh across {cap.batteries_required} packs.")

with tabs[4]:
    n, bn = proposed.noise, baseline.noise
    st.write(
        f"Proposed: {n.level_with_barrier_db:.1f} dBA at the nearest receptor "
        f"({n.simultaneous_pads} pad(s) busy, barrier {n.barrier_attenuation_db:.1f} dB). "
        f"Baseline: {bn.level_with_barrier_db:.1f} dBA. Limit {n.limit_db:.0f} dBA."
    )
    st.write(f"Without shielding, the limit is met {n.distance_to_limit_m:.0f} m from the pads.")
    if "hover_noise_dba" in placeholder_fields:
        st.warning("No published hover noise level was found for this aircraft, so the noise result uses the "
                   "placeholder level. Use the operator's measured Lmax at a stated distance.")
    st.caption("Screening estimate: point source, spherical spreading, thin-barrier approximation. "
               "Covers lift-off and landing only; overflight noise is not shielded by a barrier.")

with tabs[5]:
    a, ba = proposed.availability, baseline.availability
    st.write(
        f"Aircraft limits (wind, precipitation, night) remove {a.aircraft_limited_frac:.1%} of operating hours "
        "in both designs."
    )
    st.write(f"Proposed hub adds {a.hub_limited_frac:.1%} downtime ({a.annual_hours_lost_to_hub:.0f} h/yr); "
             f"baseline adds {ba.hub_limited_frac:.1%} ({ba.annual_hours_lost_to_hub:.0f} h/yr).")
    if ba.causes:
        st.table(pd.DataFrame({"Share of operating hours": {k: f"{v:.1%}" for k, v in ba.causes.items()}}))

with tabs[6]:
    st.subheader(LIBRARY[ref_id]["name"])
    st.caption("Figures were taken from web search excerpts of the documents linked; they were not checked "
               "against the full documents. 'single source' and 'unverified' values deserve a second look.")
    st.dataframe(
        pd.DataFrame(provenance(ref_id, inputs.aircraft)),
        column_config={"sources": st.column_config.ListColumn("sources")},
        hide_index=True, use_container_width=True,
    )
    fact_rows = facts(ref_id)
    if fact_rows:
        st.markdown("**Other published facts (not used directly in the model)**")
        st.dataframe(pd.DataFrame(fact_rows), column_config={"sources": st.column_config.ListColumn("sources")},
                     hide_index=True, use_container_width=True)

with tabs[7]:
    check_rows = []
    for p_, b_ in zip(proposed.checks, baseline.checks):
        check_rows.append({"Category": p_.category, "Check": p_.name, "Proposed": "pass" if p_.passed else "FAIL",
                           "Baseline": "pass" if b_.passed else "FAIL", "Detail (proposed)": p_.detail})
    st.dataframe(pd.DataFrame(check_rows), use_container_width=True, hide_index=True)

st.sidebar.download_button("Save inputs (JSON)", json.dumps(inputs.to_dict(), indent=2), "hub_inputs.json")
st.sidebar.download_button(
    "Download results (JSON)",
    json.dumps({"proposed": proposed.summary(), "baseline": baseline.summary()}, indent=2),
    "hub_results.json",
)
st.sidebar.download_button("Download layout (SVG)", proposed.layout.to_svg(), "hub_layout.svg")
st.sidebar.download_button("Download corridor map (SVG)", fp.to_map_svg(inputs.airspace, inputs.aircraft),
                           "hub_corridors.svg")
