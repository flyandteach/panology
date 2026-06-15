"""
Aviation Futures Intelligence — Streamlit Web UI
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd

from agent import AviationFuturesAgent, DOMAINS, HORIZON_LABELS

st.set_page_config(
    page_title="Aviation Futures Intelligence",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def llm_mode_badge() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "🟢 Claude API connected"
    if os.environ.get("OPENAI_API_KEY"):
        return "🟡 OpenAI API connected"
    return "🔴 Mock mode (no API key)"


st.sidebar.title("Aviation Futures")
st.sidebar.caption(llm_mode_badge())
st.sidebar.markdown("---")

page = st.sidebar.radio("Navigate", ["Forecast", "Domain Brief", "Scenarios"])

# ---------------------------------------------------------------------------
# Shared controls
# ---------------------------------------------------------------------------
st.sidebar.markdown("### Settings")
horizon = st.sidebar.selectbox(
    "Time Horizon",
    options=list(HORIZON_LABELS.keys()),
    format_func=lambda k: HORIZON_LABELS[k],
    index=1,
)

st.sidebar.markdown("### Domains")
selected_domains = []
for i, domain in enumerate(DOMAINS):
    if st.sidebar.checkbox(domain, value=True, key=f"domain_{i}"):
        selected_domains.append(domain)

if not selected_domains:
    st.sidebar.warning("Select at least one domain.")


# ===========================================================================
# PAGE: Forecast
# ===========================================================================
if page == "Forecast":
    st.title("Aviation Futures Intelligence")
    st.caption(
        "Synthesises signals across AI & autonomous flight, eVTOL, drone logistics, "
        "airport electrification, aerospace manufacturing, military spillover, and regulatory signals."
    )

    focus_notes = st.text_area(
        "Focus Notes (optional)",
        placeholder="E.g. 'Emphasis on infrastructure readiness gaps' or 'Focus on regulatory signals affecting eVTOL in the US'",
        height=80,
    )

    if st.button("Run Forecast", type="primary", disabled=not selected_domains):
        with st.spinner("Analysing aviation signals…"):
            agent = AviationFuturesAgent()
            result = agent.run_forecast(
                domains=selected_domains,
                horizon=horizon,
                focus_notes=focus_notes,
            )
            st.session_state["_forecast"] = result

    result = st.session_state.get("_forecast")
    if result:
        st.markdown("### Executive Summary")
        st.markdown(result.get("executive_summary", ""))

        domains_data = result.get("domains", {})
        if domains_data:
            st.markdown("### Domain Overview")
            rows = []
            for dname, ddata in domains_data.items():
                adoption = ddata.get("adoption_probability_score")
                infra = ddata.get("infrastructure_readiness")
                rows.append({
                    "Domain": dname,
                    "Signal Strength": ddata.get("signal_strength", 0),
                    "Direction": ddata.get("trend_direction", "—"),
                    "Adoption Probability": f"{adoption:.0%}" if adoption is not None else "—",
                    "Infrastructure Readiness": f"{infra:.0%}" if infra is not None else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            st.markdown("### Domain Details")
            for dname, ddata in domains_data.items():
                with st.expander(dname):
                    devs = ddata.get("key_developments", [])
                    if devs:
                        st.markdown("**Key Developments**")
                        for d in devs:
                            st.markdown(f"- {d}")
                    gaps = ddata.get("infrastructure_gaps", [])
                    if gaps:
                        st.markdown("**Infrastructure Gaps**")
                        for g in gaps:
                            st.markdown(f"- {g}")
                    signals = ddata.get("watch_signals", [])
                    if signals:
                        st.markdown("**Watch Signals**")
                        for s in signals:
                            st.markdown(f"→ {s}")

        themes = result.get("cross_domain_themes", [])
        if themes:
            st.markdown("### Cross-Domain Themes")
            for t in themes:
                urgency = t.get("urgency", "low")
                colour = {"high": "red", "medium": "orange", "low": "grey"}.get(urgency, "grey")
                st.markdown(
                    f"**:{colour}[{t['theme']}]** ({urgency} urgency)\n\n{t['description']}"
                )
                st.markdown(f"*Affects: {', '.join(t.get('affected_domains', []))}*")
                st.markdown("---")

        recs = result.get("top_recommendations", [])
        if recs:
            st.markdown("### Top Recommendations")
            for i, r in enumerate(recs, 1):
                st.markdown(f"{i}. {r}")

        st.download_button(
            label="Download Forecast JSON",
            data=json.dumps(result, indent=2),
            file_name=f"aviation_futures_{horizon}.json",
            mime="application/json",
        )


# ===========================================================================
# PAGE: Domain Brief
# ===========================================================================
elif page == "Domain Brief":
    st.title("Domain Brief")
    st.caption("Deep-dive analysis for a single aviation technology domain.")

    chosen_domain = st.selectbox("Domain", options=DOMAINS)

    if st.button("Run Domain Brief", type="primary"):
        with st.spinner(f"Analysing {chosen_domain}…"):
            agent = AviationFuturesAgent()
            brief = agent.run_domain_brief(domain=chosen_domain, horizon=horizon)
            st.session_state["_domain_brief"] = brief

    brief = st.session_state.get("_domain_brief")
    if brief:
        col1, col2, col3 = st.columns(3)
        adoption = brief.get("adoption_probability_score")
        infra = brief.get("infrastructure_readiness")
        col1.metric("Signal Strength", f"{brief.get('signal_strength', '—')}/10")
        col2.metric("Adoption Probability", f"{adoption:.0%}" if adoption is not None else "—")
        col3.metric("Infrastructure Readiness", f"{infra:.0%}" if infra is not None else "—")

        st.markdown(f"**Trend:** {brief.get('trend_direction', '—')}")
        st.markdown("### Narrative")
        st.markdown(brief.get("narrative", ""))

        for label, key in [
            ("Key Developments", "key_developments"),
            ("Infrastructure Gaps", "infrastructure_gaps"),
            ("Watch Signals", "watch_signals"),
        ]:
            items = brief.get(key, [])
            if items:
                st.markdown(f"### {label}")
                for item in items:
                    st.markdown(f"- {item}")


# ===========================================================================
# PAGE: Scenarios
# ===========================================================================
elif page == "Scenarios":
    st.title("Scenario Analysis")
    st.caption("Discrete futures triggered by specific observable events, with probability estimates.")

    if st.button("Generate Scenarios", type="primary", disabled=not selected_domains):
        with st.spinner("Building scenario analyses…"):
            agent = AviationFuturesAgent()
            result = agent.run_scenario_analysis(domains=selected_domains)
            st.session_state["_scenarios"] = result

    scenarios_result = st.session_state.get("_scenarios")
    if scenarios_result:
        scenario_list = scenarios_result.get("scenarios", [])
        if scenario_list:
            rows = []
            for s in scenario_list:
                prob = s.get("probability", 0)
                rows.append({
                    "Scenario": s.get("name", "?"),
                    "Probability": f"{prob:.0%}",
                    "Trigger": s.get("trigger", "—"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            st.markdown("### Scenario Details")
            for s in scenario_list:
                with st.expander(f"{s.get('name', '?')} — {s.get('probability', 0):.0%}"):
                    st.markdown(f"**Description:** {s.get('description', '—')}")
                    st.markdown(f"**Trigger:** {s.get('trigger', '—')}")
                    horizon_shift = s.get("horizon_shift") or s.get("impact", "")
                    if horizon_shift:
                        st.markdown(f"**Horizon impact:** {horizon_shift}")
                    winners = s.get("winners", [])
                    losers = s.get("losers", [])
                    infra_impl = s.get("infrastructure_implications", "")
                    if winners:
                        st.markdown(f"**Winners:** {', '.join(winners)}")
                    if losers:
                        st.markdown(f"**Losers:** {', '.join(losers)}")
                    if infra_impl:
                        st.markdown(f"**Infrastructure:** {infra_impl}")

        note = scenarios_result.get("scenario_matrix_note", "")
        if note:
            st.info(note)
