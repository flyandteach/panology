"""Fetches current case status from the FAA OE/AAA system for a given
Aeronautical Study Number (ASN), e.g. "2026-ANM-456-OE".

The FAA publishes a public, no-login REST lookup at:
    https://oeaaa.faa.gov/oeaaa/services/case/{asn}
per the FAA's "OE/AAA External Web Services Guide". This module calls
that endpoint but does not assume a fixed JSON schema: it scans whatever
comes back (JSON, HTML, or plain text) for one of the fixed FAA case
status words, since that vocabulary is stable regardless of response
format. If FAA changes the endpoint shape entirely, `fetch_case_status`
reports a failure rather than guessing, so callers can surface that the
checker itself is broken instead of staying silent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

CASE_URL_TEMPLATE = "https://oeaaa.faa.gov/oeaaa/services/case/{asn}"

# Fixed vocabulary of FAA OE/AAA case statuses (as seen on FAA Form 7460-1
# case printouts, e.g. "Status: Pending", "Status: Evaluating").
KNOWN_STATUSES = [
    "Determined",
    "Circularized",
    "Evaluating",
    "Interim",
    "Withdrawn",
    "Terminated",
    "Denied",
    "Pending",
]

# A status reaching one of these means the aeronautical study is finished
# and a determination has been issued.
TERMINAL_STATUSES = {"determined", "denied", "withdrawn", "terminated"}

_STATUS_RE = re.compile(
    r"\b(" + "|".join(KNOWN_STATUSES) + r")\b", re.IGNORECASE
)

REQUEST_TIMEOUT_SECONDS = 20


@dataclass
class CaseCheckResult:
    asn: str
    ok: bool
    status: str | None = None
    error: str | None = None
    checked_at: str = ""

    def __post_init__(self) -> None:
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )


def _extract_status(body: str) -> str | None:
    match = _STATUS_RE.search(body)
    if not match:
        return None
    # Normalize to the canonical capitalization from KNOWN_STATUSES.
    found = match.group(1).lower()
    for known in KNOWN_STATUSES:
        if known.lower() == found:
            return known
    return match.group(1)


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
                "Accept": "application/json, text/html;q=0.8, */*;q=0.5",
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

    status = _extract_status(response.text)
    if status is None:
        return CaseCheckResult(
            asn=asn,
            ok=False,
            error="could not find a known status keyword in the response "
            "(the FAA endpoint may have changed format)",
        )
    return CaseCheckResult(asn=asn, ok=True, status=status)


def is_terminal(status: str) -> bool:
    return status.lower() in TERMINAL_STATUSES
