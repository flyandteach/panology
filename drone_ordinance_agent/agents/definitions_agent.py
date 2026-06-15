"""
Use Definitions Agent.
Definitions aligned with WSDOT Drone Hub Land Use Guidance v5.3 (June 2026)
and the model code language in Section 5 of that document.
"""

from .base import call_llm, parse_json_response
try:
    from .. import config
except ImportError:
    import config


# Core definitions drawn directly from WSDOT v5.3 language
_BASE_DEFINITIONS = [
    (
        "Drone Hub (UAS Logistics Facility)",
        "A fixed-location facility used for repeated launch, landing, charging, staging, storage, maintenance, dispatch, or logistical support of commercial, governmental, or institutional unmanned aircraft operations. This definition applies to both primary drone hubs and accessory drone hubs.",
    ),
    (
        "Drone Access Point",
        "A structure, locker, equipment cabinet, or similar location used for package pickup, drop-off, or temporary storage that does not support unmanned aircraft takeoff, landing, charging, docking, staging, aircraft storage, or maintenance. A drone access point shall be reviewed under existing rules for accessory structures, delivery lockers, ADA access, fire lanes, parking, and site design — not under this section.",
    ),
    (
        "Accessory Drone Hub",
        "A drone hub that is incidental and subordinate to an existing primary commercial, institutional, or industrial use (for example, a restaurant, retail store, medical facility, self-storage facility, shopping center, warehouse, or public facility) and does not become the principal use of the site. Accessory status is based on the relationship to the primary use, not solely on size.",
    ),
    (
        "Primary Drone Hub",
        "A drone hub that constitutes the principal use of a site, rather than an accessory use appurtenant to a separate primary use. A primary drone hub may qualify as Tier 1, Tier 2, or Tier 3 based on its operational characteristics. Status as a primary use shall not, by itself, place a hub in a higher tier or require a more burdensome approval pathway.",
    ),
    (
        "Operational Boundary",
        "The outer edge of the area where drone hub activity occurs, including launch and landing pads, docks, staging areas, charging areas, loading areas, aircraft storage areas, and other dedicated ground-support areas used for recurring drone operations. For purposes of measuring separation distances or setback requirements under this section, the operational boundary shall be used as the reference point rather than the parcel line, unless the reviewing authority adopts a different measurement method through local rule.",
    ),
    (
        "High-Volume Operations",
        "A drone hub that conducts more than 100 flights in any rolling 60-minute period. Jurisdictions may also require applicants to disclose expected daily, monthly, or annual activity where that better reflects actual operating patterns.",
    ),
    (
        "Unmanned Aircraft System (UAS)",
        "Any aircraft operated without the possibility of direct human intervention from within or on the aircraft, including the associated elements such as communication links and components that control the unmanned aircraft, as defined in 14 C.F.R. Part 107 and 49 U.S.C. § 40102(a)(46).",
    ),
    (
        "Ground Support Infrastructure (GSI)",
        "Fixed or mobile equipment located on the facility premises used to charge, fuel, service, or store unmanned aircraft or eVTOL vehicles, including but not limited to charging stations, battery swap systems, aircraft storage structures, maintenance equipment, and dispatch or communications systems.",
    ),
    (
        "Sensitive Receptor",
        "A land use where drone noise or visual exposure may warrant added protection, including residences, schools, childcare centers, hospitals, day care facilities, houses of worship, and libraries, as identified by local code or consistent with applicable state environmental regulations.",
    ),
    (
        "Conditional or Special Use Review",
        "A discretionary local approval process, including a public hearing, that allows the reviewing authority to impose case-specific conditions addressing site design, operations, compatibility, and mitigation as a condition of approval.",
    ),
    (
        "Ministerial / Administrative Approval",
        "A non-discretionary permit issued by the designated reviewing authority upon demonstration that all applicable objective standards are met, without the requirement for a public hearing. Also referred to in this section as the 'lighter review track.'",
    ),
    (
        "Related or Supporting Uses",
        "Uses physically or operationally integrated with a drone hub, including battery storage, battery charging, aircraft maintenance, warehousing, retail sales, fleet management, data processing, or logistics dispatch. Where supporting activities materially change the scale or impact of the proposal, they shall be considered in tier classification and site review.",
    ),
    (
        "Federal Preemption",
        "The Federal Aviation Administration regulates airspace, pilot certification, airworthiness, operational rules, Remote ID, and beyond visual line of sight (BVLOS) authorizations. Nothing in this section is intended to regulate aircraft operations, flight paths, altitude, aircraft noise at the source, airspace, or FAA authorization of aircraft operations. This section applies only to the location, design, and ground-based land-use characteristics of drone hubs and to their compatibility with surrounding land uses.",
    ),
]


