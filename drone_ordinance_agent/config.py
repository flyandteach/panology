"""
Configuration for the Drone Hub / Vertiport Ordinance Agent.
"""

import os

# --- LLM ---
DEFAULT_LLM_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
TEMPERATURE = 0.4  # Lower temp for regulatory precision

# --- File Paths ---
EXPORTS_DIR = "exports"
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

# --- Tier Classification Thresholds (daily operations) ---
TIER_THRESHOLDS = {
    "tier_1": 50,    # Micro-hub: up to 50 ops/day
    "tier_2": 200,   # Community vertiport: 51-200 ops/day
    "tier_3": 500,   # Regional hub: 201-500 ops/day
    "tier_4": 9999,  # Major vertiport: 500+ ops/day
}

# --- Setback Base Values (feet) — adjusted by density multiplier ---
SETBACK_BASES = {
    "residential": 500,
    "commercial": 150,
    "industrial": 75,
    "public_open_space": 250,
    "school_hospital": 750,
    "flight_path_buffer": 200,
}

# --- Density Multipliers ---
DENSITY_MULTIPLIERS = {
    "rural": 0.5,
    "suburban": 1.0,
    "urban": 1.5,
    "dense_urban": 2.0,
}

# --- Airport Proximity Triggers (miles) ---
AIRPORT_PROXIMITY = {
    "class_b": 30,
    "class_c": 20,
    "class_d": 10,
    "class_e": 5,
    "class_g": 3,
    "heliport": 2,
    "vertiport": 1,
}

# --- Environmental Review Trigger Thresholds ---
ENV_TRIGGERS = {
    "noise_ops_per_day": 100,       # Noise impact study required above this
    "acreage_threshold": 2.0,       # CEQA/NEPA required above 2 acres disturbed
    "wetland_buffer_feet": 300,     # Wetland proximity triggers review
    "floodplain_buffer_feet": 500,
    "flight_path_residential_dist": 1000,  # Residential under flight path triggers review
}

# --- Display ---
SEPARATOR = "=" * 70
THIN_SEPARATOR = "-" * 70
