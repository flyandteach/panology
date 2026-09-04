from faa_notifier import checker


def test_extract_status_plain_text():
    assert checker._extract_status("Status: Pending") == "Pending"


def test_extract_status_json():
    body = '{"caseStatus": "Determined", "asn": "2026-ANM-456-OE"}'
    assert checker._extract_status(body) == "Determined"


def test_extract_status_case_insensitive():
    assert checker._extract_status("current status is EVALUATING now") == "Evaluating"


def test_extract_status_none_found():
    assert checker._extract_status("no relevant keywords here") is None


def test_is_terminal():
    assert checker.is_terminal("Determined")
    assert checker.is_terminal("denied")
    assert not checker.is_terminal("Pending")
    assert not checker.is_terminal("Evaluating")
