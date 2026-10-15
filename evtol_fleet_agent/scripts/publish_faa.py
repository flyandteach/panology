"""Download, validate, and publish the FAA manufacturer/model inventory."""
from __future__ import annotations
import argparse
import csv
import io
import json
import os
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from sync_to_site import SITE, request_json

SOURCE = "https://registry.faa.gov/database/ReleasableAircraft.zip"
SCOPE = {"BETA": ["BETA TECHNOLOGIES"], "Joby": ["JOBY AERO"], "Archer": ["ARCHER AVIATION"], "Electra": ["ELECTRA.AERO"], "Pivotal": ["PIVOTAL AERO", "OPENER INC"]}

def parse_archive(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        def rows(name):
            with archive.open(name) as f:
                for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
                    yield {str(k).strip(): (v or "").strip() for k, v in row.items() if k is not None}
        references = {}
        for ref in rows("ACFTREF.txt"):
            name = ref.get("MFR", "").upper()
            company = next((company for company, aliases in SCOPE.items() if any(alias in name for alias in aliases)), None)
            if company:
                references[ref["CODE"]] = (company, ref["MFR"], ref["MODEL"])
        fleet = []
        for row in rows("MASTER.txt"):
            ref = references.get(row.get("MFR MDL CODE"))
            if ref is None:
                continue
            company, manufacturer, model = ref
            fleet.append(dict(registration="N"+row["N-NUMBER"], serialNumber=row["SERIAL NUMBER"], manufacturer=company, faaManufacturer=manufacturer, model=model, year=row.get("YEAR MFR") or None, statusCode=row["STATUS CODE"], icao24=row.get("MODE S CODE HEX", "").lower(), certification=row.get("CERTIFICATION") or None, aircraftTypeCode=row.get("TYPE AIRCRAFT") or None, engineTypeCode=row.get("TYPE ENGINE") or None, registrationState=row.get("STATE") or None, certificateIssueDate=row.get("CERT ISSUE DATE") or None, expirationDate=row.get("EXPIRATION DATE") or None))
        source_date = "%04d-%02d-%02d" % archive.getinfo("MASTER.txt").date_time[:3]
    if not fleet or len({a["registration"] for a in fleet}) != len(fleet):
        raise RuntimeError("FAA inventory empty or duplicated; existing inventory retained")
    if any(a["icao24"] and (len(a["icao24"]) != 6 or any(c not in "0123456789abcdef" for c in a["icao24"])) for a in fleet):
        raise RuntimeError("Invalid FAA ICAO24 identifier; existing inventory retained")
    fleet.sort(key=lambda a: (a["manufacturer"], a["registration"]))
    return dict(registryDate=source_date, source=SOURCE, downloadedAt=datetime.now(timezone.utc).isoformat(), fleet=fleet)

def run(config, archive_path=None, dry_run=False, output=None):
    if archive_path:
        data = Path(archive_path).read_bytes()
    else:
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/zip,application/octet-stream,*/*", "Referer": "https://registry.faa.gov/AircraftInquiry/"}
        with urllib.request.urlopen(urllib.request.Request(SOURCE, headers=headers), timeout=120) as response:
            data = response.read(150_000_001)
        if len(data) > 150_000_000:
            raise RuntimeError("FAA archive exceeds download limit")
    snapshot = parse_archive(data)
    print(json.dumps({"sourceDate":snapshot["registryDate"], "aircraft":len(snapshot["fleet"]), "manufacturers":{c:sum(a["manufacturer"]==c for a in snapshot["fleet"]) for c in SCOPE}}), flush=True)
    if dry_run:
        return snapshot
    for key in ("AAM_SITE_SERVICE_TOKEN", "AAM_SYNC_KEY"):
        if not config.get(key):
            raise RuntimeError("Required secret missing: " + key)
    headers = {"OAI-Sites-Authorization": "Bearer " + config["AAM_SITE_SERVICE_TOKEN"], "X-AAM-Sync-Key": config["AAM_SYNC_KEY"], "Content-Type":"application/json"}
    result, _ = request_json(SITE+"/api/fleet", data=json.dumps(snapshot).encode(), headers=headers)
    verified, _ = request_json(SITE+"/api/fleet", headers={"OAI-Sites-Authorization":headers["OAI-Sites-Authorization"]})
    if verified["registryDate"] != snapshot["registryDate"] or verified["fleet"] != snapshot["fleet"]:
        raise RuntimeError("Dashboard FAA readback does not match published inventory")
    if output:
        path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix(".tmp");temp.write_text(json.dumps(snapshot,indent=2)+"\n");temp.replace(path)
    print("FAA publication verified: " + json.dumps(result), flush=True)
    return snapshot

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive");parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--output",default="data/aam_registry_snapshot.json")
    args=parser.parse_args()
    try:
        run(os.environ,args.archive,args.dry_run,args.output)
    except Exception as error:
        print("FAA update failed; previous inventory retained: " + str(error),file=sys.stderr)
        sys.exit(1)
