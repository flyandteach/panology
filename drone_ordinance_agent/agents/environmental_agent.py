"""
Environmental Review Triggers Agent.
Aligned with WSDOT Drone Hub Land Use Guidance v5.3 (June 2026).

Key corrections from prior version:
- REMOVED: flight path regulation triggers (local governments cannot restrict flight paths)
- REMOVED: aircraft operating hour limits (not a local land-use authority)
- FOCUS: ground-based impacts — ground noise, acreage, wetlands, floodplain, traffic
- Added: reference to FAA Draft Programmatic Environmental Assessment (Dec 2025)
- Added: FAA Part 135/108 NEPA tiering note
"""

from .base import call_llm, parse_json_response
try:
    from .. import config
except ImportError:
    import config


def _mock_environmental(inputs: dict, tier: int) -> dict:
    daily_ops = inputs.get("operational_scale", 0)
    acreage = inputs.get("site_acreage", 0.0)
    wetland = inputs.get("wetland_nearby", False)
    floodplain = inputs.get("floodplain_nearby", False)
    state = inputs.get("state", "the State")
    density = inputs.get("density", "suburban")
    num_operators = inputs.get("num_operators", 1)

    triggers = []
    studies_required = []
    mitigation_measures = []

    # --- Ground-based noise ---
    # High-volume threshold per WSDOT: >100 flights per rolling 60-min period
    # As proxy: flag if daily ops suggest persistent high throughput
    is_high_volume = daily_ops > config.ENV_TRIGGERS["noise_flights_per_hour"]
    if is_high_volume or tier >= 3:
        triggers.append({
            "trigger": "Ground-Based Noise Assessment",
            "threshold": f"Tier {tier} facility" + (f" / {daily_ops} daily ops" if is_high_volume else ""),
            "actual": f"Tier {tier}, {daily_ops} daily ops",
            "triggered": True,
            "detail": (
                "An acoustical study is required for ground-based equipment noise (loading, unloading, maintenance, "
                "charging, generators, vehicles). Noise from these sources must comply with generally applicable local "
                "noise or nuisance standards. NOTE: This study does NOT assess aircraft source noise — that falls under "
                "FAA jurisdiction. Where the project involves Part 135 package delivery, ask the applicant whether the "
                "FAA Draft Programmatic Environmental Assessment (December 2025) or a project-specific FAA NEPA document "
                "addresses noise at the proposed site, and whether any FAA assumptions about setbacks or intensity are relevant."
            ),
        })
        studies_required.append("Ground-Based Acoustical Study (equipment and vehicle noise only; not aircraft source noise)")
        mitigation_measures.append("Ground-based equipment (charging banks, HVAC, generators) shall comply with local noise ordinance at the property line.")
        mitigation_measures.append("Screening walls or berms between operational boundary and residential uses where ambient modeling shows exceedance.")

    # --- Significant ground disturbance ---
    if acreage >= config.ENV_TRIGGERS["acreage_threshold"]:
        triggers.append({
            "trigger": "Ground Disturbance / Environmental Site Assessment",
            "threshold": f">= {config.ENV_TRIGGERS['acreage_threshold']} acres disturbed",
            "actual": f"{acreage} acres",
            "triggered": True,
            "detail": (
                f"Project disturbs {acreage} acres. A Phase I Environmental Site Assessment (ESA) is required. "
                "SEPA/CEQA/NEPA documentation must address geology, soils, stormwater, and hazardous materials. "
                "A Stormwater Pollution Prevention Plan (SWPPP) is required for land-disturbing activities."
            ),
        })
        studies_required.append("Phase I Environmental Site Assessment (ESA)")
        studies_required.append("Stormwater Pollution Prevention Plan (SWPPP)")

    # --- Wetlands ---
    if wetland:
        triggers.append({
            "trigger": "Wetland Proximity — Section 404 / State Wetland Review",
            "threshold": f"Wetland within {config.ENV_TRIGGERS['wetland_buffer_feet']} ft",
            "actual": "Wetland confirmed nearby",
            "triggered": True,
            "detail": (
                f"Site is within {config.ENV_TRIGGERS['wetland_buffer_feet']} ft of a wetland. "
                "A wetland delineation and Army Corps of Engineers Section 404 jurisdictional determination is required. "
                f"A {state} state wetland permit may also be required. "
                "No fill or alteration of jurisdictional waters may occur without Section 404 / Section 401 permits."
            ),
        })
        studies_required.append("Wetland Delineation and Army Corps Jurisdictional Determination")
        studies_required.append("Biological Resources Assessment")
        mitigation_measures.append("Section 404 / Section 401 permits required if any fill or alteration of jurisdictional waters.")
        mitigation_measures.append("Wetland buffer planting and stormwater controls as required by permit conditions.")

    # --- Floodplain ---
    if floodplain:
        triggers.append({
            "trigger": "FEMA Floodplain Compliance",
            "threshold": "Site within or adjacent to FEMA Special Flood Hazard Area (SFHA)",
            "actual": "Floodplain confirmed",
            "triggered": True,
            "detail": (
                "Site is within or adjacent to a FEMA-designated Special Flood Hazard Area. "
                "A Floodplain Development Permit is required. All structures and ground support infrastructure "
                "must be elevated or flood-proofed to the Base Flood Elevation + 1 ft freeboard. "
                "A Conditional Letter of Map Revision (CLOMR) may be required prior to construction."
            ),
        })
        studies_required.append("FEMA Floodplain Development Permit / Flood Zone Certification")
        mitigation_measures.append("All GSI structures elevated or flood-proofed to BFE + 1 ft freeboard.")

    # --- Traffic and transportation (Tier 3) ---
    if tier >= 3 or num_operators > 1:
        triggers.append({
            "trigger": "Transportation Impact Analysis (Tier 3 / Multi-Operator)",
            "threshold": "Tier 3 or multiple-operator facility",
            "actual": f"Tier {tier}, {num_operators} operator(s)",
            "triggered": True,
            "detail": (
                "A Transportation Impact Analysis (TIA) is required, modeling ground-side vehicle trips "
                "(delivery vans, maintenance vehicles, employee commutes), parking demand, loading/unloading queuing, "
                "and intermodal access. For shared multi-operator hubs, cumulative trip generation from all operators "
                "must be included. A Transportation Demand Management (TDM) Plan may be required as a condition of approval."
            ),
        })
        studies_required.append("Transportation Impact Analysis (TIA)")
        if tier >= 3:
            studies_required.append("Transportation Demand Management (TDM) Plan")

    # --- Battery and fire safety (Tier 2+) ---
    if tier >= 2:
        triggers.append({
            "trigger": "Fire Safety Review — Lithium-Ion Battery Storage",
            "threshold": "Tier 2+ / installed charging and battery storage infrastructure",
            "actual": f"Tier {tier} with installed charging/docking",
            "triggered": True,
            "detail": (
                "A fire protection plan for lithium-ion energy storage systems (ESS) is required, consistent with "
                "applicable IFC/NFPA standards and local fire code. The plan shall address battery volume, thermal "
                "runaway mitigation, suppression systems, and emergency response coordination with local fire department."
            ),
        })
        studies_required.append("Fire Protection Plan — Lithium-Ion Energy Storage Systems (IFC/NFPA compliance)")
        mitigation_measures.append("Battery storage sited and constructed per applicable IFC and NFPA 855 standards.")

    # --- FAA NEPA note (informational, not a local trigger) ---
    faa_nepa_note = (
        "Informational: In December 2025, the FAA released a Draft Programmatic Environmental Assessment (PEA) "
        "for Drone Package Delivery Operations. For facilities involving Part 135 or anticipated Part 108 package "
        "delivery operations, staff should ask the applicant to identify whether FAA NEPA review has been completed "
        "or is anticipated for the proposed operation, and whether any FAA noise or setback assumptions in that review "
        "are relevant to this site. The FAA PEA is a technical reference — it is not a local zoning standard or "
        "substitute for site-specific review."
    )

    # Determine recommended environmental document type
    if tier >= 3 or len(triggers) >= 3 or acreage >= 5.0:
        env_doc = "Environmental Impact Statement / Report (EIS/EIR) — or full SEPA/CEQA review required"
    elif len(triggers) >= 1:
        env_doc = "Initial Study / Mitigated Negative Declaration (IS/MND) or SEPA Mitigated DNS"
    elif tier == 1 and not triggers:
        env_doc = "Categorical Exemption (verify applicability with Lead Agency)"
    else:
        env_doc = "Threshold Determination / Negative Declaration (SEPA DNS or CEQA ND)"

    return {
        "triggers": triggers,
        "studies_required": studies_required,
        "mitigation_measures": mitigation_measures,
        "recommended_env_document": env_doc,
        "trigger_count": len(triggers),
        "faa_nepa_note": faa_nepa_note,
        "excluded_from_local_review": [
            "Aircraft flight paths and routes — FAA jurisdiction; local governments may not restrict",
            "Aircraft source noise — regulated by FAA, not local noise ordinance",
            "Aircraft operating hours — only ground-based activity hours may be regulated locally",
            "Airspace use and authorization — FAA exclusive jurisdiction",
        ],
        "wsdot_reference": "WSDOT Drone Hub Land Use Guidance v5.3, Sections 3–4 and Site Evaluation Checklist (June 2026)",
        "notes": (
            f"Environmental review for Tier {tier} facility in {state} ({density} context). "
            f"Recommended document type: {env_doc}. "
            "Consult with Lead Agency to confirm document scope prior to SEPA/CEQA determination. "
            "Local environmental review focuses on ground-based impacts only; aircraft operational impacts are "
            "addressed through FAA NEPA review, not local environmental review."
        ),
    }


