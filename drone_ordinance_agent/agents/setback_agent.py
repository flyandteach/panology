"""
Setback Recommendations Agent.
Advisory default review thresholds per WSDOT Drone Hub Land Use Guidance v5.3, Table 2.

Key corrections from prior versions:
- Distances are 150–300 ft (not 500–750 ft)
- Measured from the OPERATIONAL BOUNDARY (not the parcel line)
- These are advisory defaults; local calibration is expected
- Jurisdictions may reduce distances through discretionary approval
- Source: WSDOT v5.3, Table 2 and Section 3 (Separation)
"""

from .base import call_llm, parse_json_response
try:
    from .. import config
except ImportError:
    import config


def _get_setbacks(density: str, tier: int) -> dict:
    ctx = config.ADVISORY_SETBACKS.get(density, config.ADVISORY_SETBACKS["suburban"])
    default_ft = ctx["residential_default_ft"]
    minimum_ft = ctx["residential_minimum_ft"]
    school_ft = ctx["school_hospital_ft"]

    # Tier 3 adds a 300-ft sensitive-receptor review threshold regardless of density
    if tier == 3:
        school_ft = max(school_ft, config.TIER_3_REVIEW_THRESHOLD_FT)

    return {
        "residential_default_ft": default_ft,
        "residential_minimum_ft": minimum_ft,
        "school_hospital_ft": school_ft,
    }


def _mock_setbacks(inputs: dict, tier: int) -> dict:
    density = inputs.get("density", "suburban")
    airport_type = inputs.get("airport_type", "class_g")
    state = inputs.get("state", "the State")

    sb = _get_setbacks(density, tier)
    residential_default = sb["residential_default_ft"]
    residential_min = sb["residential_minimum_ft"]
    school_ft = sb["school_hospital_ft"]

    airport_miles = config.AIRPORT_PROXIMITY_MILES.get(airport_type, 3)
    faa_coord = airport_type in ("class_b", "class_c", "class_d")

    # Context note for density
    density_planning_note = {
        "urban": (
            f"Urban context: {residential_default}-ft default. Higher ambient noise and denser development "
            "generally allow closer operations if noise and frequency controls are in place. "
            "May be reduced below 150 ft by discretionary approval."
        ),
        "dense_urban": (
            f"Dense urban context: {residential_default}-ft default. Same rules as urban apply. "
            "Screening and noise mitigation conditions are typically required."
        ),
        "suburban": (
            f"Suburban context: {residential_default}-ft default; reducible to {residential_min} ft "
            "by discretionary approval when the applicant demonstrates adequate performance standards. "
            "Suburban residents express stronger preferences for quiet."
        ),
        "rural": (
            f"Rural context: {residential_default}-ft default; not typically reducible given land availability. "
            "Larger buffers are feasible and reflect community expectations in rural settings."
        ),
    }.get(density, f"{residential_default}-ft default for {density} context.")

    items = [
        {
            "label": "Residential Uses",
            "measurement_from": "Operational boundary (pads, staging, charging, maintenance zones)",
            "default_ft": residential_default,
            "minimum_ft": residential_min,
            "reducible": residential_min < residential_default,
            "reduction_path": "Discretionary approval; applicant must demonstrate performance standards (noise, screening, lighting) adequately address impacts.",
            "detail": (
                f"Advisory default: {residential_default} ft. "
                f"{'Reducible to ' + str(residential_min) + ' ft by discretionary approval when performance standards are demonstrated.' if residential_min < residential_default else 'Not typically reducible given context.'} "
                "Measured from operational boundary to nearest residential structure or residential zone boundary, whichever is closer."
            ),
            "source": "WSDOT Drone Hub Land Use Guidance v5.3, Table 2",
        },
        {
            "label": "Schools, Hospitals, and Sensitive Receptors",
            "measurement_from": "Operational boundary",
            "default_ft": school_ft,
            "minimum_ft": school_ft,
            "reducible": False,
            "reduction_path": "Reviewing authority makes specific findings at Tier 3. No automatic reduction.",
            "detail": (
                f"{school_ft}-ft review threshold. "
                "For Tier 3 hubs, the reviewing authority must make specific findings regarding compatibility with schools, hospitals, childcare centers, and similar uses within this distance. "
                "The reviewing authority may impose conditions including operational restrictions, enhanced screening, and monitoring."
            ),
            "source": "WSDOT Drone Hub Land Use Guidance v5.3, Section 3",
        },
        {
            "label": "Parks and Public Open Space",
            "measurement_from": "Operational boundary",
            "default_ft": residential_default,
            "minimum_ft": residential_min,
            "reducible": residential_min < residential_default,
            "reduction_path": "Discretionary approval with conditions.",
            "detail": (
                f"Same advisory default as residential ({residential_default} ft) given public access and amenity value. "
                "Jurisdictions should evaluate visual and noise impacts on park users as part of any conditional review."
            ),
            "source": "WSDOT Drone Hub Land Use Guidance v5.3, general compatibility guidance",
        },
        {
            "label": "Commercial / Mixed-Use Properties",
            "measurement_from": "Operational boundary or parcel line (jurisdiction's choice)",
            "default_ft": 0,
            "minimum_ft": 0,
            "reducible": True,
            "reduction_path": "N/A — no advisory setback from commercial uses; site design and screening standards apply.",
            "detail": (
                "WSDOT v5.3 does not establish an advisory setback from commercial uses. "
                "Performance standards (screening, lighting, access control) and applicable building and fire codes govern. "
                "Local jurisdictions may establish commercial setbacks based on local site-design standards."
            ),
            "source": "WSDOT Drone Hub Land Use Guidance v5.3, Section 6 (Performance Standards)",
        },
        {
            "label": "Industrial / Logistics Properties",
            "measurement_from": "N/A",
            "default_ft": 0,
            "minimum_ft": 0,
            "reducible": True,
            "reduction_path": "No setback required; performance standards apply.",
            "detail": (
                "No advisory setback from industrial or logistics uses. "
                "Drone hubs are generally permitted by right in industrial/logistics zones (Tier 1 and 2). "
                "Site design, screening, and fire safety standards of this ordinance apply."
            ),
            "source": "WSDOT Drone Hub Land Use Guidance v5.3, Table 3",
        },
    ]

    airport_note = ""
    if faa_coord:
        airport_note = (
            f"Site is near a {airport_type.upper().replace('_', ' ')} airspace facility (~{airport_miles} miles). "
            "Consultation with WSDOT Aviation Division and the airport manager is recommended prior to application. "
            "FAA airspace authorization does not grant land-use approval, and land-use approval does not authorize airspace use. "
            "Submit FAA Form 7460-1 (Notice of Proposed Construction) for any structures that may affect navigable airspace."
        )
    elif airport_type != "none":
        airport_note = (
            f"Nearest airport/airspace class: {airport_type.upper().replace('_', ' ')} (~{airport_miles} miles). "
            "No mandatory local setback from airport, but applicant should verify FAA Remote ID compliance "
            "and any applicable Part 107/135/108 operational requirements for the proposed flight area."
        )

    return {
        "items": items,
        "density": density,
        "density_planning_note": density_planning_note,
        "residential_default_ft": residential_default,
        "residential_minimum_ft": residential_min,
        "school_hospital_review_threshold_ft": school_ft,
        "measurement_basis": "Operational boundary (pads, staging, charging, maintenance zones) — not the parcel line",
        "airport_type": airport_type,
        "airport_proximity_miles": airport_miles,
        "airport_note": airport_note,
        "wsdot_reference": "WSDOT Drone Hub Land Use Guidance v5.3, Table 2 (June 2026)",
        "notes": (
            f"Advisory default review thresholds for Tier {tier} in {density} context, {state}. "
            "These are starting points for local deliberation, not universal technical safety distances. "
            "The 150-ft and 300-ft figures are land-use and noise-compatibility reference points drawn from "
            "adopted Texas ordinances (Plano: 150 ft; Princeton: 300 ft, reducible to 150 ft) and WSDOT public-preference research. "
            "Local jurisdictions should calibrate to local zoning patterns, topography, ambient sound, and site-specific mitigation. "
            "Applicants may propose alternative distances through a Site-Specific Compatibility Analysis accepted by the Planning Director."
        ),
    }


