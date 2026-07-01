from unittest.mock import patch

from parcel_agent import site_report as site_report_mod
from parcel_agent.models import (
    AirportDistance, GeocodeResult, ParcelResult, PLSSDescription, PLSSResult,
)


def _agent():
    return site_report_mod.SiteReportAgent()


def test_address_path_prefers_geocoded_lat_lon():
    text = "Property Address: 400 Broad St, Seattle, WA 98109\nNo other location info."
    geo = GeocodeResult(found=True, input_address="400 Broad St, Seattle, WA 98109",
                         lat=47.6205, lon=-122.3493, county_name="King", state_abbr="WA",
                         county_fips="53033", source="census_oneline")
    parcel = ParcelResult(found=True, apn="123-456", confidence="high", geocode=geo)

    with patch.object(site_report_mod.ParcelLookupAgent, "lookup", return_value=parcel), \
         patch.object(site_report_mod.airports_mod, "nearest_airports",
                       return_value=([AirportDistance(ident="KSEA", name="Sea-Tac", lat=47.44, lon=-122.30,
                                                       distance_nm=5.0, distance_mi=5.75)], True)):
        report = _agent().run_from_text(text)

    assert report.found
    assert report.location_source == "address"
    assert report.lat == 47.6205
    assert len(report.nearest_airports) == 1
    assert report.airport_data_is_public_use_verified is True


def test_plss_path_used_when_no_address():
    text = "Legal description: SW 1/4 Section 12, T 33 N, R 21 E, WM. No street address assigned."
    plss_desc = PLSSDescription(raw_text="SW 1/4 Section 12, T 33 N, R 21 E, WM", section=12,
                                 township_number=33, township_dir="N", range_number=21, range_dir="E",
                                 meridian="WM", aliquot_parts=["SW"])
    plss_result = PLSSResult(found=True, description=plss_desc, lat=47.60, lon=-122.35,
                              confidence="aliquot_approx_within_section")
    county_geo = GeocodeResult(found=True, input_address="", lat=47.60, lon=-122.35,
                                county_name="King", state_abbr="WA", county_fips="53033",
                                source="census_coordinates")
    parcel = ParcelResult(found=True, apn="789", confidence="medium")

    with patch.object(site_report_mod.plss_mod, "resolve_plss", return_value=plss_result), \
         patch.object(site_report_mod, "geocode_census_coordinates", return_value=county_geo), \
         patch.object(site_report_mod.ParcelLookupAgent, "lookup_at_point", return_value=parcel), \
         patch.object(site_report_mod.airports_mod, "nearest_airports", return_value=([], False)):
        report = _agent().run_from_text(text)

    assert report.found
    assert report.location_source == "plss"
    assert report.lat == 47.60
    assert report.parcel.apn == "789"


def test_no_location_found_reports_failure():
    text = "This document has no address, PLSS description, or parcel number."
    report = _agent().run_from_text(text)
    assert not report.found
    assert report.error
