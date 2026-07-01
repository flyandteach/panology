# Parcel Lookup Agent

A parcel-by-address lookup tool, built to be more resilient than a
fixed-registry app like [parcel-plotter](https://parcel-plotter.replit.app):
instead of relying only on a hand-maintained list of county GIS URLs, it
tries to *discover* the right county/city ArcGIS parcel service at query
time, and falls back through multiple strategies before giving up.

There is no single nationwide API for parcel data -- every county/city runs
its own GIS system. This agent works entirely against free, public data:

1. **Geocode** the address (Census Bureau geocoder, with an OpenStreetMap
   Nominatim + Census coordinate-lookup fallback for addresses the Census
   geocoder can't match directly).
2. **Discover** candidate parcel FeatureServers via the ArcGIS Online public
   item-search API, scoped to the resolved county/state and a bounding box
   around the address. Most US county/city GIS departments publish (or
   federate) their parcel layers through ArcGIS Online, so this generalizes
   far beyond a fixed list.
3. **Verify and query** each candidate live: fetch its service metadata,
   find the polygon layer, and run a point-in-polygon spatial query at the
   geocoded coordinates. First real match wins.
4. **Curated registry fallback** (`data/county_gis_registry.json`) for
   jurisdictions that don't show up in ArcGIS Online search. Entries are
   still verified live before use, so a stale URL just fails over to the
   next strategy instead of returning wrong data.
5. **LLM-assisted fallback** (only if `ANTHROPIC_API_KEY` is set): asks
   Claude for likely ArcGIS Server catalog roots for the jurisdiction, then
   crawls and verifies them the same way -- nothing an LLM suggests is
   trusted until it's actually queried successfully.

Every lookup returns a full attempt log, so when a parcel *isn't* found you
can see exactly which strategies were tried and why they failed, rather than
a bare "not found."

## Installation

```bash
cd parcel_lookup_agent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run from the command line

```bash
python -m parcel_agent.cli --address "400 Broad St, Seattle, WA 98109"
```

Add `--json` for machine-readable output. Exit code is `0` when a parcel is
found, `1` otherwise.

## Run the web app

```bash
streamlit run app.py
```

Enter an address, see the parcel boundary on a map alongside its details
(APN, owner, situs address, acreage where available), and expand
"Diagnostics" to see what the agent tried.

## Optional: LLM-assisted fallback

```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

Without a key, the agent simply skips the LLM-suggested-catalog strategy and
relies on discovery + the curated registry.

## Extending the curated registry

If a jurisdiction never turns up via ArcGIS Online discovery, add it to
`data/county_gis_registry.json`, keyed by 5-digit county FIPS code:

```json
{
  "53033": {
    "name": "King County, WA",
    "service_url": "https://<host>/arcgis/rest/services/<Folder>/<ServiceName>/FeatureServer",
    "layer_id": 0
  }
}
```

Find the URL via the county's open-data/GIS portal, or by searching
[arcgis.com](https://www.arcgis.com) for `"<county> parcels"`. The agent
re-verifies the entry live on every use, so an outdated URL degrades to "try
the next strategy" rather than silently returning stale data.

## Field normalization

Parcel attribute field names vary a lot by jurisdiction (`APN`, `PARCEL_ID`,
`PIN`, `PARCELNO`, `Taxlot`, ...). `parcel_agent/arcgis_client.py` matches
common naming patterns for APN, owner, situs address, legal description, and
acreage, and reports how many fields it was able to match as a rough
confidence signal (`high` / `medium` / `low`). The full raw attribute set is
always included in the result too, so nothing is lost if the heuristic
misses a jurisdiction-specific field name.

## Limitations

- US-only (built around the Census Bureau geocoder and county-level GIS).
- Some counties don't publish parcel data as a public, unauthenticated
  ArcGIS service at all (paywalled assessor portals, PDF-only records,
  etc.) -- those will legitimately come back "not found" with an attempt
  log explaining what was tried.
- ArcGIS Online discovery ranks by title-keyword relevance and geographic
  bounding box; it is a heuristic, not a guarantee of picking the
  authoritative layer when a jurisdiction publishes multiple similarly
  named services.

## Directory structure

```
parcel_lookup_agent/
  app.py                        # Streamlit UI
  parcel_agent/
    agent.py                    # ParcelLookupAgent: multi-strategy orchestration
    geocode.py                  # Census + Nominatim geocoding chain
    discovery.py                # ArcGIS Online dynamic service discovery
    arcgis_client.py            # Generic ArcGIS REST client + field normalization
    registry.py                 # Curated fallback registry loader
    models.py                   # GeocodeResult / ParcelResult / Attempt dataclasses
    cli.py                      # Command-line entry point
  data/
    county_gis_registry.json    # User-extensible fallback registry
  tests/                        # Unit tests (mocked HTTP, no network required)
```
