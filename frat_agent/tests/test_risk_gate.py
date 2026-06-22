"""Tests for risk_gate hard-stop detection and verdict logic."""
import pytest
from datetime import datetime

from frat_agent.models import (
    MissionRequest, WeatherSnapshot, TfrItem, LaancData, PaveScore, SoraScore,
)
from frat_agent.agents.risk_gate import _hard_stops, _verdict, evaluate


def _mission(**overrides) -> MissionRequest:
    defaults = dict(
        lat=47.6, lon=-122.3, location_name="Test", nearest_airport_icao="KSEA",
        planned_start=datetime(2026, 6, 22, 14, 0),
        planned_end=datetime(2026, 6, 22, 16, 0),
        max_altitude_ft_agl=200,
        operation_type="VLOS",
        population_density="populated",
        aircraft_dimension_m=0.28,
        aircraft_max_speed_ms=19.0,
        aircraft_weight_lbs=2.0,
    )
    defaults.update(overrides)
    return MissionRequest(**defaults)


def _weather(**kw) -> WeatherSnapshot:
    defaults = dict(
        station="KSEA", flight_category="VFR",
        wind_dir_deg=270, wind_speed_kt=8, wind_gust_kt=None,
        visibility_sm=10.0, ceiling_ft=None, temp_c=15.0,
        raw_metar="MOCK", taf_summary="MOCK",
    )
    defaults.update(kw)
    return WeatherSnapshot(**defaults)


def _pave(pilot=1, aircraft=1, environment=1, external=1) -> PaveScore:
    return PaveScore(
        pilot=pilot, aircraft=aircraft, environment=environment, external=external,
        average=(pilot + aircraft + environment + external) / 4,
    )


def _sora(igrc=2, arc=1, sail=1) -> SoraScore:
    return SoraScore(igrc=igrc, arc=arc, arc_label="a", sail=sail)


class TestHardStops:
    def test_no_stops_nominal(self):
        stops = _hard_stops(_mission(), _weather(), [], LaancData("1", 400, "F", "G"), _pave())
        assert stops == []

    def test_wind_over_limit(self):
        stops = _hard_stops(_mission(), _weather(wind_speed_kt=24), [], None, _pave())
        assert any("23 kt" in s for s in stops)

    def test_gust_over_limit(self):
        stops = _hard_stops(_mission(), _weather(wind_gust_kt=31), [], None, _pave())
        assert any("30 kt" in s for s in stops)

    def test_visibility_below_limit(self):
        stops = _hard_stops(_mission(), _weather(visibility_sm=2.5), [], None, _pave())
        assert any("3 SM" in s for s in stops)

    def test_lifr_is_stop(self):
        stops = _hard_stops(_mission(), _weather(flight_category="LIFR"), [], None, _pave())
        assert any("LIFR" in s for s in stops)

    def test_tfr_intersection(self):
        tfr = TfrItem("T1", "VIP TFR", "", "", 0, 3000, 47.6, -122.3, 5.0, intersects_mission=True)
        stops = _hard_stops(_mission(), _weather(), [tfr], None, _pave())
        assert any("TFR" in s for s in stops)

    def test_tfr_no_intersection_not_stop(self):
        tfr = TfrItem("T1", "Distant TFR", "", "", 0, 3000, 40.0, -100.0, 5.0, intersects_mission=False)
        stops = _hard_stops(_mission(), _weather(), [tfr], None, _pave())
        assert not any("TFR" in s for s in stops)

    def test_laanc_exceeded(self):
        laanc = LaancData("1", 100, "F", "D")
        stops = _hard_stops(_mission(max_altitude_ft_agl=200), _weather(), [], laanc, _pave())
        assert any("LAANC" in s or "ceiling" in s for s in stops)

    def test_laanc_zero_not_stop(self):
        # ceiling=0 means not in LAANC-enabled area — no hard stop from altitude check
        laanc = LaancData("1", 0, "F", "G")
        stops = _hard_stops(_mission(max_altitude_ft_agl=400), _weather(), [], laanc, _pave())
        assert not any("LAANC" in s for s in stops)

    def test_bvlos_without_waiver(self):
        stops = _hard_stops(_mission(operation_type="BVLOS"), _weather(), [], None, _pave())
        assert any("BVLOS" in s for s in stops)

    def test_pave_critical_dimension(self):
        stops = _hard_stops(_mission(), _weather(), [], None, _pave(environment=5))
        assert any("Environment" in s for s in stops)


class TestVerdict:
    def test_go_low_risk(self):
        assert _verdict(_pave(1, 1, 1, 1), [], _sora(sail=1)) == "GO"

    def test_no_go_hard_stops(self):
        assert _verdict(_pave(1, 1, 1, 1), ["stop"], _sora(sail=1)) == "NO_GO"

    def test_proceed_medium_pave(self):
        # average = (2+3+3+3)/4 = 2.75 → above GO threshold (2.5), below NO_GO (3.5)
        v = _verdict(_pave(2, 3, 3, 3), [], _sora(sail=2))
        assert v == "PROCEED_WITH_MITIGATIONS"

    def test_no_go_high_pave_average(self):
        v = _verdict(_pave(4, 4, 4, 4), [], _sora(sail=2))
        assert v == "NO_GO"

    def test_no_go_high_sail(self):
        v = _verdict(_pave(1, 1, 2, 1), [], _sora(sail=5))
        assert v == "NO_GO"


class TestEvaluate:
    def test_returns_report(self):
        m = _mission()
        w = _weather()
        p = _pave()
        s = _sora()
        r = evaluate(m, w, [], [], LaancData("1", 400, "F", "G"), p, s, [], [])
        assert r.verdict in ("GO", "PROCEED_WITH_MITIGATIONS", "NO_GO")
        assert r.report_id != ""
        assert r.generated_at != ""

    def test_no_go_on_wind_hard_stop(self):
        r = evaluate(
            _mission(), _weather(wind_speed_kt=25),
            [], [], None, _pave(), _sora(), [], [],
        )
        assert r.verdict == "NO_GO"
        assert len(r.hard_stops) > 0
