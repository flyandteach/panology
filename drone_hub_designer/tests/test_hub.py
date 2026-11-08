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


# --- costs --------------------------------------------------------------------

from hub.costs import capital_recovery_factor  # noqa: E402
from hub.models import CostInputs  # noqa: E402


def test_capital_recovery_factor():
    assert capital_recovery_factor(0, 10) == pytest.approx(0.1)
    # Standard table value: 8 % over 20 years -> 0.10185
    assert capital_recovery_factor(0.08, 20) == pytest.approx(0.10185, abs=1e-5)


def test_missing_prices_are_reported_not_free():
    d = evaluate(HubInputs())
    assert "Aircraft" in d.costs.missing
    assert d.costs.capital_total == 0
    assert d.costs.operating_annual > 0  # electricity has a default rate


def test_costs_scale_with_quantities():
    costs = CostInputs(aircraft_unit_cost=1000, pad_or_dock_cost=500, discount_rate=0,
                       aircraft_life_years=5, infrastructure_life_years=10, electricity_price_per_kwh=0)
    d = evaluate(HubInputs(costs=costs))
    c = d.costs
    expected = d.capacity.aircraft_required * 1000 + d.capacity.pads_required * 500
    assert c.capital_total == pytest.approx(expected)
    assert c.annualised_capital == pytest.approx(d.capacity.aircraft_required * 1000 / 5
                                                 + d.capacity.pads_required * 500 / 10)
    assert c.cost_per_delivery == pytest.approx(c.annualised_capital / c.annual_deliveries)


def test_baseline_has_no_barrier_or_building_lines():
    _, baseline = compare_with_baseline(HubInputs())
    items = {line.item for line in baseline.costs.lines}
    assert "Noise barrier" not in items and "Operations building" not in items
    assert "Storage container" in items


# --- map site: geometry, OSM, KML ---------------------------------------------

from hub.geo import (  # noqa: E402
    derive_site, from_local, layout_shapes, min_area_rectangle, polygon_sector, to_local,
)
from hub.kml import export_geojson, export_kml, import_kml  # noqa: E402
from hub.osm import features_from_overpass, overpass_query, parse_height_m  # noqa: E402

HUB = (35.0, -80.0)


def _ll(x, y):
    return list(from_local(x, y, HUB))


def test_local_projection_round_trip_and_scale():
    lat, lon = from_local(100.0, 200.0, HUB)
    x, y = to_local(lat, lon, HUB)
    assert x == pytest.approx(100.0, abs=1e-6) and y == pytest.approx(200.0, abs=1e-6)
    # One degree of latitude is about 111.2 km on the mean-radius sphere.
    assert to_local(HUB[0] + 1, HUB[1], HUB)[1] == pytest.approx(111_195, rel=1e-3)


def test_min_area_rectangle_of_rotated_rectangle():
    import math as m
    t = m.radians(30)
    corners = [(0, 0), (60, 0), (60, 40), (0, 40)]
    rot = [(x * m.cos(t) - y * m.sin(t), x * m.sin(t) + y * m.cos(t)) for x, y in corners]
    r = min_area_rectangle(rot)
    assert sorted([r.a_m, r.b_m]) == pytest.approx([40, 60])


def test_polygon_sector_outside_and_around_origin():
    square = [(90, -10), (110, -10), (110, 10), (90, 10)]  # due east
    b_from, b_to, inner, outer = polygon_sector(square)
    assert inner == pytest.approx(90)
    assert outer == pytest.approx((110**2 + 10**2) ** 0.5)
    assert b_from == pytest.approx(90 - 6.34, abs=0.2) and b_to == pytest.approx(90 + 6.34, abs=0.2)
    north = [(-10, 90), (10, 90), (10, 110), (-10, 110)]  # straddles 0 degrees
    b_from, b_to, _, _ = polygon_sector(north)
    assert b_from > 350 and b_to < 10
    around = [(-5, -5), (5, -5), (5, 5), (-5, 5)]
    assert polygon_sector(around)[:3] == (0.0, 359.99, 0.0)


def test_derive_site_from_drawn_map():
    geo = {
        "version": 1, "hub": list(HUB), "store": _ll(0, -80),
        "lot": [_ll(-35, -30), _ll(35, -30), _ll(35, 30), _ll(-35, 30)],  # 70 wide (E-W), 60 deep (N-S)
        "obstacles": [{"name": "Pole", "lat": _ll(50, 0)[0], "lon": _ll(50, 0)[1], "height_m": 12, "width_m": 1}],
        "zones": [{"name": "Homes", "kind": "residential", "min_overflight_m": 45,
                   "polygon": [_ll(-50, 150), _ll(50, 150), _ll(50, 300), _ll(-50, 300)]}],
    }
    d = derive_site(geo)
    assert d.airspace["store_bearing_deg"] == pytest.approx(180, abs=0.5)
    assert d.site["width_m"] == pytest.approx(70, abs=0.5)
    assert d.site["depth_m"] == pytest.approx(60, abs=0.5)
    assert d.site["nearest_receptor_m"] == pytest.approx(150, abs=0.5)
    ob = d.airspace["obstacles"][0]
    assert ob["bearing_deg"] == pytest.approx(90, abs=0.5) and ob["distance_m"] == pytest.approx(50, abs=0.5)
    z = d.airspace["zones"][0]
    assert z["bearing_from_deg"] > 340 and z["bearing_to_deg"] < 20


