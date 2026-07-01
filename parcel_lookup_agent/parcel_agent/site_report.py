"""Orchestrates the full "document -> location -> parcel -> nearest airports" pipeline.

    PDF/text --(pdf_ingest)--> ExtractedLocation
                                   |
             address? --------------------------- PLSS description?
                 |                                        |
        ParcelLookupAgent.lookup()              plss.resolve_plss()
                 |                                        |
             lat/lon + parcel                  lat/lon (approximate for
                 |                              aliquot parts) + Section
                 |                              geometry, then look up the
                 |                              parcel at that point too
                 +--------------------+--------------------+
                                      |
                          airports.nearest_airports()
                                      |
                                 SiteReport

Address is preferred over PLSS when both are present (a street address is
directly geocodable and generally more precise than an approximated
aliquot centroid). A bare parcel number with no address or PLSS isn't
resolvable on its own without already knowing the county's parcel service
-- that's a known limitation, reported via `attempts` rather than guessed.
"""

from __future__ import annotations

from . import airports as airports_mod
from . import pdf_ingest
from . import plss as plss_mod
from .agent import ParcelLookupAgent
from .geocode import geocode_census_coordinates
from .models import Attempt, ExtractedLocation, ParcelResult, SiteReport

DEFAULT_N_AIRPORTS = 5


class SiteReportAgent:
    def __init__(self, parcel_agent: ParcelLookupAgent | None = None,
                 n_airports: int = DEFAULT_N_AIRPORTS, timeout: int = 20):
        self.parcel_agent = parcel_agent or ParcelLookupAgent(timeout=timeout)
        self.n_airports = n_airports
        self.timeout = timeout

    def run_from_pdf(self, source) -> SiteReport:
        extracted = pdf_ingest.extract_location_from_pdf(source)
        return self._resolve(extracted)

    def run_from_text(self, text: str) -> SiteReport:
        extracted = pdf_ingest.extract_location(text)
        return self._resolve(extracted)

    def _resolve(self, extracted: ExtractedLocation) -> SiteReport:
        attempts: list[Attempt] = []
        lat = lon = None
        location_source = location_confidence = None
        parcel_result: ParcelResult | None = None
        plss_result = None

        if extracted.address:
            parcel_result = self.parcel_agent.lookup(extracted.address)
            attempts.append(Attempt(
                strategy="address",
                detail=f"parcel lookup for '{extracted.address}': "
                       f"{'found' if parcel_result.found else parcel_result.error}",
                success=parcel_result.found,
            ))
            if parcel_result.geocode and parcel_result.geocode.found:
                lat, lon = parcel_result.geocode.lat, parcel_result.geocode.lon
                location_source = "address"
                location_confidence = parcel_result.confidence if parcel_result.found else "geocoded_only"

        if lat is None and extracted.plss:
            plss_result = plss_mod.resolve_plss(extracted.plss, timeout=self.timeout)
            attempts.append(Attempt(
                strategy="plss",
                detail=f"PLSS resolution for '{extracted.plss.raw_text}': "
                       f"{'found (' + plss_result.confidence + ')' if plss_result.found else plss_result.error}",
                success=plss_result.found,
            ))
            if plss_result.found:
                lat, lon = plss_result.lat, plss_result.lon
                location_source = "plss"
                location_confidence = plss_result.confidence
                parcel_result = self._parcel_at_point(lat, lon, attempts)

        if lat is None and extracted.apn:
            attempts.append(Attempt(
                strategy="apn",
                detail="a parcel number alone (no address or PLSS description) isn't resolvable without "
                       "already knowing which county GIS service to query -- not supported yet",
                success=False,
            ))

        if lat is None:
            return SiteReport(
                found=False, extracted=extracted, attempts=attempts,
                error="Could not resolve any location (address/PLSS/parcel number) in the document to coordinates.",
            )

        nearest, verified = airports_mod.nearest_airports(lat, lon, n=self.n_airports)
        attempts.append(Attempt(strategy="nearest_airports",
                                 detail=f"found {len(nearest)} airport(s) in the "
                                        f"{'FAA public-use-verified' if verified else 'fallback (unverified public-use)'} dataset",
                                 success=bool(nearest)))

        return SiteReport(
            found=True,
            extracted=extracted,
            lat=lat, lon=lon,
            location_source=location_source,
            location_confidence=location_confidence,
            parcel=parcel_result,
            plss_result=plss_result,
            nearest_airports=nearest,
            airport_data_is_public_use_verified=verified,
            attempts=attempts,
        )

    def _parcel_at_point(self, lat: float, lon: float, attempts: list[Attempt]) -> ParcelResult | None:
        """Reuse the parcel agent's discovery pipeline at a point with no address."""
        geo = geocode_census_coordinates(lat, lon, timeout=self.timeout)
        attempts.append(Attempt(strategy="reverse_geocode_county",
                                 detail=f"{'resolved county ' + str(geo.county_name) if geo.found else geo.error}",
                                 success=geo.found))
        if not geo.found:
            return None
        return self.parcel_agent.lookup_at_point(
            lat, lon, county_name=geo.county_name, state_abbr=geo.state_abbr,
            county_fips=geo.county_fips, attempts=attempts,
        )
