"""
Tier Classification Agent.
Primary metric: dedicated drone hub area (sq ft).
Secondary Tier 3 triggers: multiple operators, high-volume ops (>100/hr),
substantial overnight activity, or permanent charging/docking/maintenance infrastructure.
Source: WSDOT Drone Hub Land Use Guidance v5.3, Table 1.
"""

from .base import call_llm, parse_json_response
try:
    from .. import config
except ImportError:
    import config


def _classify_tier(inputs: dict) -> tuple[int, str, list[str]]:
    """Return (tier, label, tier_3_triggers_hit)."""
    sqft = inputs.get("hub_area_sqft", 5000)
    num_operators = inputs.get("num_operators", 1)
    daily_ops = inputs.get("operational_scale", 0)
    accessory = inputs.get("accessory_use", False)

    tier_3_triggers = []

    # Check secondary Tier 3 triggers regardless of sqft
    if num_operators > 1:
        tier_3_triggers.append(f"multiple operators ({num_operators})")
    # High-volume threshold: WSDOT uses >100 flights per rolling 60-min period.
    # As a proxy from daily ops, flag if daily ops suggests sustained high throughput.
    # Minnesota draft uses >300 takeoffs+landings per calendar month (~10/day) for licensing;
    # we use a more conservative flag at 200/day as a proxy for likely high-volume periods.
    if daily_ops > 200:
        tier_3_triggers.append(f"operational intensity ({daily_ops} daily ops suggests high-volume periods)")

    # Primary sqft-based tier
    if sqft < 10000:
        base_tier = 1
    elif sqft <= 20000:
        base_tier = 2
    else:
        base_tier = 3

    # Escalate to Tier 3 if any secondary trigger fires
    if base_tier < 3 and tier_3_triggers:
        final_tier = 3
    else:
        final_tier = base_tier

    labels = {
        1: "Tier 1 — Micro / Accessory Hub" if accessory else "Tier 1 — Micro Hub",
        2: "Tier 2 — Neighborhood Hub" if accessory else "Tier 2 — Neighborhood Hub",
        3: "Tier 3 — Regional Hub",
    }
    return final_tier, labels[final_tier], tier_3_triggers


def _mock_classification(inputs: dict) -> dict:
    sqft = inputs.get("hub_area_sqft", 5000)
    density = inputs.get("density", "suburban")
    airport_type = inputs.get("airport_type", "class_g")
    accessory = inputs.get("accessory_use", False)
    state = inputs.get("state", "the State")

    tier, label, tier_3_triggers = _classify_tier(inputs)

    if tier == 1:
        description = (
            "Small-scale drone hub with less than 10,000 sq ft of dedicated drone hub area. "
            "One operator; low-to-moderate recurring activity; limited installed infrastructure."
        )
        approval_track = "Permitted by right under a lighter review track (administrative, non-discretionary) in commercial, retail, and industrial zones when defined standards are met."
    elif tier == 2:
        description = (
            "Neighborhood-scale drone hub with 10,000–20,000 sq ft of dedicated drone hub area. "
            "One operator; neighborhood-scale recurring activity; installed infrastructure that remains limited in scale."
        )
        approval_track = "Permitted by right under a lighter review track in commercial, mixed-use, and industrial zones. Requires community engagement and performance standards."
    else:
        triggers_str = "; ".join(tier_3_triggers) if tier_3_triggers else "hub area ≥ 20,000 sq ft"
        description = (
            f"Regional drone hub meeting one or more major-impact triggers: {triggers_str}. "
            "Requires conditional or special use approval in districts where the use is not prohibited."
        )
        approval_track = "Conditional or special use approval required. Site-specific evaluation of sensitive receptors, noise, operating hours, emergency access, public safety coordination, and mitigation."

    faa_coordination = airport_type in ("class_b", "class_c", "class_d")

    # State-specific preemption note
    preemption_note = ""
    if state == "Florida":
        preemption_note = (
            "Florida: State law restricts local governments from regulating drone delivery service based on the location of a drone hub. "
            "Generally applicable nuisance, landscaping, setback, and similar non-drone-specific standards may still apply. Consult counsel."
        )
    elif state in ("Georgia", "Virginia"):
        preemption_note = (
            f"{state}: Preemption-sensitive or state-coordinated environment. "
            "Local land-use classification and compatibility decisions remain important, but drone-specific ordinances should be reviewed by counsel."
        )
    elif state == "Washington":
        preemption_note = (
            "Washington State has not adopted statewide preemption for drone hub siting. "
            "Local jurisdictions retain meaningful land-use authority, provided standards focus on ground infrastructure, site design, land-use compatibility, nuisance, and local approval processes. "
            "WSDOT Aviation Division coordination is recommended for proposals involving airports, corridors, or regional operations."
        )

    return {
        "tier": tier,
        "label": label,
        "description": description,
        "approval_track": approval_track,
        "hub_area_sqft": sqft,
        "accessory_use": accessory,
        "tier_3_triggers": tier_3_triggers,
        "faa_coordination_required": faa_coordination,
        "faa_coordination_note": (
            f"Site is near a {airport_type.upper().replace('_', ' ')} facility. "
            "Consult WSDOT Aviation Division and the airport manager. "
            "FAA airspace authorization does not grant land-use approval."
            if faa_coordination else
            "FAA airspace authorization is separate from local land-use approval. "
            "Applicant should confirm Remote ID compliance and any applicable waiver/exemption status."
        ),
        "state_preemption_note": preemption_note,
        "density_context": density,
        "notes": (
            f"Classification based on {sqft:,} sq ft dedicated hub area in {density} context, {state}. "
            "Reclassification required if hub area or operational characteristics change materially. "
            "Tier thresholds are not automatic proxies for safety risk; a small hub may warrant "
            "heightened review if it supports multiple operators or high-volume activity."
        ),
    }


def _build_prompt(inputs: dict) -> str:
    return f"""You are a municipal land-use planner specializing in UAS (drone hub) regulation, applying the WSDOT Drone Hub Land Use Guidance v5.3 (June 2026).

Classify the following proposed drone hub into Tier 1, 2, or 3 using the WSDOT tier framework:
- Tier 1: < 10,000 sq ft dedicated drone hub area; one operator; low-to-moderate activity; limited installed infrastructure.
- Tier 2: 10,000–20,000 sq ft; one operator; neighborhood-scale activity; limited-scale installed infrastructure.
- Tier 3: ≥ 20,000 sq ft OR multiple operators OR high-volume operations (>100 flights/rolling 60 min) OR substantial overnight ground activity OR permanent charging/docking/storage/maintenance infrastructure.

PROJECT PARAMETERS:
{inputs}

Return a JSON object with:
- tier (integer 1-3)
- label (string, e.g. "Tier 1 — Micro Hub")
- description (1-2 sentences describing this tier)
- approval_track (string)
- hub_area_sqft (integer from inputs)
- accessory_use (boolean)
- tier_3_triggers (list of strings, empty if tier < 3)
- faa_coordination_required (boolean)
- faa_coordination_note (string)
- state_preemption_note (string, empty if not applicable)
- density_context (string)
- notes (string)

Return only valid JSON."""


class ClassificationAgent:
    def classify(self, inputs: dict) -> dict:
        if not inputs:
            return _mock_classification({})

        api_live = __import__("os").environ.get("ANTHROPIC_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
        if not api_live:
            return _mock_classification(inputs)

        prompt = _build_prompt(inputs)
        response = call_llm(prompt, role="classification_agent")
        result = parse_json_response(response)
        if result.get("mock") or result.get("parse_error"):
            return _mock_classification(inputs)
        return result
