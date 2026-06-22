"""
Top-level orchestrator.  Runs the full FRAT pipeline for a given MissionRequest
and returns a completed, saved RiskReport.
"""
from __future__ import annotations
from typing import Optional

from frat_agent.models import MissionRequest, RiskReport
from frat_agent.data.weather import fetch_weather
from frat_agent.data.notam import fetch_notams
from frat_agent.data.tfr import fetch_tfrs
from frat_agent.data.laanc import fetch_laanc
from frat_agent.agents import pave_scorer, sora_scorer, mitigation_advisor, risk_gate
from frat_agent.utils.audit_log import write_record
from frat_agent.utils.export import export_json, export_text


def assess(mission: MissionRequest, save: bool = True) -> RiskReport:
    """
    Run a complete FRAT assessment.

    Steps:
      1. Fetch live weather, NOTAMs, TFRs, LAANC ceiling (parallel where possible)
      2. Compute SORA iGRC / ARC / SAIL (pure computation)
      3. Score PAVE dimensions (LLM with rule-based fallback)
      4. Generate mitigations (LLM with rule-based fallback)
      5. Run risk gate → verdict
      6. Write audit record + export report files

    Returns the completed RiskReport.
    """
    warnings: list[str] = []

    # ── Step 1: Data fetch ────────────────────────────────────────────────────
    weather, w_warn = fetch_weather(mission.nearest_airport_icao)
    if w_warn:
        warnings.append(w_warn)

    notams, n_warn = fetch_notams(mission.lat, mission.lon)
    if n_warn:
        warnings.append(n_warn)

    tfrs, t_warn = fetch_tfrs(mission.lat, mission.lon)
    if t_warn:
        warnings.append(t_warn)

    laanc, l_warn = fetch_laanc(mission.lat, mission.lon)
    if l_warn:
        warnings.append(l_warn)

    # ── Step 2: SORA (pure computation) ──────────────────────────────────────
    sora = sora_scorer.score(mission, laanc)

    # ── Step 3: PAVE scoring (LLM) ────────────────────────────────────────────
    pave = pave_scorer.score(mission, weather, notams, tfrs, laanc, sora)

    # ── Step 4: Mitigations (LLM) ────────────────────────────────────────────
    # Pre-compute hard stops so the LLM has them for context
    prelim_report = risk_gate.evaluate(
        mission, weather, notams, tfrs, laanc, pave, sora, [], warnings
    )
    mits = mitigation_advisor.advise(pave, sora, prelim_report.hard_stops)

    # ── Step 5: Final risk gate ───────────────────────────────────────────────
    report = risk_gate.evaluate(
        mission, weather, notams, tfrs, laanc, pave, sora, mits, warnings
    )

    # ── Step 6: Persist ───────────────────────────────────────────────────────
    if save:
        write_record(report)
        export_json(report)
        export_text(report)

    return report
