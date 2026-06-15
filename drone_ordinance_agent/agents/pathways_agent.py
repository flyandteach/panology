"""
Approval Pathways Agent.
Determines the required entitlement process based on tier, density, and state.
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

    # Core pathway decision logic
    if tier == 1:
        primary_path = "Ministerial / Building Permit"
        hearing_required = False
        ceqa_class = "Class 3 Categorical Exemption (New Construction of Small Structures)"
        timeline_weeks = "4–8"
        deposit_range = "$2,000–$8,000"
    elif tier == 2:
        primary_path = "Administrative Use Permit (AUP)"
        hearing_required = False
        ceqa_class = "Class 3 Categorical Exemption or Initial Study/Mitigated Negative Declaration depending on site conditions"
        timeline_weeks = "8–16"
        deposit_range = "$8,000–$25,000"
    elif tier == 3:
        primary_path = "Conditional Use Permit (CUP) — Planning Commission"
        hearing_required = True
        ceqa_class = "Initial Study / Mitigated Negative Declaration (IS/MND) or full EIR if significant unmitigated impacts"
        timeline_weeks = "16–26"
        deposit_range = "$25,000–$75,000"
    else:
        primary_path = "Specific Plan Amendment or Development Agreement + CUP — City Council"
        hearing_required = True
        ceqa_class = "Environmental Impact Report (EIR) required"
        timeline_weeks = "26–52+"
        deposit_range = "$75,000–$250,000+"

    faa_coordination = inputs.get("airport_type", "") in ("class_b", "class_c", "class_d")

    pathways = [
        {
            "label": f"Step 1 — Pre-Application Conference",
            "detail": f"Applicant meets with Planning, Building, and Public Works staff to identify applicable requirements, fee schedules, and potential issues prior to formal submission.",
            "required": True,
            "agency": f"{municipality} Planning Department",
        },
        {
            "label": f"Step 2 — {primary_path}",
            "detail": (
                f"Primary land use entitlement. "
                + ("Requires a noticed public hearing before the Planning Commission." if hearing_required else "Administrative review; no public hearing required unless appealed.")
            ),
            "required": True,
            "agency": f"{municipality} Planning Commission" if hearing_required else f"{municipality} Planning Director",
            "timeline": f"Approximately {timeline_weeks} weeks from complete application",
            "estimated_fees": deposit_range,
        },
        {
            "label": f"Step 3 — CEQA / Environmental Review",
            "detail": f"{ceqa_class}. Applicant is responsible for preparation of any required environmental document. Third-party peer review may be required at applicant's expense.",
            "required": True,
            "agency": f"{municipality} / Lead Agency",
        },
        {
            "label": "Step 4 — FAA Coordination",
            "detail": (
                "Submit FAA Form 7460-1 (Notice of Proposed Construction or Alteration) for all structures. "
                + ("A Letter of Agreement (LOA) with ATCT is required prior to operations." if faa_coordination else "Aeronautical study recommended; NOTAM protocols to be established with local FSDO.")
            ),
            "required": True,
            "agency": "Federal Aviation Administration",
        },
        {
            "label": "Step 5 — State Aeronautics Division Notification",
            "detail": f"File required notice with the {state} Division of Aeronautics per state aviation code. Some states require a permit for new landing areas; confirm current {state} requirements.",
            "required": True,
            "agency": f"{state} Division of Aeronautics",
        },
        {
            "label": "Step 6 — Building Permits & Inspections",
            "detail": "All structures, electrical systems, and mechanical equipment require standard building permits and inspections. Structural engineering wet-stamp required for rooftop installations.",
            "required": True,
            "agency": f"{municipality} Building & Safety Division",
        },
    ]

    if tier >= 3:
        pathways.append({
            "label": "Step 7 — Transportation Demand Management (TDM) Plan",
            "detail": "Applicant must submit and implement a TDM Plan addressing ground-side traffic generation, parking, and intermodal connections. Annual monitoring report required.",
            "required": True,
            "agency": f"{municipality} Public Works / Transportation",
        })

    if tier == 4:
        pathways.append({
            "label": "Step 8 — Development Agreement",
            "detail": "Due to facility scale and long-term infrastructure implications, the City may require a Development Agreement per Government Code § 65864 et seq., establishing vested rights in exchange for public benefits.",
            "required": True,
            "agency": f"{municipality} City Council",
        })

    appeal_path = (
        "Appeal of Planning Commission action to City Council within 10 days of decision."
        if hearing_required else
        "Appeal of Administrative Use Permit to Planning Commission within 10 days of decision."
    )

    return {
        "pathways": pathways,
        "primary_entitlement": primary_path,
        "public_hearing_required": hearing_required,
        "ceqa_track": ceqa_class,
        "estimated_timeline_weeks": timeline_weeks,
        "estimated_fees": deposit_range,
        "faa_coordination_required": faa_coordination,
        "appeal_path": appeal_path,
        "notes": (
            f"Timeline and fee estimates are indicative for Tier {tier} in {density} context, {state}. "
            "Actual processing times vary by jurisdiction. Pre-application coordination is strongly recommended."
        ),
    }


def _build_prompt(inputs: dict, tier: int) -> str:
    return f"""You are a municipal planning consultant specializing in aviation infrastructure entitlements.

Generate a step-by-step approval pathway for a Tier {tier} drone hub or vertiport in {inputs.get('state', 'a U.S. state')}.

PROJECT PARAMETERS:
{inputs}

Return a JSON object with:
- pathways: array of steps, each with: label, detail, required (bool), agency, timeline (optional), estimated_fees (optional)
- primary_entitlement: string (e.g. "Ministerial Permit", "CUP", "Development Agreement")
- public_hearing_required: boolean
- ceqa_track: string (CEQA/NEPA review class or document type)
- estimated_timeline_weeks: string
- estimated_fees: string
- faa_coordination_required: boolean
- appeal_path: string
- notes: string

Return only valid JSON."""


class PathwaysAgent:
    def generate(self, inputs: dict, tier: int = 2) -> dict:
        api_live = __import__("os").environ.get("ANTHROPIC_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
        if not api_live:
            return _mock_pathways(inputs, tier)

        prompt = _build_prompt(inputs, tier)
        response = call_llm(prompt, role="pathways_agent")
        result = parse_json_response(response)
        if result.get("mock") or result.get("parse_error"):
            return _mock_pathways(inputs, tier)
        return result