def test_zone_around_hub_starts_at_lot_edge():
    lot = [_ll(-30, -20), _ll(30, -20), _ll(30, 20), _ll(-30, 20)]
    parking = {"name": "Parking", "kind": "people", "min_overflight_m": 30,
               "polygon": [_ll(-100, -100), _ll(100, -100), _ll(100, 100), _ll(-100, 100)]}
    d = derive_site({"version": 1, "hub": list(HUB), "store": None, "lot": lot, "obstacles": [], "zones": [parking]})
    z = d.airspace["zones"][0]
    assert z["inner_m"] == pytest.approx(20, abs=0.5)  # nearest lot edge
    assert z["bearing_to_deg"] - z["bearing_from_deg"] > 359


def test_derived_site_runs_through_engine():
    geo = {"version": 1, "hub": list(HUB), "store": _ll(0, -80),
           "lot": [_ll(-40, -30), _ll(40, -30), _ll(40, 35), _ll(-40, 35)], "obstacles": [], "zones": []}
    d = derive_site(geo)
    data = HubInputs().to_dict()
    data["site"].update(d.site)
    data["airspace"].update(d.airspace)
    design = evaluate(HubInputs.from_dict(data))
    assert design.layout.site_w == pytest.approx(80, abs=0.5)
    shapes = layout_shapes(design.layout, HUB, 0.0)
    apron = next(s for s in shapes if s["kind"] == "apron")
    lats = [p[0] for p in apron["polygon"]]
    assert min(lats) < HUB[0] < max(lats)  # apron centred on the hub


def test_parse_osm_height_tags():
    assert parse_height_m("12") == 12
    assert parse_height_m("12.5 m") == 12.5
    assert parse_height_m("40 ft") == pytest.approx(12.192)
    assert parse_height_m("tall") is None


def _way(i, tags, pts):
    return {"type": "way", "id": i, "tags": tags, "geometry": [{"lat": a, "lon": b} for a, b in pts]}


def test_overpass_features():
    sq = lambda x, y, s: [_ll(x, y), _ll(x + s, y), _ll(x + s, y + s), _ll(x, y + s)]  # noqa: E731
    data = {"elements": [
        _way(1, {"building": "retail", "height": "9"}, sq(-50, -100, 40)),
        _way(2, {"building": "house", "building:levels": "2"}, sq(100, 100, 10)),
        _way(3, {"building": "yes"}, sq(-100, 50, 10)),
        _way(4, {"amenity": "parking"}, sq(-60, -60, 120)),  # contains the hub
        _way(5, {"amenity": "school", "name": "Elm School"}, sq(300, 0, 80)),
        _way(6, {"landuse": "residential"}, sq(0, 400, 200)),
        {"type": "node", "id": 7, "lat": _ll(0, 80)[0], "lon": _ll(0, 80)[1], "tags": {"man_made": "mast"}},
        {"type": "node", "id": 8, "lat": _ll(0, 90)[0], "lon": _ll(0, 90)[1],
         "tags": {"power": "tower", "height": "30"}},
    ]}
    obstacles, zones, notes = features_from_overpass(data, HUB)
    by_src = {o["source"].split(",")[0]: o for o in obstacles}
    assert by_src["OSM way 1"]["height_m"] == 9
    assert by_src["OSM way 2"]["height_m"] == 6.0 and "estimated" in by_src["OSM way 2"]["source"]
    assert "assumed" in by_src["OSM way 3"]["source"]
    assert by_src["OSM node 8"]["height_m"] == 30
    assert "OSM node 7" not in by_src  # mast without height is skipped, and noted
    kinds = sorted(z["kind"] for z in zones)
    assert kinds == ["people", "residential", "residential", "school"]  # parking, landuse, house, school
    assert any("inside a mapped parking area" in n for n in notes)
    assert any("Skipped 1" in n for n in notes)
    assert "around:400" in overpass_query(*HUB)


KML_SAMPLE = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Hub</name><Point><coordinates>{HUB[1]},{HUB[0]},0</coordinates></Point></Placemark>
<Placemark><name>Store</name><Point><coordinates>{_ll(0, -80)[1]},{_ll(0, -80)[0]},0</coordinates></Point></Placemark>
<Placemark><name>Light pole 40 ft</name><Point><coordinates>{_ll(30, 0)[1]},{_ll(30, 0)[0]},0</coordinates></Point></Placemark>
<Placemark><name>Lot</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
{" ".join(f"{lon},{lat},0" for lat, lon in [_ll(-35, -30), _ll(35, -30), _ll(35, 30), _ll(-35, 30), _ll(-35, -30)])}
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Houses on Oak St</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
{" ".join(f"{lon},{lat},0" for lat, lon in [_ll(-50, 150), _ll(50, 150), _ll(50, 300), _ll(-50, 150)])}
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
</Document></kml>"""


def test_kml_import():
    geo, notes = import_kml(KML_SAMPLE.encode())
    assert geo["hub"] == pytest.approx(list(HUB))
    assert geo["store"] is not None
    assert len(geo["lot"]) == 4  # closing point dropped
    assert geo["obstacles"][0]["height_m"] == pytest.approx(12.192, abs=0.05)
    assert geo["zones"][0]["kind"] == "residential"


def test_kmz_import():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("doc.kml", KML_SAMPLE)
    geo, _ = import_kml(buf.getvalue())
    assert geo["hub"] is not None


def test_kml_and_geojson_export_round_trip():
    import json as js
    geo, _ = import_kml(KML_SAMPLE.encode())
    d = derive_site(geo)
    data = HubInputs().to_dict()
    data["site"].update(d.site)
    data["airspace"].update(d.airspace)
    design = evaluate(HubInputs.from_dict(data))
    kml = export_kml(design, geo)
    again, _ = import_kml(kml.encode())
    assert again["hub"] == pytest.approx(list(HUB), abs=1e-6)
    gj = js.loads(export_geojson(design, geo))
    layers = {f["properties"]["layer"] for f in gj["features"]}
    assert {"hub", "lot", "layout", "corridor", "obstacle", "zone"} <= layers
