"""Streamlit page: upload a PDF, extract its location, find the nearest public-use airport(s).

Part of the Parcel Lookup Agent app -- see app.py for the address-lookup page.
"""

import folium
import streamlit as st
from streamlit_folium import st_folium

from parcel_agent.site_report import SiteReportAgent

st.set_page_config(page_title="Site Report from PDF", layout="wide")
st.title("Site Report from PDF")
st.caption(
    "Upload a document containing a site address, a PLSS legal description "
    "(e.g. 'SW 1/4 Section 12, T33N, R21E, WM'), and/or a parcel number. "
    "The agent extracts the location, resolves it to coordinates, looks up the "
    "parcel, and reports the nearest public-use airport(s)."
)

uploaded = st.file_uploader("Upload a PDF", type=["pdf"])
go = st.button("Analyze document", type="primary")

if go and uploaded is not None:
    agent = SiteReportAgent()
    with st.spinner("Extracting location and querying GIS/airport data..."):
        report = agent.run_from_pdf(uploaded)

    col_map, col_details = st.columns([2, 1])

    with col_details:
        st.subheader("Extracted from document")
        if report.extracted:
            st.write(f"**Address:** {report.extracted.address or '_not found_'}")
            st.write(f"**PLSS description:** {report.extracted.plss.raw_text if report.extracted.plss else '_not found_'}")
            st.write(f"**Parcel number:** {report.extracted.apn or '_not found_'}")
            st.write(f"**County/state hint:** {report.extracted.county_hint or '?'}, {report.extracted.state_hint or '?'}")

        st.subheader("Resolved location")
        if report.found:
            st.success(f"Resolved via **{report.location_source}** "
                       f"(confidence: {report.location_confidence})")
            st.write(f"**Coordinates:** {report.lat:.6f}, {report.lon:.6f}")

            if report.parcel and report.parcel.found:
                st.write(f"**Parcel APN:** {report.parcel.apn or 'unknown'}")
                st.write(f"**Owner:** {report.parcel.owner_name or 'unknown'}")
                st.write(f"**County:** {report.parcel.county_name}, {report.parcel.state_abbr}")
            else:
                st.info("No parcel could be verified at this location.")

            st.subheader("Nearest public-use airports")
            if not report.airport_data_is_public_use_verified:
                st.warning(
                    "Airport dataset is a fallback source (not verified public-use-only). "
                    "Run `python -m parcel_agent.airports_refresh` from a machine with internet "
                    "access to populate the verified FAA snapshot."
                )
            if report.nearest_airports:
                st.table([
                    {
                        "Ident": a.ident, "Name": a.name, "City": a.city, "State": a.state,
                        "Distance (nm)": a.distance_nm, "Distance (mi)": a.distance_mi,
                    }
                    for a in report.nearest_airports
                ])
            else:
                st.write("No airports found in the current dataset.")
        else:
            st.error("Could not resolve a location.")
            st.write(report.error)

        with st.expander("Diagnostics: what the agent tried", expanded=not report.found):
            for attempt in report.attempts:
                icon = "✅" if attempt.success else "⛔"
                st.write(f"{icon} **{attempt.strategy}** — {attempt.detail}")

    with col_map:
        if report.found:
            m = folium.Map(location=[report.lat, report.lon], zoom_start=11)
            folium.Marker([report.lat, report.lon], tooltip="Site", icon=folium.Icon(color="red")).add_to(m)
            if report.plss_result and report.plss_result.section_geometry:
                folium.GeoJson(
                    report.plss_result.section_geometry,
                    style_function=lambda _: {"color": "#457b9d", "weight": 2, "fillOpacity": 0.05},
                ).add_to(m)
            if report.parcel and report.parcel.geometry:
                folium.GeoJson(
                    report.parcel.geometry,
                    style_function=lambda _: {"color": "#e63946", "weight": 3, "fillOpacity": 0.15},
                ).add_to(m)
            for airport in report.nearest_airports:
                folium.Marker(
                    [airport.lat, airport.lon],
                    tooltip=f"{airport.ident} ({airport.distance_nm} nm)",
                    icon=folium.Icon(color="blue", icon="plane", prefix="fa"),
                ).add_to(m)
            st_folium(m, width=700, height=600)
        else:
            st.info("No coordinates to display yet.")
elif go:
    st.warning("Upload a PDF first.")
