from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

from . import config


@dataclass(frozen=True)
class RegisteredAircraft:
    n_number: str
    icao24: str
    manufacturer: str
    owner_name: str
    year_mfr: str
    status_code: str


def _match_manufacturer(n_number: str, owner_name: str) -> str | None:
    override = config.MANUAL_N_NUMBER_OVERRIDES.get(n_number)
    if override:
        return override
    upper = owner_name.upper()
    for manufacturer, patterns in config.MANUFACTURER_NAME_PATTERNS.items():
        if any(pattern in upper for pattern in patterns):
            return manufacturer
    return None


# registry.faa.gov's bot protection returns a bare 403 to requests that don't
# look like a browser (no User-Agent/Accept/Referer). These headers mimic a
# normal browser fetch, which is enough to get past it.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/zip,application/octet-stream,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://registry.faa.gov/AircraftInquiry/",
}


def download_registry(url: str = config.FAA_REGISTRY_URL, timeout: int = 120) -> bytes:
    response = requests.get(url, timeout=timeout, headers=BROWSER_HEADERS)
    if response.status_code == 403:
        raise RuntimeError(
            "FAA registry returned 403 Forbidden even with browser-like headers. "
            "This usually means the FAA is blocking requests from this host's IP range "
            "(common for cloud/datacenter IPs, including Streamlit Community Cloud). "
            "Try downloading ReleasableAircraft.zip from a residential/office network "
            "and loading it via a local file instead."
        )
    response.raise_for_status()
    content = response.content
    # A 200 response isn't necessarily the real file: bot-protection can return an
    # HTML challenge/interstitial page with a 200 status instead of a hard 403. Fail
    # loudly here rather than let a bad response silently parse into zero aircraft.
    if not content.startswith(b"PK"):
        preview = content[:300].decode("utf-8", errors="replace")
        raise RuntimeError(
            "FAA registry response doesn't look like a zip file (no 'PK' magic bytes) — "
            "likely a bot-protection interstitial page returned with a 200 status instead "
            "of the real file. Response preview:\n" + preview
        )
    return content


def extract_master_csv(zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        candidates = [name for name in zf.namelist() if name.upper().endswith("MASTER.TXT")]
        if not candidates:
            raise ValueError("MASTER.txt not found in FAA registry archive")
        return zf.read(candidates[0])


REQUIRED_COLUMNS = ("N-NUMBER", "NAME", "MODE S CODE HEX")

# The real registry lists ~300k aircraft. Far fewer rows means a truncated or
# wrong file, which must never be allowed to overwrite a good roster.
MIN_EXPECTED_REGISTRY_ROWS = 100_000


def _clean_key(key: str | None) -> str:
    # MASTER.txt starts with a UTF-8 byte-order mark. str.strip() does not remove
    # U+FEFF, so without this the first column is "\ufeffN-NUMBER", every lookup of
    # "N-NUMBER" comes back empty, and every aircraft is silently skipped.
    return (key or "").replace("\ufeff", "").strip().upper()


def parse_master_csv(master_csv_bytes: bytes) -> Iterable[dict[str, str]]:
    text = master_csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    header = {_clean_key(name) for name in (reader.fieldnames or [])}
    missing = [col for col in REQUIRED_COLUMNS if col not in header]
    if missing:
        raise ValueError(
            f"FAA MASTER.txt is missing expected column(s) {missing}; found {sorted(header)[:12]}. "
            "The FAA may have changed the file layout."
        )
    for row in reader:
        yield {_clean_key(key): (value or "").strip() for key, value in row.items() if key is not None}


def find_manufacturer_aircraft(rows: Iterable[dict[str, str]]) -> list[RegisteredAircraft]:
    results: list[RegisteredAircraft] = []
    for row in rows:
        raw_n_number = row.get("N-NUMBER", "")
        owner_name = row.get("NAME", "")
        icao24 = row.get("MODE S CODE HEX", "")
        if not raw_n_number or not icao24:
            continue
        n_number = raw_n_number if raw_n_number.startswith("N") else f"N{raw_n_number}"
        manufacturer = _match_manufacturer(n_number, owner_name)
        if not manufacturer:
            continue
        results.append(
            RegisteredAircraft(
                n_number=n_number,
                icao24=icao24.lower(),
                manufacturer=manufacturer,
                owner_name=owner_name,
                year_mfr=row.get("YEAR MFR", ""),
                status_code=row.get("STATUS CODE", ""),
            )
        )
    return results


def parse_registry_zip(
    zip_bytes: bytes, min_rows: int = MIN_EXPECTED_REGISTRY_ROWS
) -> list[RegisteredAircraft]:
    """Extract tracked manufacturers' aircraft from an already-downloaded ReleasableAircraft.zip.

    Useful as a fallback when the host running this can't download the zip itself
    (e.g. the FAA blocking that host's IP range) — download it manually from
    https://registry.faa.gov/database/ReleasableAircraft.zip elsewhere and pass
    the bytes here instead.
    """
    master_bytes = extract_master_csv(zip_bytes)
    rows = list(parse_master_csv(master_bytes))
    if len(rows) < min_rows:
        raise ValueError(
            f"FAA registry has only {len(rows):,} rows (expected over {min_rows:,}); "
            "the download looks truncated or wrong."
        )
    aircraft = find_manufacturer_aircraft(rows)
    if not aircraft:
        raise ValueError(
            f"Parsed {len(rows):,} registry rows but none matched Joby/Archer/BETA. That is "
            "almost certainly a parsing problem, not reality; refusing to save an empty roster."
        )
    return aircraft


def fetch_manufacturer_aircraft(url: str = config.FAA_REGISTRY_URL) -> list[RegisteredAircraft]:
    """Download the FAA releasable aircraft registry and return tracked manufacturers' aircraft.

    Requires network access to registry.faa.gov, which is not reachable from every
    sandboxed environment. Run this from a host with unrestricted outbound access,
    or fall back to parse_registry_zip() with a manually downloaded copy.
    """
    zip_bytes = download_registry(url)
    return parse_registry_zip(zip_bytes)


def write_snapshot(aircraft: list[RegisteredAircraft], path: str | Path) -> None:
    """Write tracked aircraft to a small JSON snapshot the app can read without a live FAA call.

    Intended to be run from an environment with unrestricted FAA egress (e.g. a
    scheduled CI job) and the result committed to the repo.
    """
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "aircraft": [asdict(a) for a in sorted(aircraft, key=lambda a: a.n_number)],
    }
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_snapshot(path: str | Path) -> tuple[list[RegisteredAircraft], str | None]:
    """Read a JSON snapshot written by write_snapshot(). Returns (aircraft, generated_at)."""
    snapshot_path = Path(path)
    if not snapshot_path.exists():
        return [], None
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    aircraft = [RegisteredAircraft(**row) for row in payload.get("aircraft", [])]
    return aircraft, payload.get("generated_at")


def diff_aircraft(old: list[RegisteredAircraft], new: list[RegisteredAircraft]) -> dict[str, list[str]]:
    """Compare two aircraft lists (e.g. last month's snapshot vs. a fresh pull) by N-number.

    Returns {"added": [...], "removed": [...]} (N-numbers only, sorted). A "removed"
    N-number doesn't necessarily mean deregistered — it also covers an aircraft that
    changed owners away from a tracked manufacturer.
    """
    old_n_numbers = {a.n_number for a in old}
    new_n_numbers = {a.n_number for a in new}
    return {
        "added": sorted(new_n_numbers - old_n_numbers),
        "removed": sorted(old_n_numbers - new_n_numbers),
    }