def _build_prompt(inputs: dict, tier: int) -> str:
    return f"""You are an environmental planner applying WSDOT Drone Hub Land Use Guidance v5.3 (June 2026) and SEPA/CEQA principles.

Identify environmental review triggers for a Tier {tier} drone hub.

PROJECT PARAMETERS:
{inputs}

CRITICAL CONSTRAINTS (per WSDOT v5.3 and FAA preemption):
1. Do NOT include triggers related to flight paths, aircraft routes, or airspace — these are FAA jurisdiction.
2. Do NOT include aircraft operating hours — local governments cannot set these.
3. Do NOT include aircraft source noise — FAA jurisdiction; local review covers ground-based equipment noise only.
4. FOCUS on: ground-based noise (equipment/vehicles), site disturbance, wetlands, floodplain, traffic (Tier 3), fire safety (battery storage), FAA NEPA tiering note.
5. Include a note about the FAA Draft Programmatic Environmental Assessment (December 2025) for Part 135/108 operations.

Return a JSON object with:
- triggers: array of objects, each with: trigger (name), threshold (string), actual (string), triggered (bool), detail (string)
- studies_required: list of study names
- mitigation_measures: list of measures
- recommended_env_document: string (SEPA/CEQA document type)
- trigger_count: integer
- faa_nepa_note: string (informational note about FAA NEPA process, not a local trigger)
- excluded_from_local_review: list of strings (items that are FAA jurisdiction, not local)
- wsdot_reference: string
- notes: string

Return only valid JSON."""


class EnvironmentalAgent:
    def generate(self, inputs: dict, tier: int = 1) -> dict:
        api_live = __import__("os").environ.get("ANTHROPIC_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
        if not api_live:
            return _mock_environmental(inputs, tier)

        prompt = _build_prompt(inputs, tier)
        response = call_llm(prompt, role="environmental_agent")
        result = parse_json_response(response)
        if result.get("mock") or result.get("parse_error"):
            return _mock_environmental(inputs, tier)
        return result