def _build_prompt(inputs: dict, tier: int) -> str:
    density = inputs.get("density", "suburban")
    sb = _get_setbacks(density, tier)
    return f"""You are a licensed airport land-use planner and zoning attorney applying WSDOT Drone Hub Land Use Guidance v5.3 (June 2026).

Generate setback recommendations for a Tier {tier} drone hub.

PROJECT PARAMETERS:
{inputs}

IMPORTANT WSDOT GUIDANCE PRINCIPLES:
1. Setbacks are measured from the OPERATIONAL BOUNDARY (pads, staging, charging, maintenance zones) — NOT the parcel line.
2. Advisory default thresholds from WSDOT Table 2:
   - Urban: 150 ft residential default (may be reduced below 150 ft by discretionary approval)
   - Suburban: 300 ft default (reducible to 150 ft by discretionary approval)
   - Rural: 300 ft (not typically reducible)
   These are advisory, NOT universal mandatory safety distances.
3. Schools/hospitals: 300-ft review threshold for Tier 3 (no specific WSDOT mandatory setback for T1/T2).
4. No setback from commercial or industrial uses — performance standards apply instead.
5. These figures come from Texas ordinances (Plano: ~150 ft, Princeton: 300 ft reducible to 150) and WSDOT public-preference research.

For density "{density}":
- Residential default: {sb['residential_default_ft']} ft
- Residential minimum: {sb['residential_minimum_ft']} ft
- School/hospital review threshold: {sb['school_hospital_ft']} ft

Return a JSON object with:
- items: array of objects, each with: label, measurement_from, default_ft, minimum_ft, reducible (bool), reduction_path, detail, source
  Cover: residential, schools/hospitals, parks/open space, commercial (no setback note), industrial (no setback note)
- density: string
- density_planning_note: string
- residential_default_ft: number
- residential_minimum_ft: number
- school_hospital_review_threshold_ft: number
- measurement_basis: string (must reference operational boundary, not parcel line)
- airport_type: string
- airport_proximity_miles: number
- airport_note: string
- wsdot_reference: string
- notes: string

Return only valid JSON."""


class SetbackAgent:
    def generate(self, inputs: dict, tier: int = 1) -> dict:
        api_live = __import__("os").environ.get("ANTHROPIC_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
        if not api_live:
            return _mock_setbacks(inputs, tier)

        prompt = _build_prompt(inputs, tier)
        response = call_llm(prompt, role="setback_agent")
        result = parse_json_response(response)
        if result.get("mock") or result.get("parse_error"):
            return _mock_setbacks(inputs, tier)
        return result
