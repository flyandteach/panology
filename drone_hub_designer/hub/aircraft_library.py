"""Reference delivery aircraft, with the source behind every value.

A field listed under "values" was taken from the sources named next to it. Any
AircraftProfile field not listed keeps the generic placeholder default and is
reported as a placeholder. Nothing here comes from the manufacturers' spec
sheets, which were not reachable; see hub/sources.py for that caveat.

Units are converted to SI from the published imperial figures:
1 ft = 0.3048 m, 1 mph = 0.44704 m/s, 1 kt = 0.51444 m/s, 1 mi = 1.609344 km.
"""

from __future__ import annotations

from dataclasses import fields

from .models import AircraftProfile
from .sources import SOURCES

FT = 0.3048
MPH = 0.44704
KT = 0.514444
MI = 1.609344

GENERIC = "generic"

LIBRARY = {
    GENERIC: {
        "name": "Generic small multirotor (all placeholders)",
        "values": {},
        "facts": [],
    },
    "wing_8000a": {
        "name": "Wing Hummingbird 8000-A",
        "values": {
            "span_m": (6 * FT, ["axios_noise"], "6 ft wingspan; only one source found."),
            "cruise_speed_mps": (51 * KT, ["dronexl_aircraft", "axios_noise"],
                                 "51 kt per FAA table; Axios gives 60 mph top speed."),
            "max_range_km": (2 * 6 * MI, ["dronexl_aircraft"],
                             "About 6 mi from each nest, taken as a radius. Axios reports a 12-mile "
                             "operating radius instead; unresolved."),
            "battery_mode": ("onboard", ["wing_how_drones_work"],
                             "Returns to the facility and lands on a charging pad."),
            "cruise_altitude_m": (150 * FT, ["aiwiki_wing"],
                                  "About 150 ft. Wing's own 2021 article says 100-130 ft above obstacles."),
            "launch_infrastructure": ("charging pad", ["wing_how_drones_work"], ""),
            "delivery_method": ("tether from ~23 ft hover", ["wing_how_drones_work", "dronexl_aircraft"], ""),
            "receptor_setback_m": (65 * FT, ["faa_wing_dfw_sea", "faa_wing_cfl"],
                                   "Nests at least 65 ft from noise-sensitive areas (120 ft in Class B/C/D "
                                   "airspace)."),
        },
        "facts": [
            ("Max takeoff weight", "24.3 lb per FAA table; Axios reports about 17 lb.",
             ["dronexl_aircraft", "yanko_wing", "axios_noise"]),
            ("Payload", "About 5 to 6.6 lb.", ["dronexl_aircraft", "yanko_wing"]),
            ("In-flight noise", "62.0 dBA SEL at 165 ft AGL.", ["faa_wing_houston_draft"]),
            ("Takeoff / delivery noise",
             "Below 84 dB SEL for about 30 s (distance not given in the excerpt). No hover Lmax found, so "
             "the hub noise check uses the placeholder level.", ["faa_wing_houston_draft"]),
            ("Setback in controlled airspace", "120 ft from noise-sensitive areas in Class B/C/D airspace.",
             ["faa_wing_dfw_sea", "faa_wing_cfl"]),
            ("Approved tempo", "Up to 400 deliveries per nest per operating day, 7 am to 10 pm.",
             ["faa_wing_cfl"]),
        ],
    },
    "wing_7000wb": {
        "name": "Wing Hummingbird 7000W-B",
        "values": {
            "battery_mode": ("onboard", ["wing_how_drones_work"],
                             "Returns to the facility and lands on a charging pad."),
            "cruise_altitude_m": (150 * FT, ["aiwiki_wing"], "Wing-wide figure, not model-specific."),
            "launch_infrastructure": ("charging pad", ["wing_how_drones_work"], ""),
            "delivery_method": ("tether from ~23 ft hover", ["wing_how_drones_work", "dronexl_aircraft"], ""),
            "receptor_setback_m": (65 * FT, ["faa_wing_dfw_sea", "faa_wing_cfl"],
                                   "Operator-wide EA setback (120 ft in Class B/C/D airspace)."),
        },
        "facts": [
            ("Max takeoff weight", "14 lb.", ["dronexl_aircraft", "yanko_wing"]),
            ("Payload", "About 2.3 to 2.7 lb.", ["dronexl_aircraft"]),
            ("In-flight noise", "56.5 dBA SEL at 165 ft AGL.", ["faa_wing_houston_draft"]),
            ("Dimensions, speed, range", "No model-specific figures found; placeholders used.", []),
        ],
    },
    "zipline_p2": {
        "name": "Zipline P2 Zip",
        "values": {
            "cruise_speed_mps": (70 * MPH, ["wiki_zipline"], "About 70 mph (110 km/h)."),
            "max_range_km": (2 * 10 * MI, ["cnbc_p2", "uavorg_p2"],
                             "10-mile service radius out and back with a 6-8 lb payload."),
            "battery_mode": ("onboard", ["cnbc_p2", "urgentcomm_p2"], "Docks and recharges automatically."),
            "cruise_altitude_m": (330 * FT, ["faa_zipline_dfw", "wiki_zipline"],
                                  "Holds 330 ft AGL to deliver; Pea Ridge reevaluation gives 100-400 ft."),
            "delivery_dwell_s": (75.0, ["faa_zipline_dfw"], "Hovers about 75 s to lower the droid."),
            "launch_infrastructure": ("dock", ["urgentcomm_p2", "cnbc_p2"],
                                      "Dock can be mounted on a building or stand free; no ground pad."),
            "delivery_method": ("droid lowered on tether from cruise altitude",
                                ["faa_zipline_pea_ridge", "faa_zipline_dfw"], ""),
            "receptor_setback_m": (150 * FT, ["faa_zipline_dfw"],
                                   "Docks at least 150 ft from noise-sensitive areas (325 ft in Class B/D)."),
        },
        "facts": [
            ("Payload", "Up to 8 lb.", ["cnbc_p2", "uavorg_p2", "dronexl_zipline"]),
            ("Weight", "55 lb empty, 63 lb max takeoff.", ["dronexl_zipline"]),
            ("One-way range", "Up to 24 mi when landing at another dock.", ["uavorg_p2", "cnbc_p2"]),
            ("In-flight noise", "69.1 dBA SEL at 330 ft AGL.", ["faa_zipline_dfw"]),
            ("Takeoff / delivery noise", "Below 85 dB SEL for about 30 s. No hover Lmax found.", ["faa_zipline_dfw"]),
            ("Wingspan", "Not found; placeholder used.", []),
        ],
    },
    "amazon_mk30": {
        "name": "Amazon Prime Air MK30",
        "values": {
            "span_m": (5.5 * FT, [], "About 5.5 ft per press coverage; outlet not confirmed."),
            "cruise_speed_mps": (67 * MPH, ["faa_amz_pendleton"],
                                 "About 67 mph wing-borne. Other FAA documents give 62 mph and a 73 mph maximum."),
            "max_range_km": (2 * 7.5 * MI, ["faa_amz_chicago_d", "faa_amz_pendleton"],
                             "7.5 mi, taken as a radius as press reports describe it; FAA wording is "
                             "'maximum operating range', so it may be round trip."),
            "cruise_altitude_m": (180 * FT, ["faa_amz_tpa"], "En route 180-377 ft AGL; lower bound used."),
            "delivery_dwell_s": (61.0, ["faa_amz_fla_final"], "Delivery cycle about 61 s."),
            "hover_noise_dba": (70.0, ["faa_amz_chicago_d", "faa_amz_omaha"], "Takeoff Lmax about 70 dB at 75 ft."),
            "noise_ref_distance_m": (75 * FT, ["faa_amz_chicago_d", "faa_amz_omaha"], ""),
            "launch_infrastructure": ("takeoff/landing pad", ["faa_amz_tpa"], ""),
            "delivery_method": ("drops package from ~13 ft", ["faa_amz_tpa", "faa_amz_fla_final"], ""),
        },
        "facts": [
            ("Weight", "77.9 lb empty, 83.2 lb max takeoff.", ["faa_amz_chicago_d", "uavorg_mk30"]),
            ("Payload", "5 lb.", ["faa_amz_chicago_d", "uavorg_mk30"]),
            ("Delivery noise", "Lmax about 69 dB at 75 ft.", ["faa_amz_chicago_d", "faa_amz_omaha"]),
            ("In-flight noise", "63.7 dB SEL at 200 ft AGL.", ["faa_amz_chicago_d"]),
            ("Takeoff", "Vertical on powered lift, then transitions to wing-borne flight.", ["faa_amz_tpa"]),
            ("Battery handling", "Not found; placeholder used.", []),
        ],
    },
    "flytrex_sky2": {
        "name": "Flytrex Sky2",
        "values": {
            "max_range_km": (2 * 4 * MI, ["dronexl_sky2"], "4-mile operating radius."),
        },
        "facts": [
            ("Payload", "Up to 8.8 lb.", ["flytrex_lc_pr", "dronexl_sky2"]),
            ("Configuration", "Octocopter with dual batteries.", ["dronexl_sky2"]),
            ("Speed, size, noise", "Not found; placeholders used.", []),
        ],
    },
}


