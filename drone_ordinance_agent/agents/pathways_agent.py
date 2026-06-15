"""
Approval Pathways Agent.
Entitlement process aligned with WSDOT Drone Hub Land Use Guidance v5.3 (June 2026).

Key changes from prior version:
- Tier 1/2 "Permitted" zones: administrative/ministerial review, no hearing ("lighter review track")
- Tier 1/2 "Conditional" zones: 300-ft notice radius + public hearing
- Tier 3: 500-ft notice radius + public hearing; development agreement for major hubs
- Cannot set aircraft operating hour limits (only ground-based activity)
- Source: WSDOT v5.3, Section 5 and Table 3
"""

from .base import call_llm, parse_json_response
try:
    from .. import config
except ImportError:
    import config


def _mock_pathways(inputs: dict, tier: int) -> dict:
    state = inputs.get("state", "the State")
    density = inputs.get("density", "suburban")
    municipality = inputs.get("municipality") or "the Municipality"
    airport_type = inputs.get("airport_type", "class_g")
    faa_coord = airport_type in ("class_b", "class_c", "class_d")

    # Determine primary entitlement based on tier and WSDOT guidance
    if tier == 1:
        primary_path = "Administrative Site Plan Review (Lighter Review Track) — no public hearing"
        hearing_required = False
        notice_radius_ft = 0
        sepa_track = "Categorical Exemption (WAC 197-11-800, if Washington) or state equivalent; verify with Lead Agency"
        timeline_weeks = "4–8"
        fee_range = "$500–$3,000"
        dev_agreement = False
    elif tier == 2:
        primary_path = "Administrative Site Plan Review (Lighter Review Track) — no public hearing when in Permitted zones; Conditional Use Permit when in Conditional zones"
        hearing_required = False  # only if in conditional zone
        notice_radius_ft = config.NOTICE_RADIUS_TIER_1_2_FT
        sepa_track = "SEPA/CEQA Threshold Determination (Mitigated Determination of Non-Significance likely) or state equivalent"
        timeline_weeks = "6–14"
        fee_range = "$2,000–$10,000"
        dev_agreement = False
    else:  # tier 3
        primary_path = "Conditional Use Permit (CUP) or Special Use Permit — Planning Commission or equivalent body"
        hearing_required = True
        notice_radius_ft = config.NOTICE_RADIUS_TIER_3_FT
        sepa_track = "SEPA/CEQA Environmental Review required; EIS/EIR if significant unmitigated impacts identified"
        timeline_weeks = "16–32"
        fee_range = "$15,000–$75,000+"
        dev_agreement = True

    pathways = [
        {
            "label": "Step 1 — Pre-Application Conference",
            "detail": (
                f"Applicant meets with {municipality} Planning Department staff to identify applicable standards, "
                "fee schedule, and any potential site or operational issues before formal submission. "
                "Coordination with WSDOT Aviation Division and any affected airport sponsor is recommended for "
                "Tier 3 hubs or sites near airports."
            ),
            "required": True,
            "agency": f"{municipality} Planning Department",
        },
        {
            "label": "Step 2 — Drone Hub Tier Determination",
            "detail": (
                "Applicant submits tier determination worksheet identifying dedicated hub area (sq ft), "
                "number of operators, estimated daily operations, and installed infrastructure (charging, docking, maintenance). "
                "Planning Director issues written tier determination. Any party may appeal the determination within 10 days."
            ),
            "required": True,
            "agency": f"{municipality} Planning Director",
        },
        {
            "label": f"Step 3 — {primary_path}",
            "detail": (
                f"Primary land use entitlement for a Tier {tier} facility. "
                + (
                    f"Requires a noticed public hearing. Written notice to property owners within {notice_radius_ft} ft of the proposed operational boundary."
                    if hearing_required else
                    "Administrative review; no public hearing required. "
                    + (f"Written notice to property owners within {notice_radius_ft} ft if located in a Conditional zone." if notice_radius_ft else "")
                )
                + f" Estimated processing time: {timeline_weeks} weeks from complete application. Estimated fees: {fee_range}."
            ),
            "required": True,
            "agency": f"{municipality} Planning Commission" if hearing_required else f"{municipality} Planning Director",
            "notice_radius_ft": notice_radius_ft,
            "timeline": f"~{timeline_weeks} weeks",
            "estimated_fees": fee_range,
        },
        {
            "label": "Step 4 — Environmental Review (SEPA/CEQA/NEPA)",
            "detail": (
                f"{sepa_track}. Applicant is responsible for preparation of required environmental documents. "
                "Note: Where the proposed hub involves Part 135 or Part 108 package delivery operations, "
                "applicant should identify whether the FAA has completed or is preparing NEPA review for the proposed operation, "
                "and whether any FAA noise analysis identifies setback, intensity, or mitigation assumptions relevant to the site."
            ),
            "required": True,
            "agency": f"{municipality} / Lead Agency",
        },
        {
            "label": "Step 5 — Community Engagement",
            "detail": (
                f"Pre-application neighborhood engagement required before any {'CUP hearing' if hearing_required else 'administrative decision on a Conditional zone application'}. "
                "Applicant must document: issues raised, design or operational changes made in response, "
                "and proposed ongoing community liaison and complaint-response process. "
                "For Tier 3 hubs, engagement must occur with property owners within 500 ft of the operational boundary."
            ),
            "required": tier >= 2,
            "agency": "Applicant / Community",
        },
        {
            "label": "Step 6 — FAA Coordination",
            "detail": (
                "Submit FAA Form 7460-1 (Notice of Proposed Construction or Alteration) for structures that may affect navigable airspace. "
                + (
                    f"This site is near a {airport_type.upper().replace('_', ' ')} facility. "
                    "Consult with WSDOT Aviation Division and the airport manager. "
                    "Note: FAA airspace authorization does not grant land-use approval. "
                    if faa_coord else
                    "Confirm applicant's Remote ID compliance and current operational authorization (Part 107, 135, or anticipated Part 108). "
                    "FAA airspace authorization is separate from local land-use approval."
                )
            ),
            "required": True,
            "agency": "Federal Aviation Administration / WSDOT Aviation Division",
        },
        {
            "label": "Step 7 — Building Permits and Inspections",
            "detail": (
                "All structures, electrical systems (charging infrastructure), mechanical equipment, and battery storage facilities "
                "require standard building permits and inspection. Fire code compliance review required for lithium-ion battery storage. "
                "Structural engineering required for rooftop or elevated pad installations."
            ),
            "required": True,
            "agency": f"{municipality} Building & Safety Division",
        },
    ]

    if dev_agreement:
        pathways.append({
            "label": "Step 8 — Development Agreement (Tier 3)",
            "detail": (
                "For Tier 3 hubs, the reviewing authority may require a Development Agreement capturing: "
                "operational commitments (sortie counts, ground-activity hours, complaint response), "
                "monitoring obligations, community benefit provisions, review triggers, and a performance review "
                "at 18–24 months after commencement of operations. "
                f"Authorized under applicable {state} state law."
            ),
            "required": False,
            "agency": f"{municipality} City Council",
        })

    if tier >= 3:
        pathways.append({
            "label": "Step 9 — Periodic Code Review",
            "detail": (
                "Given the pace of FAA rulemaking (including proposed Part 108 for BVLOS normalization) and "
                "evolving industry practices, conditions of approval should include a mechanism for review every "
                "2–3 years so that local standards can be updated as federal rules and operational patterns evolve."
            ),
            "required": False,
            "agency": f"{municipality} Planning Department",
        })

    appeal_path = (
        f"Appeal of {primary_path} to Planning Commission within 14 days of written decision."
        if not hearing_required else
        f"Appeal of Planning Commission decision to City Council within 14 days of written decision."
    )

    return {
        "pathways": pathways,
        "primary_entitlement": primary_path,
        "public_hearing_required": hearing_required,
        "notice_radius_ft": notice_radius_ft,
        "environmental_track": sepa_track,
        "estimated_timeline_weeks": timeline_weeks,
        "estimated_fees": fee_range,
        "development_agreement_recommended": dev_agreement,
        "faa_coordination_required": faa_coord,
        "aircraft_hour_limits": (
            "NOT APPLICABLE — This ordinance does not regulate aircraft operating hours. "
            "Only ground-based site activity (loading, maintenance, lighting, employee activity) "
            "may be regulated, and only if comparable standards apply to similar commercial or industrial uses. "
            "Drone-specific aircraft operating-hour limits should be avoided unless reviewed by counsel."
        ),
        "appeal_path": appeal_path,
        "wsdot_reference": "WSDOT Drone Hub Land Use Guidance v5.3, Section 5 and Table 3 (June 2026)",
        "notes": (
            f"Approval pathway for Tier {tier} in {density} context, {state}. "
            "Timeline and fee estimates are indicative. "
            "'Lighter review track' means administrative/non-discretionary site plan review without a public hearing (WSDOT v5.3 terminology). "
            "Part 108 BVLOS rulemaking is anticipated but not yet final as of mid-2026; ordinance language should "
            "reference federal rules by function rather than specific part number to avoid future amendments."
        ),
    }


