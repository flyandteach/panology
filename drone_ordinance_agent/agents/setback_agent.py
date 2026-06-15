"""
Setback Recommendations Agent.
Computes and justifies setback distances adjusted for density, tier, and airport type.
"""

from .base import call_llm, parse_json_response
try:
    from .. import config
except ImportError:
    import config


def _compute_setbacks(inputs: dict, tier: int) -> dict:
    density = inputs.get("density", "suburban")
    airport_type = inputs.get("airport_type", "class_g")
    scale = inputs.get("operational_scale", 100)

    multiplier = config.DENSITY_MULTIPLIERS.get(density, 1.0)
    # Higher tiers get a 15% additional buffer per tier above 1
    tier_factor = 1.0 + (tier - 1) * 0.15

    setbacks = {}
    for use, base_ft in config.SETBACK_BASES.items():
        computed = int(base_ft * multiplier * tier_factor)
        setbacks[use] = computed

    # Airport proximity special rule
    airport_buffer = config.AIRPORT_PROXIMITY.get(airport_type, 3)
    airport_note = (
        f"Site is within {airport_buffer} miles of a {airport_type.upper().replace('_', ' ')} facility. "
        f"FAA coordination required. All flight path corridors must clear the airport's Part 77 surfaces."
    )

    items = [
        {
            "label": "Residential Property Line",
            "feet": setbacks["residential"],
            "detail": f"Minimum {setbacks['residential']} ft from any residential parcel boundary. Applies to both landing pad perimeter and the centreline of any designated flight path corridor at lowest authorized altitude.",
        },
        {
            "label": "Commercial / Mixed-Use Property Line",
            "feet": setbacks["commercial"],
            "detail": f"Minimum {setbacks['commercial']} ft from adjacent commercial or mixed-use parcel boundaries. May be reduced to {int(setbacks['commercial'] * 0.75)} ft with reciprocal easement and noise barrier.",
        },
        {
            "label": "Industrial Property Line",
            "feet": setbacks["industrial"],
            "detail": f"Minimum {setbacks['industrial']} ft from industrial parcel boundaries.",
        },
        {
            "label": "Public Open Space / Parks",
            "feet": setbacks["public_open_space"],
            "detail": f"Minimum {setbacks['public_open_space']} ft from the edge of any publicly dedicated park, greenway, or open space.",
        },
        {
            "label": "Schools & Hospitals (Sensitive Receptors)",
            "feet": setbacks["school_hospital"],
            "detail": f"Minimum {setbacks['school_hospital']} ft from the nearest property line of any school, hospital, childcare center, or licensed healthcare facility. Non-waivable.",
        },
        {
            "label": "Flight Path Corridor Buffer",
            "feet": setbacks["flight_path_buffer"],
            "detail": f"Flight path corridors at altitudes below 400 ft AGL shall maintain a lateral buffer of {setbacks['flight_path_buffer']} ft from residential structures.",
        },
    ]

    return {
        "items": items,
        "density": density,
        "density_multiplier": multiplier,
        "tier_factor": round(tier_factor, 2),
        "airport_type": airport_type,
        "airport_proximity_miles": airport_buffer,
        "airport_note": airport_note,
        "notes": (
            f"Setbacks computed using base values × {multiplier}x density multiplier ({density}) "
            f"× {round(tier_factor, 2)}x tier factor (Tier {tier}). "
            "Applicants may propose alternative setbacks through a Site-Specific Safety Study accepted by the Planning Director."
        ),
    }


def _build_prompt(inputs: dict, tier: int) -> str:
    density = inputs.get("density", "suburban")
    multiplier = config.DENSITY_MULTIPLIERS.get(density, 1.0)
    return f"""You are a licensed airport land-use planner and zoning attorney.

Generate specific setback requirements for a Tier {tier} drone hub or vertiport.

PROJECT PARAMETERS:
{inputs}
Density multiplier: {multiplier}x

Return a JSON object with:
- items: array of objects, each with: label, feet (integer), detail (one legal sentence)
  Cover: residential property line, commercial property line, industrial property line, parks/open space, schools/hospitals, flight path corridor buffer.
- density: string
- density_multiplier: number
- tier_factor: number
- airport_type: string
- airport_proximity_miles: number
- airport_note: string
- notes: string

Return only valid JSON."""


class SetbackAgent:
    def generate(self, inputs: dict, tier: int = 2) -> dict:
        api_live = __import__("os").environ.get("ANTHROPIC_API_KEY") or __import__("os").environ.get("OPENAI_API_KEY")
        if not api_live:
            return _compute_setbacks(inputs, tier)

        prompt = _build_prompt(inputs, tier)
        response = call_llm(prompt, role="setback_agent")
        result = parse_json_response(response)
        if result.get("mock") or result.get("parse_error"):
            return _compute_setbacks(inputs, tier)
        return result
