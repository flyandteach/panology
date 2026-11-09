"""
Configuration constants for the AMRG (Advanced Mobility Research Group)
weekly literature-watch agent.
"""

import os

# --- Search topics ---
# Each entry is an OpenAlex full-text search query (plain keywords -- the
# API does its own relevance ranking; no quoting/boolean syntax needed).
SEARCH_TOPICS = {
    "AAM": "advanced air mobility",
    "UAM": "urban air mobility",
    "eVTOL": "eVTOL aircraft",
    "electric_aircraft": "electric aircraft propulsion",
    "vertiports": "vertiport design operations",
    "ai_in_aviation": "artificial intelligence aviation safety",
}

# Only keep results published within this many days of the run. Enforced
# directly via OpenAlex's from_publication_date filter (a real filter, not
# a best-effort approximation).
LOOKBACK_DAYS = 10

# Max results to inspect per topic per run (keeps runs fast and limits how
# much of the shared anonymous rate budget a single run consumes).
MAX_RESULTS_PER_TOPIC = 10

# --- OpenAlex search backend (agents/article_search.py) ---
# Both optional. OPENALEX_MAILTO opts into OpenAlex's "polite pool" for
# better reliability -- this is a courtesy query param, not an account, so
# it's fine to use a contact address here, but it's still sent to a
# third-party service on every request: leave it unset unless you want
# that, and never default it to someone's personal email without asking.
# OPENALEX_API_KEY is a free personal key for a dedicated rate budget
# instead of sharing the lowest-priority anonymous tier with everyone else
# hitting the API (https://docs.openalex.org/how-to-use-the-api/api-overview#api-key).
OPENALEX_MAILTO = os.environ.get("OPENALEX_MAILTO", "")
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", "")

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

# --- Email delivery ---
# Sends a weekly digest (what ran, what was found, links) via SMTP. Default
# transport is Gmail SMTP with an App Password -- no new third-party account
# needed. Auth/config via env vars:
#   EMAIL_SMTP_USER      - the Gmail address to send from
#   EMAIL_SMTP_PASSWORD  - a Gmail App Password (requires 2FA on that account;
#                          https://myaccount.google.com/apppasswords)
#   EMAIL_TO             - recipient(s), comma-separated (defaults to EMAIL_SMTP_USER)
# Without EMAIL_SMTP_USER/PASSWORD configured, the pipeline still runs; it
# just skips sending and says so in the run report.
EMAIL_SMTP_HOST = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
EMAIL_TO = os.environ.get("EMAIL_TO") or "flyandteach@gmail.com"

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
