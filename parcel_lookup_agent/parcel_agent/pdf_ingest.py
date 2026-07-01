"""Extract a location description (address, PLSS, or parcel number) from a PDF.

Designed for the kind of document a real-estate/aviation site review deals
with: survey reports, title reports, memos -- where the location is stated
in prose or a labeled field, not in a structured table.

Extraction is a best-effort, layered heuristic:
  1. Look for a labeled field ("Site Address:", "Parcel Number:", ...).
  2. Fall back to a generic pattern match anywhere in the text.
  3. PLSS descriptions are found via `plss.parse_plss`, which already
     handles both labeled and unlabeled occurrences.

Nothing here guarantees correctness on an arbitrary document -- it's meant
to get the obvious case right and otherwise leave fields as None so the
caller can ask a human to fill the gap, rather than silently guessing.
"""

from __future__ import annotations

import re

from . import plss as plss_mod
from .models import ExtractedLocation

_US_STATE_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}

_LABELED_ADDRESS = re.compile(
    r"(?:site|property|situs|location|subject)\s*address\s*:?\s*(?P<addr>[^\n]{6,120})", re.IGNORECASE
)
_STREET_SUFFIXES = (
    r"St(?:reet)?|Ave(?:nue)?|Rd|Road|Dr(?:ive)?|Ln|Lane|Blvd|Boulevard|Way|Ct|Court|"
    r"Pl(?:ace)?|Hwy|Highway|Cir(?:cle)?|Pkwy|Parkway|Ter(?:race)?"
)
_GENERIC_ADDRESS = re.compile(
    rf"\b\d{{1,6}}\s+[A-Za-z0-9.'\s]{{2,40}}?\s+(?:{_STREET_SUFFIXES})\b\.?[^\n]{{0,45}}",
    re.IGNORECASE,
)

_LABELED_PARCEL = re.compile(
    r"(?:tax\s+)?(?:assessor'?s?\s+)?parcel\s*(?:number|no\.?|id)?\s*:?\s*(?P<apn>[A-Z0-9][A-Z0-9\-]{4,25})",
    re.IGNORECASE,
)
_LABELED_APN = re.compile(r"\bAPN\s*:?\s*(?P<apn>[A-Z0-9][A-Z0-9\-]{4,25})", re.IGNORECASE)

_COUNTY_STATE = re.compile(
    r"(?P<county>[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){0,2})\s+County,?\s+"
    r"(?P<state>[A-Z]{2}\b|[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)"
)


def extract_text_from_pdf(source) -> str:
    """`source` can be a file path, a file-like object, or raw bytes."""
    from pypdf import PdfReader

    reader = PdfReader(source)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def _extract_address(text: str) -> str | None:
    labeled = _LABELED_ADDRESS.search(text)
    if labeled:
        return labeled.group("addr").strip().rstrip(",;")
    generic = _GENERIC_ADDRESS.search(text)
    if generic:
        return generic.group(0).strip().rstrip(",;")
    return None


def _extract_apn(text: str) -> str | None:
    labeled = _LABELED_APN.search(text) or _LABELED_PARCEL.search(text)
    if labeled:
        return labeled.group("apn").strip()
    return None


def _extract_county_state(text: str) -> tuple[str | None, str | None]:
    match = _COUNTY_STATE.search(text)
    if not match:
        return None, None
    county = match.group("county").strip()
    state_raw = match.group("state").strip()
    if len(state_raw) == 2:
        return county, state_raw.upper()
    return county, _US_STATE_ABBR.get(state_raw.lower())


def extract_location(text: str) -> ExtractedLocation:
    plss_desc = plss_mod.parse_plss(text)
    county, state = _extract_county_state(text)
    return ExtractedLocation(
        address=_extract_address(text),
        plss=plss_desc,
        apn=_extract_apn(text),
        county_hint=county,
        state_hint=state,
        raw_text_excerpt=text[:400].strip(),
    )


def extract_location_from_pdf(source) -> ExtractedLocation:
    text = extract_text_from_pdf(source)
    return extract_location(text)
