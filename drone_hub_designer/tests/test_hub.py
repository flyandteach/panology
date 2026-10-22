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
