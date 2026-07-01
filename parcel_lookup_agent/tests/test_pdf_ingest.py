from parcel_agent.pdf_ingest import extract_location

SAMPLE = """
SITE REVIEW MEMORANDUM

Property Address: 18740 Meridian Ave N, Shoreline, WA 98133

Tax Parcel Number: 3626049001

The subject property is legally described as the SW 1/4 of Section 12,
T 33 N, R 21 E, WM, located in Skagit County, Washington.
"""

PLSS_ONLY = """
Legal description: NE 1/4 Section 9, T 15 N, R 30 E, B.M., Clackamas County, Oregon.
No street address has been assigned to this parcel.
"""


def test_extract_location_finds_all_fields():
    loc = extract_location(SAMPLE)
    assert loc.address == "18740 Meridian Ave N, Shoreline, WA 98133"
    assert loc.apn == "3626049001"
    assert loc.plss is not None
    assert loc.plss.section == 12
    assert loc.county_hint == "Skagit"
    assert loc.state_hint == "WA"


def test_extract_location_plss_only_no_address():
    loc = extract_location(PLSS_ONLY)
    assert loc.address is None
    assert loc.plss is not None
    assert loc.plss.section == 9
    assert loc.plss.meridian == "BM"
    assert loc.county_hint == "Clackamas"
    assert loc.state_hint == "OR"


def test_extract_location_empty_text():
    loc = extract_location("nothing useful here")
    assert loc.address is None
    assert loc.plss is None
    assert loc.apn is None
