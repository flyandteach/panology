"""Streamlit UI for the parcel lookup agent.

Run with: streamlit run app.py
"""

import folium
import streamlit as st
from streamlit_folium import st_folium

from parcel_agent.agent import ParcelLookupAgent

st.set_page_config(page_title="Parcel Lookup Agent", layout="wide")
st.title("Parcel Lookup Agent")
st.caption(
    "Looks up a US parcel by address using free public county/city GIS data. "
    "Tries dynamic ArcGIS Online discovery, then a curated fallback registry, "
    "then (if ANTHROPIC_API_KEY is set) an LLM-suggested-and-verified GIS catalog search."
)

address = st.text_input("Street address", placeholder="e.g. 400 Broad St, Seattle, WA 98109")
go = st.button("Look up parcel", type="primary")

if go and address.strip():
    agent = ParcelLookupAgent()
    with st.spinner("Geocoding and querying county/city GIS services..."):
        result = agent.lookup(address.strip())

    col_map, col_details = st.columns([2, 1])

    with col_details:
        if result.found:
            st.success(f"Parcel found (confidence: {result.confidence}, via {result.strategy_used})")
            st.metric("APN / Parcel ID", result.apn or "unknown")
            st.write(f"**Owner:** {result.owner_name or 'unknown'}")
            st.write(f"**Situs address:** {result.situs_address or 'unknown'}")
            st.write(f"**Legal description:** {result.legal_description or 'unknown'}")
            if result.area_acres:
                st.write(f"**Acres:** {result.area_acres}")
            st.write(f"**County:** {result.county_name}, {result.state_abbr}")
            st.write(f"**Source:** {result.source_service}")
            st.write(f"**Layer:** {result.source_layer_name}")
            with st.expander("Raw attributes from the GIS service"):
                st.json(result.raw_attributes)
        else:
            st.error("No parcel found.")
            st.write(result.error)
            if result.geocode and result.geocode.found:
                st.write(f"Geocoded to {result.geocode.matched_address} "
                         f"({result.geocode.lat}, {result.geocode.lon}), "
                         f"county: {result.county_name}, {result.state_abbr}. "
                         "The address itself resolved fine -- no parcel service could be "
                         "verified for this jurisdiction. Consider adding it to "
                         "data/county_gis_registry.json.")

        with st.expander("Diagnostics: what the agent tried", expanded=not result.found):
            for attempt in result.attempts:
                icon = "✅" if attempt.success else "⛔"
                st.write(f"{icon} **{attempt.strategy}** — {attempt.detail}")

    with col_map:
        if result.geocode and result.geocode.found:
            m = folium.Map(location=[result.geocode.lat, result.geocode.lon], zoom_start=18)
            folium.Marker([result.geocode.lat, result.geocode.lon], tooltip="Geocoded address").add_to(m)
            if result.geometry:
                folium.GeoJson(
                    result.geometry,
                    style_function=lambda _: {"color": "#e63946", "weight": 3, "fillOpacity": 0.15},
                ).add_to(m)
            st_folium(m, width=700, height=550)
        else:
            st.info("No coordinates to display yet.")
elif go:
    st.warning("Enter an address first.")
