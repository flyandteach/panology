# Drone Delivery Hub Designer

A design tool for permanent, high-tempo drone delivery hubs at retail sites.

Today's store hubs are interim setups. Wing's Walmart nests, for example, are
described as a fenced area of the parking lot with a shipping container and
pads, built so a service can be launched quickly. This tool sizes a hub
meant for long-term, high-tempo use, and grades it against that interim
parking-lot baseline on the same aircraft, demand and site.

It is a screening and comparison tool, not an engineering or permitting
model. **Every default value is a placeholder**: it does not describe any
vendor's aircraft and does not come from a regulation. Replace the defaults
with OEM data, site measurements and the requirements of the authority
having jurisdiction (AHJ).

## What it models

| Area | Method (`hub/…`) |
|---|---|
| Throughput (`capacity.py`) | Mean trip = 2/3 of the service radius, which is the mean distance for deliveries spread evenly over a disc. Fleet comes from Little's law (sortie rate x cycle time) plus a spare share. Pads are sized with an M/M/c (Erlang C) queue against a mean-wait target and a utilisation cap. Pack count and charging slots are sized for swap or onboard charging. |
| Turnaround placement | `turnaround_on_pad = True` (baseline) keeps the pad busy through loading and the swap. `False` (proposed) uses the pad only for lift-off and landing, with loading done in a covered bay. |
| Noise (`noise.py`) | Point source with spherical spreading (-6 dB per doubling of distance), energy sum of pads busy at once, and the Maekawa / Kurze-Anderson thin-barrier approximation (capped at 20 dB, no credit if the barrier does not break line of sight). Covers lift-off and landing only. A barrier does nothing for overflight. |
| Fire (`fire.py`) | Total lithium-ion energy on site, flagged above **20 kWh**, the level at which NFPA 855 applies to lithium-ion energy storage systems. It also checks battery-room separation, suppression and temperature control. Whether spare drone packs on chargers count as an ESS is the AHJ's call. The 2026 edition of NFPA 855 makes a hazard mitigation analysis the default. |
| Weather / night (`weather.py`) | Hours lost to the aircraft's own limits (wind, precipitation, night), plus extra hours lost to the facility: uncovered loading in rain, snow on unheated pads, heat-limited charging without a conditioned battery room, and no lighting after dark. Conditions are treated as independent. |
| Layout (`layout.py`) | Places, from the store outward: public setback, operations building, fenced apron with the pad grid, and a battery room set apart by the separation distance. Draws the result as SVG and reports whether it fits the lot. |
| Reference aircraft (`aircraft_library.py`, `sources.py`) | Pick Wing Hummingbird 8000-A or 7000W-B, Zipline P2, Amazon MK30, Flytrex Sky2, or a generic aircraft. Each value records its source and a confidence level: 2+ sources, single source, unverified, or placeholder. Values the user edits show as user input. |
| Flight paths (`flightpath.py`) | Tests every compass heading (5° steps) for a straight departure/arrival corridor. The aircraft lifts vertically, then climbs at a constant gradient to cruise. A heading is blocked if the aircraft is not at least the clearance margin above an obstacle in the lane. The tool also measures how much of each lane is flown below each sensitive zone's minimum overflight height. Corridors are chosen to minimise low overflight first, then the extra distance fixed corridors add to deliveries spread evenly over the service area. The corridor count comes from the movement rate and the per-corridor spacing. The added distance feeds into fleet sizing. |
| Costs (`costs.py`) | Bill of quantities from the design, multiplied by unit costs you enter. Capital is annualised with the capital recovery factor, using separate aircraft and infrastructure lives. Operating costs cover energy, demand charges, staff (ground crew sized from the tempo), maintenance, pack replacement and lease. Cost per delivery = annual cost / (daily orders x 365 x availability). |
| Scorecard (`design.py`) | Pass/fail checks per category. The thresholds in `CRITERIA` are this tool's defaults, not regulations. |

