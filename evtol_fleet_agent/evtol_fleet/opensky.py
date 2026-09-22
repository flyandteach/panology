from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterator

import requests
from requests.exceptions import ConnectionError, Timeout

from . import config

logger = logging.getLogger(__name__)

# (connect, read). A short connect timeout matters: OpenSky silently drops TCP
# connections from many cloud-hosting IP ranges, so a blocked host shows up as a
# connect timeout. Failing in ~10s beats hanging a dashboard for minutes.
REQUEST_TIMEOUT = (10, 60)

BLOCKED_HOST_HINT = (
    "OpenSky could not be reached from this machine. OpenSky filters many cloud-hosting "
    "IP ranges (Streamlit Cloud, Railway, and likely other hosted runners), which shows up "
    "as a connection timeout like this one. Run the flight sync from a home/office network "
    "instead: `python scripts/sync_flights.py`, then commit data/evtol_fleet.db."
)


class OpenSkyError(RuntimeError):
    """Base class for OpenSky failures that should stop a sync run."""


class OpenSkyUnreachable(OpenSkyError):
    """OpenSky refused or dropped the connection (typically a blocked hosting IP)."""


class OpenSkyCreditsExhausted(OpenSkyError):
    """The account's API credits are used up; resume after `retry_after` seconds."""

    def __init__(self, retry_after: int | None) -> None:
        self.retry_after = retry_after
        wait = f"about {retry_after // 60} minutes" if retry_after else "a while"
        super().__init__(
            f"OpenSky API credits are exhausted for now (retry in {wait}). Progress so far "
            f"is saved; re-run the sync later and it resumes where it stopped."
        )


class OpenSkyAuthError(OpenSkyError):
    """Credentials were rejected."""


@dataclass(frozen=True)
class Flight:
    icao24: str
    first_seen: int
    last_seen: int
    est_departure_airport: str | None
    est_arrival_airport: str | None
    callsign: str | None

    @property
    def duration_seconds(self) -> int:
        return max(0, self.last_seen - self.first_seen)