def _mock_definitions(inputs: dict, tier: int) -> dict:
    state = inputs.get("state", "the State")
    defs = list(_BASE_DEFINITIONS)

    # State-specific cross-reference
    if state == "Washington":
        state_note = (
            "Definitions are consistent with WSDOT Drone Hub Land Use Guidance v5.3 (June 2026) and Washington State Growth Management Act designations. "
            "The term 'drone hub' is used consistently throughout; local jurisdictions may substitute 'UAS logistics facility' or equivalent to match local code conventions."
        )
    else:
        state_note = (
            f"Definitions are adapted from WSDOT Drone Hub Land Use Guidance v5.3 (June 2026) for use in {state}. "
            "Verify consistency with applicable state aviation statutes, preemption provisions, and local code conventions before adoption. "
            "Definitions may require adjustment upon adoption of FAA final rules under proposed 14 C.F.R. Part 108 (BVLOS normalizing framework)."
        )

    return {
        "definitions": [{"term": term, "definition": defn} for term, defn in defs],
        "notes": state_note,
    }


def _build_prompt(inputs: dict, tier: int) -> str:
    return f"""You are a municipal attorney drafting a drone hub zoning ordinance for {inputs.get('municipality', inputs.get('state', 'a municipality'))}.

Apply the WSDOT Drone Hub Land Use Guidance v5.3 (June 2026) model code language. The facility is Tier {tier}.

PROJECT PARAMETERS:
{inputs}

Generate legally precise definitions for all terms this ordinance will use. Must include:
- Drone Hub (UAS Logistics Facility) — use WSDOT definition: fixed-location facility for repeated launch/landing/charging/staging/storage/maintenance/dispatch of commercial UAS operations
- Drone Access Point — distinct from a drone hub; package pickup/drop-off only, no takeoff/landing/charging
- Accessory Drone Hub — incidental and subordinate to existing primary use
- Primary Drone Hub — principal use of a site
- Operational Boundary — outer edge of pads, staging, charging, storage areas; used for setback measurement
- High-Volume Operations — more than 100 flights in any rolling 60-minute period
- UAS (Unmanned Aircraft System)
- Ground Support Infrastructure (GSI)
- Sensitive Receptor
- Conditional or Special Use Review
- Ministerial / Administrative Approval
- Federal Preemption statement (nothing in this section regulates flight paths, altitude, airspace, or aircraft noise at source)

Return a JSON object with:
- definitions: array of objects with "term" (string) and "definition" (string)
- notes: string with state-specific cross-references

Return only valid JSON."""


class DefinitionsAgent:
    def generate(self, inputs: dict, tier: int = 1) -> dict:
        api_live = __import__("os").environ.get("ANTHROPIC_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
        if not api_live:
            return _mock_definitions(inputs, tier)

        prompt = _build_prompt(inputs, tier)
        response = call_llm(prompt, role="definitions_agent")
        result = parse_json_response(response)
        if result.get("mock") or result.get("parse_error"):
            return _mock_definitions(inputs, tier)
        return result
