"""
Use Definitions Agent.
Generates legally precise definitions for all terms used in the ordinance.
"""

from .base import call_llm, parse_json_response
try:
    from .. import config
except ImportError:
    import config


_BASE_DEFINITIONS = [
    ("Unmanned Aircraft System (UAS)", "Any aircraft operated without a human pilot on board, including all associated elements such as communication links and components that control the unmanned aircraft, as defined in 49 U.S.C. § 40102(a)(46)."),
    ("Electric Vertical Takeoff and Landing Aircraft (eVTOL)", "A powered-lift aircraft that uses electrical energy to achieve vertical takeoff, hover, and landing capability, and may be piloted or operated autonomously."),
    ("Drone Hub", "A Tier 1 or Tier 2 facility designed primarily for unmanned aircraft system operations, including package delivery nodes, rooftop pads, and automated ground-side infrastructure, but excluding scheduled passenger air service."),
    ("Vertiport", "A Tier 3 or Tier 4 designated landing and takeoff area for eVTOL aircraft, which may include passenger lounges, ground transport connections, and on-site maintenance facilities."),
    ("Skyport", "A Tier 4 major vertiport facility integrated with existing transit infrastructure, capable of handling high-frequency eVTOL operations at scale within an urban core."),
    ("Operational Scale", "The maximum number of discrete aircraft take-off and landing cycles (TOFL) anticipated at a facility within a 24-hour period, used to determine tier classification under this ordinance."),
    ("Flight Path Corridor", "The designated three-dimensional airspace volume through which aircraft consistently ingress and egress a drone hub or vertiport, as defined in the facility's approved operational plan."),
    ("Ground Support Infrastructure (GSI)", "Fixed or mobile equipment located on the facility premises used to charge, fuel, service, or store unmanned aircraft or eVTOL vehicles, including but not limited to charging stations, hangar structures, and battery swap systems."),
    ("Urban Air Mobility (UAM)", "A safe, efficient, and automated aviation transportation system for passengers and cargo that operates at lower altitudes within urban and suburban environments."),
    ("Noise-Sensitive Receptor", "Any land use or structure particularly sensitive to noise impacts, including residences, schools, hospitals, day care centers, houses of worship, and libraries, as classified under applicable state environmental regulations."),
    ("Conditional Use Permit (CUP)", "A discretionary approval granted by the Planning Commission or its designee authorizing a use that requires special conditions to ensure compatibility with surrounding land uses."),
    ("Ministerial Approval", "A non-discretionary permit issued by the Building Official upon demonstration that all objective standards are met, without requiring a public hearing."),
]


def _mock_definitions(inputs: dict) -> dict:
    state = inputs.get("state", "the State")
    tier = inputs.get("_tier", 2)

    defs = list(_BASE_DEFINITIONS)

    if tier >= 3:
        defs.append(("Intermodal Connection", "A physical infrastructure link between a vertiport or skyport and a surface transportation system, including but not limited to rail stations, bus terminals, and ride-hail staging areas."))

    defs.append(("Setback", f"The minimum horizontal distance required between a structure, landing pad, or flight path corridor and a specified land use or property boundary, as established in Article IV of this ordinance and applicable {state} state law."))

    return {
        "definitions": [
            {"term": term, "definition": defn}
            for term, defn in defs
        ],
        "notes": f"All definitions are consistent with FAA Advisory Circular 150/5390-2D (Heliport Design, adapted for eVTOL) and {state} state aviation statutes. Definitions may require adjustment upon adoption of final FAA UAM certification standards.",
    }


def _build_prompt(inputs: dict, tier: int) -> str:
    return f"""You are a municipal attorney drafting a drone hub and vertiport zoning ordinance for {inputs.get('state', 'a U.S. state')}.

The facility is classified as Tier {tier} under this ordinance. Generate precise legal definitions for all terms this ordinance will use.

PROJECT PARAMETERS:
State: {inputs.get('state')}
Airport Type: {inputs.get('airport_type')}
Density: {inputs.get('density')}
Operational Scale: {inputs.get('operational_scale')} ops/day
Municipality: {inputs.get('municipality', 'unspecified')}

Return a JSON object with:
- definitions: array of objects, each with "term" (string) and "definition" (string, one precise legal sentence)
- notes: string with any state-specific cross-references

Include at minimum: UAS, eVTOL, Drone Hub, Vertiport, Operational Scale, Flight Path Corridor, Ground Support Infrastructure, UAM, Noise-Sensitive Receptor, Setback, Conditional Use Permit.

Return only valid JSON."""


class DefinitionsAgent:
    def generate(self, inputs: dict, tier: int = 2) -> dict:
        api_live = __import__("os").environ.get("ANTHROPIC_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
        if not api_live:
            enriched = {**inputs, "_tier": tier}
            return _mock_definitions(enriched)

        prompt = _build_prompt(inputs, tier)
        response = call_llm(prompt, role="definitions_agent")
        result = parse_json_response(response)
        if result.get("mock") or result.get("parse_error"):
            return _mock_definitions({**inputs, "_tier": tier})
        return result
