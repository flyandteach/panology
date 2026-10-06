"""Retrieve OpenSky flights outside the dashboard host and save them securely."""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SITE = "https://aam-fleet-tracker.flyandteach.chatgpt.site"
AUTH = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API = "https://opensky-network.org/api/flights/aircraft"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

opener = urllib.request.build_opener(NoRedirect)

def request_json(url, *, data=None, headers=None, empty_404=False):
    headers = {"Accept": "application/json", "User-Agent": "AAM-Fleet-Tracker/1.0", **(headers or {})}
    for attempt in range(2):
        try:
            with opener.open(urllib.request.Request(url, data=data, headers=headers), timeout=30) as r:
                return json.load(r), r.headers
        except urllib.error.HTTPError as e:
            if empty_404 and e.code == 404:
                return [], e.headers
            if e.code >= 500 and attempt == 0:
                time.sleep(2)
                continue
            raise RuntimeError(f"HTTP {e.code} from {urllib.parse.urlparse(url).hostname}") from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == 0:
                time.sleep(2)
                continue
            raise RuntimeError(f"Connection failed to {urllib.parse.urlparse(url).hostname}") from None
    raise RuntimeError("Request failed")

def run(config, days=2, probe=False):
    for name in ("OPENSKY_CLIENT_ID", "OPENSKY_CLIENT_SECRET", "AAM_SITE_SERVICE_TOKEN", "AAM_SYNC_KEY"):
        if not config.get(name):
            raise RuntimeError(f"Required secret is missing: {name}")
    site_headers = {"OAI-Sites-Authorization": "Bearer " + config["AAM_SITE_SERVICE_TOKEN"]}
    roster, _ = request_json(SITE + "/api/sync-fleet", headers=site_headers)
    aircraft = sorted({a["icao24"] for a in roster["fleet"]})
    if not aircraft:
        raise RuntimeError("The dashboard returned an empty aircraft roster")
    token_body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": config["OPENSKY_CLIENT_ID"], "client_secret": config["OPENSKY_CLIENT_SECRET"]}).encode()
    try:
        auth, _ = request_json(AUTH, data=token_body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        token = auth.get("access_token")
        if not token:
            raise RuntimeError("OpenSky returned no access token")
    except RuntimeError as error:
        if probe:
            raise
        end = int(datetime.now(timezone.utc).timestamp()) // 86400 * 86400
        payload = dict(begin=end-172800, end=end, aircraftQueried=[], flights=[], errors=[dict(icao24=a, error=str(error)) for a in aircraft], creditsRemaining=None)
        request_json(SITE + "/api/ingest", data=json.dumps(payload).encode(), headers={**site_headers, "X-AAM-Sync-Key": config["AAM_SYNC_KEY"], "Content-Type": "application/json"})
        raise
    if probe:
        print("OpenSky authentication succeeded; dashboard roster is accessible.")
        return 0
    end = int(datetime.now(timezone.utc).timestamp()) // 86400 * 86400
    begin = end - days * 86400
    failures = False
    while begin < end:
        window_end = min(begin + 172800, end)
        def query(icao):
            url = API + "?" + urllib.parse.urlencode(dict(icao24=icao, begin=begin, end=window_end))
            try:
                flights, headers = request_json(url, headers={"Authorization": "Bearer " + token}, empty_404=True)
                if not isinstance(flights, list):
                    raise RuntimeError("OpenSky returned an unexpected flight response")
                credit = headers.get("X-Rate-Limit-Remaining")
                return icao, flights, int(credit) if credit and credit.isdigit() else None, None
            except RuntimeError as error:
                return icao, [], None, str(error)
        flights, queried, errors, credits = [], [], [], []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            for icao, records, credit, error in executor.map(query, aircraft):
                if error:
                    errors.append(dict(icao24=icao, error=error))
                else:
                    queried.append(icao)
                    flights.extend(records)
                if credit is not None:
                    credits.append(credit)
        payload = dict(begin=begin, end=window_end, aircraftQueried=queried, flights=flights, errors=errors, creditsRemaining=min(credits) if credits else None)
        saved, _ = request_json(SITE + "/api/ingest", data=json.dumps(payload).encode(), headers={**site_headers, "X-AAM-Sync-Key": config["AAM_SYNC_KEY"], "Content-Type": "application/json"})
        print(json.dumps(saved))
        if saved["status"] != "complete":
            failures = True
            break
        begin = window_end
    readback, _ = request_json(SITE + "/api/activity", headers=site_headers)
    if not readback.get("lastSync"):
        raise RuntimeError("Dashboard did not return a saved sync result")
    print("Dashboard readback: " + json.dumps(readback["lastSync"]))
    return 1 if failures else 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--config-stdin", action="store_true", help="Read secrets from stdin for a supervised run; never write them to a file")
    args = parser.parse_args()
    if not 1 <= args.days <= 30:
        parser.error("--days must be between 1 and 30")
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
        sys.exit(run(config, args.days, args.probe))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
