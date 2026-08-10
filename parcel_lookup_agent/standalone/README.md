# WA Parcel & Airport Locator (standalone)

A single self-contained HTML file — no backend, no build step, no Python.
Merges and hardens the three tools you built (`plsslookup.html`,
`projectlocator.html`, `waparcellocator.html`) into one:

- **Locate by address, tax parcel number, PLSS legal description
  (Township/Range/Section, with aliquot parts), or lat/lon coordinates.**
- **Paste free text or upload a PDF/DOCX/TXT/CSV** — it extracts whichever
  of those it can find, using surrounding city/county mentions as context
  even when nothing more specific is present (so a document that only says
  "near Ephrata in Grant County" still gets you an approximate location
  instead of a dead end).
- **Nearest public-use airports** with distance (nm/mi) and bearing.
- **A "Run diagnostics" panel** (top right) that tests every data source
  live and reports pass/fail with a link to the raw request — since I
  can't run this from my end, that panel is how you (or I, if you paste me
  its output) find out which specific service is actually broken instead
  of guessing.

## What changed from your three originals

I kept your working endpoints and patterns (WA DNR PLSS cadastre, WA
statewide parcels service, WSDOT airports, the Census-JSONP CORS
workaround) and added:

1. **Fallback chains**, not single points of failure:
   - PLSS: WA DNR primary → nationwide BLM cadastral service if DNR is
     unreachable.
   - Parcels: WA statewide service primary → per-county ArcGIS Online
     discovery if that fails (needs a county — Manual entry has a field
     for it, and the extractor picks it up from document text too).
   - Airports: WSDOT primary → WSDOT legacy URL → ArcGIS Online discovery
     → a small static seed list as an absolute last resort (clearly
     labeled as such in the UI).
   - Address geocoding: Census (JSONP) primary → Nominatim fallback.
2. **Two real extraction bugs fixed** (present in the original code, caught
   by testing, not just re-typed): the address regex silently truncated
   anything with a post-directional ("...Ave **N**, Shoreline, WA" used to
   stop at "Ave"), and the county regex was greedy enough to capture
   "near Ephrata in Grant" instead of "Grant" as the county name.
3. **The diagnostics panel** — new. Nothing here could be tested against
   live services from the environment I built this in (network access is
   restricted there to package registries only), so this is the mechanism
   for actually finding out what's broken instead of me guessing.

## Before you rely on it: run diagnostics first

Open the file, click **Run diagnostics** (top right), and see what's
actually reachable from your network. Expected results:

- Any row that fails with a message mentioning CORS/network → click its
  "Open raw request" link in a new tab. The browser will show you the real
  error (service moved, renamed, actually CORS-blocked, firewall, etc.) —
  that's far more informative than anything the page itself can detect.
- If **WA DNR PLSS** fails but **BLM fallback** passes, PLSS lookups still
  work, just via the nationwide source instead of the WA-specific one.
- If **WSDOT airports (primary)** fails, check whether **legacy** or
  **ArcGIS Online search** pass instead — the UI will tell you which
  source it actually used for a given lookup (shown under the airport
  list).
- If everything fails, you're most likely opening the file directly as a
  `file://` URL and something in your browser/network is blocking those
  requests — see "Hosting" below.

## Hosting

Static file, deploy anywhere:

- **GitHub Pages / Netlify / any static host** (recommended) — just serve
  this one file. Every dependency (Leaflet, pdf.js, mammoth.js) loads from
  a CDN; everything else is inline.
- **Double-clicking it locally** works in most browsers, but a `file://`
  page's requests carry no `Origin` header the way an `https://` page's
  do, which occasionally causes a service to respond differently (or a
  browser to be stricter about it) than it would over a real URL. If
  diagnostics show failures locally that don't reproduce once hosted, this
  is why — host it.

## Known limitations (by design, not oversights)

- **Washington State only.** The parcel and PLSS sources are WA-specific;
  this intentionally does not attempt nationwide coverage (see the
  scoping discussion — a nationwide version would need per-state/county
  discovery for parcels, which is a materially different and less
  reliable tool).
- **Aliquot (quarter-section) outlines are geometric approximations**,
  computed by subdividing the Section's bounding rectangle — not a
  surveyed boundary. Sections aren't perfect squares. Fine for "how far to
  the nearest airport," not for a legal boundary determination.
- **A bare parcel number with no county context** can only be resolved via
  the statewide service; if that's down and no county is known (from the
  document or Manual entry), there's no way to know which county's own
  parcel service to fall back to. Add a county in Manual entry to unlock
  that fallback.
- **The static airport seed list** is a last-resort fallback only, used
  when every live airport source fails. It is not guaranteed current —
  the UI labels results from it explicitly so you know to double check.
