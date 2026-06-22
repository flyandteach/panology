"""Tests for pure-computation SORA 2.5 scorer."""
import pytest
from datetime import datetime

from frat_agent.models import MissionRequest, LaancData
from frat_agent.agents.sora_scorer import score, _dim_index, _compute_igrc, _compute_arc, _compute_sail


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


def _laanc(cls: str = "G", ceiling: int = 400) -> LaancData:
    return LaancData("1", ceiling, "Test Facility", cls)


class TestDimIndex:
    def test_sub_one_metre(self):
        assert _dim_index(0.3) == 0

    def test_one_to_three(self):
        assert _dim_index(1.5) == 1

    def test_exactly_three(self):
        # upper bound is exclusive at 3.0 → goes to next bucket
        assert _dim_index(3.0) == 2

    def test_large(self):
        assert _dim_index(50.0) == 5


class TestIGRC:
    def test_small_sparse(self):
        m = _mission(aircraft_dimension_m=0.5, population_density="sparse")
        igrc, _ = _compute_igrc(m)
        assert igrc == 2

    def test_small_populated(self):
        m = _mission(aircraft_dimension_m=0.5, population_density="populated")
        igrc, _ = _compute_igrc(m)
        assert igrc == 3

    def test_gathering_adds_one(self):
        m = _mission(aircraft_dimension_m=0.5, population_density="sparse", over_people=True)
        igrc, _ = _compute_igrc(m)
        # sparse index 0 = 2, over_people bumps +1 → 3
        assert igrc == 3

    def test_bvlos_adds_one(self):
        m = _mission(aircraft_dimension_m=0.5, population_density="sparse", operation_type="BVLOS")
        igrc_base, _ = _compute_igrc(_mission(aircraft_dimension_m=0.5, population_density="sparse"))
        igrc_bvlos, _ = _compute_igrc(m)
        assert igrc_bvlos == igrc_base + 1

    def test_max_capped_at_nine(self):
        m = _mission(aircraft_dimension_m=100.0, population_density="gathering", operation_type="BVLOS", over_people=True)
        igrc, _ = _compute_igrc(m)
        assert igrc == 9


class TestARC:
    def test_class_g_low_alt(self):
        arc, _ = _compute_arc(_mission(max_altitude_ft_agl=200), _laanc("G"))
        assert arc == 1  # ARC-a

    def test_class_g_high_alt(self):
        arc, _ = _compute_arc(_mission(max_altitude_ft_agl=500), _laanc("G"))
        assert arc == 2  # ARC-b

    def test_class_e_low(self):
        arc, _ = _compute_arc(_mission(max_altitude_ft_agl=200), _laanc("E"))
        assert arc == 2  # ARC-b

    def test_class_d(self):
        arc, _ = _compute_arc(_mission(max_altitude_ft_agl=200), _laanc("D"))
        assert arc == 3  # ARC-c

    def test_class_b(self):
        arc, _ = _compute_arc(_mission(max_altitude_ft_agl=200), _laanc("B"))
        assert arc == 4  # ARC-d

    def test_night_non_g_bumps_arc(self):
        m = _mission(max_altitude_ft_agl=200, is_night=True)
        arc_day, _ = _compute_arc(_mission(max_altitude_ft_agl=200, is_night=False), _laanc("E"))
        arc_night, _ = _compute_arc(m, _laanc("E"))
        assert arc_night == arc_day + 1


class TestSAIL:
    def test_igrc1_arca(self):
        assert _compute_sail(1, 1) == 1

    def test_igrc9_arcd(self):
        assert _compute_sail(9, 4) == 6

    def test_igrc5_arcb(self):
        assert _compute_sail(5, 2) == 4


class TestFullScore:
    def test_returns_sora_score_object(self):
        m = _mission()
        s = score(m, _laanc())
        assert 1 <= s.igrc <= 9
        assert 1 <= s.arc <= 4
        assert s.arc_label in ("a", "b", "c", "d")
        assert 1 <= s.sail <= 6
        assert s.igrc_rationale != ""
        assert s.arc_rationale != ""

    def test_low_risk_scenario(self):
        m = _mission(
            aircraft_dimension_m=0.3,
            population_density="sparse",
            operation_type="VLOS",
            max_altitude_ft_agl=100,
        )
        s = score(m, _laanc("G", 400))
        assert s.igrc <= 3
        assert s.arc <= 2
        assert s.sail <= 3
