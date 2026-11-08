"""
Heuristic fact-check agent.

Scope (deliberately limited -- see README "Fact-check limitations"):
  - Reference existence: extracts the reference list and checks each entry
    resolves against Crossref's free public API (no key required). This
    confirms a matching bibliographic record exists; it is NOT a guarantee
    the citing article represents that source accurately.
  - Statistical/claim plausibility: an LLM pass flags numeric claims that
    look internally inconsistent or implausible on their face. This is a
    sanity check, not independent verification against primary data.

Explicitly out of scope: plagiarism-overlap scanning and AI-authorship
detection. Neither has a reliable free/unsupervised tool, and an
unsupported percentage or likelihood would be more misleading than useful.
If you have a licensed tool for either (Turnitin, Copyleaks, Originality.ai,
etc.), wire its API into this module -- the summarizer already has a slot
for a "fact_check" section in the output template.
"""

import json
import re
import time

import requests

import config
from utils.llm import call_llm

CROSSREF_API = "https://api.crossref.org/works"


def extract_references(full_text: str) -> list:
    """Best-effort split of a trailing References/Bibliography section into
    individual entries."""
    match = re.search(
        r"\n\s*(References|Bibliography|Works Cited)\s*\n(.*)",
        full_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []

    tail = match.group(2)
    # Cut off anything after a likely appendix/acknowledgment boundary.
    tail = re.split(r"\n\s*(Appendix|Acknowledg)", tail, maxsplit=1, flags=re.IGNORECASE)[0]

    # Split on blank-line-separated or numbered ("[1]", "1.") entries.
    raw_entries = re.split(r"\n(?=\[\d+\]|\d{1,3}\.\s)", tail)
    entries = [e.strip().replace("\n", " ") for e in raw_entries if len(e.strip()) > 20]
    return entries[:100]  # cap to keep the run fast


def verify_reference(entry: str) -> dict:
    """Query Crossref for a bibliographic match. Returns
    {"entry": str, "found": bool, "matched_title": str|None, "doi": str|None}."""
    try:
        resp = requests.get(
            CROSSREF_API,
            params={"query.bibliographic": entry, "rows": 1},
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])
    except Exception as e:
        return {"entry": entry, "found": None, "matched_title": None, "doi": None, "error": str(e)}

    if not items:
        return {"entry": entry, "found": False, "matched_title": None, "doi": None}

    top = items[0]
    title = (top.get("title") or [""])[0]
    return {
        "entry": entry,
        "found": True,
        "matched_title": title,
        "doi": top.get("DOI"),
    }


def verify_references(entries: list, max_checks: int = 25, sleep_between: float = 0.5) -> list:
    """Verify up to `max_checks` references against Crossref, rate-limited."""
    results = []
    for entry in entries[:max_checks]:
        results.append(verify_reference(entry))
        time.sleep(sleep_between)
    return results


CLAIM_CHECK_PROMPT = """You are doing a plausibility sanity-check (NOT a citation or source check) \
on numeric/statistical claims in the excerpt below from an aviation research article.

For each distinct numeric claim (statistic, percentage, measurement, count), judge only whether \
it is internally plausible (consistent with itself and with other numbers in the excerpt, not an \
obvious unit/order-of-magnitude error). Do not try to verify it against outside sources -- you \
don't have access to them. If you're not confident a claim is implausible, don't flag it.

ARTICLE EXCERPT:
{EXCERPT}

Return ONLY JSON: {{"flagged_claims": [{{"claim": str, "concern": str}}], "claims_reviewed": int}}"""


def check_claim_plausibility(full_text: str, excerpt_chars: int = 12000) -> dict:
    """LLM-based sanity check on numeric claims. Heuristic only."""
    excerpt = full_text[:excerpt_chars]
    prompt = CLAIM_CHECK_PROMPT.replace("{EXCERPT}", excerpt)
    mock = json.dumps({"flagged_claims": [], "claims_reviewed": 0})
    response = call_llm(prompt, mock_response=mock)

    for extractor in [
        lambda r: json.loads(r),
        lambda r: json.loads(re.search(r"```(?:json)?\s*(\{.*?\})\s*```", r, re.DOTALL).group(1)),
        lambda r: json.loads(re.search(r"\{.*\}", r, re.DOTALL).group(0)),
    ]:
        try:
            data = extractor(response)
            return {
                "flagged_claims": list(data.get("flagged_claims", [])),
                "claims_reviewed": int(data.get("claims_reviewed", 0)),
            }
        except Exception:
            continue

    return {"flagged_claims": [], "claims_reviewed": 0, "parse_error": True}


def run_fact_check(full_text: str) -> dict:
    """Full heuristic fact-check pass for one article."""
    entries = extract_references(full_text)
    reference_results = verify_references(entries)
    claim_result = check_claim_plausibility(full_text)

    verified_count = sum(1 for r in reference_results if r.get("found") is True)
    not_found_count = sum(1 for r in reference_results if r.get("found") is False)

    return {
        "references_detected": len(entries),
        "references_checked": len(reference_results),
        "references_verified": verified_count,
        "references_not_found": not_found_count,
        "reference_details": reference_results,
        "flagged_claims": claim_result["flagged_claims"],
        "claims_reviewed": claim_result["claims_reviewed"],
        "scope_note": (
            "Reference existence checked against Crossref; claim plausibility is an LLM "
            "sanity check, not source verification. Plagiarism-overlap and AI-authorship "
            "detection are intentionally omitted -- no reliable free tool exists for either, "
            "and an unsupported score would be misleading."
        ),
    }
