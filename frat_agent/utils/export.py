"""
Export a RiskReport as:
  • JSON file  (machine-readable audit record)
  • TXT file   (human-readable formatted report)
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from frat_agent.config import PAVE_RISK_LABELS, VERDICT_LABELS
from frat_agent.models import RiskReport


_REPORTS_DIR = Path(__file__).parent.parent / "reports"


def _ensure_dir() -> None:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def export_json(report: RiskReport, path: Path | None = None) -> Path:
    _ensure_dir()
    path = path or (_REPORTS_DIR / f"{report.report_id}.json")
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path


def export_text(report: RiskReport, path: Path | None = None) -> Path:
    _ensure_dir()
    path = path or (_REPORTS_DIR / f"{report.report_id}.txt")
    path.write_text(_render(report), encoding="utf-8")
    return path


def _render(r: RiskReport) -> str:
    sep  = "=" * 70
    dash = "-" * 70
    lines = [
        sep,
        "  FRAT-AS-A-SERVICE — FLIGHT RISK ASSESSMENT REPORT",
        sep,
        f"  Report ID  : {r.report_id}",
        f"  Generated  : {r.generated_at}",
        f"  Pilot      : {r.mission.get('pilot_name', 'N/A')}",
        f"  Location   : {r.mission.get('location_name', 'N/A')}",
        f"             : {r.mission.get('lat')}, {r.mission.get('lon')}",
        f"  Planned    : {r.mission.get('planned_start')} → {r.mission.get('planned_end')}",
        f"  Altitude   : {r.mission.get('max_altitude_ft_agl')} ft AGL",
        f"  Operation  : {r.mission.get('operation_type')} — {r.mission.get('aircraft_make_model')}",
        "",
        sep,
        f"  VERDICT: {r.verdict_label}",
        sep,
        "",
    ]

    if r.hard_stops:
        lines += ["  ⛔  HARD STOPS (must be resolved before flight):", ""]
        for hs in r.hard_stops:
            lines.append(f"    • {hs}")
        lines.append("")

    # ── Weather ──────────────────────────────────────────────────────────────
    lines += [dash, "  WEATHER", dash]
    if r.weather:
        w = r.weather
        lines += [
            f"  Station        : {w.station}",
            f"  Flight Category: {w.flight_category}",
            f"  Wind           : {w.wind_dir_deg or '---'}° / {w.wind_speed_kt} kt"
              + (f" G{w.wind_gust_kt}kt" if w.wind_gust_kt else ""),
            f"  Visibility     : {w.visibility_sm or 'N/A'} SM",
            f"  Ceiling        : {w.ceiling_ft or 'Clear'} ft",
            f"  Raw METAR      : {w.raw_metar}",
            f"  TAF            : {w.taf_summary}",
        ]
    else:
        lines.append("  Weather data unavailable")
    lines.append("")

    # ── NOTAM summary ─────────────────────────────────────────────────────────
    lines += [dash, f"  NOTAMs ({len(r.notams)} within search radius)", dash]
    for n in r.notams:
        lines.append(f"  [{n.classification}] {n.notam_id}: {n.text[:120]}")
    if not r.notams:
        lines.append("  No NOTAMs fetched")
    lines.append("")

    # ── TFR summary ───────────────────────────────────────────────────────────
    lines += [dash, f"  TFRs ({len(r.tfrs)} retrieved)", dash]
    for t in r.tfrs:
        intersect_str = "⚠ INTERSECTS MISSION AREA" if t.intersects_mission else "Outside area"
        lines.append(f"  {t.notam_id}: {t.name}  [{intersect_str}]")
        lines.append(f"    Alt: {t.min_alt_ft}–{t.max_alt_ft} ft  |  {t.effective_start} → {t.effective_end}")
    if not r.tfrs:
        lines.append("  No TFRs retrieved")
    lines.append("")

    # ── LAANC ─────────────────────────────────────────────────────────────────
    lines += [dash, "  LAANC / UAS FACILITY MAP", dash]
    if r.laanc:
        lines += [
            f"  Facility    : {r.laanc.facility_name}",
            f"  Airspace    : Class {r.laanc.airspace_class}",
            f"  LAANC Ceil  : {r.laanc.authorized_ceiling_ft} ft AGL",
            f"  Requested   : {r.mission.get('max_altitude_ft_agl')} ft AGL",
        ]
        if (r.mission.get("max_altitude_ft_agl") or 0) > r.laanc.authorized_ceiling_ft:
            lines.append("  ⚠  Requested altitude EXCEEDS LAANC ceiling — waiver/DrAW required")
    else:
        lines.append("  LAANC data unavailable")
    lines.append("")

    # ── PAVE ──────────────────────────────────────────────────────────────────
    lines += [dash, "  PAVE RISK ASSESSMENT", dash]
    p = r.pave
    lines += [
        f"  Pilot       : {p.pilot}/5  ({PAVE_RISK_LABELS.get(p.pilot, '?')})",
        f"  Aircraft    : {p.aircraft}/5  ({PAVE_RISK_LABELS.get(p.aircraft, '?')})",
        f"  Environment : {p.environment}/5  ({PAVE_RISK_LABELS.get(p.environment, '?')})",
        f"  External    : {p.external}/5  ({PAVE_RISK_LABELS.get(p.external, '?')})",
        f"  Average     : {p.average:.1f}/5",
        "",
        "  Narrative:",
    ]
    for para in (p.narrative or "").split("\n"):
        if para.strip():
            lines.append(f"  {para.strip()}")
    lines.append("")
    for dim, factors in [
        ("Pilot", p.pilot_factors),
        ("Aircraft", p.aircraft_factors),
        ("Environment", p.environment_factors),
        ("External", p.external_factors),
    ]:
        if factors:
            lines.append(f"  {dim} risk factors:")
            for f_ in factors:
                lines.append(f"    • {f_}")
    lines.append("")

    # ── SORA ──────────────────────────────────────────────────────────────────
    lines += [dash, "  SORA 2.5 SCORING", dash]
    s = r.sora
    sail_roman = ["", "I", "II", "III", "IV", "V", "VI"]
    lines += [
        f"  iGRC   : {s.igrc}  — {s.igrc_rationale}",
        f"  ARC    : {s.arc_label.upper()}  — {s.arc_rationale}",
        f"  SAIL   : {sail_roman[s.sail] if 1 <= s.sail <= 6 else s.sail}",
    ]
    lines.append("")

    # ── Mitigations ───────────────────────────────────────────────────────────
    lines += [dash, "  REQUIRED MITIGATIONS", dash]
    if r.mitigations:
        for m in r.mitigations:
            stop_tag = " ⛔ HARD STOP" if m.is_hard_stop else ""
            lines.append(f"  [{m.dimension.upper()}]{stop_tag} {m.risk_factor}")
            lines.append(f"    → {m.action}")
            if m.reduces_to:
                lines.append(f"    → Risk reduces to: {m.reduces_to}")
    else:
        lines.append("  No mitigations required")
    lines.append("")

    # ── Data warnings ─────────────────────────────────────────────────────────
    if r.data_warnings:
        lines += [dash, "  DATA QUALITY WARNINGS", dash]
        for w in r.data_warnings:
            lines.append(f"  ⚠ {w}")
        lines.append("")

    lines += [
        dash,
        "  DISCLAIMER: This report is decision support only, not an FAA authorization.",
        "  The pilot-in-command retains sole responsibility under 14 CFR 107.49.",
        sep,
    ]
    return "\n".join(lines)
