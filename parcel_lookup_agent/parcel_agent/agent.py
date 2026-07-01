"""ParcelLookupAgent: multi-strategy address -> parcel resolution.

Pipeline:
  1. Geocode the address (with internal retry/fallback -- see geocode.py).
  2. Discover candidate parcel FeatureServers via ArcGIS Online search,
     scoped to the resolved county/state and, once we have coordinates,
     a bounding box (discovery.py).
  3. For each candidate, verify it live (describe_service) and try a
     point-in-polygon query. First hit wins.
  4. If discovery found nothing usable, fall back to the curated
     registry (registry.py), also verified live before use.
  5. If that also fails and ANTHROPIC_API_KEY is set, ask Claude for
     likely ArcGIS Server catalog roots for that jurisdiction's GIS site
     and crawl them for a parcel service -- again, verified live, never
     trusted blindly.

Every step is logged to `ParcelResult.attempts` so a failed lookup says
exactly what was tried, instead of just "not found".
"""

from __future__ import annotations

import os

import requests

from . import arcgis_client, discovery, registry
from .geocode import geocode
from .models import Attempt, ParcelResult

MAX_CANDIDATES_TO_TRY = 5


def _try_service(service_url: str, lon: float, lat: float, label: str,
                  attempts: list[Attempt]) -> ParcelResult | None:
    """Probe one service: verify it, find polygon layers, query the point."""
    try:
        layers = arcgis_client.list_polygon_layers(service_url)
    except (requests.RequestException, arcgis_client.ArcGISError, ValueError) as exc:
        attempts.append(Attempt(strategy=label, detail=f"{service_url}: unreachable/invalid ({exc})", success=False))
        return None

    if not layers:
        attempts.append(Attempt(strategy=label, detail=f"{service_url}: no polygon layers", success=False))
        return None

    for layer in layers:
        layer_id = layer.get("id", 0)
        layer_name = layer.get("name", str(layer_id))
        try:
            features = arcgis_client.query_point(service_url, layer_id, lon, lat)
        except (requests.RequestException, arcgis_client.ArcGISError, ValueError) as exc:
            attempts.append(Attempt(strategy=label,
                                     detail=f"{service_url} layer {layer_name}: query failed ({exc})",
                                     success=False))
            continue

        if not features:
            attempts.append(Attempt(strategy=label, detail=f"{service_url} layer {layer_name}: no feature at point",
                                     success=False))
            continue

        feature = features[0]
        properties = feature.get("properties", {}) or {}
        normalized = arcgis_client.normalize_attributes(properties)
        matched = normalized.pop("matched_field_count")
        confidence = "high" if matched >= 2 else ("medium" if matched == 1 else "low")

        attempts.append(Attempt(strategy=label,
                                 detail=f"{service_url} layer {layer_name}: matched a parcel ({len(features)} candidate(s))",
                                 success=True))

        return ParcelResult(
            found=True,
            geometry=feature.get("geometry"),
            source_service=service_url,
            source_layer_name=layer_name,
            strategy_used=label,
            confidence=confidence,
            raw_attributes=properties,
            attempts=attempts,
            **normalized,
        )

    return None


def _llm_suggest_catalog_roots(county_name: str | None, state_abbr: str | None) -> list[str]:
    """Ask Claude for likely ArcGIS Server catalog root URLs for a jurisdiction.

    Purely a source of candidates to verify -- nothing here is trusted
    until it's actually fetched and found to be a real ArcGIS catalog.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not county_name:
        return []
    try:
        import anthropic
    except ImportError:
        return []

    prompt = (
        f"List up to 5 candidate ArcGIS Server REST services-directory root URLs "
        f"(the kind that end in '/arcgis/rest/services' or '/arcgis/rest/services/<folder>') "
        f"that {county_name}, {state_abbr or ''} government GIS department is likely to publish "
        f"parcel/assessor/property data on. Only return URLs you have real knowledge of; if unsure, "
        f"return fewer. Respond with one URL per line, nothing else."
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text
    except Exception:
        return []

    urls = [line.strip() for line in text.splitlines() if line.strip().startswith("http")]
    return urls[:5]


class ParcelLookupAgent:
    def __init__(self, max_candidates: int = MAX_CANDIDATES_TO_TRY, timeout: int = 20):
        self.max_candidates = max_candidates
        self.timeout = timeout

    def lookup(self, address: str) -> ParcelResult:
        attempts: list[Attempt] = []

        geo = geocode(address, timeout=self.timeout)
        attempts.append(Attempt(
            strategy="geocode",
            detail=f"{geo.source}: {'matched ' + (geo.matched_address or '') if geo.found else geo.error}",
            success=geo.found,
        ))
        if not geo.found or geo.lat is None or geo.lon is None:
            return ParcelResult(found=False, geocode=geo, attempts=attempts,
                                 error="Could not geocode the address with any available strategy.")

        result = self.lookup_at_point(geo.lat, geo.lon, county_name=geo.county_name, state_abbr=geo.state_abbr,
                                       county_fips=geo.county_fips, attempts=attempts)
        result.geocode = geo
        if not result.found:
            result.error = result.error or "Address geocoded successfully, but no parcel could be verified across all strategies."
        return result

    def lookup_at_point(self, lat: float, lon: float, county_name: str | None = None,
                         state_abbr: str | None = None, county_fips: str | None = None,
                         attempts: list[Attempt] | None = None) -> ParcelResult:
        """Find the parcel at a known point, independent of how the point was obtained.

        Used both by `lookup()` after geocoding an address, and directly by
        callers (e.g. the PLSS/site-report pipeline) that already have
        coordinates from some other source.
        """
        attempts = attempts if attempts is not None else []

        # Strategy 1: dynamic ArcGIS Online discovery.
        candidates = discovery.find_parcel_service_candidates(
            county_name=county_name, state_abbr=state_abbr, lat=lat, lon=lon, timeout=self.timeout,
        )
        attempts.append(Attempt(strategy="discovery", detail=f"found {len(candidates)} candidate service(s)",
                                 success=bool(candidates)))
        for candidate in candidates[: self.max_candidates]:
            result = _try_service(candidate["url"], lon, lat, "arcgis_online_discovery", attempts)
            if result:
                result.county_name = county_name
                result.state_abbr = state_abbr
                return result

        # Strategy 2: curated fallback registry.
        entry = registry.lookup_by_fips(county_fips)
        if entry:
            result = _try_service(entry["service_url"], lon, lat, "curated_registry", attempts)
            if result:
                result.county_name = county_name
                result.state_abbr = state_abbr
                return result
        else:
            attempts.append(Attempt(strategy="curated_registry",
                                     detail=f"no entry for county FIPS {county_fips}", success=False))

        # Strategy 3: LLM-suggested catalog roots, crawled and verified live.
        roots = _llm_suggest_catalog_roots(county_name, state_abbr)
        attempts.append(Attempt(strategy="llm_suggested_catalog", detail=f"{len(roots)} candidate root(s) suggested",
                                 success=bool(roots)))
        for root in roots:
            service_urls = arcgis_client.find_parcel_services_in_catalog(root, timeout=self.timeout)
            for service_url in service_urls[: self.max_candidates]:
                result = _try_service(service_url, lon, lat, "llm_suggested_catalog", attempts)
                if result:
                    result.county_name = county_name
                    result.state_abbr = state_abbr
                    return result

        return ParcelResult(
            found=False,
            county_name=county_name,
            state_abbr=state_abbr,
            attempts=attempts,
            error="No parcel could be verified across all strategies.",
        )
