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

## Site Report: PDF -> location -> parcel -> nearest airport(s)

A second capability, on top of the same address-lookup pipeline: given a
document (survey report, memo, title report) that describes a site by street
address, PLSS legal description (e.g. `SW 1/4 Section 12, T33N, R21E, WM`),
and/or a parcel number, extract that description, resolve it to coordinates,
look up the parcel, and report the nearest public-use airport(s) with
distances.

1. **Extract** — pull text out of the PDF and find a labeled or
   pattern-matched address, PLSS description, parcel number, and county/state
   hint (`parcel_agent/pdf_ingest.py`).
2. **Resolve to coordinates** — an address is geocoded via the same pipeline
   as above. A PLSS description is resolved by querying the BLM's public PLSS
   Cadastral Survey ArcGIS service for the Section's geometry
   (`parcel_agent/plss.py`); if the description includes an aliquot part
   (e.g. "SW 1/4"), the agent approximates that sub-parcel by geometrically
   subdividing the Section's bounding box, since the national BLM layer only
   carries geometry down to the Section level. **This is an approximation,
   not a surveyed boundary** — fine for "how far to the nearest airport,"
   not for legal boundary determination.
3. **Look up the parcel** at the resolved point, reusing the same
   discovery/registry pipeline as the address flow.
4. **Find the nearest public-use airport(s)** (`parcel_agent/airports.py`),
   with distances in both nautical miles and statute miles.

A bare parcel number with no address or PLSS description isn't resolvable on
its own (there's no way to know which county's parcel service to query) —
that's reported explicitly rather than guessed.

### Airport data: bundled snapshot vs. fallback

FAA's own airport data has an explicit `Ownership`/`Facility Use` field
(`PU` = public use, `PR` = private use), which matters here — the free
`airportsdata` package used elsewhere in the Python ecosystem covers every
landing area worldwide (private ranch strips included) with no public/private
distinction.

This repo ships `data/airports_public_use_snapshot.json` as an **empty
placeholder**. To populate it with real, FAA-sourced, public-use-only data,
run from a machine with normal internet access:

```bash
python -m parcel_agent.airports_refresh
```

This searches ArcGIS Online for FAA's published Airports feature service
(rather than hardcoding a URL that could go stale), verifies it live, and
writes only public-use records to the snapshot file. If discovery doesn't
find the right service, pass it explicitly:

```bash
python -m parcel_agent.airports_refresh --service-url https://<...>/Airports/FeatureServer
```

Until you run this, nearest-airport results fall back to the `airportsdata`
package and are clearly flagged in both the CLI and the UI as **not**
verified public-use-only.

### Run the site report from the command line

```bash
python -m parcel_agent.site_report_cli --pdf report.pdf
```

### Run the site report web page

The Streamlit app is multipage — `streamlit run app.py` and use the sidebar
to switch to **Site Report**, or go straight to `pages/1_Site_Report.py`.
Upload a PDF, and the page shows the extracted fields, resolved location and
parcel on a map, the nearest airports table, and a diagnostics panel.

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
- PLSS aliquot-part (quarter-section, quarter-quarter) resolution is a
  geometric approximation of the Section's bounding box, not a surveyed
  boundary — see "Site Report" above.
- Nearest-airport results are only verified public-use-only after you've run
  `airports_refresh.py`; out of the box they use an unverified, worldwide
  (not public-use-filtered) fallback dataset.
- PDF text extraction depends on the PDF having a text layer; scanned
  documents without OCR won't yield extractable text.

## Directory structure

```
parcel_lookup_agent/
  app.py                        # Streamlit UI: address lookup
  pages/
    1_Site_Report.py            # Streamlit UI: PDF -> location -> parcel -> nearest airports
  parcel_agent/
    agent.py                    # ParcelLookupAgent: multi-strategy orchestration
    geocode.py                  # Census + Nominatim geocoding chain
    discovery.py                # ArcGIS Online dynamic service discovery
    arcgis_client.py            # Generic ArcGIS REST client + field normalization
    registry.py                 # Curated fallback registry loader
    plss.py                     # PLSS description parsing + BLM Cadastral resolution
    pdf_ingest.py                # PDF text extraction + location extraction
    airports.py                  # Nearest public-use-airport lookup
    airports_refresh.py          # One-time/periodic FAA airport snapshot refresh
    site_report.py                # Orchestrates PDF -> location -> parcel -> airports
    models.py                    # Shared dataclasses
    cli.py                        # Address-lookup CLI
    site_report_cli.py            # Site-report CLI
  data/
    county_gis_registry.json     # User-extensible fallback parcel registry
    airports_public_use_snapshot.json  # Populated by airports_refresh.py
  tests/                          # Unit tests (mocked HTTP, no network required)
```
