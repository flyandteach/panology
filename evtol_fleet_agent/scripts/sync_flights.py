"""Sync OpenSky flight history for every aircraft in the committed roster.

Run this from a home or office network. OpenSky drops connections from many
cloud-hosting IP ranges (Streamlit Cloud, and possibly GitHub's hosted runners),
so a normal residential connection is the most reliable place to run it:

    cd evtol_fleet_agent
    export OPENSKY_CLIENT_ID=...  OPENSKY_CLIENT_SECRET=...
    python scripts/sync_flights.py --days 90
    git add data/evtol_fleet.db && git commit -m "Update flight history" && git push

It resumes from where the last run stopped, so running it again after an
interruption (or after OpenSky credits refill) only fetches what's missing.
Exit code is 0 on a clean run or when it paused because OpenSky's daily credits
ran out (expected during the initial backfill; the next run continues), and 2
for real problems (OpenSky unreachable, bad credentials, per-aircraft errors).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evtol_fleet import config
from evtol_fleet.opensky import OpenSkyClient, OpenSkyCreditsExhausted
from evtol_fleet.pipeline import SyncReport, refresh_flights, sync_registry_from_snapshot
from evtol_fleet.store import FleetStore


def _fmt(ts: int | None) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else "n/a"


def print_report(report: SyncReport) -> None:
    total = sum(report.new_flights.values())
    print(f"New flights stored: {total} ({report.new_flights})")
    print(f"Flight data is final through {_fmt(report.synced_through)} UTC (OpenSky publishes daily).")
    for n_number, error in report.errors.items():
        print(f"  ERROR {n_number}: {error}")
    if report.stopped_reason:
        print(f"STOPPED EARLY: {report.stopped_reason}")


def run(days: int, db_path: str, manufacturer: str | None = None) -> SyncReport:
    with FleetStore(db_path) as store:
        counts, generated_at = sync_registry_from_snapshot(store)
        print(f"Roster: {counts} (snapshot {generated_at})")
        client = OpenSkyClient()
        if not client.is_authenticated():
            print(
                "WARNING: OPENSKY_CLIENT_ID/OPENSKY_CLIENT_SECRET not set; anonymous access has a "
                "small credit allowance, so the run may stop early (it will resume next time)."
            )
        begin = int(datetime.now(tz=timezone.utc).timestamp()) - days * config.DAY_SECONDS

        def progress(done: int, total: int, n_number: str) -> None:
            print(f"  [{done}/{total}] {n_number}")

        report = refresh_flights(
            store, client, begin, manufacturer=manufacturer, progress_callback=progress
        )
    print_report(report)
    return report


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=90, help="How far back to backfill (default 90).")
    parser.add_argument("--db", default=config.DEFAULT_DB_PATH)
    parser.add_argument("--manufacturer", choices=sorted(config.MANUFACTURER_NAME_PATTERNS))
    args = parser.parse_args()
    report = run(args.days, args.db, args.manufacturer)
    credits_pause = isinstance(report.stop_error, OpenSkyCreditsExhausted) and not report.errors
    if credits_pause:
        # GitHub Actions annotation: shows as a yellow note, not a failed run.
        print("::warning::OpenSky daily credits used up; progress saved, next run continues the backfill.")
    sys.exit(0 if report.ok or credits_pause else 2)


if __name__ == "__main__":
    main()
