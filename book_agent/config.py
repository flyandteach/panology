"""
Configuration constants and thresholds for the Recursive Editorial Book Agent.
"""

import os

# --- Scoring Thresholds ---
THRESHOLDS = {
    "min_any_score": 8.0,         # No individual dimension score below this
    "min_average": 8.5,           # Overall average must meet this
    "repetition": 9.0,            # Repetition/redundancy score minimum
    "continuity": 9.0,            # Continuity score minimum
    "critical_audience": 8.5,     # Critical audience score minimum
    "line_edit": 8.0,             # Line editor score minimum
}

# --- Revision Control ---
MAX_REVISION_CYCLES = 5

# --- LLM Model Config ---
DEFAULT_LLM_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
TEMPERATURE = 0.7

# --- File Paths ---
MEMORY_FILENAME = "project_memory.json"
DRAFTS_CURRENT_DIR = "drafts/current"
DRAFTS_APPROVED_DIR = "drafts/approved"
DRAFTS_REJECTED_DIR = "drafts/rejected"
EXPORTS_DIR = "exports"
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

# --- Score Dimensions ---
SCORE_DIMENSIONS = ["line_edit", "repetition", "continuity", "critical_audience"]

# --- Display Settings ---
SEPARATOR = "=" * 70
THIN_SEPARATOR = "-" * 70
