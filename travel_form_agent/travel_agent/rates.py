"""WSDOT/OFM travel rates and object code rules.

Rates verified against OFM Directive 26A-01 (effective 2026-01-01).
Update the RATES block each January when OFM publishes the new directive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# POV mileage rates (Directive 26A-01, effective 2026-01-01)
# ---------------------------------------------------------------------------
POV_FULL_RATE = 0.725       # GC01 – full POV rate (no state vehicle available)
POV_ELECTIVE_RATE = 0.205   # GC02 – elective POV rate (state vehicle was available)
# VERIFY each January: motorcycle and aircraft rates
MOTORCYCLE_RATE = 0.725     # VERIFY – same as POV per 26A-01, confirm with OFM
AIRCRAFT_RATE = 1.21        # VERIFY – privately owned aircraft, cents/mile

# ---------------------------------------------------------------------------
# In-state meal tiers (OFM FY2026)
# Splits: B=breakfast, L=lunch, D=dinner
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MealTier:
    daily_total: float
    breakfast: float
    lunch: float
    dinner: float


MEAL_TIERS: Dict[int, MealTier] = {
    68: MealTier(68.0, 14.00, 19.00, 35.00),
    80: MealTier(80.0, 17.00, 22.00, 41.00),
    86: MealTier(86.0, 20.00, 24.00, 42.00),
    92: MealTier(92.0, 24.00, 27.00, 41.00),
}

# ---------------------------------------------------------------------------
# Washington county → meal tier (OFM FY2026 per diem map)
# Verify seasonally – Snohomish and some coastal counties vary by season.
# Counties not listed default to the base $68 tier.
# ---------------------------------------------------------------------------
COUNTY_MEAL_TIER: Dict[str, int] = {
    # $92 tier
    "king": 92,
    # $86 tier
    "snohomish": 86,
    "island": 86,
    "san juan": 86,
    # $80 tier
    "pierce": 80,
    "clark": 80,
    "thurston": 80,
    "whatcom": 80,
    "skagit": 80,
    "kitsap": 80,
    "jefferson": 80,
    "clallam": 80,
}

DEFAULT_MEAL_TIER = 68  # most in-state counties

# ---------------------------------------------------------------------------
# Washington city → county lookup
# Covers the cities most likely to appear on WSDOT travel requests.
# ---------------------------------------------------------------------------
CITY_COUNTY: Dict[str, str] = {
    # King County
    "seattle": "king", "bellevue": "king", "renton": "king", "kent": "king",
    "auburn": "king", "federal way": "king", "redmond": "king", "kirkland": "king",
    "sammamish": "king", "shoreline": "king", "burien": "king", "tukwila": "king",
    "seatac": "king", "des moines": "king", "mercer island": "king",
    "newcastle": "king", "issaquah": "king", "covington": "king",
    "maple valley": "king", "enumclaw": "king", "black diamond": "king",
    "boeing field": "king", "bfi": "king",
    # Snohomish County
    "everett": "snohomish", "marysville": "snohomish", "lynnwood": "snohomish",
    "edmonds": "snohomish", "mountlake terrace": "snohomish", "mukilteo": "snohomish",
    "bothell": "snohomish", "mill creek": "snohomish", "monroe": "snohomish",
    "arlington": "snohomish", "stanwood": "snohomish",
    # Pierce County
    "tacoma": "pierce", "lakewood": "pierce", "puyallup": "pierce",
    "bonney lake": "pierce", "sumner": "pierce", "orting": "pierce",
    "gig harbor": "pierce", "university place": "pierce",
    # Thurston County
    "olympia": "thurston", "lacey": "thurston", "tumwater": "thurston",
    "yelm": "thurston", "tenino": "thurston",
    # Clark County
    "vancouver": "clark", "camas": "clark", "washougal": "clark",
    "battle ground": "clark", "ridgefield": "clark", "la center": "clark",
    # Whatcom County
    "bellingham": "whatcom", "ferndale": "whatcom", "blaine": "whatcom",
    "lynden": "whatcom", "sumas": "whatcom",
    # Skagit County
    "mount vernon": "skagit", "burlington": "skagit", "anacortes": "skagit",
    "sedro-woolley": "skagit", "concrete": "skagit",
    # Kitsap County
    "bremerton": "kitsap", "silverdale": "kitsap", "port orchard": "kitsap",
    "poulsbo": "kitsap", "bainbridge island": "kitsap",
    # Jefferson County
    "port townsend": "jefferson", "port hadlock": "jefferson",
    # Clallam County
    "port angeles": "clallam", "sequim": "clallam", "forks": "clallam",
    # Island County
    "oak harbor": "island", "coupeville": "island", "langley": "island",
    # San Juan County
    "friday harbor": "san juan", "eastsound": "san juan",
    # Other common destinations (base tier)
    "spokane": "spokane", "yakima": "yakima", "kennewick": "benton",
    "pasco": "franklin", "richland": "benton", "wenatchee": "chelan",
    "leavenworth": "chelan", "moses lake": "grant", "ellensburg": "kittitas",
    "walla walla": "walla walla", "longview": "cowlitz", "kelso": "cowlitz",
    "aberdeen": "grays harbor", "hoquiam": "grays harbor",
    "chehalis": "lewis", "centralia": "lewis", "shelton": "mason",
    "colville": "stevens", "republic": "ferry", "okanogan": "okanogan",
    "omak": "okanogan", "chelan": "chelan", "bridgeport": "douglas",
    "ephrata": "grant", "coulee dam": "grant",
}


def resolve_county(city: str) -> Optional[str]:
    """Return the WA county name for a city, or None if unknown."""
    return CITY_COUNTY.get(city.strip().lower())


def meal_tier_for_county(county: str) -> int:
    """Return the meal tier daily total for a county."""
    return COUNTY_MEAL_TIER.get(county.strip().lower(), DEFAULT_MEAL_TIER)


def meal_tier_for_city(city: str) -> Tuple[int, Optional[str]]:
    """Return (tier_total, county_name) for a destination city."""
    county = resolve_county(city)
    if county is None:
        return DEFAULT_MEAL_TIER, None
    return meal_tier_for_county(county), county


def get_meal_amounts(tier_total: int) -> MealTier:
    return MEAL_TIERS.get(tier_total, MEAL_TIERS[DEFAULT_MEAL_TIER])


# ---------------------------------------------------------------------------
# Object code engine
# ---------------------------------------------------------------------------

def subsistence_object_code(overnight: bool, scope: str = "in_state") -> str:
    """
    scope: 'in_state' | 'out_of_state' | 'out_of_country'
    Returns the Chapter 5 object code for subsistence.
    """
    if scope == "in_state":
        return "GA01" if overnight else "GA02"
    if scope == "out_of_state":
        return "GF05" if overnight else "GF02"
    if scope == "out_of_country":
        return "GF06" if overnight else "GF03"
    return "GA01"


def mileage_object_code(state_vehicle_available: bool) -> str:
    return "GC02" if state_vehicle_available else "GC01"


def mileage_rate(state_vehicle_available: bool) -> float:
    return POV_ELECTIVE_RATE if state_vehicle_available else POV_FULL_RATE


def registration_object_code(reg_type: str) -> str:
    """
    reg_type: 'conference' | 'training' | 'out_of_state'
    """
    mapping = {
        "conference": "EG02",
        "training": "EG01",
        "out_of_state": "EG94",
    }
    return mapping.get(reg_type.lower(), "EG02")


OTHER_TRAVEL_CODES = {
    "parking": "GD01",
    "taxi": "GD01",
    "rideshare": "GD01",
    "ferry": "GD01",
    "toll": "GD01",
    "bus": "GD01",
    "rail": "GD01",
    "rental_car": "GD01",
    "official_meal": "GD03",
    "good_to_go": "GD05",
    "motor_pool": "GN01",
    "tef": "GN02",
    "airfare_in_state": "GB01",
    "airfare_out_of_state": "GG05",
    "airfare_out_of_country": "GG06",
}


def other_travel_object_code(expense_type: str) -> str:
    return OTHER_TRAVEL_CODES.get(expense_type.lower(), "GD01")
