"""
Fetch METAR and TAF from aviationweather.gov REST API (post-Sept-2025 schema).
Falls back to a mock response when the API is unreachable or no key is configured.
"""
from __future__ import annotations
import os
from typing import Optional

import requests

from frat_agent.config import WEATHER_API_BASE
from frat_agent.models import WeatherSnapshot


_TIMEOUT = 10


def _get_metar(station: str) -> Optional[dict]:
    url = f"{WEATHER_API_BASE}/metar"
    params = {"ids": station, "format": "json", "taf": "false"}
    r = requests.get(url, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data[0] if data else None


def _get_taf(station: str) -> Optional[dict]:
    url = f"{WEATHER_API_BASE}/taf"
    params = {"ids": station, "format": "json"}
    r = requests.get(url, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data[0] if data else None


def _flight_category(vis_sm: Optional[float], ceiling_ft: Optional[int]) -> str:
    if vis_sm is None and ceiling_ft is None:
        return "UNKNOWN"
    vis_sm    = vis_sm or 10.0
    ceil_ft   = ceiling_ft or 9999
    if vis_sm < 1 or ceil_ft < 500:
        return "LIFR"
    if vis_sm < 3 or ceil_ft < 1000:
        return "IFR"
    if vis_sm <= 5 or ceil_ft <= 3000:
        return "MVFR"
    return "VFR"


def _ceiling_from_sky(sky_condition: list[dict]) -> Optional[int]:
    for layer in sky_condition:
        cover = layer.get("skyCover", "")
        if cover in ("BKN", "OVC", "OVX"):
            return layer.get("cloudBase")
    return None


def _parse_metar(raw: dict) -> dict:
    sky  = raw.get("skyCondition", [])
    ceil = _ceiling_from_sky(sky)
    vis  = raw.get("visibility")
    try:
        vis = float(vis) if vis is not None else None
    except (TypeError, ValueError):
        vis = None
    return {
        "station":        raw.get("stationId", "????"),
        "wind_dir_deg":   raw.get("wdir"),
        "wind_speed_kt":  int(raw.get("wspd") or 0),
        "wind_gust_kt":   int(raw.get("wgst")) if raw.get("wgst") else None,
        "visibility_sm":  vis,
        "ceiling_ft":     ceil,
        "temp_c":         raw.get("temp"),
        "raw_metar":      raw.get("rawOb", ""),
        "flight_category":_flight_category(vis, ceil),
    }


def _taf_summary(raw: dict) -> str:
    forecasts = raw.get("forecast", [])
    lines = []
    for f in forecasts[:4]:
        change_type = f.get("changeType", "")
        time_from   = f.get("fcstTimeFrom", "")
        wspd        = f.get("wspd")
        wgst        = f.get("wgst")
        vis         = f.get("visibility")
        sky         = f.get("skyCondition", [])
        ceil        = _ceiling_from_sky(sky)
        line = f"{change_type} {time_from}: wind {wspd}kt"
        if wgst:
            line += f" G{wgst}kt"
        if vis:
            line += f", vis {vis}SM"
        if ceil:
            line += f", ceil {ceil}ft"
        lines.append(line.strip())
    return " | ".join(lines) if lines else "No TAF forecast available"


def fetch_weather(station: str) -> tuple[Optional[WeatherSnapshot], Optional[str]]:
    """
    Returns (WeatherSnapshot, warning_string).
    warning_string is None on success, error description on failure.
    """
    try:
        metar_raw = _get_metar(station)
        taf_raw   = _get_taf(station)

        if not metar_raw:
            return _mock_weather(station), f"No METAR data returned for {station}; using mock"

        parsed = _parse_metar(metar_raw)
        taf_str = _taf_summary(taf_raw) if taf_raw else "TAF unavailable"

        snap = WeatherSnapshot(
            station          = parsed["station"],
            flight_category  = parsed["flight_category"],
            wind_dir_deg     = parsed["wind_dir_deg"],
            wind_speed_kt    = parsed["wind_speed_kt"],
            wind_gust_kt     = parsed["wind_gust_kt"],
            visibility_sm    = parsed["visibility_sm"],
            ceiling_ft       = parsed["ceiling_ft"],
            temp_c           = parsed["temp_c"],
            raw_metar        = parsed["raw_metar"],
            taf_summary      = taf_str,
        )
        return snap, None

    except Exception as exc:
        return _mock_weather(station), f"Weather API error for {station}: {exc}"


# ── Mock (used when API is unreachable) ───────────────────────────────────────

def _mock_weather(station: str) -> WeatherSnapshot:
    return WeatherSnapshot(
        station         = station,
        flight_category = "VFR",
        wind_dir_deg    = 270,
        wind_speed_kt   = 8,
        wind_gust_kt    = None,
        visibility_sm   = 10.0,
        ceiling_ft      = None,
        temp_c          = 15.0,
        raw_metar       = f"MOCK {station} AUTO 08/15 270/08KT 10SM SKC",
        taf_summary     = "MOCK TAF: VFR conditions expected throughout period",
    )
