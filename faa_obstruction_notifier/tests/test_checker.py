from faa_notifier import checker

NPF_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<caseData><OECase><caseId>691612871</caseId>"
    "<asn>2026-ANM-456-OE</asn><statusCode>NPF</statusCode>"
    "<year>2026</year></OECase></caseData>"
)

HLD_EVAL_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<caseData><OECase><statusCode>HLD-Eval</statusCode></OECase></caseData>"
)


def test_extract_status_code_from_real_shape():
    assert checker._extract_status_code(NPF_XML) == "NPF"
    assert checker._extract_status_code(HLD_EVAL_XML) == "HLD-Eval"


def test_extract_status_code_no_match():
    assert checker._extract_status_code("<caseData><OECase></OECase></caseData>") is None


def test_extract_status_code_not_xml():
    assert checker._extract_status_code("not xml at all") is None


def test_known_status_labels_match_confirmed_pdfs():
    assert checker.KNOWN_STATUS_LABELS["NPF"] == "Pending"
    assert checker.KNOWN_STATUS_LABELS["HLD-Eval"] == "Evaluating"


def test_is_likely_terminal():
    assert checker.is_likely_terminal("DNH")
    assert checker.is_likely_terminal("DOH")
    assert checker.is_likely_terminal("TERMINATED")
    assert not checker.is_likely_terminal("NPF")
    assert not checker.is_likely_terminal("HLD-Eval")
