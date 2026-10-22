import math

import pytest

from hub import HubInputs, compare_with_baseline, evaluate
from hub.capacity import erlang_c, mean_trip_distance_km, mean_wait_s, pads_required, size_capacity
from hub.fire import assess_fire
from hub.layout import plan_layout
from hub.models import AircraftProfile, DemandProfile, DesignRequirements
from hub.noise import barrier_attenuation_db, combine_sources, distance_to_level, level_at_distance


def test_mean_trip_distance_is_two_thirds_radius():
    assert mean_trip_distance_km(9) == pytest.approx(6)


def test_erlang_c_single_server_equals_utilisation():
    # For M/M/1 the probability of waiting is rho.
    assert erlang_c(1, 0.6) == pytest.approx(0.6)


def test_erlang_c_known_value():
    # Textbook value: c = 2, a = 1 Erlang -> P(wait) = 1/3.
    assert erlang_c(2, 1.0) == pytest.approx(1 / 3)


def test_mean_wait_unstable_is_infinite():
    assert math.isinf(mean_wait_s(1, 1 / 10, 20))


def test_pads_required_meets_target():
    lam, svc = 60 / 3600, 40.0
    c = pads_required(lam, svc, target_wait_s=5, max_util=0.7)
    assert mean_wait_s(c, lam, svc) <= 5
    assert lam * svc / c <= 0.7


def test_on_pad_turnaround_needs_more_pad_time():
    ac, dm = AircraftProfile(), DemandProfile(peak_orders_per_hour=60)
    off = size_capacity(ac, dm, DesignRequirements(turnaround_on_pad=False))
    on = size_capacity(ac, dm, DesignRequirements(turnaround_on_pad=True))
    assert on.pad_events_per_hour * on.pad_service_s > off.pad_events_per_hour * off.pad_service_s
    assert on.pads_required >= off.pads_required


def test_onboard_charging_grows_fleet():
    dm = DemandProfile()
    swap = size_capacity(AircraftProfile(battery_mode="swap"), dm, DesignRequirements())
    onboard = size_capacity(AircraftProfile(battery_mode="onboard"), dm, DesignRequirements())
    assert onboard.aircraft_required > swap.aircraft_required


def test_bad_battery_mode():
    with pytest.raises(ValueError):
        size_capacity(AircraftProfile(battery_mode="nuclear"), DemandProfile(), DesignRequirements())


def test_inverse_square_spreading():
    assert level_at_distance(70, 10, 20) == pytest.approx(70 - 6.02, abs=0.01)
    assert distance_to_level(70, 10, 50) == pytest.approx(100)
    assert combine_sources(60, 2) == pytest.approx(63.01, abs=0.01)


def test_barrier_below_line_of_sight_does_nothing():
    assert barrier_attenuation_db(5, 100, 1.0, 3.0, 3.0, 500) == 0.0


def test_barrier_attenuation_capped():
    assert barrier_attenuation_db(1, 1, 50, 0, 0, 4000) == 20.0


def test_fire_threshold_flag():
    assert assess_fire(25, 10, True, True).exceeds_nfpa855_threshold
    small = assess_fire(10, 10, True, True)
    assert not small.exceeds_nfpa855_threshold and small.flags == []


def test_layout_places_every_pad_without_overlap():
    lay = plan_layout(80, 80, 7, 1.5, 2, 1, 3, 10, 10, 6, 10, True)
    pads = lay.pads
    assert len(pads) == 7
    for i, a in enumerate(pads):
        for b in pads[i + 1:]:
            assert a.x2 <= b.x or b.x2 <= a.x or a.y2 <= b.y or b.y2 <= a.y
    bat = lay.get("Battery charging / storage room")
    assert all(bat.x - p.x2 >= 10 - 1e-9 for p in pads)
    assert lay.fits


def test_layout_reports_too_small_site():
    lay = plan_layout(10, 10, 6, 1.5, 2, 1, 3, 10, 10, 6, 10, True)
    assert not lay.fits
    assert "<svg" in lay.to_svg()


def test_proposed_beats_baseline_on_long_term_categories():
    proposed, baseline = compare_with_baseline(HubInputs())
    p, b = proposed.scores(), baseline.scores()
    for cat in ("Safety", "Weather", "Night", "Noise", "Fire"):
        assert p[cat] > b[cat], cat
    assert proposed.availability.availability > baseline.availability.availability


def test_inputs_round_trip_and_reject_unknown_fields():
    inputs = HubInputs()
    assert HubInputs.from_dict(inputs.to_dict()) == inputs
    with pytest.raises(ValueError):
        HubInputs.from_dict({"site": {"widht_m": 3}})


def test_summary_is_json_serialisable():
    import json

    json.dumps(evaluate(HubInputs()).summary())


# --- reference aircraft ---------------------------------------------------

from hub.aircraft_library import LIBRARY, facts, profile_for, provenance  # noqa: E402
from hub.models import AircraftProfile, AirspaceProfile, Obstacle, SensitiveZone  # noqa: E402
from hub.sources import SOURCES  # noqa: E402


