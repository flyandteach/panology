"""
LLM-backed mitigation advisor.
Given the completed PAVE + SORA scores, returns a list of named Mitigation objects.
Falls back to rule-based mitigations when the LLM is unavailable.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional

from frat_agent.config import DEFAULT_MODEL, MAX_TOKENS, TEMPERATURE
from frat_agent.models import PaveScore, SoraScore, Mitigation


_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "mitigation_advisor.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_message(pave: PaveScore, sora: SoraScore, hard_stops: list[str]) -> str:
    sail_roman = ["", "I", "II", "III", "IV", "V", "VI"]
    lines = [
        "## PAVE Scores",
        f"Pilot: {pave.pilot}/5  Factors: {pave.pilot_factors}",
        f"Aircraft: {pave.aircraft}/5  Factors: {pave.aircraft_factors}",
        f"Environment: {pave.environment}/5  Factors: {pave.environment_factors}",
        f"External: {pave.external}/5  Factors: {pave.external_factors}",
        "",
        "## SORA",
        f"iGRC: {sora.igrc}  ARC: {sora.arc_label.upper()}  SAIL: {sail_roman[sora.sail] if 1 <= sora.sail <= 6 else sora.sail}",
        "",
        "## Hard Stops Already Identified",
        "\n".join(f"- {h}" for h in hard_stops) if hard_stops else "None",
        "",
        "Return a JSON array of mitigations as specified in your system prompt.",
    ]
    return "\n".join(lines)


def _llm_mitigations(pave: PaveScore, sora: SoraScore, hard_stops: list[str]) -> list[dict]:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    msg = client.messages.create(
        model       = os.getenv("FRAT_MODEL", DEFAULT_MODEL),
        max_tokens  = MAX_TOKENS,
        temperature = TEMPERATURE,
        system      = _load_system_prompt(),
        messages    = [{"role": "user", "content": _build_user_message(pave, sora, hard_stops)}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def _rule_based_mitigations(pave: PaveScore, sora: SoraScore) -> list[dict]:
    mits = []

    def add(dim: str, factor: str, action: str, reduces_to: Optional[str] = None, hard: bool = False) -> None:
        mits.append({
            "dimension": dim, "risk_factor": factor,
            "action": action, "reduces_to": reduces_to, "is_hard_stop": hard,
        })

    for f in pave.pilot_factors:
        if "currency" in f.lower() and "lapsed" in f.lower():
            add("pilot", f, "Complete a self-reviewed currency flight before this mission to restore recency.", "MEDIUM")
        elif "night" in f.lower():
            add("pilot", f, "Do not conduct night operations until night currency is re-established.", None, hard=True)
        else:
            add("pilot", f, "Review and address before flight.", "LOW-MEDIUM")

    for f in pave.aircraft_factors:
        add("aircraft", f, "Inspect and verify before flight; document in maintenance log.", "LOW")

    for f in pave.environment_factors:
        if "wind" in f.lower() and "hard limit" in f.lower():
            add("environment", f, "Abort mission — wind exceeds 14 CFR 107.51 limit.", None, hard=True)
        elif "visibility" in f.lower() and "hard" in f.lower():
            add("environment", f, "Abort mission — visibility below 3 SM minimum (107.51).", None, hard=True)
        elif "tfr" in f.lower():
            add("environment", f, "Abort — active TFR. Verify at tfr.faa.gov and contact ATCT if appropriate.", None, hard=True)
        elif "laanc" in f.lower():
            add("environment", f, "Apply for Part 107.39 waiver or DrAW; do not exceed LAANC ceiling without authorization.", "MEDIUM")
        elif "mvfr" in f.lower():
            add("environment", f, "Monitor weather; hold launch until VFR conditions confirmed or reschedule.", "LOW")
        elif "notam" in f.lower():
            add("environment", f, "Review NOTAM text; adjust flight path or timing to avoid affected area.", "LOW-MEDIUM")
        else:
            add("environment", f, "Address before launch.", "LOW-MEDIUM")

    for f in pave.external_factors:
        add("external", f, "Formally brief stakeholders that safety requirements are non-negotiable; reschedule if pressure persists.", "LOW")

    if sora.sail >= 4:
        add("sora", f"SAIL {sora.sail} requires specific Operational Safety Objectives (OSOs)",
            "Document and satisfy applicable OSOs from JARUS SORA 2.5 Annex E before flight authorization.", "MEDIUM")

    return mits


def advise(pave: PaveScore, sora: SoraScore, hard_stops: list[str]) -> list[Mitigation]:
    try:
        raw = _llm_mitigations(pave, sora, hard_stops)
    except Exception:
        raw = _rule_based_mitigations(pave, sora)

    return [
        Mitigation(
            dimension    = m["dimension"],
            risk_factor  = m["risk_factor"],
            action       = m["action"],
            reduces_to   = m.get("reduces_to"),
            is_hard_stop = m.get("is_hard_stop", False),
        )
        for m in raw
    ]