def reference_names() -> dict[str, str]:
    return {key: entry["name"] for key, entry in LIBRARY.items()}


def profile_for(reference_id: str, **overrides) -> AircraftProfile:
    entry = LIBRARY[reference_id]
    values = {name: v[0] for name, v in entry["values"].items()}
    values.update(name=entry["name"], reference_id=reference_id)
    values.update(overrides)
    return AircraftProfile(**values)


def _confidence(sources: list[str]) -> str:
    if not sources:
        return "unverified"
    return "2+ sources" if len(sources) > 1 else "single source"


def provenance(reference_id: str, profile: AircraftProfile | None = None) -> list[dict]:
    """One row per aircraft field: where the value came from, or that it is a placeholder.

    If the user has edited a value away from the reference, the row says so.
    """
    entry = LIBRARY[reference_id]
    rows = []
    for f in fields(AircraftProfile):
        if f.name in ("name", "reference_id"):
            continue
        ref = entry["values"].get(f.name)
        current = getattr(profile, f.name) if profile else (ref[0] if ref else f.default)
        if ref is None:
            basis, conf, note, src = "placeholder", "placeholder", "", []
            if profile is not None and current != f.default:
                basis, conf = "user input", "user input"
        else:
            value, src, note = ref
            basis, conf = "reference", _confidence(src)
            if current != value:
                basis, conf = "user input", "user input"
                note = f"Reference value {_fmt(value)} overridden. {note}"
        rows.append({
            "field": f.name,
            "value": _fmt(current),
            "basis": basis,
            "confidence": conf,
            "note": note,
            "sources": [SOURCES[s][1] for s in src],
        })
    return rows


def facts(reference_id: str) -> list[dict]:
    return [
        {"item": label, "detail": text, "sources": [SOURCES[s][1] for s in src]}
        for label, text, src in LIBRARY[reference_id]["facts"]
    ]


def _fmt(v) -> str:
    return f"{v:.3g}" if isinstance(v, float) else str(v)
