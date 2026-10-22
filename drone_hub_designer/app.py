from __future__ import annotations

import json
from dataclasses import fields

import pandas as pd
import streamlit as st

from hub import CRITERIA, HubInputs, compare_with_baseline
from hub.models import AircraftProfile, DemandProfile, DesignRequirements, SiteProfile

st.set_page_config(page_title="Drone Delivery Hub Designer", layout="wide")
st.title("Drone Delivery Hub Designer")
st.caption(
    "Sizes a permanent drone delivery hub for a peak order rate and grades it against an interim "
    "parking-lot nest on throughput, safety, weather, night, noise and fire. Defaults are placeholders: "
    "replace them with OEM data, site measurements and your AHJ's requirements."
)

SECTIONS = [
    ("aircraft", "Aircraft", AircraftProfile),
    ("demand", "Demand", DemandProfile),
    ("site", "Site and climate", SiteProfile),
    ("design", "Design choices", DesignRequirements),
]

uploaded = st.sidebar.file_uploader("Load inputs (JSON)", type="json")
base = HubInputs.from_dict(json.load(uploaded)) if uploaded else HubInputs()
key_prefix = uploaded.file_id if uploaded else "default"


def widget(section: str, name: str, value):
    label = name.replace("_", " ")
    key = f"{key_prefix}.{section}.{name}"
    if isinstance(value, bool):
        return st.checkbox(label, value=value, key=key)
    if isinstance(value, int):
        return int(st.number_input(label, value=value, min_value=0, step=1, key=key))
    if isinstance(value, float):
        return float(st.number_input(label, value=value, min_value=0.0, key=key, format="%.3g"))
    if name == "battery_mode":
        return st.selectbox(label, ["swap", "onboard"], index=["swap", "onboard"].index(value), key=key)
    return st.text_input(label, value=value, key=key)


values = {}
for section, title, dc in SECTIONS:
    current = getattr(base, section)
    with st.sidebar.expander(title, expanded=section == "demand"):
        values[section] = {f.name: widget(section, f.name, getattr(current, f.name)) for f in fields(dc)}

inputs = HubInputs.from_dict(values)
proposed, baseline = compare_with_baseline(inputs)
cap = proposed.capacity

cols = st.columns(6)
cols[0].metric("Pads", cap.pads_required, delta=cap.pads_required - baseline.capacity.pads_required,
               delta_color="inverse", help="Change vs the parking-lot baseline")
cols[1].metric("Aircraft", cap.aircraft_required)
cols[2].metric("Battery packs", cap.batteries_required)
cols[3].metric("Charging slots", cap.charging_slots)
cols[4].metric("Peak power", f"{proposed.peak_power_kw:.0f} kW")
cols[5].metric("Availability", f"{proposed.availability.availability:.0%}",
               delta=f"{proposed.availability.availability - baseline.availability.availability:+.0%}")

left, right = st.columns([3, 2])
with left:
    st.subheader("Layout")
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
        pd.DataFrame(
            {"Proposed": proposed.scores(), "Parking-lot baseline": baseline.scores()}
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

st.subheader("Details")
t1, t2, t3, t4 = st.tabs(["Throughput", "Noise", "Weather and night", "All checks"])
with t1:
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
with t2:
    n, bn = proposed.noise, baseline.noise
    st.write(
        f"Proposed: {n.level_with_barrier_db:.1f} dBA at the nearest receptor "
        f"({n.simultaneous_pads} pad(s) busy, barrier {n.barrier_attenuation_db:.1f} dB). "
        f"Baseline: {bn.level_with_barrier_db:.1f} dBA. Limit {n.limit_db:.0f} dBA."
    )
    st.write(f"Without shielding, the limit is met {n.distance_to_limit_m:.0f} m from the pads.")
    st.caption("Screening estimate: point source, spherical spreading, thin-barrier approximation. "
               "Covers lift-off and landing only; overflight noise is not shielded by a barrier.")
with t3:
    a, ba = proposed.availability, baseline.availability
    st.write(
        f"Aircraft limits (wind, precipitation, night) remove {a.aircraft_limited_frac:.1%} of operating hours "
        "in both designs."
    )
    st.write(f"Proposed hub adds {a.hub_limited_frac:.1%} downtime ({a.annual_hours_lost_to_hub:.0f} h/yr); "
             f"baseline adds {ba.hub_limited_frac:.1%} ({ba.annual_hours_lost_to_hub:.0f} h/yr).")
    if ba.causes:
        st.table(pd.DataFrame({"Share of operating hours": {k: f"{v:.1%}" for k, v in ba.causes.items()}}))
with t4:
    rows = []
    for p, b in zip(proposed.checks, baseline.checks):
        rows.append({"Category": p.category, "Check": p.name, "Proposed": "pass" if p.passed else "FAIL",
                     "Baseline": "pass" if b.passed else "FAIL", "Detail (proposed)": p.detail})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.sidebar.download_button("Save inputs (JSON)", json.dumps(inputs.to_dict(), indent=2), "hub_inputs.json")
st.sidebar.download_button(
    "Download results (JSON)",
    json.dumps({"proposed": proposed.summary(), "baseline": baseline.summary()}, indent=2),
    "hub_results.json",
)
st.sidebar.download_button("Download layout (SVG)", proposed.layout.to_svg(), "hub_layout.svg")
