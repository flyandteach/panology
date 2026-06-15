"""
Environmental Review Triggers Agent.
Determines which environmental review thresholds apply and what studies are required.
"""

from .base import call_llm, parse_json_response
try:
    from .. import config
except ImportError:
    import config


def _mock_environmental(inputs: dict, tier: int) -> dict:
    scale = inputs.get("operational_scale", 100)
    acreage = inputs.get("site_acreage", 0.0)
    wetland = inputs.get("wetland_nearby", False)
    floodplain = inputs.get("floodplain_nearby", False)
    residential_ft = inputs.get("residential_proximity_ft", 0)
    state = inputs.get("state", "the State")
    density = inputs.get("density", "suburban")

    triggers = []
    studies_required = []
    mitigation_measures = []

    # Noise
    if scale > config.ENV_TRIGGERS["noise_ops_per_day"]:
        triggers.append({
            "trigger": "Noise Impact Study Required",
            "threshold": f">{config.ENV_TRIGGERS['noise_ops_per_day']} operations/day",
            "actual": f"{scale} operations/day",
            "triggered": True,
            "detail": f"Facility exceeds {config.ENV_TRIGGERS['noise_ops_per_day']} ops/day. An acoustical study prepared by a qualified acoustical engineer is required, modeling cumulative DNL and CNEL at all noise-sensitive receptors within 1 mile.",
        })
        studies_required.append("Acoustical / Noise Impact Study")
        mitigation_measures.append("Operational hour restrictions if noise exceeds applicable community noise levels.")
        mitigation_measures.append("Noise barriers or berms along residential-facing property lines if modeled levels exceed thresholds.")

    # CEQA acreage
    if acreage >= config.ENV_TRIGGERS["acreage_threshold"]:
        triggers.append({
            "trigger": "Significant Ground Disturbance",
            "threshold": f">={config.ENV_TRIGGERS['acreage_threshold']} acres disturbed",
            "actual": f"{acreage} acres",
            "triggered": True,
            "detail": f"Project disturbs ≥{config.ENV_TRIGGERS['acreage_threshold']} acres. A Phase I Environmental Site Assessment is required. CEQA/NEPA documentation must address geology, soils, and hazardous materials.",
        })
        studies_required.append("Phase I Environmental Site Assessment (ESA)")
        studies_required.append("Stormwater Pollution Prevention Plan (SWPPP)")

    # Wetlands
    if wetland:
        triggers.append({
            "trigger": "Wetland Proximity",
            "threshold": f"Wetland within {config.ENV_TRIGGERS['wetland_buffer_feet']} ft",
            "actual": "Wetland confirmed nearby",
            "triggered": True,
            "detail": (
                f"Site is within {config.ENV_TRIGGERS['wetland_buffer_feet']} ft of a wetland. "
                "A wetland delineation and jurisdictional determination (Army Corps of Engineers Section 404 / "
                f"{state} state wetland permit) is required. No flight path corridor may be established over wetland areas without FAA and Army Corps approval."
            ),
        })
        studies_required.append("Wetland Delineation & Jurisdictional Determination (Army Corps / State)")
        studies_required.append("Biological Resources Assessment")
        mitigation_measures.append("Section 404 / Section 401 permits required if any fill or alteration of jurisdictional waters.")

    # Floodplain
    if floodplain:
        triggers.append({
            "trigger": "FEMA Floodplain",
            "threshold": "Site within FEMA Special Flood Hazard Area (SFHA)",
            "actual": "Floodplain confirmed",
            "triggered": True,
            "detail": "Site is within or adjacent to a FEMA-designated Special Flood Hazard Area. A FEMA Flood Zone Certification is required. All GSI must be elevated or flood-proofed to the Base Flood Elevation + 1 ft freeboard. Conditional Letter of Map Revision (CLOMR) may be required.",
        })
        studies_required.append("FEMA Flood Zone Certification / Floodplain Analysis")
        mitigation_measures.append("All GSI structures flood-proofed to BFE + 1 ft.")

    # Flight path over residential
    if residential_ft > 0 and residential_ft < config.ENV_TRIGGERS["flight_path_residential_dist"]:
        triggers.append({
            "trigger": "Residential Flight Path Proximity",
            "threshold": f"Residential within {config.ENV_TRIGGERS['flight_path_residential_dist']} ft of flight path",
            "actual": f"{residential_ft} ft",
            "triggered": True,
            "detail": (
                f"Nearest residential structure is {residential_ft} ft from the proposed flight path corridor. "
                "A Health Risk Assessment (HRA) may be required by the local air quality management district. "
                "Community benefit agreement recommended."
            ),
        })
        studies_required.append("Health Risk Assessment (HRA) — Air Quality Management District")
        mitigation_measures.append("Community outreach and benefits program for impacted residential areas.")

    # Always required at Tier 3+
    if tier >= 3:
        triggers.append({
            "trigger": "Traffic & Circulation Study",
            "threshold": "Tier 3+ facility",
            "actual": f"Tier {tier}",
            "triggered": True,
            "detail": "All Tier 3 and 4 facilities must submit a Transportation Impact Analysis (TIA) modeling ground-side vehicle trips, parking demand, and intermodal transfer queuing.",
        })
        studies_required.append("Transportation Impact Analysis (TIA)")

    # Determine CEQA document type
    if tier >= 4 or (len(triggers) >= 3) or (acreage >= 5.0):
        ceqa_document = "Environmental Impact Report (EIR)"
    elif len(triggers) >= 1:
        ceqa_document = "Initial Study / Mitigated Negative Declaration (IS/MND)"
    elif tier == 1 and not triggers:
        ceqa_document = "Categorical Exemption — Class 3 (New Construction of Small Structures)"
    else:
        ceqa_document = "Initial Study / Negative Declaration (IS/ND)"

    return {
        "triggers": triggers,
        "studies_required": studies_required,
        "mitigation_measures": mitigation_measures,
        "ceqa_document": ceqa_document,
        "trigger_count": len(triggers),
        "notes": (
            f"Environmental review analysis for Tier {tier} facility in {state} ({density} context). "
            f"Recommended CEQA/NEPA document type: {ceqa_document}. "
            "Consult with the local Lead Agency to confirm document type and scope prior to NOP/NOI filing."
        ),
    }


def _build_prompt(inputs: dict, tier: int) -> str:
    return f"""You are an environmental planner and CEQA/NEPA specialist.

Identify all environmental review triggers for a Tier {tier} drone hub or vertiport.

PROJECT PARAMETERS:
{inputs}

Return a JSON object with:
- triggers: array of objects, each with: trigger (name), threshold (string), actual (string), triggered (bool), detail (string)
- studies_required: list of required study names
- mitigation_measures: list of mitigation measures
- ceqa_document: recommended CEQA/NEPA document type
- trigger_count: integer
- notes: string

Cover: noise, ground disturbance/CEQA, wetlands (Section 404), floodplain (FEMA), flight path residential proximity, traffic (Tier 3+), biological resources.

Return only valid JSON."""


class EnvironmentalAgent:
    def generate(self, inputs: dict, tier: int = 2) -> dict:
        api_live = __import__("os").environ.get("ANTHROPIC_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
        if not api_live:
            return _mock_environmental(inputs, tier)

        prompt = _build_prompt(inputs, tier)
        response = call_llm(prompt, role="environmental_agent")
        result = parse_json_response(response)
        if result.get("mock") or result.get("parse_error"):
            return _mock_environmental(inputs, tier)
        return result
