from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterator

import requests

from . import config

logger = logging.getLogger(__name__)


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
    """Split [begin, end) into chunks OpenSky's /flights/aircraft endpoint will accept."""
    cursor = begin
    while cursor < end:
        window_end = min(cursor + max_window_seconds, end)
        yield cursor, window_end
        cursor = window_end


class OpenSkyClient:
    """Client for OpenSky's REST API with OAuth2 client-credentials auth.

    Falls back to anonymous requests if no credentials are configured, but OpenSky
    heavily rate-limits (or blocks) anonymous access to historical endpoints like
    /flights/aircraft. Register a free account at opensky-network.org and set
    OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET for reliable access.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_base: str = config.OPENSKY_API_BASE,
        token_url: str = config.OPENSKY_TOKEN_URL,
        session: requests.Session | None = None,
    ) -> None:
        self.client_id = client_id or config.OPENSKY_CLIENT_ID
        self.client_secret = client_secret or config.OPENSKY_CLIENT_SECRET
        self.api_base = api_base
        self.token_url = token_url
        self.session = session or requests.Session()
        self._token: str | None = None
        self._token_expiry: float = 0.0

    def is_authenticated(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_token(self) -> str | None:
        if not self.is_authenticated():
            return None
        if self._token and time.time() < self._token_expiry - 30:
            return self._token
        response = self.session.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + float(payload.get("expires_in", 1800))
        return self._token

    def _headers(self) -> dict[str, str]:
        token = self._get_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def get_flights_for_aircraft(
        self, icao24: str, begin: int, end: int, max_retries: int = 5
    ) -> list[Flight]:
        if end - begin > config.OPENSKY_MAX_WINDOW_SECONDS:
            raise ValueError("window exceeds OpenSky's 30-day limit; use iter_windows() to chunk it")
        url = f"{self.api_base}/flights/aircraft"
        params = {"icao24": icao24.lower(), "begin": begin, "end": end}
        backoff = 5.0
        for attempt in range(max_retries):
            response = self.session.get(url, params=params, headers=self._headers(), timeout=60)
            if response.status_code == 404:
                return []
            if response.status_code == 429:
                logger.warning(
                    "OpenSky rate limited for %s (attempt %s/%s); backing off %.1fs",
                    icao24,
                    attempt + 1,
                    max_retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= 2
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
        raise RuntimeError(f"OpenSky rate limit exceeded after {max_retries} retries for {icao24}")

    def get_flights_in_range(
        self, icao24: str, begin: int, end: int, pause_between_requests: float = 1.0
    ) -> list[Flight]:
        flights: list[Flight] = []
        for window_begin, window_end in iter_windows(begin, end):
            flights.extend(self.get_flights_for_aircraft(icao24, window_begin, window_end))
            if pause_between_requests:
                time.sleep(pause_between_requests)
        return flights
