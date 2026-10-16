"""Fetches current case status from the FAA OE/AAA system for a given
Aeronautical Study Number (ASN), e.g. "2026-ANM-456-OE".

FAA's public, no-login REST lookup is:
    https://oeaaa.faa.gov/oeaaa/services/case/{asn}
(confirmed against FAA's own published WADL and, live, against real
ASNs — see the "confirmed live" note below). It returns XML like:

    <caseData><OECase>
      ...
      <statusCode>NPF</statusCode>
      ...
    </OECase></caseData>

`statusCode` is FAA's raw internal case-status code, not the plain-English
word ("Pending", "Evaluating", ...) shown on the OE/AAA web UI or on a
printed Form 7460-1 — that label is derived client-side from the code and
isn't in this API response. Two mappings are confirmed live (matched
against the status printed on the originally submitted Form 7460-1 PDFs
for the same ASNs on 2026-09-04):

    NPF       -> "Pending"
    HLD-Eval  -> "Evaluating"

Beyond those two, FAA's published determination outcomes are
"Determination of No Hazard" (DNH) and "Determination of Hazard" (DOH)
per the FAA Program Handbook, but the exact statusCode string used for a
finished case has not been observed directly, so it is NOT hardcoded as
a fixed "terminal status" list here. Instead: ANY change in statusCode
is treated as notify-worthy, so an unanticipated code still reaches the
user instead of being silently misclassified.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from xml.etree import ElementTree

import requests

CASE_URL_TEMPLATE = "https://oeaaa.faa.gov/oeaaa/services/case/{asn}"

# Confirmed live 2026-09-04 by cross-checking against the status printed on
# the originally submitted Form 7460-1 PDFs for the same ASNs. Purely
# cosmetic — an unmapped code is just shown as-is, never dropped.
KNOWN_STATUS_LABELS = {
    "NPF": "Pending",
    "HLD-Eval": "Evaluating",
}

# Best-effort only, NOT verified against a live "Determined" case — codes
# containing these substrings get a "likely a final determination" flag in
# notifications, but this list gates only that cosmetic flag. Notification
# itself fires on any statusCode change regardless of this list.
LIKELY_TERMINAL_SUBSTRINGS = ["DNH", "DOH", "DET", "TERM", "DENIED", "WITHDR"]

REQUEST_TIMEOUT_SECONDS = 20


@dataclass
class CaseCheckResult:
    asn: str
    ok: bool
    status_code: str | None = None
    status_label: str | None = None
    error: str | None = None
    checked_at: str = ""
    debug_http_status: int | None = None
    debug_content_type: str | None = None
    debug_body_snippet: str | None = None

    def __post_init__(self) -> None:
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

    @property
    def display_status(self) -> str | None:
        if self.status_code is None:
            return None
        label = KNOWN_STATUS_LABELS.get(self.status_code)
        return f"{label} ({self.status_code})" if label else self.status_code


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _extract_status_code(xml_text: str) -> str | None:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return None
    for el in root.iter():
        if _local_tag(el.tag) == "statusCode" and el.text:
            return el.text.strip()
    return None


def fetch_case_status(
    asn: str, session: requests.Session | None = None
) -> CaseCheckResult:
    """Look up the current status for one ASN. Never raises; failures are
    reported on the returned CaseCheckResult so a single bad case doesn't
    abort a whole watchlist run."""
    http = session or requests
    url = CASE_URL_TEMPLATE.format(asn=asn)
    try:
        response = http.get(
            url,
            headers={
                "Accept": "application/xml, text/xml;q=0.9, */*;q=0.5",
                "User-Agent": "faa-obstruction-notifier/1.0",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return CaseCheckResult(asn=asn, ok=False, error=f"request failed: {exc}")

    if response.status_code == 404:
        return CaseCheckResult(
            asn=asn, ok=False, error="ASN not found (HTTP 404) — check the case number"
        )
    if response.status_code != 200:
        return CaseCheckResult(
            asn=asn, ok=False, error=f"unexpected HTTP {response.status_code}"
        )

    status_code = _extract_status_code(response.text)
    if status_code is None:
        return CaseCheckResult(
            asn=asn,
            ok=False,
            error="could not find a <statusCode> element in the response "
            "(the FAA endpoint may have changed format)",
            debug_http_status=response.status_code,
            debug_content_type=response.headers.get("Content-Type"),
            debug_body_snippet=response.text[:1000],
        )
    return CaseCheckResult(
        asn=asn,
        ok=True,
        status_code=status_code,
        status_label=KNOWN_STATUS_LABELS.get(status_code),
    )


def is_likely_terminal(status_code: str) -> bool:
    upper = status_code.upper()
    return any(sub in upper for sub in LIKELY_TERMINAL_SUBSTRINGS)