def iter_windows(
    begin: int, end: int, max_window_seconds: int = config.OPENSKY_MAX_WINDOW_SECONDS
) -> Iterator[tuple[int, int]]:
    """Split [begin, end) into contiguous chunks no longer than max_window_seconds.

    Window boundaries are aligned to multiples of max_window_seconds from the Unix
    epoch; with the default 2-day window that means every window starts at UTC
    midnight and covers at most 2 calendar days (the cheapest OpenSky billing tier).
    """
    cursor = begin
    while cursor < end:
        aligned_end = (cursor // max_window_seconds + 1) * max_window_seconds
        window_end = min(aligned_end, end)
        yield cursor, window_end
        cursor = window_end


def _retry_after_seconds(response: requests.Response) -> int | None:
    for header in ("X-Rate-Limit-Retry-After-Seconds", "Retry-After"):
        value = response.headers.get(header)
        if value:
            try:
                return int(float(value))
            except ValueError:
                pass
    return None


class OpenSkyClient:
    """Client for OpenSky's REST API with OAuth2 client-credentials auth.

    Anonymous access works for testing but has a small credit allowance; register
    a free account at opensky-network.org and set OPENSKY_CLIENT_ID /
    OPENSKY_CLIENT_SECRET for real use.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_base: str = config.OPENSKY_API_BASE,
        token_url: str = config.OPENSKY_TOKEN_URL,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ) -> None:
        self.client_id = client_id or config.OPENSKY_CLIENT_ID
        self.client_secret = client_secret or config.OPENSKY_CLIENT_SECRET
        self.api_base = api_base
        self.token_url = token_url
        self.session = session or requests.Session()
        self._sleep = sleep
        self._token: str | None = None
        self._token_expiry: float = 0.0

    def is_authenticated(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_token(self, max_retries: int = 2) -> str | None:
        if not self.is_authenticated():
            return None
        if self._token and time.time() < self._token_expiry - 30:
            return self._token
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    self.token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
            except (ConnectionError, Timeout) as e:
                last_exc = e
                logger.warning("OpenSky auth attempt %s/%s failed: %s", attempt + 1, max_retries, e)
                if attempt < max_retries - 1:
                    self._sleep(3)
                continue
            if response.status_code in (400, 401):
                raise OpenSkyAuthError(
                    "OpenSky rejected the client ID/secret. Check OPENSKY_CLIENT_ID and "
                    "OPENSKY_CLIENT_SECRET (API client credentials from your OpenSky account "
                    "page, not your website username/password)."
                )
            response.raise_for_status()
            payload = response.json()
            self._token = payload["access_token"]
            self._token_expiry = time.time() + float(payload.get("expires_in", 1800))
            return self._token
        raise OpenSkyUnreachable(f"{BLOCKED_HOST_HINT} (auth server: {last_exc})") from last_exc

    def _headers(self) -> dict[str, str]:
        token = self._get_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def get_flights_for_aircraft(
        self, icao24: str, begin: int, end: int, max_retries: int = 3
    ) -> list[Flight]:
        if end - begin > config.OPENSKY_MAX_WINDOW_SECONDS:
            raise ValueError("window exceeds OpenSky's 2-day limit; use iter_windows() to chunk it")
        url = f"{self.api_base}/flights/aircraft"
        params = {"icao24": icao24.lower(), "begin": begin, "end": end}
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    url, params=params, headers=self._headers(), timeout=REQUEST_TIMEOUT
                )
            except (ConnectionError, Timeout) as e:
                last_exc = e
                logger.warning(
                    "OpenSky connection issue for %s (attempt %s/%s): %s",
                    icao24, attempt + 1, max_retries, e,
                )
                if attempt < max_retries - 1:
                    self._sleep(5 * (attempt + 1))
                continue
            if response.status_code == 404:
                # OpenSky's documented "no flights in this interval" response.
                return []
            if response.status_code == 401:
                # Token expired early; drop it and retry once with a fresh one.
                self._token = None
                continue
            if response.status_code == 429:
                retry_after = _retry_after_seconds(response)
                if retry_after is None or retry_after > config.OPENSKY_MAX_RETRY_AFTER_SECONDS:
                    raise OpenSkyCreditsExhausted(retry_after)
                logger.warning("OpenSky rate limited for %s; waiting %ss", icao24, retry_after)
                self._sleep(retry_after + 1)
                continue
            response.raise_for_status()
            data = response.json() or []
            return [
                Flight(
                    icao24=item["icao24"],
                    first_seen=item["firstSeen"],
                    last_seen=item["lastSeen"],
                    est_departure_airport=item.get("estDepartureAirport"),
                    est_arrival_airport=item.get("estArrivalAirport"),
                    callsign=(item.get("callsign") or "").strip() or None,
                )
                for item in data
            ]
        if last_exc is not None:
            raise OpenSkyUnreachable(f"{BLOCKED_HOST_HINT} ({last_exc})") from last_exc
        raise OpenSkyError(f"OpenSky request for {icao24} failed after {max_retries} attempts")

    def iter_flight_windows(
        self, icao24: str, begin: int, end: int, pause_between_requests: float = 1.0
    ) -> Iterator[tuple[int, list[Flight]]]:
        """Yield (synced_through, flights) one UTC day at a time over [begin, end).

        Each request reaches OPENSKY_WINDOW_OVERLAP_SECONDS back so flights that
        cross midnight UTC are still returned whole. Yielding per day lets callers
        save progress, so an interrupted run (credits, network) resumes cleanly.
        """
        for step_begin, step_end in iter_windows(begin, end, config.OPENSKY_SYNC_STEP_SECONDS):
            query_begin = step_begin - config.OPENSKY_WINDOW_OVERLAP_SECONDS
            flights = self.get_flights_for_aircraft(icao24, query_begin, step_end)
            yield step_end, flights
            if pause_between_requests:
                self._sleep(pause_between_requests)

    def get_flights_in_range(
        self, icao24: str, begin: int, end: int, pause_between_requests: float = 1.0
    ) -> list[Flight]:
        flights: list[Flight] = []
        for _, window_flights in self.iter_flight_windows(icao24, begin, end, pause_between_requests):
            flights.extend(window_flights)
        return flights
