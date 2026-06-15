"""
Tier Classification Agent.
Assigns the facility tier and operational class based on scale, airport type, and density.
"""

from .base import call_llm, parse_json_response
try:
    from .. import config
except ImportError:
    import config


def _mock_classification(inputs: dict) -> dict:
    scale = inputs.get("operational_scale", 0)
    density = inputs.get("density", "suburban")
    airport_type = inputs.get("airport_type", "class_g")

    if scale <= config.TIER_THRESHOLDS["tier_1"]:
        tier, label = 1, "Micro-Hub"
        description = "Small-scale drone delivery node or rooftop pad, no passenger operations."
    elif scale <= config.TIER_THRESHOLDS["tier_2"]:
        tier, label = 2, "Community Vertiport"
        description = "Neighborhood-serving facility supporting package delivery and limited eVTOL passenger service."
    elif scale <= config.TIER_THRESHOLDS["tier_3"]:
        tier, label = 3, "Regional Vertiport"
        description = "Multi-modal hub with scheduled eVTOL service, ground transport integration, and on-site maintenance."
    else:
        tier, label = 4, "Major Vertiport / Skyport"
        description = "High-capacity facility functioning as a primary node in the regional UAM network."

    faa_coordination = airport_type in ("class_b", "class_c", "class_d")

    return {
        "tier": tier,
        "label": label,
        "description": description,
        "operational_class": "UAM-A" if scale > 200 else "UAS-C",
        "faa_coordination_required": faa_coordination,
        "faa_coordination_note": (
            f"This site is within a {airport_type.upper().replace('_', ' ')} airspace. "
            "A Letter of Agreement (LOA) with the controlling ATCT is required prior to operations."
            if faa_coordination else
            "No mandatory FAA coordination for airspace class, but notification of local FSDO is recommended."
        ),
        "density_modifier": density,
        "notes": (
            f"Tier {tier} classification applies in {density} contexts. "
            "Reclassification required if operational scale changes by more than 25% over any 12-month period."
        ),
    }


def _build_prompt(inputs: dict) -> str:
    prompt_path = config.PROMPTS_DIR + "/classification.md"
    try:
        with open(prompt_path, encoding="utf-8") as fh:
            template = fh.read()
        return template.replace("{INPUTS}", str(inputs))
    except FileNotFoundError:
        pass

    return f"""You are a municipal aviation and land-use attorney specializing in UAM (Urban Air Mobility) regulation.

Given the following project parameters, generate a tier classification for a drone hub or vertiport facility.

PROJECT PARAMETERS:
{inputs}

Respond with a JSON object containing:
- tier (integer 1-4)
- label (short facility type name)
- description (1-2 sentences)
- operational_class (e.g. UAS-C, UAM-A)
- faa_coordination_required (boolean)
- faa_coordination_note (string)
- density_modifier (string)
- notes (string with reclassification triggers)

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
