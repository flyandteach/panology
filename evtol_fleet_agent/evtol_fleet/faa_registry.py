from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
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
    return response.content


def extract_master_csv(zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        candidates = [name for name in zf.namelist() if name.upper().endswith("MASTER.TXT")]
        if not candidates:
            raise ValueError("MASTER.txt not found in FAA registry archive")
        return zf.read(candidates[0])


def parse_master_csv(master_csv_bytes: bytes) -> Iterable[dict[str, str]]:
    text = master_csv_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        yield {(key or "").strip(): (value or "").strip() for key, value in row.items()}


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


def parse_registry_zip(zip_bytes: bytes) -> list[RegisteredAircraft]:
    """Extract tracked manufacturers' aircraft from an already-downloaded ReleasableAircraft.zip.

    Useful as a fallback when the host running this can't download the zip itself
    (e.g. the FAA blocking that host's IP range) — download it manually from
    https://registry.faa.gov/database/ReleasableAircraft.zip elsewhere and pass
    the bytes here instead.
    """
    master_bytes = extract_master_csv(zip_bytes)
    rows = parse_master_csv(master_bytes)
    return find_manufacturer_aircraft(rows)


def fetch_manufacturer_aircraft(url: str = config.FAA_REGISTRY_URL) -> list[RegisteredAircraft]:
    """Download the FAA releasable aircraft registry and return tracked manufacturers' aircraft.

    Requires network access to registry.faa.gov, which is not reachable from every
    sandboxed environment. Run this from a host with unrestricted outbound access,
    or fall back to parse_registry_zip() with a manually downloaded copy.
    """
    zip_bytes = download_registry(url)
    return parse_registry_zip(zip_bytes)
