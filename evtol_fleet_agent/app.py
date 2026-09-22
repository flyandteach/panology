from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from evtol_fleet import config
from evtol_fleet.metrics import summarize
from evtol_fleet.opensky import OpenSkyClient
from evtol_fleet.pipeline import (
    refresh_flights,
    refresh_registry,
    refresh_registry_from_zip_bytes,
    sync_registry_from_snapshot,
)
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

# The aircraft roster comes from a JSON snapshot committed to the repo by a scheduled
# GitHub Actions job (see scripts/refresh_registry_snapshot.py), not a live FAA call —
# registry.faa.gov blocks requests from hosting platforms like Streamlit Community Cloud
# outright, headers or not. This runs on every load; it's just a local file read, so it's
# free and keeps the store in sync with whatever's currently deployed.
_, registry_generated_at = sync_registry_from_snapshot(store)


def sync_flights(progress, start_fraction: float, days_back: int) -> None:
    client_id, client_secret = get_opensky_credentials()
    client = OpenSkyClient(client_id=client_id, client_secret=client_secret)
    if not client.is_authenticated():
        st.warning(
            "No OpenSky credentials configured — using anonymous access, which is heavily "
            "rate-limited and may fail. Set OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET in "
            "the app's Secrets."
        )
    end = int(datetime.now(tz=timezone.utc).timestamp())
    begin = end - int(days_back) * 24 * 3600

    def on_progress(done: int, total: int, n_number: str) -> None:
        fraction = start_fraction + (1 - start_fraction) * (done / max(total, 1))
        progress.progress(min(fraction, 1.0), text=f"Syncing flights: {n_number} ({done}/{total})")

    refresh_flights(store, client, begin, end, progress_callback=on_progress)


with st.sidebar:
    st.header("Data")
    st.caption(
        "Aircraft roster last updated: "
        + (registry_generated_at or "never — the registry snapshot hasn't run yet")
    )
    st.caption(
        "Flight history is cached locally and wiped whenever the app restarts on Streamlit "
        "Community Cloud (redeploys, or waking from sleep) — click below to re-sync it."
    )
    days_back = st.number_input(
        "Days of flight history to sync", min_value=1, max_value=365, value=30, step=1
    )
    if st.button("Sync latest OpenSky flights", use_container_width=True):
        progress = st.progress(0.0, text="Syncing flights...")
        try:
            sync_flights(progress, start_fraction=0.0, days_back=days_back)
            progress.progress(1.0, text="Done.")
            st.success("Flights synced.")
            st.rerun()
        except Exception as e:
            st.error(f"Sync failed: {e}")

    with st.expander("Advanced: refresh the FAA aircraft roster now"):
        st.caption(
            "The roster normally updates itself via a scheduled GitHub Actions job, so you "
            "shouldn't need this. It's here for forcing an out-of-schedule refresh — note "
            "registry.faa.gov typically blocks requests from cloud-hosted apps like this one, "
            "so the live pull below may 403. If it does, download "
            "[ReleasableAircraft.zip](https://registry.faa.gov/database/ReleasableAircraft.zip) "
            "yourself from a normal network and upload it instead."
        )
        if st.button("Try live FAA pull", use_container_width=True):
            progress = st.progress(0.0, text="Refreshing FAA registry...")
            try:
                registry_counts = refresh_registry(store)
                progress.progress(
                    1.0, text=f"Registry refreshed: {registry_counts or 'no tracked aircraft found'}"
                )
                st.success("Registry refreshed.")
                st.rerun()
            except Exception as e:
                st.error(f"Refresh failed: {e}")

        uploaded_zip = st.file_uploader("Or upload ReleasableAircraft.zip", type=["zip"])
        if uploaded_zip is not None and st.button("Sync from uploaded file", use_container_width=True):
            progress = st.progress(0.0, text="Parsing uploaded registry file...")
            try:
                registry_counts = refresh_registry_from_zip_bytes(store, uploaded_zip.read())
                progress.progress(
                    1.0, text=f"Registry refreshed: {registry_counts or 'no tracked aircraft found'}"
                )
                st.success("Registry refreshed.")
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")

aircraft_rows = store.list_aircraft()

if not aircraft_rows:
    st.warning(
        "No aircraft in the roster yet. The scheduled GitHub Actions job hasn't populated "
        "`data/tracked_aircraft.json` — trigger it manually from the repo's Actions tab, or use "
        "**Advanced: refresh the FAA aircraft roster now** in the sidebar."
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
    st.caption(f"{len(aircraft_rows)} aircraft in roster.")

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
