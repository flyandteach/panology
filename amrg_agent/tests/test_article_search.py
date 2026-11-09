import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents import article_search

SAMPLE_WORK = {
    "id": "https://openalex.org/W123",
    "title": "Noise Modeling for eVTOL Aircraft in Urban Environments",
    "display_name": "Noise Modeling for eVTOL Aircraft in Urban Environments",
    "doi": "https://doi.org/10.1234/evtol.noise",
    "publication_year": 2025,
    "publication_date": "2025-10-01",
    "cited_by_count": 3,
    "authorships": [
        {
            "author": {"display_name": "Jane Doe"},
            "institutions": [{"display_name": "MIT"}, {"display_name": "NASA Ames"}],
        },
        {"author": {"display_name": "John Smith"}, "institutions": []},
    ],
    "primary_location": {
        "landing_page_url": "https://journal.example.com/articles/123",
        "is_oa": True,
        "pdf_url": "https://journal.example.com/articles/123.pdf",
        "source": {"display_name": "Journal of Air Transportation"},
    },
    "best_oa_location": {"pdf_url": "https://repo.example.com/123_oa.pdf"},
    "open_access": {"is_oa": True, "oa_url": "https://oa.example.com/123"},
    "abstract_inverted_index": {
        "eVTOL": [0], "noise": [1], "is": [2], "a": [3], "key": [4], "concern": [5],
    },
}


def test_reconstruct_abstract_orders_by_position():
    assert article_search._reconstruct_abstract(SAMPLE_WORK["abstract_inverted_index"]) == (
        "eVTOL noise is a key concern"
    )


def test_reconstruct_abstract_handles_missing_index():
    assert article_search._reconstruct_abstract(None) == ""
    assert article_search._reconstruct_abstract({}) == ""


def test_format_authors_includes_institutions_when_present():
    authors = article_search._format_authors(SAMPLE_WORK["authorships"])
    assert authors == ["Jane Doe (MIT, NASA Ames)", "John Smith"]


def test_format_authors_handles_empty_list():
    assert article_search._format_authors([]) == []
    assert article_search._format_authors(None) == []


def test_best_pdf_url_prefers_best_oa_location():
    assert article_search._best_pdf_url(SAMPLE_WORK) == "https://repo.example.com/123_oa.pdf"


def test_best_pdf_url_falls_back_to_open_access_oa_url():
    work = {"primary_location": {}, "open_access": {"oa_url": "https://oa.example.com/only"}}
    assert article_search._best_pdf_url(work) == "https://oa.example.com/only"


def test_best_pdf_url_empty_when_no_oa_signal():
    assert article_search._best_pdf_url({}) == ""


def test_source_url_prefers_landing_page_then_doi_then_id():
    assert article_search._source_url(SAMPLE_WORK) == "https://journal.example.com/articles/123"
    assert article_search._source_url({"doi": "https://doi.org/10.1/x"}) == "https://doi.org/10.1/x"
    assert article_search._source_url({"id": "https://openalex.org/W999"}) == "https://openalex.org/W999"


def test_normalize_result_shape():
    result = article_search._normalize_result(SAMPLE_WORK, "eVTOL")
    assert result["topic"] == "eVTOL"
    assert result["title"] == "Noise Modeling for eVTOL Aircraft in Urban Environments"
    assert result["venue"] == "Journal of Air Transportation"
    assert result["pub_year"] == 2025
    assert result["pdf_url"] == "https://repo.example.com/123_oa.pdf"
    assert result["source_url"] == "https://journal.example.com/articles/123"
    assert result["num_citations"] == 3
    assert "eVTOL noise" in result["abstract"]


def test_has_public_fulltext():
    assert article_search.has_public_fulltext({"pdf_url": "https://x.com/a.pdf"}) is True
    assert article_search.has_public_fulltext({"pdf_url": ""}) is False
    assert article_search.has_public_fulltext({}) is False


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_search_all_topics_marks_rate_limit_as_blocked(monkeypatch):
    def fake_get(*args, **kwargs):
        return _FakeResponse(429, text="rate limited")

    monkeypatch.setattr(article_search.requests, "get", fake_get)
    report = article_search.search_all_topics(topics={"eVTOL": "eVTOL aircraft"})
    assert report["eVTOL"]["blocked"] is True
    assert report["eVTOL"]["results"] == []


def test_search_all_topics_surfaces_other_errors_without_blocking(monkeypatch):
    def fake_get(*args, **kwargs):
        return _FakeResponse(500, text="server error")

    monkeypatch.setattr(article_search.requests, "get", fake_get)
    report = article_search.search_all_topics(topics={"eVTOL": "eVTOL aircraft"})
    assert report["eVTOL"]["blocked"] is False
    assert report["eVTOL"]["error"] is not None


def test_search_all_topics_returns_normalized_results_on_success(monkeypatch):
    def fake_get(*args, **kwargs):
        return _FakeResponse(200, payload={"results": [SAMPLE_WORK]})

    monkeypatch.setattr(article_search.requests, "get", fake_get)
    report = article_search.search_all_topics(topics={"eVTOL": "eVTOL aircraft"})
    assert report["eVTOL"]["blocked"] is False
    assert report["eVTOL"]["error"] is None
    assert len(report["eVTOL"]["results"]) == 1
    assert report["eVTOL"]["results"][0]["title"].startswith("Noise Modeling")
