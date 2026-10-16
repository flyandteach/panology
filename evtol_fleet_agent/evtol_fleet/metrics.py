from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AircraftSummary:
    n_number: str
    manufacturer: str
    icao24: str
    total_flights: int
    total_flight_seconds: int

    @property
    def total_flight_hours(self) -> float:
        return round(self.total_flight_seconds / 3600, 2)


def summarize(aircraft_rows: list[dict], flight_rows: list[dict]) -> list[AircraftSummary]:
    """Aggregate flight count and total flight time per aircraft.

    Flight time is derived from OpenSky's ADS-B-observed first/last seen timestamps
    (track duration), not engine or Hobbs time — treat it as a best-effort estimate.
    """
    flights_by_n_number: dict[str, list[dict]] = {}
    for flight in flight_rows:
        flights_by_n_number.setdefault(flight["n_number"], []).append(flight)

    summaries = []
    for aircraft in aircraft_rows:
        n_number = aircraft["n_number"]
        flights = flights_by_n_number.get(n_number, [])
        total_seconds = sum(max(0, f["last_seen"] - f["first_seen"]) for f in flights)
        summaries.append(
            AircraftSummary(
                n_number=n_number,
                manufacturer=aircraft["manufacturer"],
                icao24=aircraft["icao24"],
                total_flights=len(flights),
                total_flight_seconds=total_seconds,
            )
        )
    return summaries
