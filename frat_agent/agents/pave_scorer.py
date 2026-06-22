"""
LLM-backed PAVE risk scorer.
Assembles all live data into a structured prompt and calls the Claude API.
Falls back to rule-based scoring when the LLM is unavailable.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional

from frat_agent.config import DEFAULT_MODEL, MAX_TOKENS, TEMPERATURE
from frat_agent.models import (
    MissionRequest, WeatherSnapshot, NotamItem, TfrItem, LaancData, PaveScore, SoraScore,
)


_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "pave_scorer.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_message(
    mission:  MissionRequest,
    weather:  Optional[WeatherSnapshot],
    notams:   list[NotamItem],
    tfrs:     list[TfrItem],
    laanc:    Optional[LaancData],
    sora:     SoraScore,
) -> str:
    tfr_intersecting = [t for t in tfrs if t.intersects_mission]
    notam_texts = [f"[{n.classification}] {n.text[:200]}" for n in notams[:10]]
    tfr_texts   = [
        f"{t.notam_id} ({t.name}): {t.min_alt_ft}–{t.max_alt_ft} ft, "
        f"valid {t.effective_start} → {t.effective_end}"
        for t in tfr_intersecting
    ]

    w = weather
    weather_block = (
        f"Station: {w.station}\n"
        f"Flight category: {w.flight_category}\n"
        f"Wind: {w.wind_dir_deg or '???'}°/{w.wind_speed_kt}kt"
          + (f" G{w.wind_gust_kt}kt" if w.wind_gust_kt else "") + "\n"
        f"Visibility: {w.visibility_sm} SM\n"
        f"Ceiling: {w.ceiling_ft or 'Clear'} ft\n"
        f"METAR: {w.raw_metar}\n"
        f"TAF summary: {w.taf_summary}"
    ) if w else "Weather data unavailable"

    laanc_block = (
        f"Facility: {laanc.facility_name}\n"
        f"Airspace class: {laanc.airspace_class}\n"
        f"LAANC authorized ceiling: {laanc.authorized_ceiling_ft} ft AGL\n"
        f"Requested altitude: {mission.max_altitude_ft_agl} ft AGL"
    ) if laanc else "LAANC data unavailable"

    sail_roman = ["", "I", "II", "III", "IV", "V", "VI"]
    sora_block = (
        f"iGRC: {sora.igrc} ({sora.igrc_rationale})\n"
        f"ARC: {sora.arc_label.upper()} ({sora.arc_rationale})\n"
        f"SAIL: {sail_roman[sora.sail] if 1 <= sora.sail <= 6 else sora.sail}"
    )

    return f"""## Mission Parameters

Location: {mission.location_name} ({mission.lat}, {mission.lon})
Planned window: {mission.planned_start.isoformat()} → {mission.planned_end.isoformat()}
Max altitude: {mission.max_altitude_ft_agl} ft AGL
Operation type: {mission.operation_type}
Population density: {mission.population_density}
Over people: {mission.over_people}
Over moving vehicles: {mission.over_moving_vehicles}
Night operation: {mission.is_night}

## Aircraft
Make/model: {mission.aircraft_make_model}
Weight: {mission.aircraft_weight_lbs} lbs
Characteristic dimension: {mission.aircraft_dimension_m} m
Max speed: {mission.aircraft_max_speed_ms} m/s

## Pilot
Name: {mission.pilot_name}
Certificate: {mission.pilot_certificate}
Total hours: {mission.pilot_total_hours}
Days since last flight (currency): {mission.pilot_currency_days}
Night current: {mission.pilot_night_current}

## External Pressures (1=none, 5=extreme)
Schedule pressure: {mission.schedule_pressure}
Client pressure: {mission.client_pressure}
Financial pressure: {mission.financial_pressure}

## Weather
{weather_block}

## LAANC / Airspace
{laanc_block}

## Active NOTAMs ({len(notams)} total)
{chr(10).join(notam_texts) if notam_texts else "None"}

## TFRs Intersecting Mission Area ({len(tfr_intersecting)})
{chr(10).join(tfr_texts) if tfr_texts else "None"}

## SORA Pre-Computation
{sora_block}

## Notes from operator
{mission.notes or "None"}

