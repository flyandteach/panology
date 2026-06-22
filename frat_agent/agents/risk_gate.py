"""
Risk gate — aggregates PAVE + SORA + live data checks into a final verdict.
Pure computation; no LLM call.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from frat_agent.config import (
    WIND_HARD_LIMIT_KT, GUST_HARD_LIMIT_KT, VIS_HARD_LIMIT_SM,
    CEILING_CAUTION_FT, PAVE_GO_THRESHOLD, PAVE_CAUTION_THRESHOLD,
    VERDICT_LABELS,
)
from frat_agent.models import (
    MissionRequest, WeatherSnapshot, NotamItem, TfrItem, LaancData,
    PaveScore, SoraScore, Mitigation, RiskReport,
)


def _hard_stops(
    mission:  MissionRequest,
    weather:  Optional[WeatherSnapshot],
    tfrs:     list[TfrItem],
    laanc:    Optional[LaancData],
    pave:     PaveScore,
) -> list[str]:
    stops = []

    # ── Regulatory hard limits (Part 107) ────────────────────────────────────
    if weather:
        if weather.wind_speed_kt >= WIND_HARD_LIMIT_KT:
            stops.append(
                f"Wind {weather.wind_speed_kt} kt ≥ 23 kt hard limit (14 CFR 107.51(a)); "
                "operation not permitted without waiver"
            )
        if weather.wind_gust_kt and weather.wind_gust_kt >= GUST_HARD_LIMIT_KT:
            stops.append(
                f"Gust {weather.wind_gust_kt} kt ≥ 30 kt operational threshold; "
                "abort and reassess"
            )
        if weather.visibility_sm is not None and weather.visibility_sm < VIS_HARD_LIMIT_SM:
            stops.append(
                f"Visibility {weather.visibility_sm} SM < 3 SM minimum (14 CFR 107.51(b)); "
                "operation not permitted"
            )
        if weather.flight_category == "LIFR":
            stops.append(
                "LIFR conditions — IFR environment; Part 107 VLOS operations not permitted"
            )

    # ── TFR intersection ─────────────────────────────────────────────────────
    for t in tfrs:
        if t.intersects_mission:
            stops.append(
                f"Active TFR '{t.name}' ({t.notam_id}) intersects mission area — "
                "flight prohibited without explicit ATC authorization"
            )

    # ── LAANC ceiling exceeded ────────────────────────────────────────────────
    if laanc and laanc.authorized_ceiling_ft > 0:
        if mission.max_altitude_ft_agl > laanc.authorized_ceiling_ft:
            stops.append(
                f"Requested altitude {mission.max_altitude_ft_agl} ft AGL exceeds "
                f"LAANC ceiling {laanc.authorized_ceiling_ft} ft — "
                "waiver (DrAW or Part 107.39) required"
            )

    # ── Night without night waiver hint ──────────────────────────────────────
    if mission.is_night and not mission.pilot_night_current:
        stops.append(
            "Night operation planned but pilot is not night current — "
            "complete night currency requirements before flight"
        )

    # ── BVLOS without certification ───────────────────────────────────────────
    if mission.is_bvlos and mission.pilot_certificate == "Part 107":
        stops.append(
            "BVLOS operation requires a Part 107.31 waiver or Part 108 authorization "
            "— standard Part 107 certificate does not authorize BVLOS"
        )

    # ── Any PAVE dimension at CRITICAL ───────────────────────────────────────
    if pave.pilot == 5:
        stops.append("Pilot PAVE dimension scored CRITICAL (5/5)")
    if pave.aircraft == 5:
        stops.append("Aircraft PAVE dimension scored CRITICAL (5/5)")
    if pave.environment == 5:
        stops.append("Environment PAVE dimension scored CRITICAL (5/5)")
    if pave.external == 5:
        stops.append("External PAVE dimension scored CRITICAL (5/5)")

    return stops


def _verdict(pave: PaveScore, stops: list[str], sora: SoraScore) -> str:
    if stops:
        return "NO_GO"
    if pave.average <= PAVE_GO_THRESHOLD and sora.sail <= 2:
        return "GO"
    if pave.average <= PAVE_CAUTION_THRESHOLD and sora.sail <= 4:
        return "PROCEED_WITH_MITIGATIONS"
    if pave.average > PAVE_CAUTION_THRESHOLD or sora.sail >= 5:
        return "NO_GO"
    return "PROCEED_WITH_MITIGATIONS"


def evaluate(
    mission:       MissionRequest,
    weather:       Optional[WeatherSnapshot],
    notams:        list[NotamItem],
    tfrs:          list[TfrItem],
    laanc:         Optional[LaancData],
    pave:          PaveScore,
    sora:          SoraScore,
    mitigations:   list[Mitigation],
    data_warnings: list[str],
) -> RiskReport:
    stops   = _hard_stops(mission, weather, tfrs, laanc, pave)
    verdict = _verdict(pave, stops, sora)

    report_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + str(uuid.uuid4())[:8].upper()

    return RiskReport(
        report_id      = report_id,
        generated_at   = datetime.now(timezone.utc).isoformat(),
        verdict        = verdict,
        verdict_label  = VERDICT_LABELS[verdict],
        mission        = mission.to_dict(),
        weather        = weather,
        notams         = notams,
        tfrs           = tfrs,
        laanc          = laanc,
        pave           = pave,
        sora           = sora,
        mitigations    = mitigations,
        hard_stops     = stops,
        data_warnings  = data_warnings,
    )
