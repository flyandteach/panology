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


def download_registry(url: str = config.FAA_REGISTRY_URL, timeout: int = 120) -> bytes:
    response = requests.get(url, timeout=timeout)
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


def fetch_manufacturer_aircraft(url: str = config.FAA_REGISTRY_URL) -> list[RegisteredAircraft]:
    """Download the FAA releasable aircraft registry and return tracked manufacturers' aircraft.

    Requires network access to registry.faa.gov, which is not reachable from every
    sandboxed environment. Run this from a host with unrestricted outbound access.
    """
    zip_bytes = download_registry(url)
    master_bytes = extract_master_csv(zip_bytes)
    rows = parse_master_csv(master_bytes)
    return find_manufacturer_aircraft(rows)
