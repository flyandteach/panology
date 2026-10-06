"""Publish the existing GitHub updater's cached OpenSky records to the dashboard."""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from sync_to_site import SITE, request_json

def publish(config, db_path, days=30):
    for key in ("AAM_SITE_SERVICE_TOKEN", "AAM_SYNC_KEY"):
        if not config.get(key):
            raise RuntimeError(f"Required secret is missing: {key}")
    headers = {"OAI-Sites-Authorization": "Bearer " + config["AAM_SITE_SERVICE_TOKEN"]}
    roster, _ = request_json(SITE + "/api/sync-fleet", headers=headers)
    tracked = {a["icao24"] for a in roster["fleet"]}
    if not tracked:
        raise RuntimeError("Dashboard returned an empty roster")
    path = Path(db_path).resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        watermarks = {r["icao24"]: r["synced_through"] for r in db.execute("SELECT icao24, synced_through FROM sync_state")}
        end = int(datetime.now(timezone.utc).timestamp()) // 86400 * 86400
        begin = end - days * 86400
        total = 0
        while begin < end:
            window_end = min(begin + 172800, end)
            rows = [r for r in db.execute("SELECT * FROM flights WHERE first_seen >= ? AND first_seen < ? ORDER BY first_seen", (begin, window_end)) if r["icao24"] in tracked]
            flights = [dict(icao24=r["icao24"], firstSeen=r["first_seen"], lastSeen=r["last_seen"], estDepartureAirport=r["est_departure_airport"], estArrivalAirport=r["est_arrival_airport"], callsign=r["callsign"]) for r in rows]
            available = {a for a in tracked if watermarks.get(a, 0) > begin} | {r["icao24"] for r in rows}
            coverage = all(watermarks.get(a, 0) >= window_end for a in tracked)
            if available or flights:
                payload = dict(begin=begin, end=window_end, aircraftQueried=sorted(available), flights=flights, errors=[], creditsRemaining=None, coverageComplete=coverage)
                result, _ = request_json(SITE + "/api/ingest", data=json.dumps(payload).encode(), headers={**headers, "X-AAM-Sync-Key": config["AAM_SYNC_KEY"], "Content-Type": "application/json"})
                total += result["flightsStored"]
                print(json.dumps(result), flush=True)
            begin = window_end
    data, _ = request_json(SITE + "/api/activity", headers=headers)
    print("Dashboard verification: " + json.dumps(dict(newRecords=total, month=data["month"], summary=data["summary"], lastSync=data["lastSync"])), flush=True)
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="evtol_fleet_agent/data/evtol_fleet.db")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--config-stdin", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.days <= 90:
        parser.error("--days must be between 1 and 90")
    if args.config_stdin:
        import termios
        settings = termios.tcgetattr(sys.stdin)
        settings[3] &= ~termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSANOW, settings)
        print("Ready for secrets on stdin", flush=True)
        config = json.loads(sys.stdin.readline())
    else:
        config = os.environ
    try:
        sys.exit(publish(config, args.db, args.days))
    except (RuntimeError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
