from dataclasses import dataclass

# ── API endpoints ──────────────────────────────────────────────────────────────
WEATHER_API_BASE = "https://aviationweather.gov/api/data"
NOTAM_API_BASE   = "https://notamapi.faa.gov/notamapi/v1/notams"
NOTAM_TOKEN_URL  = "https://idm.faa.gov/idm/externalauth/oauth/token"
TFR_LIST_URL     = "https://tfr.faa.gov/tfr2/list.html"
TFR_DETAIL_URL   = "https://tfr.faa.gov/save_pages/detail_{notam_id}.xml"
UASFM_QUERY_URL  = (
    "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services"
    "/UAS_Facility_Maps/FeatureServer/0/query"
)

# ── Default LLM ────────────────────────────────────────────────────────────────
DEFAULT_MODEL  = "claude-sonnet-4-6"
MAX_TOKENS     = 4096
TEMPERATURE    = 0.2   # low temp for structured scoring

# ── PAVE risk thresholds (1–5 scale; 5 = highest risk) ────────────────────────
PAVE_GO_THRESHOLD         = 2.5   # avg <= this → GO
PAVE_CAUTION_THRESHOLD    = 3.5   # avg <= this → PROCEED_WITH_MITIGATIONS

# ── Hard-limit weather thresholds for Part 107 VLOS ───────────────────────────
WIND_HARD_LIMIT_KT        = 23    # 107.51(a)
GUST_HARD_LIMIT_KT        = 30
VIS_HARD_LIMIT_SM         = 3.0   # 107.51(b)
# Ceiling is not legally specified for Part 107 VLOS but operationally:
CEILING_CAUTION_FT        = 1000  # MVFR / operational caution

# ── NOTAM search radius ────────────────────────────────────────────────────────
NOTAM_RADIUS_NM           = 5

# ── SORA iGRC table ───────────────────────────────────────────────────────────
# Rows: population density  ("sparse", "populated", "gathering")
# Cols: UA characteristic dimension category index (0–5 maps to DIM_CLASSES)
# Source: JARUS SORA 2.5 Annex B (simplified)
DIM_CLASSES = [1.0, 3.0, 8.0, 20.0, 40.0, float("inf")]  # upper bounds in metres
IGRC_TABLE = {
    #            <1m  <3m  <8m  <20m <40m  ≥40m
    "sparse":   [  2,   3,   4,    5,   6,    7],
    "populated":[  3,   4,   5,    6,   7,    8],
    "gathering":[  4,   5,   6,    7,   8,    9],
}

# ── SORA ARC rules ────────────────────────────────────────────────────────────
# Simplified mapping → "a", "b", "c", "d"
# Applied in sora_scorer.py based on airspace class + altitude
ARC_LABEL = {1: "a", 2: "b", 3: "c", 4: "d"}

# ── SAIL lookup table  (iGRC rows × ARC cols) ────────────────────────────────
# Source: SORA 2.5 Table 2
SAIL_TABLE = {
    #         ARC-a  ARC-b  ARC-c  ARC-d
    1:       [    1,     2,     4,     6],
    2:       [    1,     2,     4,     6],
    3:       [    2,     3,     5,     6],
    4:       [    2,     3,     5,     6],
    5:       [    3,     4,     5,     6],
    6:       [    3,     4,     5,     6],
    7:       [    4,     5,     6,     6],
    8:       [    5,     6,     6,     6],
    9:       [    6,     6,     6,     6],
}

# ── Scoring dimensions reported in the audit record ───────────────────────────
PAVE_DIMENSIONS = ["pilot", "aircraft", "environment", "external"]
PAVE_RISK_LABELS = {1: "LOW", 2: "LOW-MEDIUM", 3: "MEDIUM", 4: "HIGH", 5: "CRITICAL"}
VERDICT_LABELS = {
    "GO":                      "GO — proceed as planned",
    "PROCEED_WITH_MITIGATIONS":"PROCEED WITH MITIGATIONS — review named items before launch",
    "NO_GO":                   "NO-GO — one or more hard stops identified",
}