def _build_prompt(inputs: dict, tier: int) -> str:
    return f"""You are a municipal planning consultant applying WSDOT Drone Hub Land Use Guidance v5.3 (June 2026).

Generate the approval pathway for a Tier {tier} drone hub in {inputs.get('state', 'a U.S. state')}.

PROJECT PARAMETERS:
{inputs}

WSDOT GUIDANCE REQUIREMENTS:
- Tier 1 and 2 in "Permitted" zones: administrative (lighter review track), NO public hearing, ministerial approval
- Tier 1 and 2 in "Conditional" zones: 300-ft notice radius + public hearing
- Tier 3: 500-ft notice radius + public hearing; development agreement recommended; periodic code review clause
- AIRCRAFT OPERATING HOUR LIMITS: Do NOT include these — local governments cannot set aircraft-specific hours
- Ground-based site activity (loading, maintenance, parking, lighting, generators) CAN be regulated
- FAA coordination note must clarify: airspace authorization ≠ land-use approval
- Include community engagement requirements (pre-application for CUP zones; documented for Tier 3)
- Reference proposed 14 CFR Part 108 (BVLOS) as emerging framework; write standards by function not part number

Return a JSON object with:
- pathways: array of step objects with: label, detail, required (bool), agency, notice_radius_ft (optional), timeline (optional), estimated_fees (optional)
- primary_entitlement: string
- public_hearing_required: boolean
- notice_radius_ft: number
- environmental_track: string
- estimated_timeline_weeks: string
- estimated_fees: string
- development_agreement_recommended: boolean
- faa_coordination_required: boolean
- aircraft_hour_limits: string (explanation of why NOT included)
- appeal_path: string
- wsdot_reference: string
- notes: string

Return only valid JSON."""


class PathwaysAgent:
    def generate(self, inputs: dict, tier: int = 1) -> dict:
        api_live = __import__("os").environ.get("ANTHROPIC_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
        if not api_live:
            return _mock_pathways(inputs, tier)

        prompt = _build_prompt(inputs, tier)
        response = call_llm(prompt, role="pathways_agent")
        result = parse_json_response(response)
        if result.get("mock") or result.get("parse_error"):
            return _mock_pathways(inputs, tier)
        return result
