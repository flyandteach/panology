"""
Zoning Language Agent.
Draft ordinance text aligned with WSDOT Drone Hub Land Use Guidance v5.3 (June 2026).
Includes required federal preemption statement, WSDOT Table 3 compatibility matrix,
and performance standards focused on ground-based impacts only.
"""

from .base import call_llm, parse_json_response
try:
    from .. import config
except ImportError:
    import config


def _zone_compat_rows(tier: int) -> tuple[list, list, list]:
    permitted, conditional, prohibited = [], [], []
    for zone, compat in config.ZONE_COMPATIBILITY.items():
        code = compat.get(f"tier_{tier}", "X")
        if code == "P":
            permitted.append(zone)
        elif code == "C":
            conditional.append(zone)
        else:
            prohibited.append(zone)
    return permitted, conditional, prohibited


def _mock_zoning(inputs: dict, tier: int) -> dict:
    state = inputs.get("state", "the State")
    density = inputs.get("density", "suburban")
    municipality = inputs.get("municipality") or "the Municipality"
    accessory = inputs.get("accessory_use", False)
    sqft = inputs.get("hub_area_sqft", 5000)

    permitted_zones, conditional_zones, prohibited_zones = _zone_compat_rows(tier)

    if density in ("rural", "suburban"):
        setback_note = "300 feet from residential uses (advisory default; reducible to 150 feet by discretionary approval for Tier 1 and Tier 2)"
        noise_std = "generally applicable local noise or nuisance code standards"
    else:
        setback_note = "150 feet from residential uses (advisory default; may be reduced below 150 feet by discretionary approval where ambient noise and density support closer operations)"
        noise_std = "generally applicable local noise or nuisance code standards"

    text = f"""SECTION 1. PURPOSE AND INTENT

The {municipality} City Council finds that drone hubs are emerging infrastructure that support package delivery,
medical supply transport, infrastructure inspection, and emergency response. This Article establishes
land-use standards to permit drone hubs in appropriate locations, at a scale commensurate with their
operational intensity, while protecting public health, safety, and neighborhood character consistent with
applicable {state} law and Federal Aviation Administration regulations.

SECTION 2. FEDERAL PREEMPTION

Nothing in this Article is intended to regulate aircraft operations, flight paths, altitude, aircraft noise
at the source, airspace, or FAA authorization of aircraft operations. The provisions of this Article apply
only to the location, design, and ground-based land-use characteristics of drone hubs and to their
compatibility with surrounding land uses. Local standards adopted under this Article shall not attempt to
restrict where drones can fly or prohibit lawfully authorized aircraft operations.

SECTION 3. APPLICABILITY AND SCOPE

(a) This Article applies to all Drone Hubs, as defined in Article II, including new construction, expansion
    of an existing drone hub's operational boundary by more than 10%, and any change in operational
    characteristics that would trigger reclassification to a higher tier.

(b) A Drone Access Point, as defined in Article II, shall not be reviewed under this Article. Drone access
    points shall be reviewed under existing rules for accessory structures, delivery lockers, ADA access,
    fire lanes, parking, and site design.

(c) An Accessory Drone Hub may be permitted as an accessory use to an existing primary commercial or
    industrial use — including, but not limited to, retail establishments, restaurants, medical facilities,
    self-storage, shopping centers, and warehousing or distribution facilities — provided that all standards
    of this Article are met. Accessory status does not by itself reduce the applicable tier classification.

SECTION 4. USE TABLE

Drone hubs shall be treated as a distinct use category. The following table establishes permitted (P),
conditional (C), and prohibited (X) status by tier and zoning district.

    ZONE DISTRICT                          TIER 1    TIER 2    TIER 3
    -----------------------------------------------------------------------
    Residential (all)                         X         X         X
    Neighborhood Commercial / Mixed Use       C         C         C
    Regional Commercial / Retail              P         P         C
    Industrial / Logistics                    P         P         C
    Airport-Related / Aviation Overlay *      P         P         C
    Institutional                             C         C         C

    * When a drone hub is proposed near an airport, consultation with WSDOT Aviation Division
      and the airport manager is recommended prior to application.

    P = Permitted (administrative, non-discretionary site plan review when standards are met)
    C = Conditional / Special Use Permit (discretionary review with public hearing)
    X = Prohibited

SECTION 5. SEPARATION AND SETBACKS

(a) Measurement. Setback distances under this Article shall be measured from the outer edge of the
    Operational Boundary (including launch and landing pads, staging areas, charging areas, and maintenance
    zones) to the nearest point of the sensitive receptor, unless the reviewing authority adopts a different
    measurement method by local rule.

(b) Residential separation. The following advisory default review thresholds apply:
    — Urban context:   150 feet (may be reduced below 150 feet by discretionary approval where
                       ambient noise and density support closer operations with conditions)
    — Suburban context: 300 feet (reducible to 150 feet by discretionary approval when the
                        applicant demonstrates that performance standards will adequately address impacts)
    — Rural context:   300 feet

(c) Schools and hospitals. A 300-foot review threshold applies to the distance between the operational
    boundary and the nearest property line of any school, hospital, childcare center, or licensed
    healthcare facility. For Tier 3 hubs, the reviewing authority shall make specific findings regarding
    compatibility with such uses within 300 feet.

(d) Adjustment. The reviewing authority may, through discretionary approval, reduce or increase a
    separation distance where the applicant demonstrates through site design, operational restrictions,
    screening, and noise mitigation that impacts on sensitive receptors will be adequately addressed.

SECTION 6. PERFORMANCE STANDARDS

All drone hubs shall comply with the following performance standards:

(a) Ground-based noise. Noise from outdoor loading, unloading, maintenance, charging equipment,
    generators, vehicles, and other ground support activity shall comply with {noise_std}.
    This section does not regulate aircraft noise at the source.

(b) Ground-based site activity. Generally applicable standards for outdoor loading, maintenance, lighting,
    parking, employee activity, generator use, and other ground-based site activity may apply, provided
    that the same standards apply to comparable commercial or industrial uses. This section does not
    establish aircraft-specific hours of operation.

(c) Screening. Fencing, walls, or substantial landscaping shall screen outdoor staging areas, landing pads,
    and operational boundary areas from adjacent public rights-of-way and sensitive receptors.

(d) Lighting. All lighting shall be downward-shielded and shall not produce glare or light trespass onto
    adjacent properties or into the flight path environment. Lighting shall comply with applicable FAA
    Advisory Circulars regarding aviation lighting to the extent applicable to the site.

(e) Battery and energy storage. Battery storage and charging shall comply with applicable fire code
    provisions for lithium-ion energy storage systems. An applicant proposing battery storage exceeding
    the fire code's threshold for automatic review shall submit a fire protection plan.

(f) Access and security. The perimeter of the operational boundary shall include controlled access points.
    Operator contact information and emergency procedures shall be posted at each access point.

SECTION 7. TIER 3 SUPPLEMENTAL REQUIREMENTS

In addition to the standards in Section 6, Tier 3 drone hubs shall:

(a) Submit an operational plan describing estimated flight counts, ground-based activity hours,
    emergency response coordination, off-site recovery procedures, and complaint-handling processes.

(b) Provide written evidence of pre-application community engagement, including a description of issues
    raised and changes made in response to community input.

(c) Maintain sortie count records, ground-activity logs, and complaint documentation available to the
    reviewing authority upon request.

(d) Coordinate with local fire and police departments regarding emergency access and response procedures
    prior to issuance of any certificate of occupancy.

(e) Execute a performance review agreement requiring an operational review within 18–24 months of
    commencement of operations to confirm that actual impacts align with projections.

SECTION 8. NONCONFORMING DRONE HUBS

Any drone hub lawfully established prior to the effective date of this Article may continue operations as
a nonconforming use. Any expansion of the operational boundary by more than 10%, or any change in
operational characteristics that would trigger a higher tier classification, shall require full compliance
with this Article for the expanded or changed portion of the facility."""

    return {
        "text": text,
        "permitted_zones": permitted_zones,
        "conditional_zones": conditional_zones,
        "prohibited_zones": prohibited_zones,
        "federal_preemption_included": True,
        "setback_basis": "operational boundary (pads, staging, charging, maintenance zones)",
        "residential_setback_default_ft": 300 if density in ("suburban", "rural") else 150,
        "residential_setback_minimum_ft": 150,
        "school_hospital_review_threshold_ft": 300,
        "noise_standard": "generally applicable local noise or nuisance code; no aircraft source noise regulation",
        "notes": (
            f"Zoning language adapted from WSDOT Drone Hub Land Use Guidance v5.3 model code for Tier {tier} "
            f"in {density} context, {state}. Federal preemption statement included per WSDOT guidance. "
            "Operating hour limits on aircraft are excluded; only ground-based site activity may be regulated. "
            "Adopt in consultation with local counsel and verify against applicable state preemption provisions."
        ),
    }