---
Score each PAVE dimension 1–5 and return JSON as specified in your system prompt.
"""


def _llm_score(user_message: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    msg = client.messages.create(
        model       = os.getenv("FRAT_MODEL", DEFAULT_MODEL),
        max_tokens  = MAX_TOKENS,
        temperature = TEMPERATURE,
        system      = _load_system_prompt(),
        messages    = [{"role": "user", "content": user_message}],
    )
    raw = msg.content[0].text.strip()
    # Strip any accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def _rule_based_score(
    mission:  MissionRequest,
    weather:  Optional[WeatherSnapshot],
    notams:   list[NotamItem],
    tfrs:     list[TfrItem],
    laanc:    Optional[LaancData],
) -> dict:
    """Deterministic fallback — no LLM."""
    # ── Pilot ──────────────────────────────────────────────────────────────
    p_score = 1
    p_factors = []
    if mission.pilot_currency_days > 90:
        p_score = max(p_score, 4)
        p_factors.append(f"Currency lapsed — {mission.pilot_currency_days} days since last flight (>90)")
    elif mission.pilot_currency_days > 30:
        p_score = max(p_score, 2)
        p_factors.append(f"Currency aging — {mission.pilot_currency_days} days since last flight")
    if mission.is_night and not mission.pilot_night_current:
        p_score = max(p_score, 4)
        p_factors.append("Night operation but pilot not night current")
    if mission.pilot_total_hours < 10:
        p_score = max(p_score, 3)
        p_factors.append(f"Low total UAS hours: {mission.pilot_total_hours}")

    # ── Aircraft ───────────────────────────────────────────────────────────
    a_score = 1
    a_factors = []
    if mission.is_night and mission.aircraft_weight_lbs < 0.55:
        a_factors.append("Micro UAS — verify anti-collision lighting for night ops")
        a_score = max(a_score, 2)

    # ── Environment ────────────────────────────────────────────────────────
    e_score = 1
    e_factors = []
    if weather:
        if weather.wind_speed_kt >= 23:
            e_score = 5
            e_factors.append(f"Wind {weather.wind_speed_kt} kt ≥ hard limit of 23 kt (107.51)")
        elif weather.wind_speed_kt >= 18:
            e_score = max(e_score, 3)
            e_factors.append(f"Wind {weather.wind_speed_kt} kt approaching 23 kt limit")
        if weather.wind_gust_kt and weather.wind_gust_kt >= 30:
            e_score = 5
            e_factors.append(f"Gust {weather.wind_gust_kt} kt ≥ hard-limit threshold of 30 kt")
        if weather.visibility_sm is not None and weather.visibility_sm < 3.0:
            e_score = 5
            e_factors.append(f"Visibility {weather.visibility_sm} SM < 3 SM minimum (107.51)")
        if weather.flight_category in ("IFR", "LIFR"):
            e_score = max(e_score, 4)
            e_factors.append(f"Flight category {weather.flight_category} — instrument conditions")
        elif weather.flight_category == "MVFR":
            e_score = max(e_score, 3)
            e_factors.append("MVFR conditions")

    if laanc and mission.max_altitude_ft_agl > laanc.authorized_ceiling_ft > 0:
        e_score = max(e_score, 4)
        e_factors.append(
            f"Requested altitude {mission.max_altitude_ft_agl} ft exceeds LAANC ceiling "
            f"{laanc.authorized_ceiling_ft} ft"
        )

    for t in tfrs:
        if t.intersects_mission:
            e_score = 5
            e_factors.append(f"Active TFR {t.notam_id} ({t.name}) intersects mission area")

    for n in notams:
        if n.classification in ("TFR", "AIRSPACE"):
            e_score = max(e_score, 3)
            e_factors.append(f"Active {n.classification} NOTAM: {n.text[:100]}")

    # ── External ───────────────────────────────────────────────────────────
    ext_score = 1
    ext_factors = []
    max_pressure = max(mission.schedule_pressure, mission.client_pressure, mission.financial_pressure)
    if max_pressure >= 4:
        ext_score = 3
        ext_factors.append(f"High external pressure (max rating: {max_pressure}/5)")
    elif max_pressure >= 3:
        ext_score = 2
        ext_factors.append(f"Moderate external pressure (max rating: {max_pressure}/5)")

    avg = (p_score + a_score + e_score + ext_score) / 4
    return {
        "pilot":              p_score,
        "aircraft":           a_score,
        "environment":        e_score,
        "external":           ext_score,
        "pilot_factors":      p_factors,
        "aircraft_factors":   a_factors,
        "environment_factors":e_factors,
        "external_factors":   ext_factors,
        "narrative": (
            f"Rule-based fallback assessment (LLM unavailable). "
            f"Average PAVE score: {avg:.1f}/5. "
            f"{'Hard stops identified — do not fly.' if max(p_score, a_score, e_score, ext_score) == 5 else 'Review highlighted factors before flight.'}"
        ),
    }


def score(
    mission:  MissionRequest,
    weather:  Optional[WeatherSnapshot],
    notams:   list[NotamItem],
    tfrs:     list[TfrItem],
    laanc:    Optional[LaancData],
    sora:     SoraScore,
) -> PaveScore:
    user_msg = _build_user_message(mission, weather, notams, tfrs, laanc, sora)
    try:
        d = _llm_score(user_msg)
    except Exception:
        d = _rule_based_score(mission, weather, notams, tfrs, laanc)

    scores = [d["pilot"], d["aircraft"], d["environment"], d["external"]]
    return PaveScore(
        pilot              = d["pilot"],
        aircraft           = d["aircraft"],
        environment        = d["environment"],
        external           = d["external"],
        average            = sum(scores) / len(scores),
        pilot_factors      = d.get("pilot_factors", []),
        aircraft_factors   = d.get("aircraft_factors", []),
        environment_factors= d.get("environment_factors", []),
        external_factors   = d.get("external_factors", []),
        narrative          = d.get("narrative", ""),
    )
