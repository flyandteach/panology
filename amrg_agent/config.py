"""
Configuration constants for the AMRG (Advanced Mobility Research Group)
weekly literature-watch agent.
"""

import os

# --- Search topics ---
# Each entry is a Google Scholar query string. Keep these focused; scholarly
# scrapes the public Scholar results page and broad queries return noisy hits.
SEARCH_TOPICS = {
    "AAM": "\"advanced air mobility\"",
    "UAM": "\"urban air mobility\"",
    "eVTOL": "eVTOL aircraft",
    "electric_aircraft": "\"electric aircraft\" propulsion",
    "vertiports": "vertiport design OR operations",
    "ai_in_aviation": "\"artificial intelligence\" aviation safety OR operations",
}

# Only keep results published within this many days of the run (best-effort;
# Scholar's own metadata is coarse, so this is applied on a best-effort basis
# using the publication year plus the date-sorted search order).
LOOKBACK_DAYS = 10

# Max results to inspect per topic per run (keeps runs fast and reduces the
# chance of Scholar rate-limiting/CAPTCHA-blocking the run).
MAX_RESULTS_PER_TOPIC = 10

# --- LLM config ---
DEFAULT_LLM_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
TEMPERATURE = 0.4

# --- Paths ---
BASE_DIR = os.path.dirname(__file__)
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
STATE_DIR = os.path.join(BASE_DIR, "state")
SEEN_ARTICLES_FILE = os.path.join(STATE_DIR, "seen_articles.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DOWNLOADS_DIR = os.path.join(OUTPUT_DIR, "downloads")

# --- Google Drive delivery ---
# Service-account driven upload (see amrg_agent/agents/drive_upload.py).
# Auth is provided via one of:
#   GOOGLE_SERVICE_ACCOUNT_FILE  - path to a service-account JSON key
#   GOOGLE_SERVICE_ACCOUNT_JSON  - the JSON key contents inline (e.g. a CI secret)
# The target folder must already exist and be shared with the service
# account's email (Drive service accounts have no storage quota of their own).
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")

# --- HTTP ---
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

# --- Writing-score formula weights (per AMRG project instructions) ---
QUALITY_WEIGHTS = {
    "cohesion": 0.20,
    "lexical_diversity": 0.15,
    "semantic_complexity": 0.15,
    "syntactic_complexity": 0.20,
    "grammar": 0.15,
    "topic_relevance": 0.15,
}
READABILITY_WEIGHT = 0.35
QUALITY_WEIGHT = 0.65