def _build_prompt(inputs: dict, tier: int) -> str:
    permitted, conditional, prohibited = _zone_compat_rows(tier)
    density = inputs.get("density", "suburban")
    setback = 300 if density in ("suburban", "rural") else 150

    return f"""You are a municipal attorney drafting a drone hub zoning ordinance for {inputs.get('municipality', inputs.get('state', 'a municipality'))}.

Apply WSDOT Drone Hub Land Use Guidance v5.3 (June 2026). The facility is Tier {tier}.

PROJECT PARAMETERS:
{inputs}

Use compatibility for Tier {tier}:
- Permitted by right: {', '.join(permitted)}
- Conditional/CUP required: {', '.join(conditional)}
- Prohibited: {', '.join(prohibited)}
Advisory residential setback: {setback} ft from operational boundary (not parcel line).

Draft ordinance sections covering:
1. Purpose and intent
2. Federal preemption statement (MUST include: "Nothing in this section regulates aircraft operations, flight paths, altitude, aircraft noise at the source, airspace, or FAA authorization")
3. Applicability and scope (including drone access point carve-out and accessory use provision)
4. Use table (P/C/X by tier using WSDOT Table 3)
5. Separation and setbacks (measured from operational boundary; context-sensitive)
6. Performance standards (ground-based noise only; no aircraft operating hours; screening; lighting; battery storage)
7. Tier 3 supplemental requirements (if applicable)
8. Nonconforming drone hubs

Return a JSON object with:
- text: complete multi-section ordinance draft (string)
- permitted_zones: list
- conditional_zones: list
- prohibited_zones: list
- federal_preemption_included: boolean (must be true)
- setback_basis: string
- residential_setback_default_ft: number
- residential_setback_minimum_ft: number
- school_hospital_review_threshold_ft: number
- noise_standard: string
- notes: string

Return only valid JSON."""


class ZoningAgent:
    def generate(self, inputs: dict, tier: int = 1) -> dict:
        api_live = __import__("os").environ.get("ANTHROPIC_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
        if not api_live:
            return _mock_zoning(inputs, tier)

        prompt = _build_prompt(inputs, tier)
        response = call_llm(prompt, role="zoning_agent", max_tokens=4096)
        result = parse_json_response(response)
        if result.get("mock") or result.get("parse_error"):
            return _mock_zoning(inputs, tier)
        return result