def test_every_library_source_is_registered():
    for entry in LIBRARY.values():
        for _, srcs, _ in entry["values"].values():
            assert all(s in SOURCES for s in srcs)
        for _, _, srcs in entry["facts"]:
            assert all(s in SOURCES for s in srcs)


def test_every_library_field_exists_on_profile():
    names = {f for f in AircraftProfile.__dataclass_fields__}
    for entry in LIBRARY.values():
        assert set(entry["values"]) <= names


def test_reference_values_convert_units():
    p = profile_for("zipline_p2")
    assert p.cruise_altitude_m == pytest.approx(330 * 0.3048)
    assert p.max_range_km == pytest.approx(2 * 10 * 1.609344)
    assert p.battery_mode == "onboard"


def test_provenance_marks_placeholders_and_overrides():
    rows = {r["field"]: r for r in provenance("zipline_p2", profile_for("zipline_p2", cruise_speed_mps=20.0))}
    assert rows["span_m"]["basis"] == "placeholder"
    assert rows["cruise_speed_mps"]["basis"] == "user input"
    assert rows["max_range_km"]["confidence"] == "2+ sources"
    assert facts("amazon_mk30")


def test_reference_id_in_inputs_fills_and_overrides():
    i = HubInputs.from_dict({"aircraft": {"reference_id": "amazon_mk30", "span_m": 2.0}})
    assert i.aircraft.span_m == 2.0
    assert i.aircraft.hover_noise_dba == 70.0
    with pytest.raises(ValueError):
        HubInputs.from_dict({"aircraft": {"reference_id": "no_such_drone"}})


# --- flight paths -----------------------------------------------------------

from hub.flightpath import (  # noqa: E402
    altitude_at, assess_heading, mean_detour_m, plan_flight_paths, transition_distance_m,
)


def _ac(**kw):
    base = dict(cruise_altitude_m=50, vertical_climb_m=10, climb_rate_mps=2, climb_ground_speed_mps=10)
    base.update(kw)
    return AircraftProfile(**base)


def test_climb_profile():
    ac = _ac()
    assert altitude_at(0, ac) == 10
    assert altitude_at(100, ac) == pytest.approx(30)
    assert altitude_at(1000, ac) == 50
    assert transition_distance_m(ac) == pytest.approx(200)


def test_obstacle_in_lane_blocks_only_that_heading():
    air = AirspaceProfile(obstacles=[Obstacle("Tower", 90, 50, 40, 5)], zones=[], obstacle_clearance_m=5)
    ac = _ac()
    assert not assess_heading(90, ac, air).clear  # 20 m altitude at 50 m < 45 m needed
    assert assess_heading(270, ac, air).clear
    assert assess_heading(0, ac, air).clear


def test_low_overflight_counted_inside_sector_only():
    zone = SensitiveZone("Homes", "residential", 80, 100, 0, 100, 40)
    air = AirspaceProfile(obstacles=[], zones=[zone])
    ac = _ac()
    inside = assess_heading(90, ac, air).low_overflight_m["Homes"]
    assert inside == pytest.approx(100, abs=5)  # below 40 m until x = 150 m, zone ends at 100 m
    assert assess_heading(270, ac, air).low_overflight_m == {}


def test_sector_wraps_through_north():
    zone = SensitiveZone("North", "people", 350, 10, 0, 500, 1000)
    air = AirspaceProfile(obstacles=[], zones=[zone])
    assert assess_heading(0, _ac(), air).low_overflight_m
    assert not assess_heading(180, _ac(), air).low_overflight_m


def test_more_corridors_reduce_detour():
    one = mean_detour_m([0], 200, 5000)
    four = mean_detour_m([0, 90, 180, 270], 200, 5000)
    assert four < one
    assert four > 0


def test_planner_avoids_blocked_and_low_headings():
    obstacles = [Obstacle("Store", 180, 30, 15, 80)]
    zones = [SensitiveZone("Homes", "residential", 45, 135, 0, 300, 60)]
    air = AirspaceProfile(obstacles=obstacles, zones=zones, min_corridors=2)
    fp = plan_flight_paths(_ac(), air, sorties_per_hour=20, service_radius_km=5)
    assert fp.enough_corridors
    for c in fp.corridors:
        assert not (135 <= c.heading_deg <= 225)
        assert not (45 <= c.heading_deg <= 135)
    assert fp.low_overflight_m == 0
    assert "<svg" in fp.to_map_svg(air, _ac()) and "<svg" in fp.to_profile_svg(air, _ac())


def test_tempo_drives_corridor_count():
    air = AirspaceProfile(obstacles=[], zones=[], min_corridors=1, movement_spacing_s=60, max_corridor_utilization=0.5)
    fp = plan_flight_paths(_ac(), air, sorties_per_hour=60, service_radius_km=5)
    # 120 movements/h, 30 per corridor -> 4 corridors
    assert fp.corridors_required == 4 and len(fp.corridors) == 4


def test_detour_feeds_capacity():
    d = evaluate(HubInputs())
    assert d.flight_paths.mean_detour_m > 0
    base = size_capacity(d.inputs.aircraft, d.inputs.demand, d.inputs.design)
    assert d.capacity.flight_time_s > base.flight_time_s
