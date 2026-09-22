from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from evtol_fleet import config
from evtol_fleet.metrics import summarize
from evtol_fleet.opensky import OpenSkyClient
from evtol_fleet.pipeline import refresh_flights, refresh_registry
from evtol_fleet.store import FleetStore

st.set_page_config(page_title="eVTOL Fleet Tracker", layout="wide")
st.title("eVTOL Fleet Tracker")
st.caption("FAA registry + OpenSky flight activity for Joby, Archer, and BETA aircraft.")


def get_opensky_credentials() -> tuple[str | None, str | None]:
    """Prefer Streamlit secrets (used on Community Cloud), fall back to env vars (local runs)."""
    try:
        client_id = st.secrets.get("OPENSKY_CLIENT_ID")
        client_secret = st.secrets.get("OPENSKY_CLIENT_SECRET")
    except Exception:
        client_id = client_secret = None
    return client_id or os.environ.get("OPENSKY_CLIENT_ID"), client_secret or os.environ.get(
        "OPENSKY_CLIENT_SECRET"
    )


store = FleetStore(config.DEFAULT_DB_PATH)

with st.sidebar:
    st.header("Data")
    st.caption(
        "Cached locally in SQLite. On Streamlit Community Cloud this cache is wiped whenever "
        "the app restarts (redeploys, or waking from sleep) — re-run the refresh below if the "
        "dashboard looks empty."
    )
    days_back = st.number_input(
        "Days of flight history to sync", min_value=1, max_value=365, value=30, step=1
    )
    if st.button("Refresh FAA + OpenSky data", use_container_width=True):
        client_id, client_secret = get_opensky_credentials()
        client = OpenSkyClient(client_id=client_id, client_secret=client_secret)
        if not client.is_authenticated():
            st.warning(
                "No OpenSky credentials configured — using anonymous access, which is heavily "
                "rate-limited and may fail. Set OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET in "
                "the app's Secrets."
            )
        progress = st.progress(0.0, text="Refreshing FAA registry...")
        try:
            registry_counts = refresh_registry(store)
            progress.progress(
                0.2, text=f"Registry refreshed: {registry_counts or 'no tracked aircraft found'}"
            )
            end = int(datetime.now(tz=timezone.utc).timestamp())
            begin = end - int(days_back) * 24 * 3600

            def on_progress(done: int, total: int, n_number: str) -> None:
                fraction = 0.2 + 0.8 * (done / max(total, 1))
                progress.progress(min(fraction, 1.0), text=f"Syncing flights: {n_number} ({done}/{total})")

            refresh_flights(store, client, begin, end, progress_callback=on_progress)
            progress.progress(1.0, text="Done.")
            st.success("Data refreshed.")
            st.rerun()
        except Exception as e:
            st.error(f"Refresh failed: {e}")

aircraft_rows = store.list_aircraft()

if not aircraft_rows:
    st.warning(
        "No aircraft in the local cache yet. Click **Refresh FAA + OpenSky data** in the "
        "sidebar to pull the FAA registry and OpenSky flight history."
    )
    st.stop()

manufacturers = sorted({a["manufacturer"] for a in aircraft_rows})

with st.sidebar:
    st.header("Filters")
    selected_manufacturers = st.multiselect("Manufacturer", manufacturers, default=manufacturers)
    available_n_numbers = sorted(
        a["n_number"] for a in aircraft_rows if a["manufacturer"] in selected_manufacturers
    )
    selected_n_numbers = st.multiselect("N-Number", available_n_numbers, default=available_n_numbers)
    st.caption(f"{len(aircraft_rows)} aircraft in local cache.")

filtered_aircraft = [a for a in aircraft_rows if a["n_number"] in selected_n_numbers]

if not filtered_aircraft:
    st.info("Select at least one manufacturer or N-number in the sidebar.")
    st.stop()

flight_rows = store.flights_for_n_numbers([a["n_number"] for a in filtered_aircraft])
summaries = summarize(filtered_aircraft, flight_rows)

total_flights = sum(s.total_flights for s in summaries)
total_hours = sum(s.total_flight_hours for s in summaries)

col1, col2, col3 = st.columns(3)
col1.metric("Aircraft selected", len(summaries))
col2.metric("Total flights", f"{total_flights:,}")
col3.metric("Total flight time (hrs)", f"{total_hours:,.1f}")

st.subheader("Per-aircraft summary")
summary_df = pd.DataFrame(
    [
        {
            "N-Number": s.n_number,
            "Manufacturer": s.manufacturer,
            "ICAO24": s.icao24,
            "Total Flights": s.total_flights,
            "Total Flight Hours": s.total_flight_hours,
        }
        for s in summaries
    ]
).sort_values("Total Flights", ascending=False)
st.dataframe(summary_df, use_container_width=True, hide_index=True)

st.subheader("Flights by aircraft")
st.bar_chart(summary_df.set_index("N-Number")["Total Flights"])

with st.expander("Flight log"):
    log_df = pd.DataFrame(flight_rows)
    if log_df.empty:
        st.write("No flights recorded for the current selection.")
    else:
        log_df["first_seen"] = pd.to_datetime(log_df["first_seen"], unit="s", utc=True)
        log_df["last_seen"] = pd.to_datetime(log_df["last_seen"], unit="s", utc=True)
        log_df["duration_min"] = (log_df["last_seen"] - log_df["first_seen"]).dt.total_seconds() / 60
        display_cols = [
            "n_number",
            "callsign",
            "est_departure_airport",
            "est_arrival_airport",
            "first_seen",
            "last_seen",
            "duration_min",
        ]
        st.dataframe(
            log_df[display_cols].sort_values("first_seen", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