The parking-lot baseline (`models.parking_lot_baseline`) keeps your pad
geometry and sizing targets. It turns off covered loading, heated pads,
lighting, the noise barrier, battery separation, suppression and
conditioning. It puts turnaround back on the pad and shrinks setbacks to 2 m
and the building to one container. Edit that function if the interim site
you are comparing against differs.

## Reference aircraft: what is and isn't published

Figures come from FAA environmental assessments, the manufacturers and the
press, gathered in October 2026 from web search excerpts. This environment
could not open the PDFs themselves, so open the linked document before relying
on a number. Gaps that stay as placeholders for every aircraft: climb rate and
climb speed, pad occupancy times, pack energy and charge time. Wing and
Zipline also have no published hover Lmax; their FAA assessments give takeoff
and delivery noise only as an SEL ceiling, without a distance. FAA assessments
do give minimum distances from noise-sensitive areas: Wing nests 65 ft (120 ft
in Class B/C/D airspace) and Zipline docks 150 ft (325 ft in Class B/D). The
tool checks the nearest receptor against these.

With onboard charging (Wing, Zipline), the charge time drives fleet size and,
in the baseline, pad count, because the aircraft charges where it lands. The
45-minute default is a placeholder, so enter the operator's figure.

## Costs: no prices are shipped

Every unit cost defaults to zero ("not entered"); the app and CLI list the
missing ones. The exception is electricity: 13.86 cents/kWh, the US
commercial average for January-June 2026 from EIA Table 5.6.B, taken from a
secondary source. Discount rate, asset lives, pack cycle life, charger
efficiency and crew utilisation have placeholder defaults; edit them.

## Not yet modelled

- Airspace classes, airport proximity, terrain and the operator's own route
  approvals. Corridors are straight lanes against the obstacles and zones
  you enter.
- Detailed sizing of the battery room's floor area and ventilation.
- Noise from overflight, tonal penalties and day-night averages (Ldn).
- Parcel flow from the store to the hub.
- Downwash and FOD loading on surrounding surfaces.

## Use

```bash
cd drone_hub_designer
pip install -r requirements.txt
streamlit run app.py                     # interactive designer
python -m hub.cli examples/high_tempo_suburban.json --svg layout.svg
python -m hub.cli --json                 # defaults, full JSON output
pytest
```

Inputs are six groups (`aircraft`, `demand`, `site`, `design`, `airspace`,
`costs`). Setting `aircraft.reference_id` fills every other aircraft field
from the library, and any field you give overrides it. The app can
save and load them as JSON, and `examples/` has a 90-orders/hour case using the Wing 8000-A.

## Regulatory context (as of October 2026)

- The FAA's proposed Part 108 BVLOS rule had not been published as final as
  of mid-2026; reporting says it went to White House review on 2026-07-10.
  Check the FAA rulemaking page (RIN 2120-AL82) for current status.
- Local governments approve the ground site plan. Zoning has been denied in
  at least one county over impacts on residential areas, so the noise and
  setback outputs are what a site-plan submission will be judged on.

Sources: [DroneXL Walmart/Wing operations](https://dronexl.co/2024/06/04/wing-drone-delivery-operations-walmart/),
[Supermarket News](https://www.supermarketnews.com/grocery-technology/video-walmart-wing-drone-service-reaching-new-heights-in-dallas-fort-worth),
[GadgetReview on zoning pushback](https://www.gadgetreview.com/walmarts-parking-lot-drone-airports-are-going-viral-and-the-neighbors-are-furious),
[Energy-Storage.news on NFPA 855 (2026)](https://www.energy-storage.news/nfpa-855-2026-edition-updates-and-what-they-mean-for-energy-storage-projects/),
[DroneXL on the Part 108 delay](https://dronexl.co/2026/06/18/faa-part-108-presumptive-right-of-way-bvlos-delay/).
These are secondary sources. Confirm the code and rule figures against the
edition your jurisdiction has adopted.
